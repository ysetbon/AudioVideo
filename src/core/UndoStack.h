#pragma once

#include <QString>
#include <QObject>
#include <vector>
#include <memory>
#include <functional>

namespace ClipTune {

class Command {
public:
    virtual ~Command() = default;
    virtual void execute() = 0;
    virtual void undo() = 0;
    virtual QString description() const = 0;

    // Optional: merge with previous command of same type
    virtual bool mergeWith(const Command* /*other*/) { return false; }
    virtual int id() const { return -1; }  // -1 = no merging
};

using CommandPtr = std::unique_ptr<Command>;

class UndoStack : public QObject {
    Q_OBJECT

public:
    explicit UndoStack(QObject* parent = nullptr);
    ~UndoStack() override = default;

    // Execute and push command
    void push(CommandPtr command);

    // Undo/Redo
    void undo();
    void redo();
    bool canUndo() const;
    bool canRedo() const;

    // Info
    QString undoText() const;
    QString redoText() const;
    int index() const { return m_index; }
    int count() const { return static_cast<int>(m_commands.size()); }

    // Clean state tracking
    void setClean();
    bool isClean() const;
    int cleanIndex() const { return m_cleanIndex; }

    // Clear all commands
    void clear();

    // Limit stack size
    void setUndoLimit(int limit) { m_undoLimit = limit; }
    int undoLimit() const { return m_undoLimit; }

signals:
    void canUndoChanged(bool canUndo);
    void canRedoChanged(bool canRedo);
    void undoTextChanged(const QString& text);
    void redoTextChanged(const QString& text);
    void cleanChanged(bool clean);
    void indexChanged(int index);

private:
    void trimToLimit();

    std::vector<CommandPtr> m_commands;
    int m_index = 0;        // Points to next command to execute
    int m_cleanIndex = 0;   // Index when marked clean
    int m_undoLimit = 100;
};

// Convenience command using lambdas
class LambdaCommand : public Command {
public:
    LambdaCommand(QString description,
                  std::function<void()> doFunc,
                  std::function<void()> undoFunc);

    void execute() override;
    void undo() override;
    QString description() const override { return m_description; }

private:
    QString m_description;
    std::function<void()> m_doFunc;
    std::function<void()> m_undoFunc;
};

} // namespace ClipTune
