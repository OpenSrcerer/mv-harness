"""W4 R-ADVERSARY perturbation tests: the synthetic song re-analysed after simple, label-preserving edits.

The runs are made by ``out/_wip/r-adversary/run_queue.ps1`` (mvh analyze --profile max, offline) into
``out/_wip/r-adversary/<name>``; each test skips when its run is absent. The generator truth is the reference.

* W4A-GAIN (M2 allin1 + structure): the section grid and labels are not gain-invariant.
  - -12 dB (no clipping, every stem still present): the boundaries stay, but allin1 labels the whole song 'intro', and
    structure turns verse / chorus / bridge / chorus into inst / inst / build / drop.
  - +12 dB (a hot, clipped master: 43,630 clipped samples): the bridge (truth 25.0 s, also the EDM build start)
    starts one bar late at 27.0 s, is labelled chorus, and the build shrinks from 7.5 s to 5.5 s.
  Beats, downbeats, drum hits, key and the drop are unchanged in both, so the music did not change. A level
  normalisation before the label models would do.
* W4A-STABLE (M2 structure, fed by M1 dynamics): the same instability under other edits that keep the music.
  - 48 kHz (soxr resample): dynamics splits into 7 parts instead of 5 (42.5-56.5 s 'medium' becomes 'loud' + a 'soft'
    52.5 s), and the outro starts one bar late at 52.5 s (truth 50.5 s).
  - atempo 0.9 (108 BPM; every truth time x 1/0.9): beats stay perfect (F 1.00) and the tempo is 107.94, but BOTH EDM
    roles disappear (truth build 27.8 s, drop 38.3 s), the bridge is labelled chorus and the drop section is cut in two
    (an 'outro' at 47.2 s inside the drop).
  - MP3 192k: identical to the baseline (control).
"""

from __future__ import annotations

import pytest

TRUTH_LABELS = ["intro", "verse", "chorus", "bridge", "chorus", "outro"]
TRUTH_T = [1.0, 9.0, 17.0, 25.0, 34.5, 50.5]


def _sections(f):
    return [(s["label"], float(s["t"])) for s in f.events("sections")]


@pytest.mark.parametrize("name", ["synth_gm12", "synth_gp12"])
def test_w4a_sections_survive_a_12db_gain_change(perturbed, name):
    f = perturbed(name)
    sec = _sections(f)
    starts = [t for _, t in sec]
    missing = [t for t in TRUTH_T if not any(abs(t - s) <= 0.5 for s in starts)]
    assert not missing, f"{name}: truth section starts {missing} lost (est starts {[round(s, 2) for s in starts]})"
    labels = [lab for lab, _ in sec]
    if len(labels) == len(TRUTH_LABELS):
        wrong = [(i + 1, t, e) for i, (t, e) in enumerate(zip(TRUTH_LABELS, labels)) if t != e]
        assert not wrong, f"{name}: {len(wrong)} of 6 section labels changed with the gain (section, truth, est): {wrong}"


@pytest.mark.parametrize("name", ["synth_gm12", "synth_gp12"])
def test_w4a_edm_build_start_survives_a_12db_gain_change(perturbed, name):
    f = perturbed(name)
    builds = [e for e in f.events("edm_roles") if e["role"] == "build"]
    assert builds, f"{name}: no build"
    assert abs(builds[0]["t"] - 25.0) <= 0.5, f"{name}: build starts at {builds[0]['t']:.2f} s (truth 25.0 s)"


def test_w4a_control_unperturbed_synth_matches_truth(real_folder):
    f = real_folder("synth")
    sec = _sections(f)
    assert [lab for lab, _ in sec] == TRUTH_LABELS
    assert all(abs(a - b) <= 0.5 for (_, a), b in zip(sec, TRUTH_T))


def test_w4a_sections_survive_resampling_to_48k(perturbed):
    f = perturbed("synth_sr48")
    starts = [t for _, t in _sections(f)]
    missing = [t for t in TRUTH_T if not any(abs(t - s) <= 0.5 for s in starts)]
    assert not missing, f"synth_sr48: truth section starts {missing} lost (est starts {[round(s, 2) for s in starts]})"


def test_w4a_edm_roles_survive_a_10pct_time_stretch(perturbed, synth_truth):
    f = perturbed("synth_tempo90")
    k = 1 / 0.9
    est = [(e["role"], float(e["t"])) for e in f.events("edm_roles")]
    for r in synth_truth["edm_roles"]:
        t = r["t"] * k
        assert any(role == r["role"] and abs(te - t) <= 0.5 for role, te in est), (
            f"synth_tempo90: truth {r['role']} at {t:.2f} s not found (est {[(a, round(b, 2)) for a, b in est]})")


def test_w4a_control_mp3_keeps_the_structure(perturbed):
    f = perturbed("synth_mp3")
    sec = _sections(f)
    assert [lab for lab, _ in sec] == TRUTH_LABELS
    assert all(abs(a - b) <= 0.5 for (_, a), b in zip(sec, TRUTH_T))


def test_w4a_a_cappella_has_no_agent_kicks(perturbed):
    """W4A-ACAP (M1 spectral hits.kick, with M3a drums kick QA and M2 choreo): the fixture's own vocals stem, no
    drums at all (truth: 0 kicks). drums finds no drum stem and falls back to kick_source = mix, so song.kicks() is
    hits.kick: 13 'kicks' with kick_conf 0.68-1.00 and strength up to 2.0, each within 0.25 s of a sung word onset.
    meta/drums.json agreement is mix_in_drums 0.0 / drums_in_mix None, and no QA flag is raised (low: false). choreo
    then builds 16 groove bars with kick/snare/hat rows and 7 'drum' hit points on a vocal-only track."""
    f = perturbed("synth_acap")
    assert not [h for h in f.events("drum_hits")], "control: the a cappella run has no drum hits"
    src = f.json("meta/drums.json")["kick_source"]
    kicks = f.events("hits.kick") if src == "mix" else [h for h in f.events("drum_hits") if h["drum"] == "kick"]
    flags = f.json("manifest.json")["status"].get("flags", [])
    qa = [x for x in flags if x.startswith("qa:kick")]
    assert len(kicks) <= 2 or qa, (f"synth_acap (vocals only, truth 0 kicks): kick_source={src}, {len(kicks)} agent-facing kicks, "
                                   f"no qa:kick* flag (flags with 'kick': {[x for x in flags if 'kick' in x]})")


def test_w4a_a_cappella_has_no_drum_hit_points(perturbed):
    f = perturbed("synth_acap")
    drum_hp = [h for h in f.events("hit_points") if "drum" in h.get("kinds", [])]
    assert not drum_hp, f"synth_acap (no drums): {len(drum_hp)} hit points of kind 'drum'"
