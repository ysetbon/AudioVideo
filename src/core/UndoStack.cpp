#include "UndoStack.h"

namespace ClipTune {

UndoStack::UndoStack(QObject* parent)
    : QObject(parent)
{
}

void UndoStack::push(CommandPtr command)
{
    if (!command) return;

    // Remove any commands after current index
    if (m_index < static_cast<int>(m_commands.size())) {
        m_commands.erase(m_commands.begin() + m_index, m_commands.end());
    }

    // Try to merge with previous command
    if (!m_commands.empty() && command->id() >= 0) {
        auto& last = m_commands.back();
        if (last->id() == command->id() && last->mergeWith(command.get())) {
            // Command was merged, don't add new one
            emit indexChanged(m_index);
            return;
        }
    }

    // Execute and add command
    command->execute();
    m_commands.push_back(std::move(command));
    m_index = static_cast<int>(m_commands.size());

    trimToLimit();

    emit canUndoChanged(canUndo());
    emit canRedoChanged(canRedo());
    emit undoTextChanged(undoText());
    emit redoTextChanged(redoText());
    emit indexChanged(m_index);

    if (m_cleanIndex > m_index) {
        m_cleanIndex = -1;  // Clean state is no longer reachable
    }
    emit cleanChanged(isClean());
}

void UndoStack::undo()
{
    if (!canUndo()) return;

    --m_index;
    m_commands[m_index]->undo();

    emit canUndoChanged(canUndo());
    emit canRedoChanged(canRedo());
    emit undoTextChanged(undoText());
    emit redoTextChanged(redoText());
    emit indexChanged(m_index);
    emit cleanChanged(isClean());
}

void UndoStack::redo()
{
    if (!canRedo()) return;

    m_commands[m_index]->execute();
    ++m_index;

    emit canUndoChanged(canUndo());
    emit canRedoChanged(canRedo());
    emit undoTextChanged(undoText());
    emit redoTextChanged(redoText());
    emit indexChanged(m_index);
    emit cleanChanged(isClean());
}

bool UndoStack::canUndo() const
{
    return m_index > 0;
}

bool UndoStack::canRedo() const
{
    return m_index < static_cast<int>(m_commands.size());
}

QString UndoStack::undoText() const
{
    if (canUndo()) {
        return m_commands[m_index - 1]->description();
    }
    return QString();
}

QString UndoStack::redoText() const
{
    if (canRedo()) {
        return m_commands[m_index]->description();
    }
    return QString();
}

void UndoStack::setClean()
{
    m_cleanIndex = m_index;
    emit cleanChanged(true);
}

bool UndoStack::isClean() const
{
    return m_cleanIndex == m_index;
}

void UndoStack::clear()
{
    m_commands.clear();
    m_index = 0;
    m_cleanIndex = 0;

    emit canUndoChanged(false);
    emit canRedoChanged(false);
    emit undoTextChanged(QString());
    emit redoTextChanged(QString());
    emit indexChanged(0);
    emit cleanChanged(true);
}

void UndoStack::trimToLimit()
{
    if (m_undoLimit <= 0) return;

    while (static_cast<int>(m_commands.size()) > m_undoLimit) {
        m_commands.erase(m_commands.begin());
        --m_index;
        if (m_cleanIndex > 0) {
            --m_cleanIndex;
        } else {
            m_cleanIndex = -1;
        }
    }
}

// LambdaCommand implementation
LambdaCommand::LambdaCommand(QString description,
                             std::function<void()> doFunc,
                             std::function<void()> undoFunc)
    : m_description(std::move(description))
    , m_doFunc(std::move(doFunc))
    , m_undoFunc(std::move(undoFunc))
{
}

void LambdaCommand::execute()
{
    if (m_doFunc) m_doFunc();
}

void LambdaCommand::undo()
{
    if (m_undoFunc) m_undoFunc();
}

} // namespace ClipTune
