#include "Mp4Muxer.h"
#include <stdexcept>

namespace ClipTune {

Mp4Muxer::Mp4Muxer() = default;

Mp4Muxer::~Mp4Muxer()
{
    close();
}

bool Mp4Muxer::open(const QString& filename,
                    const VideoEncoderSettings& videoSettings,
                    const AudioEncoderSettings& audioSettings)
{
    close();

    try {
        m_formatCtx = createOutputFormatContext(filename.toStdString());

        if (!initVideoEncoder(videoSettings)) {
            close();
            return false;
        }

        if (!initAudioEncoder(audioSettings)) {
            close();
            return false;
        }

        // Open output file
        if (!(m_formatCtx->oformat->flags & AVFMT_NOFILE)) {
            int ret = avio_open(&m_formatCtx->pb, filename.toStdString().c_str(), AVIO_FLAG_WRITE);
            if (ret < 0) {
                close();
                return false;
            }
        }

        // Write header
        int ret = avformat_write_header(m_formatCtx.get(), nullptr);
        if (ret < 0) {
            close();
            return false;
        }
        m_headerWritten = true;

        return true;
    } catch (...) {
        close();
        return false;
    }
}

bool Mp4Muxer::openVideoOnly(const QString& filename, const VideoEncoderSettings& settings)
{
    close();

    try {
        m_formatCtx = createOutputFormatContext(filename.toStdString());

        if (!initVideoEncoder(settings)) {
            close();
            return false;
        }

        if (!(m_formatCtx->oformat->flags & AVFMT_NOFILE)) {
            int ret = avio_open(&m_formatCtx->pb, filename.toStdString().c_str(), AVIO_FLAG_WRITE);
            if (ret < 0) {
                close();
                return false;
            }
        }

        int ret = avformat_write_header(m_formatCtx.get(), nullptr);
        if (ret < 0) {
            close();
            return false;
        }
        m_headerWritten = true;

        return true;
    } catch (...) {
        close();
        return false;
    }
}

bool Mp4Muxer::openAudioOnly(const QString& filename, const AudioEncoderSettings& settings)
{
    close();

    try {
        // For audio-only, use WAV format
        m_formatCtx = createOutputFormatContext(filename.toStdString(), "wav");

        if (!initAudioEncoder(settings)) {
            close();
            return false;
        }

        if (!(m_formatCtx->oformat->flags & AVFMT_NOFILE)) {
            int ret = avio_open(&m_formatCtx->pb, filename.toStdString().c_str(), AVIO_FLAG_WRITE);
            if (ret < 0) {
                close();
                return false;
            }
        }

        int ret = avformat_write_header(m_formatCtx.get(), nullptr);
        if (ret < 0) {
            close();
            return false;
        }
        m_headerWritten = true;

        return true;
    } catch (...) {
        close();
        return false;
    }
}

void Mp4Muxer::close()
{
    if (m_headerWritten && m_formatCtx) {
        av_write_trailer(m_formatCtx.get());
    }

    m_videoScaler.reset();
    m_videoFrame.reset();
    m_videoCodecCtx.reset();
    m_audioResampler.reset();
    m_audioFrame.reset();
    m_audioCodecCtx.reset();

    if (m_formatCtx) {
        if (m_formatCtx->pb && !(m_formatCtx->oformat->flags & AVFMT_NOFILE)) {
            avio_closep(&m_formatCtx->pb);
        }
    }
    m_formatCtx.reset();

    m_videoStream = nullptr;
    m_audioStream = nullptr;
    m_videoFramesWritten = 0;
    m_audioSamplesWritten = 0;
    m_progress = 0.0;
    m_headerWritten = false;
}

bool Mp4Muxer::initVideoEncoder(const VideoEncoderSettings& settings)
{
    const AVCodec* codec = avcodec_find_encoder_by_name(settings.codec.toStdString().c_str());
    if (!codec) {
        codec = avcodec_find_encoder(AV_CODEC_ID_H264);
    }
    if (!codec) return false;

    m_videoStream = avformat_new_stream(m_formatCtx.get(), nullptr);
    if (!m_videoStream) return false;

    m_videoCodecCtx = createCodecContext(codec);

    m_videoCodecCtx->width = settings.width;
    m_videoCodecCtx->height = settings.height;
    m_videoCodecCtx->time_base = AVRational{1, static_cast<int>(settings.frameRate * 1000)};
    m_videoCodecCtx->framerate = AVRational{static_cast<int>(settings.frameRate * 1000), 1000};
    m_videoCodecCtx->pix_fmt = AV_PIX_FMT_YUV420P;
    m_videoCodecCtx->bit_rate = settings.bitrate;
    m_videoCodecCtx->gop_size = 12;

    if (m_formatCtx->oformat->flags & AVFMT_GLOBALHEADER) {
        m_videoCodecCtx->flags |= AV_CODEC_FLAG_GLOBAL_HEADER;
    }

    // Set preset for x264
    if (codec->id == AV_CODEC_ID_H264) {
        av_opt_set(m_videoCodecCtx->priv_data, "preset", settings.preset.toStdString().c_str(), 0);
        av_opt_set_int(m_videoCodecCtx->priv_data, "crf", settings.crf, 0);
    }

    int ret = avcodec_open2(m_videoCodecCtx.get(), codec, nullptr);
    if (ret < 0) return false;

    ret = avcodec_parameters_from_context(m_videoStream->codecpar, m_videoCodecCtx.get());
    if (ret < 0) return false;

    m_videoStream->time_base = m_videoCodecCtx->time_base;

    // Initialize scaler for RGB to YUV conversion
    m_videoScaler.reset(sws_getContext(
        settings.width, settings.height, AV_PIX_FMT_RGB24,
        settings.width, settings.height, AV_PIX_FMT_YUV420P,
        SWS_BILINEAR, nullptr, nullptr, nullptr));

    // Allocate video frame
    m_videoFrame = createFrame();
    m_videoFrame->format = AV_PIX_FMT_YUV420P;
    m_videoFrame->width = settings.width;
    m_videoFrame->height = settings.height;
    av_frame_get_buffer(m_videoFrame.get(), 0);

    return true;
}

bool Mp4Muxer::initAudioEncoder(const AudioEncoderSettings& settings)
{
    const AVCodec* codec = avcodec_find_encoder_by_name(settings.codec.toStdString().c_str());
    if (!codec) {
        codec = avcodec_find_encoder(AV_CODEC_ID_AAC);
    }
    if (!codec) return false;

    m_audioStream = avformat_new_stream(m_formatCtx.get(), nullptr);
    if (!m_audioStream) return false;

    m_audioCodecCtx = createCodecContext(codec);

    m_audioCodecCtx->sample_rate = settings.sampleRate;
    m_audioCodecCtx->bit_rate = settings.bitrate;
    av_channel_layout_default(&m_audioCodecCtx->ch_layout, settings.channels);

    // Find supported sample format
    m_audioCodecCtx->sample_fmt = AV_SAMPLE_FMT_FLTP;
    if (codec->sample_fmts) {
        m_audioCodecCtx->sample_fmt = codec->sample_fmts[0];
        for (int i = 0; codec->sample_fmts[i] != AV_SAMPLE_FMT_NONE; ++i) {
            if (codec->sample_fmts[i] == AV_SAMPLE_FMT_FLTP) {
                m_audioCodecCtx->sample_fmt = AV_SAMPLE_FMT_FLTP;
                break;
            }
        }
    }

    m_audioCodecCtx->time_base = AVRational{1, settings.sampleRate};

    if (m_formatCtx->oformat->flags & AVFMT_GLOBALHEADER) {
        m_audioCodecCtx->flags |= AV_CODEC_FLAG_GLOBAL_HEADER;
    }

    int ret = avcodec_open2(m_audioCodecCtx.get(), codec, nullptr);
    if (ret < 0) return false;

    ret = avcodec_parameters_from_context(m_audioStream->codecpar, m_audioCodecCtx.get());
    if (ret < 0) return false;

    m_audioStream->time_base = m_audioCodecCtx->time_base;

    // Initialize resampler for float to encoder format
    AVChannelLayout srcLayout = AV_CHANNEL_LAYOUT_STEREO;
    ret = swr_alloc_set_opts2(&m_audioResampler,
                               &m_audioCodecCtx->ch_layout,
                               m_audioCodecCtx->sample_fmt,
                               settings.sampleRate,
                               &srcLayout,
                               AV_SAMPLE_FMT_FLT,
                               settings.sampleRate,
                               0, nullptr);

    SwrContext* swrPtr = m_audioResampler.release();
    if (ret < 0 || !swrPtr) return false;
    m_audioResampler.reset(swrPtr);

    ret = swr_init(m_audioResampler.get());
    if (ret < 0) return false;

    // Allocate audio frame
    m_audioFrame = createFrame();
    m_audioFrame->format = m_audioCodecCtx->sample_fmt;
    av_channel_layout_copy(&m_audioFrame->ch_layout, &m_audioCodecCtx->ch_layout);
    m_audioFrame->sample_rate = settings.sampleRate;
    m_audioFrame->nb_samples = m_audioCodecCtx->frame_size ? m_audioCodecCtx->frame_size : 1024;
    av_frame_get_buffer(m_audioFrame.get(), 0);

    return true;
}

bool Mp4Muxer::writeVideoFrame(AVFrame* frame)
{
    return writeFrame(m_videoCodecCtx.get(), m_videoStream, frame);
}

bool Mp4Muxer::writeAudioFrame(AVFrame* frame)
{
    return writeFrame(m_audioCodecCtx.get(), m_audioStream, frame);
}

bool Mp4Muxer::encodeAndWriteVideo(const uint8_t* rgbData, int width, int height, int64_t pts)
{
    if (!m_videoCodecCtx || !m_videoScaler || !m_videoFrame) return false;

    // Convert RGB to YUV
    const uint8_t* srcData[1] = { rgbData };
    int srcLinesize[1] = { width * 3 };

    av_frame_make_writable(m_videoFrame.get());

    sws_scale(m_videoScaler.get(),
              srcData, srcLinesize, 0, height,
              m_videoFrame->data, m_videoFrame->linesize);

    m_videoFrame->pts = pts;

    bool result = writeVideoFrame(m_videoFrame.get());
    if (result) {
        ++m_videoFramesWritten;
    }
    return result;
}

bool Mp4Muxer::encodeAndWriteAudio(const float* samples, int numSamples, int64_t pts)
{
    if (!m_audioCodecCtx || !m_audioResampler || !m_audioFrame) return false;

    av_frame_make_writable(m_audioFrame.get());

    // Resample
    const uint8_t* inData[1] = { reinterpret_cast<const uint8_t*>(samples) };
    int outSamples = swr_convert(m_audioResampler.get(),
                                  m_audioFrame->data,
                                  m_audioFrame->nb_samples,
                                  inData,
                                  numSamples);

    if (outSamples < 0) return false;

    m_audioFrame->nb_samples = outSamples;
    m_audioFrame->pts = pts;

    bool result = writeAudioFrame(m_audioFrame.get());
    if (result) {
        m_audioSamplesWritten += outSamples;
    }
    return result;
}

bool Mp4Muxer::writeFrame(AVCodecContext* codecCtx, AVStream* stream, AVFrame* frame)
{
    if (!m_formatCtx || !codecCtx || !stream) return false;

    int ret = avcodec_send_frame(codecCtx, frame);
    if (ret < 0) return false;

    auto pkt = createPacket();

    while (ret >= 0) {
        ret = avcodec_receive_packet(codecCtx, pkt.get());
        if (ret == AVERROR(EAGAIN) || ret == AVERROR_EOF) {
            break;
        }
        if (ret < 0) return false;

        // Rescale timestamps
        av_packet_rescale_ts(pkt.get(), codecCtx->time_base, stream->time_base);
        pkt->stream_index = stream->index;

        ret = av_interleaved_write_frame(m_formatCtx.get(), pkt.get());
        if (ret < 0) return false;

        av_packet_unref(pkt.get());
    }

    return true;
}

bool Mp4Muxer::finalize()
{
    if (!m_formatCtx) return false;

    // Flush video encoder
    if (m_videoCodecCtx) {
        writeFrame(m_videoCodecCtx.get(), m_videoStream, nullptr);
    }

    // Flush audio encoder
    if (m_audioCodecCtx) {
        writeFrame(m_audioCodecCtx.get(), m_audioStream, nullptr);
    }

    return true;
}

} // namespace ClipTune
