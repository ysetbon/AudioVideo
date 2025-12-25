# WaveSync - Audio/Video Editor Feature Specification

A professional audio/video editing application built with Python and Pygame.

---

## Core Architecture

### Technology Stack
- **GUI Framework**: Pygame (hardware-accelerated rendering)
- **Media Decoding**: PyAV (FFmpeg bindings)
- **Audio Playback**: sounddevice (PortAudio bindings)
- **File Dialogs**: tkinter
- **Data Processing**: NumPy

### Project Structure
```
AudioVideo/
├── main.py              # Application entry point
├── requirements.txt     # Python dependencies
├── src/
│   ├── __init__.py
│   ├── app.py           # Main application class
│   ├── models/
│   │   ├── __init__.py
│   │   ├── project.py   # Project, Track, Clip data models
│   │   └── media.py     # MediaInfo, media-related models
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── audio.py     # Audio playback engine
│   │   ├── decoder.py   # Media decoding (video/audio)
│   │   └── exporter.py  # Export/render functionality
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── colors.py    # Color scheme constants
│   │   ├── fonts.py     # Font management
│   │   ├── components/
│   │   │   ├── __init__.py
│   │   │   ├── button.py
│   │   │   ├── menu.py
│   │   │   ├── slider.py
│   │   │   ├── scrollbar.py
│   │   │   └── dialog.py
│   │   ├── panels/
│   │   │   ├── __init__.py
│   │   │   ├── timeline.py
│   │   │   ├── preview.py
│   │   │   ├── toolbar.py
│   │   │   └── inspector.py
│   │   └── timeline/
│   │       ├── __init__.py
│   │       ├── track.py
│   │       ├── clip.py
│   │       ├── ruler.py
│   │       └── playhead.py
│   └── utils/
│       ├── __init__.py
│       ├── time.py      # Time formatting utilities
│       └── waveform.py  # Waveform generation
└── assets/
    └── icons/           # UI icons (optional)
```

---

## 1. Project Management

### 1.1 New Project
- Create empty project with default settings
- Default tracks: 1 video track (V1), 2 audio tracks (A1, A2)
- Default duration: 3 minutes (extends automatically)
- Default sample rate: 48000 Hz
- Default frame rate: 30 fps

### 1.2 Open Project
- Load project from `.wavesync` JSON file
- Restore all tracks, clips, and settings
- Re-link media files (prompt if missing)
- Restore playhead position

### 1.3 Save Project
- Save to `.wavesync` JSON file format
- Store relative paths to media files
- Include all clip properties (position, trim, gain, fades)
- Include track settings (volume, mute, solo)
- Include view state (zoom level, scroll position)

### 1.4 Auto-Save
- Auto-save every 2 minutes when changes exist
- Save to `.wavesync.autosave` backup file
- Prompt to recover on crash

---

## 2. Media Management

### 2.1 Import Media
- Supported video formats: MP4, MOV, AVI, MKV, WebM
- Supported audio formats: MP3, WAV, AAC, FLAC, OGG, M4A
- Extract media information:
  - Duration
  - Video: resolution, frame rate, codec
  - Audio: sample rate, channels, codec
- Generate waveforms for audio tracks
- Generate thumbnails for video tracks
- Add to appropriate track based on media type

### 2.2 Media Cache
- Cache decoded audio in memory for smooth playback
- Cache generated waveforms
- Cache video thumbnails
- LRU eviction when memory limit reached

### 2.3 Missing Media Handling
- Detect missing media files on project load
- Prompt user to relink files
- Search common locations automatically
- Show placeholder for missing clips

---

## 3. Timeline

### 3.1 Track Management
- Add video tracks
- Add audio tracks
- Delete tracks (with confirmation if contains clips)
- Reorder tracks via drag-and-drop
- Rename tracks (double-click label)

### 3.2 Track Controls
- **Mute (M)**: Silence track output
- **Solo (S)**: Only play soloed tracks (audio only)
- **Volume slider**: Adjust track volume 0-200%
- **Lock**: Prevent accidental edits
- **Color**: Customize track color

