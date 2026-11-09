"""Seam S07 (M5, minor): Versatile is an instrumental (lyrics.instrumental = true, no voices, no lines), but
vocal.mouth_open opens for about 0.5 s on a vocal chop (lipsync:ungated_wordless). A character would mouth along to
an instrumental; the ungated fallback should not apply when lyrics says instrumental (or it should be a param)."""

from __future__ import annotations

import numpy as np


def test_real_versatile_mouth_stays_closed(real_song):
    from mvh.assets import mvh_load

    s = real_song("versatile")
    assert s.json("lyrics/lyrics.json")["instrumental"] is True
    v = np.asarray(mvh_load.load(str(s.folder)).curve("vocal.mouth_open").values)
    assert float(v.max()) < 0.1, f"{int((v > 0.1).sum())} frames open"
