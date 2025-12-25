"""Main WaveSync application window using tkinter with FFmpeg playback."""
import sys
import os
import subprocess
import threading
import json
import math
import wave
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional, Callable, Dict
from PIL import Image, ImageTk
import io
import numpy as np

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False
    print("Warning: sounddevice not installed. Run: pip install sounddevice")


def get_ffmpeg_path():
    """Get FFmpeg executable path."""
    # Try common locations
    if sys.platform == 'win32':
        paths = [
            'ffmpeg',
            'C:\\ffmpeg\\bin\\ffmpeg.exe',
            os.path.expanduser('~\\ffmpeg\\bin\\ffmpeg.exe'),
        ]
    else:
        paths = ['ffmpeg', '/usr/bin/ffmpeg', '/usr/local/bin/ffmpeg']

    for path in paths:
        try:
            subprocess.run([path, '-version'], capture_output=True, check=True)
            return path
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    return 'ffmpeg'  # Hope it's in PATH


def get_ffplay_path():
    """Get FFplay executable path."""
    if sys.platform == 'win32':
        paths = [
            'ffplay',
            'C:\\ffmpeg\\bin\\ffplay.exe',
            os.path.expanduser('~\\ffplay\\bin\\ffplay.exe'),
        ]
    else:
        paths = ['ffplay', '/usr/bin/ffplay', '/usr/local/bin/ffplay']

    for path in paths:
        try:
            subprocess.run([path, '-version'], capture_output=True, check=True)
            return path
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    return 'ffplay'


def get_ffprobe_path():
    """Get FFprobe executable path."""
    if sys.platform == 'win32':
        paths = [
            'ffprobe',
            'C:\\ffmpeg\\bin\\ffprobe.exe',
            os.path.expanduser('~\\ffprobe\\bin\\ffprobe.exe'),
        ]
    else:
        paths = ['ffprobe', '/usr/bin/ffprobe', '/usr/local/bin/ffprobe']

    for path in paths:
        try:
            subprocess.run([path, '-version'], capture_output=True, check=True)
            return path
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    return 'ffprobe'


FFMPEG = get_ffmpeg_path()
FFPLAY = get_ffplay_path()
FFPROBE = get_ffprobe_path()


