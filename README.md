# ClipTune - Audio/Video Editor

A simple audio and video editing application built with C++20, Qt 6, and FFmpeg. ClipTune provides a timeline-based editing experience similar to a simplified Audacity combined with basic video editing capabilities.

## Features

### MVP Capabilities
- Import audio/video files (via FFmpeg)
- Timeline with multiple tracks (audio + video)
- Clip trim, move, and split operations
- Audio mixing with multi-track support
- Per-clip gain control
- **Fade-in/fade-out** per audio clip (linear, exponential, S-curve)
- Preview playback (audio as master clock, video synced)
- Export to MP4 (H.264 + AAC) and WAV

## Tech Stack

- **C++20** - Modern C++ standard
- **Qt 6** - UI framework with `QAudioSink` for audio output
- **FFmpeg** - Media decoding/encoding (libavformat, libavcodec, libavutil, swresample, swscale)
- **CMake** - Build system
- **vcpkg** - Dependency management

## Prerequisites (Windows)

### 1. Visual Studio 2022
- Install with "Desktop development with C++" workload
- Components: MSVC toolset, Windows SDK

### 2. CMake
- Version 3.20 or later
- Install from cmake.org or via VS installer

### 3. Qt 6
**Option A (Recommended): Qt Online Installer**
- Download from qt.io
- Install Qt 6.x for MSVC 2022 64-bit
- Note the installation path for CMake configuration

**Option B: Qt via vcpkg**
- Possible but slower to build

### 4. vcpkg
```bash
git clone https://github.com/microsoft/vcpkg.git
cd vcpkg
.\bootstrap-vcpkg.bat
```

## Building

### 1. Clone the repository
```bash
git clone https://github.com/ysetbon/AudioVideo.git
cd AudioVideo
```

### 2. Configure with CMake
```bash
mkdir build
cd build
cmake .. -DCMAKE_TOOLCHAIN_FILE=<path-to-vcpkg>/scripts/buildsystems/vcpkg.cmake \
         -DCMAKE_PREFIX_PATH=<path-to-Qt6>/msvc2022_64
```

### 3. Build
```bash
cmake --build . --config Release
```

### 4. Deploy (Windows)
```bash
# Copy Qt runtime DLLs
<path-to-Qt6>/msvc2022_64/bin/windeployqt.exe ClipTune.exe

# Copy FFmpeg DLLs from vcpkg
```

## Project Structure

```
ClipTune/
├── CMakeLists.txt          # Main CMake configuration
├── vcpkg.json              # vcpkg dependencies
├── src/
│   ├── main.cpp            # Application entry point
│   ├── app/
│   │   └── Application.*   # Application initialization
│   ├── core/
│   │   ├── Project.*       # Project model
│   │   ├── Track.*         # Track model
│   │   ├── Clip.*          # Clip model with fade settings
│   │   ├── UndoStack.*     # Undo/redo system
│   │   └── Commands.*      # Command pattern implementations
│   ├── media/
│   │   ├── FfmpegInit.*    # FFmpeg initialization and RAII wrappers
│   │   ├── Demuxer.*       # Container demuxing
│   │   ├── AudioDecoder.*  # Audio decoding
│   │   ├── VideoDecoder.*  # Video decoding
│   │   ├── Resampler.*     # Audio resampling
│   │   ├── Scaler.*        # Video scaling
│   │   └── FrameQueues.*   # Thread-safe frame queues
│   ├── audio/
│   │   ├── AudioEngine.*   # Audio playback via QAudioSink
│   │   ├── AudioRingBuffer.* # Lock-free ring buffer
│   │   ├── Mixer.*         # Multi-track audio mixing
│   │   └── FadeDSP.*       # Fade envelope processing
│   ├── ui/
│   │   ├── MainWindow.*    # Main application window
│   │   ├── TimelineWidget.*# Timeline view
│   │   ├── PreviewWidget.* # Video preview
│   │   ├── ClipItem.*      # Clip visualization
│   │   ├── RulerWidget.*   # Time ruler
│   │   ├── TrackHeaderWidget.* # Track controls
│   │   └── WaveformCache.* # Waveform generation/caching
│   └── render/
│       ├── ExportJob.*     # Export task management
│       └── Mp4Muxer.*      # MP4/WAV encoding
```

## Audio Format

Internal processing uses:
- Sample rate: **48000 Hz**
- Channels: **2** (stereo)
- Sample type: **float32**

## Fade Implementation

Fades are non-destructive and applied in real-time during mixing:

```
Gain multiplier g(t) where t = time from clip start:

Linear:
- Fade in:  g = t / fadeInDuration      (for t < fadeIn)
- Fade out: g = (L - t) / fadeOutDuration (for t > L - fadeOut)
- Otherwise: g = 1.0

Final sample = source_sample × g(t) × clipGain × trackVolume
```

## Keyboard Shortcuts

- **Space** - Play/Pause
- **Escape** - Stop
- **Left/Right** - Seek backward/forward
- **Ctrl+I** - Import media
- **Ctrl+Z** - Undo
- **Ctrl+Y** - Redo
- **Delete** - Delete selected clip
- **S** - Split clip at playhead
- **Ctrl+0** - Zoom to fit
- **Ctrl++/-** - Zoom in/out

## License

MIT License - See LICENSE file for details.

## FFmpeg Licensing Note

FFmpeg features can toggle between LGPL and GPL depending on enabled codecs. The default vcpkg build uses LGPL-compatible options. If distributing commercially, verify your FFmpeg build's license obligations.
