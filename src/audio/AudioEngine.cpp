#include "AudioEngine.h"
#include "core/Project.h"
#include <QAudioDevice>
#include <QMediaDevices>
#include <cstring>

namespace ClipTune {

// AudioOutputDevice implementation

AudioOutputDevice::AudioOutputDevice(ThreadSafeAudioRingBuffer* buffer, QObject* parent)
    : QIODevice(parent)
    , m_buffer(buffer)
{
    open(QIODevice::ReadOnly);
}

qint64 AudioOutputDevice::readData(char* data, qint64 maxSize)
{
    if (!m_buffer || maxSize <= 0) {
        return 0;
    }

    size_t samplesToRead = maxSize / sizeof(float);
    size_t samplesRead = m_buffer->read(reinterpret_cast<float*>(data), samplesToRead);

    // If we didn't get enough data, pad with silence
    if (samplesRead < samplesToRead) {
        std::memset(data + samplesRead * sizeof(float), 0,
                   (samplesToRead - samplesRead) * sizeof(float));
    }

    return maxSize;  // Always return requested amount (with silence padding if needed)
}

qint64 AudioOutputDevice::writeData(const char* /*data*/, qint64 /*maxSize*/)
{
    return -1;  // Write not supported
}

qint64 AudioOutputDevice::bytesAvailable() const
{
    return static_cast<qint64>(m_buffer->availableRead() * sizeof(float)) + QIODevice::bytesAvailable();
}

// AudioEngine implementation

AudioEngine::AudioEngine(QObject* parent)
    : QObject(parent)
    , m_ringBuffer(m_sampleRate * m_channels * 2)  // 2 seconds buffer
{
}

AudioEngine::~AudioEngine()
{
    stop();
    shutdownAudio();
}

void AudioEngine::setProject(Project* project)
{
    bool wasPlaying = m_playing;
    if (wasPlaying) {
        stop();
    }

    m_project = project;
    m_mixer.setProject(project);

    if (project) {
        m_mixer.setSampleRate(project->settings().sampleRate);
        m_mixer.setChannels(2);
        m_sampleRate = project->settings().sampleRate;
    }

    initAudio();
}

void AudioEngine::play()
{
    if (!m_project || m_playing) return;

    m_playing = true;
    startMixerThread();

    if (m_audioSink) {
        m_audioSink->resume();
    }

    emit playingChanged(true);
}

void AudioEngine::pause()
{
    if (!m_playing) return;

    m_playing = false;
    stopMixerThread();

    if (m_audioSink) {
        m_audioSink->suspend();
    }

    emit playingChanged(false);
}

void AudioEngine::stop()
{
    m_playing = false;
    stopMixerThread();

    m_currentTime = 0.0;
    m_ringBuffer.clear();
    m_mixer.seek(0.0);

    if (m_audioSink) {
        m_audioSink->stop();
    }

    emit playingChanged(false);
    emit timeChanged(0.0);
}

void AudioEngine::seek(double time)
{
    bool wasPlaying = m_playing;
    if (wasPlaying) {
        m_playing = false;
        stopMixerThread();
    }

    m_currentTime = std::max(0.0, time);
    m_ringBuffer.clear();
    m_mixer.seek(m_currentTime);

    emit timeChanged(m_currentTime);

    if (wasPlaying) {
        m_playing = true;
        startMixerThread();
    }
}

double AudioEngine::projectDuration() const
{
    return m_project ? m_project->duration() : 0.0;
}

void AudioEngine::setMasterVolume(float volume)
{
    m_masterVolume = std::clamp(volume, 0.0f, 2.0f);
    if (m_audioSink) {
        m_audioSink->setVolume(m_masterVolume);
    }
}

void AudioEngine::onAudioStateChanged(QAudio::State state)
{
    if (state == QAudio::IdleState && m_playing) {
        // Buffer underrun or end of playback
        if (m_currentTime >= projectDuration()) {
            stop();
        }
    } else if (state == QAudio::StoppedState) {
        if (m_audioSink && m_audioSink->error() != QAudio::NoError) {
            emit stateError(QStringLiteral("Audio error: %1").arg(static_cast<int>(m_audioSink->error())));
        }
    }
}

void AudioEngine::initAudio()
{
    shutdownAudio();

    // Set up audio format
    QAudioFormat format;
    format.setSampleRate(m_sampleRate);
    format.setChannelCount(m_channels);
    format.setSampleFormat(QAudioFormat::Float);

    // Get default audio output device
    QAudioDevice device = QMediaDevices::defaultAudioOutput();

    if (!device.isFormatSupported(format)) {
        // Try to find a supported format
        format = device.preferredFormat();
        m_sampleRate = format.sampleRate();
        m_channels = format.channelCount();
        m_mixer.setSampleRate(m_sampleRate);
        m_mixer.setChannels(m_channels);
    }

    // Create audio sink
    m_audioSink = std::make_unique<QAudioSink>(device, format, this);
    m_audioSink->setVolume(m_masterVolume);

    connect(m_audioSink.get(), &QAudioSink::stateChanged,
            this, &AudioEngine::onAudioStateChanged);

    // Create output device
    m_outputDevice = std::make_unique<AudioOutputDevice>(&m_ringBuffer, this);

    // Start audio output
    m_audioSink->start(m_outputDevice.get());
    m_audioSink->suspend();  // Start paused
}

void AudioEngine::shutdownAudio()
{
    stopMixerThread();

    if (m_audioSink) {
        m_audioSink->stop();
        m_audioSink.reset();
    }
    m_outputDevice.reset();
}

void AudioEngine::startMixerThread()
{
    if (m_mixerRunning) return;

    m_mixerRunning = true;
    m_mixerThread = std::thread(&AudioEngine::mixerThreadFunc, this);
}

void AudioEngine::stopMixerThread()
{
    m_mixerRunning = false;
    if (m_mixerThread.joinable()) {
        m_mixerThread.join();
    }
}

void AudioEngine::mixerThreadFunc()
{
    constexpr size_t framesPerBlock = 1024;
    std::vector<float> mixBuffer(framesPerBlock * m_channels);

    while (m_mixerRunning && m_playing) {
        // Check if buffer needs more data
        size_t available = m_ringBuffer.availableWrite();
        if (available < framesPerBlock * m_channels) {
            // Buffer is full enough, sleep a bit
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
            continue;
        }

        // Check if we've reached the end
        double currentTime = m_currentTime.load();
        double duration = projectDuration();
        if (currentTime >= duration) {
            // End of project
            m_playing = false;
            break;
        }

        // Mix audio
        size_t framesMixed = m_mixer.mix(currentTime, mixBuffer.data(), framesPerBlock);

        if (framesMixed > 0) {
            // Apply master volume
            for (size_t i = 0; i < framesMixed * m_channels; ++i) {
                mixBuffer[i] *= m_masterVolume;
            }

            // Write to ring buffer
            m_ringBuffer.write(mixBuffer.data(), framesMixed * m_channels);

            // Update time
            m_currentTime = currentTime + static_cast<double>(framesMixed) / m_sampleRate;
        }
    }
}

} // namespace ClipTune
