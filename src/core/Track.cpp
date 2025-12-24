#include "Track.h"
#include <algorithm>

namespace ClipTune {

Track::Track(TrackType type, const QString& name)
    : m_id(QUuid::createUuid())
    , m_name(name)
    , m_type(type)
{
    if (m_name.isEmpty()) {
        m_name = (type == TrackType::Audio) ? QStringLiteral("Audio Track")
                                             : QStringLiteral("Video Track");
    }
}

Track::Track(const Track& other)
    : m_id(QUuid::createUuid())  // New track gets new ID
    , m_name(other.m_name)
    , m_type(other.m_type)
    , m_volume(other.m_volume)
    , m_pan(other.m_pan)
    , m_muted(other.m_muted)
    , m_solo(other.m_solo)
    , m_height(other.m_height)
{
    // Deep copy clips
    for (const auto& clip : other.m_clips) {
        m_clips.push_back(std::make_shared<Clip>(*clip));
    }
}

Track& Track::operator=(const Track& other)
{
    if (this != &other) {
        // Keep our ID
        m_name = other.m_name;
        m_type = other.m_type;
        m_volume = other.m_volume;
        m_pan = other.m_pan;
        m_muted = other.m_muted;
        m_solo = other.m_solo;
        m_height = other.m_height;

        m_clips.clear();
        for (const auto& clip : other.m_clips) {
            m_clips.push_back(std::make_shared<Clip>(*clip));
        }
    }
    return *this;
}

void Track::addClip(ClipPtr clip)
{
    if (clip) {
        m_clips.push_back(clip);
        sortClips();
    }
}

void Track::removeClip(const QUuid& clipId)
{
    m_clips.erase(
        std::remove_if(m_clips.begin(), m_clips.end(),
                       [&clipId](const ClipPtr& c) { return c->id() == clipId; }),
        m_clips.end());
}

ClipPtr Track::findClip(const QUuid& clipId) const
{
    auto it = std::find_if(m_clips.begin(), m_clips.end(),
                           [&clipId](const ClipPtr& c) { return c->id() == clipId; });
    return (it != m_clips.end()) ? *it : nullptr;
}

ClipPtr Track::clipAt(double timelineSec) const
{
    for (const auto& clip : m_clips) {
        if (clip->containsTime(timelineSec)) {
            return clip;
        }
    }
    return nullptr;
}

std::vector<ClipPtr> Track::clipsInRange(double startSec, double endSec) const
{
    std::vector<ClipPtr> result;
    for (const auto& clip : m_clips) {
        // Clip overlaps range if clip.start < range.end AND clip.end > range.start
        if (clip->timelineStart() < endSec && clip->timelineEnd() > startSec) {
            result.push_back(clip);
        }
    }
    return result;
}

void Track::insertClip(ClipPtr clip, double timelineStart)
{
    if (clip) {
        clip->setTimelineStart(timelineStart);
        m_clips.push_back(clip);
        sortClips();
    }
}

void Track::moveClip(const QUuid& clipId, double newTimelineStart)
{
    if (auto clip = findClip(clipId)) {
        clip->setTimelineStart(newTimelineStart);
        sortClips();
    }
}

ClipPtr Track::splitClipAt(const QUuid& clipId, double timelinePosition)
{
    auto clip = findClip(clipId);
    if (!clip) return nullptr;

    auto newClip = clip->split(timelinePosition);
    if (newClip) {
        auto newClipPtr = ClipPtr(newClip.release());
        m_clips.push_back(newClipPtr);
        sortClips();
        return newClipPtr;
    }
    return nullptr;
}

double Track::duration() const
{
    double maxEnd = 0.0;
    for (const auto& clip : m_clips) {
        maxEnd = std::max(maxEnd, clip->timelineEnd());
    }
    return maxEnd;
}

void Track::sortClips()
{
    std::sort(m_clips.begin(), m_clips.end(),
              [](const ClipPtr& a, const ClipPtr& b) {
                  return a->timelineStart() < b->timelineStart();
              });
}

std::unique_ptr<Track> Track::clone() const
{
    return std::make_unique<Track>(*this);
}

} // namespace ClipTune
