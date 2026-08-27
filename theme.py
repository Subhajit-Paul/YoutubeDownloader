"""Design system — the single source of truth for all three front-ends.

The Qt apps and the TUI previously carried three unrelated palettes (indigo,
cyan, blue), so the product read as three unrelated tools. Everything visual now
derives from the tokens below.

Principles
  - One accent, used only for the primary action and focus. Colour carries
    meaning; if everything is accented, nothing is.
  - A neutral surface ramp does the structural work, not borders.
  - An 8pt spacing rhythm, so alignment is a consequence of the system rather
    than something to be hand-tuned per screen.
  - Contrast is verified (see contrast_ratio and tests/test_theme.py), not
    eyeballed.
"""

# ── Surfaces ─────────────────────────────────────────────────────────────────
# A ramp, not a set: each step is a consistent lift, so elevation reads even
# without borders or shadows.
BG = "#0A0C10"          # window
SURFACE = "#11141A"     # inputs, inset areas
CARD = "#161A21"        # raised panels
ELEVATED = "#1C212A"    # hover / active panels
BORDER = "#212733"      # hairlines
BORDER_STRONG = "#2C3441"

# ── Text ─────────────────────────────────────────────────────────────────────
TEXT = "#E8EBF0"        # primary
MUTED = "#98A2B3"       # secondary / labels
FAINT = "#6B7686"       # tertiary / placeholders
ON_ACCENT = "#FFFFFF"

# ── Accent ───────────────────────────────────────────────────────────────────
ACCENT = "#6D5EF7"
ACCENT_HOVER = "#8375F9"
ACCENT_PRESSED = "#5B4CE0"
ACCENT_DIM = "#1A1733"  # tinted fill behind accent content

# ── Semantic ─────────────────────────────────────────────────────────────────
SUCCESS = "#3FB950"
WARNING = "#D29922"
ERROR = "#F85149"

# ── Per-app identity ─────────────────────────────────────────────────────────
# The chrome is identical across apps; only the mark's glyph and tint differ, so
# the family reads as one product while each app stays recognisable.
# 'on_tint' is per-identity because cyan is a light hue: white on it is 2.4:1,
# unreadable. Dark text on a light tint is the correct pairing, not an exception.
IDENTITY = {
    "video": {"name": "Video Downloader", "glyph": "▶",
              "tint": "#6D5EF7", "on_tint": "#FFFFFF"},
    "audio": {"name": "Audio Downloader", "glyph": "♪",
              "tint": "#22B8CF", "on_tint": "#04222B"},
    "tui":   {"name": "Downloader",       "glyph": "▶",
              "tint": "#6D5EF7", "on_tint": "#FFFFFF"},
}

# ── Spacing (8pt rhythm) ─────────────────────────────────────────────────────
SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "2xl": 32}

# ── Radius ───────────────────────────────────────────────────────────────────
RADIUS_CONTROL = 8
RADIUS_CARD = 12
RADIUS_PANEL = 16

# ── Type scale ───────────────────────────────────────────────────────────────
FONT_STACK = ('-apple-system, "Segoe UI Variable Text", "Segoe UI", Roboto, '
              '"Helvetica Neue", Arial, sans-serif')
MONO_STACK = ('"SF Mono", "Cascadia Code", "JetBrains Mono", Consolas, '
              '"Liberation Mono", monospace')

TYPE = {
    "display": (28, 600),
    "title":   (20, 600),
    "body":    (14, 400),
    "label":   (13, 500),
    "caption": (12, 400),
    "micro":   (11, 500),
}

CONTROL_HEIGHT = 44
CONTROL_HEIGHT_SM = 34


# ── Contrast ─────────────────────────────────────────────────────────────────

def _srgb_to_linear(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_colour):
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return (0.2126 * _srgb_to_linear(r)
            + 0.7152 * _srgb_to_linear(g)
            + 0.0722 * _srgb_to_linear(b))


def contrast_ratio(fg, bg):
    """WCAG 2.1 contrast ratio between two hex colours (1.0 – 21.0)."""
    a, b = relative_luminance(fg), relative_luminance(bg)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)
