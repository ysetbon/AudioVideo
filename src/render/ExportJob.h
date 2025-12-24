#pragma once

#include "Mp4Muxer.h"
#include "core/Project.h"
#include "audio/Mixer.h"
#include <QObject>
#include <QThread>
#include <atomic>

namespace ClipTune {

struct ExportSettings {
    QString outputPath;

    // Video settings
    bool includeVideo = true;
    VideoEncoderSettings videoSettings;

    // Audio settings
    bool includeAudio = true;
    AudioEncoderSettings audioSettings;

    // Range
    double startTime = 0.0;
    double endTime = -1.0;  // -1 = project duration
};

class ExportJob : public QObject {
    Q_OBJECT

public:
    explicit ExportJob(Project* project, const ExportSettings& settings, QObject* parent = nullptr);
    ~ExportJob() override;

    // Start export (runs in background thread)
    void start();

    // Cancel export
    void cancel();

    // State
    bool isRunning() const { return m_running; }
    bool isCancelled() const { return m_cancelled; }
    double progress() const { return m_progress; }

signals:
    void started();
    void progressChanged(double progress);
    void finished(bool success, const QString& message);
    void error(const QString& message);

private slots:
    void doExport();

private:
    bool exportVideoAndAudio();
    bool exportVideoOnly();
    bool exportAudioOnly();

    Project* m_project;
    ExportSettings m_settings;
    Mixer m_mixer;

    QThread* m_thread = nullptr;
    std::atomic<bool> m_running{false};
    std::atomic<bool> m_cancelled{false};
    std::atomic<double> m_progress{0.0};
};

// Helper function to export WAV file
bool exportWav(Project* project, const QString& outputPath,
               double startTime = 0.0, double endTime = -1.0);

} // namespace ClipTune
