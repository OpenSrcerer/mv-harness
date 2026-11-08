# ruff: noqa: E501  (long data tables / docstrings in generated-fixture code)
"""Render the score into generator tracks (the stems) and collect the event truth.

Tracks are stereo float64 [2, N_SAMPLES]. After a single global gain (mix sample peak -1 dBFS) every base track
is quantised to the 24-bit grid, so all derived stems are exact integer sums:

  drums        = kick + snare + toms + hihat + ride + crash      (DrumSep sub-stems)
  vocals       = lead_vocals + backing_vocals
  mix          = vocals + drums + bass + guitar + piano + other
  instrumental = mix - vocals
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .. import dsp, tts
from ..audio_io import quantize24
from . import score as S

__all__ = ["Render", "render"]

GAINS = {
    "kick": 0.9,
    "snare": 0.55,
    "toms": 0.5,
    "hihat": 0.35,
    "ride": 0.3,
    "crash": 0.3,
    "bass": 0.6,
    "pad": 0.75,
    "riser": 0.3,
    "piano": 0.45,
    "lead": 1.6,
    "backing": 0.9,
}
PANS = {
    "kick": 0.0,
    "snare": 0.05,
    "tom_hi": -0.3,
    "tom_lo": 0.3,
    "hat": 0.25,
    "hat_open": 0.25,
    "ride": -0.35,
    "crash": -0.15,
    "bass": 0.0,
    "piano": 0.2,
    "V1": 0.0,
    "V2_lead": 0.0,
    "V2_backing": 0.35,
}


@dataclass
class Render:
    sr: int
    tracks: dict[str, np.ndarray]  # base + derived stems, 24-bit grid, [2, N]
    voice_tracks: dict[str, np.ndarray]  # V1, V2 (all of each voice), V2_lead, V2_backing (mono-summed views)
    inst_tracks: dict[str, np.ndarray]  # instrument slug -> [2, N] (for instrument activity truth)
    gain: float  # global gain applied before quantisation
    drum_hits: list[dict] = field(default_factory=list)
    notes: dict[str, list[dict]] = field(default_factory=dict)
    words: list[dict] = field(default_factory=list)  # lead words (lyrics truth)
    backing_words: list[dict] = field(default_factory=list)  # V2 harmony words in duets
    f0_midi: np.ndarray | None = None  # lead fractional MIDI per sample, NaN where unvoiced
    f0_voice: np.ndarray | None = None  # 1 = V1, 2 = V2, 0 = none (per sample)
    events: dict[str, list[dict]] = field(default_factory=dict)


def _z() -> np.ndarray:
    return np.zeros((2, S.N_SAMPLES))


def _idx(t: float) -> int:
    return int(round(t * S.SR))


def _render_drums(r: Render, tr: dict[str, np.ndarray]) -> None:
    shots = {
        "kick": dsp.kick(),
        "snare": dsp.snare(),
        "tom_hi": dsp.tom(196.0, seed=31),
        "tom_lo": dsp.tom(130.0, seed=32),
        "hat": dsp.hihat(),
        "hat_open": dsp.hihat(open_=True, seed=41),
        "ride": dsp.ride(),
    }
    crash_cache: dict[float, np.ndarray] = {}
    hits: list[tuple[float, str, float]] = []
    for step, inst, vel in S.PICKUP_HITS:
        hits.append((S.snap(S.BAR[0].t + step * S.BEAT / 4), inst, vel))
    for bar, name in sorted(S.BAR_PATTERN.items()):
        for step, inst, vel in S.PATTERNS[name]:
            hits.append((S.step_time(bar, step), inst, round(vel * S.section_vel(bar), 4)))
    for bar, (vel, length) in sorted(S.CRASHES.items()):
        hits.append((S.step_time(bar, 0), f"crash:{length}", round(vel * S.section_vel(bar), 4)))
    hits.sort(key=lambda h: (h[0], h[1]))
    for t, inst, vel in hits:
        if inst.startswith("crash:"):
            length = float(inst.split(":")[1])
            if length not in crash_cache:
                crash_cache[length] = dsp.crash(length_s=length)
            x, inst = crash_cache[length], "crash"
        else:
            x = shots[inst]
        drum, sub = S.DRUM_MAP[inst]
        dsp.place(tr[f"drums_{sub}"], dsp.pan(x * vel * GAINS[sub], PANS[inst]), _idx(t))
        r.drum_hits.append(
            {
                "t": t,
                "inst": inst,
                "drum": drum,
                "sub": sub,
                "vel": vel,
                "bar": S.bar_of(t),
                "pattern": S.BAR_PATTERN.get(S.bar_of(t) or -1, "pickup" if S.bar_of(t) == 0 else None),
            }
        )


def _bass_events() -> list[tuple[float, float, int, float]]:
    ev = []
    sync = [(0, 3, 0), (3, 1, 12), (6, 2, 0), (10, 2, 0), (12, 3, 12)]
    drop = [(s, 2, 12 if (s // 2) % 2 else 0) for s in range(0, 16, 2)]
    for bar in range(1, 29):
        ch = S.CHORDS[bar]
        if ch == "N":
            continue
        root = S.BASS_ROOT[ch]
        if bar in (3, 4) or 13 <= bar <= 15:
            pat = [(0, 16, 0)]
        elif bar == 16:
            pat = [(0, 12, 0)]
        elif 5 <= bar <= 12:
            pat = sync
        elif 18 <= bar <= 25:
            pat = drop
        elif bar == 26:
            pat = [(0, 8, 0), (8, 8, 0)]
        elif bar == 27:
            pat = [(0, 14, 0)]
        else:
            pat = []
        for step, dur, octv in pat:
            t0 = S.step_time(bar, step)
            t1 = S.step_time(bar, step + dur)
            if bar == 16 and step + dur >= 12:
                t1 = S.BAR[16].end
            vel = round((1.0 if step % 4 == 0 else 0.85) * S.section_vel(bar), 4)
            ev.append((t0, round(t1 - t0 - 0.02, 6), root + octv, vel))
    return ev


def _pad_events() -> list[tuple[float, float, int, float]]:
    ev = []
    for bar in range(1, 29):
        ch = S.CHORDS[bar]
        if ch == "N" or bar == 28:
            continue
        b = S.BAR[bar]
        d = b.d if bar != 27 else 3.4  # the final chord is held through bar 28 and released before the end
        for m in S.CHORD_TONES[ch]:
            ev.append((b.t, d, m, 0.7))
    return ev


def _piano_events() -> list[tuple[float, float, int, float]]:
    ev = []
    for bar in list(range(9, 13)) + list(range(18, 22)):
        tones = S.PIANO_TONES[S.CHORDS[bar]]
        order = [0, 1, 2, 3, 2, 1, 0, 1]
        for slot in range(8):
            t0 = S.slot_time(bar, slot)
            t1 = S.slot_time(bar, slot + 1)
            ev.append((t0, round((t1 - t0) * 0.9, 6), tones[order[slot]], 0.65 if slot % 2 == 0 else 0.5))
    return ev


def _render_pitched(r: Render, tr: dict[str, np.ndarray], inst: dict[str, np.ndarray]) -> None:
    bass_ev = _bass_events()
    for t, d, m, v in bass_ev:
        dsp.place(tr["bass"], dsp.pan(dsp.bass_note(m, d, v) * GAINS["bass"], PANS["bass"]), _idx(t))
    pad_ev = _pad_events()
    for t, d, m, v in pad_ev:
        dsp.place(inst["synth_pad"], dsp.pad_note(m, d, v) * GAINS["pad"], _idx(t))
    piano_ev = _piano_events()
    for t, d, m, v in piano_ev:
        dsp.place(tr["piano"], dsp.pan(dsp.piano_note(m, d, v) * GAINS["piano"], PANS["piano"]), _idx(t))
    rs = S.BAR[13].t
    re_ = S.BAR[16].end
    dsp.place(
        inst["synth_fx"], dsp.pan(dsp.riser(re_ - rs, seed=S.SEED % 1000) * GAINS["riser"], 0.0), _idx(rs)
    )
    tr["other"] += inst["synth_pad"] + inst["synth_fx"]

    def note_items(ev):
        return [{"t": t, "d": d, "midi": m, "vel": v} for t, d, m, v in ev]

    r.notes["bass"] = note_items(bass_ev)
    r.notes["other"] = note_items(pad_ev)
    r.notes["piano"] = note_items(piano_ev)
    r.notes["guitar"] = []


def _render_vocals(r: Render, tr: dict[str, np.ndarray], vt: dict[str, np.ndarray]) -> None:
    f0 = np.full(S.N_SAMPLES, np.nan)
    fv = np.zeros(S.N_SAMPLES, dtype=np.int8)
    seed = 100
    for line in S.LINES:
        prev = None
        for k, w in enumerate(line.words, start=1):
            t0 = S.slot_time(line.bar, w.slot)
            t1 = S.slot_time(line.bar, w.slot + w.slots)
            d = round(t1 - t0 - S.WORD_GAP_S, 6)
            seed += 1
            sw = tts.sing(
                tts.word(S.VOICE_TTS[line.voice], w.text.lower()), w.midi, d, prev_midi=prev, seed=seed
            )
            prev = w.midi
            i0 = _idx(t0)
            key = "V1" if line.voice == "V1" else "V2_lead"
            mono = sw.audio * GAINS["lead"]
            dsp.place(vt[key], dsp.pan(mono, PANS[key]), i0)
            n = sw.audio.size
            seg = slice(i0, i0 + n)
            f0[seg] = np.where(sw.voiced, sw.midi, np.nan)
            fv[seg] = 1 if line.voice == "V1" else 2
            r.words.append(
                {
                    "id": f"{line.id}.{k:02d}",
                    "line_id": line.id,
                    "text": w.text,
                    "t": t0,
                    "d": round(n / S.SR, 6),
                    "midi": w.midi,
                    "voice": line.voice,
                    "voiced_s": round(float(sw.voiced.sum()) / S.SR, 6),
                    "nucleus": [round(t0 + sw.nucleus[0], 6), round(t0 + sw.nucleus[1], 6)],
                }
            )
            if line.duet and w.harmony is not None:
                seed += 1
                hb = tts.sing(tts.word("zira", w.text.lower()), w.harmony, d, seed=seed)
                dsp.place(vt["V2_backing"], dsp.pan(hb.audio * GAINS["backing"], PANS["V2_backing"]), i0)
                r.backing_words.append(
                    {
                        "id": f"{line.id}.{k:02d}",
                        "line_id": line.id,
                        "t": t0,
                        "d": round(hb.audio.size / S.SR, 6),
                        "midi": w.harmony,
                        "voice": "V2",
                    }
                )
    tr["lead_vocals"] += vt["V1"] + vt["V2_lead"]
    tr["backing_vocals"] += vt["V2_backing"]
    r.f0_midi = f0
    r.f0_voice = fv
    r.notes["vocals"] = [{"t": w["t"], "d": w["d"], "midi": w["midi"], "vel": 0.8} for w in r.words]


def _gate() -> np.ndarray:
    """Hard cut into the silent bar 17 (5 ms fade before 32.5 s) and a 50 ms fade to zero at the very end."""
    g = np.ones(S.N_SAMPLES)
    a, b = _idx(S.BAR[17].t), _idx(S.BAR[17].end)
    f = int(0.005 * S.SR)
    g[a - f : a] = np.linspace(1, 0, f, endpoint=False)
    g[a:b] = 0.0
    e = int(0.05 * S.SR)
    g[-e:] = np.linspace(1, 0, e) ** 2
    return g


def render() -> Render:
    base = [
        "drums_kick",
        "drums_snare",
        "drums_toms",
        "drums_hihat",
        "drums_ride",
        "drums_crash",
        "bass",
        "guitar",
        "piano",
        "other",
        "lead_vocals",
        "backing_vocals",
    ]
    tr = {k: _z() for k in base}
    vt = {k: _z() for k in ("V1", "V2_lead", "V2_backing")}
    inst = {k: _z() for k in ("synth_pad", "synth_fx")}
    r = Render(S.SR, tr, {}, {}, 1.0)
    _render_drums(r, tr)
    _render_pitched(r, tr, inst)
    _render_vocals(r, tr, vt)
    g = _gate()
    for d in (tr, vt, inst):
        for k in d:
            d[k] *= g
    raw_mix = sum(tr[k] for k in base)
    gain = float(10 ** (-1.0 / 20) / np.max(np.abs(raw_mix)))
    r.gain = gain
    for k in base:
        tr[k] = quantize24(tr[k] * gain)
    for d in (vt, inst):
        for k in d:
            d[k] = quantize24(d[k] * gain)
    tr["drums"] = sum(tr[f"drums_{s}"] for s in ("kick", "snare", "toms", "hihat", "ride", "crash"))
    tr["vocals"] = tr["lead_vocals"] + tr["backing_vocals"]
    tr["mix"] = tr["vocals"] + tr["drums"] + tr["bass"] + tr["guitar"] + tr["piano"] + tr["other"]
    tr["instrumental"] = tr["mix"] - tr["vocals"]
    r.voice_tracks = {
        "V1": vt["V1"],
        "V2": vt["V2_lead"] + vt["V2_backing"],
        "V2_lead": vt["V2_lead"],
        "V2_backing": vt["V2_backing"],
    }
    r.inst_tracks = {
        "drums": tr["drums"],
        "bass": tr["bass"],
        "synth_pad": inst["synth_pad"],
        "synth_fx": inst["synth_fx"],
        "piano": tr["piano"],
        "voice": tr["vocals"],
    }
    # drum hits / notes inside the gated silence would be inaudible: there are none by construction (checked in tests)
    return r
