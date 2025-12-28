"""Theme configuration for WaveSync."""

class Theme:
    # Modern Dark Theme Palette (inspired by VS Code / Modern IDEs)
    BG_MAIN = '#1e1e1e'      # Main window background
    BG_PANEL = '#252526'     # Toolbars, panels
    BG_HOVER = '#2a2d2e'     # Hover state
    BG_ACTIVE = '#37373d'    # Active/Pressed state
    BG_INPUT = '#3c3c3c'     # Input fields
    
    FG_PRIMARY = '#cccccc'   # Main text
    FG_SECONDARY = '#858585' # Secondary text / labels
    FG_DISABLED = '#505050'  # Disabled text
    FG_HIGHLIGHT = '#ffffff' # Bright text

    # Accents
    ACCENT = '#007acc'       # Primary accent (Blue)
    ACCENT_HOVER = '#0062a3'
    
    SUCCESS = '#89d185'      # Green
    SUCCESS_HOVER = '#6bb566'
    ERROR = '#f48771'        # Red
    ERROR_HOVER = '#d9664d'
    WARNING = '#cca700'      # Yellow

    BORDER = '#3e3e42'       # Borders/Separators
    PLAYHEAD = '#d7ba7d'     # Yellow/Orange for playhead
    
    # Professional Transport Button Colors
    # Play button - vibrant green
    PLAY_BG = '#2d8a4e'
    PLAY_HOVER = '#3ba55d'
    PLAY_ACTIVE = '#248a46'
    PLAY_ICON = '#ffffff'
    PLAY_GLOW = '#4cc76f'
    
    # Pause button - amber/orange
    PAUSE_BG = '#d4a016'
    PAUSE_HOVER = '#e6b422'
    PAUSE_ACTIVE = '#c4940e'
    PAUSE_ICON = '#1e1e1e'
    PAUSE_GLOW = '#f0c432'
    
    # Stop button - subtle red
    STOP_BG = '#c94a4a'
    STOP_HOVER = '#dc5c5c'
    STOP_ACTIVE = '#b83c3c'
    STOP_ICON = '#ffffff'
    STOP_GLOW = '#e87070'
    
    # Generic transport buttons (skip, etc)
    TRANSPORT_BG = '#404040'
    TRANSPORT_HOVER = '#525252'
    TRANSPORT_ACTIVE = '#363636'
    TRANSPORT_ICON = '#e0e0e0'
    TRANSPORT_GLOW = '#666666'
    
    # Track Colors (Pastels for visibility)
    TRACK_VIDEO = '#c586c0'  # Purple
    TRACK_AUDIO_1 = '#4ec9b0' # Teal
    TRACK_AUDIO_2 = '#569cd6' # Blue
    TRACK_AUDIO_3 = '#ce9178' # Orange
    TRACK_AUDIO_4 = '#dcdcaa' # Yellow

    # Fonts
    FONT_FAMILY = 'Segoe UI'
    FONT_MAIN = ('Segoe UI', 10)
    FONT_BOLD = ('Segoe UI', 10, 'bold')
    FONT_LARGE = ('Segoe UI', 12)
    FONT_LARGE_BOLD = ('Segoe UI', 12, 'bold')
    FONT_TITLE = ('Segoe UI', 16, 'bold')
    FONT_MONO = ('Consolas', 12)
    FONT_MONO_LARGE = ('Consolas', 16, 'bold')

    @staticmethod
    def configure_style(style):
        """Configure ttk style."""
        style.theme_use('clam')
        
        # General background
        style.configure('.', 
            background=Theme.BG_MAIN, 
            foreground=Theme.FG_PRIMARY,
            font=Theme.FONT_MAIN,
            borderwidth=0
        )
        
        # Frames
        style.configure('TFrame', background=Theme.BG_MAIN)
        style.configure('Panel.TFrame', background=Theme.BG_PANEL)
        
        # Labels
        style.configure('TLabel', background=Theme.BG_MAIN, foreground=Theme.FG_PRIMARY)
        style.configure('Panel.TLabel', background=Theme.BG_PANEL, foreground=Theme.FG_PRIMARY)
        style.configure('Status.TLabel', background=Theme.ACCENT, foreground=Theme.FG_HIGHLIGHT, padding=(10, 2))
        style.configure('Title.TLabel', font=Theme.FONT_TITLE, foreground=Theme.FG_HIGHLIGHT)
        
        # Buttons (TTK)
        style.configure('TButton', 
            background=Theme.BG_INPUT, 
            foreground=Theme.FG_PRIMARY,
            borderwidth=0,
            focuscolor=Theme.BG_ACTIVE,
            padding=(15, 8),
            font=Theme.FONT_MAIN
        )
        style.map('TButton',
            background=[('active', Theme.BG_HOVER), ('pressed', Theme.BG_ACTIVE)],
            foreground=[('disabled', Theme.FG_DISABLED)]
        )

        # Primary Action Button
        style.configure('Action.TButton',
            background=Theme.ACCENT,
            foreground=Theme.FG_HIGHLIGHT,
            font=Theme.FONT_BOLD
        )
        style.map('Action.TButton',
            background=[('active', Theme.ACCENT_HOVER), ('pressed', Theme.BG_ACTIVE)]
        )

        # Transport Buttons (Custom)
        style.configure('Transport.TButton',
            background=Theme.BG_PANEL,
            foreground=Theme.FG_HIGHLIGHT,
            font=('Segoe UI', 14),
            padding=(10, 5)
        )
        style.map('Transport.TButton',
            background=[('active', Theme.BG_HOVER)]
        )

        # Scales
        style.configure('Horizontal.TScale', 
            background=Theme.BG_PANEL, 
            troughcolor=Theme.BG_INPUT,
            sliderthickness=16,
            sliderlength=24,
            borderwidth=0
        )

