# ruff: noqa: E501  (long catalogue tables / docstrings)
"""choreo stage (contract v1, owner M2): the counts a choreographer and a dancing character move to.

* **Eight-counts** (D13): counts restart at every phrase start (phrases restart at every section start), count 1 is
  the phrase's first downbeat; a phrase is cut into 8-beat counts (6 when the phrase is in 3/4) and a remainder
  becomes a shorter count flagged ``partial``. ``E000`` is the synthesised 5-6-7-8 lead-in: the 4 beats before
  ``E001`` (``start_beat`` may be negative; times extrapolated with the first beat interval). Pickup beats before the
  lead-in carry no count. Repeated sections get the same count structure because the phrases repeat.
* **Accents** per beat (0..1): max(kick vel, 0.9 snare vel, crash vel, 0.7 tom vel) of drum hits within +-30 ms,
  +0.15 for a lead-vocal note onset within +-60 ms, +0.10 on a phrase start; 0 outside pulse regions. The
  ``choreo.accent`` curve flashes each beat's accent (flash rule) with a 120 ms release.
* **Sub-counts** (D14) are derived by the helpers (``count(t).sub``: 1 e & a); nothing extra is stored.
* **Grooves**: per bar a 16-step matrix (kick, snare, hat, perc = toms/cymbals/perc) from the drum hits, the
  swing ratio of the off-beat 8ths, a syncopation index (weights 5/4/3/2/1, Longuet-Higgins style, as in the
  synthetic truth) and a groove id (bars clustered by pattern similarity, G01.. in order of first use).
* **Hit points**: beats where >= 3 kinds coincide (drum, cymbal, impact, vocal_onset, chord change on a downbeat,
  section start, drop) plus every stop; strength = 0.3 accent + 0.1 n_kinds + 0.1 impact strength (stop 0.85);
  ranked by strength, at most ``max(24, 0.35 bars)`` kept (with no drums stage, strong accents and onsets count as kinds).
* **Holds**: lead-vocal notes >= 0.7 s (vocal_note), held chords over sparse drums (chord), decay tails (decay),
  silences (silence).
* **Movement density** ``choreo.movement``: smoothed hit/onset density x intensity, 0 in silence.
* **tables/{beats,bars,sections}.csv** (D2) joined with sections, phrases, counts and grooves.

When the drums stage has no output (real-song fixtures, or a failed separation) the stage falls back to its own
percussive (HPSS) onset classifier on the mix (kick 30-150 Hz, snare 150-2500 Hz, hat > 5 kHz) and flags it.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from mvh.contract.ids import make_id, ref_key
from mvh.runner.spec import StageError, StageResult, StageSpec, catalog_outputs

STAGE = StageSpec(
    "choreo",
    ('rhythm', 'structure', 'drums', 'spectral', 'vocals', 'harmony', 'dynamics'),
    "main",
    "1.0.0",
    override_keys=(),
    outputs=catalog_outputs("choreo"),
    params={'hit_window_s': 0.03, 'vocal_window_s': 0.06, 'min_hold_vocal_s': 0.7, 'hit_point_min_kinds': 3,
            'groove_similarity': 0.85, 'accent_release_s': 0.12},
    module="M2",
    description='Eight-counts per phrase/section with accents, grooves, hit points, holds, movement density; tables/*.csv.',
)

FPS = 100
ROWS = ("kick", "snare", "hat", "perc")
ROW_OF = {"kick": "kick", "snare": "snare", "hat": "hat", "tom": "perc", "cymbal": "perc", "perc": "perc"}
SYNC_W = [5, 1, 2, 1, 3, 1, 2, 1, 4, 1, 2, 1, 3, 1, 2, 1]


def _opt(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001 - optional upstream evidence
        return default


def syncopation(pattern: dict[str, list[float]], n_steps: int = 16) -> float:
    """S = sum over kick/snare onsets s with no onset at s+1 of max(0, w[s+1] - w[s]); min(1, S / 12)."""
    on = [max(pattern["kick"][k], pattern["snare"][k]) > 0 for k in range(n_steps)]
    s = 0.0
    for k in range(n_steps - 1):
        if on[k] and not on[k + 1]:
            s += max(0, SYNC_W[k + 1] - SYNC_W[k])
    return float(min(1.0, s / 12.0))


def own_drum_hits(mono: np.ndarray, sr: int) -> list[dict[str, Any]]:
    """Fallback drum classifier: percussive (HPSS) band onsets of the mix (kick / snare / hat)."""
    import librosa

    y = np.asarray(mono, np.float32)
    if sr != 44100:
        import soxr
        y = soxr.resample(y, sr, 44100).astype(np.float32)
        sr = 44100
    M = np.abs(librosa.stft(y, n_fft=2048, hop_length=441, center=True))
    _, P = librosa.decompose.hpss(M, kernel_size=31)
    f = librosa.fft_frequencies(sr=sr, n_fft=2048)
    out = []
    for drum, lo, hi in (("kick", 30, 150), ("snare", 150, 2500), ("hat", 5000, 16000)):
        band = (P[(f >= lo) & (f < hi)] ** 2).sum(axis=0)
        db = 10 * np.log10(np.maximum(band, 1e-12))
        rise = db - np.minimum.reduce([np.r_[np.full(j, db[0]), db[:-j]] for j in (1, 2, 3)])
        thr = max(6.0, np.percentile(rise, 90))
        ref = np.percentile(db, 99)
        last = -100
        for i in range(1, len(rise) - 1):
            if rise[i] >= thr and rise[i] >= rise[i - 1] and rise[i] > rise[i + 1] and i - last >= 5:
                lvl = float(np.max(db[i:i + 3]))
                vel = float(np.clip(1.0 + (lvl - ref) / 30.0, 0.05, 1.0))
                out.append({"t": i / 100.0, "drum": drum, "vel": round(vel, 3)})
                last = i
    out.sort(key=lambda h: h["t"])
    return out


def _smooth_same(x: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """np.convolve(..., 'same') whose output is always len(x) (also for a signal shorter than the kernel)."""
    x = np.asarray(x, float)
    s0 = (len(kernel) - 1) // 2
    return np.convolve(x, kernel, mode="full")[s0:s0 + len(x)]


def run(ctx) -> StageResult:  # noqa: C901
    p = ctx.params
    warnings: list[str] = []
    fallbacks: list[str] = []
    notes: list[str] = []
    beats = list(ctx.events("beats").items)
    bars = list(ctx.events("bars").items)
    if not beats:
        raise StageError("rhythm produced no beats")
    sections = list(ctx.events("sections").items)
    phrases = list(ctx.events("phrases").items)
    edm = _opt(lambda: list(ctx.events("edm_roles").items), []) or []
    tempo = _opt(lambda: ctx.upstream("rhythm").json("meta/tempo.json"), {}) or {}
    mix = ctx.audio("mix", mono=True)
    x = np.asarray(mix.samples, np.float32).reshape(-1)
    sr = int(mix.sr)
    duration = x.size / sr
    n = -(-x.size * 100 // sr)
    bt = np.array([b["t"] for b in beats], float)
    nb = len(bt)
    ip = np.array([bool(b["in_pulse"]) for b in beats])
    ibi = np.diff(bt) if nb > 1 else np.array([0.5])
    ibi_after = np.r_[ibi, ibi[-1] if len(ibi) else 0.5]

    # ------------------------------------------------------------------ evidence
    hits = _opt(lambda: [{"t": float(h["t"]), "drum": h["drum"], "vel": float(h["vel"])} for h in ctx.events("drum_hits").items])
    if not hits:
        hits = own_drum_hits(x, sr)
        fallbacks.append("drums:own_hpss")
        notes.append("drum hits: own HPSS band classifier on the mix (drums stage output unavailable)")
    hits.sort(key=lambda h: h["t"])
    # cymbals: a cymbal that repeats on the grid (>= 3 within +-2 beats) is a ride (time-keeping, hat row); an isolated
    # one is a crash (accent, perc row, the 'cymbal' hit-point kind). drum_hits only says 'cymbal' (contract enum).
    med_ibi = float(np.median(np.diff([b["t"] for b in beats]))) if len(beats) > 1 else 0.5
    cym_t = np.array([h["t"] for h in hits if h["drum"] == "cymbal"], float)
    for h in hits:
        if h["drum"] == "cymbal":
            k = int(np.sum(np.abs(cym_t - h["t"]) <= 2.05 * med_ibi))
            h["cym"] = "ride" if k >= 3 else "crash"
    ht = np.array([h["t"] for h in hits], float)
    vnotes = _opt(lambda: list(ctx.events("notes.vocals").items), None)
    if vnotes is None:
        fallbacks.append("vocals:unavailable")
        vnotes = []
    vphr = _opt(lambda: list(ctx.events("vocal_phrases").items), []) or []
    chords = _opt(lambda: list(ctx.events("chords").items), None)
    if chords is None:
        fallbacks.append("chords:unavailable")
        chords = []
    impacts = _opt(lambda: list(ctx.events("impacts").items), None)
    stops = _opt(lambda: list(ctx.events("stops").items), None)
    silences = _opt(lambda: list(ctx.events("silences").items), None)
    tails = _opt(lambda: list(ctx.events("decay_tails").items), None)
    dyn = _opt(lambda: list(ctx.events("dynamics").items), None)
    if dyn is None:
        fallbacks.append("dynamics:unavailable")
        notes.append("dynamics unavailable: no impacts/stops/silences/decay tails; sections.csv level null")
    impacts, stops, silences, tails, dyn = impacts or [], stops or [], silences or [], tails or [], dyn or []
    von = np.array(sorted(float(v["t"]) for v in vnotes), float)

    # ------------------------------------------------------------------ section / phrase membership of beats
    def member(items, t):
        for it in items:
            if it["t"] - 1e-4 <= t < it["t"] + it["d"] - 1e-4:
                return it
        return None

    sec_of = [member(sections, t) for t in bt]
    phr_of = [member(phrases, t) for t in bt]
    phrase_start = set()
    for ph in phrases:
        k = int(np.argmin(np.abs(bt - ph["t"])))
        if abs(bt[k] - ph["t"]) < 0.02:
            phrase_start.add(k)

    # ------------------------------------------------------------------ accents
    hw = float(p.get("hit_window_s", 0.03))
    vw = float(p.get("vocal_window_s", 0.06))
    W = {"kick": 1.0, "snare": 0.9, "cymbal": 1.0, "tom": 0.7, "hat": 0.0, "perc": 0.6, "ride": 0.0}
    accent = np.zeros(nb)
    near_hits: list[list[dict[str, Any]]] = []
    for i, t in enumerate(bt):
        lo, hi = np.searchsorted(ht, [t - hw, t + hw])
        hs = hits[lo:hi]
        near_hits.append(hs)
        a = max([W.get("ride" if h.get("cym") == "ride" else h["drum"], 0.5) * h["vel"] for h in hs], default=0.0)
        if len(von):
            j = np.searchsorted(von, t)
            if any(0 <= q < len(von) and abs(von[q] - t) <= vw for q in (j - 1, j)):
                a += 0.15
        if i in phrase_start:
            a += 0.10
        accent[i] = float(np.clip(a, 0, 1)) if ip[i] else 0.0

    # ------------------------------------------------------------------ eight-counts
    counts: list[dict[str, Any]] = []
    eight_of = [None] * nb
    count_of = [None] * nb
    first_count_beat = None
    for ph in phrases:
        idx = [i for i in range(nb) if phr_of[i] is ph]
        if not idx:
            continue
        bib = [beats[i]["beats_in_bar"] for i in idx]
        size = 6 if (max(set(bib), key=bib.count) == 3) else 8
        for c0 in range(0, len(idx), size):
            chunk = idx[c0:c0 + size]
            k0, k1 = chunk[0], chunk[-1]
            t0 = bt[k0]
            t1 = bt[k1 + 1] if k1 + 1 < nb else min(duration, bt[k1] + ibi_after[k1])
            if t1 <= t0:
                t1 = t0 + 1e-3
            eid = make_id("eight", len(counts) + 1)
            counts.append({"id": eid, "t": t0, "d": t1 - t0, "start_beat": int(k0), "len": len(chunk), "first_count": 1,
                           "phrase_id": ph["id"], "section_id": ph.get("section_id"), "partial": len(chunk) < size,
                           "lead_in": False, "in_pulse": bool(np.mean(ip[chunk]) >= 0.5),
                           "accents": [round(float(accent[i]), 4) for i in chunk]})
            for c, i in enumerate(chunk):
                eight_of[i] = eid
                count_of[i] = c + 1
            if first_count_beat is None:
                first_count_beat = k0
    lead = None
    if first_count_beat is not None:
        size0 = 6 if counts and counts[0]["len"] == 6 and not counts[0]["partial"] else 8
        L = 3 if size0 == 6 else 4
        sb = first_count_beat - L
        i0 = 1.0 / max(1e-6, (bt[1] - bt[0])) if nb > 1 else 2.0
        step = 1.0 / i0
        tt = [bt[k] if 0 <= k < nb else bt[0] + (k * step if k < 0 else 0) for k in range(sb, first_count_beat)]
        acc = [round(float(accent[k]), 4) if 0 <= k < nb else 0.0 for k in range(sb, first_count_beat)]
        lead = {"id": "E000", "t": float(tt[0]), "d": float(bt[first_count_beat] - tt[0]), "start_beat": int(sb), "len": L,
                "first_count": 8 - L + 1 if L == 4 else 4, "phrase_id": None, "section_id": None, "partial": False, "lead_in": True,
                "in_pulse": bool(all(0 <= k < nb and ip[k] for k in range(sb, first_count_beat))), "accents": acc}
        for c, k in enumerate(range(sb, first_count_beat)):
            if 0 <= k < nb and eight_of[k] is None:
                eight_of[k] = "E000"
                count_of[k] = lead["first_count"] + c
    count_items = ([lead] if lead else []) + counts
    for c in count_items:
        c["t"] = round(float(c["t"]), 6)
        c["d"] = round(float(c["d"]), 6)

    # ------------------------------------------------------------------ grooves (per bar)
    bar_items = [b for b in bars if b["bar"] >= 1]
    groove_rows = []
    for b in bar_items:
        k0 = int(b["first_beat"])
        nbeats = int(b["n_beats"])
        if nbeats <= 0:
            continue
        pat = {r: [0.0] * 16 for r in ROWS}
        offs = []
        t_end = b["t"] + b["d"]
        lo, hi = np.searchsorted(ht, [b["t"] - 0.03, t_end - 0.03])
        n_hit = 0
        for h in hits[lo:hi]:
            k = int(np.searchsorted(bt, h["t"] + 0.03) - 1)
            k = min(max(k, k0), k0 + nbeats - 1)
            d_ = bt[k + 1] - bt[k] if k + 1 < nb else ibi_after[k]
            frac = (h["t"] - bt[k]) / max(1e-6, d_)
            step = (k - k0) * 4 + int(round(frac * 4))
            if 0.42 <= frac <= 0.72:
                offs.append((k, frac))
            if 0 <= step < min(16, nbeats * 4):
                row = "hat" if h.get("cym") == "ride" else ROW_OF.get(h["drum"], "perc")
                pat[row][step] = max(pat[row][step], round(h["vel"], 3))
                n_hit += 1
        if n_hit == 0:
            continue
        sw = 1.0
        # per beat: the off-beat hit nearest to the '&' (0.42..0.72 of the beat); straight 16ths keep 0.5
        per_beat: dict[int, float] = {}
        for k, fr in offs:
            if k not in per_beat or abs(fr - 0.5) < abs(per_beat[k] - 0.5):
                per_beat[k] = fr
        if len(per_beat) >= 2:
            f = float(np.median(list(per_beat.values())))
            sw = round(float(np.clip(f / max(1e-3, 1 - f), 0.5, 3.0)), 3)
            if abs(sw - 1.0) < 0.06:
                sw = 1.0
        groove_rows.append({"bar": b["bar"], "t": b["t"], "d": b["d"], "pattern": pat, "swing": sw,
                            "syncopation": round(syncopation(pat, min(16, nbeats * 4)), 4)})
    # cluster bars by pattern. Clean hits (drums stage): cosine on velocity patterns + binary Jaccard against the
    # cluster's first bar. Own-classifier hits (noisy): kick/snare-weighted cosine of +-1-step blurred patterns
    # against the running cluster mean, so jitter and missed hats do not create one groove per bar.
    noisy = "drums:own_hpss" in fallbacks
    sim_thr = float(p.get("groove_similarity_noisy", 0.72) if noisy else p.get("groove_similarity", 0.85))
    rw = {"kick": 1.0, "snare": 1.0, "hat": 0.5, "perc": 0.4}

    def blur(v16):
        v16 = np.asarray(v16, float)
        return v16 + 0.5 * np.r_[v16[1:], 0.0] + 0.5 * np.r_[0.0, v16[:-1]]

    protos: list[dict[str, Any]] = []
    for g in groove_rows:
        v = np.concatenate([np.asarray(g["pattern"][r]) for r in ROWS])
        vb = v > 0
        vbl = np.concatenate([rw[r] * blur(g["pattern"][r]) for r in ROWS])
        best, bs = None, sim_thr
        for pr in protos:
            if noisy:
                u = pr["blur_sum"] / len(pr["members"])
                s = float(vbl @ u / (np.linalg.norm(vbl) * np.linalg.norm(u) + 1e-12))
            else:
                u = pr["vec"]
                cos = float(v @ u / (np.linalg.norm(v) * np.linalg.norm(u) + 1e-12))
                jac = float((vb & pr["bin"]).sum() / max(1, (vb | pr["bin"]).sum()))
                s = 0.5 * cos + 0.5 * jac
            if s >= bs:
                best, bs = pr, s
        if best is None:
            best = {"id": make_id("groove", len(protos) + 1), "vec": v.copy(), "bin": vb.copy(), "members": [],
                    "blur_sum": np.zeros_like(vbl)}
            protos.append(best)
        best["members"].append(g)
        best["blur_sum"] = best["blur_sum"] + vbl
        g["groove_id"] = best["id"]
    groove_meta = []
    for pr in protos:
        mem = pr["members"]
        proto = {r: [round(float(np.mean([m["pattern"][r][k] for m in mem])), 3) for k in range(16)] for r in ROWS}
        groove_meta.append({"id": pr["id"], "n_bars": len(mem), "bars": [int(m["bar"]) for m in mem],
                            "swing": round(float(np.median([m["swing"] for m in mem])), 3),
                            "syncopation": round(float(np.median([m["syncopation"] for m in mem])), 4), "prototype": proto})
    groove_items = [{"t": round(g["t"], 6), "d": round(g["d"], 6), "bar": int(g["bar"]), "groove_id": g["groove_id"], "swing": g["swing"],
                     "syncopation": g["syncopation"], "pattern": g["pattern"]} for g in groove_rows]
    groove_of_bar = {g["bar"]: g for g in groove_rows}

    # ------------------------------------------------------------------ hit points
    sec_start = {}
    for s in sections:
        k = int(np.argmin(np.abs(bt - s["t"])))
        if abs(bt[k] - s["t"]) < 0.03:
            sec_start[k] = s
    drop_start = {}
    for e in edm:
        if e.get("role") == "drop":
            k = int(np.argmin(np.abs(bt - e["t"])))
            if abs(bt[k] - e["t"]) < 0.03:
                drop_start[k] = e
    chord_t = np.array([c["t"] for c in chords if c.get("label") not in (None, "N")], float)
    down = {i for i, b in enumerate(beats) if b["beat_in_bar"] == 1}
    ip_acc = accent[ip & (accent > 0)]
    acc_hi = max(0.6, float(np.percentile(ip_acc, 90))) if len(ip_acc) >= 10 else None
    on_t = []
    for nm in ("onsets.bass", "onsets.mid", "onsets.high"):
        on_t += [float(o["t"]) for o in (_opt(lambda nm=nm: list(ctx.events(nm).items), []) or []) if float(o.get("strength", 0)) >= 0.6]
    on_t = np.array(sorted(on_t), float)
    cand = []
    for i, t in enumerate(bt):
        if not ip[i]:
            continue
        kinds, srcs = [], [{"file": "events/beats.json", "id": ref_key("beat", i)}]
        hs = near_hits[i]
        if any(h["drum"] in ("kick", "snare") and h["vel"] >= 0.5 for h in hs):
            kinds.append("drum")
        if any(h["drum"] == "cymbal" and h.get("cym") != "ride" for h in hs):
            kinds.append("cymbal")
        imp = [it for it in impacts if abs(it["t"] - t) <= 0.06]
        if imp:
            kinds.append("impact")
            srcs.append({"file": "events/impacts.json", "id": imp[0]["id"]})
        if len(von):
            j = np.searchsorted(von, t)
            if any(0 <= q < len(von) and abs(von[q] - t) <= vw for q in (j - 1, j)):
                kinds.append("vocal_onset")
        if noisy and acc_hi is not None and accent[i] >= acc_hi:     # thin evidence (no drums stage): strong accents count
            kinds.append("accent")
        if noisy and len(on_t) and np.min(np.abs(on_t - t)) <= 0.04:
            kinds.append("onset")
        if i in down and len(chord_t) and np.min(np.abs(chord_t - t)) <= 0.06:
            kinds.append("chord")
        if i in sec_start:
            kinds.append("section")
            srcs.append({"file": "events/sections.json", "id": sec_start[i]["id"]})
        if i in drop_start:
            kinds.append("drop")
            srcs.append({"file": "events/edm_roles.json", "id": drop_start[i]["id"]})
        if len(kinds) >= int(p.get("hit_point_min_kinds", 3)):
            st = 0.3 * accent[i] + 0.1 * len(kinds) + 0.1 * max([float(it.get("strength", 0)) for it in imp], default=0.0)
            cand.append({"t": float(t), "strength": float(np.clip(st, 0, 1)), "kinds": kinds, "sources": srcs})
    for s in stops:
        cand.append({"t": float(s["t"]), "strength": 0.85, "kinds": ["stop"], "sources": [{"file": "events/stops.json", "id": s["id"]}]})
    cap = max(24, int(0.35 * len(bar_items)))
    cand.sort(key=lambda c: (-c["strength"], c["t"]))
    cand = cand[:cap]
    for r, c in enumerate(cand, start=1):
        c["rank"] = r
    cand.sort(key=lambda c: c["t"])
    hit_points = [{"id": make_id("hit_point", k + 1), "t": round(c["t"], 6), "strength": round(c["strength"], 4), "rank": c["rank"],
                   "kinds": c["kinds"], "sources": c["sources"]} for k, c in enumerate(cand)]

    # ------------------------------------------------------------------ holds
    holds_raw = []
    min_v = float(p.get("min_hold_vocal_s", 0.7))
    for v in vnotes:
        if float(v["d"]) >= min_v:
            vp = next((q for q in vphr if q["t"] - 1e-3 <= v["t"] < q["t"] + q["d"]), None)
            src = {"file": "events/vocal_phrases.json", "id": vp["id"]} if vp else {"file": "events/beats.json", "id": ref_key("beat", int(np.argmin(np.abs(bt - v["t"]))))}
            holds_raw.append({"t": float(v["t"]), "d": float(v["d"]), "kind": "vocal_note", "strength": min(1.0, float(v["d"]) / 1.5), "source": src})
    for c in chords:
        if c.get("label") in (None, "N") or float(c["d"]) < 2.0:
            continue
        t0, t1 = float(c["t"]), float(c["t"]) + float(c["d"])
        lo, hi = np.searchsorted(ht, [t0 + 0.1, t1])
        span_beats = max(1.0, (t1 - t0) / float(np.median(ibi) if len(ibi) else 0.5))
        if (hi - lo) / span_beats <= 0.25:
            bi = [b for b in bars if b["t"] - 0.05 <= t0 < b["t"] + b["d"]]
            src = {"file": "events/bars.json", "id": ref_key("bar", int(bi[0]["bar"]))} if bi else {"file": "events/beats.json", "id": ref_key("beat", int(np.argmin(np.abs(bt - t0))))}
            holds_raw.append({"t": t0, "d": t1 - t0, "kind": "chord", "strength": float(np.clip(0.5 + 0.1 * (t1 - t0), 0, 0.9)), "source": src})
    for y in tails:
        holds_raw.append({"t": float(y["t"]), "d": float(y["d"]), "kind": "decay", "strength": float(y.get("strength", 0.6)),
                          "source": {"file": "events/decay_tails.json", "id": y["id"]}})
    for z in silences:
        holds_raw.append({"t": float(z["t"]), "d": float(z["d"]), "kind": "silence", "strength": 1.0,
                          "source": {"file": "events/silences.json", "id": z["id"]}})
    holds_raw = [h for h in holds_raw if h["d"] > 0]
    holds_raw.sort(key=lambda h: (h["t"], h["kind"]))
    holds = [{"id": make_id("hold", k + 1), "t": round(h["t"], 6), "d": round(h["d"], 6), "kind": h["kind"],
              "strength": round(float(np.clip(h["strength"], 0, 1)), 4), "source": h["source"]} for k, h in enumerate(holds_raw)]

    # ------------------------------------------------------------------ curves
    from mvh.contract.conventions import flash_samples

    acc_curve = np.zeros(n, np.float32)
    rel = float(p.get("accent_release_s", 0.12))
    tail = np.exp(-np.arange(0, int(4 * rel * FPS) + 1) / (rel * FPS))
    for i, t in enumerate(bt):
        a = float(accent[i])
        if a <= 0:
            continue
        f0, f1 = flash_samples(float(t))
        for f in (f0, f1):
            if 0 <= f < n:
                acc_curve[f] = max(acc_curve[f], a)
        seg = a * tail[1:]
        s0 = f1 + 1
        e0 = min(n, s0 + len(seg))
        if s0 < n:
            acc_curve[s0:e0] = np.maximum(acc_curve[s0:e0], seg[: e0 - s0])
    dens = np.zeros(n)
    for h in hits:
        k = int(round(h["t"] * FPS))
        if 0 <= k < n:
            dens[k] += h["vel"]
    for t in von:
        k = int(round(t * FPS))
        if 0 <= k < n:
            dens[k] += 0.5
    win = np.hanning(2 * FPS + 1)
    win /= win.sum()
    dens = _smooth_same(dens, win) * FPS          # weighted events per second
    inten = _opt(lambda: np.asarray(ctx.curve("dyn.intensity").values, float)[:n])
    if inten is None or len(inten) < n:
        rmsd = _smooth_same(np.asarray(x, np.float64) ** 2, np.ones(441) / 441)[:: max(1, sr // FPS)][:n]
        lev = 10 * np.log10(np.maximum(rmsd, 1e-12))
        lev = np.r_[lev, np.full(max(0, n - len(lev)), lev[-1] if len(lev) else -120)]
        inten = np.clip((lev - (np.percentile(lev, 98) - 30)) / 30, 0, 1)
        fallbacks.append("intensity:own_rms")
    dn = dens / max(1e-9, np.percentile(dens, 98))
    mv = np.clip(0.7 * np.clip(dn, 0, 1.2) + 0.3 * inten, 0, 1)
    ipc = _opt(lambda: np.asarray(ctx.curve("rhythm.in_pulse").values, float)[:n])
    if ipc is not None and len(ipc) == n:
        mv = mv * (0.35 + 0.65 * ipc)
    mv = _smooth_same(mv, np.ones(25) / 25)
    w = ctx.writer
    w.curves("core", {"choreo.movement": np.clip(mv, 0, 1).astype(np.float32), "choreo.accent": np.clip(acc_curve, 0, 1)})

    # ------------------------------------------------------------------ events + tables
    w.events("counts", count_items)
    w.events("grooves", groove_items)
    w.events("hit_points", hit_points)
    w.events("holds", holds)
    w.json("meta/grooves.json", {"grooves": groove_meta, "source": "drum_hits" if "drums:own_hpss" not in fallbacks else "own_hpss",
                                 "dominant": max(groove_meta, key=lambda g: g["n_bars"])["id"] if groove_meta else None})
    beat_rows = []
    for i, b in enumerate(beats):
        s, ph = sec_of[i], phr_of[i]
        beat_rows.append({"beat_index": b["beat_index"], "t": b["t"], "bar": b["bar"], "beat_in_bar": b["beat_in_bar"],
                          "beats_in_bar": b["beats_in_bar"], "in_pulse": b["in_pulse"], "strength": b["strength"],
                          "section_id": s["id"] if s else None, "phrase_id": ph["id"] if ph else None,
                          "eight_id": eight_of[i], "count": count_of[i], "accent": round(float(accent[i]), 4)})
    w.table("tables/beats.csv", beat_rows, ["beat_index", "t", "bar", "beat_in_bar", "beats_in_bar", "in_pulse", "strength",
                                            "section_id", "phrase_id", "eight_id", "count", "accent"])
    bar_rows = []
    for b in bars:
        s = member(sections, b["t"] + 1e-3) if b["bar"] >= 1 else None
        ph = member(phrases, b["t"] + 1e-3) if b["bar"] >= 1 else None
        g = groove_of_bar.get(b["bar"])
        bar_rows.append({"bar": b["bar"], "t": b["t"], "d": b["d"], "beats_in_bar": b["beats_in_bar"], "n_beats": b["n_beats"],
                         "pickup": b["pickup"], "in_pulse": b["in_pulse"], "section_id": s["id"] if s else None,
                         "phrase_id": ph["id"] if ph else None, "groove_id": g["groove_id"] if g else None,
                         "swing": g["swing"] if g else None, "syncopation": g["syncopation"] if g else None})
    w.table("tables/bars.csv", bar_rows, ["bar", "t", "d", "beats_in_bar", "n_beats", "pickup", "in_pulse", "section_id", "phrase_id",
                                          "groove_id", "swing", "syncopation"])
    sec_rows = []
    for s in sections:
        role = next((e["role"] for e in edm if e["section_id"] == s["id"]), None)
        ov = [(min(s["t"] + s["d"], d_["t"] + d_["d"]) - max(s["t"], d_["t"]), d_) for d_ in dyn]
        ov = [o for o in ov if o[0] > 0]
        lvl = max(ov, key=lambda o: o[0])[1] if ov else None
        mean_l = None
        if ov:
            tot = sum(o[0] for o in ov)
            mean_l = round(sum(o[0] * float(o[1]["mean_lufs"]) for o in ov) / tot, 2)
        sec_rows.append({"id": s["id"], "t": s["t"], "d": s["d"], "label": s["label"], "occurrence": s["occurrence"],
                         "repeat_group": s["repeat_group"], "start_bar": s["start_bar"], "n_bars": s["n_bars"], "edm_role": role,
                         "level": lvl["level"] if lvl else None, "mean_lufs": mean_l})
    w.table("tables/sections.csv", sec_rows, ["id", "t", "d", "label", "occurrence", "repeat_group", "start_bar", "n_bars", "edm_role",
                                              "level", "mean_lufs"])
    per_section = {}
    for c in counts:
        k = c["section_id"] or "-"
        d = per_section.setdefault(k, {"n": 0, "partial": 0})
        d["n"] += 1
        d["partial"] += int(c["partial"])
    summary = {"n_counts": len(count_items), "n_partial": sum(1 for c in counts if c["partial"]), "n_grooves": len(groove_meta),
               "dominant_groove": groove_meta and max(groove_meta, key=lambda g: g["n_bars"])["id"] or None,
               "n_hit_points": len(hit_points), "n_holds": len(holds), "bpm": tempo.get("bpm"),
               "mean_swing": round(float(np.mean([g["swing"] for g in groove_rows])), 3) if groove_rows else None}
    status = "degraded" if "drums:own_hpss" in fallbacks else "ok"
    return StageResult(status=status, summary=summary, warnings=warnings, fallbacks=sorted(set(fallbacks)),
                       provenance={"notes": notes})
