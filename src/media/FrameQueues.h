#pragma once

#include "FfmpegInit.h"
#include <queue>
#include <mutex>
#include <condition_variable>
#include <optional>
#include <atomic>

namespace ClipTune {

// Thread-safe frame with timestamp
struct TimestampedFrame {
    AVFramePtr frame;
    double timestampSec = 0.0;
};

// Thread-safe queue for decoded frames
template<typename T>
class ThreadSafeQueue {
public:
    explicit ThreadSafeQueue(size_t maxSize = 30)
        : m_maxSize(maxSize)
    {}

    // Push item (blocks if queue is full)
    void push(T item) {
        std::unique_lock<std::mutex> lock(m_mutex);
        m_notFull.wait(lock, [this] { return m_queue.size() < m_maxSize || m_stopped; });

        if (m_stopped) return;

        m_queue.push(std::move(item));
        lock.unlock();
        m_notEmpty.notify_one();
    }

    // Try push without blocking
    bool tryPush(T item) {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (m_queue.size() >= m_maxSize) {
            return false;
        }
        m_queue.push(std::move(item));
        m_notEmpty.notify_one();
        return true;
    }

    // Pop item (blocks if queue is empty)
    std::optional<T> pop() {
        std::unique_lock<std::mutex> lock(m_mutex);
        m_notEmpty.wait(lock, [this] { return !m_queue.empty() || m_stopped; });

        if (m_stopped && m_queue.empty()) {
            return std::nullopt;
        }

        T item = std::move(m_queue.front());
        m_queue.pop();
        lock.unlock();
        m_notFull.notify_one();
        return item;
    }

    // Try pop without blocking
    std::optional<T> tryPop() {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (m_queue.empty()) {
            return std::nullopt;
        }
        T item = std::move(m_queue.front());
        m_queue.pop();
        m_notFull.notify_one();
        return item;
    }

    // Peek front item without removing
    std::optional<T> peek() const {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (m_queue.empty()) {
            return std::nullopt;
        }
        return m_queue.front();
    }

    // Clear queue
    void clear() {
        std::lock_guard<std::mutex> lock(m_mutex);
        std::queue<T> empty;
        std::swap(m_queue, empty);
        m_notFull.notify_all();
    }

    // Stop queue (unblocks all waiting threads)
    void stop() {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_stopped = true;
        m_notEmpty.notify_all();
        m_notFull.notify_all();
    }

    void start() {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_stopped = false;
    }

    bool isEmpty() const {
        std::lock_guard<std::mutex> lock(m_mutex);
        return m_queue.empty();
    }

    size_t size() const {
        std::lock_guard<std::mutex> lock(m_mutex);
        return m_queue.size();
    }

    bool isStopped() const {
        return m_stopped;
    }

private:
    mutable std::mutex m_mutex;
    std::condition_variable m_notEmpty;
    std::condition_variable m_notFull;
    std::queue<T> m_queue;
    size_t m_maxSize;
    std::atomic<bool> m_stopped{false};
};

// Specialized queues
using AudioFrameQueue = ThreadSafeQueue<TimestampedFrame>;
using VideoFrameQueue = ThreadSafeQueue<TimestampedFrame>;
using PacketQueue = ThreadSafeQueue<AVPacketPtr>;

// Audio buffer with timestamp tracking
struct AudioBuffer {
    std::vector<float> samples;  // Interleaved stereo float samples
    double startTimeSec = 0.0;
    int sampleRate = 48000;
    int channels = 2;

    double duration() const {
        return static_cast<double>(samples.size()) / (sampleRate * channels);
    }

    double endTimeSec() const {
        return startTimeSec + duration();
    }
};

using AudioBufferQueue = ThreadSafeQueue<AudioBuffer>;

} // namespace ClipTune
