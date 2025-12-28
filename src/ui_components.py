import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
from .theme import Theme


class RoundedButton(tk.Canvas):
    def __init__(self, parent, text, command=None, width=100, height=40, radius=8, 
                 bg_color=Theme.BG_INPUT, hover_color=Theme.BG_HOVER, 
                 fg_color=Theme.FG_PRIMARY, font=Theme.FONT_MAIN, canvas_bg=Theme.BG_PANEL):
        super().__init__(parent, width=width, height=height, bg=canvas_bg, highlightthickness=0)
        
        self.command = command
        self.text = text
        self.radius = radius
        self.bg_color = bg_color
        self.hover_color = hover_color
        self.fg_color = fg_color
        self.font = font
        
        self._width = width
        self._height = height
        
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>", self._on_hover)
        self.bind("<Leave>", self._on_leave)
        
        self._draw(self.bg_color)

    def _draw(self, color):
        self.delete("all")
        
        x1, y1 = 0, 0
        x2, y2 = self._width, self._height
        r = self.radius
        
        points = [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1
        ]
        
        self.create_polygon(points, smooth=True, fill=color, outline=color)
        self.create_text(self._width/2, self._height/2, text=self.text, 
                        fill=self.fg_color, font=self.font)

    def set_text(self, text):
        self.text = text
        self._draw(self.bg_color)

    def set_colors(self, bg_color=None, hover_color=None, fg_color=None):
        if bg_color: self.bg_color = bg_color
        if hover_color: self.hover_color = hover_color
        if fg_color: self.fg_color = fg_color
        self._draw(self.bg_color)

    def _on_press(self, event):
        self._draw(Theme.BG_ACTIVE)

    def _on_release(self, event):
        if self.command:
            self.command()
        self._on_hover(event)

    def _on_hover(self, event):
        self._draw(self.hover_color)

    def _on_leave(self, event):
        self._draw(self.bg_color)

    def configure_color(self, bg_color=None, hover_color=None, fg_color=None):
        if bg_color: self.bg_color = bg_color
        if hover_color: self.hover_color = hover_color
        if fg_color: self.fg_color = fg_color
        self._draw(self.bg_color)


class IconButton(RoundedButton):
    def __init__(self, parent, text, command=None, width=40, height=40, radius=20, **kwargs):
        super().__init__(parent, text, command, width, height, radius, **kwargs)


