# ClipTune - Audio/Video Editor (Python)

A timeline-based audio and video editing application built with Python, PyQt6, and FFmpeg.

## Project Goal

Create a simple yet functional audio/video editor similar to a simplified Audacity with video support. The focus is on fast development iteration and maintainability.

## Target Features

### Core Features
- Import audio/video files (MP3, WAV, MP4, MOV, etc.)
- Timeline with multiple tracks (audio + video)
- Clip operations: trim, move, split, delete
- Audio mixing with multi-track support
- Per-clip gain/volume control
- Fade-in/fade-out per audio clip (linear, exponential, S-curve)
- Preview playback with audio/video sync
- Export to MP4 (H.264 + AAC) and WAV

### UI Components
- Main window with menu bar and toolbar
- Timeline widget with tracks
- Video preview panel
- Track headers with mute/solo controls
- Time ruler
- Waveform visualization

## Tech Stack

- **Python 3.11+** - Main language
- **PyQt6** - UI framework
- **ffmpeg-python** or **PyAV** - Media decoding/encoding
- **numpy** - Audio processing
- **sounddevice** - Audio playback

## Architecture

```
cliptune/
├── main.py              # Entry point
├── requirements.txt     # Dependencies
├── core/
│   ├── project.py       # Project model
│   ├── track.py         # Track model
│   ├── clip.py          # Clip model with fade settings
│   └── commands.py      # Undo/redo command pattern
├── media/
│   ├── decoder.py       # Audio/video decoding
│   ├── encoder.py       # Export encoding
│   └── waveform.py      # Waveform generation
├── audio/
│   ├── engine.py        # Audio playback
│   ├── mixer.py         # Multi-track mixing
│   └── effects.py       # Fade/gain processing
└── ui/
    ├── main_window.py   # Main application window
    ├── timeline.py      # Timeline widget
    ├── preview.py       # Video preview
    ├── clip_item.py     # Clip visualization
    ├── ruler.py         # Time ruler
    └── track_header.py  # Track controls
```

## Audio Format (Internal)

- Sample rate: **48000 Hz**
- Channels: **2** (stereo)
- Sample type: **float32** (numpy)

## Keyboard Shortcuts

- **Space** - Play/Pause
- **Escape** - Stop
- **Left/Right** - Seek backward/forward
- **Ctrl+I** - Import media
- **Ctrl+Z** - Undo
- **Ctrl+Y** - Redo
- **Delete** - Delete selected clip
- **S** - Split clip at playhead

## Getting Started

```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Run
python main.py
```

## License

MIT License
