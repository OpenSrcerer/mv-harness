"""Music-theory helpers for the harmony stage: pitch-class names, Harte labels, chord templates, key profiles.

numpy only (no model, no I/O) so every function is unit-testable on synthetic input.
"""
from __future__ import annotations

import re

import numpy as np

# pitch-class names. Chords keep lv-chordia's own spelling; keys use the conventional spelling of the key signature.
SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MAJOR_NAMES = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
MINOR_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B"]
_ROOT_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def note_pc(name: str) -> int:
    """'C', 'F#', 'Bb', 'Ebb' -> pitch class (C = 0)."""
    name = name.strip()
    pc = _ROOT_PC[name[0].upper()]
    for ch in name[1:]:
        pc += 1 if ch in "#♯" else -1 if ch in "b♭" else 0
    return pc % 12


def key_name(pc: int, mode: str) -> str:
    return f"{(MAJOR_NAMES if mode == 'major' else MINOR_NAMES)[pc % 12]} {mode}"


# key index convention inside the stage: 0..11 = major (tonic pc), 12..23 = minor (tonic pc + 12)
def key_index(pc: int, mode: str) -> int:
    return pc % 12 + (0 if mode == "major" else 12)


def key_from_index(k: int) -> tuple[int, str]:
    return k % 12, ("major" if k < 12 else "minor")


def parse_key_label(s: str) -> tuple[int, str]:
    """'Bb Major' / 'A minor' / 'C:maj' -> (pc, mode)."""
    s = s.strip()
    if ":" in s:
        root, q = s.split(":", 1)
        return note_pc(root), ("minor" if q.startswith("min") else "major")
    root, mode = s.split()[:2]
    return note_pc(root), mode.lower()


def _set_index(k: int) -> int:
    """Pitch-set id of a key: the tonic of its relative major."""
    pc, mode = key_from_index(k)
    return pc if mode == "major" else (pc + 3) % 12


def key_relation(a: int, b: int) -> str:
    """Relation of two key indices: exact | relative (same pitch set) | parallel (same tonic) | fifth (pitch sets one
    step apart on the circle of fifths: C major / G major / E minor / A minor vs F major ...) | other."""
    if a == b:
        return "exact"
    (pa, _ma), (pb, _mb) = key_from_index(a), key_from_index(b)
    sa, sb = _set_index(a), _set_index(b)
    if sa == sb:
        return "relative"
    if pa == pb:
        return "parallel"
    if (sa - sb) % 12 in (5, 7):
        return "fifth"
    return "other"


# ------------------------------------------------------------------------------------------ key profiles
KS_MAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KS_MIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
TP_MAJ = np.array([5.0, 2.0, 3.5, 2.0, 4.5, 4.0, 2.0, 4.5, 2.0, 3.5, 1.5, 4.0])
TP_MIN = np.array([5.0, 2.0, 3.5, 4.5, 2.0, 4.0, 2.0, 4.5, 3.5, 2.0, 1.5, 4.0])
# Albrecht-Shanahan 2013 (corpus derived), a third opinion that is not based on a perception experiment
AS_MAJ = np.array([0.238, 0.006, 0.111, 0.006, 0.137, 0.094, 0.016, 0.214, 0.009, 0.080, 0.008, 0.081])
AS_MIN = np.array([0.220, 0.006, 0.104, 0.123, 0.019, 0.103, 0.012, 0.214, 0.062, 0.022, 0.061, 0.052])

PROFILES = {"ks": (KS_MAJ, KS_MIN), "temperley": (TP_MAJ, TP_MIN), "albrecht": (AS_MAJ, AS_MIN)}


def profile_scores(chroma12: np.ndarray, maj: np.ndarray, mnr: np.ndarray) -> np.ndarray:
    """Pearson correlation of a 12-vector against the 24 rotated profiles (index convention above)."""
    c = np.asarray(chroma12, np.float64)
    out = np.zeros(24)
    if c.std() < 1e-12:
        return out
    cz = (c - c.mean()) / c.std()
    for pc in range(12):
        for j, prof in enumerate((maj, mnr)):
            p = np.roll(prof, pc)
            out[pc + 12 * j] = float(np.mean(cz * (p - p.mean()) / p.std()))
    return out


# ------------------------------------------------------------------------------------------ chord vocabulary
# interval sets (semitones above the root) of the qualities we template-match and the labels lv-chordia emits
QUALITY_INTERVALS: dict[str, tuple[int, ...]] = {
    "maj": (0, 4, 7), "min": (0, 3, 7), "dim": (0, 3, 6), "aug": (0, 4, 8),
    "sus2": (0, 2, 7), "sus4": (0, 5, 7),
    "7": (0, 4, 7, 10), "maj7": (0, 4, 7, 11), "min7": (0, 3, 7, 10), "dim7": (0, 3, 6, 9), "hdim7": (0, 3, 6, 10),
    "9": (0, 4, 7, 10, 2), "maj9": (0, 4, 7, 11, 2), "min9": (0, 3, 7, 10, 2),
    "11": (0, 4, 7, 10, 5), "13": (0, 4, 7, 10, 9),
}
_BASS_INTERVAL = {"1": 0, "b2": 1, "2": 2, "b3": 3, "3": 4, "4": 5, "b5": 6, "5": 7, "#5": 8, "b6": 8, "6": 9, "bb7": 9,
                  "b7": 10, "7": 11, "9": 2, "b9": 1, "11": 5, "13": 9}
