#pragma once

#include "core/Project.h"
#include "core/Track.h"
#include "core/Clip.h"
#include "FadeDSP.h"
#include <vector>
#include <unordered_map>
#include <memory>

namespace ClipTune {

// Forward declarations
class AudioDecoder;
class Resampler;
class Demuxer;

// Per-clip audio cache/decoder state
struct ClipAudioState {
    std::unique_ptr<Demuxer> demuxer;
    std::unique_ptr<AudioDecoder> decoder;
    std::unique_ptr<Resampler> resampler;
    std::vector<float> decodedSamples;
    double currentPosition = 0.0;  // Current decode position in source
    bool isLoaded = false;
};

class Mixer {
public:
    Mixer();
    ~Mixer();

    // Set project reference
    void setProject(Project* project);

    // Audio format settings
    void setSampleRate(int rate) { m_sampleRate = rate; }
    void setChannels(int channels) { m_channels = channels; }
    int sampleRate() const { return m_sampleRate; }
    int channels() const { return m_channels; }

    // Mix audio for time range into buffer
    // Returns number of frames written
    size_t mix(double startTime, float* buffer, size_t numFrames);

    // Mix audio for time range, returning vector
    std::vector<float> mix(double startTime, size_t numFrames);

    // Preload clip audio data
    bool preloadClip(const Clip& clip);

    // Unload clip audio data
    void unloadClip(const QUuid& clipId);

    // Clear all cached audio data
    void clearCache();

    // Check if clip is loaded
    bool isClipLoaded(const QUuid& clipId) const;

    // Seek to time (clears and refills caches as needed)
    void seek(double time);

private:
    // Mix a single clip into buffer
    void mixClip(const Clip& clip, double startTime, float* buffer, size_t numFrames);

    // Get or create clip state
    ClipAudioState* getClipState(const QUuid& clipId);

    // Read decoded samples from clip at source time
    std::vector<float> readClipSamples(const Clip& clip, double sourceTime, size_t numFrames);

    Project* m_project = nullptr;
    int m_sampleRate = 48000;
    int m_channels = 2;

    std::unordered_map<QUuid, std::unique_ptr<ClipAudioState>> m_clipStates;

    // Scratch buffer for mixing
    std::vector<float> m_scratchBuffer;
};

} // namespace ClipTune
