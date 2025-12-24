#include "FadeDSP.h"
#include <algorithm>
#include <cmath>

namespace ClipTune {

float FadeDSP::calculateEnvelope(double t, double L, double fadeIn, double fadeOut, FadeCurve curve)
{
    // Clamp t to valid range
    t = std::clamp(t, 0.0, L);

    float fadeInGain = 1.0f;
    float fadeOutGain = 1.0f;

    // Fade in envelope
    if (fadeIn > 0.0 && t < fadeIn) {
        switch (curve) {
            case FadeCurve::Linear:
                fadeInGain = linearFade(t, fadeIn);
                break;
            case FadeCurve::Exponential:
                fadeInGain = exponentialFade(t, fadeIn);
                break;
            case FadeCurve::SCurve:
                fadeInGain = sCurveFade(t, fadeIn);
                break;
        }
    }

    // Fade out envelope
    if (fadeOut > 0.0 && t > L - fadeOut) {
        double fadeOutTime = L - t;  // Time remaining until end
        switch (curve) {
            case FadeCurve::Linear:
                fadeOutGain = linearFade(fadeOutTime, fadeOut);
                break;
            case FadeCurve::Exponential:
                fadeOutGain = exponentialFade(fadeOutTime, fadeOut);
                break;
            case FadeCurve::SCurve:
                fadeOutGain = sCurveFade(fadeOutTime, fadeOut);
                break;
        }
    }

    // Combine fade in and fade out (handle overlap case)
    return fadeInGain * fadeOutGain;
}

void FadeDSP::applyFade(float* samples, size_t numFrames,
                        double startTime, double clipDuration,
                        double fadeIn, double fadeOut, FadeCurve curve,
                        int sampleRate, int channels)
{
    if (!samples || numFrames == 0) return;

    double secondsPerSample = 1.0 / sampleRate;

    for (size_t frame = 0; frame < numFrames; ++frame) {
        double t = startTime + frame * secondsPerSample;
        float envelope = calculateEnvelope(t, clipDuration, fadeIn, fadeOut, curve);

        // Apply to all channels in this frame
        for (int ch = 0; ch < channels; ++ch) {
            samples[frame * channels + ch] *= envelope;
        }
    }
}

void FadeDSP::applyGain(float* samples, size_t numSamples, float gain)
{
    if (!samples || numSamples == 0) return;

    if (gain == 1.0f) return;  // No-op

    for (size_t i = 0; i < numSamples; ++i) {
        samples[i] *= gain;
    }
}

void FadeDSP::applyGainAndFade(float* samples, size_t numFrames,
                               float gain, double startTime, double clipDuration,
                               double fadeIn, double fadeOut, FadeCurve curve,
                               int sampleRate, int channels)
{
    if (!samples || numFrames == 0) return;

    double secondsPerSample = 1.0 / sampleRate;

    for (size_t frame = 0; frame < numFrames; ++frame) {
        double t = startTime + frame * secondsPerSample;
        float envelope = calculateEnvelope(t, clipDuration, fadeIn, fadeOut, curve);
        float totalGain = gain * envelope;

        // Apply to all channels in this frame
        for (int ch = 0; ch < channels; ++ch) {
            samples[frame * channels + ch] *= totalGain;
        }
    }
}

void FadeDSP::mixInto(float* dest, const float* src, size_t numSamples, float gain)
{
    if (!dest || !src || numSamples == 0) return;

    for (size_t i = 0; i < numSamples; ++i) {
        dest[i] += src[i] * gain;
    }
}

std::vector<float> FadeDSP::generateEnvelope(double clipDuration, double fadeIn, double fadeOut,
                                             FadeCurve curve, int numPoints)
{
    std::vector<float> envelope(numPoints);

    for (int i = 0; i < numPoints; ++i) {
        double t = (static_cast<double>(i) / (numPoints - 1)) * clipDuration;
        envelope[i] = calculateEnvelope(t, clipDuration, fadeIn, fadeOut, curve);
    }

    return envelope;
}

float FadeDSP::linearFade(double t, double duration)
{
    if (duration <= 0.0) return 1.0f;
    return static_cast<float>(std::clamp(t / duration, 0.0, 1.0));
}

float FadeDSP::exponentialFade(double t, double duration)
{
    if (duration <= 0.0) return 1.0f;
    double normalized = std::clamp(t / duration, 0.0, 1.0);
    // Exponential curve: y = 1 - e^(-3x) / (1 - e^(-3))
    // This gives a natural fade curve
    constexpr double k = 3.0;
    double expFactor = 1.0 - std::exp(-k);
    return static_cast<float>((1.0 - std::exp(-k * normalized)) / expFactor);
}

float FadeDSP::sCurveFade(double t, double duration)
{
    if (duration <= 0.0) return 1.0f;
    double normalized = std::clamp(t / duration, 0.0, 1.0);
    // S-curve using smoothstep: y = 3x^2 - 2x^3
    return static_cast<float>(normalized * normalized * (3.0 - 2.0 * normalized));
}

} // namespace ClipTune
