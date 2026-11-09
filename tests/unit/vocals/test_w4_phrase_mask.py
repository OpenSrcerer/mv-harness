"""W4A-VOCPHR: inside a sparsely pitched lyric line the lead-stem energy is phrase material (processed / whispered voice)."""
from __future__ import annotations

import numpy as np

from mvh.stages.vocals.pitch import energy_phrase_mask, phrases


def test_sparse_pitch_line_takes_the_stem_energy():
    n = 1000
    voiced = np.zeros(n, bool)
    voiced[120:140] = True                       # 0.2 s of trusted pitch in a 3 s sung line
    energy = np.zeros(n, bool)
    energy[100:400] = True                       # the stem is active and loud over the whole line
    m, added = energy_phrase_mask(voiced, energy, [(100, 400)])
    assert added == 280 and m[100:400].all()
    ph = phrases(np.where(m, 0.0, np.nan))
    assert ph == [(100, 400)]


def test_well_pitched_line_is_unchanged_and_no_line_no_energy():
    n = 1000
    voiced = np.zeros(n, bool)
    voiced[100:350] = True
    energy = np.zeros(n, bool)
    energy[100:400] = True
    m, added = energy_phrase_mask(voiced, energy, [(100, 400)])
    assert added == 0 and (m == voiced).all()
    m, added = energy_phrase_mask(np.zeros(n, bool), energy, [])
    assert added == 0 and not m.any()            # stem energy outside any lyric line is not a phrase
