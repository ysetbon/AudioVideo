#pragma once

#include "UndoStack.h"
#include "Clip.h"
#include "Track.h"
#include <QUuid>

namespace ClipTune {

class Project;

// Add clip to track
class AddClipCommand : public Command {
public:
    AddClipCommand(Project* project, TrackPtr track, ClipPtr clip);
    void execute() override;
    void undo() override;
    QString description() const override { return QStringLiteral("Add Clip"); }

private:
    Project* m_project;
    TrackPtr m_track;
    ClipPtr m_clip;
};

// Remove clip from track
class RemoveClipCommand : public Command {
public:
    RemoveClipCommand(Project* project, TrackPtr track, ClipPtr clip);
    void execute() override;
    void undo() override;
    QString description() const override { return QStringLiteral("Remove Clip"); }

private:
    Project* m_project;
    TrackPtr m_track;
    ClipPtr m_clip;
};

// Move clip on timeline
class MoveClipCommand : public Command {
public:
    MoveClipCommand(ClipPtr clip, double oldStart, double newStart);
    void execute() override;
    void undo() override;
    QString description() const override { return QStringLiteral("Move Clip"); }
    int id() const override { return 1; }
    bool mergeWith(const Command* other) override;

private:
    ClipPtr m_clip;
    double m_oldStart;
    double m_newStart;
};

// Trim clip (change in/out points)
class TrimClipCommand : public Command {
public:
    TrimClipCommand(ClipPtr clip,
                    double oldIn, double oldOut, double oldTimelineStart,
                    double newIn, double newOut, double newTimelineStart);
    void execute() override;
    void undo() override;
    QString description() const override { return QStringLiteral("Trim Clip"); }
    int id() const override { return 2; }
    bool mergeWith(const Command* other) override;

private:
    ClipPtr m_clip;
    double m_oldIn, m_oldOut, m_oldTimelineStart;
    double m_newIn, m_newOut, m_newTimelineStart;
};

// Split clip
class SplitClipCommand : public Command {
public:
    SplitClipCommand(Project* project, TrackPtr track, ClipPtr originalClip, double splitPosition);
    void execute() override;
    void undo() override;
    QString description() const override { return QStringLiteral("Split Clip"); }

private:
    Project* m_project;
    TrackPtr m_track;
    ClipPtr m_originalClip;
    ClipPtr m_newClip;
    double m_splitPosition;
    double m_originalOutPoint;
};

// Change clip gain
class ChangeGainCommand : public Command {
public:
    ChangeGainCommand(ClipPtr clip, double oldGain, double newGain);
    void execute() override;
    void undo() override;
    QString description() const override { return QStringLiteral("Change Gain"); }
    int id() const override { return 3; }
    bool mergeWith(const Command* other) override;

private:
    ClipPtr m_clip;
    double m_oldGain;
    double m_newGain;
};

// Change fade settings
class ChangeFadeCommand : public Command {
public:
    ChangeFadeCommand(ClipPtr clip, FadeSettings oldFade, FadeSettings newFade);
    void execute() override;
    void undo() override;
    QString description() const override { return QStringLiteral("Change Fade"); }
    int id() const override { return 4; }
    bool mergeWith(const Command* other) override;

private:
    ClipPtr m_clip;
    FadeSettings m_oldFade;
    FadeSettings m_newFade;
};

// Add track
class AddTrackCommand : public Command {
public:
    AddTrackCommand(Project* project, TrackType type, const QString& name);
    void execute() override;
    void undo() override;
    QString description() const override { return QStringLiteral("Add Track"); }

private:
    Project* m_project;
    TrackType m_type;
    QString m_name;
    TrackPtr m_track;
};

// Remove track
class RemoveTrackCommand : public Command {
public:
    RemoveTrackCommand(Project* project, TrackPtr track, int index);
    void execute() override;
    void undo() override;
    QString description() const override { return QStringLiteral("Remove Track"); }

private:
    Project* m_project;
    TrackPtr m_track;
    int m_index;
};

} // namespace ClipTune
