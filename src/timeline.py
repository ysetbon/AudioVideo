"""Timeline canvas widget for displaying tracks and clips."""
import math
import tkinter as tk
from typing import Optional, Callable, Dict, TYPE_CHECKING

from .theme import Theme

if TYPE_CHECKING:
    from .audio_engine import AudioEngine


class TimelineCanvas(tk.Canvas):
    """Timeline canvas with tracks and playhead."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=Theme.BG_MAIN, highlightthickness=0, **kwargs)

        self.pixels_per_second = 100
        self.duration = 180  # 3 minutes
        self.playhead_position = 0.0
        self.tracks = []

        self.on_playhead_change: Optional[Callable] = None
        self.on_track_add_media: Optional[Callable] = None
        self.on_clip_select: Optional[Callable] = None
        self.on_timeline_edited: Optional[Callable[[], None]] = None
        self.on_zoom_request: Optional[Callable[[int], None]] = None  # delta: positive=zoom in, negative=zoom out
        self.on_scroll_update: Optional[Callable[[float, float], None]] = None  # (scroll_percent, visible_percent)

        # Horizontal scroll offset (in pixels)
        self.scroll_offset = 0

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
        self.audio_engine: Optional['AudioEngine'] = None

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
        # Mouse wheel zoom (Windows and Linux)
        self.bind('<MouseWheel>', self._on_mousewheel)
        self.bind('<Button-4>', self._on_mousewheel_linux)  # Linux scroll up
        self.bind('<Button-5>', self._on_mousewheel_linux)  # Linux scroll down

        self._draw()

    def _create_default_tracks(self):
        self.tracks = [
            {'name': 'V1', 'type': 'video', 'color': Theme.TRACK_VIDEO, 'muted': False, 'solo': False, 'clips': []},
            {'name': 'A1', 'type': 'audio', 'color': Theme.TRACK_AUDIO_1, 'muted': False, 'solo': False, 'clips': []},
            {'name': 'A2', 'type': 'audio', 'color': Theme.TRACK_AUDIO_2, 'muted': False, 'solo': False, 'clips': []},
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
            time = (event.x - self.header_width + self.scroll_offset) / self.pixels_per_second
            self.set_playhead(time)
            if self.on_playhead_change:
                self.on_playhead_change(self.playhead_position)
            self._drag_playhead = True

    def _on_drag(self, event):
        if self._drag_state:
            self._apply_drag(event.x, event.y)
            return

        if self._drag_playhead and event.x > self.header_width:
            time = max(0, min(self.duration, (event.x - self.header_width + self.scroll_offset) / self.pixels_per_second))
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
        self._clamp_scroll_offset()
        self._draw()
        self._notify_scroll_update()

    def _on_mousewheel(self, event):
        """Handle mouse wheel zoom (Windows/macOS)."""
        if self.on_zoom_request:
            # event.delta is positive for scroll up (zoom in), negative for scroll down (zoom out)
            # On Windows, delta is typically 120 per notch
            delta = 1 if event.delta > 0 else -1
            self.on_zoom_request(delta)

    def _on_mousewheel_linux(self, event):
        """Handle mouse wheel zoom (Linux)."""
        if self.on_zoom_request:
            # Button-4 is scroll up (zoom in), Button-5 is scroll down (zoom out)
            delta = 1 if event.num == 4 else -1
            self.on_zoom_request(delta)

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
        x1 = self.header_width + float(clip['start']) * self.pixels_per_second - self.scroll_offset
        x2 = self.header_width + float(clip['start'] + clip['duration']) * self.pixels_per_second - self.scroll_offset
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
            new_start = (float(x) - self.header_width + self.scroll_offset - float(state['grab_offset_x'])) / self.pixels_per_second
            clip['start'] = max(0.0, new_start)

        elif mode == 'trim_start':
            original_start = float(state['start_time'])
            original_duration = float(state['duration'])
            original_source_start = float(state['source_start'])
            original_source_end = original_source_start + original_duration
            original_end = original_start + original_duration

            earliest_start = max(0.0, original_start - original_source_start)
            latest_start = max(0.0, original_end - self._min_clip_duration)

            proposed_start = (float(x) - self.header_width + self.scroll_offset) / self.pixels_per_second
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

            proposed_end = (float(x) - self.header_width + self.scroll_offset) / self.pixels_per_second
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
            start_x = self.header_width + (clip_start * self.pixels_per_second) - self.scroll_offset
            new_fade = (float(x) - float(start_x)) / self.pixels_per_second
            clip['fade_in'] = max(0.0, min(float(new_fade), float(clip_duration)))
            if state.get('curve_target') == 'fade_in_curve' and state.get('curve_start') is not None:
                dy = float(y) - float(state.get('mouse_y_start', y))
                curve = float(state['curve_start']) - (dy / 10.0)
                clip['fade_in_curve'] = max(-5.0, min(5.0, curve))

        elif mode == 'fade_out':
            clip_start = float(clip.get('start', 0.0))
            clip_duration = float(clip.get('duration', 0.0))
            end_x = self.header_width + ((clip_start + clip_duration) * self.pixels_per_second) - self.scroll_offset
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
        self.pixels_per_second = max(5, min(1000, pixels_per_second))
        self._waveform_cache.clear()  # Clear cache as clip widths change
        self._clamp_scroll_offset()
        self._draw()
        self._notify_scroll_update()

    def set_scroll_offset(self, percent: float):
        """Set scroll offset as percentage (0.0 to 1.0) of scrollable area."""
        total_width = self.duration * self.pixels_per_second
        visible_width = self.winfo_width() - self.header_width
        max_scroll = max(0, total_width - visible_width)
        self.scroll_offset = int(percent * max_scroll)
        self._draw()

    def _clamp_scroll_offset(self):
        """Ensure scroll offset is within valid bounds."""
        total_width = self.duration * self.pixels_per_second
        visible_width = max(1, self.winfo_width() - self.header_width)
        max_scroll = max(0, total_width - visible_width)
        self.scroll_offset = max(0, min(self.scroll_offset, int(max_scroll)))

    def _notify_scroll_update(self):
        """Notify callback about scroll state."""
        if self.on_scroll_update:
            total_width = self.duration * self.pixels_per_second
            visible_width = max(1, self.winfo_width() - self.header_width)
            max_scroll = max(1, total_width - visible_width)
            scroll_percent = self.scroll_offset / max_scroll if max_scroll > 0 else 0
            visible_percent = min(1.0, visible_width / max(1, total_width))
            self.on_scroll_update(scroll_percent, visible_percent)

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
        self.create_rectangle(0, 0, width, self.ruler_height, fill=Theme.BG_PANEL, outline='')
        self.create_rectangle(0, 0, self.header_width, self.ruler_height, fill=Theme.BG_PANEL, outline='')

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
        self.create_line(self.header_width, 0, self.header_width, height, fill=Theme.BORDER)
        self.create_line(0, self.ruler_height, width, self.ruler_height, fill=Theme.BORDER)

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

        # Calculate the starting time based on scroll offset
        start_time = (self.scroll_offset / self.pixels_per_second)
        # Round down to nearest minor tick
        start_time = (start_time // minor) * minor

        t = start_time
        while t <= self.duration:
            x = self.header_width + int(t * self.pixels_per_second) - self.scroll_offset
            if x > width:
                break
            if x < self.header_width:
                t += minor
                continue

            is_major = abs(t % major) < 0.01 or t == 0

            if is_major:
                self.create_line(x, 15, x, self.ruler_height, fill=Theme.FG_SECONDARY)
                minutes = int(t // 60)
                seconds = int(t % 60)
                self.create_text(x + 4, 8, text=f"{minutes}:{seconds:02d}",
                               anchor='w', fill=Theme.FG_SECONDARY, font=('Segoe UI', 9))
            else:
                self.create_line(x, 22, x, self.ruler_height, fill=Theme.FG_DISABLED)

            t += minor

    def _draw_track(self, track, y, width, track_idx):
        # Track header
        self.create_rectangle(0, y, self.header_width, y + self.track_height,
                            fill=Theme.BG_PANEL, outline='')

        # Color indicator
        self.create_rectangle(0, y, 4, y + self.track_height, fill=track['color'], outline='')

        # Track name
        self.create_text(12, y + 12, text=track['name'], anchor='w',
                        fill=Theme.FG_HIGHLIGHT, font=('Segoe UI', 11, 'bold'))
        self.create_text(12, y + 30, text=track['type'].capitalize(), anchor='w',
                        fill=Theme.FG_SECONDARY, font=('Segoe UI', 9))

        # M/S buttons
        m_color = Theme.ERROR if track['muted'] else Theme.BG_INPUT
        s_color = Theme.WARNING if track['solo'] else Theme.BG_INPUT

        self.create_rectangle(12, y + 50, 36, y + 70, fill=m_color, outline=Theme.BORDER)
        self.create_text(24, y + 60, text='M', fill=Theme.FG_HIGHLIGHT, font=('Segoe UI', 9, 'bold'))

        self.create_rectangle(42, y + 50, 66, y + 70, fill=s_color, outline=Theme.BORDER)
        self.create_text(54, y + 60, text='S', fill=Theme.FG_HIGHLIGHT, font=('Segoe UI', 9, 'bold'))

        # Add media button (+)
        btn_x1, btn_y1 = 100, y + 50
        btn_x2, btn_y2 = 140, y + 70
        self.create_rectangle(btn_x1, btn_y1, btn_x2, btn_y2, fill=Theme.SUCCESS, outline=Theme.BORDER)
        self.create_text((btn_x1 + btn_x2) // 2, (btn_y1 + btn_y2) // 2, text='+',
                        fill=Theme.BG_MAIN, font=('Segoe UI', 14, 'bold'))
        self._add_buttons[track_idx] = (btn_x1, btn_y1, btn_x2, btn_y2)

        # Track content area
        self.create_rectangle(self.header_width, y, width, y + self.track_height,
                            fill=Theme.BG_MAIN, outline='')

        # Grid lines
        major = 5 if self.pixels_per_second < 50 else 1
        start_time = (self.scroll_offset / self.pixels_per_second)
        start_time = (start_time // major) * major
        t = start_time
        while t <= self.duration:
            x = self.header_width + int(t * self.pixels_per_second) - self.scroll_offset
            if x > width:
                break
            if x >= self.header_width:
                self.create_line(x, y, x, y + self.track_height, fill=Theme.BG_HOVER)
            t += major

        # Draw clips if any
        for clip in track.get('clips', []):
            self._draw_clip(clip, track, y, width)

        # Bottom border
        self.create_line(0, y + self.track_height - 1, width, y + self.track_height - 1, fill=Theme.BORDER)

        # "Drop media" hint (only if no clips)
        if not track.get('clips'):
            center_x = self.header_width + (width - self.header_width) // 2
            center_y = y + self.track_height // 2
            self.create_text(center_x, center_y, text="Click + to add media",
                            fill=Theme.FG_DISABLED, font=('Segoe UI', 10))

    def _draw_clip(self, clip, track, y, width):
        """Draw a media clip on the track with waveform."""
        start_x = self.header_width + int(clip['start'] * self.pixels_per_second) - self.scroll_offset
        end_x = self.header_width + int((clip['start'] + clip['duration']) * self.pixels_per_second) - self.scroll_offset

        # Skip drawing if clip is completely outside visible area
        if end_x < self.header_width or start_x > width:
            return
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
            bg_color = Theme.BG_INPUT  # Gray for loading
            outline_color = Theme.FG_DISABLED
            outline_width = 1
        else:
            bg_color = self._darken_color(track['color'], 0.3)
            outline_color = Theme.FG_HIGHLIGHT if is_selected else track['color']
            outline_width = 2 if is_selected else 1

        self.create_rectangle(start_x + 1, clip_y1, end_x - 1, clip_y2,
                            fill=bg_color, outline=outline_color, width=outline_width)

        if is_selected and not is_loading and clip_width >= 12:
            self.create_line(start_x + 2, clip_y1, start_x + 2, clip_y2, fill=Theme.FG_HIGHLIGHT)
            self.create_line(end_x - 2, clip_y1, end_x - 2, clip_y2, fill=Theme.FG_HIGHLIGHT)

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
                        y_pt = int(line_bottom - g * line_height)
                        points.extend([x, y_pt])
                    if len(points) >= 4:
                        self.create_line(points, fill=Theme.PLAYHEAD, width=1, smooth=True)

                    if is_selected and fade_px >= (curve_r * 4):
                        mid_x = start_x + (fade_px / 2)
                        mid_g = self._curve_gain(0.5, curve)
                        mid_y = int(line_bottom - mid_g * line_height)
                        self.create_oval(mid_x - curve_r, mid_y - curve_r, mid_x + curve_r, mid_y + curve_r,
                                         fill=Theme.PLAYHEAD, outline='')
                self.create_oval(fade_in_x - r, handle_y - r, fade_in_x + r, handle_y + r,
                                 fill=Theme.FG_HIGHLIGHT, outline='')

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
                        y_pt = int(line_bottom - g * line_height)
                        points.extend([x, y_pt])
                    if len(points) >= 4:
                        self.create_line(points, fill=Theme.PLAYHEAD, width=1, smooth=True)

                    if is_selected and fade_px >= (curve_r * 4):
                        mid_x = fade_out_x + (fade_px / 2)
                        mid_g = self._curve_gain(0.5, curve)
                        mid_y = int(line_bottom - mid_g * line_height)
                        self.create_oval(mid_x - curve_r, mid_y - curve_r, mid_x + curve_r, mid_y + curve_r,
                                         fill=Theme.PLAYHEAD, outline='')
                self.create_oval(fade_out_x - r, handle_y - r, fade_out_x + r, handle_y + r,
                                 fill=Theme.FG_HIGHLIGHT, outline='')

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
                            fill=Theme.FG_SECONDARY, font=('Segoe UI', 10, 'italic'))
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

        x = self.header_width + int(round(self.playhead_position * self.pixels_per_second)) - self.scroll_offset
        if self._playhead_line_id is None:
            self._playhead_line_id = self.create_line(
                x, 0, x, height,
                fill=Theme.PLAYHEAD,
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
                fill=Theme.PLAYHEAD,
                outline='',
                tags=('playhead',),
            )
        else:
            try:
                self.coords(self._playhead_handle_id, x - 8, 0, x + 8, 0, x, 12)
            except Exception:
                self._playhead_handle_id = None

        self.tag_raise('playhead')
