#include "TimelineWidget.h"
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QScrollBar>
#include <QWheelEvent>
#include <cmath>

namespace ClipTune {

TimelineWidget::TimelineWidget(QWidget* parent)
    : QWidget(parent)
    , m_waveformCache(this)
{
    setupUi();

    connect(&m_waveformCache, &WaveformCache::waveformReady,
            this, &TimelineWidget::refresh);
}

TimelineWidget::~TimelineWidget() = default;

void TimelineWidget::setupUi()
{
    auto* mainLayout = new QVBoxLayout(this);
    mainLayout->setContentsMargins(0, 0, 0, 0);
    mainLayout->setSpacing(0);

    // Ruler
    m_ruler = new RulerWidget(this);
    connect(m_ruler, &RulerWidget::playheadDragged, this, &TimelineWidget::onPlayheadDragged);
    connect(m_ruler, &RulerWidget::playheadClicked, this, &TimelineWidget::onPlayheadDragged);

    // Header + timeline container
    auto* contentLayout = new QHBoxLayout();
    contentLayout->setContentsMargins(0, 0, 0, 0);
    contentLayout->setSpacing(0);

    // Track headers scroll area
    m_headerScrollArea = new QScrollArea(this);
    m_headerScrollArea->setFixedWidth(150);
    m_headerScrollArea->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    m_headerScrollArea->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    m_headerScrollArea->setStyleSheet("QScrollArea { border: none; background: #333; }");

    m_headerContainer = new QWidget();
    m_headerContainer->setLayout(new QVBoxLayout());
    m_headerContainer->layout()->setContentsMargins(0, 0, 0, 0);
    m_headerContainer->layout()->setSpacing(0);
    m_headerScrollArea->setWidget(m_headerContainer);

    // Graphics view for clips
    m_scene = new QGraphicsScene(this);
    m_scene->setBackgroundBrush(QColor(40, 40, 45));

    m_view = new QGraphicsView(m_scene, this);
    m_view->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOn);
    m_view->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOn);
    m_view->setAlignment(Qt::AlignLeft | Qt::AlignTop);
    m_view->setStyleSheet("QGraphicsView { border: none; }");

    // Sync vertical scroll
    connect(m_view->verticalScrollBar(), &QScrollBar::valueChanged,
            m_headerScrollArea->verticalScrollBar(), &QScrollBar::setValue);
    connect(m_headerScrollArea->verticalScrollBar(), &QScrollBar::valueChanged,
            m_view->verticalScrollBar(), &QScrollBar::setValue);

    // Sync horizontal scroll with ruler
    connect(m_view->horizontalScrollBar(), &QScrollBar::valueChanged,
            this, &TimelineWidget::onHorizontalScroll);

    // Playhead line
    m_playheadLine = m_scene->addLine(0, 0, 0, 1000, QPen(Qt::red, 1));
    m_playheadLine->setZValue(1000);

    // Add to layouts
    auto* rulerLayout = new QHBoxLayout();
    rulerLayout->setContentsMargins(0, 0, 0, 0);
    rulerLayout->setSpacing(0);
    rulerLayout->addSpacing(150);  // Match header width
    rulerLayout->addWidget(m_ruler);

    mainLayout->addLayout(rulerLayout);
    contentLayout->addWidget(m_headerScrollArea);
    contentLayout->addWidget(m_view);
    mainLayout->addLayout(contentLayout);
}

void TimelineWidget::setProject(Project* project)
{
    // Disconnect old project
    if (m_project) {
        disconnect(m_project, nullptr, this, nullptr);
    }

    m_project = project;

    if (m_project) {
        connect(m_project, &Project::clipAdded, this, &TimelineWidget::onClipAdded);
        connect(m_project, &Project::clipRemoved, this, &TimelineWidget::onClipRemoved);
        connect(m_project, &Project::trackAdded, this, &TimelineWidget::onTrackAdded);
        connect(m_project, &Project::trackRemoved, this, &TimelineWidget::onTrackRemoved);
        connect(m_project, &Project::durationChanged, [this](double d) {
            m_ruler->setDuration(d);
            updateSceneRect();
        });

        m_ruler->setDuration(m_project->duration());
    }

    rebuildTracks();
    rebuildClips();
    updateSceneRect();
}

