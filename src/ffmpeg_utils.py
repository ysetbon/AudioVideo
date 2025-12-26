"""FFmpeg utility functions for locating FFmpeg executables."""
import sys
import os
import subprocess


def get_ffmpeg_path():
    """Get FFmpeg executable path."""
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


# Initialize paths
FFMPEG = get_ffmpeg_path()
FFPLAY = get_ffplay_path()
FFPROBE = get_ffprobe_path()
