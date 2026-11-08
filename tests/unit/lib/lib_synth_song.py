"""A small, deterministic song folder for the loader parity tests, written with the contract writers
(mvh.contract.curvefile.assemble and mvh.contract.events). Synthetic data only: no audio, no real lyrics.

Covers: every resample policy, NaN-aware pitch with gaps, a 1 Hz file, per-voice mouth_open (3 voices),
a pickup bar, a 3/4 bar, virtual beats, an E000 lead-in and a partial count, overlapping sections and a gap,
tiered cues with ties, onsets for vizState, lyrics with words, singing (duet + backing) and meaning.

    python tests/unit/lib/lib_synth_song.py <out_dir>
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

from mvh.contract import conventions as cv
from mvh.contract.curvefile import ChannelData, assemble
from mvh.contract.events import dumps_events, dumps_json, make_envelope

DURATION = 8.0
SR = 48000
N_SAMPLES = int(DURATION * SR)
N = cv.n_curve_frames(N_SAMPLES, SR)  # 800 frames at 100 Hz
PROV = {"stage": "synthetic", "notes": ["lib parity fixture"]}


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def beats() -> list[dict]:
    """Pickup beat (bar 0, beat 4 of 4), then bars of 4, 4, 3, 4, 4, ...; beats 9 and 10 are virtual."""
    sizes = [4, 4, 3] + [4] * 10
    out = [{"bar": 0, "beat_in_bar": 4, "beats_in_bar": 4}]
    for b, nb in enumerate(sizes, start=1):
        for k in range(nb):
            out.append({"bar": b, "beat_in_bar": k + 1, "beats_in_bar": nb})
    items = []
    t = 0.25
    for i in range(15):
        it = dict(out[i])
        it.update(
            {
                "beat_index": i,
                "t": round(t, 6),
                "in_pulse": i not in (9, 10),
                "strength": round(0.5 + 0.4 * math.sin(i), 6),
                "conf": 0.9,
            }
        )
        items.append(it)
        t += 0.5 + 0.02 * math.sin(i * 1.3)  # slightly uneven grid
    return items


def counts(bts) -> list[dict]:
    def t_of(b):
        return bts[b]["t"] if 0 <= b < len(bts) else round(bts[0]["t"] + 0.5 * b, 6)

    rows = [
        ("E000", -3, 4, 5, True, True, None),
        ("E001", 1, 8, 1, False, False, "P01"),
        ("E002", 9, 3, 1, True, False, "P01"),
        ("E003", 12, 8, 1, False, False, "P02"),
    ]
    out = []
    for cid, sb, ln, fc, partial, lead_in, ph in rows:
        t0 = t_of(sb)
        t1 = t_of(sb + ln) if sb + ln < len(bts) else t0 + 0.5 * ln
        out.append(
            {
                "id": cid,
                "t": t0,
                "d": round(t1 - t0, 6),
                "start_beat": sb,
                "len": ln,
                "first_count": fc,
                "phrase_id": ph,
                "section_id": None if ph is None else "S01",
                "partial": partial,
                "lead_in": lead_in,
                "in_pulse": not partial,
                "accents": [round(0.2 + 0.1 * ((k * 7) % 9), 6) for k in range(ln)],
            }
        )
    return out


def curves() -> list[ChannelData]:
    i = np.arange(N, dtype=np.float64)
    t = i / 100.0
    f32 = lambda a: np.asarray(a, dtype=np.float32)  # noqa: E731
    ch = {
        "bands.bass": 0.5 + 0.4 * np.sin(t * 2.1),
        "bands.bass_db": -30 + 10 * np.sin(t * 2.1),
        "bands.bass_viz": 0.4 + 0.3 * np.sin(t * 3.3 + 0.2),
        "bands.mid_viz": 0.35 + 0.25 * np.cos(t * 1.7),
        "bands.high_viz": 0.3 + 0.2 * np.sin(t * 5.1),
        "bands.level": 0.5 + 0.3 * np.sin(t * 0.9),
        "tempo.bpm": 118 + 4 * np.sin(t * 0.7),
        "rhythm.in_pulse": ((t < 4.6) | (t > 5.6)).astype(float),
        "choreo.accent": np.abs(np.sin(t * 6.0)) ** 4,
    }
    for name in ("hits.kick", "hits.kick_raw", "hits.mid", "hits.high"):
        env = np.zeros(N)
        period = {"hits.kick": 0.5, "hits.kick_raw": 0.5, "hits.mid": 0.37, "hits.high": 0.23}[name]
        rel = 0.0 if name.endswith("_raw") else 0.18
        for k in range(1, int(DURATION / period)):
            te = round(k * period + 0.013 * math.sin(k), 6)
            peak = 0.7 + 0.5 * abs(math.sin(k * 0.9))
            a, b = cv.flash_samples(te)
            tail = np.where(i > b, np.exp(-(t - b / 100.0) / rel) * peak if rel > 0 else 0.0, 0.0)
            env = np.maximum(env, tail)
            env[a : b + 1] = np.maximum(env[a : b + 1], peak)
        ch[name] = env
    data = [ChannelData(k, f32(v)) for k, v in ch.items()]

    # vocal: NaN-aware pitch with gaps; three voices of mouth_open
    midi = 60 + 5 * np.sin(t * 1.3) + 0.3 * np.sin(t * 17)
    gap = ((t >= 1.0) & (t < 1.37)) | ((t >= 3.005) & (t < 3.5)) | (t >= 7.2) | (t < 0.1)
    midi = np.where(gap, np.nan, midi)
    hz = np.where(gap, np.nan, 440.0 * 2 ** ((midi - 69) / 12))
    voiced = (~gap).astype(float)
    p2, p98 = 55.0, 65.5
    pitch01 = np.clip((np.where(gap, 60.0, midi) - p2) / (p98 - p2), 0, 1)
    conf = np.where(gap, 0.1, 0.8 + 0.1 * np.sin(t))
    m1 = np.where((t >= 0.5) & (t < 2.0) | (t >= 3.5) & (t < 4.0), 0.5 + 0.5 * np.sin(t * 31), 0.0)
    m2 = np.where((t >= 1.75) & (t < 3.0), 0.5 + 0.5 * np.sin(t * 23 + 1), 0.0)
    m3 = np.where((t >= 2.25) & (t < 2.75), 0.4 + 0.4 * np.cos(t * 17), 0.0)
    for k, v in {
        "vocal.f0_hz": hz,
        "vocal.midi": midi,
        "vocal.pitch01": pitch01,
        "vocal.voiced": voiced,
        "vocal.conf": conf,
        "vocal.mouth_open": np.maximum(np.maximum(m1, m2), m3),
        "vocal.mouth_open.V1": m1,
        "vocal.mouth_open.V2": m2,
        "vocal.mouth_open.V3": m3,
    }.items():
        data.append(ChannelData(k, f32(v)))

    # 1 Hz file
    n1 = cv.n_curve_frames(N_SAMPLES, SR, 1)
    data.append(ChannelData("mood.valence", f32(0.5 + 0.3 * np.sin(np.arange(n1) * 0.8))))
    data.append(ChannelData("mood.arousal", f32(0.4 + 0.2 * np.cos(np.arange(n1) * 0.6))))

    # spectrum128 (row-major uint8)
    k = np.arange(128)[None, :]
    spec = 127.5 + 120 * np.sin(t[:, None] * 3.0 + k * 0.11) * np.cos(k * 0.05)
    data.append(
        ChannelData(
            "spectrum128",
            np.clip(np.round(spec), 0, 255).astype(np.uint8),
            meta={"band_edges_hz": [32 * (500 ** (j / 128)) for j in range(129)]},
        )
    )
    return data


def events() -> dict[str, list[dict]]:
    bts = beats()
    ev = {"beats": bts, "counts": counts(bts)}
    ev["sections"] = [
        {
            "id": "S01",
            "t": 0.0,
            "d": 3.0,
            "label": "intro",
            "occurrence": 1,
            "occurrence_label": "intro#1",
            "repeat_group": "A",
            "start_bar": 0,
            "n_bars": 4,
        },
        {
            "id": "S02",
            "t": 3.0,
            "d": 3.0,
            "label": "verse",
            "occurrence": 1,
            "occurrence_label": "verse#1",
            "repeat_group": "B",
            "start_bar": 4,
            "n_bars": 6,
        },
        {
            "id": "S03",
            "t": 5.5,
            "d": 2.0,
            "label": "chorus",
            "occurrence": 1,
            "occurrence_label": "chorus#1",
            "repeat_group": "C",
            "start_bar": 9,
            "n_bars": 4,
        },
    ]
    ev["cues"] = [
        {
            "id": f"Q{k + 1:04d}",
            "t": t,
            "kind": kind,
            "tier": tier,
            "strength": None if tier == 4 else 0.7,
            "lead_in_s": None,
            "next_major_in_s": None,
            "source": {"file": "events/sections.json", "id": "S01"},
        }
        for k, (t, kind, tier) in enumerate(
            [
                (0.0, "section", 1),
                (0.25, "beat", 4),
                (0.75, "downbeat", 3),
                (0.75, "phrase", 2),
                (1.0416, "hit_point", 3),
                (2.0208333, "impact", 2),
                (3.0, "section", 1),
                (3.0, "beat", 4),
                (4.2, "stop", 2),
                (5.5, "drop", 1),
                (6.01, "hit_point", 3),
                (7.9999, "beat", 4),
            ]
        )
    ]
    ob = [
        {
            "t": round(b["t"] + 0.004, 6),
            "strength": round(0.3 + 0.6 * abs(math.sin(b["beat_index"] * 0.7)), 6),
        }
        for b in bts
    ]
    ob.insert(3, {"t": round(ob[2]["t"] + 0.01, 6)})  # two onsets inside one frame, one without strength
    ev["onsets.bass"] = ob
    ev["onsets.mid"] = [
        {"t": round(0.11 + 0.37 * k, 6), "strength": round(0.5 + 0.5 * math.cos(k), 6)} for k in range(21)
    ]
    ev["onsets.high"] = [
        {"t": round(0.05 + 0.23 * k, 6), "strength": round(abs(math.sin(k * 1.7)), 6)} for k in range(34)
    ]
    ev["hits.kick"] = [
        {
            "t": round(k * 0.5 + 0.013 * math.sin(k), 6),
            "t_peak": round(k * 0.5 + 0.02, 6),
            "strength": round(0.7 + 0.5 * abs(math.sin(k * 0.9)), 6),
            "db": -12.0,
        }
        for k in range(1, 16)
    ]
    ev["singing"] = [
        {
            "t": 0.5,
            "d": 1.5,
            "character_id": "C1",
            "voice_id": "V1",
            "line_id": "L001",
            "lead_backing": "lead",
        },
        {
            "t": 1.75,
            "d": 1.25,
            "character_id": "C2",
            "voice_id": "V2",
            "line_id": "L002",
            "lead_backing": "lead",
        },
        {
            "t": 1.75,
            "d": 1.25,
            "character_id": "C1",
            "voice_id": "V1",
            "line_id": "L002",
            "lead_backing": "backing",
        },
        {
            "t": 2.25,
            "d": 0.5,
            "character_id": "C3",
            "voice_id": "V3",
            "line_id": "L003",
            "lead_backing": "backing",
        },
        {
            "t": 3.5,
            "d": 0.5,
            "character_id": "C1",
            "voice_id": "V1",
            "line_id": "L004",
            "lead_backing": "lead",
        },
    ]
    ev["vocal_phrases"] = [
        {
            "id": "VP001",
            "t": 0.1,
            "d": 0.9,
            "median_midi": 61.0,
            "min_midi": 56.0,
            "max_midi": 65.0,
            "mean_db": -20.0,
        },
        {
            "id": "VP002",
            "t": 1.37,
            "d": 1.635,
            "median_midi": 62.0,
            "min_midi": 57.0,
            "max_midi": 65.2,
            "mean_db": -18.0,
        },
    ]
    ev["notes.vocals"] = [
        {"t": round(0.1 + 0.3 * k, 6), "d": 0.25, "midi": 60 + (k % 5), "name": "C4", "vel": 0.7, "conf": 0.8}
        for k in range(20)
    ]
    ev["notes.bass"] = [
        {
            "t": round(0.25 + 0.5 * k, 6),
            "d": 0.4,
            "midi": 40 + (k % 3),
            "name": "E2",
            "vel": round(0.5 + 0.03 * k, 6),
            "conf": 0.9,
        }
        for k in range(15)
    ]
    return ev


def lyrics() -> dict:
    lines, words = [], []
    spans = [(0.5, 1.5), (1.75, 1.25), (2.25, 0.5), (3.5, 0.5)]
    for li, (t0, d) in enumerate(spans, start=1):
        lid = f"L{li:03d}"
        nw = 3 if li != 3 else 2
        for k in range(nw):
            wt = t0 + d * k / nw + (0.05 if k else 0.0)
            words.append(
                {
                    "id": f"{lid}.{k + 1:02d}",
                    "line_id": lid,
                    "t": round(wt, 6),
                    "d": round(d / nw * 0.8, 6),
                    "text": "la",
                    "conf": 0.8,
                }
            )
        lines.append(
            {
                "id": lid,
                "t": t0,
                "d": d,
                "text": " ".join(["la"] * nw),
                "section_id": "S01" if t0 < 3 else "S02",
                "text_group": f"T{li:02d}",
                "repeat_group": None,
                "conf": 0.8,
                "grade": "B",
                "first_word": f"{lid}.01",
                "n_words": nw,
                "backing": li == 3,
                "speaker_hint": None,
                "timing_source": "ctc",
            }
        )
    return {
        "schema": "mvh/files/lyrics",
        "schema_version": "1.0.0-rc.1",
        "provenance": PROV,
        "source": {"kind": "user", "lrclib_id": None, "duration_diff_s": None, "has_word_sync": False},
        "instrumental": False,
        "language": "xx",
        "grade": "B",
        "lyrics_match_score": None,
        "coverage": 0.9,
        "lines": lines,
        "words": words,
    }


def meaning() -> dict:
    prov = {"source": "user", "status": "user", "cites": [{"id": "S01"}]}
    return {
        "schema": "mvh/files/meaning",
        "schema_version": "1.0.0-rc.1",
        "status": "user",
        "logline": "a synthetic song",
        "summary": None,
        "themes": [],
        "perspective": {"narrator": None, "addressee": None},
        "characters": [],
        "setting": None,
        "motifs": [],
        "symbolism": [],
        "sections": [
            {
                "section_id": "S01",
                "t0": 0.0,
                "t1": 3.0,
                "occurrence_label": "intro#1",
                "feel": "calm",
                "meaning": "waking up",
                "emotion": {"lyric": "hope", "audio": "calm", "agree": True},
                "palette_hint": ["#112233"],
                "movement_hint": "slow",
                "camera_hint": "wide",
                "characters_present": ["C1"],
                "do_not": ["no text on screen"],
                "provenance": prov,
            },
            {
                "section_id": "S03",
                "t0": 5.5,
                "t1": 7.5,
                "occurrence_label": "chorus#1",
                "feel": "bright",
                "meaning": None,
                "emotion": {"lyric": None, "audio": None, "agree": None},
                "palette_hint": [],
                "movement_hint": None,
                "camera_hint": None,
                "characters_present": [],
                "do_not": ["no faces", "no logos"],
                "provenance": prov,
            },
        ],
        "palette": ["#112233"],
        "tone": None,
        "do_not": ["no logos"],
        "open_questions": [],
    }


def build(out: Path | str) -> Path:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    assemble(out, curves())
    files = []
    for name, items in events().items():
        env = make_envelope(name, items, PROV)
        rel = f"events/{name}.json"
        _write(out / rel, dumps_events(env))
        files.append({"path": rel, "kind": "events", "stage": "synthetic", "events": name})
    _write(out / "lyrics/lyrics.json", dumps_json(lyrics()))
    _write(out / "meaning/meaning.json", dumps_json(meaning()))
    files += [
        {"path": "lyrics/lyrics.json", "kind": "json", "stage": "synthetic"},
        {"path": "meaning/meaning.json", "kind": "json", "stage": "synthetic"},
    ]
    manifest = {
        "schema": "mvh/manifest",
        "schema_version": "1.0.0-rc.1",
        "slug": "lib-synth",
        "source": {
            "file_name": "synthetic",
            "pcm_sha256": "0" * 64,
            "duration_s": DURATION,
            "sample_rate": SR,
            "channels": 2,
            "n_samples": N_SAMPLES,
        },
        "files": files,
        "warnings": [],
    }
    _write(out / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1) + "\n")
    return out


if __name__ == "__main__":
    print(build(sys.argv[1]))
