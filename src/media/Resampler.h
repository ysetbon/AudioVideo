#pragma once

#include "FfmpegInit.h"
#include <vector>
#include <cstdint>

namespace ClipTune {

// Audio format specification
struct AudioFormat {
    int sampleRate = 48000;
    int channels = 2;
    AVSampleFormat sampleFormat = AV_SAMPLE_FMT_FLT;  // float32 interleaved
    AVChannelLayout channelLayout = AV_CHANNEL_LAYOUT_STEREO;

    static AudioFormat projectDefault() {
        return AudioFormat{};
    }
};

class Resampler {
public:
    Resampler();
    ~Resampler();

    // Initialize resampler
    bool init(const AudioFormat& srcFormat, const AudioFormat& dstFormat);
    void close();
    bool isOpen() const { return m_swrCtx != nullptr; }

    // Resample audio frame to output format
    // Returns vector of float samples (interleaved stereo for default format)
    std::vector<float> resample(AVFrame* frame);

    // Resample with output to buffer
    // Returns number of samples written per channel
    int resample(AVFrame* frame, float* outBuffer, int maxSamples);

    // Get number of samples that will be output for given input
    int getOutputSamples(int inputSamples) const;

    // Flush remaining samples from resampler
    std::vector<float> flush();

    // Output format
    const AudioFormat& outputFormat() const { return m_dstFormat; }

private:
    SwrContextPtr m_swrCtx;
    AudioFormat m_srcFormat;
    AudioFormat m_dstFormat;
};

} // namespace ClipTune
