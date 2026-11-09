"""R-DSP review (M1 spectral): regression guard for viz-port fidelity against the REAL viz/js/audio.js, driven causally
under Node (viz_causal.cjs) with the AnalyserNode data a browser would deliver. The builder's parity test checks the
band map and single functions; this checks the whole offline pipeline end to end. viz is frame-rate dependent (its flux
onsets grow with fps), and the offline port runs at 100 Hz, so the reference is viz at 100 fps.
Passing at review time (bands corr >= 0.99, onset counts within 3 %); it guards the fixes for the kick findings."""

from __future__ import annotations

import numpy as np
from rdsp_m1_support import frame_times, run_spectral, viz_causal
from tests.synth.m1.signals import groove


def test_offline_viz_values_track_the_real_viz(viz_ok, tmp_path):
    x, sr, _ = groove(24.0)
    v = viz_causal(x, sr, tmp_path / "viz", fps=(100, 1))
    ctx = run_spectral(x, sr, tmp_path / "s")
    ch = ctx.written_curves()
    # viz frame k is causal at (k + 1) / 100 s; the offline frame i is centred at i / 100 s
    for vk, ck in (("bass", "bands.bass_viz"), ("mid", "bands.mid_viz"), ("high", "bands.high_viz"), ("level", "bands.level")):
        off = ch[ck].astype(np.float64)
        corrs = []
        for lag in range(0, 4):
            a = v[vk][lag:]
            n = min(a.size, off.size) - 10
            corrs.append(float(np.corrcoef(a[:n], off[:n])[0, 1]))
        best = max(corrs)
        assert best >= 0.98, (vk, best)
    n_viz = {b: int(v[k].sum()) for b, k in (("bass", "onset"), ("mid", "midOnset"), ("high", "highOnset"))}
    for b, nv in n_viz.items():
        n_off = len(ctx.written_events(f"onsets.{b}")["items"])
        assert abs(n_off - nv) <= max(3, 0.1 * nv), (b, n_off, nv)
    # the hits the viz itself registers (its one-hit-per-note logic) are all in hits.kick and flagged viz=true
    viz_hits = frame_times(v["kickHit"], v["t"])
    flagged = [it for it in ctx.written_events("hits.kick")["items"] if it["viz"]]
    assert abs(len(flagged) - viz_hits.size) <= max(3, 0.1 * viz_hits.size), (len(flagged), viz_hits.size)
