#pragma once

#include "Track.h"
#include "UndoStack.h"
#include <QString>
#include <QObject>
#include <vector>
#include <memory>

namespace ClipTune {

struct ProjectSettings {
    int sampleRate = 48000;
    int channels = 2;
    int videoWidth = 1920;
    int videoHeight = 1080;
    double frameRate = 30.0;
};

class Project : public QObject {
    Q_OBJECT

public:
    explicit Project(QObject* parent = nullptr);
    ~Project() override = default;

    // File operations
    QString filePath() const { return m_filePath; }
    void setFilePath(const QString& path) { m_filePath = path; }
    bool isModified() const { return m_modified; }
    void setModified(bool modified);

    // Project settings
    ProjectSettings& settings() { return m_settings; }
    const ProjectSettings& settings() const { return m_settings; }

    // Track management
    const std::vector<TrackPtr>& tracks() const { return m_tracks; }
    TrackPtr addTrack(TrackType type, const QString& name = QString());
    void removeTrack(const QUuid& trackId);
    void moveTrack(int fromIndex, int toIndex);
    TrackPtr findTrack(const QUuid& trackId) const;
    TrackPtr trackAt(int index) const;
    int trackIndex(const QUuid& trackId) const;
    int trackCount() const { return static_cast<int>(m_tracks.size()); }

    // Audio tracks
    std::vector<TrackPtr> audioTracks() const;
    int audioTrackCount() const;

    // Video tracks
    std::vector<TrackPtr> videoTracks() const;
    int videoTrackCount() const;

    // Find clip across all tracks
    ClipPtr findClip(const QUuid& clipId) const;
    TrackPtr trackForClip(const QUuid& clipId) const;

    // Project duration (end of last clip across all tracks)
    double duration() const;

    // Undo/Redo
    UndoStack& undoStack() { return m_undoStack; }
    const UndoStack& undoStack() const { return m_undoStack; }

    // Clear project
    void clear();

    // Import media file, returns created clip
    ClipPtr importMedia(const QString& filePath, TrackPtr targetTrack, double timelineStart = 0.0);

signals:
    void modifiedChanged(bool modified);
    void trackAdded(TrackPtr track);
    void trackRemoved(const QUuid& trackId);
    void trackMoved(int fromIndex, int toIndex);
    void clipAdded(ClipPtr clip, TrackPtr track);
    void clipRemoved(const QUuid& clipId, const QUuid& trackId);
    void clipModified(ClipPtr clip);
    void projectCleared();
    void durationChanged(double newDuration);

private:
    QString m_filePath;
    bool m_modified = false;
    ProjectSettings m_settings;
    std::vector<TrackPtr> m_tracks;
    UndoStack m_undoStack;
};

} // namespace ClipTune
