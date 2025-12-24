#include "AudioDecoder.h"
#include <stdexcept>

namespace ClipTune {

AudioDecoder::AudioDecoder() = default;

AudioDecoder::~AudioDecoder()
{
    close();
}

bool AudioDecoder::init(const Demuxer& demuxer)
{
    close();

    if (!demuxer.info().hasAudio || !demuxer.audioCodec()) {
        return false;
    }

    const AVCodec* codec = demuxer.audioCodec();
    m_codecCtx = createCodecContext(codec);

    AVStream* stream = demuxer.audioStream();
    int ret = avcodec_parameters_to_context(m_codecCtx.get(), stream->codecpar);
    if (ret < 0) {
        close();
        return false;
    }

    ret = avcodec_open2(m_codecCtx.get(), codec, nullptr);
    if (ret < 0) {
        close();
        return false;
    }

    return true;
}

void AudioDecoder::close()
{
    m_codecCtx.reset();
}

bool AudioDecoder::sendPacket(AVPacket* pkt)
{
    if (!m_codecCtx) return false;

    int ret = avcodec_send_packet(m_codecCtx.get(), pkt);
    return ret >= 0 || ret == AVERROR(EAGAIN);
}

AVFramePtr AudioDecoder::receiveFrame()
{
    if (!m_codecCtx) return nullptr;

    auto frame = createFrame();
    int ret = avcodec_receive_frame(m_codecCtx.get(), frame.get());

    if (ret == AVERROR(EAGAIN) || ret == AVERROR_EOF) {
        return nullptr;
    }
    if (ret < 0) {
        throw std::runtime_error("Error decoding audio: " + avErrorToString(ret));
    }

    return frame;
}

void AudioDecoder::flush()
{
    if (m_codecCtx) {
        avcodec_flush_buffers(m_codecCtx.get());
    }
}

std::vector<AVFramePtr> AudioDecoder::decodePacket(AVPacket* pkt)
{
    std::vector<AVFramePtr> frames;

    if (!sendPacket(pkt)) {
        return frames;
    }

    while (auto frame = receiveFrame()) {
        frames.push_back(std::move(frame));
    }

    return frames;
}

int AudioDecoder::sampleRate() const
{
    return m_codecCtx ? m_codecCtx->sample_rate : 0;
}

int AudioDecoder::channels() const
{
    return m_codecCtx ? m_codecCtx->ch_layout.nb_channels : 0;
}

AVSampleFormat AudioDecoder::sampleFormat() const
{
    return m_codecCtx ? m_codecCtx->sample_fmt : AV_SAMPLE_FMT_NONE;
}

const AVChannelLayout* AudioDecoder::channelLayout() const
{
    return m_codecCtx ? &m_codecCtx->ch_layout : nullptr;
}

} // namespace ClipTune
