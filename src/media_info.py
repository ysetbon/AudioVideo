"""Media information utilities using FFprobe."""
import subprocess
import json

from .ffmpeg_utils import FFPROBE


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

    @staticmethod
    def get_video_dimensions(filepath: str) -> tuple:
        """Get video width and height. Returns (width, height) or (0, 0) if not found."""
        info = MediaInfo.get_info(filepath)
        for stream in info.get('streams', []):
            if stream.get('codec_type') == 'video':
                width = stream.get('width', 0)
                height = stream.get('height', 0)
                return (width, height)
        return (0, 0)
