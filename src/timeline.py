"""Timeline canvas widget for displaying tracks and clips."""
import math
import tkinter as tk
from typing import Optional, Callable, Dict, TYPE_CHECKING

from .theme import Theme
from .ui_components import draw_add_button

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
        self.on_add_video_track: Optional[Callable[[], None]] = None
        self.on_add_audio_track: Optional[Callable[[], None]] = None

        # Horizontal scroll offset (in pixels)
        self.scroll_offset = 0

        # Playhead rendering (avoid full redraw on scrubbing)
        self._playhead_line_id: Optional[int] = None
        self._playhead_handle_id: Optional[int] = None
        self._drag_playhead = False

        # Play start marker (dashed line showing where play started)
        self.play_start_position: Optional[float] = None  # None when not playing

        # Track configuration
        self.track_height = 80  # default track height (px)
        self.min_track_height = 80
        self.max_track_height = 260
        self.header_width = 150
        self.ruler_height = 30
        self._track_resize_grab_px = 5
        self._track_layout: list[tuple[int, int]] = []  # (y1, y2) per track

        # Button hit areas (track_index -> (x1, y1, x2, y2))
        self._add_buttons = {}
        self._hovered_add_button: Optional[int] = None

        # Clip thumbnails cache
        self._thumbnails = {}

        # Waveform cache: (filepath, width) -> waveform data
        self._waveform_cache: Dict[tuple, list] = {}

        # Reference to audio engine (set by app)
        self.audio_engine: Optional['AudioEngine'] = None

        # Selection / editing state
        self.selected_clip: Optional[dict] = None
        self._drag_state: Optional[dict] = None
        self._hover_clip: Optional[dict] = None
        self._hover_part: Optional[str] = None

        # Track reorder state
        self._track_drag_insert_idx: Optional[int] = None

        self._clip_edge_px = 8
        self._min_clip_duration = 0.05  # seconds
        self._fade_handle_radius = 5
        self._fade_handle_y_offset = 14

        # Create default tracks
        self._create_default_tracks()

        # Bindings
        self.bind('<Button-1>', self._on_click)
        self.bind('<Double-Button-1>', self._on_double_click)
        self.bind('<B1-Motion>', self._on_drag)
        self.bind('<ButtonRelease-1>', self._on_release)
        self.bind('<Configure>', self._on_resize)
        self.bind('<Motion>', self._on_motion)
        self.bind('<Leave>', self._on_leave)
        # Mouse wheel zoom (Windows and Linux)
        self.bind('<MouseWheel>', self._on_mousewheel)
        self.bind('<Button-4>', self._on_mousewheel_linux)  # Linux scroll up
        self.bind('<Button-5>', self._on_mousewheel_linux)  # Linux scroll down
        # Right-click context menu for track panel
        self.bind('<Button-3>', self._on_right_click)

        self._draw()

    def _set_hover_target(self, clip: Optional[dict], part: Optional[str]):
        if clip is self._hover_clip and part == self._hover_part:
            return
        self._hover_clip = clip
        self._hover_part = part
        self._draw()

    def _on_leave(self, event):
        if self._drag_state:
            return
        if self._hovered_add_button is not None:
            self._hovered_add_button = None
            self._draw()
        self._set_hover_target(None, None)
        self.config(cursor='')

    def _create_default_tracks(self):
        self.tracks = [
            {'name': 'V1', 'type': 'video', 'color': Theme.TRACK_VIDEO, 'muted': False, 'solo': False, 'clips': [], 'height': self.track_height},
            {'name': 'A1', 'type': 'audio', 'color': Theme.TRACK_AUDIO_1, 'muted': False, 'solo': False, 'clips': [], 'height': self.track_height},
            {'name': 'A2', 'type': 'audio', 'color': Theme.TRACK_AUDIO_2, 'muted': False, 'solo': False, 'clips': [], 'height': self.track_height},
        ]
        self._recompute_track_layout()

    def _normalize_track_height(self, value) -> int:
        try:
            height = int(round(float(value)))
        except Exception:
            height = int(self.track_height)
        return max(int(self.min_track_height), min(int(self.max_track_height), int(height)))

    def _ensure_track_heights(self):
        for track in self.tracks:
            if 'height' not in track:
                track['height'] = self.track_height
            track['height'] = self._normalize_track_height(track.get('height'))

    def _recompute_track_layout(self):
        self._ensure_track_heights()
        y = int(self.ruler_height)
        layout: list[tuple[int, int]] = []
        for track in self.tracks:
            h = self._normalize_track_height(track.get('height'))
            layout.append((y, y + h))
            y += h
        self._track_layout = layout

    def _track_bounds(self, track_idx: int) -> Optional[tuple[int, int]]:
        if len(self._track_layout) != len(self.tracks):
            self._recompute_track_layout()
        if 0 <= track_idx < len(self._track_layout):
            return self._track_layout[track_idx]
        return None

    def _hit_test_track_resize(self, x: int, y: int) -> Optional[int]:
        if x > self.header_width:
            return None
        if len(self._track_layout) != len(self.tracks):
            self._recompute_track_layout()
        grab = int(self._track_resize_grab_px)
        for idx, (_y1, y2) in enumerate(self._track_layout):
            if abs(int(y) - int(y2)) <= grab:
                return idx
        return None

    def _on_click(self, event):
        self._drag_playhead = False

        # Track height resize (drag the bottom edge of a track header)
        resize_idx = self._hit_test_track_resize(event.x, event.y)
        if resize_idx is not None:
            bounds = self._track_bounds(resize_idx)
            if bounds:
                track = self.tracks[resize_idx]
                self._drag_state = {
                    'mode': 'resize_track',
                    'track_idx': resize_idx,
                    'start_y': int(event.y),
                    'start_height': self._normalize_track_height(track.get('height', self.track_height)),
                }
                self.config(cursor='sb_v_double_arrow')
                return

        # Check if click is on an add button
        for track_idx, (x1, y1, x2, y2) in self._add_buttons.items():
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                if self.on_track_add_media:
                    self.on_track_add_media(track_idx, self.tracks[track_idx])
                return

        # Track M/S buttons and track label drag
        track_idx = self._track_index_at_y(event.y)
        if track_idx is not None and event.x < self.header_width:
            bounds = self._track_bounds(track_idx)
            if not bounds:
                return
            track_y1, _track_y2 = bounds
            if 12 <= event.x <= 36 and (track_y1 + 50) <= event.y <= (track_y1 + 70):
                self.tracks[track_idx]['muted'] = not self.tracks[track_idx].get('muted', False)
                self._draw()
                if self.on_timeline_edited:
                    self.on_timeline_edited()
                return
            if 42 <= event.x <= 66 and (track_y1 + 50) <= event.y <= (track_y1 + 70):
                self.tracks[track_idx]['solo'] = not self.tracks[track_idx].get('solo', False)
                self._draw()
                if self.on_timeline_edited:
                    self.on_timeline_edited()
                return

            # Click on track label area (upper part, above buttons) - start track reorder drag
            if event.y < (track_y1 + 45):
                self._drag_state = {
                    'mode': 'reorder_track',
                    'track_idx': track_idx,
                    'start_y': event.y,
                }
                self._track_drag_insert_idx = track_idx
                self.config(cursor='fleur')
                self._draw()
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

    def _on_double_click(self, event):
        resize_idx = self._hit_test_track_resize(event.x, event.y)
        if resize_idx is None:
            return
        if 0 <= resize_idx < len(self.tracks):
            self.tracks[resize_idx]['height'] = self.track_height
            self._drag_state = None
            self._draw()

    def _on_drag(self, event):
        if self._drag_state:
            if self._drag_state.get('mode') == 'resize_track':
                self._apply_track_resize(event.y)
            elif self._drag_state.get('mode') == 'reorder_track':
                self._apply_track_reorder(event.y)
            else:
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
        if self._drag_state.get('mode') == 'resize_track':
            self._drag_state = None
            self._recompute_track_layout()
            self._draw()
            return
        if self._drag_state.get('mode') == 'reorder_track':
            self._finalize_track_reorder()
            self._drag_state = None
            self._track_drag_insert_idx = None
            self.config(cursor='')
            self._recompute_track_layout()
            self._draw()
            if self.on_timeline_edited:
                self.on_timeline_edited()
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

    def _on_right_click(self, event):
        """Handle right-click for context menu in track labels panel."""
        # Only show menu if clicking in the track labels area (left panel)
        if event.x >= self.header_width:
            return

        # Check if clicking on an existing track's label area
        track_idx = self._track_index_at_y(event.y)
        if track_idx is not None:
            # Clicked on an existing track - could add track-specific menu later
            return

        # Clicked on empty area below tracks or in header - show add track menu
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Add Video Track", command=self._menu_add_video_track)
        menu.add_command(label="Add Audio Track", command=self._menu_add_audio_track)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _menu_add_video_track(self):
        """Handle add video track from context menu."""
        if self.on_add_video_track:
            self.on_add_video_track()

    def _menu_add_audio_track(self):
        """Handle add audio track from context menu."""
        if self.on_add_audio_track:
            self.on_add_audio_track()

    def _on_motion(self, event):
        if self._drag_state:
            return

        cursor = ''
        hover_clip = None
        hover_part = None

        resize_idx = self._hit_test_track_resize(event.x, event.y)
        if resize_idx is not None:
            self._set_hover_target(None, None)
            self.config(cursor='sb_v_double_arrow')
            return

        # Add button hover
        for track_idx, (x1, y1, x2, y2) in self._add_buttons.items():
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                if self._hovered_add_button != track_idx:
                    self._hovered_add_button = track_idx
                    self._draw()
                self._set_hover_target(None, None)
                self.config(cursor='hand2')
                return
        
        if self._hovered_add_button is not None:
            self._hovered_add_button = None
            self._draw()

        # Track M/S hover and track label drag hover
        track_idx = self._track_index_at_y(event.y)
        if track_idx is not None and event.x < self.header_width:
            bounds = self._track_bounds(track_idx)
            if not bounds:
                return
            track_y1, _track_y2 = bounds
            if ((12 <= event.x <= 36) or (42 <= event.x <= 66)) and ((track_y1 + 50) <= event.y <= (track_y1 + 70)):
                self._set_hover_target(None, None)
                self.config(cursor='hand2')
                return
            # Track label area (upper part) - show move cursor
            if event.y < (track_y1 + 45):
                self._set_hover_target(None, None)
                self.config(cursor='fleur')
                return

        # Clip hover
        hit = self._hit_test_clip(event.x, event.y)
        if hit:
            _, clip, part = hit
            if part in ('trim_start', 'trim_end', 'fade_in', 'fade_out'):
                cursor = 'sb_h_double_arrow'
            elif part in ('fade_in_curve', 'fade_out_curve'):
                cursor = 'sb_v_double_arrow'
            else:
                cursor = 'fleur'

            if part in ('fade_in', 'fade_out'):
                hover_clip = clip
                hover_part = part

        self._set_hover_target(hover_clip, hover_part)
        self.config(cursor=cursor)

    def _apply_track_resize(self, y: int):
        state = self._drag_state
        if not state or state.get('mode') != 'resize_track':
            return

        track_idx = state.get('track_idx')
        if track_idx is None or not (0 <= int(track_idx) < len(self.tracks)):
            return

        start_y = int(state.get('start_y', y))
        start_height = self._normalize_track_height(state.get('start_height', self.track_height))
        delta = int(y) - int(start_y)
        new_height = self._normalize_track_height(start_height + delta)

        track = self.tracks[int(track_idx)]
        if self._normalize_track_height(track.get('height', self.track_height)) != new_height:
            track['height'] = new_height
            self._draw()

    def _apply_track_reorder(self, y: int):
        """Update the insertion index during track reorder drag."""
        state = self._drag_state
        if not state or state.get('mode') != 'reorder_track':
            return

        # Find which track position we're hovering over
        if len(self._track_layout) != len(self.tracks):
            self._recompute_track_layout()

        # Determine insertion point based on y position
        new_insert_idx = len(self.tracks)  # Default: insert at end

        for idx, (y1, y2) in enumerate(self._track_layout):
            mid_y = (y1 + y2) // 2
            if y < mid_y:
                new_insert_idx = idx
                break

        # Handle y above all tracks
        if y < self.ruler_height:
            new_insert_idx = 0

        if new_insert_idx != self._track_drag_insert_idx:
            self._track_drag_insert_idx = new_insert_idx
            self._draw()

    def _finalize_track_reorder(self):
        """Move the dragged track to its new position."""
        state = self._drag_state
        if not state or state.get('mode') != 'reorder_track':
            return

        src_idx = state.get('track_idx')
        dst_idx = self._track_drag_insert_idx

        if src_idx is None or dst_idx is None:
            return
        if src_idx == dst_idx or src_idx == dst_idx - 1:
            # No movement needed
            return

        # Remove track from source position
        track = self.tracks.pop(src_idx)

        # Adjust destination index if source was before destination
        if src_idx < dst_idx:
            dst_idx -= 1

        # Insert at new position
        self.tracks.insert(dst_idx, track)

    def _track_index_at_y(self, y: int) -> Optional[int]:
        if y < self.ruler_height:
            return None
        if len(self._track_layout) != len(self.tracks):
            self._recompute_track_layout()
        for idx, (y1, y2) in enumerate(self._track_layout):
            if y1 <= int(y) < y2:
                return idx
        return None

    def _clip_rect(self, clip: dict, track_idx: int) -> Optional[tuple]:
        """Return (x1, y1, x2, y2) in canvas coords for a clip."""
        if 'start' not in clip or 'duration' not in clip:
            return None
        bounds = self._track_bounds(track_idx)
        if not bounds:
            return None
        track_y1, track_y2 = bounds
        padding = 4
        x1 = self.header_width + float(clip['start']) * self.pixels_per_second - self.scroll_offset
        x2 = self.header_width + float(clip['start'] + clip['duration']) * self.pixels_per_second - self.scroll_offset
        y1 = track_y1 + padding
        y2 = track_y2 - padding
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
            bounds = self._track_bounds(track_idx)
            if not bounds:
                return
            track_y1, track_y2 = bounds
            clip_y1 = track_y1 + 4
            clip_y2 = track_y2 - 4
            line_top = clip_y1 + 2
            line_bottom = clip_y2 - 2
            line_height = max(1, line_bottom - line_top)
            gain = (line_bottom - float(y)) / float(line_height)
            clip['fade_in_curve'] = self._curve_from_mid_gain(gain)

        elif mode == 'fade_out_curve':
            bounds = self._track_bounds(track_idx)
            if not bounds:
                return
            track_y1, track_y2 = bounds
            clip_y1 = track_y1 + 4
            clip_y2 = track_y2 - 4
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
        # Calculate playhead's current screen position (relative to content area)
        old_pps = self.pixels_per_second
        playhead_screen_x = self.playhead_position * old_pps - self.scroll_offset

        # Update zoom level
        self.pixels_per_second = max(5, min(1000, pixels_per_second))

        # Adjust scroll offset to keep playhead at same screen position
        new_scroll_offset = self.playhead_position * self.pixels_per_second - playhead_screen_x
        self.scroll_offset = int(new_scroll_offset)

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
        self._recompute_track_layout()
        dragging_track_idx = None
        if self._drag_state and self._drag_state.get('mode') == 'reorder_track':
            dragging_track_idx = self._drag_state.get('track_idx')

        for idx, track in enumerate(self.tracks):
            bounds = self._track_bounds(idx)
            if not bounds:
                continue
            y1, y2 = bounds
            self._draw_track(track, y1, width, idx, y2 - y1)

            # Highlight the track being dragged
            if idx == dragging_track_idx:
                self.create_rectangle(0, y1, width, y2,
                                     fill='', outline=Theme.PLAYHEAD, width=2)

        # Draw track reorder insertion indicator
        if self._drag_state and self._drag_state.get('mode') == 'reorder_track' and self._track_drag_insert_idx is not None:
            insert_y = self.ruler_height
            if self._track_drag_insert_idx < len(self._track_layout):
                insert_y = self._track_layout[self._track_drag_insert_idx][0]
            elif len(self._track_layout) > 0:
                insert_y = self._track_layout[-1][1]

            # Draw a thick colored line at the insertion point
            self.create_line(0, insert_y, width, insert_y,
                            fill=Theme.SUCCESS, width=3)
            # Draw small triangles on the sides
            self.create_polygon(0, insert_y - 6, 0, insert_y + 6, 8, insert_y,
                               fill=Theme.SUCCESS, outline='')
            self.create_polygon(width, insert_y - 6, width, insert_y + 6, width - 8, insert_y,
                               fill=Theme.SUCCESS, outline='')

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

    def _draw_track(self, track, y, width, track_idx, track_height: int):
        # Track header
        self.create_rectangle(0, y, self.header_width, y + track_height,
                            fill=Theme.BG_PANEL, outline='')

        # Color indicator
        self.create_rectangle(0, y, 4, y + track_height, fill=track['color'], outline='')

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

        # Add media button (+) - professional rounded design
        btn_x1, btn_y1 = 90, y + 50
        btn_x2, btn_y2 = 140, y + 72
        is_hovered = self._hovered_add_button == track_idx
        draw_add_button(self, btn_x1, btn_y1, btn_x2, btn_y2, hovered=is_hovered)
        self._add_buttons[track_idx] = (btn_x1, btn_y1, btn_x2, btn_y2)

        # Track content area
        self.create_rectangle(self.header_width, y, width, y + track_height,
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
                self.create_line(x, y, x, y + track_height, fill=Theme.BG_HOVER)
            t += major

        # Draw clips if any
        for clip in track.get('clips', []):
            self._draw_clip(clip, track, y, width, track_height)

        # Bottom border
        self.create_line(0, y + track_height - 1, width, y + track_height - 1, fill=Theme.BORDER)

        # "Drop media" hint (only if no clips)
        if not track.get('clips'):
            center_x = self.header_width + (width - self.header_width) // 2
            center_y = y + track_height // 2
            self.create_text(center_x, center_y, text="Click + to add media",
                            fill=Theme.FG_DISABLED, font=('Segoe UI', 10))

    def _draw_clip(self, clip, track, y, width, track_height: int):
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
        clip_y2 = y + track_height - padding
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

            is_hovered_fade = self._hover_clip is clip and self._hover_part in ('fade_in', 'fade_out')
            is_active_fade = (
                bool(self._drag_state)
                and self._drag_state.get('clip') is clip
                and self._drag_state.get('mode') in ('fade_in', 'fade_out')
            )

            if is_selected or fade_in > 0 or fade_out > 0 or is_hovered_fade or is_active_fade:
                r = self._fade_handle_radius
                handle_y = clip_y1 + self._fade_handle_y_offset
                line_top = clip_y1 + 2
                line_bottom = clip_y2 - 2
                line_height = max(1, line_bottom - line_top)
                curve_r = max(4, r - 1)  # Slightly larger control points

                fade_in_x = start_x + int(fade_in * self.pixels_per_second)
                fade_in_x = max(start_x, min(fade_in_x, end_x))
                if fade_in > 0:
                    fade_px = max(1, fade_in_x - start_x)
                    # More steps for smoother anti-aliased curve
                    steps = max(12, min(64, fade_px // 4))
                    curve = clip.get('fade_in_curve', 0.0)
                    points = []
                    for i in range(steps + 1):
                        p = i / steps
                        g = self._curve_gain(p, curve)
                        x = start_x + (p * fade_px)
                        y_pt = line_bottom - g * line_height
                        points.extend([x, y_pt])
                    if len(points) >= 4:
                        # Draw shadow for depth
                        shadow_points = [p + 1 if i % 2 == 1 else p for i, p in enumerate(points)]
                        self.create_line(shadow_points, fill='#000000', width=3, smooth=True, splinesteps=36)
                        # Main curve with thicker stroke and high spline smoothness
                        self.create_line(points, fill=Theme.PLAYHEAD, width=2, smooth=True, splinesteps=36)

                    if is_selected and fade_px >= (curve_r * 4):
                        mid_x = start_x + (fade_px / 2)
                        mid_g = self._curve_gain(0.5, curve)
                        mid_y = line_bottom - mid_g * line_height
                        # Control point with outline for better visibility
                        self.create_oval(mid_x - curve_r - 1, mid_y - curve_r - 1, mid_x + curve_r + 1, mid_y + curve_r + 1,
                                         fill='#000000', outline='')
                        self.create_oval(mid_x - curve_r, mid_y - curve_r, mid_x + curve_r, mid_y + curve_r,
                                         fill=Theme.PLAYHEAD, outline=Theme.FG_HIGHLIGHT, width=1)
                fade_in_hovered = self._hover_clip is clip and self._hover_part == 'fade_in'
                fade_in_active = bool(self._drag_state) and self._drag_state.get('clip') is clip and self._drag_state.get('mode') == 'fade_in'
                if fade_in_hovered or fade_in_active:
                    glow_r_outer = r + 6
                    glow_r_inner = r + 3
                    self.create_oval(
                        fade_in_x - glow_r_outer, handle_y - glow_r_outer, fade_in_x + glow_r_outer, handle_y + glow_r_outer,
                        outline=Theme.WARNING, width=2
                    )
                    self.create_oval(
                        fade_in_x - glow_r_inner, handle_y - glow_r_inner, fade_in_x + glow_r_inner, handle_y + glow_r_inner,
                        outline=Theme.PLAYHEAD, width=2
                    )
                fade_in_fill = Theme.WARNING if fade_in_active else Theme.FG_HIGHLIGHT
                self.create_oval(
                    fade_in_x - r, handle_y - r, fade_in_x + r, handle_y + r,
                    fill=fade_in_fill, outline=''
                )

                fade_out_x = end_x - int(fade_out * self.pixels_per_second)
                fade_out_x = max(start_x, min(fade_out_x, end_x))
                if fade_out > 0:
                    fade_px = max(1, end_x - fade_out_x)
                    # More steps for smoother anti-aliased curve
                    steps = max(12, min(64, fade_px // 4))
                    curve = clip.get('fade_out_curve', 0.0)
                    points = []
                    for i in range(steps + 1):
                        p = i / steps
                        g = self._curve_gain(1.0 - p, curve)
                        x = fade_out_x + (p * fade_px)
                        y_pt = line_bottom - g * line_height
                        points.extend([x, y_pt])
                    if len(points) >= 4:
                        # Draw shadow for depth
                        shadow_points = [p + 1 if i % 2 == 1 else p for i, p in enumerate(points)]
                        self.create_line(shadow_points, fill='#000000', width=3, smooth=True, splinesteps=36)
                        # Main curve with thicker stroke and high spline smoothness
                        self.create_line(points, fill=Theme.PLAYHEAD, width=2, smooth=True, splinesteps=36)

                    if is_selected and fade_px >= (curve_r * 4):
                        mid_x = fade_out_x + (fade_px / 2)
                        mid_g = self._curve_gain(0.5, curve)
                        mid_y = line_bottom - mid_g * line_height
                        # Control point with outline for better visibility
                        self.create_oval(mid_x - curve_r - 1, mid_y - curve_r - 1, mid_x + curve_r + 1, mid_y + curve_r + 1,
                                         fill='#000000', outline='')
                        self.create_oval(mid_x - curve_r, mid_y - curve_r, mid_x + curve_r, mid_y + curve_r,
                                         fill=Theme.PLAYHEAD, outline=Theme.FG_HIGHLIGHT, width=1)
                fade_out_hovered = self._hover_clip is clip and self._hover_part == 'fade_out'
                fade_out_active = bool(self._drag_state) and self._drag_state.get('clip') is clip and self._drag_state.get('mode') == 'fade_out'
                if fade_out_hovered or fade_out_active:
                    glow_r_outer = r + 6
                    glow_r_inner = r + 3
                    self.create_oval(
                        fade_out_x - glow_r_outer, handle_y - glow_r_outer, fade_out_x + glow_r_outer, handle_y + glow_r_outer,
                        outline=Theme.WARNING, width=2
                    )
                    self.create_oval(
                        fade_out_x - glow_r_inner, handle_y - glow_r_inner, fade_out_x + glow_r_inner, handle_y + glow_r_inner,
                        outline=Theme.PLAYHEAD, width=2
                    )
                fade_out_fill = Theme.WARNING if fade_out_active else Theme.FG_HIGHLIGHT
                self.create_oval(
                    fade_out_x - r, handle_y - r, fade_out_x + r, handle_y + r,
                    fill=fade_out_fill, outline=''
                )

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
        self._draw_play_start_marker(height)
        self._update_playhead_visual(height)

    def _draw_play_start_marker(self, height: int):
        """Draw dashed line at the position where playback started."""
        if self.play_start_position is None:
            return

        x = self.header_width + int(round(self.play_start_position * self.pixels_per_second)) - self.scroll_offset

        # Don't draw if outside visible area
        if x < self.header_width or x > self.winfo_width():
            return

        # Use a bright cyan/teal color for visibility
        marker_color = '#00ffff'

        # Draw dashed vertical line using tkinter's dash option
        self.create_line(
            x, self.ruler_height, x, height,
            fill=marker_color, width=2, dash=(8, 5),
            tags=('play_start_marker',)
        )

        # Draw small marker at the top
        self.create_polygon(
            x - 6, self.ruler_height - 2, x + 6, self.ruler_height - 2, x, self.ruler_height + 10,
            fill=marker_color, outline='', tags=('play_start_marker',)
        )

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
