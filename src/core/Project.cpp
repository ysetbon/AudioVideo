#include "Project.h"
#include <algorithm>

namespace ClipTune {

Project::Project(QObject* parent)
    : QObject(parent)
    , m_undoStack(this)
{
}

void Project::setModified(bool modified)
{
    if (m_modified != modified) {
        m_modified = modified;
        emit modifiedChanged(modified);
    }
}

TrackPtr Project::addTrack(TrackType type, const QString& name)
{
    auto track = std::make_shared<Track>(type, name);
    m_tracks.push_back(track);
    setModified(true);
    emit trackAdded(track);
    emit durationChanged(duration());
    return track;
}

void Project::removeTrack(const QUuid& trackId)
{
    auto it = std::find_if(m_tracks.begin(), m_tracks.end(),
                           [&trackId](const TrackPtr& t) { return t->id() == trackId; });
    if (it != m_tracks.end()) {
        m_tracks.erase(it);
        setModified(true);
        emit trackRemoved(trackId);
        emit durationChanged(duration());
    }
}

void Project::moveTrack(int fromIndex, int toIndex)
{
    if (fromIndex < 0 || fromIndex >= static_cast<int>(m_tracks.size()) ||
        toIndex < 0 || toIndex >= static_cast<int>(m_tracks.size()) ||
        fromIndex == toIndex) {
        return;
    }

    auto track = m_tracks[fromIndex];
    m_tracks.erase(m_tracks.begin() + fromIndex);
    m_tracks.insert(m_tracks.begin() + toIndex, track);
    setModified(true);
    emit trackMoved(fromIndex, toIndex);
}

TrackPtr Project::findTrack(const QUuid& trackId) const
{
    auto it = std::find_if(m_tracks.begin(), m_tracks.end(),
                           [&trackId](const TrackPtr& t) { return t->id() == trackId; });
    return (it != m_tracks.end()) ? *it : nullptr;
}

TrackPtr Project::trackAt(int index) const
{
    if (index >= 0 && index < static_cast<int>(m_tracks.size())) {
        return m_tracks[index];
    }
    return nullptr;
}

int Project::trackIndex(const QUuid& trackId) const
{
    for (size_t i = 0; i < m_tracks.size(); ++i) {
        if (m_tracks[i]->id() == trackId) {
            return static_cast<int>(i);
        }
    }
    return -1;
}

std::vector<TrackPtr> Project::audioTracks() const
{
    std::vector<TrackPtr> result;
    for (const auto& track : m_tracks) {
        if (track->type() == TrackType::Audio) {
            result.push_back(track);
        }
    }
    return result;
}

int Project::audioTrackCount() const
{
    return static_cast<int>(std::count_if(m_tracks.begin(), m_tracks.end(),
                                          [](const TrackPtr& t) { return t->type() == TrackType::Audio; }));
}

std::vector<TrackPtr> Project::videoTracks() const
{
    std::vector<TrackPtr> result;
    for (const auto& track : m_tracks) {
        if (track->type() == TrackType::Video) {
            result.push_back(track);
        }
    }
    return result;
}

int Project::videoTrackCount() const
{
    return static_cast<int>(std::count_if(m_tracks.begin(), m_tracks.end(),
                                          [](const TrackPtr& t) { return t->type() == TrackType::Video; }));
}

ClipPtr Project::findClip(const QUuid& clipId) const
{
    for (const auto& track : m_tracks) {
        if (auto clip = track->findClip(clipId)) {
            return clip;
        }
    }
    return nullptr;
}

TrackPtr Project::trackForClip(const QUuid& clipId) const
{
    for (const auto& track : m_tracks) {
        if (track->findClip(clipId)) {
            return track;
        }
    }
    return nullptr;
}

double Project::duration() const
{
    double maxDuration = 0.0;
    for (const auto& track : m_tracks) {
        maxDuration = std::max(maxDuration, track->duration());
    }
    return maxDuration;
}

void Project::clear()
{
    m_tracks.clear();
    m_filePath.clear();
    m_undoStack.clear();
    setModified(false);
    emit projectCleared();
    emit durationChanged(0.0);
}

ClipPtr Project::importMedia(const QString& filePath, TrackPtr targetTrack, double timelineStart)
{
    if (!targetTrack) return nullptr;

    // Determine clip type based on track type
    ClipType clipType = (targetTrack->type() == TrackType::Audio) ? ClipType::Audio : ClipType::Video;

    auto clip = std::make_shared<Clip>(filePath, clipType);
    clip->setTimelineStart(timelineStart);

    // Media duration will be set by the media engine after probing
    // For now, set a placeholder
    clip->setMediaDuration(0.0);
    clip->setOutPoint(0.0);

    targetTrack->addClip(clip);
    setModified(true);
    emit clipAdded(clip, targetTrack);
    emit durationChanged(duration());

    return clip;
}

} // namespace ClipTune
