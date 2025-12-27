"""Main WaveSync application window."""
import os
import math
import wave
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional, Tuple
from PIL import Image, ImageTk
import numpy as np

from .audio_engine import AudioEngine
from .timeline import TimelineCanvas
from .media_info import MediaInfo
from .video_extractor import VideoFrameExtractor
from .video_preview import VideoPreviewStream
from .theme import Theme
from .ui_components import RoundedButton, IconButton


class WaveSyncApp:
    """Main WaveSync application."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("WaveSync - Audio/Video Editor")
        self.root.geometry("1280x800")
        self.root.minsize(1024, 700)
        self.root.configure(bg=Theme.BG_MAIN)

        # State
        self.is_playing = False
        self.playhead_position = 0.0
        self.project_duration = 180.0
        self.selected_clip = None
        self.selected_track_idx = None
        self.clipboard_clip = None  # For copy/paste

        # Audio engine (loads audio into memory like Audacity)
        self.audio_engine = AudioEngine()

        # Current preview image
        self.preview_image = None
        self.current_video_clip = None
        self._preview_lock = threading.Lock()
        self._preview_event = threading.Event()
        self._preview_request: Optional[tuple] = None  # (request_id, filepath, time, width, height)
        self._preview_request_id = 0
        self._preview_worker_started = False
        self._closing = False
        self._preview_stream = VideoPreviewStream(fps=30.0)

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
        with self._preview_lock:
            self._closing = True
        self._preview_event.set()
        try:
            self._preview_stream.close()
        except Exception:
            pass
        self.audio_engine.cleanup()
        self.root.destroy()

    def _setup_style(self):
        style = ttk.Style()
        Theme.configure_style(style)

    def _setup_menu(self):
        # ... (menu setup remains the same for now)
        menubar = tk.Menu(self.root, bg=Theme.BG_PANEL, fg=Theme.FG_PRIMARY,
                         activebackground=Theme.ACCENT, activeforeground=Theme.FG_HIGHLIGHT,
                         borderwidth=0)
        self.root.config(menu=menubar)

        def create_menu(parent, label):
            menu = tk.Menu(parent, tearoff=0, bg=Theme.BG_PANEL, fg=Theme.FG_PRIMARY,
                          activebackground=Theme.ACCENT, activeforeground=Theme.FG_HIGHLIGHT)
            parent.add_cascade(label=label, menu=menu)
            return menu

        file_menu = create_menu(menubar, "File")
        file_menu.add_command(label="New Project", accelerator="Ctrl+N", command=self._on_new)
        file_menu.add_command(label="Open Project...", accelerator="Ctrl+O", command=self._on_open)
        file_menu.add_command(label="Save Project", accelerator="Ctrl+S", command=self._on_save)
        file_menu.add_separator()
        file_menu.add_command(label="Import Media...", accelerator="Ctrl+I", command=self._on_import)
        file_menu.add_command(label="Export...", accelerator="Ctrl+E", command=self._on_export)
        file_menu.add_command(label="Export Audio Only...", command=self._on_export_audio_only)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", accelerator="Alt+F4", command=self._on_close)

        edit_menu = create_menu(menubar, "Edit")
        edit_menu.add_command(label="Undo", accelerator="Ctrl+Z", state='disabled')
        edit_menu.add_command(label="Redo", accelerator="Ctrl+Y", state='disabled')
        edit_menu.add_separator()
        edit_menu.add_command(label="Copy", accelerator="Ctrl+C", command=self._on_copy)
        edit_menu.add_command(label="Paste", accelerator="Ctrl+V", command=self._on_paste)
        edit_menu.add_separator()
        edit_menu.add_command(label="Split at Playhead", accelerator="S", command=self._on_split)

        track_menu = create_menu(menubar, "Track")
        track_menu.add_command(label="Add Video Track", command=self._on_add_video_track)
        track_menu.add_command(label="Add Audio Track", command=self._on_add_audio_track)

        view_menu = create_menu(menubar, "View")
        view_menu.add_command(label="Zoom In", accelerator="Ctrl++", command=self._on_zoom_in)
        view_menu.add_command(label="Zoom Out", accelerator="Ctrl+-", command=self._on_zoom_out)
        view_menu.add_command(label="Zoom to Fit", accelerator="Ctrl+0", command=self._on_zoom_fit)

        help_menu = create_menu(menubar, "Help")
        help_menu.add_command(label="Keyboard Shortcuts", accelerator="F1", command=self._on_shortcuts)
        help_menu.add_command(label="About WaveSync", command=self._on_about)

    def _setup_ui(self):
        # Main container
        main_container = ttk.Frame(self.root)
        main_container.pack(fill='both', expand=True)

        # Toolbar (Top)
        toolbar = ttk.Frame(main_container, style='Panel.TFrame', height=70)
        toolbar.pack(fill='x', side='top')
        toolbar.pack_propagate(False)

        # Transport controls
        transport_frame = ttk.Frame(toolbar, style='Panel.TFrame')
        transport_frame.pack(side='left', padx=20, pady=10)

        self.skip_back_btn = IconButton(transport_frame, text="⏮", command=self._on_skip_back, 
                                      width=36, height=36, radius=8,
                                      bg_color=Theme.BG_INPUT, hover_color=Theme.BG_HOVER)
        self.skip_back_btn.pack(side='left', padx=4)

        self.play_btn = RoundedButton(transport_frame, text="▶", command=self._on_play_pause,
                                    width=60, height=36, radius=18,
                                    bg_color=Theme.SUCCESS, hover_color=Theme.SUCCESS_HOVER,
                                    fg_color=Theme.BG_MAIN, font=Theme.FONT_LARGE_BOLD)
        self.play_btn.pack(side='left', padx=10)

        self.stop_btn = RoundedButton(transport_frame, text="⏹", command=self._on_stop,
                                    width=40, height=36, radius=8,
                                    bg_color=Theme.ERROR, hover_color=Theme.ERROR_HOVER,
                                    fg_color=Theme.BG_MAIN, font=Theme.FONT_LARGE)
        self.stop_btn.pack(side='left', padx=4)

        self.skip_fwd_btn = IconButton(transport_frame, text="⏭", command=self._on_skip_forward,
                                     width=36, height=36, radius=8,
                                     bg_color=Theme.BG_INPUT, hover_color=Theme.BG_HOVER)
        self.skip_fwd_btn.pack(side='left', padx=4)

        # Time display
        self.time_label = tk.Label(toolbar, text="00:00:00 / 03:00:00",
                                   bg=Theme.BG_PANEL, fg=Theme.ACCENT,
                                   font=Theme.FONT_MONO_LARGE, padx=20)
        self.time_label.pack(side='left', padx=20)

        # Zoom controls
        zoom_frame = ttk.Frame(toolbar, style='Panel.TFrame')
        zoom_frame.pack(side='right', padx=20)

        IconButton(zoom_frame, text="-", command=self._on_zoom_out, 
                  width=30, height=30, radius=5).pack(side='left')

        self.zoom_scale = tk.Scale(zoom_frame, from_=5, to=1000, orient='horizontal',
                                   length=150, bg=Theme.BG_PANEL, fg=Theme.FG_PRIMARY,
                                   troughcolor=Theme.BG_INPUT, highlightthickness=0,
                                   showvalue=False, command=self._on_zoom_change)
        self.zoom_scale.set(100)
        self.zoom_scale.pack(side='left', padx=8)

        IconButton(zoom_frame, text="+", command=self._on_zoom_in,
                  width=30, height=30, radius=5).pack(side='left')

        self.zoom_label = tk.Label(zoom_frame, text="100%", bg=Theme.BG_PANEL, fg=Theme.FG_SECONDARY,
                                   font=Theme.FONT_MAIN)
        self.zoom_label.pack(side='left', padx=8)

        # Middle Content Area (Split into Left: Preview+Timeline, Right: Properties)
        content_split = ttk.Frame(main_container)
        content_split.pack(fill='both', expand=True)

        # Left side (Preview + Timeline)
        left_frame = ttk.Frame(content_split)
        left_frame.pack(side='left', fill='both', expand=True)

        # Preview area
        self.preview_frame = tk.Frame(left_frame, bg='#000000', height=350)
        self.preview_frame.pack(fill='x', padx=0, pady=0)
        self.preview_frame.pack_propagate(False)

        self.preview_label = tk.Label(self.preview_frame, text="Video Preview",
                                bg='#000000', fg=Theme.FG_DISABLED, font=Theme.FONT_TITLE)
        self.preview_label.place(relx=0.5, rely=0.5, anchor='center')

        # Timeline container (for timeline + scrollbar)
        timeline_container = ttk.Frame(left_frame)
        timeline_container.pack(fill='both', expand=True, padx=0, pady=0)

        # Timeline
        self.timeline = TimelineCanvas(timeline_container, height=300)
        self.timeline.configure(bg=Theme.BG_MAIN, highlightthickness=0)
        self.timeline.pack(fill='both', expand=True, padx=0, pady=0)
        self.timeline.on_playhead_change = self._on_playhead_change
        self.timeline.on_track_add_media = self._on_track_add_media
        self.timeline.on_timeline_edited = self._on_timeline_edited
        self.timeline.on_zoom_request = self._on_zoom_wheel
        self.timeline.on_clip_select = self._on_clip_select
        self.timeline.audio_engine = self.audio_engine

        # Horizontal scrollbar for timeline
        self.timeline_scrollbar = ttk.Scale(
            timeline_container, from_=0, to=100, orient='horizontal',
            command=self._on_timeline_scroll
        )
        self.timeline_scrollbar.pack(fill='x', padx=0, pady=0)
        self.timeline.on_scroll_update = self._update_scrollbar

        # Right side (Properties Panel)
        self.props_frame = ttk.Frame(content_split, style='Panel.TFrame', width=250)
        self.props_frame.pack(side='right', fill='y')
        self.props_frame.pack_propagate(False)

        # Properties Header
        tk.Label(self.props_frame, text="PROPERTIES", bg=Theme.BG_PANEL, fg=Theme.FG_SECONDARY,
                font=('Segoe UI', 9, 'bold'), pady=10).pack(fill='x')

        self.props_content = tk.Frame(self.props_frame, bg=Theme.BG_PANEL)
        self.props_content.pack(fill='both', expand=True, padx=10)
        
        self.props_label = tk.Label(self.props_content, text="No clip selected", 
                                  bg=Theme.BG_PANEL, fg=Theme.FG_DISABLED, wraplength=230)
        self.props_label.pack(pady=20)

        # Status bar
        status_frame = ttk.Frame(main_container, style='Panel.TFrame', height=30)
        status_frame.pack(fill='x', side='bottom')
        status_frame.pack_propagate(False)

        self.status_label = ttk.Label(status_frame, text="Ready", style='Panel.TLabel')
        self.status_label.pack(side='left', padx=10, pady=4)

        ttk.Label(status_frame, text="48000 Hz | Stereo", style='Panel.TLabel').pack(side='right', padx=10, pady=4)

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
        self.root.bind('<Control-c>', lambda e: self._on_copy())
        self.root.bind('<Control-C>', lambda e: self._on_copy())
        self.root.bind('<Control-v>', lambda e: self._on_paste())
        self.root.bind('<Control-V>', lambda e: self._on_paste())
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

    def _get_preview_target_size(self) -> Tuple[int, int]:
        """Compute a reasonable preview decode size (kept small for performance)."""
        try:
            width = int(self.preview_frame.winfo_width()) - 20
            height = int(self.preview_frame.winfo_height()) - 20
        except Exception:
            width, height = 640, 360

        width = max(320, width)
        height = max(180, height)

        # Keep decoding light; the preview is for editing, not final render.
        width = min(width, 640)
        height = min(height, 360)

        return width, height

    def _show_video_frame(self, filepath: str, time: float):
        """Extract and show video frame."""
        width, height = self._get_preview_target_size()
        with self._preview_lock:
            self._preview_request_id += 1
            request_id = self._preview_request_id
            self._preview_request = (request_id, filepath, float(time), width, height)

            if not self._preview_worker_started:
                self._preview_worker_started = True
                threading.Thread(target=self._preview_worker, daemon=True).start()

        self._preview_event.set()

    def _preview_worker(self):
        while True:
            self._preview_event.wait()
            self._preview_event.clear()

            with self._preview_lock:
                if self._closing:
                    break
                request = self._preview_request

            if not request:
                continue

            request_id, filepath, time, width, height = request
            try:
                frame = self._preview_stream.get_frame(filepath, time, width, height)
                if not frame:
                    with self._preview_lock:
                        if self._closing:
                            break
                    frame = VideoFrameExtractor.extract_frame(filepath, time, width=width, height=height)
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
        try:
            self._preview_stream.close()
        except Exception:
            pass

    def _display_frame(self, image: Image.Image):
        """Display frame in preview area."""
        try:
            if image.mode != "RGB":
                image = image.convert("RGB")

            if (
                self.preview_image is not None
                and self.preview_image.width() == image.width
                and self.preview_image.height() == image.height
            ):
                self.preview_image.paste(image)
            else:
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

    def _on_clip_select(self, clip, track_idx):
        """Handle clip selection."""
        self.selected_clip = clip
        self.selected_track_idx = track_idx
        if not clip:
            self.props_label.config(text="No clip selected")
            return

        info = f"Clip: {clip.get('name', 'Untitled')}\n\n"
        info += f"Start: {clip.get('start', 0.0):.2f}s\n"
        info += f"Duration: {clip.get('duration', 0.0):.2f}s\n"
        info += f"Source Start: {clip.get('source_start', 0.0):.2f}s\n\n"
        
        if 'media_duration' in clip:
             info += f"Media Len: {clip['media_duration']:.2f}s\n"
        
        info += f"\nFade In: {clip.get('fade_in', 0.0):.2f}s\n"
        info += f"Fade Out: {clip.get('fade_out', 0.0):.2f}s"

        self.props_label.config(text=info)

    def _play(self):
        """Start playback."""
        self.is_playing = True
        self.play_btn.set_text("⏸")
        self.play_btn.set_colors(bg_color=Theme.WARNING, hover_color=Theme.WARNING)
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
            self.play_btn.set_text("▶")
            self.play_btn.set_colors(bg_color=Theme.SUCCESS, hover_color=Theme.SUCCESS_HOVER)
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
        self.play_btn.set_text("▶")
        self.play_btn.set_colors(bg_color=Theme.SUCCESS, hover_color=Theme.SUCCESS_HOVER)
        self.status_label.config(text="Paused")
        if self.playback_job:
            self.root.after_cancel(self.playback_job)
            self.playback_job = None

    def _on_stop(self):
        self.is_playing = False
        self.audio_engine.stop()  # Stops and resets position to 0
        self.play_btn.set_text("▶")
        self.play_btn.set_colors(bg_color=Theme.SUCCESS, hover_color=Theme.SUCCESS_HOVER)
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

    def _on_zoom_in(self, step: int = None):
        current = self.zoom_scale.get()
        if step is None:
            # Dynamic step: larger steps at higher zoom levels
            step = max(10, int(current * 0.15))
        new_val = min(1000, current + step)
        self.zoom_scale.set(new_val)
        self._on_zoom_change(new_val)

    def _on_zoom_out(self, step: int = None):
        current = self.zoom_scale.get()
        if step is None:
            # Dynamic step: larger steps at higher zoom levels
            step = max(10, int(current * 0.15))
        new_val = max(5, current - step)
        self.zoom_scale.set(new_val)
        self._on_zoom_change(new_val)

    def _on_zoom_fit(self):
        self.zoom_scale.set(100)
        self._on_zoom_change(100)

    def _on_zoom_wheel(self, delta: int):
        """Handle mouse wheel zoom from timeline."""
        if delta > 0:
            self._on_zoom_in()
        else:
            self._on_zoom_out()

    def _on_timeline_scroll(self, value):
        """Handle horizontal scrollbar movement."""
        scroll_percent = float(value) / 100.0
        self.timeline.set_scroll_offset(scroll_percent)

    def _update_scrollbar(self, scroll_percent: float, visible_percent: float):
        """Update scrollbar position and size based on timeline state."""
        self.timeline_scrollbar.set(scroll_percent * 100)

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

        self._export_wav(filepath, audio_only=False)

    def _on_export_audio_only(self):
        """Export only audio tracks to WAV file."""
        filepath = filedialog.asksaveasfilename(
            title="Export Audio Only",
            defaultextension=".wav",
            filetypes=[("WAV Audio", "*.wav"), ("All Files", "*.*")]
        )
        if not filepath:
            return

        root, ext = os.path.splitext(filepath)
        ext = ext.lower()
        if not ext:
            filepath = filepath + ".wav"

        self._export_wav(filepath, audio_only=True)

    def _export_wav(self, filepath: str, audio_only: bool = False):
        mode = "Audio Only" if audio_only else "WAV"
        self.status_label.config(text=f"Exporting {mode}: {os.path.basename(filepath)}")
        threading.Thread(target=self._export_wav_worker, args=(filepath, audio_only), daemon=True).start()

    def _export_wav_worker(self, filepath: str, audio_only: bool = False):
        try:
            sample_rate = int(self.audio_engine.sample_rate)
            channels = int(self.audio_engine.channels)

            # Get tracks to export
            tracks_to_export = self._get_audible_tracks()
            if audio_only:
                tracks_to_export = [t for t in tracks_to_export if t.get('type') == 'audio']

            clips = []
            for track in tracks_to_export:
                for clip in track.get('clips', []):
                    if clip.get('loading'):
                        continue
                    if clip.get('path'):
                        clips.append(clip)

            if not clips:
                msg = "No audio track clips to export." if audio_only else "No clips to export."
                self.root.after(0, lambda m=msg: messagebox.showinfo("Export", m))
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

    def _on_copy(self):
        """Copy the selected clip to clipboard."""
        if not self.selected_clip:
            self.status_label.config(text="No clip selected to copy")
            return

        # Store a deep copy of the clip with all properties
        self.clipboard_clip = {
            'name': self.selected_clip.get('name', 'Untitled'),
            'path': self.selected_clip.get('path'),
            'duration': self.selected_clip.get('duration', 0.0),
            'source_start': self.selected_clip.get('source_start', 0.0),
            'media_duration': self.selected_clip.get('media_duration'),
            'fade_in': self.selected_clip.get('fade_in', 0.0),
            'fade_out': self.selected_clip.get('fade_out', 0.0),
            'fade_in_curve': self.selected_clip.get('fade_in_curve', 0.0),
            'fade_out_curve': self.selected_clip.get('fade_out_curve', 0.0),
            'track_idx': self.selected_track_idx,
        }
        self.status_label.config(text=f"Copied: {self.clipboard_clip['name']}")

    def _on_paste(self):
        """Paste the clipboard clip at playhead position."""
        if not self.clipboard_clip:
            self.status_label.config(text="Nothing to paste")
            return

        # Determine target track
        track_idx = self.clipboard_clip.get('track_idx', 0)
        if track_idx is None or track_idx >= len(self.timeline.tracks):
            track_idx = 0

        track = self.timeline.tracks[track_idx]

        # Create new clip at playhead position
        new_clip = {
            'name': self.clipboard_clip['name'],
            'path': self.clipboard_clip['path'],
            'start': self.playhead_position,
            'duration': self.clipboard_clip['duration'],
            'source_start': self.clipboard_clip['source_start'],
            'fade_in': self.clipboard_clip['fade_in'],
            'fade_out': self.clipboard_clip['fade_out'],
            'fade_in_curve': self.clipboard_clip['fade_in_curve'],
            'fade_out_curve': self.clipboard_clip['fade_out_curve'],
            'loading': False,
        }

        # Preserve media_duration so clip can be untrimmed/expanded
        if self.clipboard_clip.get('media_duration') is not None:
            new_clip['media_duration'] = self.clipboard_clip['media_duration']

        track['clips'].append(new_clip)
        self.timeline._draw()
        self.status_label.config(text=f"Pasted: {new_clip['name']} at {self.playhead_position:.2f}s")

    def _on_add_video_track(self):
        num = len([t for t in self.timeline.tracks if t['type'] == 'video']) + 1
        self.timeline.tracks.append({
            'name': f'V{num}', 'type': 'video', 'color': Theme.TRACK_VIDEO, 'muted': False, 'solo': False, 'clips': [], 'height': self.timeline.track_height
        })
        self.timeline._draw()
        self.status_label.config(text=f"Added video track V{num}")

    def _on_add_audio_track(self):
        num = len([t for t in self.timeline.tracks if t['type'] == 'audio']) + 1
        # Cycle through audio track colors
        colors = [Theme.TRACK_AUDIO_1, Theme.TRACK_AUDIO_2, Theme.TRACK_AUDIO_3, Theme.TRACK_AUDIO_4]
        color = colors[(num - 1) % len(colors)]
        
        self.timeline.tracks.append({
            'name': f'A{num}', 'type': 'audio', 'color': color, 'muted': False, 'solo': False, 'clips': [], 'height': self.timeline.track_height
        })
        self.timeline._draw()
        self.status_label.config(text=f"Added audio track A{num}")

    def _on_shortcuts(self):
        messagebox.showinfo("Keyboard Shortcuts", """
PLAYBACK:
  Space - Play/Pause
  Escape - Stop
  <- / -> - Skip 5 seconds
  Home / End - Go to start/end

EDITING:
  Ctrl+C - Copy selected clip
  Ctrl+V - Paste at playhead
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
