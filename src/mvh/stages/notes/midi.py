# ruff: noqa: E501  (long numeric tables / docstrings)
"""Standard MIDI files with a tempo map from the beat grid (owner M3b; used by notes and vocals).

The map makes MIDI time equal song time: tick 0 = the first sample of audio/mix.flac; every beat of events/beats.json
lands on a multiple of PPQ (one beat = one quarter note; the lead-in before the first beat is a whole number of quarters), with a tempo event at every beat whose interval differs from
the previous one; before the first beat and after the last the first/last interval continues. Time signatures come from
events/bars.json (``beats_in_bar``/4). Note times are mapped through the same piecewise-linear map, so a note's seconds
survive the round trip within one tick.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

PPQ = 480
PROGRAMS = {"bass": 33, "piano": 0, "guitar": 29, "other": 89, "vocals": 52}  # GM: finger bass, piano, overdrive, pad, choir


def _us(seconds: float) -> int:
    return int(min(16777215, max(1, round(seconds * 1e6))))


@dataclass
class TempoMap:
    beats: np.ndarray            # beat times (s), strictly increasing
    bars: list[tuple[float, int]]  # (bar start time, beats_in_bar)
    description: str

    @classmethod
    def from_grid(cls, beat_times: Sequence[float], bars: Sequence[tuple[float, int]] = (), bpm: float | None = None,
                  duration_s: float = 0.0) -> "TempoMap":
        b = np.unique(np.asarray([t for t in beat_times if np.isfinite(t)], np.float64))
        if b.size < 2:
            ibi = 60.0 / float(bpm or 120.0)
            b = np.arange(0.0, max(duration_s, ibi * 2) + ibi, ibi)
            desc = f"constant {60 / ibi:.3f} BPM (no beat grid)"
        else:
            ibis = np.diff(b)
            desc = (f"one tempo event per beat from events/beats.json ({b.size} beats, {60 / np.median(ibis):.2f} BPM median); "
                    f"PPQ {PPQ}; tick 0 = first sample of audio/mix.flac; time signatures from events/bars.json")
        return cls(b, [(float(t), int(n)) for t, n in bars if n], desc)

    @property
    def lead_quarters(self) -> int:
        """Quarter notes before the first beat (the lead-in from t = 0 is stretched to a whole number of them)."""
        b0, first = float(self.beats[0]), float(self.beats[1] - self.beats[0])
        return int(np.ceil(b0 / first - 1e-9)) if b0 > 1e-6 else 0

    @property
    def qpos(self) -> np.ndarray:
        """Quarter-note position of every beat. Normally consecutive integers; a gap in the grid longer than 1.5 median
        intervals (a beatless break) spans round(gap / median) quarters, so tempos stay musical and within MIDI range."""
        ib = np.diff(self.beats)
        med = float(np.median(ib))
        q = np.where(ib > 1.5 * med, np.maximum(1, np.round(ib / med)), 1).astype(np.int64)
        return self.lead_quarters + np.concatenate([[0], np.cumsum(q)])

    def ticks(self, t: float | np.ndarray) -> np.ndarray:
        """Song seconds -> ticks (float): t = 0 is tick 0, beats on their quarter positions, linear in between,
        extrapolated with the last interval after the last beat."""
        b = self.beats
        t = np.asarray(t, np.float64)
        m = self.lead_quarters
        qp = self.qpos.astype(np.float64)
        last = (b[-1] - b[-2]) / (qp[-1] - qp[-2])
        k = np.interp(t, b, qp)
        k = np.where(t > b[-1], qp[-1] + (t - b[-1]) / last, k)
        pre = (t / b[0] * m) if m > 0 else np.zeros_like(t)
        return np.where(t < b[0], pre, k) * PPQ

    def tempo_events(self) -> list[tuple[int, int]]:
        """[(tick, microseconds per quarter)]: the lead-in tempo at tick 0, then one at every beat whose interval
        differs from the previous one (the last interval continues after the last beat)."""
        b = self.beats
        ib = np.diff(b)
        qp = self.qpos
        m = self.lead_quarters
        ev: list[tuple[int, int]] = []
        if m > 0:
            ev.append((0, _us(b[0] / m)))
        for i in range(b.size - 1):
            us = _us(ib[i] / (qp[i + 1] - qp[i]))
            if not ev or us != ev[-1][1]:
                ev.append((int(qp[i]) * PPQ, us))
        return ev

    def timesig_events(self) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        for t, n in self.bars:
            tk = int(round(float(self.ticks(t))))
            if tk < 0:
                tk = 0
            if not out or out[-1][1] != n:
                if out and out[-1][0] == tk:
                    out[-1] = (tk, n)
                else:
                    out.append((tk, n))
        return out


def smf_bytes(tracks: Mapping[str, Sequence[Mapping]], tmap: TempoMap) -> bytes:
    """Type-1 SMF: track 0 = tempo map + time signatures, then one track per source (name = source); notes are dicts
    with t, d, midi, vel (0..1). Deterministic bytes."""
    import mido

    mf = mido.MidiFile(type=1, ticks_per_beat=PPQ)
    t0 = mido.MidiTrack()
    t0.append(mido.MetaMessage("track_name", name="tempo map", time=0))
    meta: list[tuple[int, int, mido.MetaMessage]] = []
    for tk, us in tmap.tempo_events():
        meta.append((tk, 0, mido.MetaMessage("set_tempo", tempo=us, time=0)))
    for tk, n in tmap.timesig_events() or [(0, 4)]:
        meta.append((tk, 1, mido.MetaMessage("time_signature", numerator=n, denominator=4, time=0)))
    meta.sort(key=lambda x: (x[0], x[1]))
    last = 0
    for tk, _o, msg in meta:
        t0.append(msg.copy(time=tk - last))
        last = tk
    mf.tracks.append(t0)
    for ch, (name, notes) in enumerate(tracks.items()):
        chan = ch if ch < 9 else ch + 1
        tr = mido.MidiTrack()
        tr.append(mido.MetaMessage("track_name", name=name, time=0))
        tr.append(mido.Message("program_change", program=PROGRAMS.get(name, 0), channel=chan, time=0))
        evs: list[tuple[int, int, int, int]] = []  # (tick, order, note, velocity) order 0 = off first
        for n in notes:
            on = int(round(float(tmap.ticks(float(n["t"])))))
            off = int(round(float(tmap.ticks(float(n["t"]) + float(n["d"])))))
            on = max(on, 0)
            off = max(off, on + 1)
            vel = int(min(127, max(1, round(float(n.get("vel", 0.8)) * 127))))
            evs.append((on, 1, int(n["midi"]), vel))
            evs.append((off, 0, int(n["midi"]), 0))
        evs.sort()
        last = 0
        for tk, order, m, v in evs:
            typ = "note_on" if order == 1 else "note_off"
            tr.append(mido.Message(typ, note=m, velocity=v if order == 1 else 0, channel=chan, time=tk - last))
            last = tk
        mf.tracks.append(tr)
    bio = io.BytesIO()
    mf.save(file=bio)
    return bio.getvalue()


def tempo_map_from_ctx(ctx, duration_s: float) -> TempoMap:
    """Build the map from events/beats.json + events/bars.json (+ meta/tempo.json bpm when there is no grid)."""
    beats, bars, bpm = [], [], None
    try:
        beats = [float(it["t"]) for it in ctx.events("beats").items]
    except Exception:  # noqa: BLE001
        pass
    try:
        bars = [(float(it["t"]), int(it.get("beats_in_bar") or 0)) for it in ctx.events("bars").items]
    except Exception:  # noqa: BLE001
        pass
    try:
        bpm = float(ctx.upstream("rhythm").json("meta/tempo.json").get("bpm"))
    except Exception:  # noqa: BLE001
        pass
    return TempoMap.from_grid(beats, bars, bpm, duration_s)
