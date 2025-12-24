#include "PreviewWidget.h"
#include <QPainter>
#include <QMouseEvent>

namespace ClipTune {

PreviewWidget::PreviewWidget(QWidget* parent)
    : QWidget(parent)
{
    setMinimumSize(320, 180);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    setStyleSheet("background-color: black;");
}

void PreviewWidget::setFrame(const QImage& frame)
{
    QMutexLocker locker(&m_frameMutex);
    m_frame = frame;
    m_needsRescale = true;

    if (!frame.isNull()) {
        m_aspectRatio = static_cast<double>(frame.width()) / frame.height();
    }

    update();
}

void PreviewWidget::clearFrame()
{
    QMutexLocker locker(&m_frameMutex);
    m_frame = QImage();
    m_scaledFrame = QImage();
    update();
}

void PreviewWidget::setVideoSize(int width, int height)
{
    if (height > 0) {
        m_aspectRatio = static_cast<double>(width) / height;
        update();
    }
}

void PreviewWidget::paintEvent(QPaintEvent* /*event*/)
{
    QPainter painter(this);
    painter.setRenderHint(QPainter::SmoothPixmapTransform);

    // Fill background
    painter.fillRect(rect(), Qt::black);

    QMutexLocker locker(&m_frameMutex);

    if (m_frame.isNull()) {
        // Draw placeholder
        painter.setPen(QColor(80, 80, 80));
        painter.drawText(rect(), Qt::AlignCenter, "No Video");
        return;
    }

    // Calculate video display rect
    QRect videoRect = calculateVideoRect();

    // Rescale if needed
    if (m_needsRescale || m_scaledFrame.size() != videoRect.size()) {
        m_scaledFrame = m_frame.scaled(videoRect.size(), Qt::IgnoreAspectRatio, Qt::SmoothTransformation);
        m_needsRescale = false;
    }

    // Draw the frame
    painter.drawImage(videoRect, m_scaledFrame);
}

void PreviewWidget::mousePressEvent(QMouseEvent* event)
{
    if (event->button() == Qt::LeftButton) {
        emit clicked();
    }
    QWidget::mousePressEvent(event);
}

void PreviewWidget::mouseDoubleClickEvent(QMouseEvent* event)
{
    if (event->button() == Qt::LeftButton) {
        emit doubleClicked();
    }
    QWidget::mouseDoubleClickEvent(event);
}

void PreviewWidget::resizeEvent(QResizeEvent* event)
{
    m_needsRescale = true;
    QWidget::resizeEvent(event);
}

QRect PreviewWidget::calculateVideoRect() const
{
    QSize widgetSize = size();
    double widgetAspect = static_cast<double>(widgetSize.width()) / widgetSize.height();

    int videoWidth, videoHeight;

    if (widgetAspect > m_aspectRatio) {
        // Widget is wider than video - fit to height
        videoHeight = widgetSize.height();
        videoWidth = static_cast<int>(videoHeight * m_aspectRatio);
    } else {
        // Widget is taller than video - fit to width
        videoWidth = widgetSize.width();
        videoHeight = static_cast<int>(videoWidth / m_aspectRatio);
    }

    int x = (widgetSize.width() - videoWidth) / 2;
    int y = (widgetSize.height() - videoHeight) / 2;

    return QRect(x, y, videoWidth, videoHeight);
}

} // namespace ClipTune
