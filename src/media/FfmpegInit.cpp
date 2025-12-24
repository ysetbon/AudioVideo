#include "FfmpegInit.h"
#include <stdexcept>

namespace ClipTune {

void initFfmpeg()
{
    // In modern FFmpeg (4.0+), av_register_all() is deprecated and not needed
    // Network initialization might still be useful for streaming support
#if LIBAVFORMAT_VERSION_MAJOR < 58
    av_register_all();
#endif
    avformat_network_init();
}

// AVFormatContext deleter
void AVFormatContextDeleter::operator()(AVFormatContext* ctx) const
{
    if (ctx) {
        if (ctx->pb && !(ctx->oformat && (ctx->oformat->flags & AVFMT_NOFILE))) {
            avio_closep(&ctx->pb);
        }
        avformat_close_input(&ctx);
    }
}

AVFormatContextPtr createInputFormatContext(const std::string& filename)
{
    AVFormatContext* ctx = nullptr;
    int ret = avformat_open_input(&ctx, filename.c_str(), nullptr, nullptr);
    if (ret < 0) {
        throw std::runtime_error("Failed to open input: " + filename + " - " + avErrorToString(ret));
    }

    ret = avformat_find_stream_info(ctx, nullptr);
    if (ret < 0) {
        avformat_close_input(&ctx);
        throw std::runtime_error("Failed to find stream info: " + avErrorToString(ret));
    }

    return AVFormatContextPtr(ctx);
}

AVFormatContextPtr createOutputFormatContext(const std::string& filename, const char* formatName)
{
    AVFormatContext* ctx = nullptr;
    int ret = avformat_alloc_output_context2(&ctx, nullptr, formatName, filename.c_str());
    if (ret < 0 || !ctx) {
        throw std::runtime_error("Failed to create output context: " + avErrorToString(ret));
    }
    return AVFormatContextPtr(ctx);
}

// AVCodecContext deleter
void AVCodecContextDeleter::operator()(AVCodecContext* ctx) const
{
    if (ctx) {
        avcodec_free_context(&ctx);
    }
}

AVCodecContextPtr createCodecContext(const AVCodec* codec)
{
    AVCodecContext* ctx = avcodec_alloc_context3(codec);
    if (!ctx) {
        throw std::runtime_error("Failed to allocate codec context");
    }
    return AVCodecContextPtr(ctx);
}

// AVFrame deleter
void AVFrameDeleter::operator()(AVFrame* frame) const
{
    if (frame) {
        av_frame_free(&frame);
    }
}

AVFramePtr createFrame()
{
    AVFrame* frame = av_frame_alloc();
    if (!frame) {
        throw std::runtime_error("Failed to allocate frame");
    }
    return AVFramePtr(frame);
}

// AVPacket deleter
void AVPacketDeleter::operator()(AVPacket* pkt) const
{
    if (pkt) {
        av_packet_free(&pkt);
    }
}

AVPacketPtr createPacket()
{
    AVPacket* pkt = av_packet_alloc();
    if (!pkt) {
        throw std::runtime_error("Failed to allocate packet");
    }
    return AVPacketPtr(pkt);
}

// SwrContext deleter
void SwrContextDeleter::operator()(SwrContext* ctx) const
{
    if (ctx) {
        swr_free(&ctx);
    }
}

// SwsContext deleter
void SwsContextDeleter::operator()(SwsContext* ctx) const
{
    if (ctx) {
        sws_freeContext(ctx);
    }
}

std::string avErrorToString(int errnum)
{
    char buf[AV_ERROR_MAX_STRING_SIZE] = {0};
    av_strerror(errnum, buf, sizeof(buf));
    return std::string(buf);
}

double ptsToSeconds(int64_t pts, AVRational timebase)
{
    if (pts == AV_NOPTS_VALUE) {
        return 0.0;
    }
    return static_cast<double>(pts) * av_q2d(timebase);
}

int64_t secondsToPts(double seconds, AVRational timebase)
{
    return static_cast<int64_t>(seconds / av_q2d(timebase));
}

} // namespace ClipTune
