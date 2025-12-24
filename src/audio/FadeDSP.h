#pragma once

#include "core/Clip.h"
#include <vector>
#include <cmath>

namespace ClipTune {

class FadeDSP {
public:
    // Calculate fade envelope multiplier for a given time within clip
    // t: time from clip start (in seconds) within the used region
    // L: clip duration (seconds)
    // fadeIn: fade in duration (seconds)
    // fadeOut: fade out duration (seconds)
    // curve: fade curve type
    static float calculateEnvelope(double t, double L, double fadeIn, double fadeOut, FadeCurve curve);

    // Apply fade envelope to buffer of samples
    // startTime: time at start of buffer (relative to clip start)
    // sampleRate: audio sample rate
    // channels: number of audio channels (samples are interleaved)
    static void applyFade(float* samples, size_t numFrames,
                          double startTime, double clipDuration,
                          double fadeIn, double fadeOut, FadeCurve curve,
                          int sampleRate, int channels);

    // Apply gain to buffer
    static void applyGain(float* samples, size_t numSamples, float gain);

    // Apply gain with fade envelope
    static void applyGainAndFade(float* samples, size_t numFrames,
                                 float gain, double startTime, double clipDuration,
                                 double fadeIn, double fadeOut, FadeCurve curve,
                                 int sampleRate, int channels);

    // Mix source buffer into destination with gain
    static void mixInto(float* dest, const float* src, size_t numSamples, float gain = 1.0f);

    // Generate fade envelope for visualization
    static std::vector<float> generateEnvelope(double clipDuration, double fadeIn, double fadeOut,
                                               FadeCurve curve, int numPoints);

private:
    // Curve calculation helpers
    static float linearFade(double t, double duration);
    static float exponentialFade(double t, double duration);
    static float sCurveFade(double t, double duration);
};

} // namespace ClipTune
