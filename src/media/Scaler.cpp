#include "Scaler.h"
#include <stdexcept>

namespace ClipTune {

Scaler::Scaler() = default;

Scaler::~Scaler()
{
    close();
}

bool Scaler::init(int srcWidth, int srcHeight, AVPixelFormat srcFormat,
                  int dstWidth, int dstHeight, AVPixelFormat dstFormat)
{
    close();

    m_srcWidth = srcWidth;
    m_srcHeight = srcHeight;
    m_dstWidth = dstWidth;
    m_dstHeight = dstHeight;
    m_srcFormat = srcFormat;
    m_dstFormat = dstFormat;

    SwsContext* ctx = sws_getContext(srcWidth, srcHeight, srcFormat,
                                      dstWidth, dstHeight, dstFormat,
                                      SWS_BILINEAR, nullptr, nullptr, nullptr);

    if (!ctx) {
        return false;
    }

    m_swsCtx.reset(ctx);
    return true;
}

void Scaler::close()
{
    m_swsCtx.reset();
}

AVFramePtr Scaler::scale(AVFrame* srcFrame)
{
    if (!m_swsCtx || !srcFrame) {
        return nullptr;
    }

    auto dstFrame = createFrame();
    dstFrame->format = m_dstFormat;
    dstFrame->width = m_dstWidth;
    dstFrame->height = m_dstHeight;

    int ret = av_frame_get_buffer(dstFrame.get(), 0);
    if (ret < 0) {
        throw std::runtime_error("Failed to allocate frame buffer: " + avErrorToString(ret));
    }

    sws_scale(m_swsCtx.get(),
              srcFrame->data, srcFrame->linesize,
              0, m_srcHeight,
              dstFrame->data, dstFrame->linesize);

    // Copy timestamp
    dstFrame->pts = srcFrame->pts;

    return dstFrame;
}

QImage Scaler::toQImage(AVFrame* frame)
{
    if (!frame || frame->format != AV_PIX_FMT_RGB24) {
        return QImage();
    }

    // Create QImage from frame data
    QImage image(frame->data[0],
                 frame->width, frame->height,
                 frame->linesize[0],
                 QImage::Format_RGB888);

    // Deep copy to detach from frame buffer
    return image.copy();
}

QImage Scaler::scaleToQImage(AVFrame* srcFrame)
{
    if (!srcFrame) {
        return QImage();
    }

    // If scaler not initialized or format changed, initialize
    if (!m_swsCtx ||
        srcFrame->width != m_srcWidth ||
        srcFrame->height != m_srcHeight ||
        static_cast<AVPixelFormat>(srcFrame->format) != m_srcFormat) {

        if (!init(srcFrame->width, srcFrame->height,
                  static_cast<AVPixelFormat>(srcFrame->format),
                  m_dstWidth > 0 ? m_dstWidth : srcFrame->width,
                  m_dstHeight > 0 ? m_dstHeight : srcFrame->height,
                  AV_PIX_FMT_RGB24)) {
            return QImage();
        }
    }

    auto rgbFrame = scale(srcFrame);
    if (!rgbFrame) {
        return QImage();
    }

    return toQImage(rgbFrame.get());
}

} // namespace ClipTune
