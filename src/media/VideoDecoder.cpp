#include "VideoDecoder.h"
#include <stdexcept>

namespace ClipTune {

VideoDecoder::VideoDecoder() = default;

VideoDecoder::~VideoDecoder()
{
    close();
}

bool VideoDecoder::init(const Demuxer& demuxer)
{
    close();

    if (!demuxer.info().hasVideo || !demuxer.videoCodec()) {
        return false;
    }

    const AVCodec* codec = demuxer.videoCodec();
    m_codecCtx = createCodecContext(codec);

    AVStream* stream = demuxer.videoStream();
    int ret = avcodec_parameters_to_context(m_codecCtx.get(), stream->codecpar);
    if (ret < 0) {
        close();
        return false;
    }

    // Enable multi-threading
    m_codecCtx->thread_count = 0;  // Auto-detect
    m_codecCtx->thread_type = FF_THREAD_FRAME | FF_THREAD_SLICE;

    ret = avcodec_open2(m_codecCtx.get(), codec, nullptr);
    if (ret < 0) {
        close();
        return false;
    }

    return true;
}

void VideoDecoder::close()
{
    m_codecCtx.reset();
}

bool VideoDecoder::sendPacket(AVPacket* pkt)
{
    if (!m_codecCtx) return false;

    int ret = avcodec_send_packet(m_codecCtx.get(), pkt);
    return ret >= 0 || ret == AVERROR(EAGAIN);
}

AVFramePtr VideoDecoder::receiveFrame()
{
    if (!m_codecCtx) return nullptr;

    auto frame = createFrame();
    int ret = avcodec_receive_frame(m_codecCtx.get(), frame.get());

    if (ret == AVERROR(EAGAIN) || ret == AVERROR_EOF) {
        return nullptr;
    }
    if (ret < 0) {
        throw std::runtime_error("Error decoding video: " + avErrorToString(ret));
    }

    return frame;
}

void VideoDecoder::flush()
{
    if (m_codecCtx) {
        avcodec_flush_buffers(m_codecCtx.get());
    }
}

std::vector<AVFramePtr> VideoDecoder::decodePacket(AVPacket* pkt)
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

int VideoDecoder::width() const
{
    return m_codecCtx ? m_codecCtx->width : 0;
}

int VideoDecoder::height() const
{
    return m_codecCtx ? m_codecCtx->height : 0;
}

AVPixelFormat VideoDecoder::pixelFormat() const
{
    return m_codecCtx ? m_codecCtx->pix_fmt : AV_PIX_FMT_NONE;
}

} // namespace ClipTune