void TimelineWidget::setPixelsPerSecond(double pps)
{
    m_pixelsPerSecond = std::clamp(pps, MinPixelsPerSecond, MaxPixelsPerSecond);
    m_ruler->setPixelsPerSecond(m_pixelsPerSecond);

    for (auto* item : m_clipItems) {
        item->setPixelsPerSecond(m_pixelsPerSecond);
    }

    updateSceneRect();
    updatePlayheadLine();
    emit zoomChanged(m_pixelsPerSecond);
}

void TimelineWidget::zoomIn()
{
    setPixelsPerSecond(m_pixelsPerSecond * 1.5);
}

void TimelineWidget::zoomOut()
{
    setPixelsPerSecond(m_pixelsPerSecond / 1.5);
}

void TimelineWidget::zoomToFit()
{
    if (!m_project || m_project->duration() <= 0) return;

    double availableWidth = m_view->viewport()->width() - 20;
    double pps = availableWidth / m_project->duration();
    setPixelsPerSecond(pps);
    setViewOffset(0);
}

void TimelineWidget::setViewOffset(double seconds)
{
    m_viewOffset = std::max(0.0, seconds);
    m_ruler->setViewOffset(m_viewOffset);
    m_view->horizontalScrollBar()->setValue(static_cast<int>(m_viewOffset * m_pixelsPerSecond));
}

void TimelineWidget::setPlayheadTime(double seconds)
{
    m_playheadTime = std::max(0.0, seconds);
    m_ruler->setPlayheadTime(m_playheadTime);
    updatePlayheadLine();
}

void TimelineWidget::selectClip(ClipPtr clip)
{
    m_selectedClip = clip;

    for (auto* item : m_clipItems) {
        item->setSelected(item->clip() == clip);
    }

    emit selectionChanged();
}

void TimelineWidget::selectTrack(TrackPtr track)
{
    m_selectedTrack = track;
    emit selectionChanged();
}

void TimelineWidget::clearSelection()
{
    m_selectedClip = nullptr;
    m_selectedTrack = nullptr;

    for (auto* item : m_clipItems) {
        item->setSelected(false);
    }

    emit selectionChanged();
}

void TimelineWidget::splitClipAtPlayhead()
{
    if (!m_selectedClip || !m_project) return;

    auto track = m_project->trackForClip(m_selectedClip->id());
    if (!track) return;

    auto newClip = track->splitClipAt(m_selectedClip->id(), m_playheadTime);
    if (newClip) {
        rebuildClips();
    }
}

void TimelineWidget::deleteSelectedClip()
{
    if (!m_selectedClip || !m_project) return;

    auto track = m_project->trackForClip(m_selectedClip->id());
    if (!track) return;

    track->removeClip(m_selectedClip->id());
    rebuildClips();
    clearSelection();
}

void TimelineWidget::refresh()
{
    for (auto* item : m_clipItems) {
        item->update();
    }
}

void TimelineWidget::resizeEvent(QResizeEvent* event)
{
    QWidget::resizeEvent(event);
    updateSceneRect();
}

void TimelineWidget::wheelEvent(QWheelEvent* event)
{
    if (event->modifiers() & Qt::ControlModifier) {
        // Zoom
        if (event->angleDelta().y() > 0) {
            zoomIn();
        } else {
            zoomOut();
        }
        event->accept();
    } else {
        QWidget::wheelEvent(event);
    }
}

void TimelineWidget::onPlayheadDragged(double time)
{
    setPlayheadTime(time);
    emit playheadMoved(time);
}

void TimelineWidget::onHorizontalScroll(int value)
{
    double offset = value / m_pixelsPerSecond;
    m_viewOffset = offset;
    m_ruler->setViewOffset(offset);
}