class MediaInfo:
    """Get media file information using FFprobe."""

    @staticmethod
    def get_duration(filepath: str) -> float:
        """Get media duration in seconds."""
        try:
            cmd = [
                FFPROBE, '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                filepath
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            data = json.loads(result.stdout)
            return float(data.get('format', {}).get('duration', 10.0))
        except Exception:
            return 10.0

    @staticmethod
    def get_info(filepath: str) -> dict:
        """Get full media information."""
        try:
            cmd = [
                FFPROBE, '-v', 'quiet',
                '-print_format', 'json',
                '-show_format', '-show_streams',
                filepath
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return json.loads(result.stdout)
        except Exception:
            return {}

    @staticmethod
    def has_video(filepath: str) -> bool:
        """Check if file has video stream."""
        info = MediaInfo.get_info(filepath)
        for stream in info.get('streams', []):
            if stream.get('codec_type') == 'video':
                return True
        return False

    @staticmethod
    def has_audio(filepath: str) -> bool:
        """Check if file has audio stream."""
        info = MediaInfo.get_info(filepath)
        for stream in info.get('streams', []):
            if stream.get('codec_type') == 'audio':
                return True
        return False


class VideoFrameExtractor:
    """Extract video frames using FFmpeg."""

    @staticmethod
    def extract_frame(filepath: str, time: float = 0, width: int = 320, height: int = 180) -> Optional[Image.Image]:
        """Extract a single frame at specified time."""
        try:
            cmd = [
                FFMPEG, '-ss', str(time),
                '-i', filepath,
                '-vframes', '1',
                '-s', f'{width}x{height}',
                '-f', 'image2pipe',
                '-vcodec', 'png',
                '-'
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=10)
            if result.returncode == 0 and result.stdout:
                return Image.open(io.BytesIO(result.stdout))
        except Exception as e:
            print(f"Frame extraction error: {e}")
        return None

    @staticmethod
    def extract_thumbnail(filepath: str, width: int = 160, height: int = 90) -> Optional[Image.Image]:
        """Extract a thumbnail from the video."""
        return VideoFrameExtractor.extract_frame(filepath, time=1.0, width=width, height=height)


class LoadedAudio:
    """Represents a loaded audio file with its decoded samples."""

    # Pre-compute waveform at 10 points per second
    # 400 sec file = 4000 points
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
        self._stream: Optional[sd.OutputStream] = None

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


class TimelineCanvas(tk.Canvas):
    """Timeline canvas with tracks and playhead."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg='#1a1a1a', highlightthickness=0, **kwargs)

        self.pixels_per_second = 100
        self.duration = 180  # 3 minutes
        self.playhead_position = 0.0
        self.tracks = []

        self.on_playhead_change: Optional[Callable] = None
        self.on_track_add_media: Optional[Callable] = None
        self.on_clip_select: Optional[Callable] = None
        self.on_timeline_edited: Optional[Callable[[], None]] = None

        # Playhead rendering (avoid full redraw on scrubbing)
        self._playhead_line_id: Optional[int] = None
        self._playhead_handle_id: Optional[int] = None
        self._drag_playhead = False

        # Track configuration
        self.track_height = 80
        self.header_width = 150
        self.ruler_height = 30

        # Button hit areas (track_index -> (x1, y1, x2, y2))
        self._add_buttons = {}

        # Clip thumbnails cache
        self._thumbnails = {}

        # Waveform cache: (filepath, width) -> waveform data
        self._waveform_cache: Dict[tuple, list] = {}

        # Reference to audio engine (set by app)
        self.audio_engine: Optional[AudioEngine] = None

        # Selection / editing state
        self.selected_clip: Optional[dict] = None
        self._drag_state: Optional[dict] = None

        self._clip_edge_px = 8
        self._min_clip_duration = 0.05  # seconds
        self._fade_handle_radius = 5
        self._fade_handle_y_offset = 14

        # Create default tracks
        self._create_default_tracks()

        # Bindings
        self.bind('<Button-1>', self._on_click)
        self.bind('<B1-Motion>', self._on_drag)
        self.bind('<ButtonRelease-1>', self._on_release)
        self.bind('<Configure>', self._on_resize)
        self.bind('<Motion>', self._on_motion)

        self._draw()

    def _create_default_tracks(self):
        self.tracks = [
            {'name': 'V1', 'type': 'video', 'color': '#a78bfa', 'muted': False, 'solo': False, 'clips': []},
            {'name': 'A1', 'type': 'audio', 'color': '#4ade80', 'muted': False, 'solo': False, 'clips': []},
            {'name': 'A2', 'type': 'audio', 'color': '#60a5fa', 'muted': False, 'solo': False, 'clips': []},
        ]

    def _on_click(self, event):
        self._drag_playhead = False

        # Check if click is on an add button
        for track_idx, (x1, y1, x2, y2) in self._add_buttons.items():
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                if self.on_track_add_media:
                    self.on_track_add_media(track_idx, self.tracks[track_idx])
                return

        # Track M/S buttons
        track_idx = self._track_index_at_y(event.y)
        if track_idx is not None and event.x < self.header_width:
            track_y = self.ruler_height + track_idx * self.track_height
            if 12 <= event.x <= 36 and (track_y + 50) <= event.y <= (track_y + 70):
                self.tracks[track_idx]['muted'] = not self.tracks[track_idx].get('muted', False)
                self._draw()
                if self.on_timeline_edited:
                    self.on_timeline_edited()
                return
            if 42 <= event.x <= 66 and (track_y + 50) <= event.y <= (track_y + 70):
                self.tracks[track_idx]['solo'] = not self.tracks[track_idx].get('solo', False)
                self._draw()
                if self.on_timeline_edited:
                    self.on_timeline_edited()
                return

        # Clip selection / drag begin
        hit = self._hit_test_clip(event.x, event.y)
        if hit:
            hit_track_idx, hit_clip, hit_part = hit
            if hit_clip.get('loading'):
                return

            self.selected_clip = hit_clip
            if self.on_clip_select:
                self.on_clip_select(hit_clip, hit_track_idx)

            start_time = float(hit_clip.get('start', 0.0))
            duration = float(hit_clip.get('duration', 0.0))
            source_start = float(hit_clip.get('source_start', 0.0))
            media_duration = hit_clip.get('media_duration')
            if media_duration is None and self.audio_engine and hit_clip.get('path') in self.audio_engine.loaded_audio:
                media_duration = self.audio_engine.loaded_audio[hit_clip.get('path')].duration

            clip_start_x = self.header_width + (start_time * self.pixels_per_second)
            curve_target = None
            curve_start = None
            if hit_part in ('fade_in', 'fade_in_curve'):
                curve_target = 'fade_in_curve'
                curve_start = float(hit_clip.get('fade_in_curve', 0.0))
            elif hit_part in ('fade_out', 'fade_out_curve'):
                curve_target = 'fade_out_curve'
                curve_start = float(hit_clip.get('fade_out_curve', 0.0))

            self._drag_state = {
                'mode': hit_part,  # 'move' | 'trim_start' | 'trim_end'
                'track_idx': hit_track_idx,
                'clip': hit_clip,
                'mouse_x': event.x,
                'mouse_y': event.y,
                'mouse_y_start': event.y,
                'curve_target': curve_target,
                'curve_start': curve_start,
                'start_time': start_time,
                'duration': duration,
                'source_start': source_start,
                'media_duration': float(media_duration) if media_duration is not None else None,
                'grab_offset_x': float(event.x) - float(clip_start_x),
            }
            self._draw()
            return
        else:
            if self.selected_clip is not None:
                self.selected_clip = None
                self._draw()

        # Click anywhere in the timeline content (including ruler) moves playhead
        if event.x > self.header_width:
            time = (event.x - self.header_width) / self.pixels_per_second
            self.set_playhead(time)
            if self.on_playhead_change:
                self.on_playhead_change(self.playhead_position)
            self._drag_playhead = True

    def _on_drag(self, event):
        if self._drag_state:
            self._apply_drag(event.x, event.y)
            return

        if self._drag_playhead and event.x > self.header_width:
            time = max(0, min(self.duration, (event.x - self.header_width) / self.pixels_per_second))
            self.set_playhead(time)
            if self.on_playhead_change:
                self.on_playhead_change(self.playhead_position)

    def _on_release(self, event):
        self._drag_playhead = False
        if not self._drag_state:
            return
        self._drag_state = None
        self._sort_all_tracks()
        self._draw()
        if self.on_timeline_edited:
            self.on_timeline_edited()

    def _on_resize(self, event):
        self._draw()

    def _on_motion(self, event):
        if self._drag_state:
            return

        cursor = ''

        # Add button hover
        for track_idx, (x1, y1, x2, y2) in self._add_buttons.items():
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                cursor = 'hand2'
                self.config(cursor=cursor)
                return

        # Track M/S hover
        track_idx = self._track_index_at_y(event.y)
        if track_idx is not None and event.x < self.header_width:
            track_y = self.ruler_height + track_idx * self.track_height
            if ((12 <= event.x <= 36) or (42 <= event.x <= 66)) and ((track_y + 50) <= event.y <= (track_y + 70)):
                self.config(cursor='hand2')
                return

        # Clip hover
        hit = self._hit_test_clip(event.x, event.y)
        if hit:
            _, _, part = hit
            if part in ('trim_start', 'trim_end', 'fade_in', 'fade_out'):
                cursor = 'sb_h_double_arrow'
            elif part in ('fade_in_curve', 'fade_out_curve'):
                cursor = 'sb_v_double_arrow'
            else:
                cursor = 'fleur'

        self.config(cursor=cursor)

    def _track_index_at_y(self, y: int) -> Optional[int]:
        if y < self.ruler_height:
            return None
        rel = y - self.ruler_height
        idx = int(rel // self.track_height)
        if 0 <= idx < len(self.tracks):
            return idx
        return None

    def _clip_rect(self, clip: dict, track_idx: int) -> Optional[tuple]:
        """Return (x1, y1, x2, y2) in canvas coords for a clip."""
        if 'start' not in clip or 'duration' not in clip:
            return None
        track_y = self.ruler_height + track_idx * self.track_height
        padding = 4
        x1 = self.header_width + float(clip['start']) * self.pixels_per_second
        x2 = self.header_width + float(clip['start'] + clip['duration']) * self.pixels_per_second
        y1 = track_y + padding
        y2 = track_y + self.track_height - padding
        return (x1, y1, x2, y2)

    def _hit_test_clip(self, x: int, y: int) -> Optional[tuple]:
        """Return (track_idx, clip, part) where part is move/trim_start/trim_end/fade_in/fade_out/fade_*_curve."""
        for track_idx, track in enumerate(self.tracks):
            for clip in track.get('clips', []):
                rect = self._clip_rect(clip, track_idx)
                if not rect:
                    continue
                x1, y1, x2, y2 = rect
                if x1 <= x <= x2 and y1 <= y <= y2:
                    if not clip.get('loading'):
                        is_selected = clip is self.selected_clip
                        handle_y = y1 + self._fade_handle_y_offset
                        r = self._fade_handle_radius
                        r2 = r * r

                        fade_in = float(clip.get('fade_in', 0.0))
                        fade_in_x = x1 + (fade_in * self.pixels_per_second)
                        fade_in_x = max(x1, min(fade_in_x, x2))
                        if ((x - fade_in_x) * (x - fade_in_x) + (y - handle_y) * (y - handle_y)) <= r2:
                            return (track_idx, clip, 'fade_in')

                        fade_out = float(clip.get('fade_out', 0.0))
                        fade_out_x = x2 - (fade_out * self.pixels_per_second)
                        fade_out_x = max(x1, min(fade_out_x, x2))
                        if ((x - fade_out_x) * (x - fade_out_x) + (y - handle_y) * (y - handle_y)) <= r2:
                            return (track_idx, clip, 'fade_out')

                        if is_selected:
                            line_top = y1 + 2
                            line_bottom = y2 - 2
                            line_height = max(1, line_bottom - line_top)
                            curve_r = max(3, r - 2)
                            curve_r2 = curve_r * curve_r

                            if fade_in > 0:
                                fade_px = fade_in_x - x1
                                if fade_px >= (curve_r * 4):
                                    mid_x = x1 + (fade_px / 2)
                                    mid_g = self._curve_gain(0.5, clip.get('fade_in_curve', 0.0))
                                    mid_y = line_bottom - (mid_g * line_height)
                                    if ((x - mid_x) * (x - mid_x) + (y - mid_y) * (y - mid_y)) <= curve_r2:
                                        return (track_idx, clip, 'fade_in_curve')

                            if fade_out > 0:
                                fade_px = x2 - fade_out_x
                                if fade_px >= (curve_r * 4):
                                    mid_x = fade_out_x + (fade_px / 2)
                                    mid_g = self._curve_gain(0.5, clip.get('fade_out_curve', 0.0))
                                    mid_y = line_bottom - (mid_g * line_height)
                                    if ((x - mid_x) * (x - mid_x) + (y - mid_y) * (y - mid_y)) <= curve_r2:
                                        return (track_idx, clip, 'fade_out_curve')

                    if (x - x1) <= self._clip_edge_px and (x2 - x1) >= (self._clip_edge_px * 2):
                        return (track_idx, clip, 'trim_start')
                    if (x2 - x) <= self._clip_edge_px and (x2 - x1) >= (self._clip_edge_px * 2):
                        return (track_idx, clip, 'trim_end')
                    return (track_idx, clip, 'move')
        return None

    def _apply_drag(self, x: int, y: int):
        state = self._drag_state
        if not state:
            return

        clip = state['clip']
        mode = state['mode']
        track_idx = state['track_idx']

        if mode == 'move':
            new_track_idx = self._track_index_at_y(y)
            if new_track_idx is not None and new_track_idx != track_idx:
                old_track = self.tracks[track_idx]
                new_track = self.tracks[new_track_idx]
                if clip in old_track.get('clips', []):
                    old_track['clips'].remove(clip)
                new_track.setdefault('clips', []).append(clip)
                state['track_idx'] = new_track_idx
                track_idx = new_track_idx

        media_duration = state.get('media_duration')

        if mode == 'move':
            new_start = (float(x) - self.header_width - float(state['grab_offset_x'])) / self.pixels_per_second
            clip['start'] = max(0.0, new_start)

        elif mode == 'trim_start':
            original_start = float(state['start_time'])
            original_duration = float(state['duration'])
            original_source_start = float(state['source_start'])
            original_source_end = original_source_start + original_duration
            original_end = original_start + original_duration

            earliest_start = max(0.0, original_start - original_source_start)
            latest_start = max(0.0, original_end - self._min_clip_duration)

            proposed_start = (float(x) - self.header_width) / self.pixels_per_second
            proposed_start = max(earliest_start, min(proposed_start, latest_start))

            new_duration = max(self._min_clip_duration, original_end - proposed_start)
            new_source_start = original_source_end - new_duration

            if media_duration is not None:
                new_source_start = max(0.0, min(float(media_duration), float(new_source_start)))
                max_duration = max(self._min_clip_duration, float(media_duration) - new_source_start)
                new_duration = min(new_duration, max_duration)
                proposed_start = original_end - new_duration

            clip['start'] = max(0.0, proposed_start)
            clip['duration'] = max(self._min_clip_duration, new_duration)
            clip['source_start'] = max(0.0, new_source_start)
            clip['fade_in'] = max(0.0, min(float(clip.get('fade_in', 0.0)), float(clip['duration'])))
            clip['fade_out'] = max(0.0, min(float(clip.get('fade_out', 0.0)), float(clip['duration'])))

        elif mode == 'trim_end':
            original_start = float(state['start_time'])
            original_source_start = float(state['source_start'])

            proposed_end = (float(x) - self.header_width) / self.pixels_per_second
            proposed_end = max(original_start + self._min_clip_duration, proposed_end)

            new_duration = proposed_end - original_start

            if media_duration is not None:
                max_duration = max(self._min_clip_duration, float(media_duration) - float(original_source_start))
                new_duration = min(new_duration, max_duration)

            clip['duration'] = max(self._min_clip_duration, new_duration)
            clip['fade_in'] = max(0.0, min(float(clip.get('fade_in', 0.0)), float(clip['duration'])))
            clip['fade_out'] = max(0.0, min(float(clip.get('fade_out', 0.0)), float(clip['duration'])))

        elif mode == 'fade_in':
            clip_start = float(clip.get('start', 0.0))
            clip_duration = float(clip.get('duration', 0.0))
            start_x = self.header_width + (clip_start * self.pixels_per_second)
            new_fade = (float(x) - float(start_x)) / self.pixels_per_second
            clip['fade_in'] = max(0.0, min(float(new_fade), float(clip_duration)))
            if state.get('curve_target') == 'fade_in_curve' and state.get('curve_start') is not None:
                dy = float(y) - float(state.get('mouse_y_start', y))
                curve = float(state['curve_start']) - (dy / 10.0)
                clip['fade_in_curve'] = max(-5.0, min(5.0, curve))

        elif mode == 'fade_out':
            clip_start = float(clip.get('start', 0.0))
            clip_duration = float(clip.get('duration', 0.0))
            end_x = self.header_width + ((clip_start + clip_duration) * self.pixels_per_second)
            new_fade = (float(end_x) - float(x)) / self.pixels_per_second
            clip['fade_out'] = max(0.0, min(float(new_fade), float(clip_duration)))
            if state.get('curve_target') == 'fade_out_curve' and state.get('curve_start') is not None:
                dy = float(y) - float(state.get('mouse_y_start', y))
                curve = float(state['curve_start']) - (dy / 10.0)
                clip['fade_out_curve'] = max(-5.0, min(5.0, curve))

        elif mode == 'fade_in_curve':
            track_y = self.ruler_height + track_idx * self.track_height
            clip_y1 = track_y + 4
            clip_y2 = track_y + self.track_height - 4
            line_top = clip_y1 + 2
            line_bottom = clip_y2 - 2
            line_height = max(1, line_bottom - line_top)
            gain = (line_bottom - float(y)) / float(line_height)
            clip['fade_in_curve'] = self._curve_from_mid_gain(gain)

        elif mode == 'fade_out_curve':
            track_y = self.ruler_height + track_idx * self.track_height
            clip_y1 = track_y + 4
            clip_y2 = track_y + self.track_height - 4
            line_top = clip_y1 + 2
            line_bottom = clip_y2 - 2
            line_height = max(1, line_bottom - line_top)
            gain = (line_bottom - float(y)) / float(line_height)
            clip['fade_out_curve'] = self._curve_from_mid_gain(gain)

        self._draw()

    def _sort_all_tracks(self):
        for track in self.tracks:
            clips = track.get('clips', [])
            if clips:
                clips.sort(key=lambda c: float(c.get('start', 0.0)))

    def _curve_gain(self, t: float, curve: float) -> float:
        """Map a 0..1 ramp to a curved ramp (0=linear)."""
        t = max(0.0, min(1.0, float(t)))
        try:
            curve = float(curve)
        except Exception:
            curve = 0.0

        if abs(curve) < 1e-6:
            return t

        power = 1.0 + min(8.0, abs(curve))
        if curve > 0:
            return t ** power
        return 1.0 - ((1.0 - t) ** power)

    def _curve_from_mid_gain(self, gain: float) -> float:
        """Invert curve based on midpoint gain at t=0.5."""
        try:
            gain = float(gain)
        except Exception:
            return 0.0

        gain = max(0.001, min(0.999, gain))
        if abs(gain - 0.5) < 1e-3:
            return 0.0

        log_half = math.log(0.5)
        if gain < 0.5:
            power = math.log(gain) / log_half
            curve = power - 1.0
            return max(0.0, min(5.0, curve))

        power = math.log(1.0 - gain) / log_half
        curve = -(power - 1.0)
        return min(0.0, max(-5.0, curve))

    def set_playhead(self, position: float):
        self.playhead_position = max(0, min(position, self.duration))
        self._update_playhead_visual()

    def set_zoom(self, pixels_per_second: int):
        self.pixels_per_second = max(10, min(300, pixels_per_second))
        self._waveform_cache.clear()  # Clear cache as clip widths change
        self._draw()

    def _draw(self):
        self.delete('all')
        self._add_buttons.clear()
        self._playhead_line_id = None
        self._playhead_handle_id = None
        width = self.winfo_width()
        height = self.winfo_height()

        if width < 10 or height < 10:
            return

        # Draw ruler background
        self.create_rectangle(0, 0, width, self.ruler_height, fill='#2d2d2d', outline='')
        self.create_rectangle(0, 0, self.header_width, self.ruler_height, fill='#252525', outline='')

        # Draw ruler ticks and labels
        self._draw_ruler(width)

        # Draw tracks
        y = self.ruler_height
        for idx, track in enumerate(self.tracks):
            self._draw_track(track, y, width, idx)
            y += self.track_height

        # Draw playhead
        self._draw_playhead(height)

        # Draw borders
        self.create_line(self.header_width, 0, self.header_width, height, fill='#444444')
        self.create_line(0, self.ruler_height, width, self.ruler_height, fill='#444444')

    def _draw_ruler(self, width):
        # Determine tick interval
        if self.pixels_per_second >= 100:
            major = 1
            minor = 0.25
        elif self.pixels_per_second >= 50:
            major = 2
            minor = 0.5
        elif self.pixels_per_second >= 20:
            major = 5
            minor = 1
        else:
            major = 10
            minor = 2

        t = 0.0
        while t <= self.duration:
            x = self.header_width + int(t * self.pixels_per_second)
            if x > width:
                break

            is_major = abs(t % major) < 0.01 or t == 0

            if is_major:
                self.create_line(x, 15, x, self.ruler_height, fill='#888888')
                minutes = int(t // 60)
                seconds = int(t % 60)
                self.create_text(x + 4, 8, text=f"{minutes}:{seconds:02d}",
                               anchor='w', fill='#888888', font=('Segoe UI', 9))
            else:
                self.create_line(x, 22, x, self.ruler_height, fill='#555555')

            t += minor

    def _draw_track(self, track, y, width, track_idx):
        # Track header
        self.create_rectangle(0, y, self.header_width, y + self.track_height,
                            fill='#252525', outline='')

        # Color indicator
        self.create_rectangle(0, y, 4, y + self.track_height, fill=track['color'], outline='')

        # Track name
        self.create_text(12, y + 12, text=track['name'], anchor='w',
                        fill='#ffffff', font=('Segoe UI', 11, 'bold'))
        self.create_text(12, y + 30, text=track['type'].capitalize(), anchor='w',
                        fill='#888888', font=('Segoe UI', 9))

        # M/S buttons
        m_color = '#f87171' if track['muted'] else '#3a3a3a'
        s_color = '#fb923c' if track['solo'] else '#3a3a3a'

        self.create_rectangle(12, y + 50, 36, y + 70, fill=m_color, outline='#555555')
        self.create_text(24, y + 60, text='M', fill='#ffffff', font=('Segoe UI', 9, 'bold'))

        self.create_rectangle(42, y + 50, 66, y + 70, fill=s_color, outline='#555555')
        self.create_text(54, y + 60, text='S', fill='#ffffff', font=('Segoe UI', 9, 'bold'))

        # Add media button (+)
        btn_x1, btn_y1 = 100, y + 50
        btn_x2, btn_y2 = 140, y + 70
        self.create_rectangle(btn_x1, btn_y1, btn_x2, btn_y2, fill='#4ade80', outline='#3ac070')
        self.create_text((btn_x1 + btn_x2) // 2, (btn_y1 + btn_y2) // 2, text='+',
                        fill='#1a1a1a', font=('Segoe UI', 14, 'bold'))
        self._add_buttons[track_idx] = (btn_x1, btn_y1, btn_x2, btn_y2)

        # Track content area
        self.create_rectangle(self.header_width, y, width, y + self.track_height,
                            fill='#1a1a1a', outline='')

        # Grid lines
        t = 0.0
        major = 5 if self.pixels_per_second < 50 else 1
        while t <= self.duration:
            x = self.header_width + int(t * self.pixels_per_second)
            if x > width:
                break
            self.create_line(x, y, x, y + self.track_height, fill='#2a2a2a')
            t += major

        # Draw clips if any
        for clip in track.get('clips', []):
            self._draw_clip(clip, track, y, width)

        # Bottom border
        self.create_line(0, y + self.track_height - 1, width, y + self.track_height - 1, fill='#333333')

        # "Drop media" hint (only if no clips)
        if not track.get('clips'):
            center_x = self.header_width + (width - self.header_width) // 2
            center_y = y + self.track_height // 2
            self.create_text(center_x, center_y, text="Click + to add media",
                            fill='#444444', font=('Segoe UI', 10))

    def _draw_clip(self, clip, track, y, width):
        """Draw a media clip on the track with waveform."""
        start_x = self.header_width + int(clip['start'] * self.pixels_per_second)
        end_x = self.header_width + int((clip['start'] + clip['duration']) * self.pixels_per_second)
        if end_x <= start_x + 2:
            end_x = start_x + 2
        clip_width = end_x - start_x

        # Clip rectangle (darker background for waveform contrast)
        padding = 4
        clip_y1 = y + padding
        clip_y2 = y + self.track_height - padding
        clip_height = clip_y2 - clip_y1

        is_loading = clip.get('loading', False)
        is_selected = clip is self.selected_clip

        # Draw clip background
        if is_loading:
            bg_color = '#333333'  # Gray for loading
            outline_color = '#666666'
            outline_width = 1
        else:
            bg_color = self._darken_color(track['color'], 0.3)
            outline_color = '#ffffff' if is_selected else track['color']
            outline_width = 2 if is_selected else 1

        self.create_rectangle(start_x + 1, clip_y1, end_x - 1, clip_y2,
                            fill=bg_color, outline=outline_color, width=outline_width)

        if is_selected and not is_loading and clip_width >= 12:
            self.create_line(start_x + 2, clip_y1, start_x + 2, clip_y2, fill='#ffffff')
            self.create_line(end_x - 2, clip_y1, end_x - 2, clip_y2, fill='#ffffff')

        # Draw waveform if audio engine available and clip has audio (not loading)
        if not is_loading and self.audio_engine and clip.get('path') and clip_width > 10:
            self._draw_waveform(clip, track, start_x, clip_y1, clip_width, clip_height)

        # Fade handles / lines
        if not is_loading:
            fade_in = max(0.0, float(clip.get('fade_in', 0.0)))
            fade_out = max(0.0, float(clip.get('fade_out', 0.0)))

            if is_selected or fade_in > 0 or fade_out > 0:
                r = self._fade_handle_radius
                handle_y = clip_y1 + self._fade_handle_y_offset
                line_top = clip_y1 + 2
                line_bottom = clip_y2 - 2
                line_height = max(1, line_bottom - line_top)
                curve_r = max(3, r - 2)

                fade_in_x = start_x + int(fade_in * self.pixels_per_second)
                fade_in_x = max(start_x, min(fade_in_x, end_x))
                if fade_in > 0:
                    fade_px = max(1, fade_in_x - start_x)
                    steps = max(4, min(32, fade_px // 8))
                    curve = clip.get('fade_in_curve', 0.0)
                    points = []
                    for i in range(steps + 1):
                        p = i / steps
                        g = self._curve_gain(p, curve)
                        x = start_x + int(p * fade_px)
                        y = int(line_bottom - g * line_height)
                        points.extend([x, y])
                    if len(points) >= 4:
                        self.create_line(points, fill='#ffd24a', width=1, smooth=True)

                    if is_selected and fade_px >= (curve_r * 4):
                        mid_x = start_x + (fade_px / 2)
                        mid_g = self._curve_gain(0.5, curve)
                        mid_y = int(line_bottom - mid_g * line_height)
                        self.create_oval(mid_x - curve_r, mid_y - curve_r, mid_x + curve_r, mid_y + curve_r,
                                         fill='#ffd24a', outline='')
                self.create_oval(fade_in_x - r, handle_y - r, fade_in_x + r, handle_y + r,
                                 fill='#ffffff', outline='')

                fade_out_x = end_x - int(fade_out * self.pixels_per_second)
                fade_out_x = max(start_x, min(fade_out_x, end_x))
                if fade_out > 0:
                    fade_px = max(1, end_x - fade_out_x)
                    steps = max(4, min(32, fade_px // 8))
                    curve = clip.get('fade_out_curve', 0.0)
                    points = []
                    for i in range(steps + 1):
                        p = i / steps
                        g = self._curve_gain(1.0 - p, curve)
                        x = fade_out_x + int(p * fade_px)
                        y = int(line_bottom - g * line_height)
                        points.extend([x, y])
                    if len(points) >= 4:
                        self.create_line(points, fill='#ffd24a', width=1, smooth=True)

                    if is_selected and fade_px >= (curve_r * 4):
                        mid_x = fade_out_x + (fade_px / 2)
                        mid_g = self._curve_gain(0.5, curve)
                        mid_y = int(line_bottom - mid_g * line_height)
                        self.create_oval(mid_x - curve_r, mid_y - curve_r, mid_x + curve_r, mid_y + curve_r,
                                         fill='#ffd24a', outline='')
                self.create_oval(fade_out_x - r, handle_y - r, fade_out_x + r, handle_y + r,
                                 fill='#ffffff', outline='')

        # Clip name (top left)
        clip_name = clip.get('name', 'Clip')
        if len(clip_name) > 25:
            clip_name = clip_name[:22] + '...'
        # Draw text with shadow for visibility
        self.create_text(start_x + 6, clip_y1 + 10, text=clip_name,
                        anchor='w', fill='#000000', font=('Segoe UI', 8, 'bold'))
        self.create_text(start_x + 5, clip_y1 + 9, text=clip_name,
                        anchor='w', fill='#ffffff', font=('Segoe UI', 8, 'bold'))

        # Show loading text in center if loading
        if is_loading:
            center_x = (start_x + end_x) // 2
            center_y = (clip_y1 + clip_y2) // 2
            self.create_text(center_x, center_y, text="Loading...",
                            fill='#aaaaaa', font=('Segoe UI', 10, 'italic'))
        else:
            # Duration text (top right)
            duration_text = f"{clip['duration']:.1f}s"
            self.create_text(end_x - 6, clip_y1 + 10, text=duration_text,
                            anchor='e', fill='#000000', font=('Segoe UI', 8))
            self.create_text(end_x - 5, clip_y1 + 9, text=duration_text,
                            anchor='e', fill='#ffffff', font=('Segoe UI', 8))

    def _draw_waveform(self, clip, track, start_x, clip_y, clip_width, clip_height):
        """Draw simplified waveform inside clip."""
        filepath = clip.get('path')
        if not filepath or clip_width < 10:
            return

        source_start = float(clip.get('source_start', 0.0))
        duration = float(clip.get('duration', 0.0))

        end_x = start_x + int(clip_width)
        canvas_width = self.winfo_width()

        visible_x1 = max(start_x, self.header_width)
        visible_x2 = min(end_x, canvas_width)
        visible_width = int(visible_x2 - visible_x1)
        if visible_width < 10:
            return

        visible_offset = (visible_x1 - start_x) / self.pixels_per_second
        segment_source_start = source_start + max(0.0, float(visible_offset))
        segment_duration = min(duration - max(0.0, float(visible_offset)), visible_width / self.pixels_per_second)
        if segment_duration <= 0:
            return

        cache_key = (filepath, visible_width, round(segment_source_start, 3), round(segment_duration, 3))
        waveform = self._waveform_cache.get(cache_key)
        if waveform is None:
            waveform = self.audio_engine.get_waveform_segment(filepath, visible_width, segment_source_start, segment_duration)
            if waveform:
                self._waveform_cache[cache_key] = waveform

        if not waveform or len(waveform) < 2:
            return

        # Calculate drawing parameters
        center_y = clip_y + clip_height // 2
        max_amplitude = clip_height // 2 - 2

        # Build simple polygon - much fewer points
        points = []
        num_points = len(waveform)
        pixel_step = (visible_width - 4) / max(1, num_points - 1)

        # Top edge (max values)
        for i, (min_val, max_val) in enumerate(waveform):
            x = int(visible_x1 + 2 + (i * pixel_step))
            y = int(center_y - max_val * max_amplitude)
            points.extend([x, y])

        # Bottom edge (min values, reversed)
        for i in range(num_points - 1, -1, -1):
            min_val, max_val = waveform[i]
            x = int(visible_x1 + 2 + (i * pixel_step))
            y = int(center_y - min_val * max_amplitude)
            points.extend([x, y])

        if len(points) >= 6:
            self.create_polygon(points, fill=track['color'], outline='')

    def _darken_color(self, hex_color: str, factor: float) -> str:
        """Darken a hex color by a factor (0-1)."""
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        r = int(r * factor)
        g = int(g * factor)
        b = int(b * factor)
        return f'#{r:02x}{g:02x}{b:02x}'

    def _draw_playhead(self, height):
        self._update_playhead_visual(height)

    def _update_playhead_visual(self, height: Optional[int] = None):
        if height is None:
            height = self.winfo_height()
        if height < 1:
            return

        x = self.header_width + int(round(self.playhead_position * self.pixels_per_second))
        if self._playhead_line_id is None:
            self._playhead_line_id = self.create_line(
                x, 0, x, height,
                fill='#ff4444',
                width=2,
                tags=('playhead',),
            )
        else:
            try:
                self.coords(self._playhead_line_id, x, 0, x, height)
            except Exception:
                self._playhead_line_id = None
                return self._update_playhead_visual(height)

        if self._playhead_handle_id is None:
            self._playhead_handle_id = self.create_polygon(
                x - 8, 0, x + 8, 0, x, 12,
                fill='#ff4444',
                outline='',
                tags=('playhead',),
            )
        else:
            try:
                self.coords(self._playhead_handle_id, x - 8, 0, x + 8, 0, x, 12)
            except Exception:
                self._playhead_handle_id = None

        self.tag_raise('playhead')


class WaveSyncApp:
    """Main WaveSync application."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("WaveSync - Audio/Video Editor")
        self.root.geometry("1280x800")
        self.root.minsize(1024, 700)
        self.root.configure(bg='#1a1a1a')

        # State
        self.is_playing = False
        self.playhead_position = 0.0
        self.project_duration = 180.0

        # Audio engine (loads audio into memory like Audacity)
        self.audio_engine = AudioEngine()

        # Current preview image
        self.preview_image = None
        self.current_video_clip = None
        self._preview_lock = threading.Lock()
        self._preview_event = threading.Event()
        self._preview_request: Optional[tuple] = None  # (request_id, filepath, time)
        self._preview_request_id = 0
        self._preview_worker_started = False

        # Apply dark theme
        self._setup_style()
        self._setup_menu()
        self._setup_ui()
        self._setup_bindings()

        # Playback timer
        self.playback_job = None

        # Cleanup on close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        """Clean up resources on close."""
        self.audio_engine.cleanup()
        self.root.destroy()

    def _setup_style(self):
        style = ttk.Style()
        style.theme_use('clam')

        # Configure colors
        style.configure('.', background='#1a1a1a', foreground='#cccccc')
        style.configure('TFrame', background='#1a1a1a')
        style.configure('TLabel', background='#1a1a1a', foreground='#cccccc')
        style.configure('TButton', background='#3a3a3a', foreground='#cccccc',
                       borderwidth=1, focuscolor='none')
        style.map('TButton',
                 background=[('active', '#4a4a4a'), ('pressed', '#2d2d2d')])

        style.configure('Play.TButton', background='#4ade80', foreground='#1a1a1a')
        style.map('Play.TButton', background=[('active', '#5aee90')])

        style.configure('Stop.TButton', background='#f87171', foreground='#1a1a1a')
        style.map('Stop.TButton', background=[('active', '#ff8181')])

        style.configure('Horizontal.TScale', background='#1a1a1a', troughcolor='#2d2d2d')

    def _setup_menu(self):
        menubar = tk.Menu(self.root, bg='#2d2d2d', fg='#cccccc',
                         activebackground='#60a5fa', activeforeground='#ffffff',
                         borderwidth=0)
        self.root.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0, bg='#2d2d2d', fg='#cccccc',
                           activebackground='#60a5fa', activeforeground='#ffffff')
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New Project", accelerator="Ctrl+N", command=self._on_new)
        file_menu.add_command(label="Open Project...", accelerator="Ctrl+O", command=self._on_open)
        file_menu.add_command(label="Save Project", accelerator="Ctrl+S", command=self._on_save)
        file_menu.add_separator()
        file_menu.add_command(label="Import Media...", accelerator="Ctrl+I", command=self._on_import)
        file_menu.add_command(label="Export...", accelerator="Ctrl+E", command=self._on_export)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", accelerator="Alt+F4", command=self._on_close)

        # Edit menu
        edit_menu = tk.Menu(menubar, tearoff=0, bg='#2d2d2d', fg='#cccccc',
                           activebackground='#60a5fa', activeforeground='#ffffff')
        menubar.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(label="Undo", accelerator="Ctrl+Z", state='disabled')
        edit_menu.add_command(label="Redo", accelerator="Ctrl+Y", state='disabled')
        edit_menu.add_separator()
        edit_menu.add_command(label="Split at Playhead", accelerator="S", command=self._on_split)

        # Track menu
        track_menu = tk.Menu(menubar, tearoff=0, bg='#2d2d2d', fg='#cccccc',
                            activebackground='#60a5fa', activeforeground='#ffffff')
        menubar.add_cascade(label="Track", menu=track_menu)
        track_menu.add_command(label="Add Video Track", command=self._on_add_video_track)
        track_menu.add_command(label="Add Audio Track", command=self._on_add_audio_track)

        # View menu
        view_menu = tk.Menu(menubar, tearoff=0, bg='#2d2d2d', fg='#cccccc',
                           activebackground='#60a5fa', activeforeground='#ffffff')
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Zoom In", accelerator="Ctrl++", command=self._on_zoom_in)
        view_menu.add_command(label="Zoom Out", accelerator="Ctrl+-", command=self._on_zoom_out)
        view_menu.add_command(label="Zoom to Fit", accelerator="Ctrl+0", command=self._on_zoom_fit)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0, bg='#2d2d2d', fg='#cccccc',
                           activebackground='#60a5fa', activeforeground='#ffffff')
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Keyboard Shortcuts", accelerator="F1", command=self._on_shortcuts)
        help_menu.add_command(label="About WaveSync", command=self._on_about)

    def _setup_ui(self):
        # Main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill='both', expand=True)

        # Toolbar
        toolbar = tk.Frame(main_frame, bg='#2d2d2d', height=50)
        toolbar.pack(fill='x', side='top')
        toolbar.pack_propagate(False)

        # Transport controls
        transport_frame = tk.Frame(toolbar, bg='#2d2d2d')
        transport_frame.pack(side='left', padx=10, pady=8)

        btn_style = {'bg': '#3a3a3a', 'fg': '#cccccc', 'activebackground': '#4a4a4a',
                    'activeforeground': '#cccccc', 'bd': 0, 'padx': 12, 'pady': 6,
                    'font': ('Segoe UI', 12)}

        self.skip_back_btn = tk.Button(transport_frame, text="⏮", command=self._on_skip_back, **btn_style)
        self.skip_back_btn.pack(side='left', padx=2)

        self.play_btn = tk.Button(transport_frame, text="▶", command=self._on_play_pause,
                                 bg='#4ade80', fg='#1a1a1a', activebackground='#5aee90',
                                 activeforeground='#1a1a1a', bd=0, padx=16, pady=6,
                                 font=('Segoe UI', 12, 'bold'))
        self.play_btn.pack(side='left', padx=2)

        self.stop_btn = tk.Button(transport_frame, text="⏹", command=self._on_stop,
                                 bg='#f87171', fg='#1a1a1a', activebackground='#ff8181',
                                 activeforeground='#1a1a1a', bd=0, padx=12, pady=6,
                                 font=('Segoe UI', 12))
        self.stop_btn.pack(side='left', padx=2)

        self.skip_fwd_btn = tk.Button(transport_frame, text="⏭", command=self._on_skip_forward, **btn_style)
        self.skip_fwd_btn.pack(side='left', padx=2)

        # Time display
        self.time_label = tk.Label(toolbar, text="00:00:00 / 03:00:00",
                                   bg='#1a1a1a', fg='#4ade80',
                                   font=('Consolas', 14, 'bold'), padx=12, pady=4)
        self.time_label.pack(side='left', padx=20)

        # Zoom controls
        zoom_frame = tk.Frame(toolbar, bg='#2d2d2d')
        zoom_frame.pack(side='right', padx=10)

        tk.Button(zoom_frame, text="-", command=self._on_zoom_out, **btn_style).pack(side='left')

        self.zoom_scale = tk.Scale(zoom_frame, from_=10, to=300, orient='horizontal',
                                   length=100, bg='#2d2d2d', fg='#cccccc',
                                   troughcolor='#1a1a1a', highlightthickness=0,
                                   showvalue=False, command=self._on_zoom_change)
        self.zoom_scale.set(100)
        self.zoom_scale.pack(side='left', padx=4)

        tk.Button(zoom_frame, text="+", command=self._on_zoom_in, **btn_style).pack(side='left')

        self.zoom_label = tk.Label(zoom_frame, text="100%", bg='#2d2d2d', fg='#888888',
                                   font=('Segoe UI', 10))
        self.zoom_label.pack(side='left', padx=8)

        # Preview area
        self.preview_frame = tk.Frame(main_frame, bg='#0a0a0a', height=250)
        self.preview_frame.pack(fill='x', padx=4, pady=4)
        self.preview_frame.pack_propagate(False)

        self.preview_label = tk.Label(self.preview_frame, text="Video Preview\n\nLoad a video to see preview",
                                bg='#0a0a0a', fg='#555555', font=('Segoe UI', 14))
        self.preview_label.place(relx=0.5, rely=0.5, anchor='center')

        # Timeline
        self.timeline = TimelineCanvas(main_frame, height=300)
        self.timeline.pack(fill='both', expand=True, padx=4, pady=4)
        self.timeline.on_playhead_change = self._on_playhead_change
        self.timeline.on_track_add_media = self._on_track_add_media
        self.timeline.on_timeline_edited = self._on_timeline_edited
        self.timeline.audio_engine = self.audio_engine  # Connect for waveform display

        # Status bar
        status_frame = tk.Frame(main_frame, bg='#2d2d2d', height=25)
        status_frame.pack(fill='x', side='bottom')
        status_frame.pack_propagate(False)

        self.status_label = tk.Label(status_frame, text="Ready", bg='#2d2d2d', fg='#888888',
                                    font=('Segoe UI', 10), anchor='w')
        self.status_label.pack(side='left', padx=10, pady=4)

        tk.Label(status_frame, text="48000 Hz | Stereo | 3 tracks", bg='#2d2d2d', fg='#888888',
                font=('Segoe UI', 10)).pack(side='right', padx=10, pady=4)

    def _setup_bindings(self):
        self.root.bind('<space>', lambda e: self._on_play_pause())
        self.root.bind('<Escape>', lambda e: self._on_stop())
        self.root.bind('<Left>', lambda e: self._on_skip_back())
        self.root.bind('<Right>', lambda e: self._on_skip_forward())
        self.root.bind('<Home>', lambda e: self._seek_to(0))
        self.root.bind('<End>', lambda e: self._seek_to(self.project_duration))
        self.root.bind('<Control-i>', lambda e: self._on_import())
        self.root.bind('<Control-I>', lambda e: self._on_import())
        self.root.bind('<Control-s>', lambda e: self._on_save())
        self.root.bind('<Control-S>', lambda e: self._on_save())
        self.root.bind('<Control-o>', lambda e: self._on_open())
        self.root.bind('<Control-O>', lambda e: self._on_open())
        self.root.bind('<Control-n>', lambda e: self._on_new())
        self.root.bind('<Control-N>', lambda e: self._on_new())
        self.root.bind('<s>', lambda e: self._on_split())
        self.root.bind('<F1>', lambda e: self._on_shortcuts())

    def _update_time_display(self):
        current = self._format_time(self.playhead_position)
        total = self._format_time(self.project_duration)
        self.time_label.config(text=f"{current} / {total}")

    def _format_time(self, seconds: float) -> str:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        frames = int((seconds % 1) * 30)
        return f"{minutes:02d}:{secs:02d}:{frames:02d}"

    def _seek_to(self, position: float):
        self.playhead_position = max(0, min(position, self.project_duration))
        self.audio_engine.seek(self.playhead_position)
        self.timeline.set_playhead(self.playhead_position)
        self._update_time_display()
        self._update_preview_for_time(self.playhead_position)

    def _on_playhead_change(self, position: float):
        self.playhead_position = position
        self.audio_engine.seek(position)
        self._update_time_display()
        self._update_preview_for_time(position)

    def _on_timeline_edited(self):
        max_end = 0.0
        for track in self.timeline.tracks:
            for clip in track.get('clips', []):
                if clip.get('loading'):
                    continue
                try:
                    end_time = float(clip.get('start', 0.0)) + float(clip.get('duration', 0.0))
                except Exception:
                    continue
                max_end = max(max_end, end_time)

        if max_end + 10 > self.project_duration:
            self.project_duration = max_end + 10
            self.timeline.duration = self.project_duration

        self._update_time_display()
        self._update_preview_for_time(self.playhead_position)

        if self.is_playing and self.audio_engine.is_active():
            all_clips = []
            for track in self._get_audible_tracks():
                for clip in track.get('clips', []):
                    if clip.get('loading'):
                        continue
                    all_clips.append(clip)
            self.audio_engine.set_clips(all_clips)

    def _update_preview_for_time(self, time: float):
        """Update preview image for the given time position."""
        # Find video clip at current time
        for track in self.timeline.tracks:
            if track['type'] == 'video':
                for clip in track.get('clips', []):
                    if clip['start'] <= time < clip['start'] + clip['duration']:
                        clip_time = (time - clip['start']) + float(clip.get('source_start', 0.0))
                        self._show_video_frame(clip['path'], clip_time)
                        return

    def _show_video_frame(self, filepath: str, time: float):
        """Extract and show video frame."""
        with self._preview_lock:
            self._preview_request_id += 1
            request_id = self._preview_request_id
            self._preview_request = (request_id, filepath, float(time))

            if not self._preview_worker_started:
                self._preview_worker_started = True
                threading.Thread(target=self._preview_worker, daemon=True).start()

        self._preview_event.set()

    def _preview_worker(self):
        while True:
            self._preview_event.wait()
            self._preview_event.clear()

            with self._preview_lock:
                request = self._preview_request

            if not request:
                continue

            request_id, filepath, time = request
            try:
                frame = VideoFrameExtractor.extract_frame(filepath, time, 400, 225)
            except Exception as e:
                print(f"Frame extraction error: {e}")
                frame = None

            if not frame:
                continue

            def maybe_display():
                with self._preview_lock:
                    latest = self._preview_request
                    if not latest or latest[0] != request_id:
                        return
                self._display_frame(frame)

            try:
                self.root.after(0, maybe_display)
            except Exception:
                return

    def _display_frame(self, image: Image.Image):
        """Display frame in preview area."""
        try:
            self.preview_image = ImageTk.PhotoImage(image)
            self.preview_label.config(image=self.preview_image, text='')
        except Exception as e:
            print(f"Display error: {e}")

    # Playback controls
    def _on_play_pause(self):
        if self.is_playing:
            self._pause()
        else:
            self._play()

    def _get_audible_tracks(self) -> list:
        tracks = list(self.timeline.tracks)
        soloed = [t for t in tracks if t.get('solo') and not t.get('muted')]
        if soloed:
            return soloed
        return [t for t in tracks if not t.get('muted')]

    def _play(self):
        """Start playback."""
        self.is_playing = True
        self.play_btn.config(text="⏸", bg='#fb923c')
        self.status_label.config(text="Playing...")

        # Collect all audio clips from all tracks
        all_clips = []
        for track in self._get_audible_tracks():
            for clip in track.get('clips', []):
                if clip.get('loading'):
                    continue
                all_clips.append(clip)

        # Set clips and start playback
        self.audio_engine.set_clips(all_clips)
        self.audio_engine.play(start_time=self.playhead_position)

        if not self.audio_engine.is_active():
            self.is_playing = False
            self.play_btn.config(text="▶", bg='#4ade80')
            self.status_label.config(text="Audio output unavailable")
            return

        self._playback_tick()

    def _get_clips_at_time(self, time: float) -> list:
        """Get all clips that are active at the given time."""
        clips = []
        for track in self._get_audible_tracks():
            for clip in track.get('clips', []):
                if clip.get('loading'):
                    continue
                if clip['start'] <= time < clip['start'] + clip['duration']:
                    clip_with_type = clip.copy()
                    clip_with_type['type'] = track['type']
                    clips.append(clip_with_type)
        return clips

    def _pause(self):
        self.is_playing = False
        self.audio_engine.pause()
        self.play_btn.config(text="▶", bg='#4ade80')
        self.status_label.config(text="Paused")
        if self.playback_job:
            self.root.after_cancel(self.playback_job)
            self.playback_job = None

    def _on_stop(self):
        self.is_playing = False
        self.audio_engine.stop()  # Stops and resets position to 0
        self.play_btn.config(text="▶", bg='#4ade80')
        if self.playback_job:
            self.root.after_cancel(self.playback_job)
            self.playback_job = None
        self._seek_to(0)
        self.status_label.config(text="Stopped")

    def _on_skip_back(self):
        self._seek_to(self.playhead_position - 5)

    def _on_skip_forward(self):
        self._seek_to(self.playhead_position + 5)

    def _playback_tick(self):
        if self.is_playing:
            # Sync playhead position with audio engine
            self.playhead_position = self.audio_engine.get_position_for_ui()

            if self.playhead_position >= self.project_duration:
                self.playhead_position = self.project_duration
                self._pause()
            else:
                self.timeline.set_playhead(self.playhead_position)
                self._update_time_display()
                self._update_preview_for_time(self.playhead_position)

                self.playback_job = self.root.after(33, self._playback_tick)

    # Zoom controls
    def _on_zoom_change(self, value):
        zoom = int(float(value))
        self.timeline.set_zoom(zoom)
        self.zoom_label.config(text=f"{zoom}%")

    def _on_zoom_in(self):
        new_val = min(300, self.zoom_scale.get() + 20)
        self.zoom_scale.set(new_val)
        self._on_zoom_change(new_val)

    def _on_zoom_out(self):
        new_val = max(10, self.zoom_scale.get() - 20)
        self.zoom_scale.set(new_val)
        self._on_zoom_change(new_val)

    def _on_zoom_fit(self):
        self.zoom_scale.set(100)
        self._on_zoom_change(100)

    # Menu actions
    def _on_new(self):
        self._on_stop()
        # Clear all loaded audio from memory
        self.audio_engine.loaded_audio.clear()
        self.timeline._waveform_cache.clear()
        for track in self.timeline.tracks:
            track['clips'] = []
        self.timeline._draw()
        self.preview_label.config(image='', text="Video Preview\n\nLoad a video to see preview")
        self.preview_image = None
        self.status_label.config(text="New project created")

    def _on_open(self):
        filepath = filedialog.askopenfilename(
            title="Open Project",
            filetypes=[("WaveSync Projects", "*.wavesync"), ("All Files", "*.*")]
        )
        if filepath:
            self.status_label.config(text=f"Opened: {os.path.basename(filepath)}")

    def _on_save(self):
        self.status_label.config(text="Project saved")

    def _on_import(self):
        filepath = filedialog.askopenfilename(
            title="Import Media",
            filetypes=[
                ("Media Files", "*.mp4 *.mov *.avi *.mkv *.mp3 *.wav *.aac *.flac"),
                ("Video Files", "*.mp4 *.mov *.avi *.mkv"),
                ("Audio Files", "*.mp3 *.wav *.aac *.flac"),
                ("All Files", "*.*")
            ]
        )
        if filepath:
            self.status_label.config(text=f"Imported: {os.path.basename(filepath)}")

    def _on_track_add_media(self, track_idx: int, track: dict):
        """Handle adding media to a specific track."""
        # Set filetypes based on track type
        if track['type'] == 'video':
            filetypes = [
                ("Video Files", "*.mp4 *.mov *.avi *.mkv *.webm"),
                ("All Files", "*.*")
            ]
            title = f"Add Video to {track['name']}"
        else:
            filetypes = [
                ("Audio Files", "*.mp3 *.wav *.aac *.flac *.ogg *.m4a"),
                ("All Files", "*.*")
            ]
            title = f"Add Audio to {track['name']}"

        filepath = filedialog.askopenfilename(title=title, filetypes=filetypes)
        if filepath:
            filename = os.path.basename(filepath)

            # Calculate where to place the clip (do this first before async load)
            if track['clips']:
                last_clip = track['clips'][-1]
                start_time = last_clip['start'] + last_clip['duration']
            else:
                start_time = self.playhead_position

            # Add placeholder clip immediately (shows "Loading...")
            clip = {
                'name': f"Loading {filename}...",
                'path': filepath,
                'start': start_time,
                'duration': 10.0,  # Placeholder duration
                'source_start': 0.0,
                'media_duration': None,
                'fade_in': 0.0,
                'fade_out': 0.0,
                'fade_in_curve': 0.0,
                'fade_out_curve': 0.0,
                'loading': True,
            }
            track['clips'].append(clip)
            self.timeline._draw()
            self.status_label.config(text=f"Loading {filename}...")

            # Load audio asynchronously
            def on_audio_loaded(loaded):
                # Update clip on main thread
                self.root.after(0, lambda: self._finish_add_media(track, clip, loaded, filename))

            self.audio_engine.load_audio(filepath, callback=on_audio_loaded)

    def _finish_add_media(self, track: dict, clip: dict, loaded, filename: str):
        """Finish adding media after async load completes."""
        if loaded:
            duration = loaded.duration
            clip['name'] = filename
            clip['duration'] = duration
            clip['source_start'] = float(clip.get('source_start', 0.0))
            clip['media_duration'] = float(duration)
            clip['fade_in'] = float(clip.get('fade_in', 0.0))
            clip['fade_out'] = float(clip.get('fade_out', 0.0))
            clip['fade_in_curve'] = float(clip.get('fade_in_curve', 0.0))
            clip['fade_out_curve'] = float(clip.get('fade_out_curve', 0.0))
            clip['loading'] = False

            # Update project duration if needed
            end_time = clip['start'] + duration
            if end_time > self.project_duration:
                self.project_duration = end_time + 10
                self.timeline.duration = self.project_duration

            self.timeline._waveform_cache.clear()
            self.timeline._draw()
            self._update_time_display()

            # Show preview if it's a video
            if track['type'] == 'video' and MediaInfo.has_video(clip['path']):
                self._show_video_frame(clip['path'], 0)

            self.status_label.config(text=f"Loaded {filename} ({duration:.1f}s) to {track['name']}")
        else:
            # Loading failed - remove placeholder clip
            if clip in track['clips']:
                track['clips'].remove(clip)
            self.timeline._draw()
            self.status_label.config(text=f"Failed to load {filename}")

    def _on_export(self):
        filepath = filedialog.asksaveasfilename(
            title="Export",
            defaultextension=".wav",
            filetypes=[("MP4 Video", "*.mp4"), ("WAV Audio", "*.wav"), ("All Files", "*.*")]
        )
        if not filepath:
            return

        root, ext = os.path.splitext(filepath)
        ext = ext.lower()
        if not ext:
            filepath = filepath + ".wav"
            ext = ".wav"

        if ext != ".wav":
            messagebox.showinfo("Export", "Only WAV export is currently supported.")
            return

        self._export_wav(filepath)

    def _export_wav(self, filepath: str):
        self.status_label.config(text=f"Exporting WAV: {os.path.basename(filepath)}")
        threading.Thread(target=self._export_wav_worker, args=(filepath,), daemon=True).start()

    def _export_wav_worker(self, filepath: str):
        try:
            sample_rate = int(self.audio_engine.sample_rate)
            channels = int(self.audio_engine.channels)

            clips = []
            for track in self._get_audible_tracks():
                for clip in track.get('clips', []):
                    if clip.get('loading'):
                        continue
                    if clip.get('path'):
                        clips.append(clip)

            if not clips:
                self.root.after(0, lambda: messagebox.showinfo("Export", "No clips to export."))
                self.root.after(0, lambda: self.status_label.config(text="Export canceled (no clips)"))
                return

            clip_specs = []
            end_time = 0.0
            for clip in clips:
                path = clip.get('path')
                if not path:
                    continue

                loaded = self.audio_engine.loaded_audio.get(path)
                if not loaded:
                    loaded = self.audio_engine.load_audio(path)
                if not loaded:
                    continue

                start = float(clip.get('start', 0.0))
                duration = float(clip.get('duration', 0.0))
                source_start = float(clip.get('source_start', 0.0))
                fade_in = float(clip.get('fade_in', 0.0))
                fade_out = float(clip.get('fade_out', 0.0))
                fade_in_curve = float(clip.get('fade_in_curve', 0.0))
                fade_out_curve = float(clip.get('fade_out_curve', 0.0))

                if duration <= 0:
                    continue

                fade_in = max(0.0, min(fade_in, duration))
                fade_out = max(0.0, min(fade_out, duration))

                end_time = max(end_time, start + duration)

                duration_frames = int(round(duration * sample_rate))
                clip_specs.append({
                    'audio': loaded,
                    'start_frame': int(round(start * sample_rate)),
                    'duration_frames': duration_frames,
                    'source_start_frame': int(round(source_start * sample_rate)),
                    'fade_in_frames': int(round(fade_in * sample_rate)),
                    'fade_out_frames': int(round(fade_out * sample_rate)),
                    'fade_in_curve': fade_in_curve,
                    'fade_out_curve': fade_out_curve,
                })

            if not clip_specs or end_time <= 0:
                self.root.after(0, lambda: messagebox.showinfo("Export", "No audio data to export."))
                self.root.after(0, lambda: self.status_label.config(text="Export canceled (no audio)"))
                return

            total_frames = int(math.ceil(end_time * sample_rate))
            block_size = 8192

            def set_status(text: str):
                self.root.after(0, lambda t=text: self.status_label.config(text=t))

            with wave.open(filepath, 'wb') as wf:
                wf.setnchannels(channels)
                wf.setsampwidth(2)  # int16 PCM
                wf.setframerate(sample_rate)

                last_reported = -1
                for block_start in range(0, total_frames, block_size):
                    frames = min(block_size, total_frames - block_start)
                    block_end = block_start + frames

                    mixed = np.zeros((frames, channels), dtype=np.float32)

                    for spec in clip_specs:
                        clip_start = spec['start_frame']
                        clip_end = clip_start + spec['duration_frames']

                        overlap_start = max(block_start, clip_start)
                        overlap_end = min(block_end, clip_end)
                        if overlap_end <= overlap_start:
                            continue

                        out_offset = overlap_start - block_start
                        frames_to_mix = overlap_end - overlap_start
                        clip_offset = overlap_start - clip_start

                        src_frame = spec['source_start_frame'] + clip_offset
                        samples = spec['audio'].get_samples_by_frame(src_frame, frames_to_mix)

                        fade_in_frames = int(spec.get('fade_in_frames', 0) or 0)
                        fade_out_frames = int(spec.get('fade_out_frames', 0) or 0)
                        duration_frames = int(spec.get('duration_frames', 0) or 0)
                        if duration_frames > 0 and (fade_in_frames > 0 or fade_out_frames > 0):
                            positions = clip_offset + np.arange(frames_to_mix, dtype=np.float32)
                            gains = np.ones(frames_to_mix, dtype=np.float32)

                            if fade_in_frames > 0:
                                t_in = np.clip(positions / fade_in_frames, 0.0, 1.0)
                                gains = np.minimum(gains, AudioEngine._apply_fade_curve(t_in, spec.get('fade_in_curve', 0.0)))
                            if fade_out_frames > 0:
                                remaining = float(duration_frames) - positions
                                t_out = np.clip(remaining / fade_out_frames, 0.0, 1.0)
                                gains = np.minimum(gains, AudioEngine._apply_fade_curve(t_out, spec.get('fade_out_curve', 0.0)))

                            samples = samples * gains[:, None]

                        mixed[out_offset:out_offset + frames_to_mix] += samples

                    np.clip(mixed, -1.0, 1.0, out=mixed)
                    pcm = (mixed * 32767.0).astype(np.int16)
                    wf.writeframes(pcm.tobytes())

                    percent = int((block_start / max(1, total_frames)) * 100)
                    if percent != last_reported and percent % 10 == 0:
                        last_reported = percent
                        set_status(f"Exporting WAV... {percent}%")

            set_status(f"Exported WAV: {os.path.basename(filepath)}")
            self.root.after(0, lambda: messagebox.showinfo("Export", f"WAV exported to:\n{filepath}"))

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Export Failed", str(e)))
            self.root.after(0, lambda: self.status_label.config(text="Export failed"))

    def _on_split(self):
        self.status_label.config(text=f"Split at {self.playhead_position:.2f}s")

    def _on_add_video_track(self):
        num = len([t for t in self.timeline.tracks if t['type'] == 'video']) + 1
        self.timeline.tracks.append({
            'name': f'V{num}', 'type': 'video', 'color': '#a78bfa', 'muted': False, 'solo': False, 'clips': []
        })
        self.timeline._draw()
        self.status_label.config(text=f"Added video track V{num}")

    def _on_add_audio_track(self):
        num = len([t for t in self.timeline.tracks if t['type'] == 'audio']) + 1
        self.timeline.tracks.append({
            'name': f'A{num}', 'type': 'audio', 'color': '#4ade80', 'muted': False, 'solo': False, 'clips': []
        })
        self.timeline._draw()
        self.status_label.config(text=f"Added audio track A{num}")

    def _on_shortcuts(self):
        messagebox.showinfo("Keyboard Shortcuts", """
PLAYBACK:
  Space - Play/Pause
  Escape - Stop
  ← / → - Skip 5 seconds
  Home / End - Go to start/end

EDITING:
  S - Split at playhead
  Ctrl+I - Import media
  Ctrl+S - Save project
  Ctrl+O - Open project
  Ctrl+N - New project

VIEW:
  Ctrl++ / Ctrl+- - Zoom in/out
  Ctrl+0 - Zoom to fit
        """)

    def _on_about(self):
        messagebox.showinfo("About WaveSync",
            "WaveSync\nAudio/Video Editor v0.1\n\nBuilt with Python, Tkinter, and FFmpeg")

    def run(self):
        self.root.mainloop()


def run():
    app = WaveSyncApp()
    app.run()
