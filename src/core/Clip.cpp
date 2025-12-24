#include "Clip.h"
#include <algorithm>

namespace ClipTune {

Clip::Clip(const QString& mediaPath, ClipType type)
    : m_id(QUuid::createUuid())
    , m_mediaPath(mediaPath)
    , m_type(type)
{
}

Clip::Clip(const Clip& other)
    : m_id(QUuid::createUuid())  // New clip gets new ID
    , m_mediaPath(other.m_mediaPath)
    , m_type(other.m_type)
    , m_timelineStart(other.m_timelineStart)
    , m_inPoint(other.m_inPoint)
    , m_outPoint(other.m_outPoint)
    , m_mediaDuration(other.m_mediaDuration)
    , m_properties(other.m_properties)
{
}

Clip& Clip::operator=(const Clip& other)
{
    if (this != &other) {
        // Keep our ID
        m_mediaPath = other.m_mediaPath;
        m_type = other.m_type;
        m_timelineStart = other.m_timelineStart;
        m_inPoint = other.m_inPoint;
        m_outPoint = other.m_outPoint;
        m_mediaDuration = other.m_mediaDuration;
        m_properties = other.m_properties;
    }
    return *this;
}

void Clip::setTimelineStart(double seconds)
{
    m_timelineStart = std::max(0.0, seconds);
}

void Clip::setInPoint(double seconds)
{
    m_inPoint = std::clamp(seconds, 0.0, m_outPoint);
}

void Clip::setOutPoint(double seconds)
{
    m_outPoint = std::clamp(seconds, m_inPoint, m_mediaDuration);
}

void Clip::setFadeIn(double seconds)
{
    m_properties.fade.fadeInSec = std::clamp(seconds, 0.0, duration());
}

void Clip::setFadeOut(double seconds)
{
    m_properties.fade.fadeOutSec = std::clamp(seconds, 0.0, duration());
}

std::unique_ptr<Clip> Clip::split(double timelinePosition)
{
    // Validate split position is within clip
    if (timelinePosition <= m_timelineStart || timelinePosition >= timelineEnd()) {
        return nullptr;
    }

    // Calculate source time at split point
    double splitSourceTime = timelineToSourceTime(timelinePosition);

    // Create new clip for the right portion
    auto newClip = std::make_unique<Clip>(m_mediaPath, m_type);
    newClip->m_mediaDuration = m_mediaDuration;
    newClip->m_inPoint = splitSourceTime;
    newClip->m_outPoint = m_outPoint;
    newClip->m_timelineStart = timelinePosition;
    newClip->m_properties = m_properties;

    // Adjust fade for new clip
    double leftDuration = splitSourceTime - m_inPoint;
    double rightDuration = m_outPoint - splitSourceTime;

    // Fade in stays on left clip, fade out moves to right clip
    newClip->m_properties.fade.fadeInSec = 0.0;
    newClip->m_properties.fade.fadeOutSec = std::min(m_properties.fade.fadeOutSec, rightDuration);

    // Adjust this clip (left portion)
    m_outPoint = splitSourceTime;
    m_properties.fade.fadeInSec = std::min(m_properties.fade.fadeInSec, leftDuration);
    m_properties.fade.fadeOutSec = 0.0;

    return newClip;
}

bool Clip::containsTime(double timelineSec) const
{
    return timelineSec >= m_timelineStart && timelineSec < timelineEnd();
}

double Clip::timelineToSourceTime(double timelineSec) const
{
    return m_inPoint + (timelineSec - m_timelineStart);
}

std::unique_ptr<Clip> Clip::clone() const
{
    auto cloned = std::make_unique<Clip>(*this);
    return cloned;
}

} // namespace ClipTune
