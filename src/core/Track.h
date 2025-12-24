#pragma once

#include "Clip.h"
#include <QString>
#include <QUuid>
#include <vector>
#include <memory>
#include <optional>

namespace ClipTune {

enum class TrackType {
    Audio,
    Video
};

class Track {
public:
    explicit Track(TrackType type, const QString& name = QString());
    Track(const Track& other);
    Track& operator=(const Track& other);
    ~Track() = default;

    // Identity
    QUuid id() const { return m_id; }
    QString name() const { return m_name; }
    void setName(const QString& name) { m_name = name; }
    TrackType type() const { return m_type; }

    // Track properties
    double volume() const { return m_volume; }
    void setVolume(double vol) { m_volume = vol; }
    double pan() const { return m_pan; }
    void setPan(double pan) { m_pan = pan; }
    bool isMuted() const { return m_muted; }
    void setMuted(bool muted) { m_muted = muted; }
    bool isSolo() const { return m_solo; }
    void setSolo(bool solo) { m_solo = solo; }

    // Height in UI (pixels)
    int height() const { return m_height; }
    void setHeight(int h) { m_height = h; }

    // Clip management
    const std::vector<ClipPtr>& clips() const { return m_clips; }
    void addClip(ClipPtr clip);
    void removeClip(const QUuid& clipId);
    ClipPtr findClip(const QUuid& clipId) const;
    ClipPtr clipAt(double timelineSec) const;
    std::vector<ClipPtr> clipsInRange(double startSec, double endSec) const;

    // Insert clip at timeline position
    void insertClip(ClipPtr clip, double timelineStart);

    // Move clip to new position
    void moveClip(const QUuid& clipId, double newTimelineStart);

    // Split clip at position
    ClipPtr splitClipAt(const QUuid& clipId, double timelinePosition);

    // Get track duration (end of last clip)
    double duration() const;

    // Sort clips by timeline position
    void sortClips();

    // Clone
    std::unique_ptr<Track> clone() const;

private:
    QUuid m_id;
    QString m_name;
    TrackType m_type;

    double m_volume = 1.0;  // 0.0 to N
    double m_pan = 0.0;     // -1.0 (left) to 1.0 (right)
    bool m_muted = false;
    bool m_solo = false;
    int m_height = 80;      // Default track height in pixels

    std::vector<ClipPtr> m_clips;
};

using TrackPtr = std::shared_ptr<Track>;
using TrackWeakPtr = std::weak_ptr<Track>;

} // namespace ClipTune
