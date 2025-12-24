#include "Commands.h"
#include "Project.h"

namespace ClipTune {

// AddClipCommand
AddClipCommand::AddClipCommand(Project* project, TrackPtr track, ClipPtr clip)
    : m_project(project)
    , m_track(track)
    , m_clip(clip)
{
}

void AddClipCommand::execute()
{
    m_track->addClip(m_clip);
    m_project->setModified(true);
}

void AddClipCommand::undo()
{
    m_track->removeClip(m_clip->id());
    m_project->setModified(true);
}

// RemoveClipCommand
RemoveClipCommand::RemoveClipCommand(Project* project, TrackPtr track, ClipPtr clip)
    : m_project(project)
    , m_track(track)
    , m_clip(clip)
{
}

void RemoveClipCommand::execute()
{
    m_track->removeClip(m_clip->id());
    m_project->setModified(true);
}

void RemoveClipCommand::undo()
{
    m_track->addClip(m_clip);
    m_project->setModified(true);
}

// MoveClipCommand
MoveClipCommand::MoveClipCommand(ClipPtr clip, double oldStart, double newStart)
    : m_clip(clip)
    , m_oldStart(oldStart)
    , m_newStart(newStart)
{
}

void MoveClipCommand::execute()
{
    m_clip->setTimelineStart(m_newStart);
}

void MoveClipCommand::undo()
{
    m_clip->setTimelineStart(m_oldStart);
}

bool MoveClipCommand::mergeWith(const Command* other)
{
    auto* moveCmd = dynamic_cast<const MoveClipCommand*>(other);
    if (!moveCmd || moveCmd->m_clip != m_clip) {
        return false;
    }
    m_newStart = moveCmd->m_newStart;
    return true;
}

// TrimClipCommand
TrimClipCommand::TrimClipCommand(ClipPtr clip,
                                 double oldIn, double oldOut, double oldTimelineStart,
                                 double newIn, double newOut, double newTimelineStart)
    : m_clip(clip)
    , m_oldIn(oldIn), m_oldOut(oldOut), m_oldTimelineStart(oldTimelineStart)
    , m_newIn(newIn), m_newOut(newOut), m_newTimelineStart(newTimelineStart)
{
}

void TrimClipCommand::execute()
{
    m_clip->setInPoint(m_newIn);
    m_clip->setOutPoint(m_newOut);
    m_clip->setTimelineStart(m_newTimelineStart);
}

void TrimClipCommand::undo()
{
    m_clip->setInPoint(m_oldIn);
    m_clip->setOutPoint(m_oldOut);
    m_clip->setTimelineStart(m_oldTimelineStart);
}

bool TrimClipCommand::mergeWith(const Command* other)
{
    auto* trimCmd = dynamic_cast<const TrimClipCommand*>(other);
    if (!trimCmd || trimCmd->m_clip != m_clip) {
        return false;
    }
    m_newIn = trimCmd->m_newIn;
    m_newOut = trimCmd->m_newOut;
    m_newTimelineStart = trimCmd->m_newTimelineStart;
    return true;
}

// SplitClipCommand
SplitClipCommand::SplitClipCommand(Project* project, TrackPtr track, ClipPtr originalClip, double splitPosition)
    : m_project(project)
    , m_track(track)
    , m_originalClip(originalClip)
    , m_splitPosition(splitPosition)
    , m_originalOutPoint(originalClip->outPoint())
{
}

void SplitClipCommand::execute()
{
    m_newClip = m_track->splitClipAt(m_originalClip->id(), m_splitPosition);
    m_project->setModified(true);
}

void SplitClipCommand::undo()
{
    if (m_newClip) {
        m_track->removeClip(m_newClip->id());
        m_originalClip->setOutPoint(m_originalOutPoint);
        m_project->setModified(true);
    }
}

// ChangeGainCommand
ChangeGainCommand::ChangeGainCommand(ClipPtr clip, double oldGain, double newGain)
    : m_clip(clip)
    , m_oldGain(oldGain)
    , m_newGain(newGain)
{
}

void ChangeGainCommand::execute()
{
    m_clip->setGain(m_newGain);
}

void ChangeGainCommand::undo()
{
    m_clip->setGain(m_oldGain);
}

bool ChangeGainCommand::mergeWith(const Command* other)
{
    auto* gainCmd = dynamic_cast<const ChangeGainCommand*>(other);
    if (!gainCmd || gainCmd->m_clip != m_clip) {
        return false;
    }
    m_newGain = gainCmd->m_newGain;
    return true;
}

// ChangeFadeCommand
ChangeFadeCommand::ChangeFadeCommand(ClipPtr clip, FadeSettings oldFade, FadeSettings newFade)
    : m_clip(clip)
    , m_oldFade(oldFade)
    , m_newFade(newFade)
{
}

void ChangeFadeCommand::execute()
{
    m_clip->properties().fade = m_newFade;
}

void ChangeFadeCommand::undo()
{
    m_clip->properties().fade = m_oldFade;
}

bool ChangeFadeCommand::mergeWith(const Command* other)
{
    auto* fadeCmd = dynamic_cast<const ChangeFadeCommand*>(other);
    if (!fadeCmd || fadeCmd->m_clip != m_clip) {
        return false;
    }
    m_newFade = fadeCmd->m_newFade;
    return true;
}

// AddTrackCommand
AddTrackCommand::AddTrackCommand(Project* project, TrackType type, const QString& name)
    : m_project(project)
    , m_type(type)
    , m_name(name)
{
}

void AddTrackCommand::execute()
{
    m_track = m_project->addTrack(m_type, m_name);
}

void AddTrackCommand::undo()
{
    if (m_track) {
        m_project->removeTrack(m_track->id());
    }
}

// RemoveTrackCommand
RemoveTrackCommand::RemoveTrackCommand(Project* project, TrackPtr track, int index)
    : m_project(project)
    , m_track(track)
    , m_index(index)
{
}

void RemoveTrackCommand::execute()
{
    m_project->removeTrack(m_track->id());
}

void RemoveTrackCommand::undo()
{
    // Re-add track at original position
    // Note: This is simplified; a full implementation would restore exact position
    m_project->addTrack(m_track->type(), m_track->name());
}

} // namespace ClipTune
