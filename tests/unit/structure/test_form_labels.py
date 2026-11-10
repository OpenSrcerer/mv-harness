"""F-form (ffix-form): a 'chorus' label needs repetition evidence; hook stretches are chorus; the coda / bridge form slots.
Fast: ``_chorus_evidence`` on hand-made similarity matrices and allin1 probabilities (no audio)."""
from __future__ import annotations

import numpy as np

from mvh.stages.structure import STAGE, _chorus_evidence, _n_runs


def _run(groups, labels, probs, sims, dur=None, sil=None):
    n = len(labels)
    reps: list[list[int]] = []
    for g in sorted(set(groups)):
        reps.append([i for i in range(n) if groups[i] == g])
    group_of = [sorted(set(groups)).index(g) for g in groups]
    letter = {k: chr(65 + k) for k in range(len(reps))}
    labels = list(labels)
    confs = [0.5] * n
    S = np.asarray(sims, float)
    notes: list[str] = []
    ev = _chorus_evidence(dict(STAGE.params), n, reps, group_of, sil or [False] * n, probs, S, labels, confs,
                          dur or [10.0] * n, lambda i, j: float(S[i, j]), notes, [10.0 * i for i in range(n)], letter)
    return labels, confs, ev


def _sims(n, pairs, base=0.2):
    S = np.full((n, n), base)
    np.fill_diagonal(S, 1.0)
    for (i, j), v in pairs.items():
        S[i, j] = S[j, i] = v
    return S


def P(v, c, **kw):
    return {"verse": v, "chorus": c, **kw}


def test_runs_count_separate_occurrences():
    assert _n_runs([2, 3, 4, 5], [False] * 8) == 1
    assert _n_runs([2, 4], [False] * 8) == 2
    assert _n_runs([2, 4], [False, False, False, True, False]) == 1      # only a silence between them


def test_rap_loop_group_is_not_a_chorus():
    # Newton-like: one group (the beat loop) is most of the song and allin1 is split between verse and chorus
    groups = ["A", "B", "C", "B", "B", "D", "B", "B", "B", "E"]
    labels = ["verse", "chorus", "verse", "chorus", "chorus", "verse", "chorus", "chorus", "chorus", "outro"]
    probs = [P(.8, .1), P(.55, .42), P(.84, .15), P(.28, .71), P(.85, .08), P(.6, .3), P(.43, .47), P(.57, .23), P(.06, .82),
             {"outro": .9}]
    B = [1, 3, 4, 6, 7, 8]
    S = _sims(10, {(a, b): 0.85 for a in B for b in B if a < b})
    lab, conf, ev = _run(groups, labels, probs, S)
    assert "chorus" not in lab, lab
    assert all(lab[i] == "verse" for i in B)
    assert "no repetition evidence" in ev[1][0] and conf[4] == 0.85


def test_recurring_refrain_keeps_chorus():
    groups = ["A", "B", "C", "B", "C", "D"]
    labels = ["intro", "verse", "chorus", "verse", "chorus", "outro"]
    probs = [{"intro": .9}, P(.9, .05), P(.1, .85), P(.8, .1), P(.05, .9), {"outro": .9}]
    S = _sims(6, {(1, 3): .8, (2, 4): .8})
    lab, _, ev = _run(groups, labels, probs, S)
    assert lab == labels and ev[2][0].startswith("chorus: recurring refrain")


def test_single_vamp_after_the_last_chorus_is_the_coda_and_near_repeat_is_kept():
    # chorus C recurs (2, 4); 5 is a lone chorus variant like C; 6-7 one vamp the model calls chorus; 8 outro
    groups = ["A", "B", "C", "B", "C", "E", "F", "F", "G"]
    labels = ["intro", "verse", "chorus", "verse", "chorus", "chorus", "chorus", "chorus", "outro"]
    probs = [{"intro": .9}, P(.9, .05), P(.1, .85), P(.8, .1), P(.05, .9), P(.35, .55), P(.2, .5, bridge=.25), P(.1, .6, bridge=.2),
             {"outro": .9}]
    S = _sims(9, {(1, 3): .8, (2, 4): .8, (5, 2): .6, (5, 4): .6, (6, 7): .7})
    lab, _, ev = _run(groups, labels, probs, S)
    assert lab[5] == "chorus" and "near-repeat" in ev[5][0]
    assert lab[6] == lab[7] == "outro", lab


def test_lone_part_between_two_choruses_is_the_bridge():
    groups = ["A", "B", "C", "D", "C", "E"]
    labels = ["intro", "verse", "chorus", "chorus", "chorus", "outro"]
    probs = [{"intro": .9}, P(.9, .05), P(.1, .85), P(.2, .7, bridge=.1), P(.05, .9), {"outro": .9}]
    lab, _, _ = _run(groups, labels, probs, _sims(6, {(2, 4): .8}))
    assert lab[3] == "bridge"


def test_hook_stretch_next_to_a_chorus_is_chorus_but_not_the_verse_leading_in():
    # 5 sits right before chorus occurrence 6 (not the first) and repeats C: the hook; 1 is the verse into the
    # FIRST chorus and stays verse however alike
    groups = ["A", "B", "C", "B", "C", "E", "C", "F"]
    labels = ["intro", "verse", "chorus", "verse", "chorus", "verse", "chorus", "outro"]
    probs = [{"intro": .9}, P(.9, .05), P(.1, .85), P(.8, .1), P(.05, .9), P(.45, .1), P(.1, .8), {"outro": .9}]
    S = _sims(8, {(1, 3): .8, (2, 4): .7, (2, 6): .7, (4, 6): .7, (5, 2): .5, (5, 4): .5, (5, 6): .5, (1, 2): .65})
    lab, _, ev = _run(groups, labels, probs, S)
    assert lab[5] == "chorus" and "hook stretch" in ev[5][0]
    assert lab[1] == "verse" and lab[3] == "verse"


def test_hook_rule_needs_the_chorus_to_be_closer_than_the_verse():
    groups = ["A", "B", "C", "B", "C", "E", "C", "F"]
    labels = ["intro", "verse", "chorus", "verse", "chorus", "verse", "chorus", "outro"]
    probs = [{"intro": .9}, P(.9, .05), P(.1, .85), P(.8, .1), P(.05, .9), P(.6, .1), P(.1, .8), {"outro": .9}]
    S = _sims(8, {(1, 3): .8, (2, 4): .7, (2, 6): .7, (4, 6): .7, (5, 2): .5, (5, 4): .5, (5, 6): .5, (5, 1): .5, (5, 3): .5})
    lab, _, _ = _run(groups, labels, probs, S)
    assert lab[5] == "verse"
