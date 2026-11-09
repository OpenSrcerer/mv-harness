"""Shared deterministic test-signal primitives (PLAN §7.1 "per-module generators"). Each returns (audio, sr, truth).

  click_track      metronome clicks with an optional linear tempo ramp and 8th-note swing; truth = click/beat times
  ebu_signal       EBU Tech 3341/3342 style loudness signals; truth = expected integrated loudness / LRA / true peak
  sweep            linear or exponential sine sweep; truth = instantaneous frequency at 100 Hz
  midi_render      notes rendered with a simple synth (sine | saw | bass | piano | pad) + the .mid bytes; truth = notes
  sung_sine        harmonic "sung" tone with vibrato following note events; truth = f0 at 100 Hz (NaN between notes)
  tts_sentence     natural SAPI sentence (David or Zira); truth = SAPI word starts + energy-based word ends
  tts_words        SAPI words placed at given times (exact word onsets and durations)
  edge_case        edge-case FILES on demand under tests/.cache/synth/edge/ (mono, 48 kHz, MP3 with encoder delay,
                   corrupt FLAC, 10 s, 10 min, unicode path); returns (path, truth)

Audio arrays are float64, mono [n] unless stated ([2, n] for stereo). Everything is seeded and byte-reproducible.
"""

from __future__ import annotations

import json
import math
import zlib
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from . import dsp, tts
from .audio_io import encode, quantize24, write_wav
from .midi import write_smf

__all__ = [
    "click_track",
    "ebu_signal",
    "EBU_CASES",
    "sweep",
    "midi_render",
    "sung_sine",
    "tts_sentence",
    "tts_words",
    "edge_case",
    "EDGE_CASES",
    "CACHE",
]

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / "tests" / ".cache" / "synth"
SR = 44100


# ------------------------------------------------------------------------------------------------ clicks
def _click(sr: int, accent: bool) -> np.ndarray:
    n = int(0.03 * sr)
    t = np.arange(n) / sr
    f = 2000.0 if accent else 1200.0
    return np.sin(2 * np.pi * f * t) * np.exp(-t / 0.006)


def click_track(
    bpm: float = 120.0,
    duration_s: float = 10.0,
    *,
    ramp_to_bpm: float | None = None,
    swing: float = 1.0,
    subdivision: int = 1,
    beats_per_bar: int = 4,
    offset_s: float = 0.5,
    sr: int = SR,
    level_db: float = -6.0,
) -> tuple[np.ndarray, int, dict[str, Any]]:
    """Clicks on every beat (subdivision=2 adds swung off-8ths). The tempo ramps linearly in *time* from bpm to
    ramp_to_bpm over the track. Truth times are on the sample grid; the click's first sample is the onset."""
    n = int(round(duration_s * sr))
    x = np.zeros(n)
    b1 = ramp_to_bpm or bpm
    beats, clicks = [], []
    t = offset_s
    k = 0
    while t < duration_s - 0.05:
        ts = round(t * sr) / sr
        beats.append(
            {
                "t": ts,
                "beat_index": k,
                "beat_in_bar": k % beats_per_bar + 1,
                "bpm": bpm + (b1 - bpm) * (t / duration_s),
            }
        )
        clicks.append({"t": ts, "accent": k % beats_per_bar == 0, "kind": "beat"})
        ibi = 60.0 / (bpm + (b1 - bpm) * (t / duration_s))
        if subdivision == 2:
            to = t + ibi * swing / (1 + swing)
            if to < duration_s - 0.05:
                clicks.append({"t": round(to * sr) / sr, "accent": False, "kind": "offbeat"})
        t += ibi
        k += 1
    for c in clicks:
        dsp.place(
            x[None, :],
            _click(sr, c["accent"]) * dsp.db_to_lin(level_db) * (1.0 if c["kind"] == "beat" else 0.5),
            int(round(c["t"] * sr)),
        )
    truth = {
        "kind": "click_track",
        "bpm_start": bpm,
        "bpm_end": b1,
        "swing": swing,
        "beats": beats,
        "clicks": clicks,
        "downbeats": [b["t"] for b in beats if b["beat_in_bar"] == 1],
    }
    return x, sr, truth


