#pragma once

#include <vector>
#include <atomic>
#include <cstddef>
#include <mutex>

namespace ClipTune {

// Lock-free single-producer single-consumer ring buffer for audio samples
class AudioRingBuffer {
public:
    explicit AudioRingBuffer(size_t capacitySamples = 48000 * 2);  // 1 second stereo

    // Write samples to buffer
    // Returns number of samples actually written
    size_t write(const float* data, size_t numSamples);

    // Read samples from buffer
    // Returns number of samples actually read
    size_t read(float* data, size_t numSamples);

    // Available samples to read
    size_t availableRead() const;

    // Available space to write
    size_t availableWrite() const;

    // Clear buffer
    void clear();

    // Capacity
    size_t capacity() const { return m_capacity; }

    // Is empty
    bool isEmpty() const { return availableRead() == 0; }

    // Is full
    bool isFull() const { return availableWrite() == 0; }

private:
    std::vector<float> m_buffer;
    size_t m_capacity;
    std::atomic<size_t> m_writePos{0};
    std::atomic<size_t> m_readPos{0};
};

// Thread-safe ring buffer with mutex (for multi-producer scenarios)
class ThreadSafeAudioRingBuffer {
public:
    explicit ThreadSafeAudioRingBuffer(size_t capacitySamples = 48000 * 2);

    size_t write(const float* data, size_t numSamples);
    size_t read(float* data, size_t numSamples);
    size_t availableRead() const;
    size_t availableWrite() const;
    void clear();
    size_t capacity() const { return m_buffer.capacity(); }

private:
    AudioRingBuffer m_buffer;
    mutable std::mutex m_mutex;
};

} // namespace ClipTune
