"""fverify F-V1 (major, CR-F-gain-1 not applied): the gain fix changed what the separate_hq worker computes (DrumSep now
runs on the drum stem scaled to the -10 LUFS analysis level, hq_worker param ``drumsep_analysis_lufs``) but the
separate_hq stage version is still 1.0.0. The runner's cache key has no code hash, so every existing song folder (the
user's out/<song>, the integrator's real-song folders) keeps its master-level DrumSep sub-stems on a re-run; only a
``--force separate_hq`` picks the fix up. drums 1.4.0 then reads stems the fix did not produce."""

from __future__ import annotations

import inspect

from mvh.sep import hq_worker
from mvh.stages.separate_hq import STAGE


def test_separate_hq_version_moves_with_the_drumsep_analysis_level():
    src = inspect.getsource(hq_worker)
    assert "drumsep_analysis_lufs" in src  # the behaviour change is in the worker
    assert STAGE.version != "1.0.0", (
        "separate_hq is still 1.0.0 although the worker now runs DrumSep at the analysis level (F-gain-1): cached "
        "folders keep master-level DrumSep sub-stems unless --force separate_hq (CR-F-gain-1)"
    )
