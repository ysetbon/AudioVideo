#include "ClipItem.h"
#include "TimelineWidget.h"
#include "WaveformCache.h"
#include "audio/FadeDSP.h"
#include <QPainter>
#include <QCursor>
#include <QGraphicsScene>
#include <QFileInfo>
#include <algorithm>

namespace ClipTune {

ClipItem::ClipItem(ClipPtr clip, TimelineWidget* timeline, QGraphicsItem* parent)
    : QGraphicsRectItem(parent)
    , m_clip(clip)
    , m_timeline(timeline)
{
    setAcceptHoverEvents(true);
    setFlag(QGraphicsItem::ItemIsMovable, false);  // We handle movement ourselves
    setFlag(QGraphicsItem::ItemIsSelectable, true);
    setFlag(QGraphicsItem::ItemSendsGeometryChanges, true);

    updateFromClip();
}

void ClipItem::updateFromClip()
{
    if (!m_clip) return;

    double x = m_clip->timelineStart() * m_pixelsPerSecond;
    double width = m_clip->duration() * m_pixelsPerSecond;

    setRect(0, 0, width, rect().height() > 0 ? rect().height() : 60);
    setPos(x, pos().y());

    update();
}

void ClipItem::setPixelsPerSecond(double pps)
{
    m_pixelsPerSecond = pps;
    updateFromClip();
}

void ClipItem::setSelected(bool selected)
{
    m_selected = selected;
    update();
}

void ClipItem::paint(QPainter* painter, const QStyleOptionGraphicsItem* /*option*/, QWidget* /*widget*/)
{
    QRectF r = rect();

    // Background
    QColor bgColor = (m_clip->type() == ClipType::Audio)
                     ? QColor(80, 120, 180)
                     : QColor(120, 180, 80);

    if (m_clip->isMuted()) {
        bgColor = bgColor.darker(150);
    }

    if (m_selected) {
        bgColor = bgColor.lighter(120);
    }

    painter->fillRect(r, bgColor);

    // Draw content based on type
    if (m_clip->type() == ClipType::Audio || m_clip->type() == ClipType::AudioVideo) {
        paintAudioClip(painter, r);
    }
    if (m_clip->type() == ClipType::Video || m_clip->type() == ClipType::AudioVideo) {
        paintVideoClip(painter, r);
    }

    // Draw fade overlay
    paintFadeOverlay(painter, r);

    // Border
    painter->setPen(m_selected ? QPen(Qt::white, 2) : QPen(Qt::black, 1));
    painter->drawRect(r);

    // Clip name
    painter->setPen(Qt::white);
    QString name = QFileInfo(m_clip->mediaPath()).fileName();
    QRectF textRect = r.adjusted(4, 2, -4, -2);
    painter->drawText(textRect, Qt::AlignLeft | Qt::AlignTop, name);

    // Fade handles (if selected)
    if (m_selected) {
        paintFadeHandles(painter, r);
    }
}

void ClipItem::paintAudioClip(QPainter* painter, const QRectF& rect)
{
    paintWaveform(painter, rect);
}

void ClipItem::paintVideoClip(QPainter* painter, const QRectF& rect)
{
    // Draw film strip pattern
    painter->setPen(Qt::NoPen);
    painter->setBrush(QColor(0, 0, 0, 30));

    double sprocketSize = 6;
    double spacing = 20;
    double y1 = rect.top() + 2;
    double y2 = rect.bottom() - sprocketSize - 2;

    for (double x = rect.left() + 5; x < rect.right() - sprocketSize; x += spacing) {
        painter->drawRect(QRectF(x, y1, sprocketSize, sprocketSize));
        painter->drawRect(QRectF(x, y2, sprocketSize, sprocketSize));
    }
}

void ClipItem::paintWaveform(QPainter* painter, const QRectF& rect)
{
    if (!m_waveformCache) return;

    const WaveformData* waveform = m_waveformCache->getWaveform(m_clip->mediaPath());
    if (!waveform) return;

    int numBuckets = static_cast<int>(rect.width());
    if (numBuckets <= 0) return;

    std::vector<float> minPeaks, maxPeaks;
    waveform->getPeaksForRange(m_clip->inPoint(), m_clip->outPoint(), numBuckets, minPeaks, maxPeaks);

    QPainterPath path;
    double centerY = rect.center().y();
    double amplitude = rect.height() * 0.4;

    // Draw waveform
    painter->setPen(QPen(QColor(200, 220, 255), 1));

    for (int i = 0; i < numBuckets; ++i) {
        double x = rect.left() + i;
        double minY = centerY - minPeaks[i] * amplitude;
        double maxY = centerY - maxPeaks[i] * amplitude;
        painter->drawLine(QPointF(x, minY), QPointF(x, maxY));
    }
}

void ClipItem::paintFadeOverlay(QPainter* painter, const QRectF& rect)
{
    double fadeInPx = m_clip->fadeInSec() * m_pixelsPerSecond;
    double fadeOutPx = m_clip->fadeOutSec() * m_pixelsPerSecond;

    if (fadeInPx > 0) {
        QLinearGradient grad(rect.left(), 0, rect.left() + fadeInPx, 0);
        grad.setColorAt(0, QColor(0, 0, 0, 150));
        grad.setColorAt(1, QColor(0, 0, 0, 0));
        painter->fillRect(QRectF(rect.left(), rect.top(), fadeInPx, rect.height()), grad);

        // Fade line
        painter->setPen(QPen(Qt::yellow, 2));
        painter->drawLine(QPointF(rect.left(), rect.bottom()),
                         QPointF(rect.left() + fadeInPx, rect.top()));
    }

    if (fadeOutPx > 0) {
        QLinearGradient grad(rect.right() - fadeOutPx, 0, rect.right(), 0);
        grad.setColorAt(0, QColor(0, 0, 0, 0));
        grad.setColorAt(1, QColor(0, 0, 0, 150));
        painter->fillRect(QRectF(rect.right() - fadeOutPx, rect.top(), fadeOutPx, rect.height()), grad);

        // Fade line
        painter->setPen(QPen(Qt::yellow, 2));
        painter->drawLine(QPointF(rect.right() - fadeOutPx, rect.top()),
                         QPointF(rect.right(), rect.bottom()));
    }
}

void ClipItem::paintFadeHandles(QPainter* painter, const QRectF& rect)
{
    painter->setBrush(Qt::yellow);
    painter->setPen(QPen(Qt::black, 1));

    // Fade in handle
    double fadeInPx = m_clip->fadeInSec() * m_pixelsPerSecond;
    QRectF fadeInHandle(rect.left() + fadeInPx - FadeHandleSize/2, rect.top() - FadeHandleSize/2,
                        FadeHandleSize, FadeHandleSize);
    painter->drawEllipse(fadeInHandle);

    // Fade out handle
    double fadeOutPx = m_clip->fadeOutSec() * m_pixelsPerSecond;
    QRectF fadeOutHandle(rect.right() - fadeOutPx - FadeHandleSize/2, rect.top() - FadeHandleSize/2,
                         FadeHandleSize, FadeHandleSize);
    painter->drawEllipse(fadeOutHandle);
}

ClipItem::DragMode ClipItem::dragModeAt(const QPointF& pos) const
{
    QRectF r = rect();

    // Check fade handles first (only if selected)
    if (m_selected) {
        if (fadeInHandleRect().contains(pos)) return DragMode::FadeInHandle;
        if (fadeOutHandleRect().contains(pos)) return DragMode::FadeOutHandle;
    }

    // Check trim zones
    if (pos.x() < TrimZone) return DragMode::TrimLeft;
    if (pos.x() > r.width() - TrimZone) return DragMode::TrimRight;

    return DragMode::Move;
}

QRectF ClipItem::fadeInHandleRect() const
{
    double fadeInPx = m_clip->fadeInSec() * m_pixelsPerSecond;
    return QRectF(fadeInPx - FadeHandleSize/2, -FadeHandleSize/2,
                  FadeHandleSize, FadeHandleSize);
}

QRectF ClipItem::fadeOutHandleRect() const
{
    double fadeOutPx = m_clip->fadeOutSec() * m_pixelsPerSecond;
    return QRectF(rect().width() - fadeOutPx - FadeHandleSize/2, -FadeHandleSize/2,
                  FadeHandleSize, FadeHandleSize);
}

void ClipItem::mousePressEvent(QGraphicsSceneMouseEvent* event)
{
    if (event->button() == Qt::LeftButton) {
        m_dragMode = dragModeAt(event->pos());
        m_dragStartPos = event->scenePos();
        m_dragStartTimeline = m_clip->timelineStart();
        m_dragStartIn = m_clip->inPoint();
        m_dragStartOut = m_clip->outPoint();
        m_dragStartFadeIn = m_clip->fadeInSec();
        m_dragStartFadeOut = m_clip->fadeOutSec();
        event->accept();
    } else {
        QGraphicsRectItem::mousePressEvent(event);
    }
}

void ClipItem::mouseMoveEvent(QGraphicsSceneMouseEvent* event)
{
    if (m_dragMode == DragMode::None) {
        QGraphicsRectItem::mouseMoveEvent(event);
        return;
    }

    double dx = (event->scenePos().x() - m_dragStartPos.x()) / m_pixelsPerSecond;

    switch (m_dragMode) {
        case DragMode::Move: {
            double newStart = std::max(0.0, m_dragStartTimeline + dx);
            m_clip->setTimelineStart(newStart);
            break;
        }
        case DragMode::TrimLeft: {
            double newIn = std::clamp(m_dragStartIn + dx, 0.0, m_dragStartOut - 0.1);
            double trimDelta = newIn - m_dragStartIn;
            m_clip->setInPoint(newIn);
            m_clip->setTimelineStart(m_dragStartTimeline + trimDelta);
            break;
        }
        case DragMode::TrimRight: {
            double newOut = std::clamp(m_dragStartOut + dx, m_dragStartIn + 0.1, m_clip->mediaDuration());
            m_clip->setOutPoint(newOut);
            break;
        }
        case DragMode::FadeInHandle: {
            double newFadeIn = std::clamp(m_dragStartFadeIn + dx, 0.0, m_clip->duration());
            m_clip->setFadeIn(newFadeIn);
            break;
        }
        case DragMode::FadeOutHandle: {
            double newFadeOut = std::clamp(m_dragStartFadeOut - dx, 0.0, m_clip->duration());
            m_clip->setFadeOut(newFadeOut);
            break;
        }
        default:
            break;
    }

    updateFromClip();
    event->accept();
}

void ClipItem::mouseReleaseEvent(QGraphicsSceneMouseEvent* event)
{
    if (m_dragMode != DragMode::None) {
        // TODO: Create undo command for the edit
        m_dragMode = DragMode::None;
        event->accept();
    } else {
        QGraphicsRectItem::mouseReleaseEvent(event);
    }
}

void ClipItem::hoverMoveEvent(QGraphicsSceneHoverEvent* event)
{
    DragMode mode = dragModeAt(event->pos());

    switch (mode) {
        case DragMode::TrimLeft:
        case DragMode::TrimRight:
            setCursor(Qt::SizeHorCursor);
            break;
        case DragMode::FadeInHandle:
        case DragMode::FadeOutHandle:
            setCursor(Qt::CrossCursor);
            break;
        default:
            setCursor(Qt::OpenHandCursor);
            break;
    }

    QGraphicsRectItem::hoverMoveEvent(event);
}

QVariant ClipItem::itemChange(GraphicsItemChange change, const QVariant& value)
{
    if (change == ItemSelectedChange) {
        m_selected = value.toBool();
    }
    return QGraphicsRectItem::itemChange(change, value);
}

} // namespace ClipTune