_HARTE_RE = re.compile(r"^(?P<root>[A-G][#b]*)(?::(?P<q>[^/]+))?(?:/(?P<bass>.+))?$")


def parse_harte(label: str) -> tuple[int | None, str, int | None]:
    """'D:maj/5' -> (2, 'maj', 9); 'N' -> (None, 'N', None); 'C:sus4(b7)' -> (0, 'sus4', None).
    Quality is returned in the contract vocabulary ('maj', 'min', '7', 'maj7', ...); unknown shapes degrade to their
    nearest simple parent (maj/min) so the label is always usable."""
    label = label.strip()
    if label in ("N", "X", ""):
        return None, "N", None
    m = _HARTE_RE.match(label)
    if not m:
        return None, "N", None
    root = note_pc(m.group("root"))
    q = (m.group("q") or "maj").strip()
    base = re.sub(r"\(.*\)$", "", q)
    if base == "":
        base = "maj"
    if base in ("maj", "min", "dim", "aug", "sus2", "sus4", "7", "maj7", "min7", "dim7", "hdim7", "9", "maj9", "min9", "11", "13"):
        quality = base
    elif base.startswith("min"):
        quality = "min"
    else:
        quality = "maj"
    bass = None
    b = m.group("bass")
    if b is not None:
        if b in _BASS_INTERVAL:
            bass = (root + _BASS_INTERVAL[b]) % 12
        else:
            try:
                bass = note_pc(b)
            except KeyError:
                bass = None
    return root, quality, bass


def harte_label(root_pc: int | None, quality: str, spelling: str | None = None) -> str:
    if root_pc is None or quality == "N":
        return "N"
    return f"{spelling or SHARP[root_pc % 12]}:{quality}"


def chord_tones(root: int, quality: str) -> tuple[int, ...]:
    return tuple((root + i) % 12 for i in QUALITY_INTERVALS.get(quality, (0, 4, 7)))


def chord_template(root: int, quality: str = "maj", overtones: bool = True) -> np.ndarray:
    """A 12-vector template: chord tones 1.0 (root 1.2), tiny weight elsewhere. Harmonics are already folded into
    chroma, so no overtone model is needed beyond the root emphasis."""
    t = np.full(12, 0.02)
    for i in QUALITY_INTERVALS.get(quality, (0, 4, 7)):
        t[(root + i) % 12] = 1.0
    t[root % 12] = 1.25 if overtones else 1.0
    return t / np.linalg.norm(t)


TRIAD_QUALITIES = ("maj", "min")


def template_bank(qualities: tuple[str, ...] = TRIAD_QUALITIES) -> tuple[np.ndarray, list[tuple[int, str]]]:
    """(matrix [n, 12], [(root, quality), ...]) for every root and quality."""
    rows, ids = [], []
    for q in qualities:
        for r in range(12):
            rows.append(chord_template(r, q))
            ids.append((r, q))
    return np.stack(rows), ids


# ------------------------------------------------------------------------------------------ chord <-> key
_MAJOR_SCALE = (0, 2, 4, 5, 7, 9, 11)
_MINOR_SCALE = (0, 2, 3, 5, 7, 8, 10)
# diatonic triad quality by scale degree
_MAJOR_TRIADS = {0: "maj", 2: "min", 4: "min", 5: "maj", 7: "maj", 9: "min", 11: "dim"}
_MINOR_TRIADS = {0: "min", 2: "dim", 3: "maj", 5: "min", 7: "min", 8: "maj", 10: "maj"}


def chord_key_fit(root: int | None, quality: str, key_idx: int) -> float:
    """How well a chord belongs to a key, 0..1.35: diatonic root and matching triad quality 1.0, tonic chord and the
    dominant get a bonus, a diatonic root with another quality 0.5, chromatic 0 (borrowed V/IV in minor/major 0.3)."""
    if root is None:
        return 0.0
    tonic, mode = key_from_index(key_idx)
    d = (root - tonic) % 12
    triads = _MAJOR_TRIADS if mode == "major" else _MINOR_TRIADS
    base = quality
    if base in ("7", "9", "11", "13"):
        base = "maj"
    elif base in ("maj7", "maj9"):
        base = "maj"
    elif base in ("min7", "min9"):
        base = "min"
    elif base in ("hdim7", "dim7"):
        base = "dim"
    elif base in ("sus2", "sus4"):
        base = triads.get(d, "maj")
    s = 0.0
    if d in triads:
        s = 1.0 if triads[d] == base else 0.5
    elif mode == "minor" and d == 7 and base == "maj":
        s = 1.0  # harmonic-minor dominant
    elif mode == "major" and d == 10 and base == "maj":
        s = 0.3  # bVII borrowed
    elif mode == "minor" and d == 5 and base == "maj":
        s = 0.3
    if d == 0 and s >= 1.0:
        s += 0.35
    elif d == 7 and s >= 1.0:
        s += 0.15
    return s
