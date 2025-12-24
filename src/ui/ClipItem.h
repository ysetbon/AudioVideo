#pragma once

#include "core/Clip.h"
#include <QGraphicsRectItem>
#include <QGraphicsSceneMouseEvent>

namespace ClipTune {

class TimelineWidget;
class WaveformCache;

class ClipItem : public QGraphicsRectItem {
public:
    enum class DragMode {
        None,
        Move,
        TrimLeft,
        TrimRight,
        FadeInHandle,
        FadeOutHandle
    };

    ClipItem(ClipPtr clip, TimelineWidget* timeline, QGraphicsItem* parent = nullptr);
    ~ClipItem() override = default;

    ClipPtr clip() const { return m_clip; }

    // Update visual from clip data
    void updateFromClip();

    // Set zoom level (pixels per second)
    void setPixelsPerSecond(double pps);
    double pixelsPerSecond() const { return m_pixelsPerSecond; }

    // Set waveform cache
    void setWaveformCache(WaveformCache* cache) { m_waveformCache = cache; }

    // Selection
    bool isSelected() const { return m_selected; }
    void setSelected(bool selected);

protected:
    void paint(QPainter* painter, const QStyleOptionGraphicsItem* option, QWidget* widget) override;
    void mousePressEvent(QGraphicsSceneMouseEvent* event) override;
    void mouseMoveEvent(QGraphicsSceneMouseEvent* event) override;
    void mouseReleaseEvent(QGraphicsSceneMouseEvent* event) override;
    void hoverMoveEvent(QGraphicsSceneHoverEvent* event) override;
    QVariant itemChange(GraphicsItemChange change, const QVariant& value) override;

private:
    void paintAudioClip(QPainter* painter, const QRectF& rect);
    void paintVideoClip(QPainter* painter, const QRectF& rect);
    void paintWaveform(QPainter* painter, const QRectF& rect);
    void paintFadeOverlay(QPainter* painter, const QRectF& rect);
    void paintFadeHandles(QPainter* painter, const QRectF& rect);

    DragMode dragModeAt(const QPointF& pos) const;
    QRectF fadeInHandleRect() const;
    QRectF fadeOutHandleRect() const;

    ClipPtr m_clip;
    TimelineWidget* m_timeline;
    WaveformCache* m_waveformCache = nullptr;

    double m_pixelsPerSecond = 100.0;
    bool m_selected = false;

    DragMode m_dragMode = DragMode::None;
    QPointF m_dragStartPos;
    double m_dragStartTimeline = 0.0;
    double m_dragStartIn = 0.0;
    double m_dragStartOut = 0.0;
    double m_dragStartFadeIn = 0.0;
    double m_dragStartFadeOut = 0.0;

    static constexpr double HandleWidth = 8.0;
    static constexpr double TrimZone = 10.0;
    static constexpr double FadeHandleSize = 12.0;
};

} // namespace ClipTune
