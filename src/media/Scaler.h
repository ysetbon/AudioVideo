#pragma once

#include "FfmpegInit.h"
#include <QImage>

namespace ClipTune {

class Scaler {
public:
    Scaler();
    ~Scaler();

    // Initialize scaler for video conversion
    bool init(int srcWidth, int srcHeight, AVPixelFormat srcFormat,
              int dstWidth, int dstHeight, AVPixelFormat dstFormat = AV_PIX_FMT_RGB24);
    void close();
    bool isOpen() const { return m_swsCtx != nullptr; }

    // Scale/convert frame
    AVFramePtr scale(AVFrame* srcFrame);

    // Convert AVFrame to QImage (RGB24 format)
    QImage toQImage(AVFrame* frame);

    // Scale and convert to QImage in one step
    QImage scaleToQImage(AVFrame* srcFrame);

    // Output dimensions
    int outputWidth() const { return m_dstWidth; }
    int outputHeight() const { return m_dstHeight; }

private:
    SwsContextPtr m_swsCtx;
    int m_srcWidth = 0;
    int m_srcHeight = 0;
    int m_dstWidth = 0;
    int m_dstHeight = 0;
    AVPixelFormat m_srcFormat = AV_PIX_FMT_NONE;
    AVPixelFormat m_dstFormat = AV_PIX_FMT_NONE;
};

} // namespace ClipTune
