#pragma once

#include "core/Project.h"
#include "ClipItem.h"
#include "RulerWidget.h"
#include "TrackHeaderWidget.h"
#include "WaveformCache.h"
#include <QWidget>
#include <QScrollArea>
#include <QGraphicsScene>
#include <QGraphicsView>
#include <vector>
#include <unordered_map>

namespace ClipTune {

class TimelineWidget : public QWidget {
    Q_OBJECT

public:
    explicit TimelineWidget(QWidget* parent = nullptr);
    ~TimelineWidget() override;

    // Project
    void setProject(Project* project);
    Project* project() const { return m_project; }

    // Zoom (pixels per second)
    void setPixelsPerSecond(double pps);
    double pixelsPerSecond() const { return m_pixelsPerSecond; }
    void zoomIn();
    void zoomOut();
    void zoomToFit();

    // Scroll position
    void setViewOffset(double seconds);
    double viewOffset() const { return m_viewOffset; }

    // Playhead
    void setPlayheadTime(double seconds);
    double playheadTime() const { return m_playheadTime; }

    // Selection
    ClipPtr selectedClip() const { return m_selectedClip; }
    TrackPtr selectedTrack() const { return m_selectedTrack; }
    void selectClip(ClipPtr clip);
    void selectTrack(TrackPtr track);
    void clearSelection();

    // Waveform cache
    WaveformCache& waveformCache() { return m_waveformCache; }

    // Split clip at playhead
    void splitClipAtPlayhead();

    // Delete selected clip
    void deleteSelectedClip();

signals:
    void playheadMoved(double time);
    void selectionChanged();
    void clipMoved(ClipPtr clip);
    void clipTrimmed(ClipPtr clip);
    void zoomChanged(double pixelsPerSecond);

public slots:
    void refresh();

protected:
    void resizeEvent(QResizeEvent* event) override;
    void wheelEvent(QWheelEvent* event) override;

private slots:
    void onPlayheadDragged(double time);
    void onHorizontalScroll(int value);
    void onClipAdded(ClipPtr clip, TrackPtr track);
    void onClipRemoved(const QUuid& clipId, const QUuid& trackId);
    void onTrackAdded(TrackPtr track);
    void onTrackRemoved(const QUuid& trackId);

private:
    void setupUi();
    void rebuildTracks();
    void rebuildClips();
    void updateSceneRect();
    void updatePlayheadLine();

    ClipItem* findClipItem(const QUuid& clipId) const;
    ClipItem* createClipItem(ClipPtr clip, int trackIndex);

    Project* m_project = nullptr;

    // UI Components
    RulerWidget* m_ruler = nullptr;
    QWidget* m_headerContainer = nullptr;
    QGraphicsScene* m_scene = nullptr;
    QGraphicsView* m_view = nullptr;
    QScrollArea* m_headerScrollArea = nullptr;

    // Clip items
    std::vector<ClipItem*> m_clipItems;
    std::unordered_map<QUuid, ClipItem*> m_clipItemMap;

    // Track headers
    std::vector<TrackHeaderWidget*> m_trackHeaders;

    // Playhead line
    QGraphicsLineItem* m_playheadLine = nullptr;

    // View state
    double m_pixelsPerSecond = 100.0;
    double m_viewOffset = 0.0;
    double m_playheadTime = 0.0;

    // Selection
    ClipPtr m_selectedClip;
    TrackPtr m_selectedTrack;

    // Waveform cache
    WaveformCache m_waveformCache;

    static constexpr double MinPixelsPerSecond = 10.0;
    static constexpr double MaxPixelsPerSecond = 500.0;
};

} // namespace ClipTune
