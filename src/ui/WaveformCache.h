#pragma once

#include <QString>
#include <QHash>
#include <QObject>
#include <vector>
#include <unordered_map>
#include <unordered_set>
#include <memory>
#include <mutex>

// Note: Qt6 provides std::hash<QString> in qhashfunctions.h

namespace ClipTune {

// Waveform peak data for a single audio file
struct WaveformData {
    std::vector<float> minPeaks;  // Minimum values per bucket
    std::vector<float> maxPeaks;  // Maximum values per bucket
    int samplesPerBucket = 1024;
    int sampleRate = 48000;
    int channels = 2;
    double duration = 0.0;

    // Get peak range for time range
    void getPeaksForRange(double startTime, double endTime, int numBuckets,
                          std::vector<float>& outMin, std::vector<float>& outMax) const;

    // Get number of buckets
    size_t numBuckets() const { return minPeaks.size(); }
};

class WaveformCache : public QObject {
    Q_OBJECT

public:
    explicit WaveformCache(QObject* parent = nullptr);
    ~WaveformCache() override;

    // Get or generate waveform for file
    // Returns nullptr if not cached and background generation starts
    const WaveformData* getWaveform(const QString& filePath);

    // Check if waveform is cached
    bool hasCachedWaveform(const QString& filePath) const;

    // Generate waveform synchronously (blocks)
    bool generateWaveform(const QString& filePath);

    // Generate waveform asynchronously
    void generateWaveformAsync(const QString& filePath);

    // Clear cache
    void clear();

    // Remove specific entry
    void remove(const QString& filePath);

    // Cache directory for persistent storage
    void setCacheDirectory(const QString& path) { m_cacheDir = path; }
    QString cacheDirectory() const { return m_cacheDir; }

signals:
    void waveformReady(const QString& filePath);
    void waveformError(const QString& filePath, const QString& error);

private:
    bool loadFromDisk(const QString& filePath);
    bool saveToDisk(const QString& filePath, const WaveformData& data);
    QString getCacheFilePath(const QString& filePath) const;

    std::unordered_map<QString, std::unique_ptr<WaveformData>> m_cache;
    std::unordered_set<QString> m_generating;  // Files currently being generated
    QString m_cacheDir;
    mutable std::mutex m_mutex;
};

} // namespace ClipTune
