"""Timeline canvas widget for displaying tracks and clips."""
import copy
import math
import os
import tkinter as tk
from typing import Optional, Callable, Dict, TYPE_CHECKING

from .theme import Theme
from .ui_components import draw_add_button
from .media_info import MediaInfo

if TYPE_CHECKING:
    from .audio_engine import AudioEngine


class TimelineCanvas(tk.Canvas):
    """Timeline canvas with tracks and playhead."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=Theme.BG_MAIN, highlightthickness=0, takefocus=True, **kwargs)

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
        self.on_play_pause: Optional[Callable[[], None]] = None  # Spacebar play/pause

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
        self.tool_panel_width = 40  # Left tool panel width
        self.header_width = 150  # Track header width (after tool panel)
        self.ruler_height = 30

        # Tool selection ('select' or 'slice')
        self._current_tool = 'select'
        self._hovered_tool: Optional[str] = None
        self._tool_buttons: Dict[str, tuple] = {}  # tool_name -> (x1, y1, x2, y2)

        # Magnet/snap toggle (independent of tool selection)
        self._magnet_enabled = False
        self._snap_threshold_px = 10  # Snap when within 10 pixels of edge
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

        # Slice tool state
        self._slice_hover_info: Optional[dict] = None  # {'track_idx': int, 'clip': dict, 'time': float, 'x': int}

        # Undo/Redo stacks
        self._undo_stack: list = []
        self._redo_stack: list = []
        self._max_undo_levels = 50
        self._pending_undo_state: Optional[dict] = None  # State saved before operation starts

        self._clip_edge_px = 8
        self._min_clip_duration = 0.05  # seconds
        self._fade_handle_radius = 5
        self._fade_handle_y_offset = 14

        # Volume envelope state
        self._envelope_point_radius = 5
        self._envelope_line_hit_tolerance = 6  # pixels
        self._hovered_envelope_point: Optional[dict] = None  # {'clip': clip, 'point_idx': int}
        self._hovered_envelope_line: Optional[dict] = None  # {'clip': clip, 'time': float}

        # View scaling for envelope/waveform visuals
        self._envelope_zoom = 1.0  # 1.0 = full 0..1 range, >1 zooms into the top range
        self._min_envelope_zoom = 1.0
        self._max_envelope_zoom = 16.0
        self._envelope_zoom_step = 1.15

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
        # Keyboard bindings
        self.bind('<Delete>', self._on_delete_key)
        self.bind('<BackSpace>', self._on_delete_key)
        self.bind('<space>', self._on_space_key)
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
        if self._slice_hover_info is not None:
            self._slice_hover_info = None
            self._draw()
        self._set_hover_target(None, None)
        self.config(cursor='')

    def _on_space_key(self, event):
        """Handle spacebar - ALWAYS trigger play/pause, nothing else."""
        if self.on_play_pause:
            self.on_play_pause()
        return "break"  # Prevent any other action

    def _on_delete_key(self, event):
        """Delete the currently selected clip."""
        if self.selected_clip is None:
            return

        # Save state for undo before deleting
        self.save_undo_state()

        # Find and remove the clip from its track
        for track_idx, track in enumerate(self.tracks):
            clips = track.get('clips', [])
            if self.selected_clip in clips:
                clips.remove(self.selected_clip)
                self.selected_clip = None
                self._draw()
                if self.on_clip_select:
                    self.on_clip_select(None, None)
                if self.on_timeline_edited:
                    self.on_timeline_edited()
                return

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

    @property
    def _content_start_x(self) -> int:
        """X position where timeline content starts (after tool panel + track headers)."""
        return self.tool_panel_width + self.header_width

    def _hit_test_track_resize(self, x: int, y: int) -> Optional[int]:
        if x < self.tool_panel_width or x > self._content_start_x:
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
        # Take focus so keyboard events work
        self.focus_set()

        # Check if click is on a tool button
        for tool_name, (x1, y1, x2, y2) in self._tool_buttons.items():
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                if tool_name == 'magnet':
                    # Magnet is a toggle, not a tool selection
                    self._magnet_enabled = not self._magnet_enabled
                else:
                    self._current_tool = tool_name
                self._draw()
                return

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
        if track_idx is not None and self.tool_panel_width < event.x < self._content_start_x:
            bounds = self._track_bounds(track_idx)
            if not bounds:
                return
            track_y1, _track_y2 = bounds
            ms_x = self.tool_panel_width + 8
            if ms_x <= event.x <= (ms_x + 24) and (track_y1 + 50) <= event.y <= (track_y1 + 70):
                self.save_undo_state()
                self.tracks[track_idx]['muted'] = not self.tracks[track_idx].get('muted', False)
                self._draw()
                if self.on_timeline_edited:
                    self.on_timeline_edited()
                return
            if (ms_x + 30) <= event.x <= (ms_x + 54) and (track_y1 + 50) <= event.y <= (track_y1 + 70):
                self.save_undo_state()
                self.tracks[track_idx]['solo'] = not self.tracks[track_idx].get('solo', False)
                self._draw()
                if self.on_timeline_edited:
                    self.on_timeline_edited()
                return

            # Click on track label area (upper part, above buttons) - start track reorder drag
            if event.y < (track_y1 + 45):
                self.save_undo_state()
                self._drag_state = {
                    'mode': 'reorder_track',
                    'track_idx': track_idx,
                    'start_y': event.y,
                }
                self._track_drag_insert_idx = track_idx
                self.config(cursor='fleur')
                self._draw()
                return

        # Clip selection / drag begin / slice
        hit = self._hit_test_clip(event.x, event.y)
        if hit:
            # Handle envelope hits (4-element tuple) vs regular hits (3-element tuple)
            if len(hit) == 4:
                hit_track_idx, hit_clip, hit_part, hit_extra = hit
            else:
                hit_track_idx, hit_clip, hit_part = hit
                hit_extra = None

            if hit_clip.get('loading'):
                return

            self.selected_clip = hit_clip
            if self.on_clip_select:
                self.on_clip_select(hit_clip, hit_track_idx)

            # Save state for undo before potential drag operation
            self.save_undo_state()

            # Handle envelope line click - create new breakpoint
            if hit_part == 'envelope_line':
                self._create_envelope_point(hit_clip, hit_extra, event.x, event.y, hit_track_idx)
                return

            # Handle envelope point drag
            if hit_part == 'envelope_point':
                point_idx = hit_extra
                envelope = hit_clip.get('volume_envelope', [])
                if 0 <= point_idx < len(envelope):
                    point = envelope[point_idx]
                    self._drag_state = {
                        'mode': 'envelope_point',
                        'track_idx': hit_track_idx,
                        'clip': hit_clip,
                        'point_idx': point_idx,
                        'original_time': float(point.get('time', 0.0)),
                        'original_volume': float(point.get('volume', 1.0)),
                        'mouse_x': event.x,
                        'mouse_y': event.y,
                        'click_x': event.x,
                        'click_y': event.y,
                        'has_dragged': True,  # Allow immediate dragging for envelope points
                    }
                    self._draw()
                return

            start_time = float(hit_clip.get('start', 0.0))
            duration = float(hit_clip.get('duration', 0.0))
            source_start = float(hit_clip.get('source_start', 0.0))
            media_duration = hit_clip.get('media_duration')
            if media_duration is None and self.audio_engine and hit_clip.get('path') in self.audio_engine.loaded_audio:
                media_duration = self.audio_engine.loaded_audio[hit_clip.get('path')].duration

            clip_start_x = self._content_start_x + (start_time * self.pixels_per_second) - self.scroll_offset
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
                'click_x': event.x,  # Initial click position for slice detection
                'click_y': event.y,
                'has_dragged': False,  # Track if actual drag occurred
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
        if event.x > self._content_start_x:
            time = (event.x - self._content_start_x + self.scroll_offset) / self.pixels_per_second
            self.set_playhead(time)
            if self.on_playhead_change:
                self.on_playhead_change(self.playhead_position)
            self._drag_playhead = True

    def _on_double_click(self, event):
        # Check if double-click is on an envelope point - delete it
        hit = self._hit_test_clip(event.x, event.y)
        if hit and len(hit) == 4:
            hit_track_idx, hit_clip, hit_part, hit_extra = hit
            if hit_part == 'envelope_point':
                point_idx = hit_extra
                # Save state for undo
                self.save_undo_state()
                # Delete the point (won't delete first/last)
                if self._delete_envelope_point(hit_clip, point_idx):
                    return

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
                # Check if mouse moved enough to be considered a drag (3px threshold)
                if not self._drag_state.get('has_dragged'):
                    click_x = self._drag_state.get('click_x', event.x)
                    click_y = self._drag_state.get('click_y', event.y)
                    dist_sq = (event.x - click_x) ** 2 + (event.y - click_y) ** 2
                    if dist_sq > 9:  # 3px threshold
                        self._drag_state['has_dragged'] = True

                # Only apply drag if we've actually started dragging
                if self._drag_state.get('has_dragged'):
                    self._apply_drag(event.x, event.y)
            return

        if self._drag_playhead and event.x > self._content_start_x:
            time = max(0, min(self.duration, (event.x - self._content_start_x + self.scroll_offset) / self.pixels_per_second))
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

        # Check if this was a click (no drag) on clip body with slice tool - perform slice
        if (self._current_tool == 'slice' and
            self._drag_state.get('mode') == 'move' and
            not self._drag_state.get('has_dragged')):
            clip = self._drag_state.get('clip')
            track_idx = self._drag_state.get('track_idx')

            # Calculate slice time from click position
            if clip and track_idx is not None:
                track = self.tracks[track_idx]
                track_type = track.get('type', 'audio')
                clip_start = float(clip.get('start', 0.0))
                clip_duration = float(clip.get('duration', 0.0))
                click_x = self._drag_state.get('click_x', event.x)

                # Calculate timeline position from click x
                raw_time = (click_x - self._content_start_x + self.scroll_offset) / self.pixels_per_second

                # For video tracks, snap to nearest frame
                if track_type == 'video':
                    fps = clip.get('frame_rate', 30.0)
                    if not fps or fps <= 0:
                        filepath = clip.get('path')
                        if filepath:
                            fps = MediaInfo.get_frame_rate(filepath)
                        else:
                            fps = 30.0
                    frame_duration = 1.0 / fps
                    frame_num = round(raw_time / frame_duration)
                    slice_time = frame_num * frame_duration
                else:
                    # Audio: exact timing
                    slice_time = raw_time

                # Clamp to valid range within clip
                min_slice_dist = self._min_clip_duration
                slice_time = max(clip_start + min_slice_dist,
                               min(slice_time, clip_start + clip_duration - min_slice_dist))

                # Save state for undo before slicing
                self.save_undo_state()

                # Perform the slice
                if self._slice_clip(track_idx, clip, slice_time):
                    self._drag_state = None
                    self._slice_hover_info = None
                    self._draw()
                    if self.on_clip_select and self.selected_clip:
                        self.on_clip_select(self.selected_clip, track_idx)
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

    def _adjust_envelope_zoom(self, delta: int):
        """Adjust vertical zoom for the volume envelope line (Ctrl+Shift+Wheel)."""
        try:
            zoom = float(self._envelope_zoom)
        except Exception:
            zoom = 1.0

        step = float(getattr(self, '_envelope_zoom_step', 1.15) or 1.15)
        if delta > 0:
            zoom *= step
        else:
            zoom /= step

        zoom = max(float(self._min_envelope_zoom), min(float(self._max_envelope_zoom), float(zoom)))
        if abs(zoom - float(self._envelope_zoom)) > 1e-6:
            self._envelope_zoom = zoom
            self._draw()

    def _on_mousewheel(self, event):
        """Handle mouse wheel zoom (Windows/macOS).

        - Wheel: timeline zoom
        - Ctrl+Shift+Wheel: envelope zoom
        """
        # Tk state bitmask: Shift=0x0001, Control=0x0004
        ctrl = bool(getattr(event, 'state', 0) & 0x0004)
        shift = bool(getattr(event, 'state', 0) & 0x0001)

        delta = 1 if event.delta > 0 else -1

        if ctrl and shift:
            self._adjust_envelope_zoom(delta)
            return "break"

        if self.on_zoom_request:
            self.on_zoom_request(delta)
        return "break"

    def _on_mousewheel_linux(self, event):
        """Handle mouse wheel zoom (Linux).

        - Wheel: timeline zoom
        - Ctrl+Shift+Wheel: envelope zoom
        """
        ctrl = bool(getattr(event, 'state', 0) & 0x0004)
        shift = bool(getattr(event, 'state', 0) & 0x0001)

        delta = 1 if event.num == 4 else -1

        if ctrl and shift:
            self._adjust_envelope_zoom(delta)
            return "break"

        if self.on_zoom_request:
            self.on_zoom_request(delta)
        return "break"

    def _on_right_click(self, event):
        """Handle right-click for context menu in track labels panel."""
        # Only show menu if clicking in the track labels area (left panel)
        if event.x >= self._content_start_x:
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
            if self._hovered_tool is not None:
                self._hovered_tool = None
                self._draw()
            self.config(cursor='sb_v_double_arrow')
            return

        # Tool button hover
        old_hovered_tool = self._hovered_tool
        self._hovered_tool = None
        for tool_name, (x1, y1, x2, y2) in self._tool_buttons.items():
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                self._hovered_tool = tool_name
                if old_hovered_tool != self._hovered_tool:
                    self._draw()
                self._set_hover_target(None, None)
                self.config(cursor='hand2')
                return

        if old_hovered_tool is not None and self._hovered_tool is None:
            self._draw()

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
        if track_idx is not None and self.tool_panel_width < event.x < self._content_start_x:
            bounds = self._track_bounds(track_idx)
            if not bounds:
                return
            track_y1, _track_y2 = bounds
            ms_x = self.tool_panel_width + 8
            if ((ms_x <= event.x <= ms_x + 24) or (ms_x + 30 <= event.x <= ms_x + 54)) and ((track_y1 + 50) <= event.y <= (track_y1 + 70)):
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
        old_slice_info = self._slice_hover_info
        self._slice_hover_info = None

        # Track envelope point hover state
        old_envelope_point = self._hovered_envelope_point
        self._hovered_envelope_point = None

        if hit:
            # Handle 4-tuple (envelope) vs 3-tuple (other)
            if len(hit) == 4:
                track_idx, clip, part, extra = hit
            else:
                track_idx, clip, part = hit
                extra = None

            # Handle envelope point hover
            if part == 'envelope_point':
                self._hovered_envelope_point = {'clip': clip, 'point_idx': extra}
                cursor = 'hand2'
                if old_envelope_point != self._hovered_envelope_point:
                    self._draw()
                self.config(cursor=cursor)
                return

            # Handle envelope line hover
            if part == 'envelope_line':
                cursor = 'crosshair'  # Indicate you can click to add point
                self.config(cursor=cursor)
                return

            if part in ('trim_start', 'trim_end', 'fade_in', 'fade_out'):
                cursor = 'sb_h_double_arrow'
            elif part in ('fade_in_curve', 'fade_out_curve'):
                cursor = 'sb_v_double_arrow'
            elif part == 'move':
                # Cursor depends on current tool
                if self._current_tool == 'slice':
                    cursor = 'crosshair'
                    # Calculate slice position
                    track = self.tracks[track_idx]
                    track_type = track.get('type', 'audio')
                    clip_start = float(clip.get('start', 0.0))
                    clip_duration = float(clip.get('duration', 0.0))

                    # Calculate timeline position from mouse x
                    raw_time = (event.x - self._content_start_x + self.scroll_offset) / self.pixels_per_second

                    # For video tracks, snap to nearest frame
                    if track_type == 'video':
                        fps = clip.get('frame_rate', 30.0)
                        if not fps or fps <= 0:
                            # Try to get from media file if we have a path
                            filepath = clip.get('path')
                            if filepath:
                                fps = MediaInfo.get_frame_rate(filepath)
                            else:
                                fps = 30.0
                        # Snap to nearest frame
                        frame_duration = 1.0 / fps
                        frame_num = round(raw_time / frame_duration)
                        slice_time = frame_num * frame_duration
                    else:
                        # Audio: exact timing
                        slice_time = raw_time

                    # Clamp to valid range within clip (with minimum distance from edges)
                    min_slice_dist = self._min_clip_duration
                    slice_time = max(clip_start + min_slice_dist,
                                   min(slice_time, clip_start + clip_duration - min_slice_dist))

                    # Calculate x position for the slice line
                    slice_x = self._content_start_x + int(slice_time * self.pixels_per_second) - self.scroll_offset

                    self._slice_hover_info = {
                        'track_idx': track_idx,
                        'clip': clip,
                        'time': slice_time,
                        'x': slice_x
                    }
                else:
                    # Select tool - show move cursor
                    cursor = 'fleur'
            else:
                cursor = 'fleur'

            if part in ('fade_in', 'fade_out'):
                hover_clip = clip
                hover_part = part

        # Redraw if slice hover changed
        if old_slice_info != self._slice_hover_info:
            self._draw()

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
        x1 = self._content_start_x + float(clip['start']) * self.pixels_per_second - self.scroll_offset
        x2 = self._content_start_x + float(clip['start'] + clip['duration']) * self.pixels_per_second - self.scroll_offset
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
                if y1 <= y <= y2 and x >= self._content_start_x:
                    visible_x1 = max(float(x1), float(self._content_start_x))
                    if not (visible_x1 <= float(x) <= float(x2)):
                        continue
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

                        # Check envelope points and line (only for audio tracks)
                        if track.get('type', 'audio') == 'audio':
                            envelope_hit = self._hit_test_envelope(clip, x, y, x1, x2, y1, y2, track_idx)
                            if envelope_hit:
                                return envelope_hit

                    if (x - x1) <= self._clip_edge_px and (x2 - x1) >= (self._clip_edge_px * 2):
                        return (track_idx, clip, 'trim_start')
                    if (x2 - x) <= self._clip_edge_px and (x2 - x1) >= (self._clip_edge_px * 2):
                        return (track_idx, clip, 'trim_end')
                    return (track_idx, clip, 'move')
        return None

    def _hit_test_envelope(self, clip, mx: int, my: int, clip_x1: int, clip_x2: int,
                           clip_y1: int, clip_y2: int, track_idx: int) -> Optional[tuple]:
        """Test if mouse is over an envelope point or line segment.

        Returns (track_idx, clip, 'envelope_point', point_idx) for point hits,
        or (track_idx, clip, 'envelope_line', time) for line hits.
        """
        envelope = clip.get('volume_envelope')
        if not envelope or len(envelope) < 2:
            return None

        clip_duration = float(clip.get('duration', 0.0))
        if clip_duration <= 0:
            return None

        # Calculate envelope Y range (same as in _draw_volume_envelope)
        envelope_top = clip_y1 + 20
        envelope_bottom = clip_y2 - 8
        envelope_height = envelope_bottom - envelope_top
        if envelope_height < 10:
            return None

        start_x = clip_x1  # This is already the screen x of clip start
        r = self._envelope_point_radius
        r2 = r * r

        # First check if mouse is near any point
        for i, point in enumerate(envelope):
            time = float(point.get('time', 0.0))
            volume = float(point.get('volume', 1.0))
            volume = max(0.0, min(1.0, volume))

            px = start_x + int(round(time * self.pixels_per_second))
            py = int(round(self._envelope_volume_to_y(volume, envelope_top, envelope_bottom)))

            dist_sq = (mx - px) * (mx - px) + (my - py) * (my - py)
            if dist_sq <= r2 * 2.5:  # Slightly larger hit area
                return (track_idx, clip, 'envelope_point', i)

        # Then check if mouse is near a line segment
        tolerance = self._envelope_line_hit_tolerance
        for i in range(len(envelope) - 1):
            p1 = envelope[i]
            p2 = envelope[i + 1]

            t1 = float(p1.get('time', 0.0))
            v1 = float(p1.get('volume', 1.0))
            t2 = float(p2.get('time', 0.0))
            v2 = float(p2.get('volume', 1.0))

            x1 = start_x + int(round(t1 * self.pixels_per_second))
            y1 = int(round(self._envelope_volume_to_y(v1, envelope_top, envelope_bottom)))
            x2 = start_x + int(round(t2 * self.pixels_per_second))
            y2 = int(round(self._envelope_volume_to_y(v2, envelope_top, envelope_bottom)))

            # Check if mx is within the x range of this segment
            if not (min(x1, x2) - tolerance <= mx <= max(x1, x2) + tolerance):
                continue

            # Calculate distance from point to line segment
            dist = self._point_to_segment_distance(mx, my, x1, y1, x2, y2)
            if dist <= tolerance:
                # Calculate the time at this x position
                if x2 != x1:
                    t = (mx - x1) / (x2 - x1)
                    t = max(0.0, min(1.0, t))
                    hit_time = t1 + t * (t2 - t1)
                else:
                    hit_time = t1
                return (track_idx, clip, 'envelope_line', hit_time)

        return None

    def _point_to_segment_distance(self, px: int, py: int, x1: int, y1: int, x2: int, y2: int) -> float:
        """Calculate distance from point (px, py) to line segment (x1,y1)-(x2,y2)."""
        dx = x2 - x1
        dy = y2 - y1
        length_sq = dx * dx + dy * dy

        if length_sq == 0:
            # Segment is a point
            return math.sqrt((px - x1) ** 2 + (py - y1) ** 2)

        # Project point onto line
        t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / length_sq))
        proj_x = x1 + t * dx
        proj_y = y1 + t * dy

        return math.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2)

    def _create_envelope_point(self, clip: dict, time: float, mouse_x: int, mouse_y: int, track_idx: int):
        """Create a new envelope breakpoint at the given time."""
        envelope = clip.get('volume_envelope')
        if not envelope:
            return

        clip_duration = float(clip.get('duration', 0.0))
        if clip_duration <= 0:
            return

        # Clamp time to valid range
        time = max(0.0, min(time, clip_duration))

        # Calculate the volume at this time by interpolating between existing points
        volume = self._get_envelope_volume_at_time(envelope, time)

        # Find the right position to insert (keep sorted by time)
        insert_idx = 0
        for i, point in enumerate(envelope):
            if float(point.get('time', 0.0)) < time:
                insert_idx = i + 1
            else:
                break

        # Create new point
        new_point = {'time': time, 'volume': volume}
        envelope.insert(insert_idx, new_point)

        # Start dragging the new point
        self._drag_state = {
            'mode': 'envelope_point',
            'track_idx': track_idx,
            'clip': clip,
            'point_idx': insert_idx,
            'original_time': time,
            'original_volume': volume,
            'mouse_x': mouse_x,
            'mouse_y': mouse_y,
            'click_x': mouse_x,
            'click_y': mouse_y,
            'has_dragged': True,  # Allow immediate dragging
        }

        self._draw()
        if self.on_timeline_edited:
            self.on_timeline_edited()

    def _get_envelope_volume_at_time(self, envelope: list, time: float) -> float:
        """Get the interpolated volume at a given time in the envelope."""
        if not envelope:
            return 1.0

        # Find surrounding points
        prev_point = None
        next_point = None

        for point in envelope:
            pt = float(point.get('time', 0.0))
            if pt <= time:
                prev_point = point
            else:
                next_point = point
                break

        if prev_point is None:
            return float(envelope[0].get('volume', 1.0))
        if next_point is None:
            return float(prev_point.get('volume', 1.0))

        # Linear interpolation
        t1 = float(prev_point.get('time', 0.0))
        v1 = float(prev_point.get('volume', 1.0))
        t2 = float(next_point.get('time', 0.0))
        v2 = float(next_point.get('volume', 1.0))

        if t2 == t1:
            return v1

        t = (time - t1) / (t2 - t1)
        return v1 + t * (v2 - v1)

    def _envelope_volume_to_y(self, volume: float, envelope_top: float, envelope_bottom: float) -> float:
        """Map a 0..1 volume value to a Y coordinate, accounting for envelope zoom."""
        height = max(1.0, float(envelope_bottom) - float(envelope_top))
        v = max(0.0, min(1.0, float(volume)))

        zoom = float(getattr(self, '_envelope_zoom', 1.0) or 1.0)
        if zoom > 1.0:
            display_min = max(0.0, 1.0 - (1.0 / zoom))
            denom = 1.0 - display_min
            if denom > 1e-9:
                v = (v - display_min) / denom
            else:
                v = 1.0
            v = max(0.0, min(1.0, v))

        return float(envelope_bottom) - (v * height)

    def _envelope_y_to_volume(self, y: float, envelope_top: float, envelope_bottom: float) -> float:
        """Map a Y coordinate back to a 0..1 volume value, accounting for envelope zoom."""
        height = max(1.0, float(envelope_bottom) - float(envelope_top))
        yy = max(float(envelope_top), min(float(envelope_bottom), float(y)))
        v_norm = (float(envelope_bottom) - yy) / height
        v_norm = max(0.0, min(1.0, v_norm))

        zoom = float(getattr(self, '_envelope_zoom', 1.0) or 1.0)
        if zoom > 1.0:
            display_min = max(0.0, 1.0 - (1.0 / zoom))
            v = display_min + (v_norm * (1.0 - display_min))
        else:
            v = v_norm

        return max(0.0, min(1.0, float(v)))

    def _delete_envelope_point(self, clip: dict, point_idx: int):
        """Delete an envelope breakpoint (but not the first or last point)."""
        envelope = clip.get('volume_envelope')
        if not envelope or len(envelope) <= 2:
            return False

        # Don't delete first or last point
        if point_idx <= 0 or point_idx >= len(envelope) - 1:
            return False

        envelope.pop(point_idx)
        self._draw()
        if self.on_timeline_edited:
            self.on_timeline_edited()
        return True

    def _adjust_envelope_for_trim(self, clip: dict, old_duration: float, new_duration: float,
                                   time_shift: float = 0.0):
        """Adjust volume envelope when clip is trimmed or expanded.

        Args:
            clip: The clip being modified
            old_duration: Duration before the change
            new_duration: Duration after the change
            time_shift: How much to shift envelope times (positive = expand start, negative = trim start)
                       For trim_end/expand_end, this should be 0.
        """
        envelope = clip.get('volume_envelope')
        if not envelope or len(envelope) < 2:
            # Create default envelope if none exists
            clip['volume_envelope'] = [
                {'time': 0.0, 'volume': 1.0},
                {'time': new_duration, 'volume': 1.0}
            ]
            return

        # Get the volume at the old boundaries (for extending)
        old_first_volume = float(envelope[0].get('volume', 1.0))
        old_last_volume = float(envelope[-1].get('volume', 1.0))

        is_expanding = new_duration > old_duration
        is_expanding_start = time_shift > 0.001
        is_trimming_start = time_shift < -0.001

        # Apply time shift to all points (for trim_start/expand_start)
        if abs(time_shift) > 0.001:
            for point in envelope:
                point['time'] = float(point.get('time', 0.0)) + time_shift

        new_envelope = []

        if is_expanding_start:
            # EXPAND START: Add new first point at 0 with old first volume, keep rest as-is
            new_envelope.append({'time': 0.0, 'volume': old_first_volume})
            for point in envelope:
                t = float(point.get('time', 0.0))
                v = float(point.get('volume', 1.0))
                if t > 0.001:  # Skip if too close to 0 (we already added that)
                    new_envelope.append({'time': t, 'volume': v})
            # Update last point to new duration
            if new_envelope:
                new_envelope[-1]['time'] = new_duration

        elif is_trimming_start:
            # TRIM START: Remove points < 0, add interpolated point at 0 if needed
            first_valid_idx = -1
            for i, point in enumerate(envelope):
                t = float(point.get('time', 0.0))
                if t >= 0:
                    first_valid_idx = i
                    break

            if first_valid_idx == -1:
                # All points are before 0, create default
                new_envelope = [
                    {'time': 0.0, 'volume': old_first_volume},
                    {'time': new_duration, 'volume': old_last_volume}
                ]
            else:
                # Check if we need interpolated point at 0
                first_valid_time = float(envelope[first_valid_idx].get('time', 0.0))
                if first_valid_time > 0.001:
                    # Need interpolated point at 0
                    vol_at_zero = self._get_envelope_volume_at_time(envelope, 0.0)
                    new_envelope.append({'time': 0.0, 'volume': vol_at_zero})

                # Add all valid points
                for i in range(first_valid_idx, len(envelope)):
                    point = envelope[i]
                    t = float(point.get('time', 0.0))
                    v = float(point.get('volume', 1.0))
                    if t <= new_duration:
                        if not new_envelope or abs(new_envelope[-1]['time'] - t) > 0.001:
                            new_envelope.append({'time': t, 'volume': v})

                # Ensure last point is at new_duration
                if new_envelope and abs(new_envelope[-1]['time'] - new_duration) > 0.001:
                    vol_at_end = self._get_envelope_volume_at_time(envelope, new_duration)
                    new_envelope.append({'time': new_duration, 'volume': vol_at_end})

        elif is_expanding:
            # EXPAND END: Keep all points, add new last point with old last volume
            for point in envelope:
                t = float(point.get('time', 0.0))
                v = float(point.get('volume', 1.0))
                new_envelope.append({'time': t, 'volume': v})
            # Add new last point at new_duration with same volume as old last
            new_envelope.append({'time': new_duration, 'volume': old_last_volume})

        else:
            # TRIM END: Remove points > new_duration, add interpolated point at new_duration
            for point in envelope:
                t = float(point.get('time', 0.0))
                v = float(point.get('volume', 1.0))
                if t < new_duration - 0.001:
                    new_envelope.append({'time': t, 'volume': v})
                elif abs(t - new_duration) < 0.001:
                    new_envelope.append({'time': new_duration, 'volume': v})
                    break

            # Ensure last point is at new_duration
            if new_envelope:
                last_time = float(new_envelope[-1].get('time', 0.0))
                if last_time < new_duration - 0.001:
                    vol_at_end = self._get_envelope_volume_at_time(envelope, new_duration)
                    new_envelope.append({'time': new_duration, 'volume': vol_at_end})

        # Ensure we have at least 2 points
        if len(new_envelope) < 2:
            new_envelope = [
                {'time': 0.0, 'volume': old_first_volume},
                {'time': new_duration, 'volume': old_last_volume}
            ]

        # Ensure first point is at 0
        if new_envelope and float(new_envelope[0].get('time', 0.0)) > 0.001:
            new_envelope.insert(0, {'time': 0.0, 'volume': float(new_envelope[0].get('volume', 1.0))})

        # Ensure last point is at new_duration
        if new_envelope and abs(float(new_envelope[-1].get('time', 0.0)) - new_duration) > 0.001:
            new_envelope.append({'time': new_duration, 'volume': float(new_envelope[-1].get('volume', 1.0))})

        clip['volume_envelope'] = new_envelope

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
            new_start = (float(x) - self._content_start_x + self.scroll_offset - float(state['grab_offset_x'])) / self.pixels_per_second
            new_start = max(0.0, new_start)

            # Apply magnet/snap if enabled
            if self._magnet_enabled and self._current_tool == 'select':
                clip_duration = float(clip.get('duration', 0.0))
                new_end = new_start + clip_duration
                snap_threshold = self._snap_threshold_px / self.pixels_per_second

                # Get all other clips in the same track
                track = self.tracks[track_idx]
                other_clips = [c for c in track.get('clips', []) if c is not clip]

                best_snap = None
                best_snap_dist = snap_threshold

                for other in other_clips:
                    other_start = float(other.get('start', 0.0))
                    other_end = other_start + float(other.get('duration', 0.0))

                    # Check if moving clip's start snaps to other clip's end
                    dist = abs(new_start - other_end)
                    if dist < best_snap_dist:
                        best_snap = ('start_to_end', other_end)
                        best_snap_dist = dist

                    # Check if moving clip's end snaps to other clip's start
                    dist = abs(new_end - other_start)
                    if dist < best_snap_dist:
                        best_snap = ('end_to_start', other_start - clip_duration)
                        best_snap_dist = dist

                    # Also snap to other clip's start (align starts)
                    dist = abs(new_start - other_start)
                    if dist < best_snap_dist:
                        best_snap = ('start_to_start', other_start)
                        best_snap_dist = dist

                    # Also snap to other clip's end (align ends)
                    dist = abs(new_end - other_end)
                    if dist < best_snap_dist:
                        best_snap = ('end_to_end', other_end - clip_duration)
                        best_snap_dist = dist

                # Also snap to timeline start (time 0)
                dist = abs(new_start)
                if dist < best_snap_dist:
                    best_snap = ('start_to_zero', 0.0)
                    best_snap_dist = dist

                # Also snap to playhead position
                dist = abs(new_start - self.playhead_position)
                if dist < best_snap_dist:
                    best_snap = ('start_to_playhead', self.playhead_position)
                    best_snap_dist = dist

                dist = abs(new_end - self.playhead_position)
                if dist < best_snap_dist:
                    best_snap = ('end_to_playhead', self.playhead_position - clip_duration)
                    best_snap_dist = dist

                # Apply the best snap if found
                if best_snap:
                    new_start = max(0.0, best_snap[1])

            clip['start'] = new_start

        elif mode == 'envelope_point':
            # Drag envelope point
            point_idx = state.get('point_idx')
            envelope = clip.get('volume_envelope', [])
            if point_idx is None or point_idx < 0 or point_idx >= len(envelope):
                return

            point = envelope[point_idx]
            clip_duration = float(clip.get('duration', 0.0))

            # Get clip rect to calculate envelope bounds
            bounds = self._track_bounds(track_idx)
            if not bounds:
                return
            track_y1, track_y2 = bounds
            padding = 4
            clip_y1 = track_y1 + padding
            clip_y2 = track_y2 - padding

            envelope_top = clip_y1 + 20
            envelope_bottom = clip_y2 - 8

            # Calculate clip start x
            clip_start_x = self._content_start_x + float(clip.get('start', 0.0)) * self.pixels_per_second - self.scroll_offset

            # Calculate new time from x position
            new_time = (float(x) - clip_start_x) / self.pixels_per_second

            # Calculate new volume from y position
            new_volume = self._envelope_y_to_volume(float(y), envelope_top, envelope_bottom)

            # First and last points can only move vertically (time is locked)
            if point_idx == 0:
                new_time = 0.0
            elif point_idx == len(envelope) - 1:
                new_time = clip_duration
            else:
                # Clamp time to be between adjacent points
                prev_time = float(envelope[point_idx - 1].get('time', 0.0)) + 0.01
                next_time = float(envelope[point_idx + 1].get('time', clip_duration)) - 0.01
                new_time = max(prev_time, min(new_time, next_time))

            point['time'] = new_time
            point['volume'] = new_volume
            self._draw()
            return

        elif mode == 'trim_start':
            original_start = float(state['start_time'])
            original_duration = float(state['duration'])
            original_source_start = float(state['source_start'])
            original_source_end = original_source_start + original_duration
            original_end = original_start + original_duration

            earliest_start = max(0.0, original_start - original_source_start)
            latest_start = max(0.0, original_end - self._min_clip_duration)

            proposed_start = (float(x) - self._content_start_x + self.scroll_offset) / self.pixels_per_second
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

            # Adjust envelope for trim_start
            # time_shift is negative when trimming (removing beginning), positive when expanding
            time_shift = new_duration - original_duration
            self._adjust_envelope_for_trim(clip, original_duration, new_duration, time_shift)

        elif mode == 'trim_end':
            original_start = float(state['start_time'])
            original_source_start = float(state['source_start'])
            original_duration = float(state['duration'])

            proposed_end = (float(x) - self._content_start_x + self.scroll_offset) / self.pixels_per_second
            proposed_end = max(original_start + self._min_clip_duration, proposed_end)

            new_duration = proposed_end - original_start

            if media_duration is not None:
                max_duration = max(self._min_clip_duration, float(media_duration) - float(original_source_start))
                new_duration = min(new_duration, max_duration)

            clip['duration'] = max(self._min_clip_duration, new_duration)
            clip['fade_in'] = max(0.0, min(float(clip.get('fade_in', 0.0)), float(clip['duration'])))
            clip['fade_out'] = max(0.0, min(float(clip.get('fade_out', 0.0)), float(clip['duration'])))

            # Adjust envelope for trim_end (no time shift, just duration change)
            self._adjust_envelope_for_trim(clip, original_duration, clip['duration'], 0.0)

        elif mode == 'fade_in':
            clip_start = float(clip.get('start', 0.0))
            clip_duration = float(clip.get('duration', 0.0))
            start_x = self._content_start_x + (clip_start * self.pixels_per_second) - self.scroll_offset
            new_fade = (float(x) - float(start_x)) / self.pixels_per_second
            clip['fade_in'] = max(0.0, min(float(new_fade), float(clip_duration)))
            if state.get('curve_target') == 'fade_in_curve' and state.get('curve_start') is not None:
                dy = float(y) - float(state.get('mouse_y_start', y))
                curve = float(state['curve_start']) - (dy / 10.0)
                clip['fade_in_curve'] = max(-5.0, min(5.0, curve))

        elif mode == 'fade_out':
            clip_start = float(clip.get('start', 0.0))
            clip_duration = float(clip.get('duration', 0.0))
            end_x = self._content_start_x + ((clip_start + clip_duration) * self.pixels_per_second) - self.scroll_offset
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

    def _slice_clip(self, track_idx: int, clip: dict, slice_time: float) -> bool:
        """Slice a clip at the specified time, creating two clips.

        Returns True if slice was successful, False otherwise.
        """
        if track_idx < 0 or track_idx >= len(self.tracks):
            return False

        track = self.tracks[track_idx]
        clips = track.get('clips', [])
        if clip not in clips:
            return False

        clip_start = float(clip.get('start', 0.0))
        clip_duration = float(clip.get('duration', 0.0))
        clip_end = clip_start + clip_duration
        source_start = float(clip.get('source_start', 0.0))

        # Validate slice time is within clip bounds with minimum margins
        min_duration = self._min_clip_duration
        if slice_time <= clip_start + min_duration or slice_time >= clip_end - min_duration:
            return False

        # Calculate durations for left and right clips
        left_duration = slice_time - clip_start
        right_duration = clip_end - slice_time

        # Calculate source offsets
        left_source_start = source_start
        right_source_start = source_start + left_duration

        # Create left clip (modify original)
        left_clip = {
            'name': clip.get('name', 'Clip'),
            'path': clip.get('path'),
            'start': clip_start,
            'duration': left_duration,
            'source_start': left_source_start,
            'media_duration': clip.get('media_duration'),
            'fade_in': min(float(clip.get('fade_in', 0.0)), left_duration),
            'fade_out': 0.0,  # No fade out on left clip
            'fade_in_curve': clip.get('fade_in_curve', 0.0),
            'fade_out_curve': 0.0,
        }

        # Create right clip
        right_clip = {
            'name': clip.get('name', 'Clip'),
            'path': clip.get('path'),
            'start': slice_time,
            'duration': right_duration,
            'source_start': right_source_start,
            'media_duration': clip.get('media_duration'),
            'fade_in': 0.0,  # No fade in on right clip
            'fade_out': min(float(clip.get('fade_out', 0.0)), right_duration),
            'fade_in_curve': 0.0,
            'fade_out_curve': clip.get('fade_out_curve', 0.0),
        }

        # Copy optional properties if they exist
        for key in ['frame_rate', 'loading']:
            if key in clip:
                left_clip[key] = clip[key]
                right_clip[key] = clip[key]

        # Split the volume envelope
        original_envelope = clip.get('volume_envelope')
        if original_envelope and len(original_envelope) >= 2:
            # Slice time relative to clip start
            slice_offset = slice_time - clip_start

            # Create left envelope (0 to slice_offset)
            left_envelope = []
            for point in original_envelope:
                t = float(point.get('time', 0.0))
                v = float(point.get('volume', 1.0))
                if t <= slice_offset:
                    left_envelope.append({'time': t, 'volume': v})

            # Add interpolated point at slice_offset if needed
            if not left_envelope or float(left_envelope[-1].get('time', 0.0)) < slice_offset - 0.001:
                vol_at_slice = self._get_envelope_volume_at_time(original_envelope, slice_offset)
                left_envelope.append({'time': slice_offset, 'volume': vol_at_slice})

            # Ensure left envelope starts at 0
            if not left_envelope or float(left_envelope[0].get('time', 0.0)) > 0.001:
                left_envelope.insert(0, {'time': 0.0, 'volume': float(original_envelope[0].get('volume', 1.0))})

            # Adjust left envelope duration to match left_duration
            if left_envelope:
                left_envelope[-1]['time'] = left_duration

            left_clip['volume_envelope'] = left_envelope

            # Create right envelope (slice_offset to end, shifted to start at 0)
            right_envelope = []

            # Add point at 0 with interpolated volume at slice point
            vol_at_slice = self._get_envelope_volume_at_time(original_envelope, slice_offset)
            right_envelope.append({'time': 0.0, 'volume': vol_at_slice})

            # Add points after slice_offset, shifted
            for point in original_envelope:
                t = float(point.get('time', 0.0))
                v = float(point.get('volume', 1.0))
                if t > slice_offset:
                    new_t = t - slice_offset
                    if new_t <= right_duration:
                        right_envelope.append({'time': new_t, 'volume': v})

            # Ensure right envelope ends at right_duration
            if not right_envelope or float(right_envelope[-1].get('time', 0.0)) < right_duration - 0.001:
                vol_at_end = float(original_envelope[-1].get('volume', 1.0))
                right_envelope.append({'time': right_duration, 'volume': vol_at_end})

            right_clip['volume_envelope'] = right_envelope

        # Remove original clip and add the two new clips
        clips.remove(clip)
        clips.append(left_clip)
        clips.append(right_clip)

        # Sort clips by start time
        clips.sort(key=lambda c: float(c.get('start', 0.0)))

        # Update selection to right clip
        self.selected_clip = right_clip

        return True

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
        visible_width = self.winfo_width() - self._content_start_x
        max_scroll = max(0, total_width - visible_width)
        self.scroll_offset = int(percent * max_scroll)
        self._draw()

    def _clamp_scroll_offset(self):
        """Ensure scroll offset is within valid bounds."""
        total_width = self.duration * self.pixels_per_second
        visible_width = max(1, self.winfo_width() - self._content_start_x)
        max_scroll = max(0, total_width - visible_width)
        self.scroll_offset = max(0, min(self.scroll_offset, int(max_scroll)))

    def _notify_scroll_update(self):
        """Notify callback about scroll state."""
        if self.on_scroll_update:
            total_width = self.duration * self.pixels_per_second
            visible_width = max(1, self.winfo_width() - self._content_start_x)
            max_scroll = max(1, total_width - visible_width)
            scroll_percent = self.scroll_offset / max_scroll if max_scroll > 0 else 0
            visible_percent = min(1.0, visible_width / max(1, total_width))
            self.on_scroll_update(scroll_percent, visible_percent)

    def _draw(self):
        self.delete('all')
        self._add_buttons.clear()
        self._tool_buttons.clear()
        self._playhead_line_id = None
        self._playhead_handle_id = None
        width = self.winfo_width()
        height = self.winfo_height()

        if width < 10 or height < 10:
            return

        # Draw tool panel background
        self.create_rectangle(0, 0, self.tool_panel_width, height, fill=Theme.BG_PANEL, outline='')

        # Draw tool buttons
        self._draw_tool_panel(height)

        # Draw ruler background
        self.create_rectangle(self.tool_panel_width, 0, width, self.ruler_height, fill=Theme.BG_PANEL, outline='')

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
        self.create_line(self.tool_panel_width, 0, self.tool_panel_width, height, fill=Theme.BORDER)
        self.create_line(self._content_start_x, 0, self._content_start_x, height, fill=Theme.BORDER)
        self.create_line(0, self.ruler_height, width, self.ruler_height, fill=Theme.BORDER)

    def _draw_tool_panel(self, height: int):
        """Draw the tool selection panel on the left side."""
        btn_size = 28
        btn_margin = 6
        btn_x = (self.tool_panel_width - btn_size) // 2
        btn_y = self.ruler_height + 10

        # Select tool button (arrow icon)
        select_active = self._current_tool == 'select'
        select_hovered = self._hovered_tool == 'select'
        select_bg = Theme.ACCENT if select_active else (Theme.BG_HOVER if select_hovered else Theme.BG_INPUT)
        select_fg = Theme.FG_HIGHLIGHT if select_active else Theme.FG_SECONDARY

        self.create_rectangle(btn_x, btn_y, btn_x + btn_size, btn_y + btn_size,
                            fill=select_bg, outline=Theme.BORDER)
        # Draw arrow/pointer icon
        arrow_cx = btn_x + btn_size // 2
        arrow_cy = btn_y + btn_size // 2
        self.create_polygon(
            arrow_cx - 6, arrow_cy - 8,
            arrow_cx + 6, arrow_cy,
            arrow_cx - 2, arrow_cy,
            arrow_cx - 2, arrow_cy + 8,
            arrow_cx - 6, arrow_cy + 8,
            arrow_cx - 6, arrow_cy - 8,
            fill=select_fg, outline=''
        )
        self._tool_buttons['select'] = (btn_x, btn_y, btn_x + btn_size, btn_y + btn_size)

        # Slice tool button (blade/cut icon)
        btn_y += btn_size + btn_margin
        slice_active = self._current_tool == 'slice'
        slice_hovered = self._hovered_tool == 'slice'
        slice_bg = Theme.ACCENT if slice_active else (Theme.BG_HOVER if slice_hovered else Theme.BG_INPUT)
        slice_fg = Theme.FG_HIGHLIGHT if slice_active else Theme.FG_SECONDARY

        self.create_rectangle(btn_x, btn_y, btn_x + btn_size, btn_y + btn_size,
                            fill=slice_bg, outline=Theme.BORDER)
        # Draw blade/cut icon (vertical line with triangles)
        blade_cx = btn_x + btn_size // 2
        blade_cy = btn_y + btn_size // 2
        self.create_line(blade_cx, btn_y + 5, blade_cx, btn_y + btn_size - 5,
                        fill=slice_fg, width=2)
        # Top triangle
        self.create_polygon(
            blade_cx - 4, btn_y + 6,
            blade_cx + 4, btn_y + 6,
            blade_cx, btn_y + 10,
            fill=slice_fg, outline=''
        )
        # Bottom triangle
        self.create_polygon(
            blade_cx - 4, btn_y + btn_size - 6,
            blade_cx + 4, btn_y + btn_size - 6,
            blade_cx, btn_y + btn_size - 10,
            fill=slice_fg, outline=''
        )
        self._tool_buttons['slice'] = (btn_x, btn_y, btn_x + btn_size, btn_y + btn_size)

        # Magnet toggle button (horseshoe magnet icon)
        btn_y += btn_size + btn_margin
        magnet_active = self._magnet_enabled
        magnet_hovered = self._hovered_tool == 'magnet'
        magnet_bg = Theme.ACCENT if magnet_active else (Theme.BG_HOVER if magnet_hovered else Theme.BG_INPUT)
        magnet_fg = Theme.FG_HIGHLIGHT if magnet_active else Theme.FG_SECONDARY

        self.create_rectangle(btn_x, btn_y, btn_x + btn_size, btn_y + btn_size,
                            fill=magnet_bg, outline=Theme.BORDER)
        # Draw horseshoe magnet icon
        magnet_cx = btn_x + btn_size // 2
        magnet_cy = btn_y + btn_size // 2
        # Draw U-shape for magnet
        # Left arm
        self.create_rectangle(magnet_cx - 8, magnet_cy - 6, magnet_cx - 4, magnet_cy + 6,
                            fill=magnet_fg, outline='')
        # Right arm
        self.create_rectangle(magnet_cx + 4, magnet_cy - 6, magnet_cx + 8, magnet_cy + 6,
                            fill=magnet_fg, outline='')
        # Bottom connector (arc approximation with rectangle)
        self.create_rectangle(magnet_cx - 8, magnet_cy + 2, magnet_cx + 8, magnet_cy + 6,
                            fill=magnet_fg, outline='')
        # Red and blue tips (classic magnet look)
        self.create_rectangle(magnet_cx - 8, magnet_cy - 6, magnet_cx - 4, magnet_cy - 2,
                            fill='#ff4444' if magnet_active else '#aa6666', outline='')
        self.create_rectangle(magnet_cx + 4, magnet_cy - 6, magnet_cx + 8, magnet_cy - 2,
                            fill='#4444ff' if magnet_active else '#6666aa', outline='')
        self._tool_buttons['magnet'] = (btn_x, btn_y, btn_x + btn_size, btn_y + btn_size)

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
            x = self._content_start_x + int(t * self.pixels_per_second) - self.scroll_offset
            if x > width:
                break
            if x < self._content_start_x:
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
        # Track header (starts after tool panel)
        self.create_rectangle(self.tool_panel_width, y, self._content_start_x, y + track_height,
                            fill=Theme.BG_PANEL, outline='')

        # Color indicator
        self.create_rectangle(self.tool_panel_width, y, self.tool_panel_width + 4, y + track_height,
                            fill=track['color'], outline='')

        # Track name
        hdr_x = self.tool_panel_width + 8
        self.create_text(hdr_x, y + 12, text=track['name'], anchor='w',
                        fill=Theme.FG_HIGHLIGHT, font=('Segoe UI', 11, 'bold'))
        self.create_text(hdr_x, y + 30, text=track['type'].capitalize(), anchor='w',
                        fill=Theme.FG_SECONDARY, font=('Segoe UI', 9))

        # M/S buttons
        m_color = Theme.ERROR if track['muted'] else Theme.BG_INPUT
        s_color = Theme.WARNING if track['solo'] else Theme.BG_INPUT

        ms_x = self.tool_panel_width + 8
        self.create_rectangle(ms_x, y + 50, ms_x + 24, y + 70, fill=m_color, outline=Theme.BORDER)
        self.create_text(ms_x + 12, y + 60, text='M', fill=Theme.FG_HIGHLIGHT, font=('Segoe UI', 9, 'bold'))

        self.create_rectangle(ms_x + 30, y + 50, ms_x + 54, y + 70, fill=s_color, outline=Theme.BORDER)
        self.create_text(ms_x + 42, y + 60, text='S', fill=Theme.FG_HIGHLIGHT, font=('Segoe UI', 9, 'bold'))

        # Add media button (+) - professional rounded design
        btn_x1, btn_y1 = ms_x + 60, y + 50
        btn_x2, btn_y2 = ms_x + 110, y + 72
        is_hovered = self._hovered_add_button == track_idx
        draw_add_button(self, btn_x1, btn_y1, btn_x2, btn_y2, hovered=is_hovered)
        self._add_buttons[track_idx] = (btn_x1, btn_y1, btn_x2, btn_y2)

        # Track content area
        self.create_rectangle(self._content_start_x, y, width, y + track_height,
                            fill=Theme.BG_MAIN, outline='')

        # Grid lines
        major = 5 if self.pixels_per_second < 50 else 1
        start_time = (self.scroll_offset / self.pixels_per_second)
        start_time = (start_time // major) * major
        t = start_time
        while t <= self.duration:
            x = self._content_start_x + int(t * self.pixels_per_second) - self.scroll_offset
            if x > width:
                break
            if x >= self._content_start_x:
                self.create_line(x, y, x, y + track_height, fill=Theme.BG_HOVER)
            t += major

        # Draw clips if any
        for clip in track.get('clips', []):
            self._draw_clip(clip, track, y, width, track_height)

        # Bottom border
        self.create_line(0, y + track_height - 1, width, y + track_height - 1, fill=Theme.BORDER)

        # "Drop media" hint (only if no clips)
        if not track.get('clips'):
            center_x = self._content_start_x + (width - self._content_start_x) // 2
            center_y = y + track_height // 2
            self.create_text(center_x, center_y, text="Click + to add media",
                            fill=Theme.FG_DISABLED, font=('Segoe UI', 10))

    def _draw_clip(self, clip, track, y, width, track_height: int):
        """Draw a media clip on the track with waveform."""
        start_x = self._content_start_x + int(clip['start'] * self.pixels_per_second) - self.scroll_offset
        end_x = self._content_start_x + int((clip['start'] + clip['duration']) * self.pixels_per_second) - self.scroll_offset

        # Skip drawing if clip is completely outside visible area (content area only)
        if end_x <= self._content_start_x or start_x >= width:
            return
        if end_x <= start_x + 2:
            end_x = start_x + 2
        clip_width = end_x - start_x

        # Visible portion (avoid drawing into track header panel)
        draw_left = max(start_x, self._content_start_x)
        draw_right = min(end_x, width)
        visible_width = int(draw_right - draw_left)
        if visible_width <= 1:
            return

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

        inset = 1 if visible_width >= 4 else 0
        self.create_rectangle(draw_left + inset, clip_y1, draw_right - inset, clip_y2,
                            fill=bg_color, outline=outline_color, width=outline_width)

        if is_selected and not is_loading and visible_width >= 12:
            left_handle_x = max(start_x + 2, self._content_start_x + 2)
            right_handle_x = min(end_x - 2, width - 2)
            if right_handle_x > left_handle_x:
                self.create_line(left_handle_x, clip_y1, left_handle_x, clip_y2, fill=Theme.FG_HIGHLIGHT)
                self.create_line(right_handle_x, clip_y1, right_handle_x, clip_y2, fill=Theme.FG_HIGHLIGHT)

        # Draw waveform if audio engine available and clip has audio (not loading)
        if not is_loading and self.audio_engine and clip.get('path') and visible_width > 10:
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
                    curve = clip.get('fade_in_curve', 0.0)
                    p0 = max(0.0, (float(draw_left) - float(start_x)) / float(fade_px))
                    p1 = min(1.0, (float(draw_right) - float(start_x)) / float(fade_px))
                    if p1 > p0:
                        visible_fade_px = max(1.0, (p1 - p0) * float(fade_px))
                        steps = max(12, min(64, int(visible_fade_px) // 4))
                        points = []
                        for i in range(steps + 1):
                            p = p0 + ((i / steps) * (p1 - p0))
                            g = self._curve_gain(p, curve)
                            x = start_x + (p * fade_px)
                            y_pt = line_bottom - g * line_height
                            points.extend([x, y_pt])
                        if len(points) >= 4:
                            # Draw shadow for depth
                            shadow_points = [p + 1 for p in points]
                            self.create_line(
                                shadow_points,
                                fill='#000000',
                                width=3,
                                smooth=True,
                                splinesteps=36,
                                capstyle=tk.ROUND,
                                joinstyle=tk.ROUND,
                            )
                            # Main curve with thicker stroke and high spline smoothness
                            self.create_line(
                                points,
                                fill=Theme.PLAYHEAD,
                                width=2,
                                smooth=True,
                                splinesteps=36,
                                capstyle=tk.ROUND,
                                joinstyle=tk.ROUND,
                            )

                    if is_selected and fade_px >= (curve_r * 4):
                        mid_x = start_x + (fade_px / 2)
                        if float(draw_left) <= float(mid_x) <= float(draw_right):
                            mid_g = self._curve_gain(0.5, curve)
                            mid_y = line_bottom - mid_g * line_height
                            # Control point with outline for better visibility
                            self.create_oval(mid_x - curve_r - 1, mid_y - curve_r - 1, mid_x + curve_r + 1, mid_y + curve_r + 1,
                                             fill='#000000', outline='')
                            self.create_oval(mid_x - curve_r, mid_y - curve_r, mid_x + curve_r, mid_y + curve_r,
                                             fill=Theme.PLAYHEAD, outline=Theme.FG_HIGHLIGHT, width=1)
                fade_in_hovered = self._hover_clip is clip and self._hover_part == 'fade_in'
                fade_in_active = bool(self._drag_state) and self._drag_state.get('clip') is clip and self._drag_state.get('mode') == 'fade_in'
                if float(draw_left) <= float(fade_in_x) <= float(draw_right):
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
                    curve = clip.get('fade_out_curve', 0.0)
                    p0 = max(0.0, (float(draw_left) - float(fade_out_x)) / float(fade_px))
                    p1 = min(1.0, (float(draw_right) - float(fade_out_x)) / float(fade_px))
                    if p1 > p0:
                        visible_fade_px = max(1.0, (p1 - p0) * float(fade_px))
                        steps = max(12, min(64, int(visible_fade_px) // 4))
                        points = []
                        for i in range(steps + 1):
                            p = p0 + ((i / steps) * (p1 - p0))
                            g = self._curve_gain(1.0 - p, curve)
                            x = fade_out_x + (p * fade_px)
                            y_pt = line_bottom - g * line_height
                            points.extend([x, y_pt])
                        if len(points) >= 4:
                            # Draw shadow for depth
                            shadow_points = [p + 1 for p in points]
                            self.create_line(
                                shadow_points,
                                fill='#000000',
                                width=3,
                                smooth=True,
                                splinesteps=36,
                                capstyle=tk.ROUND,
                                joinstyle=tk.ROUND,
                            )
                            # Main curve with thicker stroke and high spline smoothness
                            self.create_line(
                                points,
                                fill=Theme.PLAYHEAD,
                                width=2,
                                smooth=True,
                                splinesteps=36,
                                capstyle=tk.ROUND,
                                joinstyle=tk.ROUND,
                            )

                    if is_selected and fade_px >= (curve_r * 4):
                        mid_x = fade_out_x + (fade_px / 2)
                        if float(draw_left) <= float(mid_x) <= float(draw_right):
                            mid_g = self._curve_gain(0.5, curve)
                            mid_y = line_bottom - mid_g * line_height
                            # Control point with outline for better visibility
                            self.create_oval(mid_x - curve_r - 1, mid_y - curve_r - 1, mid_x + curve_r + 1, mid_y + curve_r + 1,
                                             fill='#000000', outline='')
                            self.create_oval(mid_x - curve_r, mid_y - curve_r, mid_x + curve_r, mid_y + curve_r,
                                             fill=Theme.PLAYHEAD, outline=Theme.FG_HIGHLIGHT, width=1)
                fade_out_hovered = self._hover_clip is clip and self._hover_part == 'fade_out'
                fade_out_active = bool(self._drag_state) and self._drag_state.get('clip') is clip and self._drag_state.get('mode') == 'fade_out'
                if float(draw_left) <= float(fade_out_x) <= float(draw_right):
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
        self.create_text(draw_left + 6, clip_y1 + 10, text=clip_name,
                        anchor='w', fill='#000000', font=('Segoe UI', 8, 'bold'))
        self.create_text(draw_left + 5, clip_y1 + 9, text=clip_name,
                        anchor='w', fill='#ffffff', font=('Segoe UI', 8, 'bold'))

        # Show loading text in center if loading
        if is_loading:
            center_x = (draw_left + draw_right) // 2
            center_y = (clip_y1 + clip_y2) // 2
            self.create_text(center_x, center_y, text="Loading...",
                            fill=Theme.FG_SECONDARY, font=('Segoe UI', 10, 'italic'))
        else:
            # Duration text (top right)
            duration_text = f"{clip['duration']:.1f}s"
            self.create_text(draw_right - 6, clip_y1 + 10, text=duration_text,
                            anchor='e', fill='#000000', font=('Segoe UI', 8))
            self.create_text(draw_right - 5, clip_y1 + 9, text=duration_text,
                            anchor='e', fill='#ffffff', font=('Segoe UI', 8))

        # Draw slice indicator line if hovering over this clip for slicing
        if (self._slice_hover_info and
            self._slice_hover_info.get('clip') is clip and
            not is_loading):
            slice_x = self._slice_hover_info.get('x', 0)
            # Draw slice indicator line
            self.create_line(slice_x, clip_y1 + 2, slice_x, clip_y2 - 2,
                            fill='#ff6b6b', width=2, tags=('slice_indicator',))
            # Draw small triangles at top and bottom
            tri_size = 5
            self.create_polygon(
                slice_x - tri_size, clip_y1 + 2,
                slice_x + tri_size, clip_y1 + 2,
                slice_x, clip_y1 + 2 + tri_size,
                fill='#ff6b6b', outline='', tags=('slice_indicator',)
            )
            self.create_polygon(
                slice_x - tri_size, clip_y2 - 2,
                slice_x + tri_size, clip_y2 - 2,
                slice_x, clip_y2 - 2 - tri_size,
                fill='#ff6b6b', outline='', tags=('slice_indicator',)
            )

        # Draw volume envelope (only for audio tracks, not video)
        if not is_loading and track.get('type', 'audio') == 'audio':
            self._draw_volume_envelope(clip, start_x, end_x, clip_y1, clip_y2, draw_left, draw_right)

    def _draw_volume_envelope(self, clip, start_x, end_x, clip_y1, clip_y2, draw_left, draw_right):
        """Draw the volume envelope line and breakpoints on a clip."""
        clip_duration = float(clip.get('duration', 0.0))
        if clip_duration <= 0:
            return

        # Get or initialize volume envelope
        envelope = clip.get('volume_envelope')
        if envelope is None:
            # Default: flat line at 100% volume (just start and end points)
            envelope = [
                {'time': 0.0, 'volume': 1.0},
                {'time': clip_duration, 'volume': 1.0}
            ]
            clip['volume_envelope'] = envelope

        # Ensure envelope has at least 2 points
        if len(envelope) < 2:
            envelope = [
                {'time': 0.0, 'volume': 1.0},
                {'time': clip_duration, 'volume': 1.0}
            ]
            clip['volume_envelope'] = envelope

        # Calculate Y range for envelope (leave some padding at top/bottom)
        envelope_top = clip_y1 + 20  # Leave space for clip name
        envelope_bottom = clip_y2 - 8
        envelope_height = envelope_bottom - envelope_top
        if envelope_height < 10:
            return

        # Build line points only for the visible clip region.
        # Important: never draw into the left track header area when the clip starts off-screen.
        pps = max(1.0, float(self.pixels_per_second))

        visible_t0 = (float(draw_left) - float(start_x)) / pps
        visible_t1 = (float(draw_right) - float(start_x)) / pps
        t0 = max(0.0, min(clip_duration, float(visible_t0)))
        t1 = max(0.0, min(clip_duration, float(visible_t1)))
        if t1 <= t0:
            return

        points_tv: list[tuple[float, float]] = []
        points_tv.append((t0, float(self._get_envelope_volume_at_time(envelope, t0))))
        for point in envelope:
            time = float(point.get('time', 0.0))
            if t0 < time < t1:
                points_tv.append((time, float(point.get('volume', 1.0))))
        points_tv.append((t1, float(self._get_envelope_volume_at_time(envelope, t1))))

        cleaned: list[tuple[float, float]] = []
        for time, volume in points_tv:
            if cleaned and abs(time - cleaned[-1][0]) < 1e-6:
                cleaned[-1] = (time, volume)
            else:
                cleaned.append((time, volume))

        line_points: list[float] = []
        for time, volume in cleaned:
            x = float(start_x) + (float(time) * pps)
            if x < float(draw_left):
                x = float(draw_left)
            elif x > float(draw_right):
                x = float(draw_right)
            y = self._envelope_volume_to_y(float(volume), envelope_top, envelope_bottom)
            line_points.extend([x, y])

        point_positions = []  # (x, y, idx, point) for drawing handles
        for idx, point in enumerate(envelope):
            time = float(point.get('time', 0.0))
            x = float(start_x) + (time * pps)
            if x < float(draw_left) or x > float(draw_right):
                continue
            y = self._envelope_volume_to_y(float(point.get('volume', 1.0)), envelope_top, envelope_bottom)
            point_positions.append((x, y, idx, point))

        # Draw the envelope line
        if len(line_points) >= 4:
            shadow_points = [p + 1 for p in line_points]
            self.create_line(
                shadow_points,
                fill='#000000',
                width=3,
                capstyle=tk.ROUND,
                joinstyle=tk.ROUND,
                tags=('envelope_line',),
            )
            self.create_line(
                line_points,
                fill='#ffd700',
                width=2,
                capstyle=tk.ROUND,
                joinstyle=tk.ROUND,
                tags=('envelope_line',),
            )

        # Draw breakpoints (circles)
        r = self._envelope_point_radius
        for x, y, idx, point in point_positions:
            if x < draw_left - r or x > draw_right + r:
                continue

            # Check if this point is hovered
            is_hovered = (
                self._hovered_envelope_point is not None
                and self._hovered_envelope_point.get('clip') is clip
                and self._hovered_envelope_point.get('point_idx') == idx
            )

            # Check if this point is being dragged
            is_dragging = (
                self._drag_state is not None
                and self._drag_state.get('mode') == 'envelope_point'
                and self._drag_state.get('clip') is clip
                and self._drag_state.get('point_idx') == idx
            )

            if is_hovered or is_dragging:
                # Highlight effect
                self.create_oval(x - r - 3, y - r - 3, x + r + 3, y + r + 3,
                               fill='', outline='#ffff00', width=2, tags=('envelope_point',))

            # Point fill color
            if is_dragging:
                fill_color = '#ff6600'  # Orange when dragging
            elif is_hovered:
                fill_color = '#ffff00'  # Bright yellow when hovered
            else:
                fill_color = '#ffd700'  # Gold normally

            # Draw the point
            self.create_oval(x - r, y - r, x + r, y + r,
                           fill=fill_color, outline='#000000', width=1, tags=('envelope_point',))

    def _draw_waveform(self, clip, track, start_x, clip_y, clip_width, clip_height):
        """Draw simplified waveform inside clip."""
        filepath = clip.get('path')
        if not filepath or clip_width < 10:
            return

        source_start = float(clip.get('source_start', 0.0))
        duration = float(clip.get('duration', 0.0))

        end_x = start_x + int(clip_width)
        canvas_width = self.winfo_width()

        visible_x1 = max(start_x, self._content_start_x)
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

        x = self._content_start_x + int(round(self.play_start_position * self.pixels_per_second)) - self.scroll_offset

        # Don't draw if outside visible area
        if x < self._content_start_x or x > self.winfo_width():
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

        x = self._content_start_x + int(round(self.playhead_position * self.pixels_per_second)) - self.scroll_offset
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

    # ============== Undo/Redo ==============

    def _get_tracks_snapshot(self) -> list:
        """Create a deep copy of all tracks and clips for undo/redo."""
        return copy.deepcopy(self.tracks)

    def _restore_tracks_snapshot(self, snapshot: list):
        """Restore tracks from a snapshot."""
        self.tracks = copy.deepcopy(snapshot)
        self.selected_clip = None
        self._hover_clip = None
        self._slice_hover_info = None
        self._recompute_track_layout()
        self._draw()

    def save_undo_state(self):
        """Save current state to undo stack. Call this BEFORE making changes."""
        # Save current state
        state = self._get_tracks_snapshot()
        self._undo_stack.append(state)

        # Limit stack size
        if len(self._undo_stack) > self._max_undo_levels:
            self._undo_stack.pop(0)

        # Clear redo stack when new action is performed
        self._redo_stack.clear()

    def undo(self) -> bool:
        """Undo the last action. Returns True if undo was performed."""
        if not self._undo_stack:
            return False

        # Save current state to redo stack
        current_state = self._get_tracks_snapshot()
        self._redo_stack.append(current_state)

        # Restore previous state
        previous_state = self._undo_stack.pop()
        self._restore_tracks_snapshot(previous_state)

        if self.on_timeline_edited:
            self.on_timeline_edited()

        return True

    def redo(self) -> bool:
        """Redo the last undone action. Returns True if redo was performed."""
        if not self._redo_stack:
            return False

        # Save current state to undo stack
        current_state = self._get_tracks_snapshot()
        self._undo_stack.append(current_state)

        # Restore next state
        next_state = self._redo_stack.pop()
        self._restore_tracks_snapshot(next_state)

        if self.on_timeline_edited:
            self.on_timeline_edited()

        return True

    def clear_undo_history(self):
        """Clear all undo/redo history."""
        self._undo_stack.clear()
        self._redo_stack.clear()

    # ============== Project Data ==============

    def get_project_data(self) -> dict:
        """Export all timeline data for saving to a project file."""
        tracks_data = []
        for track in self.tracks:
            track_data = {
                'name': track.get('name', ''),
                'type': track.get('type', 'audio'),
                'color': track.get('color', ''),
                'muted': track.get('muted', False),
                'solo': track.get('solo', False),
                'height': track.get('height', self.track_height),
                'clips': []
            }

            for clip in track.get('clips', []):
                clip_data = {
                    'name': clip.get('name', ''),
                    'path': clip.get('path', ''),
                    'start': clip.get('start', 0.0),
                    'duration': clip.get('duration', 0.0),
                    'source_start': clip.get('source_start', 0.0),
                    'media_duration': clip.get('media_duration'),
                    'fade_in': clip.get('fade_in', 0.0),
                    'fade_out': clip.get('fade_out', 0.0),
                    'fade_in_curve': clip.get('fade_in_curve', 0.0),
                    'fade_out_curve': clip.get('fade_out_curve', 0.0),
                }
                # Include frame_rate if present
                if 'frame_rate' in clip:
                    clip_data['frame_rate'] = clip['frame_rate']
                # Include volume envelope if present
                if 'volume_envelope' in clip:
                    clip_data['volume_envelope'] = clip['volume_envelope']
                track_data['clips'].append(clip_data)

            tracks_data.append(track_data)

        return {
            'version': 1,
            'timeline': {
                'duration': self.duration,
                'pixels_per_second': self.pixels_per_second,
                'playhead_position': self.playhead_position,
                'scroll_offset': self.scroll_offset,
            },
            'tracks': tracks_data,
            'current_tool': self._current_tool,
            'magnet_enabled': self._magnet_enabled,
        }

    def load_project_data(self, data: dict, project_dir: str = None):
        """Load timeline data from a project file.

        Args:
            data: Project data dictionary
            project_dir: Directory of the project file (for resolving relative paths)
        """
        # Clear current state
        self.selected_clip = None
        self._hover_clip = None
        self._slice_hover_info = None

        # Load timeline settings
        timeline_data = data.get('timeline', {})
        self.duration = timeline_data.get('duration', 180)
        self.pixels_per_second = timeline_data.get('pixels_per_second', 100)
        self.playhead_position = timeline_data.get('playhead_position', 0.0)
        self.scroll_offset = timeline_data.get('scroll_offset', 0)

        # Load tool selection and magnet state
        self._current_tool = data.get('current_tool', 'select')
        self._magnet_enabled = data.get('magnet_enabled', False)

        # Load tracks
        tracks_data = data.get('tracks', [])
        self.tracks = []

        for track_data in tracks_data:
            track = {
                'name': track_data.get('name', ''),
                'type': track_data.get('type', 'audio'),
                'color': track_data.get('color', Theme.TRACK_AUDIO_1),
                'muted': track_data.get('muted', False),
                'solo': track_data.get('solo', False),
                'height': track_data.get('height', self.track_height),
                'clips': []
            }

            for clip_data in track_data.get('clips', []):
                # Resolve file path
                file_path = clip_data.get('path', '')

                # Try relative path first if project_dir is provided
                if project_dir and file_path:
                    # Check if it's a relative path stored in the project
                    relative_path = clip_data.get('relative_path', '')
                    if relative_path:
                        resolved_path = os.path.join(project_dir, relative_path)
                        if os.path.exists(resolved_path):
                            file_path = resolved_path
                    # Fall back to absolute path
                    if not os.path.exists(file_path):
                        # Path doesn't exist, keep it anyway (user might fix it)
                        pass

                clip = {
                    'name': clip_data.get('name', ''),
                    'path': file_path,
                    'start': float(clip_data.get('start', 0.0)),
                    'duration': float(clip_data.get('duration', 0.0)),
                    'source_start': float(clip_data.get('source_start', 0.0)),
                    'media_duration': clip_data.get('media_duration'),
                    'fade_in': float(clip_data.get('fade_in', 0.0)),
                    'fade_out': float(clip_data.get('fade_out', 0.0)),
                    'fade_in_curve': float(clip_data.get('fade_in_curve', 0.0)),
                    'fade_out_curve': float(clip_data.get('fade_out_curve', 0.0)),
                }
                if 'frame_rate' in clip_data:
                    clip['frame_rate'] = clip_data['frame_rate']
                # Load volume envelope if present
                if 'volume_envelope' in clip_data:
                    clip['volume_envelope'] = clip_data['volume_envelope']

                track['clips'].append(clip)

            self.tracks.append(track)

        # If no tracks loaded, create defaults
        if not self.tracks:
            self._create_default_tracks()

        self._recompute_track_layout()
        self._waveform_cache.clear()
        self._clamp_scroll_offset()
        self._draw()
