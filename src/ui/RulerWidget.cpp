#include "RulerWidget.h"
#include <QPainter>
#include <QMouseEvent>
#include <cmath>

namespace ClipTune {

RulerWidget::RulerWidget(QWidget* parent)
    : QWidget(parent)
{
    setFixedHeight(30);
    setMouseTracking(true);
}

void RulerWidget::setPixelsPerSecond(double pps)
{
    m_pixelsPerSecond = pps;
    update();
}

void RulerWidget::setViewOffset(double seconds)
{
    m_viewOffset = seconds;
    update();
}

void RulerWidget::setPlayheadTime(double seconds)
{
    m_playheadTime = seconds;
    update();
}

double RulerWidget::xToTime(double x) const
{
    return m_viewOffset + x / m_pixelsPerSecond;
}

double RulerWidget::timeToX(double time) const
{
    return (time - m_viewOffset) * m_pixelsPerSecond;
}

void RulerWidget::paintEvent(QPaintEvent* /*event*/)
{
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);

    QRect r = rect();

    // Background
    painter.fillRect(r, QColor(50, 50, 55));

    // Calculate tick interval based on zoom
    double tickInterval = 1.0;  // Start with 1 second
    double pixelsPerTick = tickInterval * m_pixelsPerSecond;

    // Adjust interval to keep ticks readable
    while (pixelsPerTick < 50) {
        tickInterval *= 2;
        pixelsPerTick = tickInterval * m_pixelsPerSecond;
    }
    while (pixelsPerTick > 200) {
        tickInterval /= 2;
        pixelsPerTick = tickInterval * m_pixelsPerSecond;
    }

    // Draw ticks
    painter.setPen(QColor(150, 150, 150));
    QFont font = painter.font();
    font.setPointSize(8);
    painter.setFont(font);

    double startTime = std::floor(m_viewOffset / tickInterval) * tickInterval;
    double endTime = m_viewOffset + width() / m_pixelsPerSecond;

    for (double t = startTime; t <= endTime; t += tickInterval) {
        double x = timeToX(t);
        if (x < 0) continue;

        // Major tick
        painter.drawLine(QPointF(x, r.height() - 15), QPointF(x, r.height()));

        // Time label
        QString label = formatTime(t);
        QRectF textRect(x - 30, 2, 60, 15);
        painter.drawText(textRect, Qt::AlignCenter, label);

        // Minor ticks
        double minorInterval = tickInterval / 4;
        for (int i = 1; i < 4; ++i) {
            double minorT = t + i * minorInterval;
            double minorX = timeToX(minorT);
            if (minorX >= 0 && minorX <= width()) {
                painter.drawLine(QPointF(minorX, r.height() - 8), QPointF(minorX, r.height()));
            }
        }
    }

    // Draw playhead
    double playheadX = timeToX(m_playheadTime);
    if (playheadX >= 0 && playheadX <= width()) {
        painter.setPen(Qt::NoPen);
        painter.setBrush(Qt::red);

        // Triangle marker
        QPolygonF triangle;
        triangle << QPointF(playheadX - 6, 0)
                 << QPointF(playheadX + 6, 0)
                 << QPointF(playheadX, 10);
        painter.drawPolygon(triangle);

        // Vertical line
        painter.setPen(QPen(Qt::red, 1));
        painter.drawLine(QPointF(playheadX, 10), QPointF(playheadX, r.height()));
    }

    // Bottom border
    painter.setPen(QColor(30, 30, 35));
    painter.drawLine(0, r.height() - 1, r.width(), r.height() - 1);
}

void RulerWidget::mousePressEvent(QMouseEvent* event)
{
    if (event->button() == Qt::LeftButton) {
        double time = xToTime(event->position().x());
        time = std::max(0.0, std::min(time, m_duration));
        m_playheadTime = time;
        m_draggingPlayhead = true;
        emit playheadClicked(time);
        update();
    }
}

void RulerWidget::mouseMoveEvent(QMouseEvent* event)
{
    if (m_draggingPlayhead) {
        double time = xToTime(event->position().x());
        time = std::max(0.0, std::min(time, m_duration));
        m_playheadTime = time;
        emit playheadDragged(time);
        update();
    }
}

void RulerWidget::mouseReleaseEvent(QMouseEvent* event)
{
    if (event->button() == Qt::LeftButton) {
        m_draggingPlayhead = false;
    }
}

QString RulerWidget::formatTime(double seconds) const
{
    int totalSeconds = static_cast<int>(seconds);
    int minutes = totalSeconds / 60;
    int secs = totalSeconds % 60;
    int frames = static_cast<int>((seconds - totalSeconds) * 30);  // Assuming 30fps

    if (minutes > 0) {
        return QString("%1:%2:%3")
            .arg(minutes)
            .arg(secs, 2, 10, QChar('0'))
            .arg(frames, 2, 10, QChar('0'));
    } else {
        return QString("%1:%2")
            .arg(secs)
            .arg(frames, 2, 10, QChar('0'));
    }
}

} // namespace ClipTune