void TimelineWidget::onClipAdded(ClipPtr clip, TrackPtr track)
{
    int trackIndex = m_project->trackIndex(track->id());
    if (trackIndex >= 0) {
        auto* item = createClipItem(clip, trackIndex);
        m_waveformCache.generateWaveformAsync(clip->mediaPath());
        updateSceneRect();
    }
}

void TimelineWidget::onClipRemoved(const QUuid& clipId, const QUuid& /*trackId*/)
{
    if (auto* item = findClipItem(clipId)) {
        m_scene->removeItem(item);
        m_clipItems.erase(std::remove(m_clipItems.begin(), m_clipItems.end(), item), m_clipItems.end());
        m_clipItemMap.erase(clipId);
        delete item;
    }
    updateSceneRect();
}

void TimelineWidget::onTrackAdded(TrackPtr /*track*/)
{
    rebuildTracks();
    updateSceneRect();
}

void TimelineWidget::onTrackRemoved(const QUuid& /*trackId*/)
{
    rebuildTracks();
    rebuildClips();
    updateSceneRect();
}

void TimelineWidget::rebuildTracks()
{
    // Clear old headers
    for (auto* header : m_trackHeaders) {
        delete header;
    }
    m_trackHeaders.clear();

    if (!m_project) return;

    auto* layout = static_cast<QVBoxLayout*>(m_headerContainer->layout());

    for (const auto& track : m_project->tracks()) {
        auto* header = new TrackHeaderWidget(track);
        layout->addWidget(header);
        m_trackHeaders.push_back(header);

        connect(header, &TrackHeaderWidget::trackSelected, [this, track]() {
            selectTrack(track);
        });
    }

    layout->addStretch();
}

void TimelineWidget::rebuildClips()
{
    // Clear old items
    for (auto* item : m_clipItems) {
        m_scene->removeItem(item);
        delete item;
    }
    m_clipItems.clear();
    m_clipItemMap.clear();

    if (!m_project) return;

    int trackIndex = 0;
    for (const auto& track : m_project->tracks()) {
        for (const auto& clip : track->clips()) {
            createClipItem(clip, trackIndex);
            m_waveformCache.generateWaveformAsync(clip->mediaPath());
        }
        ++trackIndex;
    }
}

void TimelineWidget::updateSceneRect()
{
    if (!m_project) return;

    double duration = std::max(m_project->duration() + 10.0, 60.0);  // At least 60 seconds
    double width = duration * m_pixelsPerSecond;

    int totalHeight = 0;
    for (const auto& track : m_project->tracks()) {
        totalHeight += track->height();
    }
    totalHeight = std::max(totalHeight, 200);

    m_scene->setSceneRect(0, 0, width, totalHeight);
    updatePlayheadLine();
}

void TimelineWidget::updatePlayheadLine()
{
    double x = m_playheadTime * m_pixelsPerSecond;
    m_playheadLine->setLine(x, 0, x, m_scene->sceneRect().height());
}

ClipItem* TimelineWidget::findClipItem(const QUuid& clipId) const
{
    auto it = m_clipItemMap.find(clipId);
    return (it != m_clipItemMap.end()) ? it->second : nullptr;
}

ClipItem* TimelineWidget::createClipItem(ClipPtr clip, int trackIndex)
{
    auto* item = new ClipItem(clip, this);
    item->setPixelsPerSecond(m_pixelsPerSecond);
    item->setWaveformCache(&m_waveformCache);

    // Calculate Y position
    double y = 0;
    if (m_project) {
        for (int i = 0; i < trackIndex && i < m_project->trackCount(); ++i) {
            y += m_project->trackAt(i)->height();
        }
    }

    auto track = m_project ? m_project->trackAt(trackIndex) : nullptr;
    double height = track ? track->height() : 80;
    item->setRect(0, 0, item->rect().width(), height);
    item->setPos(item->pos().x(), y);

    m_scene->addItem(item);
    m_clipItems.push_back(item);
    m_clipItemMap[clip->id()] = item;

    return item;
}

} // namespace ClipTune
