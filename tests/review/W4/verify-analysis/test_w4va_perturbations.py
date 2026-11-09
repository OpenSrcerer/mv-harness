"""W4 verifier (analysis group, round 1): do the W4A-GAIN / W4A-STABLE / W4A-ACAP fixes hold beyond the adversary's own
perturbations?

The fixer validated W4A-GAIN on the synthetic song only. Its stems sum to about -20.4 LUFS, BELOW allin1's new level band
[-16, -6] LUFS, so the baseline and the -12 dB copy are both raised to -16 LUFS: allin1 sees the same input in both
runs, and the test passes by construction. Real masters are inside the band and are analysed at their own level, so a
-12 dB copy of a real song reaches allin1 several dB lower than the original. These tests re-run that edit on real songs,
other tempo / sample-rate edits on the synthetic song, and a real a cappella (a separated rap vocal).

Runs: ``out/_wip/w4verify-analysis-r1/<name>`` (``run_queue.ps1``; inputs made with ffmpeg ``volume=-12dB``,
``atempo=1.1`` / ``0.95``, ``aresample=32000:resampler=soxr``; newton_acap = the fixer's Newton ``stems/vocals.flac``).
Baselines: ``out/_wip/w4fix-analysis/<slug>`` (current code). Numbers only, no lyric text.
"""

from __future__ import annotations

import pytest
from w4va_support import GAIN_IDS, GAIN_PAIRS, TRUTH_LABELS, TRUTH_T, base, run, truth


def _match(a: list[tuple[str, float]], b: list[tuple[str, float]], tol: float = 0.5):
    """(starts of b lost in a, label changes at the shared starts)."""
    lost, relabel = [], []
    for lab, t in b:
        hit = [x for x in a if abs(x[1] - t) <= tol]
        if not hit:
            lost.append(round(t, 2))
        elif hit[0][0] != lab:
            relabel.append((round(t, 2), lab, hit[0][0]))
    return lost, relabel



# ----------------------------------------------------------------------------------------------- W4A-GAIN, real songs
@pytest.mark.parametrize("slug,name", GAIN_PAIRS, ids=GAIN_IDS)
def test_w4va_real_song_sections_survive_a_12db_gain_change(slug, name):
    """A quieter copy (no clipping, pure gain) of a real song must keep the sections and labels of the original."""
    g = run(name)
    b = base(slug)
    lost, relabel = _match(g.sections(), b.sections())
    added, _ = _match(b.sections(), g.sections())
    assert not lost and not relabel and not added, (
        f"{name}: {len(lost)} section starts lost {lost}, {len(added)} added {added}, {len(relabel)} relabelled "
        f"(t, original, -12 dB) {relabel}; dynamics silences original "
        f"{[(round(s['t'], 2), round(s['d'], 2)) for s in b.events('silences')]} vs -12 dB "
        f"{[(round(s['t'], 2), round(s['d'], 2)) for s in g.events('silences')]}")


@pytest.mark.parametrize("slug,name", GAIN_PAIRS, ids=GAIN_IDS)
def test_w4va_real_song_edm_roles_survive_a_12db_gain_change(slug, name):
    g = run(name)
    b = base(slug)
    lost, relabel = _match(g.edm(), b.edm())
    added, _ = _match(b.edm(), g.edm())
    assert not lost and not added and not relabel, (
        f"{name}: EDM roles original {[(r, round(t, 2)) for r, t in b.edm()]} vs -12 dB "
        f"{[(r, round(t, 2)) for r, t in g.edm()]}")


# ------------------------------------------------------------------------------------- W4A-STABLE, other edits (synth)
# round 2 adds two edits the fixer never tuned on (its structure rules W4-AN-11 c/d were fitted to tempo95 / sr32)
SYNTH_EDITS = [("synth_tempo110", 1 / 1.1), ("synth_tempo95", 1 / 0.95), ("synth_sr32", 1.0), ("synth_base", 1.0),
               ("synth_tempo105", 1 / 1.05), ("synth_sr22", 1.0)]


@pytest.mark.parametrize("name,k", SYNTH_EDITS, ids=[n for n, _ in SYNTH_EDITS])
def test_w4va_synth_sections_survive_other_edits(name, k):
    f = run(name)
    sec = f.sections()
    starts = [t for _, t in sec]
    missing = [round(t * k, 2) for t in TRUTH_T if not any(abs(t * k - s) <= 0.5 for s in starts)]
    assert not missing, f"{name}: truth section starts {missing} lost (est {[(lab, round(s, 2)) for lab, s in sec]})"
    labels = [lab for lab, _ in sec]
    assert labels == TRUTH_LABELS, f"{name}: labels {labels} (truth {TRUTH_LABELS})"


@pytest.mark.parametrize("name,k", SYNTH_EDITS, ids=[n for n, _ in SYNTH_EDITS])
def test_w4va_synth_edm_roles_survive_other_edits(name, k):
    f = run(name)
    est = f.edm()
    for r in truth()["edm_roles"]:
        t = r["t"] * k
        assert any(role == r["role"] and abs(te - t) <= 0.5 for role, te in est), (
            f"{name}: truth {r['role']} at {t:.2f} s not found (est {[(a, round(b, 2)) for a, b in est]})")


