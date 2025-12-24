#pragma once

#include "FfmpegInit.h"
#include <QString>
#include <optional>
#include <vector>

namespace ClipTune {

struct MediaInfo {
    QString filePath;
    double duration = 0.0;  // seconds

    // Audio stream info
    bool hasAudio = false;
    int audioStreamIndex = -1;
    int audioSampleRate = 0;
    int audioChannels = 0;
    AVSampleFormat audioSampleFormat = AV_SAMPLE_FMT_NONE;
    AVChannelLayout audioChannelLayout = {};

    // Video stream info
    bool hasVideo = false;
    int videoStreamIndex = -1;
    int videoWidth = 0;
    int videoHeight = 0;
    double videoFrameRate = 0.0;
    AVPixelFormat videoPixelFormat = AV_PIX_FMT_NONE;
};

class Demuxer {
public:
    Demuxer();
    ~Demuxer();

    // Open media file
    bool open(const QString& filePath);
    void close();
    bool isOpen() const { return m_formatCtx != nullptr; }

    // Get media info
    const MediaInfo& info() const { return m_info; }

    // Stream access
    AVFormatContext* formatContext() const { return m_formatCtx.get(); }
    AVStream* audioStream() const;
    AVStream* videoStream() const;
    const AVCodec* audioCodec() const { return m_audioCodec; }
    const AVCodec* videoCodec() const { return m_videoCodec; }

    // Read next packet
    // Returns empty optional on EOF, throws on error
    std::optional<AVPacketPtr> readPacket();

    // Read packet for specific stream type
    std::optional<AVPacketPtr> readAudioPacket();
    std::optional<AVPacketPtr> readVideoPacket();

    // Seek to timestamp (seconds)
    bool seek(double seconds);
    bool seekAudio(double seconds);
    bool seekVideo(double seconds);

    // Convert timestamps
    double audioTimestamp(int64_t pts) const;
    double videoTimestamp(int64_t pts) const;

private:
    void probeStreamInfo();

    AVFormatContextPtr m_formatCtx;
    MediaInfo m_info;
    const AVCodec* m_audioCodec = nullptr;
    const AVCodec* m_videoCodec = nullptr;
};

} // namespace ClipTune
