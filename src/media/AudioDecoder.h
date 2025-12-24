#pragma once

#include "FfmpegInit.h"
#include "Demuxer.h"
#include <vector>
#include <queue>

namespace ClipTune {

class AudioDecoder {
public:
    AudioDecoder();
    ~AudioDecoder();

    // Initialize decoder for audio stream
    bool init(const Demuxer& demuxer);
    void close();
    bool isOpen() const { return m_codecCtx != nullptr; }

    // Send packet to decoder
    bool sendPacket(AVPacket* pkt);

    // Receive decoded frame (may need multiple calls)
    // Returns nullptr when no more frames available
    AVFramePtr receiveFrame();

    // Flush decoder (call after seeking)
    void flush();

    // Decode all frames from packet
    std::vector<AVFramePtr> decodePacket(AVPacket* pkt);

    // Codec info
    int sampleRate() const;
    int channels() const;
    AVSampleFormat sampleFormat() const;
    const AVChannelLayout* channelLayout() const;

private:
    AVCodecContextPtr m_codecCtx;
};

} // namespace ClipTune
