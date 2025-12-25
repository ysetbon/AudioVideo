#!/usr/bin/env python3
"""
WaveSync - Audio/Video Editor
A professional-looking audio/video editing application interface built with Pygame.
"""

import pygame
import math
import random
import sys
import os

# Suppress pygame welcome message
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"


class Colors:
    """Color scheme for the application."""
    BG_DARK = (26, 26, 26)
    BG_MEDIUM = (45, 45, 45)
    BG_LIGHT = (58, 58, 58)
    TITLE_BAR = (42, 42, 42)
    TIMELINE_BG = (30, 30, 30)
    TIMELINE_HEADER = (40, 40, 40)
    TRACK_AREA = (21, 21, 21)
    TRACK_LABELS = (34, 34, 34)
    TEXT_PRIMARY = (204, 204, 204)
    TEXT_SECONDARY = (102, 102, 102)
    TEXT_MUTED = (85, 85, 85)
    BORDER = (68, 68, 68)
    GREEN = (74, 222, 128)
    GREEN_DARK = (34, 197, 94)
    BLUE = (96, 165, 250)
    BLUE_DARK = (59, 130, 246)
    PURPLE = (167, 139, 250)
    RED = (248, 113, 113)
    RED_DARK = (239, 68, 68)
    PLAYHEAD = (255, 68, 68)
    VIDEO_TRACK = (61, 51, 96)
    VIDEO_BORDER = (109, 90, 154)
    AUDIO1_BG = (20, 48, 37)
    AUDIO2_BG = (21, 32, 53)
    AUDIO3_BG = (37, 21, 21)
    VIDEO_PREVIEW_BG = (13, 13, 13)
    VIDEO_CONTENT = (26, 21, 32)
    THUMBNAIL_BG = (42, 32, 64)
    SILHOUETTE = (45, 37, 53)
    SILHOUETTE_THUMB = (58, 48, 96)
    BLACK = (0, 0, 0)
    WHITE = (255, 255, 255)
    WINDOW_RED = (255, 95, 87)
    WINDOW_YELLOW = (254, 188, 46)
    WINDOW_GREEN = (40, 200, 64)


