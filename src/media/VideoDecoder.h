#pragma once

#include "FfmpegInit.h"
#include "Demuxer.h"
#include <vector>

namespace ClipTune {

class VideoDecoder {
public:
    VideoDecoder();
    ~VideoDecoder();

    // Initialize decoder for video stream
    bool init(const Demuxer& demuxer);
    void close();
    bool isOpen() const { return m_codecCtx != nullptr; }

    // Send packet to decoder
    bool sendPacket(AVPacket* pkt);

    // Receive decoded frame
    AVFramePtr receiveFrame();

    // Flush decoder
    void flush();

    // Decode all frames from packet
    std::vector<AVFramePtr> decodePacket(AVPacket* pkt);

    // Codec info
    int width() const;
    int height() const;
    AVPixelFormat pixelFormat() const;

private:
    AVCodecContextPtr m_codecCtx;
};

} // namespace ClipTune
