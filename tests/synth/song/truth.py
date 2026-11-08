# ruff: noqa: E501  (long data tables / docstrings in generated-fixture code)
"""Derived ground truth: beats/bars/counts/grooves/accents/hit points/holds/cues from the score and the rendered events.

Everything here is a deterministic function of score.py and the Render (event times on the sample grid).
The formulas for the composite fields (accent, syncopation, hit-point strength) are documented inline and copied
into _truth/truth.json["formulas"].
"""

from __future__ import annotations

from typing import Any

from mvh.contract import conventions as cv

from . import score as S

__all__ = [
    "beats",
    "bars",
    "counts",
    "grooves",
    "groove_protos",
    "accents",
    "hit_points",
    "holds",
    "cues",
    "FORMULAS",
    "syncopation",
    "chords",
    "vocal_phrases",
    "lead_notes",
]

FORMULAS = {
    "accent": "per beat: max(kick vel, 0.9*snare vel, crash vel, 0.7*tom vel) of hits within +-30 ms, +0.15 if a lead word starts "
    "within +-60 ms, +0.10 if a phrase starts on the beat; clipped to 0..1; 0 for beats outside pulse regions",
    "syncopation": "weights w[16] = 5 (step 0), 4 (8), 3 (4, 12), 2 (even 8ths), 1 (odd 16ths); S = sum over onsets s (kick or snare) "
    "with no onset at s+1 of max(0, w[s+1] - w[s]); syncopation = min(1, S / 12)",
    "swing": "programmed long/short 8th ratio of the bar (1.0 straight, 1.5 = 60:40)",
    "hit_point": "beats with >= 3 coinciding kinds among drum (kick/snare), cymbal (crash), impact, vocal_onset, chord (chord change on "
    "a downbeat), section (section start), plus the stop; strength = clip(0.3*accent + 0.1*n_kinds + 0.1*impact strength, 0, 1) "
    "(stop: 0.85); rank by strength desc then time",
    "holds": "lead vocal notes >= 0.7 s (vocal_note, strength = min(1, d/1.5)); the final held chord bars 27-28 (chord); "
    "decay tail Y001 (decay); silence Z001 (silence)",
    "cues": "tier 1 section starts (lead_in = 2.0 s = one 4/4 bar), build start (lead_in 2.0), drop (lead_in = drop - build start); "
    "tier 2 phrases, impacts, stops, silences (lead_in null); tier 3 hit points and downbeats; tier 4 every beat "
    "(reference only: strength and lead_in null); co-timed candidates are merged into ONE cue (D37: tier = best, kind = highest priority, kinds[] and sources[] list all); next_major_in_s = time to the next tier-1 cue strictly after t",
}

_W16 = [5, 1, 2, 1, 3, 1, 2, 1, 4, 1, 2, 1, 3, 1, 2, 1]


def beats() -> list[dict[str, Any]]:
    return [
        {
            "beat_index": b.beat_index,
            "t": b.t,
            "bar": b.bar,
            "beat_in_bar": b.beat_in_bar,
            "beats_in_bar": b.beats_in_bar,
            "in_pulse": b.in_pulse,
        }
        for b in S.BEATS
    ]


def bars() -> list[dict[str, Any]]:
    first = {}
    for b in S.BEATS:
        first.setdefault(b.bar, b.beat_index)
    return [
        {
            "bar": b.bar,
            "t": b.t,
            "d": b.d,
            "beats_in_bar": b.beats_in_bar,
            "n_beats": b.n_beats,
            "first_beat": first[b.bar],
            "pickup": b.pickup,
            "in_pulse": b.in_pulse,
            "swing": b.swing,
        }
        for b in S.BARS
    ]


def lead_notes(words: list[dict]) -> list[dict]:
    return [
        {"t": w["t"], "d": w["d"], "midi": w["midi"], "vel": 0.8, "word_id": w["id"], "voice": w["voice"]}
        for w in words
    ]


def accents(drum_hits: list[dict], words: list[dict]) -> dict[int, float]:
    phrase_starts = {S.BAR[p.start_bar].t for p in S.PHRASES}
    out = {}
    for b in S.BEATS:
        if not b.in_pulse:
            out[b.beat_index] = 0.0
            continue
        a = 0.0
        for h in drum_hits:
            if abs(h["t"] - b.t) <= 0.030:
                w = {
                    "kick": 1.0,
                    "snare": 0.9,
                    "cymbal": 1.0 if h["inst"] == "crash" else 0.0,
                    "tom": 0.7,
                }.get(h["drum"], 0.0)
                a = max(a, w * h["vel"])
        if any(abs(w["t"] - b.t) <= 0.060 for w in words):
            a += 0.15
        if any(abs(t - b.t) < 1e-6 for t in phrase_starts):
            a += 0.10
        out[b.beat_index] = round(min(1.0, a), 4)
    return out


