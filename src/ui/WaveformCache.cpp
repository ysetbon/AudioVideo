#include "WaveformCache.h"
#include "media/Demuxer.h"
#include "media/AudioDecoder.h"
#include "media/Resampler.h"
#include <QCryptographicHash>
#include <QDir>
#include <QFile>
#include <QDataStream>
#include <QtConcurrent>
#include <algorithm>
#include <cmath>

namespace ClipTune {

void WaveformData::getPeaksForRange(double startTime, double endTime, int numBuckets,
                                    std::vector<float>& outMin, std::vector<float>& outMax) const
{
    outMin.resize(numBuckets);
    outMax.resize(numBuckets);

    if (minPeaks.empty() || numBuckets <= 0) {
        std::fill(outMin.begin(), outMin.end(), 0.0f);
        std::fill(outMax.begin(), outMax.end(), 0.0f);
        return;
    }

    double bucketDuration = (endTime - startTime) / numBuckets;
    double secondsPerSourceBucket = static_cast<double>(samplesPerBucket) / sampleRate;

    for (int i = 0; i < numBuckets; ++i) {
        double t0 = startTime + i * bucketDuration;
        double t1 = t0 + bucketDuration;

        // Map to source buckets
        int srcStart = static_cast<int>(t0 / secondsPerSourceBucket);
        int srcEnd = static_cast<int>(t1 / secondsPerSourceBucket) + 1;

        srcStart = std::clamp(srcStart, 0, static_cast<int>(minPeaks.size()) - 1);
        srcEnd = std::clamp(srcEnd, srcStart + 1, static_cast<int>(minPeaks.size()));

        float minVal = 0.0f;
        float maxVal = 0.0f;

        for (int j = srcStart; j < srcEnd; ++j) {
            minVal = std::min(minVal, minPeaks[j]);
            maxVal = std::max(maxVal, maxPeaks[j]);
        }

        outMin[i] = minVal;
        outMax[i] = maxVal;
    }
}

WaveformCache::WaveformCache(QObject* parent)
    : QObject(parent)
{
}

WaveformCache::~WaveformCache() = default;

const WaveformData* WaveformCache::getWaveform(const QString& filePath)
{
    std::lock_guard<std::mutex> lock(m_mutex);

    auto it = m_cache.find(filePath);
    if (it != m_cache.end()) {
        return it->second.get();
    }

    // Check if already generating
    if (m_generating.count(filePath) > 0) {
        return nullptr;
    }

    // Try loading from disk
    if (loadFromDisk(filePath)) {
        return m_cache[filePath].get();
    }

    // Start async generation
    m_generating.insert(filePath);

    QtConcurrent::run([this, filePath]() {
        bool success = false;

        // Generate waveform
        Demuxer demuxer;
        if (demuxer.open(filePath) && demuxer.info().hasAudio) {
            AudioDecoder decoder;
            if (decoder.init(demuxer)) {
                AudioFormat srcFormat;
                srcFormat.sampleRate = decoder.sampleRate();
                srcFormat.channels = decoder.channels();
                srcFormat.sampleFormat = decoder.sampleFormat();
                if (auto* layout = decoder.channelLayout()) {
                    av_channel_layout_copy(&srcFormat.channelLayout, layout);
                }

                // Resample to mono for waveform
                AudioFormat dstFormat;
                dstFormat.sampleRate = 22050;  // Lower rate for waveform
                dstFormat.channels = 1;
                dstFormat.sampleFormat = AV_SAMPLE_FMT_FLT;
                dstFormat.channelLayout = AV_CHANNEL_LAYOUT_MONO;

                Resampler resampler;
                if (resampler.init(srcFormat, dstFormat)) {
                    auto data = std::make_unique<WaveformData>();
                    data->sampleRate = dstFormat.sampleRate;
                    data->channels = 1;
                    data->samplesPerBucket = 512;
                    data->duration = demuxer.info().duration;

                    std::vector<float> allSamples;
                    allSamples.reserve(static_cast<size_t>(data->duration * dstFormat.sampleRate));

                    // Decode all audio
                    while (auto pkt = demuxer.readAudioPacket()) {
                        auto frames = decoder.decodePacket(pkt->get());
                        for (auto& frame : frames) {
                            auto samples = resampler.resample(frame.get());
                            allSamples.insert(allSamples.end(), samples.begin(), samples.end());
                        }
                    }

                    // Compute peaks
                    size_t numBuckets = (allSamples.size() + data->samplesPerBucket - 1) / data->samplesPerBucket;
                    data->minPeaks.resize(numBuckets);
                    data->maxPeaks.resize(numBuckets);

                    for (size_t b = 0; b < numBuckets; ++b) {
                        size_t start = b * data->samplesPerBucket;
                        size_t end = std::min(start + data->samplesPerBucket, allSamples.size());

                        float minVal = 0.0f;
                        float maxVal = 0.0f;
                        for (size_t i = start; i < end; ++i) {
                            minVal = std::min(minVal, allSamples[i]);
                            maxVal = std::max(maxVal, allSamples[i]);
                        }
                        data->minPeaks[b] = minVal;
                        data->maxPeaks[b] = maxVal;
                    }

                    {
                        std::lock_guard<std::mutex> lock(m_mutex);
                        m_cache[filePath] = std::move(data);
                        saveToDisk(filePath, *m_cache[filePath]);
                    }
                    success = true;
                }
            }
        }

        {
            std::lock_guard<std::mutex> lock(m_mutex);
            m_generating.erase(filePath);
        }

        if (success) {
            emit waveformReady(filePath);
        } else {
            emit waveformError(filePath, QStringLiteral("Failed to generate waveform"));
        }
    });

    return nullptr;
}

bool WaveformCache::hasCachedWaveform(const QString& filePath) const
{
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_cache.find(filePath) != m_cache.end();
}

bool WaveformCache::generateWaveform(const QString& filePath)
{
    // This is a simplified synchronous version
    auto* waveform = getWaveform(filePath);
    return waveform != nullptr;
}

void WaveformCache::generateWaveformAsync(const QString& filePath)
{
    getWaveform(filePath);
}

void WaveformCache::clear()
{
    std::lock_guard<std::mutex> lock(m_mutex);
    m_cache.clear();
}

void WaveformCache::remove(const QString& filePath)
{
    std::lock_guard<std::mutex> lock(m_mutex);
    m_cache.erase(filePath);
}

bool WaveformCache::loadFromDisk(const QString& filePath)
{
    QString cachePath = getCacheFilePath(filePath);
    QFile file(cachePath);

    if (!file.open(QIODevice::ReadOnly)) {
        return false;
    }

    QDataStream stream(&file);
    stream.setVersion(QDataStream::Qt_6_0);

    quint32 magic;
    stream >> magic;
    if (magic != 0x57415645) {  // "WAVE"
        return false;
    }

    auto data = std::make_unique<WaveformData>();
    stream >> data->samplesPerBucket >> data->sampleRate >> data->channels >> data->duration;

    quint32 numBuckets;
    stream >> numBuckets;

    data->minPeaks.resize(numBuckets);
    data->maxPeaks.resize(numBuckets);

    for (quint32 i = 0; i < numBuckets; ++i) {
        stream >> data->minPeaks[i] >> data->maxPeaks[i];
    }

    if (stream.status() != QDataStream::Ok) {
        return false;
    }

    m_cache[filePath] = std::move(data);
    return true;
}

bool WaveformCache::saveToDisk(const QString& filePath, const WaveformData& data)
{
    if (m_cacheDir.isEmpty()) return false;

    QDir().mkpath(m_cacheDir);
    QString cachePath = getCacheFilePath(filePath);
    QFile file(cachePath);

    if (!file.open(QIODevice::WriteOnly)) {
        return false;
    }

    QDataStream stream(&file);
    stream.setVersion(QDataStream::Qt_6_0);

    stream << quint32(0x57415645);  // "WAVE"
    stream << data.samplesPerBucket << data.sampleRate << data.channels << data.duration;
    stream << static_cast<quint32>(data.numBuckets());

    for (size_t i = 0; i < data.numBuckets(); ++i) {
        stream << data.minPeaks[i] << data.maxPeaks[i];
    }

    return stream.status() == QDataStream::Ok;
}

QString WaveformCache::getCacheFilePath(const QString& filePath) const
{
    QByteArray hash = QCryptographicHash::hash(filePath.toUtf8(), QCryptographicHash::Md5);
    return m_cacheDir + "/" + hash.toHex() + ".waveform";
}

} // namespace ClipTune
