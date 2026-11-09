"""Minimal deterministic Standard MIDI File (format 1) writer. Stdlib only.

Times are seconds on the song clock; they are converted to ticks with a tempo map given as
[(t_seconds, bpm)] change points (a constant tempo is [(0.0, bpm)]), and optional time-signature changes
[(t_seconds, numerator, denominator)].
"""

from __future__ import annotations

import struct
from typing import Iterable, Sequence

__all__ = ["write_smf", "seconds_to_ticks"]

PPQ = 480


def _vlq(n: int) -> bytes:
    n = int(n)
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(out))


def seconds_to_ticks(t: float, tempo_map: Sequence[tuple[float, float]], ppq: int = PPQ) -> int:
    ticks = 0.0
    for i, (t0, bpm) in enumerate(tempo_map):
        t1 = tempo_map[i + 1][0] if i + 1 < len(tempo_map) else float("inf")
        if t <= t0:
            break
        seg = min(t, t1) - t0
        ticks += seg * bpm / 60.0 * ppq
    return int(round(ticks))


def _track(events: Iterable[tuple[int, int, bytes]]) -> bytes:
    """events: (tick, order, data) sorted; returns an MTrk chunk with end-of-track."""
    body = b""
    last = 0
    for tick, _, data in sorted(events, key=lambda e: (e[0], e[1])):
        body += _vlq(tick - last) + data
        last = tick
    body += b"\x00\xff\x2f\x00"
    return b"MTrk" + struct.pack(">I", len(body)) + body


def write_smf(
    tracks: Sequence[tuple[str, Sequence[tuple[float, float, int, float]]]],
    tempo_map: Sequence[tuple[float, float]],
    time_sigs: Sequence[tuple[float, int, int]] = ((0.0, 4, 4),),
    programs: Sequence[int] | None = None,
) -> bytes:
    """tracks: [(name, [(t, d, midi, vel01), ...])]. Returns the SMF bytes (format 1: tempo track + one per source)."""
    meta: list[tuple[int, int, bytes]] = [(0, 0, b"\xff\x03" + _vlq(len(b"tempo")) + b"tempo")]
    for t0, bpm in tempo_map:
        us = int(round(60_000_000 / bpm))
        meta.append((seconds_to_ticks(t0, tempo_map), 1, b"\xff\x51\x03" + us.to_bytes(3, "big")))
    for t0, num, den in time_sigs:
        dd = {1: 0, 2: 1, 4: 2, 8: 3, 16: 4}[den]
        meta.append((seconds_to_ticks(t0, tempo_map), 2, b"\xff\x58\x04" + bytes([num, dd, 24, 8])))
    chunks = [_track(meta)]
    for ti, (name, notes) in enumerate(tracks):
        ch = ti % 16
        if ch == 9:
            ch = 10
        nm = name.encode("utf-8")
        ev: list[tuple[int, int, bytes]] = [(0, 0, b"\xff\x03" + _vlq(len(nm)) + nm)]
        if programs is not None:
            ev.append((0, 1, bytes([0xC0 | ch, programs[ti] & 0x7F])))
        for t, d, m, v in notes:
            on = seconds_to_ticks(t, tempo_map)
            off = max(on + 1, seconds_to_ticks(t + d, tempo_map))
            vel = max(1, min(127, int(round(v * 127))))
            ev.append((on, 3, bytes([0x90 | ch, int(m) & 0x7F, vel])))
            ev.append((off, 2, bytes([0x80 | ch, int(m) & 0x7F, 0])))  # note-offs before note-ons at a tick
        chunks.append(_track(ev))
    head = b"MThd" + struct.pack(">IHHH", 6, 1, len(chunks), PPQ)
    return head + b"".join(chunks)