# ------------------------------------------------------------------------------------------------ EBU loudness
#: name -> (segments [(dBFS per channel, seconds)], freq Hz, expected {integrated, lra, true_peak} ; None = not specified)
EBU_CASES: dict[str, dict[str, Any]] = {
    "3341_1": {
        "segments": [(-23.0, 20.0)],
        "freq": 1000.0,
        "integrated": -23.0,
        "momentary": -23.0,
        "short_term": -23.0,
    },
    "3341_2": {
        "segments": [(-33.0, 20.0)],
        "freq": 1000.0,
        "integrated": -33.0,
        "momentary": -33.0,
        "short_term": -33.0,
    },
    "3341_3": {
        "segments": [(-36.0, 10.0), (-23.0, 60.0), (-36.0, 10.0)],
        "freq": 1000.0,
        "integrated": -23.0,
    },
    "3341_4": {
        "segments": [(-72.0, 10.0), (-36.0, 10.0), (-23.0, 60.0), (-36.0, 10.0), (-72.0, 10.0)],
        "freq": 1000.0,
        "integrated": -23.0,
    },
    "3342_1": {"segments": [(-20.0, 20.0), (-30.0, 20.0)], "freq": 1000.0, "lra": 10.0},
    "3342_2": {"segments": [(-20.0, 20.0), (-15.0, 20.0)], "freq": 1000.0, "lra": 5.0},
    "3342_3": {"segments": [(-40.0, 20.0), (-20.0, 20.0)], "freq": 1000.0, "lra": 20.0},
    "true_peak_fs4": {
        "segments": [(-6.0, 5.0)],
        "freq": SR / 4.0,
        "phase": math.pi / 4,
        "true_peak_dbtp": -6.0,
        "sample_peak_db": -6.0 - 3.0103,
    },
}


def ebu_signal(case: str, sr: int = SR) -> tuple[np.ndarray, int, dict[str, Any]]:
    """Stereo [2, n] sine segments at the given dBFS *peak* level per channel (EBU convention: a 0 dBFS sine has peak 1).
    Expected values follow EBU Tech 3341 (loudness, +-0.1 LU) and Tech 3342 (LRA, +-1 LU).
    true_peak_fs4: a sine at fs/4 with 45 deg phase; samples hit 0.707 of the peak, so the sample peak reads 3.01 dB
    below the true peak (-6 dBTP)."""
    c = EBU_CASES[case]
    parts = []
    t0 = 0.0
    for db, dur in c["segments"]:
        n = int(round(dur * sr))
        t = (np.arange(n) / sr) + t0
        parts.append(dsp.db_to_lin(db) * np.sin(2 * np.pi * c["freq"] * t + c.get("phase", 0.0)))
        t0 += dur
    x = np.concatenate(parts)
    truth = {
        "kind": "ebu",
        "case": case,
        **{k: v for k, v in c.items() if k != "segments"},
        "segments": [{"dbfs": db, "seconds": dur} for db, dur in c["segments"]],
        "tolerance_lu": 0.1,
        "lra_tolerance_lu": 1.0,
    }
    return np.vstack([x, x]), sr, truth


# ------------------------------------------------------------------------------------------------ sweeps
def sweep(
    f0: float = 20.0,
    f1: float = 20000.0,
    duration_s: float = 10.0,
    *,
    kind: str = "log",
    level_db: float = -12.0,
    sr: int = SR,
) -> tuple[np.ndarray, int, dict[str, Any]]:
    n = int(round(duration_s * sr))
    t = np.arange(n) / sr
    if kind == "log":
        f = f0 * (f1 / f0) ** (t / duration_s)
    elif kind == "linear":
        f = f0 + (f1 - f0) * t / duration_s
    else:
        raise ValueError(kind)
    x = dsp.db_to_lin(level_db) * np.sin(2 * np.pi * np.cumsum(f) / sr)
    t100 = np.arange(int(math.ceil(n * 100 / sr))) / 100.0
    f100 = f0 * (f1 / f0) ** (t100 / duration_s) if kind == "log" else f0 + (f1 - f0) * t100 / duration_s
    return (
        x,
        sr,
        {"kind": "sweep", "type": kind, "f0": f0, "f1": f1, "freq_100hz": np.round(f100, 4).tolist()},
    )


