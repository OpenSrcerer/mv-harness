"""Curve channel registry (PLAN §4.1 curves/, §4.4 values). FROZEN at contract v1 (ids, units, policies).

Every channel lives in exactly one curve file. Patterned ids (``stem.{stem}.level``, ``vocal.mouth_open.{voice}``,
``inst.{label}``, ``mood.tag.{tag}``) are families: the concrete ids appear in ``curves/index.json``.
The runner packs each file column-major (one contiguous float32 block per channel, in the order the
channels are listed in ``curves/index.json``); ``spectrum128`` is a row-major uint8 matrix.

Fields per channel:
  unit      'dBFS', 'dB', 'LUFS', 'Hz', 'MIDI', 'BPM', 'dB/oct', '0..1', '-1..1', '0/1', 'unitless'
  range     expected [lo, hi] (informative; validators warn outside it)
  resample  linear | mean | max | hold  (the frame policy, conventions.curve_frame)
  norm      None, or how a 0..1 channel was derived: {'method': 'p02-p99.5', 'of': <twin id>} - the per-song
            lo/hi are written into curves/index.json by the producing stage; 'viz' = the viz/js/audio.js mapping;
            'p02-p98' for vocal.pitch01; 'model' for model probabilities; 'composite' for documented composites.
  twin      the absolute (physical) twin of a 0..1 channel, or the 0..1 twin of a physical one.
  special   {'nan': 'unvoiced'} (NaN-aware pitch sampling) or {'floor': -120.0} (dB floor; never -inf).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .ids import DRUM_SUBSTEMS, STEM_NAMES

__all__ = ["CurveFile", "Channel", "CURVE_FILES", "CHANNELS", "channel", "match_channel", "channels_of",
           "STEM_CHANNEL_NAMES", "FINE_BANDS", "VIZ_BANDS", "DB_FLOOR", "LUFS_FLOOR"]

DB_FLOOR = -120.0
LUFS_FLOOR = -70.0


@dataclass(frozen=True)
class CurveFile:
    id: str
    path: str
    dtype: str            # 'f32le' | 'u8'
    layout: str           # 'column-major' (channels) | 'row-major' (matrix [frames x k])
    rate_hz: float
    description: str


@dataclass(frozen=True)
class Channel:
    id: str
    file: str
    stage: str
    unit: str
    range: tuple[float, float]
    resample: str
    description: str
    norm: dict[str, Any] | None = None
    twin: str | None = None
    special: dict[str, Any] | None = None

    @property
    def is_pattern(self) -> bool:
        return "{" in self.id

    @property
    def nan_aware(self) -> bool:
        return bool(self.special and self.special.get("nan") == "unvoiced")


CURVE_FILES: dict[str, CurveFile] = {f.id: f for f in [
    CurveFile("core", "curves/core.f32", "f32le", "column-major", 100, "Mix-level curves at 100 Hz"),
    CurveFile("stems", "curves/stems.f32", "f32le", "column-major", 100, "Per-stem levels and activity at 100 Hz"),
    CurveFile("vocal", "curves/vocal.f32", "f32le", "column-major", 100, "Lead-vocal pitch and mouth_open at 100 Hz"),
    CurveFile("chroma12", "curves/chroma12.f32", "f32le", "column-major", 100, "12 pitch classes (C=0) at 100 Hz"),
    CurveFile("instruments_1hz", "curves/instruments_1hz.f32", "f32le", "column-major", 1, "Instrument and vocal-style probabilities at 1 Hz"),
    CurveFile("mood_1hz", "curves/mood_1hz.f32", "f32le", "column-major", 1, "Valence, arousal and mood/theme tags at 1 Hz"),
    CurveFile("spectrum128", "curves/spectrum128.u8", "u8", "row-major", 100,
              "[frames x 128] viz band values (u8/255 = viz bands[k]); same layout as viz bandBytes R channel"),
]}

VIZ_BANDS = {"bass": (32, 150), "mid": (150, 2200), "high": (2200, 16000)}
FINE_BANDS = {"sub": (20, 60), "bass": (60, 150), "lowmid": (150, 500), "mid": (500, 2000),
              "highmid": (2000, 4000), "presence": (4000, 6000), "air": (6000, 16000)}
KICK_BAND = (35, 100)
STEM_CHANNEL_NAMES = tuple(STEM_NAMES) + tuple(f"drums_{s}" for s in DRUM_SUBSTEMS)

_P = {"method": "p02-p99.5"}
_U01 = (0.0, 1.0)
_DB = (DB_FLOOR, 6.0)


def _twin_pair(base: str, file: str, stage: str, unit: str, rng, resample: str, desc: str, floor=None):
    """A physical channel <base>_<unit-suffix> and its per-song 0..1 twin <base>."""
    phys = {"dBFS": "_db", "dB": "_db", "LUFS": "_lufs", "Hz": "_hz"}[unit]
    pid = base + phys if not base.endswith(phys) else base
    nid = base[: -len(phys)] if base.endswith(phys) else base
    special = {"floor": floor} if floor is not None else None
    return [
        Channel(nid, file, stage, "0..1", _U01, resample, f"{desc} (per-song 0..1)", norm=dict(_P, of=pid), twin=pid),
        Channel(pid, file, stage, unit, rng, resample, f"{desc} ({unit})", twin=nid, special=special),
    ]


def _build() -> list[Channel]:
    ch: list[Channel] = []
    S = "spectral"
    for b, (lo, hi) in VIZ_BANDS.items():
        ch += _twin_pair(f"bands.{b}", "core", S, "dBFS", _DB, "mean", f"{b} band {lo}-{hi} Hz power", DB_FLOOR)
        ch.append(Channel(f"bands.{b}_viz", "core", S, "0..1", _U01, "mean",
                          f"viz-compatible {b} level (mean of normalised log bands, as viz audio.{b})", norm={"method": "viz"}))
    ch.append(Channel("bands.level", "core", S, "0..1", _U01, "mean", "viz-compatible overall level (viz audio.level)", norm={"method": "viz"}))
    ch += _twin_pair("bands.kick", "core", S, "dBFS", _DB, "mean", f"kick band {KICK_BAND[0]}-{KICK_BAND[1]} Hz power", DB_FLOOR)
    for b, (lo, hi) in FINE_BANDS.items():
        ch += _twin_pair(f"fine.{b}", "core", S, "dBFS", _DB, "mean", f"fine band {b} {lo}-{hi} Hz power", DB_FLOOR)
    for h, viz in (("kick", "kick"), ("mid", "midHit"), ("high", "highHit")):
        ch.append(Channel(f"hits.{h}", "core", S, "unitless", (0.0, 1.5), "max",
                          f"{h} hit envelope with 0.18 s release (viz audio.{viz}); a typical hit reads ~0.85",
                          norm={"method": "composite"}))
        ch.append(Channel(f"hits.{h}_raw", "core", S, "unitless", (0.0, 1.5), "max",
                          f"{h} hit envelope without release (viz audio.{'kickRaw' if h == 'kick' else viz + ' raw'})",
                          norm={"method": "composite"}))
    for b in VIZ_BANDS:
        ch.append(Channel(f"flux.{b}", "core", S, "0..1", _U01, "max", f"{b}-band spectral flux (onset strength), per-song 0..1",
                          norm={"method": "p02-p99.5"}))
    ch += _twin_pair("timbre.centroid_hz", "core", S, "Hz", (0.0, 22050.0), "mean", "spectral centroid")
    ch += _twin_pair("timbre.rolloff_hz", "core", S, "Hz", (0.0, 22050.0), "mean", "85% spectral roll-off")
    ch.append(Channel("timbre.flatness", "core", S, "0..1", _U01, "mean", "spectral flatness (Wiener entropy)"))
    ch.append(Channel("timbre.slope_db_oct", "core", S, "dB/oct", (-30.0, 10.0), "mean", "spectral slope"))
    ch.append(Channel("stereo.width", "core", S, "0..1", _U01, "mean", "side/(mid+side) energy ratio"))
    ch.append(Channel("stereo.balance", "core", S, "-1..1", (-1.0, 1.0), "mean", "left(-1)/right(+1) energy balance"))
    ch.append(Channel("stereo.correlation", "core", S, "-1..1", (-1.0, 1.0), "mean", "inter-channel correlation"))

    L = "loudness"
    ch += _twin_pair("loud.momentary_lufs", "core", L, "LUFS", (LUFS_FLOOR, 6.0), "mean", "momentary loudness (0.4 s, centred)", LUFS_FLOOR)
    ch += _twin_pair("loud.short_term_lufs", "core", L, "LUFS", (LUFS_FLOOR, 6.0), "mean", "short-term loudness (3 s, centred)", LUFS_FLOOR)
    ch += _twin_pair("loud.rms_db", "core", L, "dBFS", _DB, "mean", "RMS level (46 ms centred window)", DB_FLOOR)
    ch.append(Channel("loud.peak_db", "core", L, "dBFS", _DB, "max", "sample peak (46 ms centred window)", special={"floor": DB_FLOOR}))
    ch.append(Channel("loud.crest_db", "core", L, "dB", (0.0, 60.0), "mean", "crest factor (peak - RMS)"))

    R = "rhythm"
    ch.append(Channel("tempo.bpm", "core", R, "BPM", (30.0, 300.0), "linear", "local tempo from the beat grid"))
    ch.append(Channel("rhythm.beat_act", "core", R, "0..1", _U01, "max", "beat activation (beat_this probability)", norm={"method": "model"}))
    ch.append(Channel("rhythm.downbeat_act", "core", R, "0..1", _U01, "max", "downbeat activation", norm={"method": "model"}))
    ch.append(Channel("rhythm.in_pulse", "core", R, "0/1", _U01, "hold", "1 inside a pulse region"))

    D = "dynamics"
    ch.append(Channel("dyn.intensity", "core", D, "0..1", _U01, "linear",
                      "intensity composite (short-term LU vs integrated, bass, onset density, brightness)", norm={"method": "composite"}))
    ch.append(Channel("dyn.novelty", "core", D, "0..1", _U01, "max", "Foote novelty (section-change evidence)", norm={"method": "composite"}))

    for d in ("kick", "snare", "hat", "tom", "cymbal", "perc"):
        ch.append(Channel(f"drums.{d}", "core", "drums", "0..1", _U01, "max", f"{d} hit envelope (velocity-scaled)", norm={"method": "composite"}))

    C = "choreo"
    ch.append(Channel("choreo.movement", "core", C, "0..1", _U01, "linear", "movement-density composite", norm={"method": "composite"}))
    ch.append(Channel("choreo.accent", "core", C, "0..1", _U01, "max", "count accent envelope (drum hits, onsets, vocal onsets)",
                      norm={"method": "composite"}))

    A = "stem_activity"
    ch.append(Channel("stem.{stem}.level", "stems", A, "0..1", _U01, "mean", "stem RMS level (per-song 0..1 over all stems)",
                      norm=dict(_P, of="stem.{stem}.rms_db"), twin="stem.{stem}.rms_db"))
    ch.append(Channel("stem.{stem}.rms_db", "stems", A, "dBFS", _DB, "mean", "stem RMS (dBFS)", twin="stem.{stem}.level",
                      special={"floor": DB_FLOOR}))
    ch.append(Channel("stem.{stem}.rel_db", "stems", A, "dB", (DB_FLOOR, 12.0), "mean", "stem level relative to the mix",
                      special={"floor": DB_FLOOR}))
    ch.append(Channel("stem.{stem}.active", "stems", A, "0/1", _U01, "hold",
                      "1 when the stem is active (> -45 dBFS and within 18 dB of the mix, 300/500 ms hysteresis)"))

    V = "vocals"
    ch.append(Channel("vocal.f0_hz", "vocal", V, "Hz", (30.0, 2000.0), "linear", "lead-vocal f0; NaN where unvoiced",
                      special={"nan": "unvoiced"}, twin="vocal.midi"))
    ch.append(Channel("vocal.midi", "vocal", V, "MIDI", (20.0, 100.0), "linear", "lead-vocal pitch (fractional MIDI); NaN where unvoiced",
                      special={"nan": "unvoiced"}, twin="vocal.pitch01"))
    ch.append(Channel("vocal.pitch01", "vocal", V, "0..1", _U01, "linear",
                      "(midi - p2) / (p98 - p2), held through gaps with a 150 ms ease; never NaN",
                      norm={"method": "p02-p98", "of": "vocal.midi"}, twin="vocal.midi"))
    ch.append(Channel("vocal.voiced", "vocal", V, "0/1", _U01, "max", "1 where the lead vocal is voiced (== isfinite(vocal.midi))"))
    ch.append(Channel("vocal.conf", "vocal", V, "0..1", _U01, "mean", "pitch confidence", norm={"method": "model"}))
    ch.append(Channel("vocal.mouth_open", "vocal", "lipsync", "0..1", _U01, "max",
                      "mouth opening: vocal envelope (10 ms attack, 60 ms release) gated by aligned words; max over voices",
                      norm={"method": "composite"}))
    ch.append(Channel("vocal.mouth_open.{voice}", "vocal", "lipsync", "0..1", _U01, "max",
                      "mouth opening of one voice (written when there are >= 2 voices)", norm={"method": "composite"}))

    for pc in range(12):
        ch.append(Channel(f"chroma.{pc}", "chroma12", "harmony", "0..1", _U01, "mean",
                          f"chroma of pitch class {pc} (C=0), max-normalised per frame"))

    INST = "instruments"
    ch.append(Channel("inst.{label}", "instruments_1hz", INST, "0..1", _U01, "linear",
                      "instrument presence probability (fused CED/CLAP/stem activity), 4 s window, 1 s hop", norm={"method": "model"}))
    for s in ("singing", "speech", "rap"):
        ch.append(Channel(f"vstyle.{s}", "instruments_1hz", INST, "0..1", _U01, "linear", f"lead-vocal style probability: {s}",
                          norm={"method": "model"}))

    M = "mood"
    ch.append(Channel("mood.valence", "mood_1hz", M, "0..1", _U01, "linear", "audio valence (0.5 neutral); lower confidence than arousal",
                      norm={"method": "model"}))
    ch.append(Channel("mood.arousal", "mood_1hz", M, "0..1", _U01, "linear", "audio arousal (0.5 neutral)", norm={"method": "model"}))
    ch.append(Channel("mood.tag.{tag}", "mood_1hz", M, "0..1", _U01, "linear", "MTG-Jamendo mood/theme tag probability",
                      norm={"method": "model"}))

    ch.append(Channel("spectrum128", "spectrum128", "spectral", "0..1", _U01, "hold",
                      "128 log bands 32 Hz-16 kHz, viz mapping (2.6 dB/oct tilt, -88..-18 dB, soft knee, per-song gain); "
                      "u8 = round(255 * value)", norm={"method": "viz"}))
    return ch


CHANNELS: dict[str, Channel] = {c.id: c for c in _build()}

_PAT_CACHE: list[tuple[re.Pattern[str], Channel]] = [
    (re.compile("^" + re.escape(c.id).replace(r"\{stem\}", r"(?P<stem>[a-z_]+)")
                .replace(r"\{voice\}", r"(?P<voice>V[1-9]\d*)").replace(r"\{label\}", r"(?P<label>[a-z0-9_]+)")
                .replace(r"\{tag\}", r"(?P<tag>[a-z0-9_]+)") + "$"), c)
    for c in CHANNELS.values() if c.is_pattern
]


def channel(cid: str) -> Channel:
    """Registry entry for a concrete or patterned channel id (KeyError if unknown)."""
    c = match_channel(cid)
    if c is None:
        raise KeyError(cid)
    return c


def match_channel(cid: str) -> Channel | None:
    if cid in CHANNELS:
        return CHANNELS[cid]
    for rx, c in _PAT_CACHE:
        m = rx.match(cid)
        if m:
            if "stem" in m.groupdict() and m.group("stem") not in STEM_CHANNEL_NAMES:
                return None
            return c
    return None


def channels_of(stage: str) -> list[Channel]:
    return [c for c in CHANNELS.values() if c.stage == stage]


def index_entry(c: Channel, concrete_id: str | None = None, **per_song: Any) -> dict[str, Any]:
    """Registry fields of one channel as they appear in curves/index.json (without file offsets)."""
    cid = concrete_id or c.id
    e: dict[str, Any] = {"id": cid, "file": c.file, "unit": c.unit, "range": list(c.range), "resample": c.resample,
                         "norm": None, "special": c.special, "twin": c.twin, "stage": c.stage, "description": c.description}
    if c.norm is not None:
        e["norm"] = dict(c.norm)
    if c.twin and "{" in c.twin and concrete_id:
        # substitute the same placeholder value into the twin id
        for rx, pc in _PAT_CACHE:
            if pc is c:
                m = rx.match(concrete_id)
                if m:
                    e["twin"] = c.twin.format(**m.groupdict())
                    if e["norm"] and "of" in e["norm"]:
                        e["norm"]["of"] = c.norm["of"].format(**m.groupdict())
    e.update(per_song)
    return e


__all__.append("index_entry")