def test_w4va_fresh_synth_run_reproduces_the_fixers_synth():
    """A fresh analysis of the synthetic song from audio must give the fixer's published result (no hand edits)."""
    f, b = run("synth_base"), base("synth")
    assert [(lab, round(t, 2)) for lab, t in f.sections()] == [(lab, round(t, 2)) for lab, t in b.sections()]
    assert [(r, round(t, 2)) for r, t in f.edm()] == [(r, round(t, 2)) for r, t in b.edm()]
    for name in ("drum_hits", "hits.kick", "grooves", "vocal_phrases", "hit_points"):
        assert len(f.events(name)) == len(b.events(name)), f"{name}: fresh {len(f.events(name))} vs fixer {len(b.events(name))}"


# ----------------------------------------------------------------------------------------- W4A-ACAP, a real a cappella
def _agent_kicks(f):
    src = f.json("meta/drums.json")["kick_source"]
    if src == "mix":
        return src, f.events("hits.kick")
    return src, [h for h in f.events("drum_hits") if h["drum"] == "kick"]


def test_w4va_real_a_cappella_has_no_agent_kicks():
    """Newton's separated vocal stem (rap, plosives) as the input: no drums at all, so no agent-facing kicks (or a QA flag)."""
    f = run("newton_acap")
    src, kicks = _agent_kicks(f)
    flags = f.json("manifest.json")["status"].get("flags", [])
    qa = [x for x in flags if x.startswith("qa:kick")]
    assert len(kicks) <= 2 or qa, (f"newton_acap (rap vocal only): kick_source={src}, {len(kicks)} agent-facing kicks, "
                                   f"{len(f.events('drum_hits'))} drum hits, no qa:kick* flag")


def test_w4va_real_a_cappella_has_no_drum_structure():
    """Before 145 s only: from about 145 s the separated vocal stem carries the original's outro drums as bleed (17 of
    its 27 drum hits with vel >= 0.3 coincide with a drum-stem snare / tom / cymbal of the full mix), so drum hits,
    grooves and drum hit points there describe a real (leaked) drum part."""
    f = run("newton_acap")
    drum_hp = [h for h in f.events("hit_points") if "drum" in h.get("kinds", []) and h["t"] < 145.0]
    gr = [g for g in f.events("grooves") if g["t"] < 145.0]
    assert not drum_hp and not gr, (f"newton_acap (no drums): {len(drum_hp)} 'drum' hit points, {len(gr)} groove bars, "
                                    f"{len(f.events('drum_hits'))} drum hits")


@pytest.mark.parametrize("which", ["fixer_synth_acap", "newton_acap"])
def test_w4va_a_cappella_feel_is_not_half_time(which):
    """An a cappella has no backbeat: no half-time feel. The fixer's own synth_acap folder (rhythm 1.1.1) still has a
    10 s half_time segment (feel_shares half_time 0.177; backbeat.half_time_beats 0, so it comes from the tracker
    feel on the re-levelled allin1 input); the pre-fix run (out/_wip/r-adversary/synth_acap) was normal 1.0."""
    f = base("synth_acap") if which == "fixer_synth_acap" else run("newton_acap")
    shares = f.json("meta/tempo.json").get("feel_shares") or {}
    assert float(shares.get("half_time", 0.0)) <= 0.05, f"{which}: feel_shares {shares}"


@pytest.mark.parametrize("slug,name", GAIN_PAIRS, ids=GAIN_IDS)
def test_w4va_real_song_beat_grid_survives_a_12db_gain_change(slug, name):
    """The beat and downbeat grid of a -12 dB copy must match the original (F >= 0.95 at 70 ms). The original's trackers
    are bit-stable across runs (ud2-kick, integrator and w4fix-analysis MEGAFAUNA: beat_this 162.162 / 382 beats, madmom
    193.548 / 631, allin1 105.263 / 277), so a difference is the level, not run-to-run noise."""
    import numpy as np

    g, b = run(name), base(slug)

    def F(r, e, tol=0.07):
        r, e = np.asarray(r), np.asarray(e)
        rec = float(np.mean([np.min(np.abs(e - t)) <= tol for t in r]))
        pre = float(np.mean([np.min(np.abs(r - t)) <= tol for t in e]))
        return 0.0 if rec + pre == 0 else 2 * rec * pre / (rec + pre)

    fb = F([x["t"] for x in b.events("beats")], [x["t"] for x in g.events("beats")])
    fd = F([x["t"] for x in b.events("bars")], [x["t"] for x in g.events("bars")])
    tr = {k: (v.get("bpm"), v.get("n_beats")) for k, v in g.json("meta/tempo.json")["trackers"].items()}
    tr0 = {k: (v.get("bpm"), v.get("n_beats")) for k, v in b.json("meta/tempo.json")["trackers"].items()}
    assert fb >= 0.95 and fd >= 0.95, (f"{name}: beat F {fb:.3f}, downbeat F {fd:.3f} against the original; "
                                       f"trackers (bpm, n) original {tr0} vs -12 dB {tr}")
