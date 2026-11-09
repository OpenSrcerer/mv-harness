"""Audio emotion words from the mood stage, and the lyric-vs-audio agreement flag (PLAN §8 sections.emotion).

Arousal is more reliable than valence (PLAN §5 mood), so the audio word leans on arousal and the agreement
test forgives neutral valence.
"""
from __future__ import annotations

from typing import Any, Mapping

__all__ = ["audio_word", "agree", "LEXICON"]

#: word -> (valence -1..1, arousal -1..1)
LEXICON: dict[str, tuple[float, float]] = {
    "euphoric": (1, 1), "ecstatic": (1, 1), "elated": (1, 1), "joyful": (1, 0.6), "happy": (1, 0.4),
    "excited": (0.8, 1), "triumphant": (1, 0.9), "victorious": (1, 0.9), "playful": (0.8, 0.5), "hopeful": (0.8, 0.2),
    "confident": (0.6, 0.6), "proud": (0.6, 0.5), "cocky": (0.4, 0.7), "energetic": (0.4, 1), "epic": (0.4, 1),
    "warm": (0.8, 0), "tender": (0.8, -0.4), "loving": (0.9, -0.1), "romantic": (0.8, -0.1), "peaceful": (0.7, -0.8),
    "calm": (0.4, -0.8), "serene": (0.7, -0.9), "still": (0.2, -0.9), "content": (0.6, -0.5), "dreamy": (0.4, -0.6),
    "relaxed": (0.6, -0.8), "nostalgic": (0.1, -0.4), "bittersweet": (0, -0.2), "wistful": (-0.2, -0.4),
    "longing": (-0.3, -0.1), "yearning": (-0.3, 0), "melancholic": (-0.6, -0.4), "melancholy": (-0.6, -0.4),
    "sad": (-0.8, -0.5), "sorrowful": (-0.9, -0.5), "grief": (-1, -0.3), "grieving": (-1, -0.3), "lonely": (-0.7, -0.6),
    "somber": (-0.6, -0.6), "sombre": (-0.6, -0.6), "dark": (-0.6, 0.1), "haunting": (-0.4, -0.2), "eerie": (-0.5, 0),
    "anxious": (-0.6, 0.7), "tense": (-0.5, 0.7), "nervous": (-0.5, 0.6), "fearful": (-0.8, 0.7), "afraid": (-0.8, 0.6),
    "angry": (-0.8, 0.9), "furious": (-0.9, 1), "aggressive": (-0.6, 1), "defiant": (-0.3, 0.8), "menacing": (-0.7, 0.6),
    "desperate": (-0.8, 0.8), "frantic": (-0.5, 1), "bitter": (-0.7, 0.3), "mocking": (-0.2, 0.7), "taunting": (-0.2, 0.8),
    "heroic": (0.8, 0.8), "uplifting": (0.9, 0.6), "release": (0.8, 0.8), "relief": (0.7, -0.2), "neutral": (0, 0),
    "intense": (-0.1, 0.9), "powerful": (0.3, 0.9), "violent": (-0.9, 1), "chaotic": (-0.4, 1), "detached": (-0.2, -0.6),
    "numb": (-0.5, -0.8), "resigned": (-0.5, -0.6), "reflective": (0, -0.5), "mysterious": (-0.1, -0.1),
}


def audio_word(m: Mapping[str, Any] | None) -> str | None:
    """'tense (energetic, dark)' from a mood events item (valence/arousal 0..1, tags)."""
    if not m:
        return None
    try:
        v, a = float(m["valence"]), float(m["arousal"])
    except (KeyError, TypeError, ValueError):
        return None
    if a >= 0.6:
        w = "euphoric" if v >= 0.55 else ("tense" if v < 0.45 else "energetic")
    elif a < 0.4:
        w = "serene" if v >= 0.55 else ("somber" if v < 0.45 else "calm")
    else:
        w = "warm" if v >= 0.55 else ("melancholic" if v < 0.45 else "neutral")
    tags = [str(t) for t in (m.get("tags") or [])][:2]
    return f"{w} ({', '.join(tags)})" if tags else w


def _cat(x: float, lo: float = -0.25, hi: float = 0.25) -> int:
    return -1 if x < lo else (1 if x > hi else 0)


def agree(lyric_word: str | None, m: Mapping[str, Any] | None) -> bool | None:
    """True when the lyric emotion and the audio mood point the same way (valence and arousal category, neutral
    forgiven); None when either side is unknown."""
    if not lyric_word or not m:
        return None
    words = [w.strip(" ,.;:!?()").lower() for w in str(lyric_word).split()]
    hits = [LEXICON[w] for w in words if w in LEXICON]
    if not hits:
        return None
    lv = sum(h[0] for h in hits) / len(hits)
    la = sum(h[1] for h in hits) / len(hits)
    try:
        av = (float(m["valence"]) - 0.5) * 2.0
        aa = (float(m["arousal"]) - 0.5) * 2.0
    except (KeyError, TypeError, ValueError):
        return None
    cv_l, cv_a = _cat(lv), _cat(av, -0.15, 0.15)
    ca_l, ca_a = _cat(la), _cat(aa, -0.2, 0.2)
    v_ok = cv_l == cv_a or cv_l == 0 or cv_a == 0
    a_ok = ca_l == ca_a or ca_l == 0 or ca_a == 0
    return bool(v_ok and a_ok)
