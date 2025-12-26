"""Audio engine for loading and playing audio like professional DAWs."""
import sys
import os
import subprocess
import threading
from typing import Optional, Callable, Dict
import numpy as np

from .ffmpeg_utils import FFMPEG

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False
    print("Warning: sounddevice not installed. Run: pip install sounddevice")


class LoadedAudio:
    """Represents a loaded audio file with its decoded samples."""

    # Pre-compute waveform at 10 points per second
    WAVEFORM_POINTS_PER_SECOND = 10

    def __init__(self, filepath: str, samples: np.ndarray, sample_rate: int, channels: int):
        self.filepath = filepath
        self.samples = samples  # numpy array of audio samples
        self.sample_rate = sample_rate
        self.channels = channels
        self.duration = len(samples) / sample_rate
        self.name = os.path.basename(filepath)

        # Pre-compute waveform overview for fast display
        self.waveform_overview = self._compute_waveform_overview()

    def _compute_waveform_overview(self) -> list:
        """Pre-compute waveform overview (min/max pairs) for fast display."""
        # Convert to mono quickly
        if len(self.samples.shape) > 1 and self.samples.shape[1] > 1:
            mono = np.mean(self.samples, axis=1, dtype=np.float32)
        else:
            mono = self.samples.flatten()

        # Calculate number of overview points (20 per second)
        num_points = max(1, int(self.duration * self.WAVEFORM_POINTS_PER_SECOND))

        samples_per_point = max(1, len(mono) // num_points)

        # Reshape for fast numpy operations
        usable_samples = (len(mono) // samples_per_point) * samples_per_point
        if usable_samples == 0:
            return [(0.0, 0.0)]

        reshaped = mono[:usable_samples].reshape(-1, samples_per_point)
        mins = np.min(reshaped, axis=1)
        maxs = np.max(reshaped, axis=1)

        return list(zip(mins.tolist(), maxs.tolist()))

    def _resample_overview(self, overview: list, width: int) -> list:
        """Resample an overview (min/max pairs) to the requested width."""
        if not overview or width <= 0:
            return []

        overview_len = len(overview)
        if width >= overview_len:
            return overview

        result = []
        points_per_pixel = overview_len / width
        for i in range(width):
            start = int(i * points_per_pixel)
            end = int((i + 1) * points_per_pixel)
            end = min(end, overview_len)
            if start < overview_len:
                chunk = overview[start:end]
                min_val = min(p[0] for p in chunk)
                max_val = max(p[1] for p in chunk)
                result.append((min_val, max_val))
            else:
                result.append((0.0, 0.0))

        return result

    def get_waveform_for_width(self, width: int) -> list:
        """Get waveform data resampled to specified width."""
        if not self.waveform_overview or width <= 0:
            return []

        return self._resample_overview(self.waveform_overview, width)

    def get_waveform_segment_for_width(self, width: int, source_start: float, duration: float) -> list:
        """Get waveform data for a segment, resampled to the requested width."""
        if not self.waveform_overview or width <= 0 or duration <= 0 or self.duration <= 0:
            return []

        start_time = max(0.0, float(source_start))
        end_time = min(self.duration, start_time + float(duration))
        if end_time <= start_time:
            return []

        overview_len = len(self.waveform_overview)
        start_idx = int((start_time / self.duration) * overview_len)
        end_idx = int((end_time / self.duration) * overview_len)
        start_idx = max(0, min(start_idx, overview_len - 1))
        end_idx = max(start_idx + 1, min(end_idx, overview_len))

        segment = self.waveform_overview[start_idx:end_idx]
        return self._resample_overview(segment, width)

    def get_samples_at(self, start_time: float, num_samples: int) -> np.ndarray:
        """Get audio samples starting at a specific time."""
        start_sample = int(start_time * self.sample_rate)
        end_sample = start_sample + num_samples

        if start_sample >= len(self.samples):
            # Past the end, return silence
            return np.zeros((num_samples, self.channels), dtype=np.float32)

        if end_sample > len(self.samples):
            # Partial data, pad with zeros
            available = self.samples[start_sample:]
            padding = np.zeros((end_sample - len(self.samples), self.channels), dtype=np.float32)
            return np.vstack([available, padding])

        return self.samples[start_sample:end_sample]

    def get_samples_by_frame(self, start_frame: int, num_frames: int) -> np.ndarray:
        """Get audio samples by frame index (sample index), padding with silence if needed."""
        if num_frames <= 0:
            return np.zeros((0, self.channels), dtype=np.float32)

        start_frame = int(start_frame)
        end_frame = start_frame + int(num_frames)

        if start_frame >= len(self.samples):
            return np.zeros((num_frames, self.channels), dtype=np.float32)

        if end_frame <= 0:
            return np.zeros((num_frames, self.channels), dtype=np.float32)

        src_start = max(0, start_frame)
        src_end = min(len(self.samples), end_frame)
        chunk = self.samples[src_start:src_end]

        left_pad = max(0, -start_frame)
        right_pad = max(0, end_frame - len(self.samples))
        if left_pad or right_pad:
            out = np.zeros((num_frames, self.channels), dtype=np.float32)
            out[left_pad:left_pad + len(chunk)] = chunk
            return out

        return chunk


class AudioEngine:
    """Audio engine that loads and plays audio like professional DAWs."""

    DEFAULT_SAMPLE_RATE = 48000
    DEFAULT_CHANNELS = 2
    BLOCK_SIZE = 0  # Let PortAudio choose; requested via latency='low'
    LATENCY_MODE = 'low'

    def __init__(self):
        self._lock = threading.Lock()
        self.loaded_audio: Dict[str, LoadedAudio] = {}  # filepath -> LoadedAudio
        self.sample_rate = self.DEFAULT_SAMPLE_RATE
        self.channels = self.DEFAULT_CHANNELS

        # Playback state
        self.is_playing = False
        self.playback_position = 0.0  # in seconds
        self._playback_sample = 0  # current sample position
        self._ui_floor_time = 0.0  # for latency-compensated UI playhead

        # Active clips for playback
        self._active_clips = []  # list of (LoadedAudio, clip_start_time, clip_duration)

        # Audio stream
        self._stream: Optional[sd.OutputStream] = None if SOUNDDEVICE_AVAILABLE else None

        # Callback for position updates
        self.on_position_update: Optional[Callable[[float], None]] = None

        # Loading state
        self._loading_files: set = set()

    def _ensure_stream(self) -> bool:
        if not SOUNDDEVICE_AVAILABLE:
            return False

        if self._stream is not None:
            try:
                if not self._stream.active:
                    self._stream.start()
                return True
            except Exception:
                try:
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None

        try:
            self._stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=np.float32,
                blocksize=self.BLOCK_SIZE,
                latency=self.LATENCY_MODE,
                callback=self._audio_callback,
                prime_output_buffers_using_stream_callback=True,
            )
            self._stream.start()
            return True
        except Exception as e:
            print(f"Error starting audio stream: {e}")
            self._stream = None
            return False

    def get_output_latency(self) -> float:
        stream = self._stream
        if not stream:
            return 0.0
        latency = getattr(stream, 'latency', 0.0)
        try:
            if isinstance(latency, (tuple, list)):
                latency = latency[-1] if latency else 0.0
            return max(0.0, float(latency))
        except Exception:
            return 0.0

    def load_audio(self, filepath: str, callback: Optional[Callable] = None) -> Optional[LoadedAudio]:
        """Load an audio file into memory using FFmpeg. Can be async with callback."""
        if filepath in self.loaded_audio:
            if callback:
                callback(self.loaded_audio[filepath])
            return self.loaded_audio[filepath]

        if callback:
            # Async loading in background thread
            if filepath not in self._loading_files:
                self._loading_files.add(filepath)
                thread = threading.Thread(
                    target=self._load_audio_thread,
                    args=(filepath, callback),
                    daemon=True
                )
                thread.start()
            return None
        else:
            # Sync loading
            return self._load_audio_sync(filepath)

    def _load_audio_thread(self, filepath: str, callback: Callable):
        """Background thread for loading audio."""
        loaded = self._load_audio_sync(filepath)
        self._loading_files.discard(filepath)
        if callback:
            callback(loaded)

    def _load_audio_sync(self, filepath: str) -> Optional[LoadedAudio]:
        """Synchronously load audio file."""
        try:
            # Use FFmpeg to decode audio to raw PCM
            cmd = [
                FFMPEG, '-i', filepath,
                '-f', 'f32le',  # 32-bit float little-endian
                '-acodec', 'pcm_f32le',
                '-ar', str(self.sample_rate),  # Resample to our sample rate
                '-ac', str(self.channels),  # Convert to stereo
                '-'
            ]

            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                result = subprocess.run(
                    cmd, capture_output=True,
                    startupinfo=startupinfo
                )
            else:
                result = subprocess.run(cmd, capture_output=True)

            if result.returncode != 0:
                print(f"FFmpeg error: {result.stderr.decode()}")
                return None

            # Convert raw bytes to numpy array
            samples = np.frombuffer(result.stdout, dtype=np.float32)
            samples = samples.reshape(-1, self.channels)

            loaded = LoadedAudio(filepath, samples, self.sample_rate, self.channels)
            self.loaded_audio[filepath] = loaded

            print(f"Loaded: {loaded.name} ({loaded.duration:.2f}s)")
            return loaded

        except Exception as e:
            print(f"Error loading audio: {e}")
            return None

    def unload_audio(self, filepath: str):
        """Unload audio from memory."""
        if filepath in self.loaded_audio:
            del self.loaded_audio[filepath]

    @staticmethod
    def _apply_fade_curve(t: np.ndarray, curve: float) -> np.ndarray:
        """Apply curve to a 0..1 ramp. 0 is linear, positive/negative adjusts curvature."""
        try:
            curve = float(curve)
        except Exception:
            curve = 0.0

        if abs(curve) < 1e-6:
            return t

        t = t.astype(np.float32, copy=False)
        one = np.float32(1.0)
        power = np.float32(1.0 + min(8.0, abs(curve)))
        if curve > 0:
            return np.power(t, power)
        return one - np.power(one - t, power)

    def set_clips(self, clips: list):
        """Set the clips to play. Each clip should have 'path', 'start', 'duration'."""
        with self._lock:
            self._active_clips = []
            for clip in clips:
                filepath = clip.get('path')
                if not filepath or filepath not in self.loaded_audio:
                    continue

                try:
                    start = float(clip.get('start', 0.0))
                    duration = float(clip.get('duration', 0.0))
                    source_start = float(clip.get('source_start', 0.0))
                    fade_in = float(clip.get('fade_in', 0.0))
                    fade_out = float(clip.get('fade_out', 0.0))
                    fade_in_curve = float(clip.get('fade_in_curve', 0.0))
                    fade_out_curve = float(clip.get('fade_out_curve', 0.0))
                except Exception:
                    continue

                if duration <= 0:
                    continue

                start_frame = int(round(start * self.sample_rate))
                duration_frames = int(round(duration * self.sample_rate))
                if duration_frames <= 0:
                    continue

                fade_in = max(0.0, min(fade_in, duration))
                fade_out = max(0.0, min(fade_out, duration))

                self._active_clips.append({
                    'audio': self.loaded_audio[filepath],
                    'start': start,
                    'duration': duration,
                    'source_start': source_start,
                    'fade_in': fade_in,
                    'fade_out': fade_out,
                    'fade_in_curve': fade_in_curve,
                    'fade_out_curve': fade_out_curve,
                    'start_frame': start_frame,
                    'duration_frames': duration_frames,
                    'source_start_frame': int(round(source_start * self.sample_rate)),
                    'fade_in_frames': int(round(fade_in * self.sample_rate)),
                    'fade_out_frames': int(round(fade_out * self.sample_rate)),
                })

    def _audio_callback(self, outdata, frames, time_info, status):
        """Sounddevice callback - fills output buffer with mixed audio."""
        if status:
            print(f"Audio status: {status}")

        with self._lock:
            if not self.is_playing:
                outdata.fill(0)
                return

            # Mix all active clips
            mixed = np.zeros((frames, self.channels), dtype=np.float32)

            block_start = int(self._playback_sample)
            block_end = block_start + int(frames)

            for clip in self._active_clips:
                clip_start = int(clip['start_frame'])
                clip_end = clip_start + int(clip['duration_frames'])

                overlap_start = max(block_start, clip_start)
                overlap_end = min(block_end, clip_end)
                if overlap_end <= overlap_start:
                    continue

                out_offset = overlap_start - block_start
                frames_to_mix = overlap_end - overlap_start

                clip_offset = overlap_start - clip_start
                src_frame = int(clip['source_start_frame']) + clip_offset

                samples = clip['audio'].get_samples_by_frame(src_frame, frames_to_mix)

                fade_in_frames = int(clip.get('fade_in_frames', 0) or 0)
                fade_out_frames = int(clip.get('fade_out_frames', 0) or 0)
                duration_frames = int(clip.get('duration_frames', 0) or 0)
                if duration_frames > 0 and (fade_in_frames > 0 or fade_out_frames > 0):
                    positions = clip_offset + np.arange(frames_to_mix, dtype=np.float32)
                    gains = np.ones(frames_to_mix, dtype=np.float32)

                    if fade_in_frames > 0:
                        t_in = np.clip(positions / fade_in_frames, 0.0, 1.0)
                        gains = np.minimum(gains, self._apply_fade_curve(t_in, clip.get('fade_in_curve', 0.0)))
                    if fade_out_frames > 0:
                        remaining = float(duration_frames) - positions
                        t_out = np.clip(remaining / fade_out_frames, 0.0, 1.0)
                        gains = np.minimum(gains, self._apply_fade_curve(t_out, clip.get('fade_out_curve', 0.0)))

                    samples = samples * gains[:, None]

                mixed[out_offset:out_offset + frames_to_mix] += samples

            # Clip to prevent distortion
            np.clip(mixed, -1.0, 1.0, out=mixed)
            outdata[:] = mixed

            # Update position
            self._playback_sample += frames
            self.playback_position = self._playback_sample / self.sample_rate

    def play(self, start_time: float = 0):
        """Start playback from the given time."""
        if not SOUNDDEVICE_AVAILABLE:
            print("sounddevice not available")
            return

        with self._lock:
            self.playback_position = max(0.0, float(start_time))
            self._playback_sample = int(round(self.playback_position * self.sample_rate))
            self._ui_floor_time = self.playback_position
            self.is_playing = True

        if not self._ensure_stream():
            with self._lock:
                self.is_playing = False

    def pause(self):
        """Pause playback (keeps position)."""
        with self._lock:
            self.is_playing = False

    def stop(self):
        """Stop playback and reset position."""
        self.pause()
        with self._lock:
            self.playback_position = 0
            self._playback_sample = 0
            self._ui_floor_time = 0.0

    def seek(self, time: float):
        """Seek to a specific time."""
        with self._lock:
            self.playback_position = max(0.0, float(time))
            self._playback_sample = int(round(self.playback_position * self.sample_rate))
            self._ui_floor_time = self.playback_position

    def is_active(self) -> bool:
        """Check if currently playing."""
        return self.is_playing and self._stream is not None

    def get_position(self) -> float:
        """Get current playback position in seconds."""
        return self.playback_position

    def get_position_for_ui(self) -> float:
        """Playback position aligned to what you hear (accounts for output latency)."""
        with self._lock:
            position = float(self.playback_position)
            floor_time = float(self._ui_floor_time)

        compensated = position - self.get_output_latency()
        if compensated < floor_time:
            return floor_time
        return compensated

    def cleanup(self):
        """Clean up resources."""
        self.stop()
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self.loaded_audio.clear()

    def get_waveform(self, filepath: str, width: int) -> Optional[list]:
        """Get pre-computed waveform data resampled to specified width."""
        if filepath not in self.loaded_audio:
            return None

        audio = self.loaded_audio[filepath]
        return audio.get_waveform_for_width(width)

    def get_waveform_segment(self, filepath: str, width: int, source_start: float, duration: float) -> Optional[list]:
        """Get waveform data for a segment of the media."""
        if filepath not in self.loaded_audio:
            return None

        audio = self.loaded_audio[filepath]
        return audio.get_waveform_segment_for_width(width, source_start, duration)
