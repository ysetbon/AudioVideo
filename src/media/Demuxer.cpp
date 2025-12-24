#include "Demuxer.h"
#include <stdexcept>

namespace ClipTune {

Demuxer::Demuxer() = default;

Demuxer::~Demuxer()
{
    close();
}

bool Demuxer::open(const QString& filePath)
{
    close();

    try {
        m_formatCtx = createInputFormatContext(filePath.toStdString());
        m_info.filePath = filePath;
        probeStreamInfo();
        return true;
    } catch (const std::exception& e) {
        close();
        return false;
    }
}

void Demuxer::close()
{
    m_formatCtx.reset();
    m_audioCodec = nullptr;
    m_videoCodec = nullptr;
    m_info = MediaInfo{};
}

void Demuxer::probeStreamInfo()
{
    if (!m_formatCtx) return;

    // Get duration
    if (m_formatCtx->duration != AV_NOPTS_VALUE) {
        m_info.duration = static_cast<double>(m_formatCtx->duration) / AV_TIME_BASE;
    }

    // Find audio stream
    for (unsigned i = 0; i < m_formatCtx->nb_streams; ++i) {
        AVStream* stream = m_formatCtx->streams[i];
        if (stream->codecpar->codec_type == AVMEDIA_TYPE_AUDIO && !m_info.hasAudio) {
            m_info.hasAudio = true;
            m_info.audioStreamIndex = static_cast<int>(i);
            m_info.audioSampleRate = stream->codecpar->sample_rate;
            m_info.audioChannels = stream->codecpar->ch_layout.nb_channels;
            m_info.audioSampleFormat = static_cast<AVSampleFormat>(stream->codecpar->format);
            av_channel_layout_copy(&m_info.audioChannelLayout, &stream->codecpar->ch_layout);

            m_audioCodec = avcodec_find_decoder(stream->codecpar->codec_id);
        }
    }

    // Find video stream
    for (unsigned i = 0; i < m_formatCtx->nb_streams; ++i) {
        AVStream* stream = m_formatCtx->streams[i];
        if (stream->codecpar->codec_type == AVMEDIA_TYPE_VIDEO && !m_info.hasVideo) {
            m_info.hasVideo = true;
            m_info.videoStreamIndex = static_cast<int>(i);
            m_info.videoWidth = stream->codecpar->width;
            m_info.videoHeight = stream->codecpar->height;
            m_info.videoPixelFormat = static_cast<AVPixelFormat>(stream->codecpar->format);

            if (stream->avg_frame_rate.den > 0) {
                m_info.videoFrameRate = av_q2d(stream->avg_frame_rate);
            } else if (stream->r_frame_rate.den > 0) {
                m_info.videoFrameRate = av_q2d(stream->r_frame_rate);
            }

            m_videoCodec = avcodec_find_decoder(stream->codecpar->codec_id);
        }
    }
}

AVStream* Demuxer::audioStream() const
{
    if (m_formatCtx && m_info.audioStreamIndex >= 0) {
        return m_formatCtx->streams[m_info.audioStreamIndex];
    }
    return nullptr;
}

AVStream* Demuxer::videoStream() const
{
    if (m_formatCtx && m_info.videoStreamIndex >= 0) {
        return m_formatCtx->streams[m_info.videoStreamIndex];
    }
    return nullptr;
}

std::optional<AVPacketPtr> Demuxer::readPacket()
{
    if (!m_formatCtx) return std::nullopt;

    auto pkt = createPacket();
    int ret = av_read_frame(m_formatCtx.get(), pkt.get());

    if (ret == AVERROR_EOF) {
        return std::nullopt;
    }
    if (ret < 0) {
        throw std::runtime_error("Error reading packet: " + avErrorToString(ret));
    }

    return pkt;
}

std::optional<AVPacketPtr> Demuxer::readAudioPacket()
{
    while (auto pkt = readPacket()) {
        if ((*pkt)->stream_index == m_info.audioStreamIndex) {
            return pkt;
        }
        // Discard non-audio packets
    }
    return std::nullopt;
}

std::optional<AVPacketPtr> Demuxer::readVideoPacket()
{
    while (auto pkt = readPacket()) {
        if ((*pkt)->stream_index == m_info.videoStreamIndex) {
            return pkt;
        }
        // Discard non-video packets
    }
    return std::nullopt;
}

bool Demuxer::seek(double seconds)
{
    if (!m_formatCtx) return false;

    int64_t timestamp = static_cast<int64_t>(seconds * AV_TIME_BASE);
    int ret = av_seek_frame(m_formatCtx.get(), -1, timestamp, AVSEEK_FLAG_BACKWARD);
    return ret >= 0;
}

bool Demuxer::seekAudio(double seconds)
{
    if (!m_formatCtx || m_info.audioStreamIndex < 0) return false;

    AVStream* stream = audioStream();
    int64_t timestamp = secondsToPts(seconds, stream->time_base);
    int ret = av_seek_frame(m_formatCtx.get(), m_info.audioStreamIndex, timestamp, AVSEEK_FLAG_BACKWARD);
    return ret >= 0;
}

bool Demuxer::seekVideo(double seconds)
{
    if (!m_formatCtx || m_info.videoStreamIndex < 0) return false;

    AVStream* stream = videoStream();
    int64_t timestamp = secondsToPts(seconds, stream->time_base);
    int ret = av_seek_frame(m_formatCtx.get(), m_info.videoStreamIndex, timestamp, AVSEEK_FLAG_BACKWARD);
    return ret >= 0;
}

double Demuxer::audioTimestamp(int64_t pts) const
{
    if (auto stream = audioStream()) {
        return ptsToSeconds(pts, stream->time_base);
    }
    return 0.0;
}

double Demuxer::videoTimestamp(int64_t pts) const
{
    if (auto stream = videoStream()) {
        return ptsToSeconds(pts, stream->time_base);
    }
    return 0.0;
}

} // namespace ClipTune
