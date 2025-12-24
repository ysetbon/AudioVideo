#include "AudioRingBuffer.h"
#include <algorithm>
#include <cstring>

namespace ClipTune {

AudioRingBuffer::AudioRingBuffer(size_t capacitySamples)
    : m_buffer(capacitySamples)
    , m_capacity(capacitySamples)
{
}

size_t AudioRingBuffer::write(const float* data, size_t numSamples)
{
    size_t available = availableWrite();
    size_t toWrite = std::min(numSamples, available);

    if (toWrite == 0) return 0;

    size_t writePos = m_writePos.load(std::memory_order_relaxed);

    // First part: from writePos to end of buffer
    size_t firstPart = std::min(toWrite, m_capacity - writePos);
    std::memcpy(m_buffer.data() + writePos, data, firstPart * sizeof(float));

    // Second part: wrap around to beginning
    if (toWrite > firstPart) {
        size_t secondPart = toWrite - firstPart;
        std::memcpy(m_buffer.data(), data + firstPart, secondPart * sizeof(float));
    }

    // Update write position
    size_t newWritePos = (writePos + toWrite) % m_capacity;
    m_writePos.store(newWritePos, std::memory_order_release);

    return toWrite;
}

size_t AudioRingBuffer::read(float* data, size_t numSamples)
{
    size_t available = availableRead();
    size_t toRead = std::min(numSamples, available);

    if (toRead == 0) return 0;

    size_t readPos = m_readPos.load(std::memory_order_relaxed);

    // First part: from readPos to end of buffer
    size_t firstPart = std::min(toRead, m_capacity - readPos);
    std::memcpy(data, m_buffer.data() + readPos, firstPart * sizeof(float));

    // Second part: wrap around to beginning
    if (toRead > firstPart) {
        size_t secondPart = toRead - firstPart;
        std::memcpy(data + firstPart, m_buffer.data(), secondPart * sizeof(float));
    }

    // Update read position
    size_t newReadPos = (readPos + toRead) % m_capacity;
    m_readPos.store(newReadPos, std::memory_order_release);

    return toRead;
}

size_t AudioRingBuffer::availableRead() const
{
    size_t writePos = m_writePos.load(std::memory_order_acquire);
    size_t readPos = m_readPos.load(std::memory_order_acquire);

    if (writePos >= readPos) {
        return writePos - readPos;
    } else {
        return m_capacity - readPos + writePos;
    }
}

size_t AudioRingBuffer::availableWrite() const
{
    // Leave one slot empty to distinguish full from empty
    return m_capacity - availableRead() - 1;
}

void AudioRingBuffer::clear()
{
    m_readPos.store(0, std::memory_order_relaxed);
    m_writePos.store(0, std::memory_order_relaxed);
}

// ThreadSafeAudioRingBuffer

ThreadSafeAudioRingBuffer::ThreadSafeAudioRingBuffer(size_t capacitySamples)
    : m_buffer(capacitySamples)
{
}

size_t ThreadSafeAudioRingBuffer::write(const float* data, size_t numSamples)
{
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_buffer.write(data, numSamples);
}

size_t ThreadSafeAudioRingBuffer::read(float* data, size_t numSamples)
{
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_buffer.read(data, numSamples);
}

size_t ThreadSafeAudioRingBuffer::availableRead() const
{
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_buffer.availableRead();
}

size_t ThreadSafeAudioRingBuffer::availableWrite() const
{
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_buffer.availableWrite();
}

void ThreadSafeAudioRingBuffer::clear()
{
    std::lock_guard<std::mutex> lock(m_mutex);
    m_buffer.clear();
}

} // namespace ClipTune