# ------------------------------------------------------------------------------------------------ MIDI
def _voice(program: str, midi: int, d: float, vel: float, sr: int) -> np.ndarray:
    if program == "sine":
        n_on = int(round(d * sr))
        env = dsp.env_adsr(n_on, 0.005, 0.05, 0.8, 0.03, sr)
        return vel * 0.5 * np.sin(2 * np.pi * float(dsp.midi_hz(midi)) * np.arange(env.size) / sr) * env
    if program == "saw":
        n_on = int(round(d * sr))
        env = dsp.env_adsr(n_on, 0.005, 0.1, 0.7, 0.05, sr)
        f = float(dsp.midi_hz(midi))
        return vel * 0.3 * dsp.additive(f, env.size, [1.0 / k for k in range(1, 40)], sr) * env
    if program == "bass":
        return dsp.bass_note(midi, d, vel, sr)
    if program == "piano":
        return dsp.piano_note(midi, d, vel, sr)
    if program == "pad":
        return dsp.pad_note(midi, d, vel, sr).mean(axis=0)
    raise ValueError(program)


def midi_render(
    notes: Sequence[tuple[float, float, int, float]],
    *,
    program: str = "saw",
    bpm: float = 120.0,
    tail_s: float = 1.0,
    sr: int = SR,
) -> tuple[np.ndarray, int, dict[str, Any]]:
    """notes: [(t, d, midi, vel 0..1)]. Returns mono audio and truth {notes, midi_bytes_hex? no: midi (bytes) under 'smf'}."""
    end = max(t + d for t, d, _, _ in notes) + tail_s
    x = np.zeros((1, int(round(end * sr))))
    for t, d, m, v in notes:
        dsp.place(x, _voice(program, m, d, v, sr), int(round(t * sr)))
    smf = write_smf([(program, list(notes))], [(0.0, bpm)])
    truth = {
        "kind": "midi_render",
        "program": program,
        "notes": [{"t": t, "d": d, "midi": m, "name": dsp.note_name(m), "vel": v} for t, d, m, v in notes],
        "smf": smf,
    }
    return x[0], sr, truth


#: a monophonic bass line (A minor riff) and a polyphonic chord sequence for notes tests
BASS_LINE = [
    (0.5 + 0.25 * i, 0.22, m, 0.9)
    for i, m in enumerate([33, 33, 45, 33, 36, 38, 40, 43, 41, 41, 29, 41, 31, 43, 31, 28])
]
CHORDS = [
    (0.5 + 1.0 * i, 0.95, m, 0.7)
    for i, ch in enumerate([(57, 60, 64), (53, 57, 60), (55, 60, 64), (55, 59, 62)])
    for m in ch
]


