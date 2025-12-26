"""Video frame extraction using FFmpeg."""
import subprocess
import io
from typing import Optional
from PIL import Image

from .ffmpeg_utils import FFMPEG


class VideoFrameExtractor:
    """Extract video frames using FFmpeg."""

    @staticmethod
    def extract_frame(filepath: str, time: float = 0, width: int = 320, height: int = 180) -> Optional[Image.Image]:
        """Extract a single frame at specified time, maintaining aspect ratio."""
        try:
            # Use scale filter to maintain aspect ratio and fit within bounds
            # The -1 tells ffmpeg to calculate the dimension to preserve aspect ratio
            # We use 'min' to fit the frame within the target box
            scale_filter = f"scale='min({width},iw*{height}/ih)':'min({height},ih*{width}/iw)',pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black"

            cmd = [
                FFMPEG, '-ss', str(time),
                '-i', filepath,
                '-vframes', '1',
                '-vf', scale_filter,
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
    def extract_frame_aspect_ratio(filepath: str, time: float = 0,
                                    max_width: int = 640, max_height: int = 360,
                                    scale_factor: float = 0.5) -> Optional[Image.Image]:
        """Extract a frame maintaining original aspect ratio at reduced resolution.

        Args:
            filepath: Path to video file
            time: Time in seconds to extract frame
            max_width: Maximum width for the output
            max_height: Maximum height for the output
            scale_factor: Scale factor for resolution (0.5 = 50% resolution)
        """
        try:
            # Scale filter that:
            # 1. Reduces resolution by scale_factor
            # 2. Maintains aspect ratio
            # 3. Fits within max_width x max_height
            scale_filter = f"scale=iw*{scale_factor}:ih*{scale_factor},scale='min({max_width},iw)':'min({max_height},ih)':force_original_aspect_ratio=decrease"

            cmd = [
                FFMPEG, '-ss', str(time),
                '-i', filepath,
                '-vframes', '1',
                '-vf', scale_filter,
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