### 3.3 Clip Operations
- **Add clip**: Drag from media browser or use import
- **Move clip**: Drag horizontally on timeline
- **Move to track**: Drag vertically between compatible tracks
- **Trim start**: Drag left edge of clip
- **Trim end**: Drag right edge of clip
- **Split**: Split clip at playhead (keyboard: S)
- **Delete**: Remove selected clip (keyboard: Delete)
- **Duplicate**: Copy clip (Ctrl+D)
- **Ripple delete**: Delete and shift subsequent clips left

### 3.4 Clip Properties
- **Name**: Display name on clip
- **Source in/out**: Trim points in source media
- **Timeline position**: Start position on timeline
- **Duration**: Visible duration after trimming
- **Gain/Volume**: Audio volume multiplier (0-400%)
- **Fade in**: Duration of fade in (seconds)
- **Fade out**: Duration of fade out (seconds)
- **Muted**: Individually mute clip

### 3.5 Timeline Navigation
- **Horizontal scroll**: Mouse wheel or scrollbar
- **Zoom**: Ctrl + mouse wheel
- **Zoom to fit**: Fit all clips in view (Ctrl+0)
- **Zoom presets**: 1x, 2x, 5x, 10x
- **Playhead scrubbing**: Click/drag in ruler area
- **Snap to**: Grid, clip edges, playhead (toggle)

### 3.6 Visual Elements
- Time ruler with adaptive markers (seconds/frames)
- Grid lines aligned to time markers
- Playhead (red vertical line)
- Clip waveforms (audio tracks)
- Clip thumbnails (video tracks)
- Selection highlight
- Trim handles on clip edges
- Fade curves visualization

### 3.7 Multi-Select
- Click to select single clip
- Ctrl+Click to add to selection
- Shift+Click to range select
- Drag rectangle to box select
- Move/delete multiple clips at once

---

## 4. Video Preview

### 4.1 Preview Window
- Display current frame at playhead position
- Maintain aspect ratio
- Scale to fit preview area
- Background color for letterboxing

### 4.2 Preview Controls
- Play/Pause overlay button
- Fullscreen toggle (F11)
- Frame step forward/backward (. and ,)
- Time display overlay

### 4.3 Playback Quality
- Full quality preview
- Half resolution for smooth playback
- Quarter resolution for scrubbing
- Auto-adjust based on performance

---

## 5. Audio Engine

### 5.1 Playback
- Real-time audio mixing from all tracks
- Low-latency output via sounddevice
- Sample rate: 48000 Hz
- Channels: Stereo (2)
- Buffer size: 1024 samples

### 5.2 Mixing
- Sum audio from all unmuted clips
- Apply clip gain/volume
- Apply track volume
- Apply fade in/out envelopes
- Solo track handling
- Clip to prevent distortion

### 5.3 Transport Controls
- **Play/Pause**: Toggle playback (Space)
- **Stop**: Stop and return to start (Escape)
- **Skip Back**: Jump back 5 seconds (Left arrow)
- **Skip Forward**: Jump forward 5 seconds (Right arrow)
- **Go to Start**: Jump to 0:00 (Home)
- **Go to End**: Jump to project end (End)
- **Loop**: Toggle loop playback (L)
- **Loop region**: Set in/out points for looping

### 5.4 Time Display
- Timecode format: HH:MM:SS:FF (frames)
- Current position
- Total duration
- Remaining time (toggle)

---

## 6. Editing Features

### 6.1 Undo/Redo
- Unlimited undo history (within memory limits)
- Undo: Ctrl+Z
- Redo: Ctrl+Y or Ctrl+Shift+Z
- Undo history panel (optional)

### 6.2 Clipboard Operations
- Cut: Ctrl+X (remove and copy)
- Copy: Ctrl+C (copy clip)
- Paste: Ctrl+V (paste at playhead)
- Duplicate: Ctrl+D (copy in place)

### 6.3 Snapping
- Snap to grid (configurable interval)
- Snap to clip edges
- Snap to playhead
- Snap to markers
- Toggle snap: Hold Alt to temporarily disable

### 6.4 Ripple Mode
- Toggle ripple mode for insert/delete operations
- Shift subsequent clips when inserting
- Close gaps when deleting

---

## 7. Export/Render

