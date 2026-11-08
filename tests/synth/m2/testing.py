# ruff: noqa: E501
"""Shared pytest helpers for the M2 unit tests (tests/unit/{allin1,rhythm,structure,choreo,cues})."""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[3]
SYNTH = REPO / "tests" / "contract" / "synth"
REAL_SLUGS = ("megafauna", "versatile", "jeremy", "newton-vs-nye")


def configure(config) -> None:
    config.addinivalue_line("markers", "real: reads the real-song contract fixtures (opt-in: -m real or MVH_REAL_TESTS=1)")
    config.addinivalue_line("markers", "slow: runs real model inference on synthetic audio (opt-in: -m slow or MVH_SLOW_TESTS=1)")


def skip_optin(config, items) -> None:
    sel = config.getoption("-m") or ""
    for mark, env in (("real", "MVH_REAL_TESTS"), ("slow", "MVH_SLOW_TESTS")):
        if os.environ.get(env) == "1" or mark in sel:
            continue
        skip = pytest.mark.skip(reason=f"{mark} test: run with -m {mark} or {env}=1")
        for it in items:
            if mark in it.keywords:
                it.add_marker(skip)


def synth_ready() -> Path:
    if not (SYNTH / ".done.json").exists():
        from tests.synth.build import build_synth

        build_synth(SYNTH, log=lambda *a: None)
    return SYNTH


def truth() -> dict:
    with open(synth_ready() / "_truth" / "truth.json", encoding="utf-8") as fh:
        return json.load(fh)


def audio_fixture(root: Path, x: np.ndarray, sr: int) -> Path:
    """A minimal fixture folder holding only the canonical mix (ingest) and meta/source.json; every other upstream
    is absent, so stages run their fallbacks."""
    from mvh.io.wav import write_wav

    root = Path(root)
    a = np.asarray(x, np.float32)
    if a.ndim == 1:
        a = np.stack([a, a])
    (root / "_intermediate" / "ingest").mkdir(parents=True, exist_ok=True)
    write_wav(root / "_intermediate" / "ingest" / "canonical.wav", a, sr)
    (root / "meta").mkdir(parents=True, exist_ok=True)
    with open(root / "meta" / "source.json", "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"n_samples": int(a.shape[1]), "sample_rate": int(sr), "duration_s": a.shape[1] / sr}, fh)
    return root


def events(out: Path, name: str) -> list[dict]:
    from mvh.contract import catalog

    ed = catalog.event_def(name)
    with open(Path(out) / ed.file, encoding="utf-8") as fh:
        return json.load(fh)["items"]


def doc(out: Path, rel: str) -> dict:
    with open(Path(out) / rel, encoding="utf-8") as fh:
        return json.load(fh)


def validate_all(out: Path) -> list[str]:
    """Schema-validate every JSON the stage wrote (events envelopes and documents)."""
    from mvh.contract import schemas

    errs: list[str] = []
    for p in Path(out).rglob("*.json"):
        if p.name.startswith("_m2_") or "_mvh" in p.parts:
            continue
        with open(p, encoding="utf-8") as fh:
            obj = json.load(fh)
        sch = obj.get("schema") if isinstance(obj, dict) else None
        if not sch:
            continue
        for e in schemas.validate(obj, sch):
            errs.append(f"{p.name}: {e}")
    return errs
