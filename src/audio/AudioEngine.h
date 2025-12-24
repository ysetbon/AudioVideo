#pragma once

#include "AudioRingBuffer.h"
#include "Mixer.h"
#include <QObject>
#include <QAudioSink>
#include <QAudioFormat>
#include <QIODevice>
#include <memory>
#include <atomic>
#include <thread>

namespace ClipTune {

class Project;

// Custom QIODevice for reading from ring buffer
class AudioOutputDevice : public QIODevice {
    Q_OBJECT

public:
    explicit AudioOutputDevice(ThreadSafeAudioRingBuffer* buffer, QObject* parent = nullptr);

    qint64 readData(char* data, qint64 maxSize) override;
    qint64 writeData(const char* data, qint64 maxSize) override;
    bool isSequential() const override { return true; }
    qint64 bytesAvailable() const override;

private:
    ThreadSafeAudioRingBuffer* m_buffer;
};

class AudioEngine : public QObject {
    Q_OBJECT

public:
    explicit AudioEngine(QObject* parent = nullptr);
    ~AudioEngine() override;

    // Initialize with project
    void setProject(Project* project);

    // Audio format
    int sampleRate() const { return m_sampleRate; }
    int channels() const { return m_channels; }

    // Transport controls
    void play();
    void pause();
    void stop();
    void seek(double time);

    // State
    bool isPlaying() const { return m_playing; }
    double currentTime() const { return m_currentTime; }
    double projectDuration() const;

    // Volume
    float masterVolume() const { return m_masterVolume; }
    void setMasterVolume(float volume);

    // Get mixer for preloading
    Mixer& mixer() { return m_mixer; }

signals:
    void playingChanged(bool playing);
    void timeChanged(double time);
    void stateError(const QString& error);

private slots:
    void onAudioStateChanged(QAudio::State state);

private:
    void initAudio();
    void shutdownAudio();
    void startMixerThread();
    void stopMixerThread();
    void mixerThreadFunc();

    Project* m_project = nullptr;
    Mixer m_mixer;

    // Audio output
    std::unique_ptr<QAudioSink> m_audioSink;
    std::unique_ptr<AudioOutputDevice> m_outputDevice;
    ThreadSafeAudioRingBuffer m_ringBuffer;

    // Format
    int m_sampleRate = 48000;
    int m_channels = 2;

    // Playback state
    std::atomic<bool> m_playing{false};
    std::atomic<double> m_currentTime{0.0};
    float m_masterVolume = 1.0f;

    // Mixer thread
    std::thread m_mixerThread;
    std::atomic<bool> m_mixerRunning{false};
};

} // namespace ClipTune