### 7.1 Video Export
- Output formats: MP4 (H.264), WebM (VP9), MOV (ProRes)
- Resolution presets: 1080p, 720p, 480p, Custom
- Frame rate: 24, 25, 30, 60 fps
- Quality: CRF slider (lower = better quality)
- Audio codec: AAC

### 7.2 Audio Export
- Output formats: WAV, MP3, AAC, FLAC
- Sample rate: 44100, 48000 Hz
- Bit depth: 16-bit, 24-bit (WAV only)
- Bitrate: 128, 192, 256, 320 kbps (MP3/AAC)

### 7.3 Export Options
- Export entire project
- Export selection only (between in/out points)
- Export audio only
- Export video without audio
- Background rendering with progress bar

---

## 8. User Interface

### 8.1 Window Layout
```
+--------------------------------------------------+
|  [Title Bar]  WaveSync - Project Name            |
+--------------------------------------------------+
|  File  Edit  Track  View  Help                   |
+--------------------------------------------------+
|  [Toolbar] |< ▶ ■ >| 00:01:23:15 | Zoom [----●--] |
+--------------------------------------------------+
|                                                  |
|  +------------------------------------------+    |
|  |                                          |    |
|  |          [Video Preview]                 |    |
|  |                                          |    |
|  +------------------------------------------+    |
|                                                  |
+--------------------------------------------------+
|  [Timeline]                                      |
|  +------+----------------------------------------+
|  | V1   | [=======Clip 1=========]              |
|  +------+----------------------------------------+
|  | A1   | [~~~waveform~~~~~~~~~~~]              |
|  +------+----------------------------------------+
|  | A2   |         [~~~audio 2~~~~]              |
|  +------+----------------------------------------+
|         |         ▼ (playhead)                  |
+--------------------------------------------------+
|  [Status Bar] 48000 Hz | Stereo | 3 tracks       |
+--------------------------------------------------+
```

### 8.2 Menus

#### File Menu
- New Project (Ctrl+N)
- Open Project (Ctrl+O)
- Save Project (Ctrl+S)
- Save As (Ctrl+Shift+S)
- ---
- Import Media (Ctrl+I)
- Export (Ctrl+E)
- ---
- Recent Projects >
- ---
- Exit (Alt+F4)

#### Edit Menu
- Undo (Ctrl+Z)
- Redo (Ctrl+Y)
- ---
- Cut (Ctrl+X)
- Copy (Ctrl+C)
- Paste (Ctrl+V)
- Duplicate (Ctrl+D)
- Delete (Delete)
- ---
- Split at Playhead (S)
- Select All (Ctrl+A)

#### Track Menu
- Add Video Track
- Add Audio Track
- ---
- Delete Selected Track
- Rename Track
- ---
- Mute All
- Unmute All

#### View Menu
- Zoom In (Ctrl+=)
- Zoom Out (Ctrl+-)
- Zoom to Fit (Ctrl+0)
- ---
- Toggle Snap (N)
- Toggle Ripple Mode (R)
- ---
- Fullscreen Preview (F11)

#### Help Menu
- Keyboard Shortcuts (F1)
- About WaveSync

### 8.3 Keyboard Shortcuts

| Action | Shortcut |
|--------|----------|
| Play/Pause | Space |
| Stop | Escape |
| Skip Back 5s | Left Arrow |
| Skip Forward 5s | Right Arrow |
| Go to Start | Home |
| Go to End | End |
| Previous Frame | , |
| Next Frame | . |
| Split at Playhead | S |
| Delete Selection | Delete |
| Toggle Snap | N |
| Toggle Ripple | R |
| Import Media | Ctrl+I |
| Export | Ctrl+E |
| Undo | Ctrl+Z |
| Redo | Ctrl+Y |
| Save | Ctrl+S |
| Zoom In | Ctrl+= |
| Zoom Out | Ctrl+- |
| Zoom to Fit | Ctrl+0 |
| Fullscreen | F11 |