def counts(acc: dict[int, float]) -> list[dict[str, Any]]:
    """Eight-counts: 2-bar units restarting at every phrase start (= every section start here)."""
    out: list[dict[str, Any]] = []
    first = {b.bar: b.beat_index for b in reversed(S.BEATS)}
    b1 = first[1]
    out.append(
        {
            "id": "E000",
            "t": S.BAR[1].t - 4 * S.BEAT,
            "d": 4 * S.BEAT,
            "start_beat": b1 - 4,
            "len": 4,
            "first_count": 5,
            "phrase_id": None,
            "section_id": None,
            "partial": False,
            "lead_in": True,
            "in_pulse": False,
            "accents": [acc.get(i, 0.0) for i in range(b1 - 4, b1)],
        }
    )
    n = 0
    for p in S.PHRASES:
        bar_list = list(range(p.start_bar, p.start_bar + p.n_bars))
        for i in range(0, len(bar_list), 2):
            unit = bar_list[i : i + 2]
            nb = sum(S.BAR[b].n_beats for b in unit)
            start = first[unit[0]]
            n += 1
            meter8 = 6 if all(S.BAR[b].beats_in_bar == 3 for b in unit) else 8
            out.append(
                {
                    "id": f"E{n:03d}",
                    "t": S.BAR[unit[0]].t,
                    "d": nb * S.BEAT,
                    "start_beat": start,
                    "len": nb,
                    "first_count": 1,
                    "phrase_id": p.id,
                    "section_id": p.section_id,
                    "partial": nb < meter8,
                    "lead_in": False,
                    "in_pulse": all(S.BAR[b].in_pulse for b in unit),
                    "accents": [acc.get(k, 0.0) for k in range(start, start + nb)],
                }
            )
    return out


def syncopation(onsets: set[int]) -> float:
    s = 0
    for st in onsets:
        nxt = (st + 1) % 16
        if nxt not in onsets:
            s += max(0, _W16[nxt] - _W16[st])
    return round(min(1.0, s / 12.0), 4)


def _pattern_rows(hits: list[tuple[int, str, float]]) -> dict[str, list[float]]:
    rows = {k: [0.0] * 16 for k in ("kick", "snare", "hat", "perc")}
    for step, inst, vel in hits:
        r = S.GROOVE_ROW[inst]
        rows[r][step] = max(rows[r][step], vel)
    return rows


def groove_protos() -> list[dict[str, Any]]:
    out = []
    for name, gid in S.GROOVE_IDS.items():
        hits = S.PATTERNS[name]
        bars_ = sorted(b for b, p in S.BAR_PATTERN.items() if p == name)
        on = {s for s, i, _ in hits if i in ("kick", "snare")}
        out.append(
            {
                "id": gid,
                "n_bars": len(bars_),
                "bars": bars_,
                "swing": S.BAR[bars_[0]].swing,
                "syncopation": syncopation(on),
                "prototype": _pattern_rows(hits),
                "pattern_name": name,
            }
        )
    return out


def grooves() -> list[dict[str, Any]]:
    out = []
    for bar, name in sorted(S.BAR_PATTERN.items()):
        hits = list(S.PATTERNS[name])
        if bar in S.CRASHES:
            hits.append((0, "crash", S.CRASHES[bar][0]))
        on = {s for s, i, _ in S.PATTERNS[name] if i in ("kick", "snare")}
        b = S.BAR[bar]
        out.append(
            {
                "t": b.t,
                "d": b.d,
                "bar": bar,
                "groove_id": S.GROOVE_IDS[name],
                "swing": b.swing,
                "syncopation": syncopation(on),
                "pattern": _pattern_rows(hits),
            }
        )
    return out


