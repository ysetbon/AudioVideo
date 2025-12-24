#pragma once

#include <memory>
#include <string>

// FFmpeg includes (C headers need extern "C")
extern "C" {
#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>
#include <libavutil/avutil.h>
#include <libavutil/imgutils.h>
#include <libavutil/opt.h>
#include <libavutil/channel_layout.h>
#include <libswresample/swresample.h>
#include <libswscale/swscale.h>
}

namespace ClipTune {

// Initialize FFmpeg (call once at app startup)
void initFfmpeg();

// RAII wrappers for FFmpeg structures

// AVFormatContext wrapper
struct AVFormatContextDeleter {
    void operator()(AVFormatContext* ctx) const;
};
using AVFormatContextPtr = std::unique_ptr<AVFormatContext, AVFormatContextDeleter>;

// Create format context for input
AVFormatContextPtr createInputFormatContext(const std::string& filename);
// Create format context for output
AVFormatContextPtr createOutputFormatContext(const std::string& filename, const char* formatName = nullptr);

// AVCodecContext wrapper
struct AVCodecContextDeleter {
    void operator()(AVCodecContext* ctx) const;
};
using AVCodecContextPtr = std::unique_ptr<AVCodecContext, AVCodecContextDeleter>;

// Create codec context from codec
AVCodecContextPtr createCodecContext(const AVCodec* codec);

// AVFrame wrapper
struct AVFrameDeleter {
    void operator()(AVFrame* frame) const;
};
using AVFramePtr = std::unique_ptr<AVFrame, AVFrameDeleter>;

// Create empty frame
AVFramePtr createFrame();

// AVPacket wrapper
struct AVPacketDeleter {
    void operator()(AVPacket* pkt) const;
};
using AVPacketPtr = std::unique_ptr<AVPacket, AVPacketDeleter>;

// Create empty packet
AVPacketPtr createPacket();

// SwrContext wrapper
struct SwrContextDeleter {
    void operator()(SwrContext* ctx) const;
};
using SwrContextPtr = std::unique_ptr<SwrContext, SwrContextDeleter>;

// SwsContext wrapper
struct SwsContextDeleter {
    void operator()(SwsContext* ctx) const;
};
using SwsContextPtr = std::unique_ptr<SwsContext, SwsContextDeleter>;

// Utility functions
std::string avErrorToString(int errnum);
double ptsToSeconds(int64_t pts, AVRational timebase);
int64_t secondsToPts(double seconds, AVRational timebase);

} // namespace ClipTune
