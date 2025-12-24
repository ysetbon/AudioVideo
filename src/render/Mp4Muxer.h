#pragma once

#include "media/FfmpegInit.h"
#include <QString>
#include <vector>

namespace ClipTune {

struct VideoEncoderSettings {
    int width = 1920;
    int height = 1080;
    double frameRate = 30.0;
    int64_t bitrate = 8000000;  // 8 Mbps
    QString codec = "libx264";
    QString preset = "medium";
    int crf = 23;
};

struct AudioEncoderSettings {
    int sampleRate = 48000;
    int channels = 2;
    int64_t bitrate = 192000;  // 192 kbps
    QString codec = "aac";
};

class Mp4Muxer {
public:
    Mp4Muxer();
    ~Mp4Muxer();

    // Open output file
    bool open(const QString& filename,
              const VideoEncoderSettings& videoSettings,
              const AudioEncoderSettings& audioSettings);

    bool openVideoOnly(const QString& filename, const VideoEncoderSettings& settings);
    bool openAudioOnly(const QString& filename, const AudioEncoderSettings& settings);

    void close();
    bool isOpen() const { return m_formatCtx != nullptr; }

    // Write encoded frames
    bool writeVideoFrame(AVFrame* frame);
    bool writeAudioFrame(AVFrame* frame);

    // Write raw video (will encode)
    bool encodeAndWriteVideo(const uint8_t* rgbData, int width, int height, int64_t pts);

    // Write raw audio (will encode)
    bool encodeAndWriteAudio(const float* samples, int numSamples, int64_t pts);

    // Finalize (flush encoders and write trailer)
    bool finalize();

    // Progress
    double progress() const { return m_progress; }
    int64_t framesWritten() const { return m_videoFramesWritten; }

private:
    bool initVideoEncoder(const VideoEncoderSettings& settings);
    bool initAudioEncoder(const AudioEncoderSettings& settings);
    bool writeFrame(AVCodecContext* codecCtx, AVStream* stream, AVFrame* frame);

    AVFormatContextPtr m_formatCtx;

    // Video
    AVCodecContextPtr m_videoCodecCtx;
    AVStream* m_videoStream = nullptr;
    SwsContextPtr m_videoScaler;
    AVFramePtr m_videoFrame;
    int64_t m_videoFramesWritten = 0;

    // Audio
    AVCodecContextPtr m_audioCodecCtx;
    AVStream* m_audioStream = nullptr;
    SwrContextPtr m_audioResampler;
    AVFramePtr m_audioFrame;
    int64_t m_audioSamplesWritten = 0;

    double m_progress = 0.0;
    bool m_headerWritten = false;
};

} // namespace ClipTune
