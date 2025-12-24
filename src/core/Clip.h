#pragma once

#include <QString>
#include <QUuid>
#include <memory>
#include <optional>

namespace ClipTune {

enum class ClipType {
    Audio,
    Video,
    AudioVideo  // Container with both streams
};

enum class FadeCurve {
    Linear,
    Exponential,
    SCurve
};

struct FadeSettings {
    double fadeInSec = 0.0;
    double fadeOutSec = 0.0;
    FadeCurve curve = FadeCurve::Linear;
};

struct ClipProperties {
    double gain = 1.0;          // Linear gain (0.0 to N, 1.0 = unity)
    FadeSettings fade;
    bool muted = false;
};

class Clip {
public:
    Clip(const QString& mediaPath, ClipType type);
    Clip(const Clip& other);
    Clip& operator=(const Clip& other);
    ~Clip() = default;

    // Identity
    QUuid id() const { return m_id; }
    QString mediaPath() const { return m_mediaPath; }
    ClipType type() const { return m_type; }

    // Timeline positioning (in seconds)
    double timelineStart() const { return m_timelineStart; }
    void setTimelineStart(double seconds);

    // Source region (in/out points relative to source media)
    double inPoint() const { return m_inPoint; }
    double outPoint() const { return m_outPoint; }
    void setInPoint(double seconds);
    void setOutPoint(double seconds);

    // Duration on timeline
    double duration() const { return m_outPoint - m_inPoint; }
    double timelineEnd() const { return m_timelineStart + duration(); }

    // Media duration (full source length)
    double mediaDuration() const { return m_mediaDuration; }
    void setMediaDuration(double seconds) { m_mediaDuration = seconds; }

    // Properties
    ClipProperties& properties() { return m_properties; }
    const ClipProperties& properties() const { return m_properties; }

    // Gain shortcuts
    double gain() const { return m_properties.gain; }
    void setGain(double gain) { m_properties.gain = gain; }

    // Fade shortcuts
    double fadeInSec() const { return m_properties.fade.fadeInSec; }
    double fadeOutSec() const { return m_properties.fade.fadeOutSec; }
    void setFadeIn(double seconds);
    void setFadeOut(double seconds);
    FadeCurve fadeCurve() const { return m_properties.fade.curve; }
    void setFadeCurve(FadeCurve curve) { m_properties.fade.curve = curve; }

    // Mute
    bool isMuted() const { return m_properties.muted; }
    void setMuted(bool muted) { m_properties.muted = muted; }

    // Split clip at timeline position, returns new clip after split point
    std::unique_ptr<Clip> split(double timelinePosition);

    // Check if timeline position falls within this clip
    bool containsTime(double timelineSec) const;

    // Convert timeline time to source time
    double timelineToSourceTime(double timelineSec) const;

    // Clone
    std::unique_ptr<Clip> clone() const;

private:
    QUuid m_id;
    QString m_mediaPath;
    ClipType m_type;

    double m_timelineStart = 0.0;   // Where clip starts on timeline
    double m_inPoint = 0.0;          // Start point in source media
    double m_outPoint = 0.0;         // End point in source media
    double m_mediaDuration = 0.0;    // Total source media duration

    ClipProperties m_properties;
};

using ClipPtr = std::shared_ptr<Clip>;
using ClipWeakPtr = std::weak_ptr<Clip>;

} // namespace ClipTune
