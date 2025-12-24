#pragma once

#include "core/Project.h"
#include "audio/AudioEngine.h"
#include "TimelineWidget.h"
#include "PreviewWidget.h"
#include <QMainWindow>
#include <QTimer>

namespace ClipTune {

class MainWindow : public QMainWindow {
    Q_OBJECT

public:
    explicit MainWindow(QWidget* parent = nullptr);
    ~MainWindow() override;

protected:
    void closeEvent(QCloseEvent* event) override;
    void keyPressEvent(QKeyEvent* event) override;

private slots:
    // File menu
    void newProject();
    void openProject();
    void saveProject();
    void saveProjectAs();
    void importMedia();
    void exportVideo();
    void exportAudio();

    // Edit menu
    void undo();
    void redo();
    void deleteSelection();
    void splitAtPlayhead();

    // View menu
    void zoomIn();
    void zoomOut();
    void zoomToFit();

    // Transport
    void play();
    void pause();
    void stop();
    void togglePlayPause();
    void seekForward();
    void seekBackward();

    // Timeline signals
    void onPlayheadMoved(double time);
    void onTimeChanged(double time);
    void onSelectionChanged();

private:
    void setupUi();
    void setupMenus();
    void setupToolbar();
    void setupStatusBar();
    void createDefaultProject();
    void updateWindowTitle();
    void updatePlaybackState();

    bool maybeSave();

    Project* m_project = nullptr;
    AudioEngine* m_audioEngine = nullptr;

    // UI
    TimelineWidget* m_timeline = nullptr;
    PreviewWidget* m_preview = nullptr;

    // Actions
    QAction* m_undoAction = nullptr;
    QAction* m_redoAction = nullptr;
    QAction* m_playAction = nullptr;
    QAction* m_pauseAction = nullptr;
    QAction* m_stopAction = nullptr;

    // Playback timer for UI updates
    QTimer* m_playbackTimer = nullptr;
};

} // namespace ClipTune
