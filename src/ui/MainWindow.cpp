#include "MainWindow.h"
#include "core/Commands.h"
#include <QMenuBar>
#include <QToolBar>
#include <QStatusBar>
#include <QSplitter>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QFileDialog>
#include <QMessageBox>
#include <QCloseEvent>
#include <QKeyEvent>
#include <QLabel>

namespace ClipTune {

MainWindow::MainWindow(QWidget* parent)
    : QMainWindow(parent)
{
    setWindowTitle("ClipTune");
    resize(1400, 900);

    setupUi();
    setupMenus();
    setupToolbar();
    setupStatusBar();

    createDefaultProject();

    // Playback timer for UI updates
    m_playbackTimer = new QTimer(this);
    connect(m_playbackTimer, &QTimer::timeout, [this]() {
        if (m_audioEngine && m_audioEngine->isPlaying()) {
            onTimeChanged(m_audioEngine->currentTime());
        }
    });
}

MainWindow::~MainWindow()
{
    delete m_audioEngine;
    delete m_project;
}

void MainWindow::setupUi()
{
    auto* centralWidget = new QWidget(this);
    setCentralWidget(centralWidget);

    auto* mainLayout = new QVBoxLayout(centralWidget);
    mainLayout->setContentsMargins(0, 0, 0, 0);
    mainLayout->setSpacing(0);

    // Top area: preview and inspector
    auto* topSplitter = new QSplitter(Qt::Horizontal);

    // Preview widget
    m_preview = new PreviewWidget();
    m_preview->setMinimumSize(400, 250);
    topSplitter->addWidget(m_preview);

    // Placeholder for inspector panel
    auto* inspectorPlaceholder = new QWidget();
    inspectorPlaceholder->setMinimumWidth(200);
    inspectorPlaceholder->setStyleSheet("background-color: #2a2a2a;");
    topSplitter->addWidget(inspectorPlaceholder);

    topSplitter->setSizes({800, 300});

    // Main splitter: top area + timeline
    auto* mainSplitter = new QSplitter(Qt::Vertical);

    mainSplitter->addWidget(topSplitter);

    // Timeline
    m_timeline = new TimelineWidget();
    m_timeline->setMinimumHeight(200);
    mainSplitter->addWidget(m_timeline);

    mainSplitter->setSizes({400, 500});

    mainLayout->addWidget(mainSplitter);

    // Connect timeline signals
    connect(m_timeline, &TimelineWidget::playheadMoved, this, &MainWindow::onPlayheadMoved);
    connect(m_timeline, &TimelineWidget::selectionChanged, this, &MainWindow::onSelectionChanged);
}

void MainWindow::setupMenus()
{
    // File menu
    auto* fileMenu = menuBar()->addMenu("&File");

    fileMenu->addAction("&New Project", QKeySequence::New, this, &MainWindow::newProject);
    fileMenu->addAction("&Open...", QKeySequence::Open, this, &MainWindow::openProject);
    fileMenu->addSeparator();
    fileMenu->addAction("&Save", QKeySequence::Save, this, &MainWindow::saveProject);
    fileMenu->addAction("Save &As...", QKeySequence::SaveAs, this, &MainWindow::saveProjectAs);
    fileMenu->addSeparator();
    fileMenu->addAction("&Import Media...", QKeySequence(Qt::CTRL | Qt::Key_I), this, &MainWindow::importMedia);
    fileMenu->addSeparator();
    fileMenu->addAction("Export &Video...", this, &MainWindow::exportVideo);
    fileMenu->addAction("Export &Audio...", this, &MainWindow::exportAudio);
    fileMenu->addSeparator();
    fileMenu->addAction("E&xit", QKeySequence::Quit, this, &QMainWindow::close);

    // Edit menu
    auto* editMenu = menuBar()->addMenu("&Edit");

    m_undoAction = editMenu->addAction("&Undo", QKeySequence::Undo, this, &MainWindow::undo);
    m_redoAction = editMenu->addAction("&Redo", QKeySequence::Redo, this, &MainWindow::redo);
    editMenu->addSeparator();
    editMenu->addAction("&Delete", QKeySequence::Delete, this, &MainWindow::deleteSelection);
    editMenu->addAction("&Split at Playhead", QKeySequence(Qt::Key_S), this, &MainWindow::splitAtPlayhead);

    // View menu
    auto* viewMenu = menuBar()->addMenu("&View");

    viewMenu->addAction("Zoom &In", QKeySequence::ZoomIn, this, &MainWindow::zoomIn);
    viewMenu->addAction("Zoom &Out", QKeySequence::ZoomOut, this, &MainWindow::zoomOut);
    viewMenu->addAction("Zoom to &Fit", QKeySequence(Qt::CTRL | Qt::Key_0), this, &MainWindow::zoomToFit);

    // Transport menu
    auto* transportMenu = menuBar()->addMenu("&Transport");

    m_playAction = transportMenu->addAction("&Play", QKeySequence(Qt::Key_Space), this, &MainWindow::togglePlayPause);
    m_stopAction = transportMenu->addAction("&Stop", QKeySequence(Qt::Key_Escape), this, &MainWindow::stop);
    transportMenu->addSeparator();
    transportMenu->addAction("Seek &Forward", QKeySequence(Qt::Key_Right), this, &MainWindow::seekForward);
    transportMenu->addAction("Seek &Backward", QKeySequence(Qt::Key_Left), this, &MainWindow::seekBackward);

    // Track menu
    auto* trackMenu = menuBar()->addMenu("Trac&k");

    trackMenu->addAction("Add &Audio Track", [this]() {
        if (m_project) {
            m_project->addTrack(TrackType::Audio);
        }
    });
    trackMenu->addAction("Add &Video Track", [this]() {
        if (m_project) {
            m_project->addTrack(TrackType::Video);
        }
    });

    // Help menu
    auto* helpMenu = menuBar()->addMenu("&Help");
    helpMenu->addAction("&About ClipTune", [this]() {
        QMessageBox::about(this, "About ClipTune",
            "ClipTune - Audio/Video Editor\n\n"
            "A simple audio and video editing application\n"
            "using C++20, Qt 6, and FFmpeg.");
    });
}

void MainWindow::setupToolbar()
{
    auto* toolbar = addToolBar("Main Toolbar");
    toolbar->setMovable(false);

    toolbar->addAction("Import", this, &MainWindow::importMedia);
    toolbar->addSeparator();
    toolbar->addAction("Play", this, &MainWindow::play);
    toolbar->addAction("Pause", this, &MainWindow::pause);
    toolbar->addAction("Stop", this, &MainWindow::stop);
    toolbar->addSeparator();
    toolbar->addAction("Zoom In", this, &MainWindow::zoomIn);
    toolbar->addAction("Zoom Out", this, &MainWindow::zoomOut);
}

void MainWindow::setupStatusBar()
{
    statusBar()->showMessage("Ready");
}

void MainWindow::createDefaultProject()
{
    m_project = new Project(this);
    m_project->addTrack(TrackType::Audio, "Audio 1");
    m_project->addTrack(TrackType::Video, "Video 1");

    m_audioEngine = new AudioEngine(this);
    m_audioEngine->setProject(m_project);

    m_timeline->setProject(m_project);

    connect(m_audioEngine, &AudioEngine::timeChanged, this, &MainWindow::onTimeChanged);
    connect(m_audioEngine, &AudioEngine::playingChanged, this, &MainWindow::updatePlaybackState);

    updateWindowTitle();
}

void MainWindow::closeEvent(QCloseEvent* event)
{
    if (maybeSave()) {
        event->accept();
    } else {
        event->ignore();
    }
}

void MainWindow::keyPressEvent(QKeyEvent* event)
{
    // Space bar for play/pause
    if (event->key() == Qt::Key_Space && !event->isAutoRepeat()) {
        togglePlayPause();
        event->accept();
        return;
    }

    QMainWindow::keyPressEvent(event);
}

void MainWindow::newProject()
{
    if (!maybeSave()) return;

    delete m_project;
    createDefaultProject();
}

void MainWindow::openProject()
{
    if (!maybeSave()) return;

    QString fileName = QFileDialog::getOpenFileName(this, "Open Project",
        QString(), "ClipTune Projects (*.ctp);;All Files (*)");

    if (fileName.isEmpty()) return;

    // TODO: Implement project loading
    QMessageBox::information(this, "Open Project", "Project loading not yet implemented.");
}

void MainWindow::saveProject()
{
    if (m_project->filePath().isEmpty()) {
        saveProjectAs();
    } else {
        // TODO: Implement project saving
        m_project->setModified(false);
        updateWindowTitle();
    }
}

void MainWindow::saveProjectAs()
{
    QString fileName = QFileDialog::getSaveFileName(this, "Save Project",
        QString(), "ClipTune Projects (*.ctp);;All Files (*)");

    if (fileName.isEmpty()) return;

    m_project->setFilePath(fileName);
    saveProject();
}

void MainWindow::importMedia()
{
    QStringList fileNames = QFileDialog::getOpenFileNames(this, "Import Media",
        QString(), "Media Files (*.mp4 *.mkv *.avi *.mov *.mp3 *.wav *.aac *.flac);;All Files (*)");

    if (fileNames.isEmpty()) return;

    for (const QString& fileName : fileNames) {
        // Determine track type based on file extension
        QString ext = QFileInfo(fileName).suffix().toLower();
        TrackType type = (ext == "mp3" || ext == "wav" || ext == "aac" || ext == "flac")
                         ? TrackType::Audio : TrackType::Video;

        // Find or create appropriate track
        auto tracks = (type == TrackType::Audio) ? m_project->audioTracks() : m_project->videoTracks();
        TrackPtr track;

        if (tracks.empty()) {
            track = m_project->addTrack(type);
        } else {
            track = tracks.front();
        }

        // Import at end of track
        double startTime = track->duration();
        auto clip = m_project->importMedia(fileName, track, startTime);

        if (clip) {
            // Probe media to get duration
            Demuxer demuxer;
            if (demuxer.open(fileName)) {
                clip->setMediaDuration(demuxer.info().duration);
                clip->setOutPoint(demuxer.info().duration);
            }

            // Preload audio
            m_audioEngine->mixer().preloadClip(*clip);
        }
    }

    m_timeline->refresh();
    statusBar()->showMessage(QString("Imported %1 file(s)").arg(fileNames.size()), 3000);
}

void MainWindow::exportVideo()
{
    QString fileName = QFileDialog::getSaveFileName(this, "Export Video",
        QString(), "MP4 Video (*.mp4);;All Files (*)");

    if (fileName.isEmpty()) return;

    // TODO: Implement video export
    QMessageBox::information(this, "Export Video", "Video export not yet implemented.");
}

void MainWindow::exportAudio()
{
    QString fileName = QFileDialog::getSaveFileName(this, "Export Audio",
        QString(), "WAV Audio (*.wav);;All Files (*)");

    if (fileName.isEmpty()) return;

    // TODO: Implement audio export
    QMessageBox::information(this, "Export Audio", "Audio export not yet implemented.");
}

void MainWindow::undo()
{
    if (m_project && m_project->undoStack().canUndo()) {
        m_project->undoStack().undo();
        m_timeline->refresh();
    }
}

void MainWindow::redo()
{
    if (m_project && m_project->undoStack().canRedo()) {
        m_project->undoStack().redo();
        m_timeline->refresh();
    }
}

void MainWindow::deleteSelection()
{
    m_timeline->deleteSelectedClip();
}

void MainWindow::splitAtPlayhead()
{
    m_timeline->splitClipAtPlayhead();
}

void MainWindow::zoomIn()
{
    m_timeline->zoomIn();
}

void MainWindow::zoomOut()
{
    m_timeline->zoomOut();
}

void MainWindow::zoomToFit()
{
    m_timeline->zoomToFit();
}

void MainWindow::play()
{
    if (m_audioEngine) {
        m_audioEngine->play();
        m_playbackTimer->start(33);  // ~30fps UI update
    }
}

void MainWindow::pause()
{
    if (m_audioEngine) {
        m_audioEngine->pause();
        m_playbackTimer->stop();
    }
}

void MainWindow::stop()
{
    if (m_audioEngine) {
        m_audioEngine->stop();
        m_playbackTimer->stop();
        m_timeline->setPlayheadTime(0);
    }
}

void MainWindow::togglePlayPause()
{
    if (m_audioEngine && m_audioEngine->isPlaying()) {
        pause();
    } else {
        play();
    }
}

void MainWindow::seekForward()
{
    double time = m_timeline->playheadTime() + 1.0;
    m_timeline->setPlayheadTime(time);
    if (m_audioEngine) {
        m_audioEngine->seek(time);
    }
}

void MainWindow::seekBackward()
{
    double time = std::max(0.0, m_timeline->playheadTime() - 1.0);
    m_timeline->setPlayheadTime(time);
    if (m_audioEngine) {
        m_audioEngine->seek(time);
    }
}

void MainWindow::onPlayheadMoved(double time)
{
    if (m_audioEngine) {
        m_audioEngine->seek(time);
    }
}

void MainWindow::onTimeChanged(double time)
{
    m_timeline->setPlayheadTime(time);

    // Update status bar with current time
    int minutes = static_cast<int>(time) / 60;
    int seconds = static_cast<int>(time) % 60;
    int frames = static_cast<int>((time - std::floor(time)) * 30);
    statusBar()->showMessage(QString("Time: %1:%2:%3")
        .arg(minutes, 2, 10, QChar('0'))
        .arg(seconds, 2, 10, QChar('0'))
        .arg(frames, 2, 10, QChar('0')));
}

void MainWindow::onSelectionChanged()
{
    // Update UI based on selection
    // For now, just update status bar
    if (m_timeline->selectedClip()) {
        QString name = QFileInfo(m_timeline->selectedClip()->mediaPath()).fileName();
        statusBar()->showMessage(QString("Selected: %1").arg(name));
    }
}

void MainWindow::updateWindowTitle()
{
    QString title = "ClipTune";
    if (m_project) {
        if (!m_project->filePath().isEmpty()) {
            title += " - " + QFileInfo(m_project->filePath()).fileName();
        } else {
            title += " - Untitled";
        }
        if (m_project->isModified()) {
            title += " *";
        }
    }
    setWindowTitle(title);
}

void MainWindow::updatePlaybackState()
{
    bool playing = m_audioEngine && m_audioEngine->isPlaying();
    m_playAction->setEnabled(!playing);
    m_pauseAction->setEnabled(playing);
}

bool MainWindow::maybeSave()
{
    if (!m_project || !m_project->isModified()) {
        return true;
    }

    QMessageBox::StandardButton ret = QMessageBox::warning(this, "ClipTune",
        "The project has been modified.\nDo you want to save your changes?",
        QMessageBox::Save | QMessageBox::Discard | QMessageBox::Cancel);

    if (ret == QMessageBox::Save) {
        saveProject();
        return !m_project->isModified();
    } else if (ret == QMessageBox::Cancel) {
        return false;
    }

    return true;
}

} // namespace ClipTune
