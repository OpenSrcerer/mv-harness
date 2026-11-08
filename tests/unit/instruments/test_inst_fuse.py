# ruff: noqa: E501  (long numeric tables / docstrings)
"""Pure fusion rules of the instruments stage (no models)."""

from __future__ import annotations

import numpy as np

from mvh.stages.instruments import fuse as F
from mvh.stages.instruments.vocab import BY_SLUG, VOCAB


def test_vocab_slugs_valid_and_unique():
    import re

    slugs = [i.slug for i in VOCAB]
    assert len(slugs) == len(set(slugs)) and len(slugs) >= 25
    assert all(re.match(r"^[a-z0-9_]+$", s) for s in slugs)
    for i in VOCAB:  # parents are defined before their sub-types (the run loop relies on it)
        if i.parent:
            assert slugs.index(i.parent) < slugs.index(i.slug)


def test_voice_needs_the_tagger_but_drums_trust_their_stem():
    n = 10
    stem_on = np.ones(n)
    no_tag = np.zeros(n)
    voice = F.fuse(BY_SLUG["voice"], no_tag, stem_on)
    drums = F.fuse(BY_SLUG["drums"], no_tag, stem_on)
    assert voice.max() < F.ON          # a vocals stem alone (synth leads, bleed) is not a voice
    assert drums.min() >= F.ON         # a separated drum stem alone is drums
    both = F.fuse(BY_SLUG["voice"], np.ones(n), stem_on)
    assert both.min() > 0.95
    # silent anchor stem: the tagger is believed at most INACTIVE_TAG_CAP
    assert F.fuse(BY_SLUG["bass"], np.ones(n), np.zeros(n)).max() <= F.INACTIVE_TAG_CAP + 1e-6


def test_subtype_is_capped_by_parent():
    p = F.fuse(BY_SLUG["electric_guitar"], np.ones(8), None, parent_p=np.full(8, 0.3))
    assert np.allclose(p, 0.3)


def test_segments_hysteresis_bridge_and_min_length():
    p = np.array([0, .6, .6, .4, .6, .6, 0, 0, 0, 0, .7, 0, 0, 0, .9, .9, .9, 0], float)
    segs = F.segments_1hz(p, 18.0, min_s=2.0, max_gap_s=2.0)
    assert segs == [(1, 5), (14, 16)]  # the 1-frame blip at 10 is dropped; 3 (0.4 >= off) keeps the run
    t0, t1 = F.frames_to_span(1, 5, 18.0)
    assert (t0, t1) == (0.5, 5.5)


def test_window_activity_fraction():
    a = np.zeros(1000)
    a[200:600] = 1  # active 2.0-6.0 s
    w = F.window_activity(a, 10)
    assert w[4] == 1.0 and w[0] == 0.0 and 0.4 < w[2] < 0.6


def test_snap_to_activity():
    a = np.zeros(1000)
    a[230:610] = 1
    assert F.snap_to_activity(1.5, 6.5, a) == (2.3, 6.1)


def test_style_shares_hiphop_context_turns_speech_into_rap():
    labels = ["Singing", "Male singing", "Female singing", "Child singing", "Synthetic singing", "Humming", "Yodeling",
              "A capella", "Choir", "Speech", "Male speech", "Female speech", "Child speech", "Narration", "Conversation",
              "Whispering", "Shout", "Yell", "Rapping", "Hip hop music"]
    idx = {lab: i for i, lab in enumerate(labels)}
    n = 6
    lead = np.zeros((n, len(labels)))
    lead[:, idx["Speech"]] = 0.5
    mix = np.zeros((n, len(labels)))
    s = F.vocal_style_shares(lead, mix, idx)
    assert np.allclose(s[:, 1], 1.0)  # speech without a hip-hop context stays speech
    mix[:, idx["Hip hop music"]] = 0.3
    s = F.vocal_style_shares(lead, mix, idx)
    assert np.allclose(s[:, 2], 1.0)  # the same speech over a hip-hop beat is rap
    # sustained pitch pushes towards singing
    lead2 = np.zeros((n, len(labels)))
    lead2[:, idx["Speech"]] = 0.3
    lead2[:, idx["Male singing"]] = 0.25
    s1 = F.vocal_style_shares(lead2, None, idx)
    s2 = F.vocal_style_shares(lead2, None, idx, sustain=np.ones(n), voiced_s=np.full(n, 2.0))
    assert s1[0].argmax() == 1 and s2[0].argmax() == 0


def test_pitch_sustain_separates_held_notes_from_glides():
    hop = 0.016
    t = np.arange(0, 4, hop)
    held = 60 + 0.3 * np.sin(2 * np.pi * 5.5 * t)       # a held note with vibrato
    glide = 55 + 8 * np.sin(2 * np.pi * 1.7 * t)          # speech-like continuous glide
    v = np.ones(t.size, bool)
    r1, vs1 = F.pitch_sustain(held, v, 4, hop_s=hop)
    r2, _ = F.pitch_sustain(glide, v, 4, hop_s=hop)
    assert r1[2] > 0.9 and r2[2] < 0.3 and vs1[2] > 3.0


def test_smooth_labels_majority():
    lab = np.array([0, 0, 1, 0, 0, -1, 2, 2, 2])
    out = F.smooth_labels(lab, 5)
    assert out[2] == 0 and out[5] == -1 and out[7] == 2


def test_style_needs_minimum_evidence():
    idx = {lab: i for i, lab in enumerate(["Rapping", "Hip hop music", "Speech", "Singing"])}
    import mvh.stages.instruments.vocab as V

    labels = list(dict.fromkeys(V.SINGING + V.SPEECH + V.RAP + V.HIPHOP_CONTEXT))
    idx = {lab: i for i, lab in enumerate(labels)}
    lead = np.zeros((3, len(labels)))
    lead[:, idx["Rapping"]] = 0.01  # tag noise on a synth lead
    s = F.vocal_style_shares(lead, np.zeros_like(lead), idx)
    assert np.allclose(s, 0.0)
