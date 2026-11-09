"""Colour words -> hex for palettes written in plain words ("night blue, lantern amber, rust red").

Deterministic and small on purpose: a base colour word (the last one in the phrase wins, earlier colour
words are blended in), plus modifiers that darken or lighten. Phrases with no known colour word are
returned as unparsed (the meaning stage turns them into an open question for the user).
"""
from __future__ import annotations

import re

__all__ = ["parse_color", "parse_palette", "HEX_RE"]

HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")

BASE: dict[str, str] = {
    # neutrals
    "black": "#000000", "white": "#ffffff", "grey": "#808080", "gray": "#808080", "silver": "#c0c0c0",
    "charcoal": "#36454f", "ash": "#b2beb5", "smoke": "#738276", "bone": "#e3dac9", "ivory": "#fffff0",
    "cream": "#fffdd0", "paper": "#f2ecdc", "beige": "#d9c8a9", "sand": "#c2b280", "khaki": "#c3b091",
    "chrome": "#dbe4eb", "steel": "#71797e", "slate": "#708090", "concrete": "#95978f", "ink": "#1b1b2f",
    # reds / pinks
    "red": "#d32f2f", "crimson": "#dc143c", "scarlet": "#ff2400", "blood": "#8a0303", "ruby": "#9b111e",
    "wine": "#722f37", "burgundy": "#800020", "maroon": "#800000", "cherry": "#d2042d", "rose": "#e8a0b0",
    "pink": "#ffc0cb", "magenta": "#ff00ff", "fuchsia": "#ff00ff", "coral": "#ff7f50", "salmon": "#fa8072",
    "rust": "#b7410e", "brick": "#a33e2b", "neon": "#ff2fd0",
    # oranges / yellows / browns
    "orange": "#ff8c00", "amber": "#ffbf00", "gold": "#d4af37", "golden": "#d4af37", "yellow": "#ffd800",
    "lemon": "#fff44f", "mustard": "#e1ad01", "honey": "#eba937", "copper": "#b87333", "bronze": "#cd7f32",
    "brown": "#6f4e37", "chocolate": "#3d1f0f", "tan": "#d2b48c", "ochre": "#cc7722", "peach": "#ffcba4",
    "lantern": "#f2a541", "fire": "#e25822", "flame": "#e25822", "ember": "#c1440e", "sunset": "#fd5e53",
    "candle": "#f8d58c", "sepia": "#704214",
    # greens
    "green": "#2e8b57", "emerald": "#50c878", "jade": "#00a86b", "lime": "#bfff00", "olive": "#808000",
    "moss": "#8a9a5b", "forest": "#228b22", "mint": "#98ff98", "sage": "#9caf88", "acid": "#b0bf1a",
    "toxic": "#a3ff00",
    # blues / cyans
    "blue": "#1f4e9c", "navy": "#000080", "cobalt": "#0047ab", "azure": "#007fff", "sky": "#87ceeb",
    "cyan": "#00d1d1", "teal": "#008080", "turquoise": "#40e0d0", "aqua": "#00ffff", "sapphire": "#0f52ba",
    "indigo": "#4b0082", "ice": "#d6f1ff", "ocean": "#1d4e89", "sea": "#2e8bc0", "harbour": "#3e7cb1",
    "harbor": "#3e7cb1", "denim": "#1560bd", "petrol": "#005f6a", "electric": "#7df9ff",
    # purples
    "purple": "#6a0dad", "violet": "#8f00ff", "lavender": "#b57edc", "lilac": "#c8a2c8", "plum": "#8e4585",
    "mauve": "#e0b0ff", "amethyst": "#9966cc", "ultraviolet": "#5f4b8b",
}
DARKEN = {"dark": 0.45, "deep": 0.4, "night": 0.55, "midnight": 0.65, "shadow": 0.5, "dim": 0.3, "muted": 0.2,
          "dusty": 0.15}
LIGHTEN = {"light": 0.45, "pale": 0.55, "pastel": 0.5, "soft": 0.25, "bright": 0.15, "washed": 0.4, "faded": 0.35}
_WORD = re.compile(r"[a-z]+")


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, int(round(c)))):02x}" for c in rgb)


def _mix(a: tuple[float, float, float], b: tuple[float, float, float], w: float) -> tuple[float, float, float]:
    return tuple(x + (y - x) * w for x, y in zip(a, b))  # type: ignore[return-value]


def parse_color(phrase: str) -> str | None:
    """'#1b2a49' -> itself; 'night blue' -> a darkened blue; 'rust red' -> rust blended into red; None if unknown."""
    m = HEX_RE.search(phrase)
    if m:
        return _hex(_rgb(m.group(0))).lower()
    words = _WORD.findall(phrase.lower())
    colours = [w for w in words if w in BASE]
    if not colours:
        return None
    rgb: tuple[float, float, float] = tuple(float(c) for c in _rgb(BASE[colours[-1]]))  # type: ignore[assignment]
    for w in colours[:-1]:
        rgb = _mix(rgb, tuple(float(c) for c in _rgb(BASE[w])), 0.35)  # type: ignore[arg-type]
    for w in words:
        if w in DARKEN and w not in colours:
            rgb = _mix(rgb, (0.0, 0.0, 0.0), DARKEN[w])
        elif w in LIGHTEN and w not in colours:
            rgb = _mix(rgb, (255.0, 255.0, 255.0), LIGHTEN[w])
    return _hex(rgb)


def parse_palette(items: list[str]) -> tuple[list[str], list[str], list[str]]:
    """-> (hex colours, the user's words for each parsed colour, unparsed phrases)."""
    hexes: list[str] = []
    names: list[str] = []
    bad: list[str] = []
    for raw in items:
        s = str(raw).strip().strip(".").strip()
        if not s:
            continue
        found = HEX_RE.findall(s)
        if len(found) > 1:
            for f in found:
                hexes.append(_hex(_rgb(f)))
                names.append(f)
            continue
        c = parse_color(s)
        if c is None:
            bad.append(s)
        else:
            hexes.append(c)
            names.append(s)
    return hexes, names, bad