def chords() -> list[dict[str, Any]]:
    """Chord segments (consecutive equal chords merged), snapped to beats; 'N' before bar 1 and in the silent bar."""
    first = {b.bar: b.beat_index for b in reversed(S.BEATS)}
    segs = [{"t": 0.0, "end": S.BAR[1].t, "label": "N", "beat_index": None}]
    for bar in range(1, 29):
        lab = S.CHORDS[bar]
        b = S.BAR[bar]
        if segs[-1]["label"] == lab:
            segs[-1]["end"] = b.end
        else:
            segs.append({"t": b.t, "end": b.end, "label": lab, "beat_index": first[bar]})
    out = []
    for s in segs:
        lab = s["label"]
        if lab == "N":
            root, qual = None, "N"
        else:
            root, qual = S.ROOT_PC[lab], lab.split(":")[1]
        out.append(
            {
                "t": s["t"],
                "d": round(s["end"] - s["t"], 6),
                "label": lab,
                "root_pc": root,
                "quality": qual,
                "bass_pc": root,
                "conf": 1.0,
                "beat_index": s["beat_index"],
            }
        )
    return out


def vocal_phrases(words: list[dict]) -> list[dict[str, Any]]:
    """One vocal phrase per lyric line (the lead voice's words)."""
    out = []
    for i, line in enumerate(S.LINES, start=1):
        ws = [w for w in words if w["line_id"] == line.id]
        t0, t1 = ws[0]["t"], max(w["t"] + w["d"] for w in ws)
        ms = sorted(w["midi"] for w in ws)
        out.append(
            {
                "id": f"VP{i:03d}",
                "t": t0,
                "d": round(t1 - t0, 6),
                "line_id": line.id,
                "voice": line.voice,
                "median_midi": float(ms[len(ms) // 2])
                if len(ms) % 2
                else float((ms[len(ms) // 2 - 1] + ms[len(ms) // 2]) / 2),
                "min_midi": float(ms[0]),
                "max_midi": float(ms[-1]),
            }
        )
    return out


def hit_points(
    acc: dict[int, float], drum_hits: list[dict], words: list[dict], impacts: list[dict], stop: dict
) -> list[dict]:
    sec_t = {S.BAR[s.start_bar].t: s.id for s in S.SECTIONS}
    chord_change = {
        S.BAR[b].t for b in range(1, 29) if S.CHORDS[b] not in ("N",) and S.CHORDS.get(b - 1) != S.CHORDS[b]
    }
    imp_t = {i["t"]: i["id"] for i in impacts}
    cands = []
    for b in S.BEATS:
        if not b.in_pulse:
            continue
        kinds, sources = [], [{"file": "events/beats.json", "id": f"beat:{b.beat_index}"}]
        near = [h for h in drum_hits if abs(h["t"] - b.t) <= 0.03]
        if any(h["drum"] in ("kick", "snare") for h in near):
            kinds.append("drum")
        if any(h["inst"] == "crash" for h in near):
            kinds.append("cymbal")
        it = next((t for t in imp_t if abs(t - b.t) < 1e-6), None)
        if it is not None:
            kinds.append("impact")
            sources.append({"file": "events/impacts.json", "id": imp_t[it]})
        if any(abs(w["t"] - b.t) <= 0.06 for w in words):
            kinds.append("vocal_onset")
        if any(abs(t - b.t) < 1e-6 for t in chord_change):
            kinds.append("chord")
        st = next((t for t in sec_t if abs(t - b.t) < 1e-6), None)
        if st is not None:
            kinds.append("section")
            sources.append({"file": "events/sections.json", "id": sec_t[st]})
        if len(kinds) >= 3:
            istr = next((i["strength"] for i in impacts if abs(i["t"] - b.t) < 1e-6), 0.0)
            cands.append(
                {
                    "t": b.t,
                    "strength": round(min(1.0, 0.3 * acc[b.beat_index] + 0.1 * len(kinds) + 0.1 * istr), 4),
                    "kinds": kinds,
                    "sources": sources,
                }
            )
    cands.append(
        {
            "t": stop["t"],
            "strength": 0.85,
            "kinds": ["stop"],
            "sources": [{"file": "events/stops.json", "id": stop["id"]}],
        }
    )
    ranked = sorted(cands, key=lambda c: (-c["strength"], c["t"]))
    for r, c in enumerate(ranked, start=1):
        c["rank"] = r
    cands.sort(key=lambda c: c["t"])
    for i, c in enumerate(cands, start=1):
        c["id"] = f"H{i:03d}"
    return [
        {
            "id": c["id"],
            "t": c["t"],
            "strength": c["strength"],
            "rank": c["rank"],
            "kinds": c["kinds"],
            "sources": c["sources"],
        }
        for c in cands
    ]


def holds(words: list[dict], vphr: list[dict], decay: dict, silence: dict) -> list[dict]:
    items = []
    for w in words:
        if w["d"] >= 0.7:
            vp = next(p for p in vphr if p["line_id"] == w["line_id"])
            items.append(
                {
                    "t": w["t"],
                    "d": w["d"],
                    "kind": "vocal_note",
                    "strength": round(min(1.0, w["d"] / 1.5), 4),
                    "source": {"file": "events/vocal_phrases.json", "id": vp["id"]},
                }
            )
    items.append(
        {
            "t": S.BAR[27].t,
            "d": round(S.DURATION - S.BAR[27].t, 6),
            "kind": "chord",
            "strength": 0.9,
            "source": {"file": "events/bars.json", "id": "bar:27"},
        }
    )
    items.append(
        {
            "t": decay["t"],
            "d": decay["d"],
            "kind": "decay",
            "strength": decay["strength"],
            "source": {"file": "events/decay_tails.json", "id": decay["id"]},
        }
    )
    items.append(
        {
            "t": silence["t"],
            "d": silence["d"],
            "kind": "silence",
            "strength": 1.0,
            "source": {"file": "events/silences.json", "id": silence["id"]},
        }
    )
    items.sort(key=lambda h: (h["t"], h["kind"]))
    for i, h in enumerate(items, start=1):
        h["id"] = f"O{i:03d}"
    return [{"id": h["id"], **{k: v for k, v in h.items() if k != "id"}} for h in items]


def cues(hps: list[dict], impacts: list[dict], stop: dict, silence: dict) -> list[dict]:
    raw: list[dict] = []
    for s in S.SECTIONS:
        raw.append(
            {
                "t": s.t,
                "kind": "section",
                "tier": 1,
                "strength": 1.0 if s.id == "S05" else 0.9,
                "lead_in_s": 2.0,
                "source": {"file": "events/sections.json", "id": s.id},
            }
        )
    for rid, role, sb, nb, sid in S.EDM_ROLES:
        t = S.BAR[sb].t
        if role == "build":
            raw.append(
                {
                    "t": t,
                    "kind": "build_start",
                    "tier": 1,
                    "strength": 0.8,
                    "lead_in_s": 2.0,
                    "source": {"file": "events/edm_roles.json", "id": rid},
                }
            )
        elif role == "drop":
            build_t = S.BAR[next(r[2] for r in S.EDM_ROLES if r[1] == "build")].t
            raw.append(
                {
                    "t": t,
                    "kind": "drop",
                    "tier": 1,
                    "strength": 1.0,
                    "lead_in_s": round(t - build_t, 6),
                    "source": {"file": "events/edm_roles.json", "id": rid},
                }
            )
    for p in S.PHRASES:
        raw.append(
            {
                "t": S.BAR[p.start_bar].t,
                "kind": "phrase",
                "tier": 2,
                "strength": 0.6,
                "lead_in_s": None,
                "source": {"file": "events/phrases.json", "id": p.id},
            }
        )
    for i in impacts:
        raw.append(
            {
                "t": i["t"],
                "kind": "impact",
                "tier": 2,
                "strength": i["strength"],
                "lead_in_s": None,
                "source": {"file": "events/impacts.json", "id": i["id"]},
            }
        )
    raw.append(
        {
            "t": stop["t"],
            "kind": "stop",
            "tier": 2,
            "strength": stop["strength"],
            "lead_in_s": None,
            "source": {"file": "events/stops.json", "id": stop["id"]},
        }
    )
    raw.append(
        {
            "t": silence["t"],
            "kind": "silence",
            "tier": 2,
            "strength": 0.8,
            "lead_in_s": None,
            "source": {"file": "events/silences.json", "id": silence["id"]},
        }
    )
    for h in hps:
        raw.append(
            {
                "t": h["t"],
                "kind": "hit_point",
                "tier": 3,
                "strength": h["strength"],
                "lead_in_s": None,
                "source": {"file": "events/hit_points.json", "id": h["id"]},
            }
        )
    for b in S.BARS:
        if b.pickup:
            continue
        raw.append(
            {
                "t": b.t,
                "kind": "downbeat",
                "tier": 3,
                "strength": 0.5 if b.in_pulse else 0.2,
                "lead_in_s": None,
                "source": {"file": "events/bars.json", "id": f"bar:{b.bar}"},
            }
        )
    for b in S.BEATS:
        raw.append(
            {
                "t": b.t,
                "kind": "beat",
                "tier": 4,
                "strength": None,
                "lead_in_s": None,
                "source": {"file": "events/beats.json", "id": f"beat:{b.beat_index}"},
            }
        )
    return cv.merge_cues(raw)  # D37: one cue per time (kinds[] / sources[] keep every merged candidate)