### 8.4 Color Scheme (Dark Theme)
- Background Dark: #1A1A1A
- Background Medium: #2D2D2D
- Background Light: #3A3A3A
- Timeline Background: #1E1E1E
- Track Area: #151515
- Track Labels: #222222
- Text Primary: #CCCCCC
- Text Secondary: #666666
- Text Muted: #555555
- Border: #444444
- Accent Green: #4ADE80
- Accent Blue: #60A5FA
- Accent Purple: #A78BFA
- Accent Red: #F87171
- Accent Orange: #FB923C
- Playhead: #FF4444
- Video Clip: #3D3360 (border: #6D5A9A)
- Audio Clip: #143025 (border: #22C55E)

---

## 9. Performance Requirements

### 9.1 Target Performance
- 30 FPS UI rendering minimum
- < 100ms audio latency
- Smooth timeline scrolling and zooming
- Responsive clip dragging

### 9.2 Memory Management
- Stream large audio files instead of loading entirely
- Limit waveform cache to 100MB
- Limit thumbnail cache to 50MB
- Dispose unused media resources

### 9.3 Threading
- UI thread: Pygame rendering and event handling
- Audio thread: Real-time audio mixing and output
- Background threads: Media decoding, waveform generation, export

---

## 10. Data Models

### Project
```python
@dataclass
class Project:
    name: str
    path: Optional[str]  # Save location
    tracks: List[Track]
    duration: float  # seconds
    sample_rate: int  # 48000
    frame_rate: float  # 30.0
    created_at: datetime
    modified_at: datetime
```

### Track
```python
@dataclass
class Track:
    id: str  # UUID
    name: str  # "V1", "A1", etc.
    track_type: TrackType  # VIDEO or AUDIO
    clips: List[Clip]
    muted: bool
    solo: bool
    locked: bool
    volume: float  # 0.0 to 2.0
    color: Tuple[int, int, int]
```

### Clip
```python
@dataclass
class Clip:
    id: str  # UUID
    media_path: str
    name: str

    # Timeline position
    timeline_start: float  # seconds
    duration: float  # visible duration

    # Source trim
    source_start: float  # in point
    source_end: float  # out point

    # Audio properties
    gain: float  # 0.0 to 4.0
    fade_in: float  # seconds
    fade_out: float  # seconds
    muted: bool

    # Cached data (not saved)
    waveform: Optional[np.ndarray]
    thumbnails: List[pygame.Surface]
    audio_data: Optional[np.ndarray]
```

### MediaInfo
```python
@dataclass
class MediaInfo:
    path: str
    duration: float
    has_video: bool
    has_audio: bool
    width: int
    height: int
    fps: float
    sample_rate: int
    channels: int
    video_codec: str
    audio_codec: str
```

---

## 11. Future Enhancements (Out of Scope for V1)

- Multiple video tracks compositing
- Video transitions (fade, dissolve, wipe)
- Audio effects (EQ, compression, reverb)
- Video effects (color correction, filters)
- Markers and annotations
- Multi-camera editing
- Proxy workflow for 4K+ content
- GPU-accelerated encoding
- Plugin/extension system
- Collaborative editing
- Cloud project sync

---

## 12. Dependencies

```
pygame>=2.5.0
numpy>=1.24.0
av>=10.0.0
sounddevice>=0.4.6
```

---

## 13. Development Phases

### Phase 1: Core Framework
- Application window and event loop
- Basic UI rendering (title bar, menu bar, toolbar)
- Color scheme and font management

### Phase 2: Timeline Foundation
- Timeline panel with track labels
- Time ruler with markers
- Track background rendering
- Playhead display

### Phase 3: Media Handling
- Media file import
- Audio decoding and waveform generation
- Video thumbnail extraction
- Media info extraction

### Phase 4: Clip Management
- Clip data model
- Clip rendering on timeline
- Clip selection
- Clip dragging/repositioning

### Phase 5: Audio Playback
- Audio engine with real-time mixing
- Transport controls (play, pause, stop)
- Seek functionality
- Track mute/solo

### Phase 6: Advanced Editing
- Clip trimming (drag edges)
- Split at playhead
- Undo/redo system
- Copy/paste/duplicate

### Phase 7: Video Preview
- Video frame decoding
- Preview panel rendering
- Frame-accurate seeking
- Playback synchronization

### Phase 8: Export
- Video rendering pipeline
- Audio export
- Progress feedback
- Format options

### Phase 9: Polish
- Keyboard shortcuts
- Menu system completion
- Project save/load
- Error handling and user feedback
