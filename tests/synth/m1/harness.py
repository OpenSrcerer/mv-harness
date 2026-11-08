# ruff: noqa: E501  (long formulas, tables and docstrings)
"""Run the three M1 stages in-process (FakeCtx) on one signal: spectral -> loudness -> dynamics.

    python -m tests.synth.m1.harness <canonical.wav | audio file> <bars.json | -> <out dir>

Used by the unit tests (synthetic signals) and by the real-song report (real-<slug> fixture bars as the rhythm input).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from mvh.stages import dynamics as dyn_pkg
from mvh.stages import loudness as loud_pkg
from mvh.stages import spectral as spec_pkg

from .fakectx import FakeCtx, write_audio_wav


def run_m1(samples: np.ndarray, sr: int, out: Path, *, bars: list[dict[str, Any]] | None = None,
           audio_path: Path | None = None, params: dict[str, dict[str, Any]] | None = None,
           stages: tuple[str, ...] = ("spectral", "loudness", "dynamics")) -> dict[str, Any]:
    out = Path(out)
    params = params or {}
    x = np.asarray(samples, dtype=np.float32)
    if x.ndim == 1:
        x = x[None, :]
    if audio_path is None:
        audio_path = write_audio_wav(out / "_mix.wav", x, sr)
    res: dict[str, Any] = {"timings": {}}
    ctxs: dict[str, FakeCtx] = {}
    t0 = time.perf_counter()
    sp = FakeCtx(spec_pkg.STAGE, out / "spectral", samples=x, sr=sr, audio_path=audio_path, params=params.get("spectral"))
    res["spectral"] = spec_pkg.run(sp)
    res["timings"]["spectral"] = time.perf_counter() - t0
    ctxs["spectral"] = sp
    if "loudness" in stages or "dynamics" in stages:
        t0 = time.perf_counter()
        ld = FakeCtx(loud_pkg.STAGE, out / "loudness", samples=x, sr=sr, audio_path=audio_path, params=params.get("loudness"))
        res["loudness"] = loud_pkg.run(ld)
        res["timings"]["loudness"] = time.perf_counter() - t0
        ctxs["loudness"] = ld
    if "dynamics" in stages:
        t0 = time.perf_counter()
        curves = {**sp.written_curves(), **ld.written_curves()}
        evs = {n: sp.written_events(n)["items"] for n in ("hits.kick", "hits.mid", "hits.high", "onsets.bass",
                                                           "onsets.mid", "onsets.high")}
        evs["bars"] = list(bars or [])
        dy = FakeCtx(dyn_pkg.STAGE, out / "dynamics", samples=x, sr=sr, audio_path=audio_path, curves=curves,
                     events=evs, docs={"loudness": {"meta/loudness.json": ld.written_json("meta/loudness.json")}},
                     params=params.get("dynamics"))
        res["dynamics"] = dyn_pkg.run(dy)
        res["timings"]["dynamics"] = time.perf_counter() - t0
        ctxs["dynamics"] = dy
    res["ctx"] = ctxs
    return res


def main(argv: list[str]) -> int:
    from mvh.io import audio as aio

    src, bars_p, out = Path(argv[0]), argv[1], Path(argv[2])
    d = aio.decode(src)
    bars = []
    if bars_p != "-":
        with open(bars_p, encoding="utf-8") as fh:
            bars = json.load(fh)["items"]
    path = src if src.suffix.lower() == ".wav" else None
    r = run_m1(d.samples, d.sr, out, bars=bars, audio_path=path)
    print(json.dumps({k: (v.summary if hasattr(v, "summary") else v) for k, v in r.items() if k != "ctx"}, indent=1,
                     default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
