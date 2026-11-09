"""rhythm stage (contract v1, owner M2): the beat grid every choreography agent dances to.

Pipeline (PLAN §5 rhythm, amended by SPIKE "Rhythm"):

1. Trackers on the canonical mix: beat_this final0 logits (50 fps), madmom-infer RNN downbeat activations + DBN,
   the allin1 beats/downbeats/activations (upstream), and DSP features (mel onset flux, kick and snare band flux,
   RMS level, tempogram, PLP).
2. **Tempo arbitration** over the tracker estimates, the tempogram peaks and their x2 / x0.5 relatives:
   consensus + drum metrical evidence (kick/snare contrast x coverage) + tempogram salience + a resonance prior.
   Every candidate is kept in ``meta/tempo.json`` (``candidates`` + additive ``arbitration``) so the user can override
   ``rhythm.bpm``. MEGAFAUNA (~105 / 143.6 / 193-200) is the regression case.
3. Beat tracking: a beat-only HMM (madmom-infer state space) on the fused activation (mean of the tracker
   probabilities), tempo restricted to +-20 % of the arbitrated tempo; parabolic sub-frame peak; snap to a
   transient within +-25 ms (``snap_window_s``).
4. Pulse regions; the virtual grid through no-pulse gaps and to the song end (D11); pickups recovered backwards.
5. **Downbeats by a 2-of-3 vote** (beat_this, allin1, madmom DBN re-decoded at our tempo) plus their activations,
   decoded with a meter HMM over beats (3/4 and 4/4, meter changes and early-ending bars penalised). Bars, pickup
   bar 0 (D12), meter and meter changes.
6. Piecewise tempo segments with a per-segment feel (normal / half_time / double_time from the trackers' local
   tempo), QA (tracker agreement F, downbeat phase report, flags) and the curves.

Overrides (applied after tracking, before fusion): ``rhythm.bpm`` forces the tempo level; ``rhythm.beat_offset_s``
shifts the grid; ``rhythm.downbeat_phase`` rotates the bar numbering by n beats.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from mvh.runner.spec import StageError, StageResult, StageSpec, catalog_outputs

from . import fusion as fu

STAGE = StageSpec(
    "rhythm",
    ('ingest', 'allin1', 'spectral'),
    "main",
    "1.2.0",
    override_keys=('rhythm.beat_offset_s', 'rhythm.bpm', 'rhythm.downbeat_phase'),
    outputs=catalog_outputs("rhythm"),
    params={'snap_window_s': 0.025, 'tempo_ratios': [1, 2, 0.5, 1.5, 0.6667, 1.3333, 0.75],
            'use_models': True, 'tempo_tolerance': 0.2, 'snap_min_rise_db': 15.0, 'snap_mode': 'nearest', 'meters': [3, 4],
            'meter_switch_cost': 1.25, 'bar_break_cost': 4.0, 'beat_tol_s': 0.07,
            'backbeat_half_enter': 1.5, 'backbeat_half_leave': 1.3,
            # W4V-GAIN-BEATS (W4-AN-9): the trackers and DSP features read the mix scaled to this integrated loudness
            # (one pure gain; null = the master level), so the grid does not depend on the master level
            'analysis_lufs': -10.0,
            # W4V-GAIN-BEATS: tie-break for irregular bars where the evidence is flat (fusion.decode_meter late_bias)
            'meter_late_bias': 0.25,
            # W4 verifier N4: a half-time run also needs a beat-3 body in the 150-4000 Hz flux (fusion.backbeat_feel)
            'backbeat_mid_min': 1.25},
    models=("beat_this", "madmom_downbeats_blstm"),
    module="M2",
    description='Fuse beat_this, allin1 and tempogram/ACF: tempo arbitration, sub-frame beats, tempo grid, meter, pickups, pulse regions, QA.',
)

TRACKERS = ("beat_this", "allin1", "madmom")


def _try(fn, fallbacks: list[str], warnings: list[str], tag: str):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 - a missing tracker degrades the fusion, it does not fail the stage
        fallbacks.append(f"{tag}:unavailable")
        warnings.append(f"{tag} unavailable ({type(e).__name__}: {str(e)[:160]})")
        return None


def _a1_tracker(ctx, n: int) -> dict[str, Any] | None:
    from mvh.stages.allin1.read import load_allin1

    a1 = load_allin1(ctx.upstream("allin1"))
    d = a1.doc
    out: dict[str, Any] = {"beats": np.asarray(d.get("beats") or [], float), "downbeats": np.asarray(d.get("downbeats") or [], float),
                           "bpm": d.get("bpm_from_beats") or fu.bpm_of(d.get("beats")) or d.get("bpm")}
    b, db = a1.col("beat"), a1.col("downbeat")
    out["raw_act"] = (b, a1.rate_hz) if b is not None else None
    out["raw_dact"] = (db, a1.rate_hz) if db is not None else None
    return out


def _spectral_kick(ctx, n: int) -> np.ndarray | None:
    """Kick evidence from the spectral stage (events hits.kick or curve hits.kick_raw) when present."""
    try:
        ev = ctx.events("hits.kick")
        k = np.zeros(n)
        for it in ev.items:
            i = int(round(float(it["t"]) * fu.FPS))
            if 0 <= i < n:
                k[i] = max(k[i], float(it.get("strength", 1.0)))
        if k.any():
            return k
    except Exception:  # noqa: BLE001
        pass
    try:
        c = ctx.curve("hits.kick_raw")
        v = fu.fit_len(c.values, n)
        return np.maximum(0.0, np.diff(v, prepend=v[0]))
    except Exception:  # noqa: BLE001
        return None


def pulse_regions(beats: np.ndarray, in_pulse: np.ndarray, duration: float) -> list[dict[str, Any]]:
    b = np.asarray(beats, float)
    f = np.asarray(in_pulse, bool)
    if len(b) == 0:
        return [{"t": 0.0, "d": round(duration, 6), "in_pulse": False}]
    # each beat owns [t_i, t_{i+1}); the last one owns one IBI (capped at the song end)
    ends = np.r_[b[1:], min(duration, b[-1] + (b[-1] - b[-2] if len(b) > 1 else 0.5))]
    spans: list[list[Any]] = []
    if b[0] > 0:
        spans.append([0.0, float(b[0]), False])
    for t0, t1, fl in zip(b, ends, f):
        t0, t1 = float(max(0.0, t0)), float(min(duration, t1))
        if t1 <= t0:
            continue
        if spans and spans[-1][2] == bool(fl) and abs(spans[-1][1] - t0) < 1e-9:
            spans[-1][1] = t1
        else:
            spans.append([t0, t1, bool(fl)])
    if spans[-1][1] < duration - 1e-9:
        if spans[-1][2] is False:
            spans[-1][1] = duration
        else:
            spans.append([spans[-1][1], duration, False])
    return [{"t": round(a, 6), "d": round(c - a, 6), "in_pulse": fl} for a, c, fl in spans if c - a > 1e-6]


def tempo_curve(beats: np.ndarray, in_pulse: np.ndarray, n: int) -> np.ndarray:
    b = np.asarray(beats, float)
    if len(b) < 2:
        return np.full(n, 120.0, np.float32)
    lb = fu.local_bpm(b, 2)
    mids = b
    t = np.arange(n) / fu.FPS
    return np.clip(np.interp(t, mids, lb), 30.0, 300.0).astype(np.float32)


def run(ctx) -> StageResult:  # noqa: C901 - one linear pipeline
    p = ctx.params
    fallbacks: list[str] = []
    warnings: list[str] = []
    flags: list[str] = []
    notes: list[str] = []
    models_prov: list[dict[str, Any]] = []
    tools: list[dict[str, Any]] = []

    mix = ctx.audio("mix", mono=True)
    x = np.asarray(mix.samples, np.float32).reshape(-1)
    sr = int(mix.sr)
    if x.size == 0:
        raise StageError("empty mix")
    from mvh.stages.loudness.level import mix_gain

    a_gain, a_gain_db, a_lufs = mix_gain(ctx, p.get("analysis_lufs", -10.0))
    if a_gain != 1.0:
        x = (x * np.float32(a_gain)).astype(np.float32)
    notes.append(f"analysis level: mix {a_lufs:.2f} LUFS, gain {a_gain_db:+.2f} dB -> {p.get('analysis_lufs', -10.0)} LUFS")
    duration = x.size / sr
    n = -(-x.size * 100 // sr)
    from .trackers import (
        beat_this_logits,
        beat_this_post,
        dsp_features,
        librosa_tempo,
        madmom_activations,
        madmom_dbn,
        to_sr,
    )

    x44 = to_sr(x, sr, 44100)
    feats = dsp_features(x44, n)
    tools.append({"name": "librosa", "version": __import__("librosa").__version__})

    # ------------------------------------------------------------------ trackers
    bt: dict[str, Any] | None = None
    mm: dict[str, Any] | None = None
    use_models = bool(p.get("use_models", True))
    if use_models:
        def _bt():
            h = ctx.model("beat_this")
            ck = next(v for k, v in h.files.items() if k.endswith("final0.ckpt"))
            bl, dl = beat_this_logits(x, sr, str(ck))
            beats, downbeats = beat_this_post(bl, dl)
            models_prov.append({"id": h.id, "licence": h.licence, "revision": h.revision, "file": "final0.ckpt"})
            return {"beats": beats, "downbeats": downbeats, "raw_act": (fu.sigmoid(bl), 50.0), "raw_dact": (fu.sigmoid(dl), 50.0),
                    "bpm": fu.bpm_of(beats)}
        bt = _try(_bt, fallbacks, warnings, "beat_this")

        def _mm():
            h = ctx.model("madmom_downbeats_blstm")
            act = madmom_activations(x44)
            act = np.vstack([act, np.zeros((max(0, n - len(act)), 2), np.float32)])[:n]
            free = madmom_dbn(act)
            models_prov.append({"id": h.id, "licence": h.licence, "revision": h.revision})
            return {"rnn": act, "raw_act": (act[:, 0] + act[:, 1], fu.FPS), "raw_dact": (act[:, 1], fu.FPS),
                    "beats": free[:, 0] if len(free) else np.zeros(0),
                    "downbeats": free[free[:, 1] == 1, 0] if len(free) else np.zeros(0), "bpm": fu.bpm_of(free[:, 0]) if len(free) else None}
        mm = _try(_mm, fallbacks, warnings, "madmom")
    else:
        fallbacks.append("models:disabled")
    a1 = _try(lambda: _a1_tracker(ctx, n), fallbacks, warnings, "allin1")
    trk = {k: v for k, v in (("beat_this", bt), ("allin1", a1), ("madmom", mm)) if v is not None}

    kick = fu.norm01(feats["kick"])
    sk = _spectral_kick(ctx, n)
    if sk is not None:
        kick = np.maximum(kick, 0.8 * fu.norm01(sk))
        notes.append("kick evidence: own 30-150 Hz flux combined with the spectral stage's kick events")
    else:
        notes.append("kick evidence: own 30-150 Hz flux (no spectral kick events)")
    drum = np.clip(kick + 0.8 * fu.norm01(feats["snare"]), 0, None)

    # ------------------------------------------------------------------ latency calibration (per tracker, vs attacks)
    tr = fu.transients(x, sr)
    lags: dict[str, Any] = {}
    for k, v in trk.items():
        lag, nm, thr = fu.estimate_lag(v.get("beats"), tr)
        lags[k] = {"lag_ms": None if lag is None else round(1000 * lag, 1), "matches": nm, "min_rise_db": thr}
        L = float(lag or 0.0)
        if v.get("raw_act") is not None:
            v["act"] = fu.resample_to(v["raw_act"][0], v["raw_act"][1], n, shift=L)
        if v.get("raw_dact") is not None:
            v["dact"] = fu.resample_to(v["raw_dact"][0], v["raw_dact"][1], n, shift=L)
        for key in ("beats", "downbeats"):
            if v.get(key) is not None and len(v[key]):
                v[key] = np.asarray(v[key], float) + L
        if k == "madmom" and L:
            v["lag"] = L
    notes.append("tracker latency vs attacks (ms): " + ", ".join(f"{k} {d['lag_ms']}" for k, d in lags.items()))

    # ------------------------------------------------------------------ fused activation
    acts = [v["act"] for v in trk.values() if v.get("act") is not None]
    if acts:
        fused = np.clip(np.mean([fu.fit_len(a, n) for a in acts], axis=0), 0.0, 1.0)
        fused_src = "+".join(k for k, v in trk.items() if v.get("act") is not None)
    else:
        fused = np.clip(0.5 * fu.norm01(feats["plp"]) + 0.5 * fu.norm01(feats["onset"]), 0, 1) * 0.9
        fused_src = "dsp(plp+onset)"
        fallbacks.append("rhythm:dsp_only")
    notes.append(f"fused beat activation = mean of {fused_src}")

    # ------------------------------------------------------------------ tempo arbitration
    estimates = {"beat_this": bt["bpm"] if bt else None, "madmom": mm["bpm"] if mm else None,
                 "allin1": float(a1["bpm"]) if a1 and a1.get("bpm") else None, "librosa": librosa_tempo(feats["onset"])}
    peaks = fu.tempogram_peaks(feats["onset"])
    forced = ctx.overrides.get("rhythm.bpm")
    arb = fu.arbitrate_tempo(estimates, peaks, drum, forced=float(forced) if forced else None)
    T = arb.bpm
    tol = float(p.get("tempo_tolerance", 0.2)) if not forced else 0.04   # a forced level is followed closely
    lo, hi = T / (1 + tol), T * (1 + tol)
    if arb.ambiguous:
        flags.append("tempo_ambiguous")

    # ------------------------------------------------------------------ beat tracking + refinement
    frames = fu.track_beats(fused, lo, hi)
    beats0 = frames / fu.FPS
    beats1, snapped = fu.snap_beats(beats0, tr, float(p.get("snap_window_s", 0.025)), float(p.get("snap_min_rise_db", 15.0)),
                                    str(p.get("snap_mode", "nearest")))
    strong = tr.times[tr.rise_db >= 9.0] if len(tr.times) else None
    fl0, _ev = fu.pulse_flags(beats1, fused, feats["level_db"], onset_times=strong)
    beats, in_pulse = fu.regularize_grid(beats1, fl0, duration, onset_times=strong, act=fused)
    if len(beats) < 2 or not in_pulse.any():
        flags.append("no_pulse")
        warnings.append("no perceptible pulse found: virtual grid at the arbitrated tempo")
        ibi = 60.0 / T
        beats = np.arange(0.0, duration, ibi)
        in_pulse = np.zeros(len(beats), bool)
    off = ctx.overrides.get("rhythm.beat_offset_s")
    if off:
        beats = beats + float(off)
        keep = (beats >= 0) & (beats < duration)
        beats, in_pulse = beats[keep], in_pulse[keep]
    n_snapped = int(snapped.sum())

    # ------------------------------------------------------------------ downbeats: 2-of-3 vote + meter HMM
    tracker_db: dict[str, np.ndarray | None] = {}
    if bt:
        tracker_db["beat_this"] = bt["downbeats"]
    if a1:
        tracker_db["allin1"] = a1["downbeats"]
    if mm:
        try:
            con = madmom_dbn(mm["rnn"], tuple(int(m) for m in p.get("meters", [3, 4])), lo, hi)
            if len(con):
                con[:, 0] += float(mm.get("lag", 0.0))
            tracker_db["madmom"] = con[con[:, 1] == 1, 0] if len(con) else np.zeros(0)
            mm["beats_constrained"] = con[:, 0] if len(con) else np.zeros(0)
        except Exception as e:  # noqa: BLE001
            warnings.append(f"madmom constrained DBN failed ({type(e).__name__})")
            tracker_db["madmom"] = mm["downbeats"]
    tracker_votes = {k: fu.votes_on_grid(beats, db) for k, db in tracker_db.items()}
    votes = np.zeros(len(beats))
    for v_ in tracker_votes.values():
        votes += v_
    dacts = [v["dact"] for v in trk.values() if v.get("dact") is not None]
    dact_mean = np.mean([fu.fit_len(d, n) for d in dacts], axis=0) if dacts else np.zeros(n)
    dact_at = fu.sample_max(dact_mean, beats) if dacts else np.zeros(len(beats))
    score = votes + 1.0 * fu.norm01(dact_at, 99) if len(beats) else votes
    if not tracker_db and not dacts:
        score = score + 0.5 * fu.norm01(fu.sample_max(kick, beats))
        fallbacks.append("downbeats:kick_only")
    score = np.where(in_pulse, score, 0.0)
    trans = np.r_[False, in_pulse[1:] != in_pulse[:-1]] if len(beats) else np.zeros(0, bool)
    score = score + 0.5 * trans
    n_voters = max(1, len(tracker_db) + (1 if dacts else 0))
    def _decode(sc):
        return fu.decode_meter(sc, meters=tuple(int(m) for m in p.get("meters", [3, 4])), theta=None,
                               switch_cost=float(p.get("meter_switch_cost", 1.25)), break_cost=float(p.get("bar_break_cost", 4.0)),
                               late_bias=float(p.get("meter_late_bias", 0.25)))

    mp = _decode(score)
    if len(beats) and len(tracker_db) >= 2:
        # A tracker whose downbeats sit a constant number of beats off the first-pass fused bars (madmom's known
        # one-beat phase error, SPIKE) votes with that shift removed, so the known-wrong phase cannot flip the bars
        # (or insert a spurious short bar) where the other trackers are weak. The raw (uncorrected) phase stays in
        # the QA flags below.
        rep1 = fu.phase_report(beats, mp.position, tracker_db)
        corrected = {k: r["best_shift"] for k, r in rep1.items() if r["best_shift"] != 0 and r["f_best"] > r["f"] + 0.2}
        if corrected:
            votes = np.zeros(len(beats))
            for k, v_ in tracker_votes.items():
                sh = corrected.get(k, 0)
                if sh:
                    v2 = np.zeros_like(v_)
                    idx = np.nonzero(v_)[0] + sh
                    v2[idx[(idx >= 0) & (idx < len(v_))]] = 1.0
                    v_ = v2
                votes += v_
            score = votes + 1.0 * fu.norm01(dact_at, 99) if len(beats) else votes
            score = np.where(in_pulse, score, 0.0)
            score = score + 0.5 * trans
            mp = _decode(score)
            notes.append("downbeat vote: phase-shifted tracker(s) corrected before the vote: "
                         + ", ".join(f"{k}{sh:+d}" for k, sh in sorted(corrected.items())))
    k_phase = int(ctx.overrides.get("rhythm.downbeat_phase") or 0)
    if k_phase and len(beats):
        # rotate the bar numbering by k beats: beat i takes the position the decoder gave beat i - k
        pos, met = mp.position.copy(), mp.meter.copy()
        for i in range(len(beats)):
            j = i - k_phase
            if 0 <= j < len(beats):
                pos[i], met[i] = mp.position[j], mp.meter[j]
            else:
                ref = 0 if j < 0 else len(beats) - 1
                m = int(mp.meter[ref])
                pos[i] = (int(mp.position[ref]) - 1 + (j - ref)) % m + 1
                met[i] = m
        mp = fu.MeterPath(pos, met, mp.irregular.copy())
        notes.append(f"rhythm.downbeat_phase override: bar numbering rotated by {k_phase} beats")

    # ------------------------------------------------------------------ per-beat strength/conf, bars
    strength = fu.sample_max(fused, beats)
    tol_s = float(p.get("beat_tol_s", 0.07))
    support = np.zeros(len(beats))
    nb_tr = 0
    for v in trk.values():
        tb = np.asarray(v.get("beats") if v.get("beats") is not None else [], float)
        if len(tb) < 4:
            continue
        nb_tr += 1
        j = np.searchsorted(tb, beats)
        d1 = np.abs(beats - tb[np.clip(j - 1, 0, len(tb) - 1)])
        d2 = np.abs(beats - tb[np.clip(j, 0, len(tb) - 1)])
        support += (np.minimum(d1, d2) <= tol_s)
    beat_conf = np.where(in_pulse, 0.25 + 0.75 * (support / max(1, nb_tr)), 0.5) if nb_tr else np.where(in_pulse, 0.6, 0.5)
    bar_conf: dict[int, float] = {}
    bar_no = 0
    for i in range(len(beats)):
        if mp.position[i] == 1:
            bar_no += 1
            bar_conf[bar_no] = float(np.clip((votes[i] + (1.0 if dacts and fu.norm01(dact_at, 99)[i] > 0.5 else 0.0)) / n_voters, 0, 1)) if in_pulse[i] else 0.5
    if bar_no == 0:
        bar_conf[0] = 0.5
    bars = fu.build_bars(beats, mp, in_pulse, strength, beat_conf, bar_conf, duration)
    # pickup bar conf
    for b in bars.bars:
        if b["bar"] == 0:
            b["conf"] = round(float(np.mean([bb["conf"] for bb in bars.beats if bb["bar"] == 0])), 4)

    # ------------------------------------------------------------------ feel, tempo segments, pulse regions
    feel = fu.feel_labels(beats, {k: v.get("beats") for k, v in trk.items()})
    # W4A-S18: a half-time backbeat (snare on 3 of 4/4) also makes the feel half_time (the trackers only see tempo levels)
    bb_half, bb_rep = fu.backbeat_feel(beats, mp.position, mp.meter, in_pulse, feats.get("perc_hi"),
                                       enter=float(p.get("backbeat_half_enter", 1.5)), leave=float(p.get("backbeat_half_leave", 1.3)),
                                       flux_mid=feats.get("snare"), mid_min=float(p.get("backbeat_mid_min", 1.25)))
    if bb_half.any():
        feel = np.where((feel == "normal") & bb_half, "half_time", feel).astype(object)
        notes.append(f"feel: half-time backbeat on {int(bb_half.sum())} beats (snare-band ratio beat 3 / beats 2+4 = {bb_rep.get('ratio')})")
    segs = fu.tempo_segments(beats, in_pulse, feel, duration)
    pr = pulse_regions(beats, in_pulse, duration)
    ip_beats = beats[in_pulse]
    final_bpm = fu.bpm_of(ip_beats) or T
    dur_feel: dict[str, float] = {}
    for s in segs:
        dur_feel[s["feel"]] = dur_feel.get(s["feel"], 0.0) + s["d"]
    feel_global = max(dur_feel, key=dur_feel.get) if dur_feel else "normal"
    if len({s["feel"] for s in segs}) > 1:
        flags.append("feel_changes")
    is_var = bool(len({round(s["bpm"] / final_bpm, 2) for s in segs if abs(s["bpm"] / final_bpm - 1) > 0.04}) > 0
                  or not all(s["stable"] for s in segs))

    # ------------------------------------------------------------------ QA
    trk_beats = {k: v.get("beats") for k, v in trk.items() if v.get("beats") is not None and len(v.get("beats")) >= 4}
    f_vs_grid = {k: round(fu.f_measure(v, ip_beats, tol_s), 3) for k, v in trk_beats.items()}
    names = sorted(trk_beats)
    pair_f = {f"{a}~{b}": round(fu.f_measure(trk_beats[a], trk_beats[b], tol_s), 3) for i, a in enumerate(names) for b in names[i + 1:]}
    beat_agree = float(np.median(list(f_vs_grid.values()))) if f_vs_grid else None
    phase = fu.phase_report(beats, mp.position, tracker_db)
    db_agree = float(np.median([v["f"] for v in phase.values()])) if phase else None
    for k, v in phase.items():
        if v["best_shift"] != 0 and v["f_best"] > v["f"] + 0.2:
            flags.append(f"downbeat_phase_off:{k}:{v['best_shift']:+d}")
    for k in TRACKERS:
        if k not in trk:
            flags.append(f"tracker_missing:{k}")
    irregular = [b["bar"] for b in bars.bars if b.get("irregular")]
    if irregular:
        flags.append("irregular_bars")
    if not in_pulse.all():
        flags.append("no_pulse_regions")
    if beat_agree is not None and beat_agree < 0.7:
        flags.append("low_tracker_agreement")
    est_vals = [v for v in estimates.values() if v]
    if est_vals:
        rel = [v / final_bpm for v in est_vals]
        if all(abs(r - 1) < 0.04 for r in rel):
            agreement = "agree"
        elif all(min(abs(r - 1), abs(r - 2), abs(r - 0.5)) < 0.05 for r in rel):
            agreement = "octave"
        else:
            agreement = "disagree"
    else:
        agreement = "none"
    if agreement == "disagree" and not forced:
        # the trackers do not even agree on the tempo octave (MEGAFAUNA): the arbitrated level is evidence-based but
        # the user should confirm it (override rhythm.bpm; alternatives in override_hint)
        flags.append("tempo_trackers_disagree")
        warnings.append(f"beat trackers disagree on the tempo level; chose {final_bpm:.1f} BPM by arbitration "
                        f"(alternatives: {', '.join(f'{c:.1f}' for c in sorted({round(v, 1) for v in est_vals}))}); "
                        "confirm or override rhythm.bpm")
    bpb_counts: dict[int, int] = {}
    for b in bars.bars:
        if b["bar"] > 0 and b["in_pulse"]:
            bpb_counts[b["beats_in_bar"]] = bpb_counts.get(b["beats_in_bar"], 0) + 1
    bpb = max(bpb_counts, key=bpb_counts.get) if bpb_counts else 4
    meter_share = bpb_counts.get(bpb, 0) / max(1, sum(bpb_counts.values()))
    meter_conf = float(np.clip(meter_share * (0.5 + 0.5 * (db_agree if db_agree is not None else 0.5)), 0, 1))
    conf = float(np.clip(0.45 * (beat_agree if beat_agree is not None else 0.5)
                         + 0.30 * min(1.0, arb.margin / 0.5) + 0.25 * (db_agree if db_agree is not None else 0.5), 0, 1))
    if forced:
        conf = max(conf, 0.9)
        notes.append(f"rhythm.bpm override: tempo level forced to {forced}")
    alts = [c for c in arb.candidates[1:] if c["score"] >= 0.6][:3]
    alts += [c for c in arb.candidates[1:] if c["relation"] in ("x2", "x0.5") and c["score"] >= 0.3 and c not in alts]
    hint: dict[str, Any] = {}
    if alts:
        hint["rhythm.bpm"] = [c["bpm"] for c in alts]
    off_trk = {k: v["best_shift"] for k, v in phase.items() if v["best_shift"] != 0 and v["f_best"] > v["f"] + 0.2}
    if off_trk:
        hint["rhythm.downbeat_phase"] = sorted(set(off_trk.values()))

    tempo_doc = {
        "bpm": round(final_bpm, 3), "confidence": round(conf, 3), "feel": feel_global, "is_variable": is_var,
        "candidates": arb.candidates,
        "meter": {"time_signature": f"{bpb}/4", "beats_per_bar": int(bpb), "confidence": round(meter_conf, 3), "changes": bars.changes},
        "qa": {"beat_agreement_f": None if beat_agree is None else round(beat_agree, 3),
               "downbeat_agreement_f": None if db_agree is None else round(db_agree, 3), "flags": sorted(set(flags))},
        "estimates": {k: (round(v, 3) if v else None) for k, v in estimates.items()},
        "agreement": agreement,
        # ---- additive (M2): evidence the user / an agent can act on
        "arbitration": {"chosen_bpm": round(T, 3), "margin": arb.margin, "ambiguous": arb.ambiguous, "forced": forced,
                        "rows": arb.evidence["rows"][:8], "tempogram_peaks": arb.evidence["tempogram_peaks"]},
        "downbeat_vote": {"voters": sorted(tracker_db), "per_tracker": phase},
        "trackers": {k: {"bpm": (round(trk[k]["bpm"], 3) if trk[k].get("bpm") else None), "f_vs_grid": f_vs_grid.get(k),
                         "n_beats": int(len(trk[k]["beats"])) if trk[k].get("beats") is not None else 0} for k in trk},
        "pairwise_beat_f": pair_f,
        "feel_shares": {k: round(v / max(1e-9, duration), 3) for k, v in sorted(dur_feel.items())},
        "backbeat": bb_rep,
        "analysis_level": {"mix_lufs": round(float(a_lufs), 2), "gain_db": round(float(a_gain_db), 2),
                           "target_lufs": p.get("analysis_lufs", -10.0)},
        "pulse": {"in_pulse_share": round(float(sum(r["d"] for r in pr if r["in_pulse"]) / duration), 3),
                  "n_regions": len(pr), "n_virtual_beats": int((~in_pulse).sum())},
        "override_hint": hint,
        "tracker_lag": lags,
        "refinement": {"snapped_beats": n_snapped, "snap_window_s": float(p.get("snap_window_s", 0.025))},
    }

    # ------------------------------------------------------------------ write
    w = ctx.writer
    w.events("beats", bars.beats)
    bar_fields = {"irregular": {"unit": None, "type": "boolean"}} if irregular else None
    w.events("bars", bars.bars, fields=bar_fields)
    w.events("tempo_segments", segs, fields={"feel": {"unit": None, "type": "enum"}})
    w.events("pulse_regions", pr)
    w.json("meta/tempo.json", tempo_doc)
    ip_curve = np.zeros(n, np.float32)
    for r in pr:
        if r["in_pulse"]:
            a, b = int(math.floor(r["t"] * fu.FPS + 0.5)), int(math.floor((r["t"] + r["d"]) * fu.FPS + 0.5))
            ip_curve[max(0, a):min(n, b)] = 1.0
    beat_curve = bt["act"] if bt else fused
    down_curve = bt["dact"] if bt else dact_mean
    w.curves("core", {"tempo.bpm": tempo_curve(beats, in_pulse, n),
                      "rhythm.beat_act": np.clip(fu.fit_len(beat_curve, n), 0, 1).astype(np.float32),
                      "rhythm.downbeat_act": np.clip(fu.fit_len(down_curve, n), 0, 1).astype(np.float32),
                      "rhythm.in_pulse": ip_curve})
    status = "degraded" if any(f.endswith(":unavailable") for f in fallbacks) or "rhythm:dsp_only" in fallbacks else "ok"
    if not use_models:
        status = "ok"
    summary = {"bpm": tempo_doc["bpm"], "feel": feel_global, "meter": tempo_doc["meter"]["time_signature"],
               "n_beats": len(bars.beats), "n_bars": len([b for b in bars.bars if b["bar"] > 0]),
               "pickup_beats": sum(1 for b in bars.beats if b["bar"] == 0), "agreement": agreement,
               "alternatives": [c["bpm"] for c in alts], "flags": sorted(set(flags))[:8]}
    return StageResult(status=status, summary=summary, warnings=warnings, fallbacks=sorted(set(fallbacks)),
                       confidence=round(conf, 3),
                       provenance={"models": models_prov, "tools": tools, "notes": notes})