class MediaButton(tk.Canvas):
    """Professional media transport button with smooth animations and glow effects."""
    
    PLAY = "play"
    PAUSE = "pause"
    STOP = "stop"
    SKIP_BACK = "skip_back"
    SKIP_FORWARD = "skip_forward"
    
    def __init__(self, parent, icon_type, command=None, size=44, 
                 bg_color=None, hover_color=None, active_color=None,
                 icon_color=None, canvas_bg=Theme.BG_PANEL, circular=True):
        super().__init__(parent, width=size, height=size, bg=canvas_bg, highlightthickness=0)
        
        self.command = command
        self.icon_type = icon_type
        self.size = size
        self.circular = circular
        self._is_hovered = False
        self._is_pressed = False
        self._animation_step = 0
        self._animation_job = None
        
        if icon_type == self.PLAY:
            self.bg_color = bg_color or Theme.PLAY_BG
            self.hover_color = hover_color or Theme.PLAY_HOVER
            self.active_color = active_color or Theme.PLAY_ACTIVE
            self.icon_color = icon_color or Theme.PLAY_ICON
            self.glow_color = Theme.PLAY_GLOW
        elif icon_type == self.PAUSE:
            self.bg_color = bg_color or Theme.PAUSE_BG
            self.hover_color = hover_color or Theme.PAUSE_HOVER
            self.active_color = active_color or Theme.PAUSE_ACTIVE
            self.icon_color = icon_color or Theme.PAUSE_ICON
            self.glow_color = Theme.PAUSE_GLOW
        elif icon_type == self.STOP:
            self.bg_color = bg_color or Theme.STOP_BG
            self.hover_color = hover_color or Theme.STOP_HOVER
            self.active_color = active_color or Theme.STOP_ACTIVE
            self.icon_color = icon_color or Theme.STOP_ICON
            self.glow_color = Theme.STOP_GLOW
        else:
            self.bg_color = bg_color or Theme.TRANSPORT_BG
            self.hover_color = hover_color or Theme.TRANSPORT_HOVER
            self.active_color = active_color or Theme.TRANSPORT_ACTIVE
            self.icon_color = icon_color or Theme.TRANSPORT_ICON
            self.glow_color = Theme.TRANSPORT_GLOW
        
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>", self._on_hover)
        self.bind("<Leave>", self._on_leave)
        
        self._draw()
    
    def _lerp_color(self, c1, c2, t):
        """Linear interpolate between two hex colors."""
        r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
        r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        return f"#{r:02x}{g:02x}{b:02x}"
    
    def _get_current_bg(self):
        """Get current background color based on state."""
        if self._is_pressed:
            return self.active_color
        elif self._is_hovered:
            return self.hover_color
        return self.bg_color
    
    def _draw(self):
        self.delete("all")
        
        cx, cy = self.size / 2, self.size / 2
        bg_color = self._get_current_bg()
        
        if self.circular:
            padding = 3
            radius = (self.size / 2) - padding
            
            if self._is_hovered and not self._is_pressed:
                glow_radius = radius + 2
                self.create_oval(
                    cx - glow_radius, cy - glow_radius,
                    cx + glow_radius, cy + glow_radius,
                    fill="", outline=self.glow_color, width=2
                )
            
            self.create_oval(
                cx - radius, cy - radius,
                cx + radius, cy + radius,
                fill=bg_color, outline=self._darken(bg_color, 0.15), width=1
            )
        else:
            padding = 4
            r = 8
            x1, y1 = padding, padding
            x2, y2 = self.size - padding, self.size - padding
            
            points = [
                x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
                x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
                x1, y2, x1, y2 - r, x1, y1 + r, x1, y1
            ]
            self.create_polygon(points, smooth=True, fill=bg_color, 
                              outline=self._darken(bg_color, 0.15), width=1)
        
        self._draw_icon(cx, cy)
    
    def _draw_icon(self, cx, cy):
        """Draw the transport icon."""
        icon_size = self.size * 0.32
        color = self.icon_color
        
        if self.icon_type == self.PLAY:
            offset = icon_size * 0.12
            points = [
                cx - icon_size * 0.4 + offset, cy - icon_size * 0.5,
                cx + icon_size * 0.5 + offset, cy,
                cx - icon_size * 0.4 + offset, cy + icon_size * 0.5
            ]
            self.create_polygon(points, fill=color, outline=color, smooth=False)
            
        elif self.icon_type == self.PAUSE:
            bar_width = icon_size * 0.28
            bar_height = icon_size * 0.9
            gap = icon_size * 0.2
            
            self.create_rectangle(
                cx - gap - bar_width, cy - bar_height / 2,
                cx - gap, cy + bar_height / 2,
                fill=color, outline=color
            )
            self.create_rectangle(
                cx + gap, cy - bar_height / 2,
                cx + gap + bar_width, cy + bar_height / 2,
                fill=color, outline=color
            )
            
        elif self.icon_type == self.STOP:
            sq_size = icon_size * 0.7
            r = 2
            x1, y1 = cx - sq_size / 2, cy - sq_size / 2
            x2, y2 = cx + sq_size / 2, cy + sq_size / 2
            points = [
                x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
                x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
                x1, y2, x1, y2 - r, x1, y1 + r, x1, y1
            ]
            self.create_polygon(points, smooth=True, fill=color, outline=color)
            
        elif self.icon_type == self.SKIP_BACK:
            tri_size = icon_size * 0.45
            bar_width = icon_size * 0.15
            
            self.create_rectangle(
                cx - tri_size - bar_width * 0.5, cy - tri_size * 0.6,
                cx - tri_size + bar_width * 0.5, cy + tri_size * 0.6,
                fill=color, outline=color
            )
            self.create_polygon(
                cx + tri_size * 0.3, cy - tri_size * 0.6,
                cx - tri_size * 0.4, cy,
                cx + tri_size * 0.3, cy + tri_size * 0.6,
                fill=color, outline=color
            )
            
        elif self.icon_type == self.SKIP_FORWARD:
            tri_size = icon_size * 0.45
            bar_width = icon_size * 0.15
            
            self.create_rectangle(
                cx + tri_size - bar_width * 0.5, cy - tri_size * 0.6,
                cx + tri_size + bar_width * 0.5, cy + tri_size * 0.6,
                fill=color, outline=color
            )
            self.create_polygon(
                cx - tri_size * 0.3, cy - tri_size * 0.6,
                cx + tri_size * 0.4, cy,
                cx - tri_size * 0.3, cy + tri_size * 0.6,
                fill=color, outline=color
            )
    
    def _darken(self, color, factor):
        """Darken a hex color."""
        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        r = int(r * (1 - factor))
        g = int(g * (1 - factor))
        b = int(b * (1 - factor))
        return f"#{r:02x}{g:02x}{b:02x}"
    
    def _lighten(self, color, factor):
        """Lighten a hex color."""
        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        r = min(255, int(r + (255 - r) * factor))
        g = min(255, int(g + (255 - g) * factor))
        b = min(255, int(b + (255 - b) * factor))
        return f"#{r:02x}{g:02x}{b:02x}"
    
    def _on_press(self, event):
        self._is_pressed = True
        self._draw()
    
    def _on_release(self, event):
        self._is_pressed = False
        if self.command:
            self.command()
        self._draw()
    
    def _on_hover(self, event):
        self._is_hovered = True
        self._draw()
    
    def _on_leave(self, event):
        self._is_hovered = False
        self._is_pressed = False
        self._draw()
    
    def set_icon(self, icon_type):
        """Change the icon type."""
        self.icon_type = icon_type
        
        if icon_type == self.PLAY:
            self.bg_color = Theme.PLAY_BG
            self.hover_color = Theme.PLAY_HOVER
            self.active_color = Theme.PLAY_ACTIVE
            self.icon_color = Theme.PLAY_ICON
            self.glow_color = Theme.PLAY_GLOW
        elif icon_type == self.PAUSE:
            self.bg_color = Theme.PAUSE_BG
            self.hover_color = Theme.PAUSE_HOVER
            self.active_color = Theme.PAUSE_ACTIVE
            self.icon_color = Theme.PAUSE_ICON
            self.glow_color = Theme.PAUSE_GLOW
        
        self._draw()
    
    def set_colors(self, bg_color=None, hover_color=None, icon_color=None):
        """Update button colors."""
        if bg_color: self.bg_color = bg_color
        if hover_color: self.hover_color = hover_color
        if icon_color: self.icon_color = icon_color
        self._draw()


def draw_add_button(canvas, x1, y1, x2, y2, hovered=False):
    """Draw a professional rounded '+' button on a canvas. Returns button coords."""
    width = x2 - x1
    height = y2 - y1
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    r = 4
    
    if hovered:
        bg_color = Theme.TRANSPORT_HOVER
        icon_color = '#ffffff'
        border_color = Theme.ACCENT
    else:
        bg_color = Theme.TRANSPORT_BG
        icon_color = Theme.TRANSPORT_ICON
        border_color = '#555555'
    
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1
    ]
    canvas.create_polygon(points, smooth=True, fill=bg_color, outline=border_color, width=1)
    
    plus_size = min(width, height) * 0.35
    line_width = 2
    
    canvas.create_line(cx - plus_size, cy, cx + plus_size, cy, 
                      fill=icon_color, width=line_width, capstyle='round')
    canvas.create_line(cx, cy - plus_size, cx, cy + plus_size, 
                      fill=icon_color, width=line_width, capstyle='round')
    
    return (x1, y1, x2, y2)
