"""R-ML review M3a round 4, finding R4-2: the Mel-RoFormer vocals and the karaoke split are not bit-reproducible on
ROCm, so the D47 claim ("the RoFormer steps have no convolutions and stay on the GPU, bit-identical under memory
pressure") does not hold, and NF1 (two ``analyze --force`` runs give identical files) still fails, now on the vocal stems.

D47 moved only DrumSep to the CPU; the integrator's experiment (drumsep_det.py) measured only DrumSep. Two
``separate_hq`` runs of newton-vs-nye with identical code, params, models and devices
(``worker.devices`` = sw_6stem/mel_vocals/karaoke on cuda, drumsep on cpu; other agents were using the GPU during the
second run): the BS-RoFormer-SW stems (drums, bass, other) and the CPU DrumSep sub-stems are byte-identical, but
``vocals.wav`` differs in 87 % of the samples (max 4e-7, -134 dB), ``instrumental.wav`` (= mix - vocals) likewise, and
the karaoke model amplifies it: ``lead_vocals.wav`` max 1.6e-3 (-75 dB), ``backing_vocals.flac`` -52 dB. Every stage
that reads vocals, lead or backing (stem_activity, vocals, lyrics alignment, voices, lipsync, the viewer, the manifest)
follows.

Round 5 (r-ml-m3a-r5): the two round-4 folders were both made by the OLD code, so comparing them could never pass
after a fix. The test now compares two runs of the CURRENT code: run A = ``--only
separate_fast,separate_hq,stem_activity,drums --force`` on a copy of the integrator's folder
(out/_wip/r-ml-m3a-r5/detA/<slug>), run B = the same with another process holding 80 % of the free GPU memory and
running matmuls throughout (out/_wip/r-ml-m3a-r5/detB/<slug>). Round 5 result on newton-vs-nye: every stem byte-identical
(the fix in mvh.sep.determinism works). Override the two roots with MVH_REVIEW_M3A_DET_A / _B.
Skips when either folder is absent. Fast (reads WAVs).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
_R5 = REPO / "out" / "_wip" / "r-ml-m3a-r5"
RUN_A = Path(os.environ.get("MVH_REVIEW_M3A_DET_A") or _R5 / "detA")
RUN_B = Path(os.environ.get("MVH_REVIEW_M3A_DET_B") or _R5 / "detB")


def _song(root: Path, slug: str) -> Path:
    """``root/<slug>`` when it exists; the round-5 folders hold newton-vs-nye directly (``root`` itself)."""
    if (root / slug).is_dir():
        return root / slug
    return root if slug == "newton-vs-nye" and (root / "meta" / "separation.json").is_file() else root / slug


HQ_STEMS = ("stems/vocals.wav", "stems/instrumental.wav", "stems/lead_vocals.wav", "stems/backing_vocals.flac",
            "stems/drums.wav", "stems/bass.flac", "stems/other.flac")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _worker(folder: Path) -> dict:
    with open(folder / "meta" / "separation.json", encoding="utf-8") as fh:
        w = json.load(fh).get("worker", {})
    return {"devices": w.get("devices"), "settings": w.get("settings")}


@pytest.mark.parametrize("slug", ["newton-vs-nye", "versatile"])
def test_separate_hq_stems_are_bit_reproducible(slug):
    a, b = _song(RUN_A, slug), _song(RUN_B, slug)
    if not (a / "meta" / "separation.json").is_file() or not (b / "meta" / "separation.json").is_file():
        pytest.skip(f"need two separate_hq runs of {slug}: {a} and {b}")
    wa, wb = _worker(a), _worker(b)
    assert wa == wb, f"the two runs used different worker settings/devices: {wa} vs {wb}"
    differ = []
    for rel in HQ_STEMS:
        pa, pb = a / rel, b / rel
        if pa.is_file() and pb.is_file() and _sha(pa) != _sha(pb):
            differ.append(rel)
    if differ:
        import numpy as np

        from mvh.io import audio as aio
        from mvh.io.wav import read_wav

        detail = []
        for rel in differ:
            if rel.endswith(".wav"):
                x, _ = read_wav(a / rel)
                y, _ = read_wav(b / rel)
            else:
                x, y = aio.decode(a / rel).samples, aio.decode(b / rel).samples
            d = np.asarray(x, np.float64) - np.asarray(y, np.float64)
            res = 10 * np.log10(np.sum(d ** 2) / max(float(np.sum(np.asarray(x, np.float64) ** 2)), 1e-30) + 1e-30)
            detail.append(f"{rel}: max|d| {np.abs(d).max():.2g}, residual {res:.0f} dB, {np.count_nonzero(d) / d.size:.0%} of samples")
        pytest.fail(f"{slug}: two separate_hq runs with identical settings and devices {wa['devices']} differ (NF1): "
                    + "; ".join(detail))