class WaveSyncApp:
    """Main application class for WaveSync audio/video editor."""

    def __init__(self):
        pygame.init()
        pygame.font.init()

        self.width = 1100
        self.height = 700
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("WaveSync — Untitled Project")

        # Fonts
        self.font_small = pygame.font.SysFont('monospace', 10)
        self.font_medium = pygame.font.SysFont('sans-serif', 11)
        self.font_mono = pygame.font.SysFont('monospace', 13)
        self.font_title = pygame.font.SysFont('sans-serif', 11)
        self.font_label = pygame.font.SysFont('sans-serif', 10)
        self.font_tiny = pygame.font.SysFont('sans-serif', 8)

        # State
        self.is_playing = False
        self.current_time = 84.5  # 01:24:15
        self.zoom_level = 0.625
        self.clock = pygame.time.Clock()
        self.running = True

        # Pre-generate waveforms
        random.seed(42)
        self.wave1 = self._generate_waveform(400, 12, 8)
        self.wave2 = self._generate_waveform(400, 15, 10)

        # Button rects for interaction
        self.play_button_rect = None
        self.stop_button_rect = None
        self.skip_back_rect = None
        self.skip_fwd_rect = None

    def _generate_waveform(self, length, amp1, amp2):
        """Generate waveform data."""
        wave = []
        for i in range(length):
            amp = math.sin(i * 0.3) * amp1 + math.sin(i * 0.7) * amp2
            amp *= (0.5 + random.random() * 0.5)
            wave.append(amp)
        return wave

    def run(self):
        """Main application loop."""
        while self.running:
            self._handle_events()
            self._update()
            self._render()
            self.clock.tick(30)

        pygame.quit()

    def _handle_events(self):
        """Handle user input events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_SPACE:
                    self._toggle_play()
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Left click
                    self._handle_click(event.pos)

    def _handle_click(self, pos):
        """Handle mouse click."""
        if self.play_button_rect and self.play_button_rect.collidepoint(pos):
            self._toggle_play()
        elif self.stop_button_rect and self.stop_button_rect.collidepoint(pos):
            self._stop()
        elif self.skip_back_rect and self.skip_back_rect.collidepoint(pos):
            self._skip_back()
        elif self.skip_fwd_rect and self.skip_fwd_rect.collidepoint(pos):
            self._skip_forward()

    def _toggle_play(self):
        """Toggle play/pause."""
        self.is_playing = not self.is_playing

    def _stop(self):
        """Stop playback."""
        self.is_playing = False
        self.current_time = 0

    def _skip_back(self):
        """Skip backward."""
        self.current_time = max(0, self.current_time - 10)

    def _skip_forward(self):
        """Skip forward."""
        self.current_time = min(210, self.current_time + 10)

    def _update(self):
        """Update application state."""
        if self.is_playing:
            self.current_time += 1 / 30
            if self.current_time > 210:
                self.current_time = 0

    def _render(self):
        """Render the application."""
        # Background
        self.screen.fill(Colors.BG_DARK)

        # Draw window border
        pygame.draw.rect(self.screen, Colors.BORDER, (0, 0, self.width, self.height), 2, border_radius=8)

        # Draw components
        self._draw_title_bar()
        self._draw_toolbar()
        self._draw_video_preview()
        self._draw_timeline()
        self._draw_status_bar()

        pygame.display.flip()

    def _draw_title_bar(self):
        """Draw the title bar."""
        # Title bar background
        pygame.draw.rect(self.screen, Colors.TITLE_BAR, (0, 0, self.width, 32), border_radius=8)
        pygame.draw.rect(self.screen, Colors.TITLE_BAR, (0, 24, self.width, 8))

        # Window controls
        pygame.draw.circle(self.screen, Colors.WINDOW_RED, (18, 16), 6)
        pygame.draw.circle(self.screen, Colors.WINDOW_YELLOW, (38, 16), 6)
        pygame.draw.circle(self.screen, Colors.WINDOW_GREEN, (58, 16), 6)

        # Title text
        title = self.font_title.render("WaveSync — Untitled Project", True, (153, 153, 153))
        title_rect = title.get_rect(center=(self.width // 2, 16))
        self.screen.blit(title, title_rect)

    def _draw_toolbar(self):
        """Draw the toolbar with transport controls."""
        # Toolbar background
        pygame.draw.rect(self.screen, Colors.BG_MEDIUM, (0, 32, self.width, 36))

        # Transport controls
        x = 20
        y = 40

        # Skip back
        self.skip_back_rect = pygame.Rect(x, y, 24, 20)
        pygame.draw.rect(self.screen, Colors.BG_LIGHT, self.skip_back_rect, border_radius=3)
        skip_back_text = self.font_small.render("⏮", True, (136, 136, 136))
        self.screen.blit(skip_back_text, (x + 5, y + 3))

        # Play button
        x += 30
        self.play_button_rect = pygame.Rect(x, y, 28, 20)
        pygame.draw.rect(self.screen, Colors.GREEN_DARK, self.play_button_rect, border_radius=3)
        play_symbol = "⏸" if self.is_playing else "▶"
        play_text = self.font_small.render(play_symbol, True, Colors.WHITE)
        self.screen.blit(play_text, (x + 8, y + 3))

        # Stop button
        x += 34
        self.stop_button_rect = pygame.Rect(x, y, 24, 20)
        pygame.draw.rect(self.screen, Colors.BG_LIGHT, self.stop_button_rect, border_radius=3)
        stop_text = self.font_small.render("⏹", True, (136, 136, 136))
        self.screen.blit(stop_text, (x + 5, y + 3))

        # Skip forward
        x += 30
        self.skip_fwd_rect = pygame.Rect(x, y, 24, 20)
        pygame.draw.rect(self.screen, Colors.BG_LIGHT, self.skip_fwd_rect, border_radius=3)
        skip_fwd_text = self.font_small.render("⏭", True, (136, 136, 136))
        self.screen.blit(skip_fwd_text, (x + 5, y + 3))

        # Time display
        pygame.draw.rect(self.screen, (17, 17, 17), (150, 42, 110, 22), border_radius=4)
        pygame.draw.rect(self.screen, (51, 51, 51), (150, 42, 110, 22), 1, border_radius=4)

        minutes = int(self.current_time // 60)
        seconds = int(self.current_time % 60)
        frames = int((self.current_time % 1) * 30)
        time_str = f"00:{minutes:02d}:{seconds:02d}:{frames:02d}"
        time_text = self.font_mono.render(time_str, True, Colors.GREEN)
        self.screen.blit(time_text, (160, 47))

        # Zoom controls
        zoom_x = 950
        minus_text = self.font_medium.render("−", True, Colors.TEXT_SECONDARY)
        self.screen.blit(minus_text, (zoom_x, 47))

        # Zoom slider track
        pygame.draw.rect(self.screen, (51, 51, 51), (zoom_x + 15, 49, 80, 6), border_radius=3)
        fill_width = int(80 * self.zoom_level)
        pygame.draw.rect(self.screen, Colors.GREEN, (zoom_x + 15, 49, fill_width, 6), border_radius=3)
        pygame.draw.circle(self.screen, (221, 221, 221), (zoom_x + 15 + fill_width, 52), 5)

        plus_text = self.font_medium.render("+", True, Colors.TEXT_SECONDARY)
        self.screen.blit(plus_text, (zoom_x + 105, 47))

    def _draw_video_preview(self):
        """Draw the video preview panel."""
        # Container
        preview_x = 250
        preview_y = 80
        preview_w = 600
        preview_h = 300

        pygame.draw.rect(self.screen, Colors.VIDEO_PREVIEW_BG,
                        (preview_x, preview_y, preview_w, preview_h), border_radius=6)

        # Header
        pygame.draw.rect(self.screen, (37, 37, 37),
                        (preview_x, preview_y, preview_w, 28), border_radius=6)
        pygame.draw.rect(self.screen, (37, 37, 37),
                        (preview_x, preview_y + 20, preview_w, 8))

        header_text = self.font_label.render("VIDEO CLIP V1", True, Colors.PURPLE)
        self.screen.blit(header_text, (preview_x + 15, preview_y + 8))

        # Video content area
        content_x = preview_x + 10
        content_y = preview_y + 35
        content_w = preview_w - 20
        content_h = preview_h - 45

        pygame.draw.rect(self.screen, Colors.VIDEO_CONTENT,
                        (content_x, content_y, content_w, content_h), border_radius=4)

        # Background elements
        pygame.draw.rect(self.screen, (37, 32, 48),
                        (content_x + 40, content_y + 25, 100, 140), border_radius=3)
        pygame.draw.rect(self.screen, (37, 32, 48),
                        (content_x + content_w - 150, content_y + 35, 110, 120), border_radius=3)

        # Person silhouette
        center_x = content_x + content_w // 2
        pygame.draw.ellipse(self.screen, Colors.SILHOUETTE,
                           (center_x - 55, content_y + 25, 110, 110))
        pygame.draw.ellipse(self.screen, Colors.SILHOUETTE,
                           (center_x - 85, content_y + 130, 170, 110))

        # Time overlay
        pygame.draw.rect(self.screen, (0, 0, 0, 200),
                        (content_x + 10, content_y + content_h - 28, 70, 18), border_radius=3)
        time_overlay = self.font_tiny.render("01:24:15", True, Colors.WHITE)
        self.screen.blit(time_overlay, (content_x + 20, content_y + content_h - 24))

        # Resolution overlay
        pygame.draw.rect(self.screen, (0, 0, 0, 200),
                        (content_x + content_w - 80, content_y + content_h - 28, 70, 18), border_radius=3)
        res_overlay = self.font_tiny.render("1920x1080", True, Colors.WHITE)
        self.screen.blit(res_overlay, (content_x + content_w - 70, content_y + content_h - 24))

    def _draw_timeline(self):
        """Draw the timeline panel."""
        timeline_x = 15
        timeline_y = 395
        timeline_w = 1070
        timeline_h = 290

        # Background
        pygame.draw.rect(self.screen, Colors.TIMELINE_BG,
                        (timeline_x, timeline_y, timeline_w, timeline_h), border_radius=6)

        # Header
        pygame.draw.rect(self.screen, Colors.TIMELINE_HEADER,
                        (timeline_x, timeline_y, timeline_w, 28), border_radius=6)
        pygame.draw.rect(self.screen, Colors.TIMELINE_HEADER,
                        (timeline_x, timeline_y + 20, timeline_w, 8))

        # Time ruler
        times = ["00:00", "00:30", "01:00", "01:30", "02:00", "02:30", "03:00", "03:30"]
        for i, t in enumerate(times):
            text = self.font_small.render(t, True, Colors.TEXT_MUTED)
            self.screen.blit(text, (timeline_x + 130 + i * 120, timeline_y + 10))

        # Track labels area
        labels_x = timeline_x + 5
        labels_y = timeline_y + 33
        labels_w = 105
        labels_h = timeline_h - 38

        pygame.draw.rect(self.screen, Colors.TRACK_LABELS,
                        (labels_x, labels_y, labels_w, labels_h), border_radius=4)

        # Draw track labels
        self._draw_track_label(labels_x + 3, labels_y + 5, "V1", "Video",
                              Colors.PURPLE, (42, 37, 53))
        self._draw_track_label(labels_x + 3, labels_y + 60, "A1", "Audio 1",
                              Colors.GREEN, (26, 42, 32))
        self._draw_track_label(labels_x + 3, labels_y + 115, "A2", "Audio 2",
                              Colors.BLUE, (26, 32, 48))
        self._draw_track_label(labels_x + 3, labels_y + 170, "A3", "Audio 3",
                              Colors.RED, (42, 26, 26))

        # Tracks area
        tracks_x = labels_x + labels_w + 5
        tracks_y = labels_y
        tracks_w = timeline_w - labels_w - 15
        tracks_h = labels_h

        pygame.draw.rect(self.screen, Colors.TRACK_AREA,
                        (tracks_x, tracks_y, tracks_w, tracks_h), border_radius=4)

        # Grid lines
        for i in range(8):
            x = tracks_x + 5 + i * 120
            pygame.draw.line(self.screen, (34, 34, 34), (x, tracks_y), (x, tracks_y + tracks_h))

        # Draw tracks
        self._draw_video_track(tracks_x + 5, tracks_y + 5, 700)
        self._draw_audio_track(tracks_x + 30, tracks_y + 60, 650,
                              Colors.AUDIO1_BG, Colors.GREEN, Colors.GREEN_DARK, self.wave1)
        self._draw_audio_track(tracks_x + 5, tracks_y + 115, 750,
                              Colors.AUDIO2_BG, Colors.BLUE, Colors.BLUE_DARK, self.wave2)
        self._draw_sfx_track(tracks_x + 225, tracks_y + 170, 200)

        # Playhead
        playhead_x = tracks_x + 10 + int((self.current_time / 210) * 880)
        pygame.draw.line(self.screen, Colors.PLAYHEAD,
                        (playhead_x, tracks_y), (playhead_x, tracks_y + tracks_h), 2)
        # Playhead handle
        pygame.draw.polygon(self.screen, Colors.PLAYHEAD,
                           [(playhead_x - 6, tracks_y - 3),
                            (playhead_x + 6, tracks_y - 3),
                            (playhead_x, tracks_y + 5)])

    def _draw_track_label(self, x, y, name, subtitle, color, bg_color):
        """Draw a track label."""
        pygame.draw.rect(self.screen, bg_color, (x, y, 95, 50), border_radius=4)

        # Color indicator
        pygame.draw.rect(self.screen, color, (x + 3, y + 3, 4, 44), border_radius=2)

        # Text
        name_text = self.font_label.render(name, True, Colors.TEXT_PRIMARY)
        self.screen.blit(name_text, (x + 15, y + 12))

        sub_text = self.font_tiny.render(subtitle, True, Colors.TEXT_SECONDARY)
        self.screen.blit(sub_text, (x + 15, y + 28))

        # Mute button
        pygame.draw.rect(self.screen, Colors.BG_LIGHT, (x + 65, y + 17, 12, 12), border_radius=2)
        m_text = self.font_tiny.render("M", True, color)
        self.screen.blit(m_text, (x + 68, y + 18))

        # Solo button (not for video)
        if name != "V1":
            pygame.draw.rect(self.screen, Colors.BG_LIGHT, (x + 80, y + 17, 12, 12), border_radius=2)
            s_text = self.font_tiny.render("S", True, (136, 136, 136))
            self.screen.blit(s_text, (x + 83, y + 18))

    def _draw_video_track(self, x, y, width):
        """Draw video track with thumbnails."""
        pygame.draw.rect(self.screen, Colors.VIDEO_TRACK, (x, y, width, 50), border_radius=4)
        pygame.draw.rect(self.screen, Colors.VIDEO_BORDER, (x, y, width, 50), 1, border_radius=4)

        # Thumbnails
        thumb_w = 65
        for i in range(10):
            tx = x + 5 + i * 70
            if tx + thumb_w > x + width - 5:
                break

            pygame.draw.rect(self.screen, Colors.THUMBNAIL_BG, (tx, y + 5, thumb_w, 40), border_radius=2)

            # Silhouette
            pygame.draw.ellipse(self.screen, Colors.SILHOUETTE_THUMB,
                               (tx + 22, y + 9, 20, 20))
            pygame.draw.ellipse(self.screen, Colors.SILHOUETTE_THUMB,
                               (tx + 18, y + 27, 28, 16))

    def _draw_audio_track(self, x, y, width, bg_color, wave_color, border_color, wave_data):
        """Draw audio track with waveform."""
        pygame.draw.rect(self.screen, bg_color, (x, y, width, 50), border_radius=4)
        pygame.draw.rect(self.screen, border_color, (x, y, width, 50), 1, border_radius=4)

        # Waveform
        center_y = y + 25
        points = []
        step = max(1, len(wave_data) * 2 // width)

        for i in range(min(len(wave_data), width // 2)):
            px = x + 10 + i * 2
            if px > x + width - 10:
                break
            idx = (i * step) % len(wave_data)
            amp = wave_data[idx]
            points.append((px, center_y - amp))

        # Draw top then bottom of waveform
        if len(points) >= 2:
            bottom_points = [(p[0], 2 * center_y - p[1]) for p in reversed(points)]
            all_points = points + bottom_points
            pygame.draw.polygon(self.screen, wave_color, all_points)

    def _draw_sfx_track(self, x, y, width):
        """Draw SFX track with transient bars."""
        pygame.draw.rect(self.screen, Colors.AUDIO3_BG, (x, y, width, 50), border_radius=4)
        pygame.draw.rect(self.screen, Colors.RED_DARK, (x, y, width, 50), 1, border_radius=4)

        # Transient bars
        bar_positions = [10, 40, 70, 105, 135, 165]
        bar_heights = [26, 18, 32, 24, 16, 28]

        for pos, h in zip(bar_positions, bar_heights):
            bar_x = x + pos
            bar_y = y + 25 - h // 2
            pygame.draw.rect(self.screen, Colors.RED, (bar_x, bar_y, 6, h), border_radius=1)

    def _draw_status_bar(self):
        """Draw the status bar."""
        pygame.draw.rect(self.screen, (34, 34, 34), (0, 685, self.width, 15))

        left_text = self.font_tiny.render("48000 Hz • 24-bit • Stereo", True, Colors.TEXT_MUTED)
        self.screen.blit(left_text, (15, 689))

        right_text = self.font_tiny.render("CPU: 8%", True, Colors.TEXT_MUTED)
        self.screen.blit(right_text, (self.width - 60, 689))


def main():
    """Main entry point."""
    try:
        app = WaveSyncApp()
        app.run()
    except pygame.error as e:
        print(f"Pygame error: {e}")
        print("\nNote: This application requires a display. If running on a server without")
        print("a display, you can use X11 forwarding or a virtual display (Xvfb).")
        sys.exit(1)


if __name__ == "__main__":
    main()
