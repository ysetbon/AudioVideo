import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
from PIL import Image, ImageDraw, ImageFilter, ImageTk, ImageFont
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
    UNDO = "undo"
    REDO = "redo"

    _MDL2_FONT_PATH = None
    
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
        self._canvas_bg = canvas_bg
        self._image_item = None
        self._images = {}
        
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
        
        self.configure(cursor="hand2")
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
        state = "pressed" if self._is_pressed else "hover" if self._is_hovered else "normal"
        image = self._get_image(state)

        if self._image_item is None:
            self._image_item = self.create_image(
                self.size / 2, self.size / 2, image=image, anchor="center"
            )
        else:
            self.itemconfig(self._image_item, image=image)
    
    def _get_image(self, state):
        if state not in self._images:
            bg = {"normal": self.bg_color, "hover": self.hover_color, "pressed": self.active_color}[state]
            self._images[state] = self._render_image(
                bg_color=bg,
                show_glow=(state == "hover"),
            )
        return self._images[state]

    def _render_image(self, *, bg_color, show_glow):
        # Render at higher resolution and downsample for anti-aliasing.
        scale = 4
        px = int(self.size * scale)
        pad = int((3 if self.circular else 4) * scale)

        img = Image.new("RGBA", (px, px), (0, 0, 0, 0))

        if show_glow:
            glow = Image.new("RGBA", (px, px), (0, 0, 0, 0))
            glow_draw = ImageDraw.Draw(glow)
            inset = max(0, pad - int(2 * scale))
            glow_box = [inset, inset, px - inset, px - inset]
            glow_color = self._hex_to_rgba(self.glow_color, 110)
            if self.circular:
                glow_draw.ellipse(glow_box, fill=glow_color)
            else:
                r = int(self._corner_radius() * scale)
                glow_draw.rounded_rectangle(glow_box, radius=r, fill=glow_color)
            glow = glow.filter(ImageFilter.GaussianBlur(radius=int(2.8 * scale)))
            img.alpha_composite(glow)

        draw = ImageDraw.Draw(img)
        box = [pad, pad, px - pad, px - pad]
        border = self._hex_to_rgba(self._darken(bg_color, 0.18), 255)
        fill = self._hex_to_rgba(bg_color, 255)

        if self.circular:
            draw.ellipse(box, fill=fill, outline=border, width=max(1, scale))
        else:
            r = int(self._corner_radius() * scale)
            draw.rounded_rectangle(box, radius=r, fill=fill, outline=border, width=max(1, scale))

        # Subtle highlight for depth.
        highlight = Image.new("RGBA", (px, px), (0, 0, 0, 0))
        h = ImageDraw.Draw(highlight)
        hx1 = pad + int(2.0 * scale)
        hy1 = pad + int(1.2 * scale)
        hx2 = px - pad - int(2.0 * scale)
        hy2 = int(px / 2)
        h_color = (255, 255, 255, 28)
        if self.circular:
            h.ellipse([hx1, hy1, hx2, hy2], fill=h_color)
        else:
            r = int(self._corner_radius() * scale)
            h.rounded_rectangle([hx1, hy1, hx2, hy2], radius=r, fill=h_color)
        highlight = highlight.filter(ImageFilter.GaussianBlur(radius=int(1.2 * scale)))
        img.alpha_composite(highlight)

        self._draw_icon_pil(img, scale=scale)

        img = img.resize((self.size, self.size), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(img, master=self)

    def _corner_radius(self):
        return max(6, int(self.size * 0.18))

    def _hex_to_rgba(self, color, alpha=255):
        color = color.lstrip("#")
        return (int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16), alpha)

    def _draw_icon_pil(self, img, *, scale):
        import math
        import os

        px = img.size[0]
        draw = ImageDraw.Draw(img)
        cx, cy = px / 2, px / 2
        icon_size = px * 0.38

        def polygon(points, *, fill):
            draw.polygon(points, fill=fill)

        def rounded_rect(x1, y1, x2, y2, *, radius, fill):
            draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill)

        color = self._hex_to_rgba(self.icon_color, 255)

        # Slight icon shadow for contrast (especially for light icons).
        shadow = (0, 0, 0, 55)
        shadow_offset = int(0.6 * scale)

        def draw_with_shadow(draw_fn):
            draw_fn(offset=(shadow_offset, shadow_offset), fill=shadow)
            draw_fn(offset=(0, 0), fill=color)

        if self.icon_type == self.PLAY:
            play_x_offset = icon_size * 0.12

            def _play(*, offset, fill):
                dx, dy = offset
                points = [
                    cx - icon_size * 0.42 + play_x_offset + dx, cy - icon_size * 0.55 + dy,
                    cx + icon_size * 0.56 + play_x_offset + dx, cy + dy,
                    cx - icon_size * 0.42 + play_x_offset + dx, cy + icon_size * 0.55 + dy,
                ]
                polygon(points, fill=fill)

            draw_with_shadow(_play)

        elif self.icon_type == self.PAUSE:
            bar_w = icon_size * 0.26
            bar_h = icon_size * 0.95
            gap = icon_size * 0.22
            radius = int(2.2 * scale)

            def _pause(*, offset, fill):
                x1 = cx - gap - bar_w + offset[0]
                x2 = cx - gap + offset[0]
                y1 = cy - bar_h / 2 + offset[1]
                y2 = cy + bar_h / 2 + offset[1]
                rounded_rect(x1, y1, x2, y2, radius=radius, fill=fill)

                x1 = cx + gap + offset[0]
                x2 = cx + gap + bar_w + offset[0]
                rounded_rect(x1, y1, x2, y2, radius=radius, fill=fill)

            draw_with_shadow(_pause)

        elif self.icon_type == self.STOP:
            sq = icon_size * 0.74
            r = int(3.0 * scale)

            def _stop(*, offset, fill):
                x1, y1 = cx - sq / 2 + offset[0], cy - sq / 2 + offset[1]
                x2, y2 = cx + sq / 2 + offset[0], cy + sq / 2 + offset[1]
                rounded_rect(x1, y1, x2, y2, radius=r, fill=fill)

            draw_with_shadow(_stop)

        elif self.icon_type in (self.SKIP_BACK, self.SKIP_FORWARD):
            tri = icon_size * 0.50
            bar_w = icon_size * 0.16
            tri_h = tri * 0.78

            def _skip(*, offset, fill):
                if self.icon_type == self.SKIP_BACK:
                    bar_x = cx - tri - bar_w * 0.55 + offset[0]
                    tri_points = [
                        cx + tri * 0.34 + offset[0], cy - tri_h + offset[1],
                        cx - tri * 0.46 + offset[0], cy + offset[1],
                        cx + tri * 0.34 + offset[0], cy + tri_h + offset[1],
                    ]
                else:
                    bar_x = cx + tri + bar_w * 0.55 + offset[0] - bar_w
                    tri_points = [
                        cx - tri * 0.34 + offset[0], cy - tri_h + offset[1],
                        cx + tri * 0.46 + offset[0], cy + offset[1],
                        cx - tri * 0.34 + offset[0], cy + tri_h + offset[1],
                    ]

                x1 = bar_x
                y1 = cy - tri_h + offset[1]
                x2 = bar_x + bar_w
                y2 = cy + tri_h + offset[1]
                rounded_rect(x1, y1, x2, y2, radius=int(1.8 * scale), fill=fill)
                polygon(tri_points, fill=fill)

            draw_with_shadow(_skip)

        elif self.icon_type in (self.UNDO, self.REDO):
            font_path = self._resolve_mdl2_font_path(os)
            if font_path:
                try:
                    glyph = chr(0xE7A7 if self.icon_type == self.UNDO else 0xE7A6)
                    target = px * 0.68
                    font_size = max(8, int(px * 0.85))

                    for _ in range(4):
                        font = ImageFont.truetype(font_path, size=font_size)
                        bbox = draw.textbbox((0, 0), glyph, font=font)
                        w = bbox[2] - bbox[0]
                        h = bbox[3] - bbox[1]
                        if w <= 0 or h <= 0:
                            break
                        fit = min(target / w, target / h)
                        new_size = max(8, int(font_size * fit))
                        if abs(new_size - font_size) <= 1:
                            break
                        font_size = new_size

                    font = ImageFont.truetype(font_path, size=font_size)
                    bbox = draw.textbbox((0, 0), glyph, font=font)
                    w = bbox[2] - bbox[0]
                    h = bbox[3] - bbox[1]
                    x = cx - (w / 2) - bbox[0]
                    y = cy - (h / 2) - bbox[1] + (px * 0.02)

                    shadow = (0, 0, 0, 55)
                    shadow_offset = max(1, int(0.7 * scale))
                    draw.text((x + shadow_offset, y + shadow_offset), glyph, font=font, fill=shadow)
                    draw.text((x, y), glyph, font=font, fill=color)
                    return
                except (OSError, ValueError):
                    pass

            # Fallback: simple stroked curved arrow (non-Windows environments).
            def stroke(points, *, fill, width, cap_start=True, cap_end=True):
                try:
                    draw.line(points, fill=fill, width=width, joint="curve")
                except TypeError:
                    draw.line(points, fill=fill, width=width)

                cap_r = width / 2
                if cap_start:
                    x0, y0 = points[0]
                    draw.ellipse([x0 - cap_r, y0 - cap_r, x0 + cap_r, y0 + cap_r], fill=fill)
                if cap_end:
                    x1, y1 = points[-1]
                    draw.ellipse([x1 - cap_r, y1 - cap_r, x1 + cap_r, y1 + cap_r], fill=fill)

            stroke_w = max(1, int(icon_size * 0.15))
            arrow_len = stroke_w * 2.0
            arrow_w = stroke_w * 1.35
            r = icon_size * 0.63
            cy2 = cy + icon_size * 0.05

            is_redo = self.icon_type == self.REDO
            end_deg = 45 if is_redo else 135
            span_deg = 175
            start_deg = (end_deg + span_deg) % 360 if is_redo else (end_deg - span_deg) % 360

            end_rad = math.radians(end_deg)
            tip = (cx + r * math.cos(end_rad), cy2 - r * math.sin(end_rad))

            if is_redo:
                tx, ty = math.sin(end_rad), math.cos(end_rad)
            else:
                tx, ty = -math.sin(end_rad), -math.cos(end_rad)
            t_len = math.hypot(tx, ty) or 1.0
            tx, ty = tx / t_len, ty / t_len
            nx, ny = -ty, tx

            def arc_points():
                if is_redo:
                    diff = (start_deg - end_deg) % 360
                    steps = max(24, int(diff / 4))
                    for i in range(steps + 1):
                        a = math.radians(start_deg - (diff * i / steps))
                        yield (cx + r * math.cos(a), cy2 - r * math.sin(a))
                else:
                    diff = (end_deg - start_deg) % 360
                    steps = max(24, int(diff / 4))
                    for i in range(steps + 1):
                        a = math.radians(start_deg + (diff * i / steps))
                        yield (cx + r * math.cos(a), cy2 - r * math.sin(a))

            arc = list(arc_points())
            base = (tip[0] - tx * arrow_len, tip[1] - ty * arrow_len)
            arm1 = (base[0] + nx * arrow_w, base[1] + ny * arrow_w)
            arm2 = (base[0] - nx * arrow_w, base[1] - ny * arrow_w)

            def _undo_redo(*, offset, fill):
                dx, dy = offset
                arc2 = [(x + dx, y + dy) for x, y in arc]
                if arc2:
                    stroke(arc2, fill=fill, width=stroke_w, cap_start=True, cap_end=False)

                tip2 = (tip[0] + dx, tip[1] + dy)
                arm1_2 = (arm1[0] + dx, arm1[1] + dy)
                arm2_2 = (arm2[0] + dx, arm2[1] + dy)
                stroke([arm1_2, tip2], fill=fill, width=stroke_w, cap_start=True, cap_end=True)
                stroke([arm2_2, tip2], fill=fill, width=stroke_w, cap_start=True, cap_end=True)

            draw_with_shadow(_undo_redo)

    @classmethod
    def _resolve_mdl2_font_path(cls, os_mod):
        if cls._MDL2_FONT_PATH is not None:
            return cls._MDL2_FONT_PATH or None

        candidates = []
        if os_mod.name == "nt":
            windir = os_mod.environ.get("WINDIR", r"C:\Windows")
            candidates.append(os_mod.path.join(windir, "Fonts", "segmdl2.ttf"))
            candidates.append(os_mod.path.join(windir, "Fonts", "SegoeIcons.ttf"))

        for path in candidates:
            try:
                if os_mod.path.exists(path):
                    cls._MDL2_FONT_PATH = path
                    return path
            except OSError:
                continue

        cls._MDL2_FONT_PATH = ""
        return None
    
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

        self._images.clear()
        self._draw()
    
    def set_colors(self, bg_color=None, hover_color=None, icon_color=None):
        """Update button colors."""
        if bg_color: self.bg_color = bg_color
        if hover_color: self.hover_color = hover_color
        if icon_color: self.icon_color = icon_color
        self._images.clear()
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
