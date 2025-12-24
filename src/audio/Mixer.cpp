#include "Mixer.h"
#include "media/Demuxer.h"
#include "media/AudioDecoder.h"
#include "media/Resampler.h"
#include <algorithm>
#include <cstring>

namespace ClipTune {

Mixer::Mixer() = default;

Mixer::~Mixer() = default;

void Mixer::setProject(Project* project)
{
    m_project = project;
    clearCache();
}

size_t Mixer::mix(double startTime, float* buffer, size_t numFrames)
{
    if (!m_project || !buffer || numFrames == 0) {
        return 0;
    }

    // Clear output buffer
    std::memset(buffer, 0, numFrames * m_channels * sizeof(float));

    double endTime = startTime + static_cast<double>(numFrames) / m_sampleRate;

    // Get all audio tracks
    auto audioTracks = m_project->audioTracks();

    // Check for solo tracks
    bool hasSolo = std::any_of(audioTracks.begin(), audioTracks.end(),
                               [](const TrackPtr& t) { return t->isSolo(); });

    for (const auto& track : audioTracks) {
        // Skip muted tracks
        if (track->isMuted()) continue;

        // If any track is solo, only process solo tracks
        if (hasSolo && !track->isSolo()) continue;

        // Get clips that overlap this time range
        auto clips = track->clipsInRange(startTime, endTime);

        for (const auto& clip : clips) {
            if (clip->isMuted()) continue;
            if (clip->type() != ClipType::Audio && clip->type() != ClipType::AudioVideo) continue;

            mixClip(*clip, startTime, buffer, numFrames);
        }
    }

    return numFrames;
}

std::vector<float> Mixer::mix(double startTime, size_t numFrames)
{
    std::vector<float> buffer(numFrames * m_channels);
    mix(startTime, buffer.data(), numFrames);
    return buffer;
}

void Mixer::mixClip(const Clip& clip, double startTime, float* buffer, size_t numFrames)
{
    // Calculate overlap between buffer time range and clip time range
    double bufferEnd = startTime + static_cast<double>(numFrames) / m_sampleRate;
    double clipStart = clip.timelineStart();
    double clipEnd = clip.timelineEnd();

    // Calculate actual overlap
    double overlapStart = std::max(startTime, clipStart);
    double overlapEnd = std::min(bufferEnd, clipEnd);

    if (overlapStart >= overlapEnd) {
        return;  // No overlap
    }

    // Calculate buffer offset (where to start writing in output buffer)
    size_t bufferOffset = 0;
    if (clipStart > startTime) {
        bufferOffset = static_cast<size_t>((clipStart - startTime) * m_sampleRate) * m_channels;
    }

    // Calculate source time (where to read from in clip)
    double sourceTime = clip.timelineToSourceTime(overlapStart);

    // Calculate number of frames to process
    size_t framesToProcess = static_cast<size_t>((overlapEnd - overlapStart) * m_sampleRate);

    // Ensure scratch buffer is large enough
    size_t samplesNeeded = framesToProcess * m_channels;
    if (m_scratchBuffer.size() < samplesNeeded) {
        m_scratchBuffer.resize(samplesNeeded);
    }

    // Read audio samples from clip
    auto samples = readClipSamples(clip, sourceTime, framesToProcess);

    if (samples.empty()) {
        return;
    }

    // Apply gain and fade
    double clipTimeOffset = overlapStart - clipStart;  // Time from clip start
    FadeDSP::applyGainAndFade(samples.data(), samples.size() / m_channels,
                              static_cast<float>(clip.gain()),
                              clipTimeOffset, clip.duration(),
                              clip.fadeInSec(), clip.fadeOutSec(), clip.fadeCurve(),
                              m_sampleRate, m_channels);

    // Mix into output buffer
    size_t samplesToMix = std::min(samples.size(), (numFrames * m_channels) - bufferOffset);
    FadeDSP::mixInto(buffer + bufferOffset, samples.data(), samplesToMix, 1.0f);
}

bool Mixer::preloadClip(const Clip& clip)
{
    auto* state = getClipState(clip.id());
    if (!state) return false;

    if (state->isLoaded) return true;

    // Create demuxer
    state->demuxer = std::make_unique<Demuxer>();
    if (!state->demuxer->open(clip.mediaPath())) {
        return false;
    }

    // Check for audio stream
    if (!state->demuxer->info().hasAudio) {
        return false;
    }

    // Create decoder
    state->decoder = std::make_unique<AudioDecoder>();
    if (!state->decoder->init(*state->demuxer)) {
        return false;
    }

    // Create resampler to convert to project format
    AudioFormat srcFormat;
    srcFormat.sampleRate = state->decoder->sampleRate();
    srcFormat.channels = state->decoder->channels();
    srcFormat.sampleFormat = state->decoder->sampleFormat();
    if (auto* layout = state->decoder->channelLayout()) {
        av_channel_layout_copy(&srcFormat.channelLayout, layout);
    }

    AudioFormat dstFormat = AudioFormat::projectDefault();
    dstFormat.sampleRate = m_sampleRate;
    dstFormat.channels = m_channels;

    state->resampler = std::make_unique<Resampler>();
    if (!state->resampler->init(srcFormat, dstFormat)) {
        return false;
    }

    state->isLoaded = true;
    return true;
}

void Mixer::unloadClip(const QUuid& clipId)
{
    m_clipStates.erase(clipId);
}

void Mixer::clearCache()
{
    m_clipStates.clear();
}

bool Mixer::isClipLoaded(const QUuid& clipId) const
{
    auto it = m_clipStates.find(clipId);
    return it != m_clipStates.end() && it->second->isLoaded;
}

void Mixer::seek(double /*time*/)
{
    // For now, just flush decoders
    for (auto& [id, state] : m_clipStates) {
        if (state->decoder) {
            state->decoder->flush();
        }
        state->decodedSamples.clear();
        state->currentPosition = 0.0;
    }
}

ClipAudioState* Mixer::getClipState(const QUuid& clipId)
{
    auto it = m_clipStates.find(clipId);
    if (it == m_clipStates.end()) {
        auto state = std::make_unique<ClipAudioState>();
        auto* ptr = state.get();
        m_clipStates[clipId] = std::move(state);
        return ptr;
    }
    return it->second.get();
}

std::vector<float> Mixer::readClipSamples(const Clip& clip, double sourceTime, size_t numFrames)
{
    // Ensure clip is loaded
    if (!isClipLoaded(clip.id())) {
        if (!preloadClip(clip)) {
            return {};
        }
    }

    auto* state = getClipState(clip.id());
    if (!state || !state->isLoaded) {
        return {};
    }

    std::vector<float> result;
    result.reserve(numFrames * m_channels);

    // Seek if needed (simple approach: re-seek and decode)
    if (std::abs(state->currentPosition - sourceTime) > 0.1) {
        state->demuxer->seekAudio(sourceTime);
        state->decoder->flush();
        state->decodedSamples.clear();
        state->currentPosition = sourceTime;
    }

    // Decode until we have enough samples
    size_t samplesNeeded = numFrames * m_channels;

    while (result.size() < samplesNeeded) {
        // Try to get samples from cached decoded samples first
        if (!state->decodedSamples.empty()) {
            size_t toCopy = std::min(state->decodedSamples.size(), samplesNeeded - result.size());
            result.insert(result.end(),
                         state->decodedSamples.begin(),
                         state->decodedSamples.begin() + toCopy);
            state->decodedSamples.erase(state->decodedSamples.begin(),
                                         state->decodedSamples.begin() + toCopy);
            state->currentPosition += static_cast<double>(toCopy / m_channels) / m_sampleRate;
        }

        if (result.size() >= samplesNeeded) {
            break;
        }

        // Read and decode more packets
        auto pktOpt = state->demuxer->readAudioPacket();
        if (!pktOpt) {
            break;  // EOF
        }

        auto frames = state->decoder->decodePacket(pktOpt->get());
        for (auto& frame : frames) {
            auto resampled = state->resampler->resample(frame.get());
            state->decodedSamples.insert(state->decodedSamples.end(),
                                          resampled.begin(), resampled.end());
        }
    }

    return result;
}

} // namespace ClipTune