# ------------------------------------------------------------------------------------------------ sung sine
def sung_sine(
    notes: Sequence[tuple[float, float, int]],
    *,
    vib_cents: float = 40.0,
    vib_hz: float = 5.5,
    harmonics: int = 8,
    tail_s: float = 0.5,
    sr: int = SR,
) -> tuple[np.ndarray, int, dict[str, Any]]:
    """A harmonic 'voice' (1/k^1.5 harmonics) following notes [(t, d, midi)] with vibrato fading in after 150 ms.
    Truth: f0_hz and midi at 100 Hz (NaN where silent) plus the notes."""
    end = max(t + d for t, d, _ in notes) + tail_s
    n = int(round(end * sr))
    midi = np.full(n, np.nan)
    for t, d, m in notes:
        a, b = int(round(t * sr)), int(round((t + d) * sr))
        tt = np.arange(b - a) / sr
        midi[a:b] = m + vib_cents / 100.0 * np.clip((tt - 0.15) / 0.2, 0, 1) * np.sin(2 * np.pi * vib_hz * tt)
    f = np.where(np.isfinite(midi), 440.0 * 2 ** ((np.nan_to_num(midi, nan=69.0) - 69) / 12), 0.0)
    ph = 2 * np.pi * np.cumsum(f) / sr
    amp = np.isfinite(midi).astype(np.float64)
    amp = np.convolve(amp, np.ones(int(0.01 * sr)) / int(0.01 * sr), mode="same")  # 10 ms fades
    x = sum((1.0 / k**1.5) * np.sin(k * ph) for k in range(1, harmonics + 1)) * amp * 0.3
    idx = np.round(np.arange(int(math.ceil(n * 100 / sr))) * sr / 100).astype(int).clip(0, n - 1)
    m100 = midi[idx]
    truth = {
        "kind": "sung_sine",
        "notes": [{"t": t, "d": d, "midi": m} for t, d, m in notes],
        "vib_cents": vib_cents,
        "vib_hz": vib_hz,
        "midi_100hz": [None if not np.isfinite(v) else round(float(v), 4) for v in m100],
    }
    return x, sr, truth


