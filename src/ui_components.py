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
        
        # Draw rounded rectangle
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
        
        # Draw text
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
