#include "Resampler.h"
#include <stdexcept>
#include <cstring>

namespace ClipTune {

Resampler::Resampler() = default;

Resampler::~Resampler()
{
    close();
}

bool Resampler::init(const AudioFormat& srcFormat, const AudioFormat& dstFormat)
{
    close();

    m_srcFormat = srcFormat;
    m_dstFormat = dstFormat;

    SwrContext* ctx = nullptr;
    int ret = swr_alloc_set_opts2(&ctx,
                                   &dstFormat.channelLayout,
                                   dstFormat.sampleFormat,
                                   dstFormat.sampleRate,
                                   &srcFormat.channelLayout,
                                   srcFormat.sampleFormat,
                                   srcFormat.sampleRate,
                                   0, nullptr);

    if (ret < 0 || !ctx) {
        return false;
    }

    m_swrCtx.reset(ctx);

    ret = swr_init(m_swrCtx.get());
    if (ret < 0) {
        close();
        return false;
    }

    return true;
}

void Resampler::close()
{
    m_swrCtx.reset();
}

std::vector<float> Resampler::resample(AVFrame* frame)
{
    if (!m_swrCtx || !frame) {
        return {};
    }

    int outSamples = getOutputSamples(frame->nb_samples);
    if (outSamples <= 0) {
        return {};
    }

    // Allocate output buffer
    std::vector<float> output(outSamples * m_dstFormat.channels);

    uint8_t* outData[1] = { reinterpret_cast<uint8_t*>(output.data()) };

    int converted = swr_convert(m_swrCtx.get(),
                                outData, outSamples,
                                const_cast<const uint8_t**>(frame->extended_data),
                                frame->nb_samples);

    if (converted < 0) {
        throw std::runtime_error("Resampling failed: " + avErrorToString(converted));
    }

    // Resize to actual samples converted
    output.resize(converted * m_dstFormat.channels);
    return output;
}

int Resampler::resample(AVFrame* frame, float* outBuffer, int maxSamples)
{
    if (!m_swrCtx || !frame || !outBuffer) {
        return 0;
    }

    uint8_t* outData[1] = { reinterpret_cast<uint8_t*>(outBuffer) };

    int converted = swr_convert(m_swrCtx.get(),
                                outData, maxSamples,
                                const_cast<const uint8_t**>(frame->extended_data),
                                frame->nb_samples);

    if (converted < 0) {
        return 0;
    }

    return converted;
}

int Resampler::getOutputSamples(int inputSamples) const
{
    if (!m_swrCtx) return 0;

    int64_t delay = swr_get_delay(m_swrCtx.get(), m_srcFormat.sampleRate);
    return static_cast<int>(av_rescale_rnd(delay + inputSamples,
                                            m_dstFormat.sampleRate,
                                            m_srcFormat.sampleRate,
                                            AV_ROUND_UP));
}

std::vector<float> Resampler::flush()
{
    if (!m_swrCtx) {
        return {};
    }

    // Get remaining samples
    int remaining = swr_get_out_samples(m_swrCtx.get(), 0);
    if (remaining <= 0) {
        return {};
    }

    std::vector<float> output(remaining * m_dstFormat.channels);
    uint8_t* outData[1] = { reinterpret_cast<uint8_t*>(output.data()) };

    int converted = swr_convert(m_swrCtx.get(), outData, remaining, nullptr, 0);
    if (converted > 0) {
        output.resize(converted * m_dstFormat.channels);
    } else {
        output.clear();
    }

    return output;
}

} // namespace ClipTune