# ------------------------------------------------------------------------------------------------ TTS
def tts_sentence(
    voice: str = "david", text: str = "The quick brown fox jumps over the lazy dog", *, sr_out: int = SR
) -> tuple[np.ndarray, int, dict[str, Any]]:
    """Natural SAPI speech. Truth: word starts from SAPI SpeakProgress (AudioPosition) and ends where the 5 ms energy
    first drops 35 dB below the sentence peak before the next start (estimated: flagged 'end_estimated')."""
    from scipy import signal as sig

    x, sr, marks = tts.sentence(voice, text)
    y = (
        sig.resample_poly(x, sr_out // math.gcd(sr_out, sr), sr // math.gcd(sr_out, sr))
        if sr != sr_out
        else x
    )
    hop = int(0.005 * sr_out)
    fr = np.lib.stride_tricks.sliding_window_view(np.pad(y, (0, hop)), hop)[::hop]
    db = 10 * np.log10(np.mean(fr**2, axis=1) + 1e-20)
    thr = db.max() - 35.0
    words = []
    for i, m in enumerate(marks):
        start = m["t"]
        nxt = marks[i + 1]["t"] if i + 1 < len(marks) else len(y) / sr_out
        a, b = int(start / 0.005), int(nxt / 0.005)
        seg = db[a:b]
        on = np.nonzero(seg > thr)[0]
        end = (a + on[-1] + 1) * 0.005 if on.size else nxt
        words.append(
            {
                "text": m["text"],
                "t": m["t"],
                "d": round(max(0.01, min(nxt, end) - start), 6),
                "end_estimated": True,
            }
        )
    return y, sr_out, {"kind": "tts_sentence", "voice": voice, "text": text, "words": words}


def tts_words(
    words: Sequence[tuple[str, float]],
    voice: str = "david",
    *,
    sr_out: int = SR,
    duration_s: float | None = None,
) -> tuple[np.ndarray, int, dict[str, Any]]:
    """SAPI words (each rendered alone, trimmed) placed at the given onsets: exact word t and d truth."""
    from scipy import signal as sig

    clips = []
    for text, t in words:
        w = tts._trim(tts.word(voice, text.lower()))
        clips.append((text, t, sig.resample_poly(w, 2, 1) if sr_out == 44100 else w))
    end = duration_s or (max(t + c.size / sr_out for _, t, c in clips) + 0.5)
    x = np.zeros((1, int(round(end * sr_out))))
    out = []
    for text, t, c in clips:
        dsp.place(x, c, int(round(t * sr_out)))
        out.append({"text": text, "t": round(round(t * sr_out) / sr_out, 6), "d": round(c.size / sr_out, 6)})
    return x[0], sr_out, {"kind": "tts_words", "voice": voice, "words": out}


# ------------------------------------------------------------------------------------------------ edge-case files
EDGE_CASES = (
    "mono_44k",
    "stereo_48k",
    "mp3_delay",
    "corrupt_flac",
    "short_10s",
    "long_10min",
    "unicode_path",
)


def _music(duration_s: float, sr: int, seed: int) -> tuple[np.ndarray, dict]:
    """A simple stereo loop: clicks on beats at 120 BPM + a sine pad (deterministic)."""
    x, _, tr = click_track(120.0, duration_s, sr=sr, level_db=-8.0)
    t = np.arange(x.size) / sr
    pad = 0.08 * (np.sin(2 * np.pi * 220.0 * t) + 0.5 * np.sin(2 * np.pi * 277.18 * t))
    g = np.random.default_rng(seed)
    noise = 0.002 * g.standard_normal(x.size)
    return np.vstack([x + pad + noise, x + pad - noise]), tr


def edge_case(name: str, root: Path | None = None) -> tuple[Path, dict[str, Any]]:
    """Generate (once) and return an edge-case file plus its truth (also written next to it as <file>.truth.json)."""
    root = Path(root or CACHE / "edge")
    spec = {
        "mono_44k": ("mono_44k.flac", 44100, 12.0),
        "stereo_48k": ("stereo_48k.flac", 48000, 12.0),
        "mp3_delay": ("clicks_mp3_delay.mp3", 44100, 12.0),
        "corrupt_flac": ("corrupt.flac", 44100, 12.0),
        "short_10s": ("short_10s.flac", 44100, 10.0),
        "long_10min": ("long_10min.flac", 44100, 600.0),
        "unicode_path": ("dir with spaces/tëst ♪ 曲.flac", 44100, 12.0),
    }[name]
    rel, sr, dur = spec
    path = root / rel
    tpath = path.with_name(path.name + ".truth.json")
    if path.exists() and tpath.exists():
        with open(tpath, encoding="utf-8") as fh:
            return path, json.load(fh)
    x, tr = _music(dur, sr, seed=zlib.crc32(name.encode()))
    truth: dict[str, Any] = {
        "case": name,
        "sample_rate": sr,
        "duration_s": dur,
        "n_samples": int(round(dur * sr)),
        "beats": [b["t"] for b in tr["beats"]],
        "bpm": 120.0,
    }
    x = quantize24(x * 0.8)
    if name == "mono_44k":
        encode(path, x.mean(axis=0, keepdims=True), sr, "flac24")
        truth["channels"] = 1
    elif name == "mp3_delay":
        encode(path, x, sr, "mp3")
        truth.update(
            {
                "channels": 2,
                "lossy": True,
                "note": "LAME adds encoder delay + padding; ffmpeg's gapless info should "
                "trim it, so the decode must align with the beats within 1 ms (check it; report if not)",
            }
        )
    elif name == "corrupt_flac":
        tmp = path.with_name("intact.flac")
        encode(tmp, x, sr, "flac16")
        b = bytearray(tmp.read_bytes())
        mid = len(b) // 2
        for i in range(mid, mid + 64):
            b[i] ^= 0xA5  # deterministic damage to one or two frames in the middle
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes(b))
        tmp.unlink()
        truth.update(
            {
                "channels": 2,
                "corrupt": True,
                "note": "64 bytes XOR-ed at the file's midpoint: decoders must warn and "
                "either drop the damaged frame(s) or conceal them; the length may shrink (cf. Versatile.flac)",
            }
        )
    else:
        encode(path, x, sr, "flac24")
        truth["channels"] = 2
    with open(tpath, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(truth, fh, ensure_ascii=False, indent=1)
    return path, truth


def write_primitive_wav(path: Path, x: np.ndarray, sr: int) -> Path:
    """Convenience: float32 WAV for tools that need a file (our own WAV; never hand user audio to a model library)."""
    return write_wav(path, x, sr, "f32")
