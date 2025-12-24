#pragma once

#include <QWidget>

namespace ClipTune {

class RulerWidget : public QWidget {
    Q_OBJECT

public:
    explicit RulerWidget(QWidget* parent = nullptr);

    // View settings
    void setPixelsPerSecond(double pps);
    double pixelsPerSecond() const { return m_pixelsPerSecond; }

    void setViewOffset(double seconds);
    double viewOffset() const { return m_viewOffset; }

    void setDuration(double seconds) { m_duration = seconds; update(); }
    double duration() const { return m_duration; }

    // Playhead
    void setPlayheadTime(double seconds);
    double playheadTime() const { return m_playheadTime; }

    // Convert between x position and time
    double xToTime(double x) const;
    double timeToX(double time) const;

signals:
    void playheadDragged(double time);
    void playheadClicked(double time);

protected:
    void paintEvent(QPaintEvent* event) override;
    void mousePressEvent(QMouseEvent* event) override;
    void mouseMoveEvent(QMouseEvent* event) override;
    void mouseReleaseEvent(QMouseEvent* event) override;

private:
    QString formatTime(double seconds) const;

    double m_pixelsPerSecond = 100.0;
    double m_viewOffset = 0.0;
    double m_duration = 0.0;
    double m_playheadTime = 0.0;

    bool m_draggingPlayhead = false;
};

} // namespace ClipTune
