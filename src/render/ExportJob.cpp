#include "ExportJob.h"
#include "media/Demuxer.h"
#include "media/VideoDecoder.h"
#include "media/Scaler.h"
#include <QFile>
#include <QDataStream>
#include <QCoreApplication>
#include <cmath>

namespace ClipTune {

ExportJob::ExportJob(Project* project, const ExportSettings& settings, QObject* parent)
    : QObject(parent)
    , m_project(project)
    , m_settings(settings)
{
    m_mixer.setProject(project);
    m_mixer.setSampleRate(settings.audioSettings.sampleRate);
    m_mixer.setChannels(settings.audioSettings.channels);
}

ExportJob::~ExportJob()
{
    cancel();
    if (m_thread) {
        m_thread->quit();
        m_thread->wait();
        delete m_thread;
    }
}

void ExportJob::start()
{
    if (m_running) return;

    m_running = true;
    m_cancelled = false;
    m_progress = 0.0;

    m_thread = new QThread();
    moveToThread(m_thread);

    connect(m_thread, &QThread::started, this, &ExportJob::doExport);
    connect(m_thread, &QThread::finished, m_thread, &QThread::deleteLater);

    m_thread->start();
    emit started();
}

void ExportJob::cancel()
{
    m_cancelled = true;
}

void ExportJob::doExport()
{
    bool success = false;
    QString message;

    try {
        if (m_settings.includeVideo && m_settings.includeAudio) {
            success = exportVideoAndAudio();
        } else if (m_settings.includeVideo) {
            success = exportVideoOnly();
        } else if (m_settings.includeAudio) {
            success = exportAudioOnly();
        } else {
            message = "No content to export";
        }

        if (success) {
            message = "Export completed successfully";
        } else if (m_cancelled) {
            message = "Export cancelled";
        } else if (message.isEmpty()) {
            message = "Export failed";
        }
    } catch (const std::exception& e) {
        success = false;
        message = QString("Export error: %1").arg(e.what());
    }

    m_running = false;
    m_progress = success ? 1.0 : m_progress.load();

    emit finished(success, message);

    // Move back to main thread
    moveToThread(QCoreApplication::instance()->thread());

    if (m_thread) {
        m_thread->quit();
    }
}

bool ExportJob::exportVideoAndAudio()
{
    Mp4Muxer muxer;

    if (!muxer.open(m_settings.outputPath, m_settings.videoSettings, m_settings.audioSettings)) {
        emit error("Failed to open output file");
        return false;
    }

    double duration = (m_settings.endTime > 0) ? m_settings.endTime : m_project->duration();
    duration -= m_settings.startTime;

    double frameRate = m_settings.videoSettings.frameRate;
    int64_t totalFrames = static_cast<int64_t>(duration * frameRate);
    int audioSamplesPerFrame = m_settings.audioSettings.sampleRate / static_cast<int>(frameRate);

    // Get first video track for video content
    auto videoTracks = m_project->videoTracks();
    Demuxer videoDemuxer;
    VideoDecoder videoDecoder;
    Scaler videoScaler;
    bool hasVideo = false;

    if (!videoTracks.empty() && !videoTracks[0]->clips().empty()) {
        auto& firstClip = videoTracks[0]->clips()[0];
        if (videoDemuxer.open(firstClip->mediaPath()) && videoDemuxer.info().hasVideo) {
            if (videoDecoder.init(videoDemuxer)) {
                videoScaler.init(videoDecoder.width(), videoDecoder.height(), videoDecoder.pixelFormat(),
                                 m_settings.videoSettings.width, m_settings.videoSettings.height,
                                 AV_PIX_FMT_RGB24);
                hasVideo = true;
            }
        }
    }

    std::vector<float> audioBuffer(audioSamplesPerFrame * m_settings.audioSettings.channels);
    std::vector<uint8_t> videoBuffer(m_settings.videoSettings.width * m_settings.videoSettings.height * 3);

    for (int64_t frame = 0; frame < totalFrames && !m_cancelled; ++frame) {
        double currentTime = m_settings.startTime + frame / frameRate;

        // Mix audio for this frame
        m_mixer.mix(currentTime, audioBuffer.data(), audioSamplesPerFrame);

        // Encode audio
        int64_t audioPts = frame * audioSamplesPerFrame;
        muxer.encodeAndWriteAudio(audioBuffer.data(), audioSamplesPerFrame, audioPts);

        // Get video frame (simplified - just use black frame if no video)
        if (hasVideo) {
            // Read and decode video frame at current time
            // This is simplified - a full implementation would handle seeking properly
            if (auto pkt = videoDemuxer.readVideoPacket()) {
                auto frames = videoDecoder.decodePacket(pkt->get());
                if (!frames.empty()) {
                    auto rgbFrame = videoScaler.scale(frames[0].get());
                    if (rgbFrame) {
                        muxer.encodeAndWriteVideo(rgbFrame->data[0],
                                                   m_settings.videoSettings.width,
                                                   m_settings.videoSettings.height,
                                                   frame);
                    }
                }
            }
        } else {
            // Black frame
            std::fill(videoBuffer.begin(), videoBuffer.end(), 0);
            muxer.encodeAndWriteVideo(videoBuffer.data(),
                                       m_settings.videoSettings.width,
                                       m_settings.videoSettings.height,
                                       frame);
        }

        m_progress = static_cast<double>(frame + 1) / totalFrames;
        emit progressChanged(m_progress);
    }

    muxer.finalize();
    muxer.close();

    return !m_cancelled;
}

bool ExportJob::exportVideoOnly()
{
    Mp4Muxer muxer;

    if (!muxer.openVideoOnly(m_settings.outputPath, m_settings.videoSettings)) {
        emit error("Failed to open output file");
        return false;
    }

    // Similar to above but without audio
    double duration = (m_settings.endTime > 0) ? m_settings.endTime : m_project->duration();
    duration -= m_settings.startTime;

    double frameRate = m_settings.videoSettings.frameRate;
    int64_t totalFrames = static_cast<int64_t>(duration * frameRate);

    std::vector<uint8_t> videoBuffer(m_settings.videoSettings.width * m_settings.videoSettings.height * 3, 0);

    for (int64_t frame = 0; frame < totalFrames && !m_cancelled; ++frame) {
        // TODO: Compose video frame
        muxer.encodeAndWriteVideo(videoBuffer.data(),
                                   m_settings.videoSettings.width,
                                   m_settings.videoSettings.height,
                                   frame);

        m_progress = static_cast<double>(frame + 1) / totalFrames;
        emit progressChanged(m_progress);
    }

    muxer.finalize();
    muxer.close();

    return !m_cancelled;
}

bool ExportJob::exportAudioOnly()
{
    double duration = (m_settings.endTime > 0) ? m_settings.endTime : m_project->duration();
    duration -= m_settings.startTime;

    return exportWav(m_project, m_settings.outputPath, m_settings.startTime, duration);
}

bool exportWav(Project* project, const QString& outputPath, double startTime, double endTime)
{
    if (!project) return false;

    Mixer mixer;
    mixer.setProject(project);
    mixer.setSampleRate(48000);
    mixer.setChannels(2);

    double duration = (endTime > 0) ? endTime - startTime : project->duration() - startTime;
    if (duration <= 0) return false;

    size_t totalSamples = static_cast<size_t>(duration * 48000) * 2;
    std::vector<float> audioData(totalSamples);

    // Mix all audio
    size_t framesPerBlock = 4096;
    size_t totalFrames = static_cast<size_t>(duration * 48000);
    size_t framesWritten = 0;

    while (framesWritten < totalFrames) {
        size_t framesToMix = std::min(framesPerBlock, totalFrames - framesWritten);
        double time = startTime + static_cast<double>(framesWritten) / 48000;

        mixer.mix(time, audioData.data() + framesWritten * 2, framesToMix);
        framesWritten += framesToMix;
    }

    // Write WAV file
    QFile file(outputPath);
    if (!file.open(QIODevice::WriteOnly)) {
        return false;
    }

    QDataStream stream(&file);
    stream.setByteOrder(QDataStream::LittleEndian);

    // Convert float to 16-bit PCM
    std::vector<int16_t> pcmData(totalSamples);
    for (size_t i = 0; i < totalSamples; ++i) {
        float sample = std::clamp(audioData[i], -1.0f, 1.0f);
        pcmData[i] = static_cast<int16_t>(sample * 32767);
    }

    // WAV header
    uint32_t dataSize = static_cast<uint32_t>(totalSamples * sizeof(int16_t));
    uint32_t fileSize = 36 + dataSize;

    // RIFF header
    stream.writeRawData("RIFF", 4);
    stream << fileSize;
    stream.writeRawData("WAVE", 4);

    // fmt chunk
    stream.writeRawData("fmt ", 4);
    stream << uint32_t(16);      // chunk size
    stream << uint16_t(1);       // PCM format
    stream << uint16_t(2);       // channels
    stream << uint32_t(48000);   // sample rate
    stream << uint32_t(48000 * 2 * 2);  // byte rate
    stream << uint16_t(4);       // block align
    stream << uint16_t(16);      // bits per sample

    // data chunk
    stream.writeRawData("data", 4);
    stream << dataSize;
    stream.writeRawData(reinterpret_cast<const char*>(pcmData.data()), dataSize);

    return true;
}

} // namespace ClipTune
