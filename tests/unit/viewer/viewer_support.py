"""Helpers for the viewer tests: a fake upstream that reads the synthetic song fixture (tests/contract/synth/)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
SYNTH = ROOT / "tests" / "contract" / "synth"


class FakeUpstream:
    """The slice of CacheUpstream the viewer stage uses, backed by a fixture folder."""

    def __init__(self, root: Path, exclude: tuple[str, ...] = ()):
        self.root = root
        self.stage = "fake"
        self.exclude = exclude
        outs: dict[str, dict] = {}
        for p in sorted(root.glob("events/*.json")) + sorted(root.glob("lipsync/*.json")):
            outs[p.relative_to(root).as_posix()] = {"kind": "events", "public": True, "events": p.stem}
        for rel in [*sorted(f"meta/{p.name}" for p in (root / "meta").glob("*.json")), "lyrics/lyrics.json", "meaning/meaning.json",
                    "meaning/orphans.json", "meaning/input.json"]:
            if (root / rel).is_file():
                outs[rel] = {"kind": "json", "public": True}
        for p in sorted((root / "stems").glob("*.flac")):
            outs[f"stems/{p.name}"] = {"kind": "audio", "public": True}
        outs["audio/mix.flac"] = {"kind": "audio", "public": True}
        outs["audio/preview.opus"] = {"kind": "audio", "public": True}
        for rel in list(outs):
            if any(rel.startswith(x) or rel == x for x in exclude):
                outs.pop(rel)
        idx = json.loads((root / "curves" / "index.json").read_text(encoding="utf-8"))
        self.index = idx
        curves: dict[str, dict] = {}
        for c in idx["channels"]:
            if c["file"] == "spectrum128":
                continue
            curves.setdefault(c["file"], {})[c["id"]] = {"n": c["n"]}
        self.record = {"outputs": outs, "curves": curves, "matrices": {"spectrum128": {}}}

    def path(self, rel: str) -> Path:
        p = self.root / rel
        if not p.is_file() or rel not in self.record["outputs"]:
            raise FileNotFoundError(rel)
        return p

    def exists(self, rel: str) -> bool:
        return rel in self.record["outputs"]

    def curve(self, cid: str):
        c = next(c for c in self.index["channels"] if c["id"] == cid)
        f = self.index["files"][c["file"]]
        v = np.fromfile(self.root / f["path"], dtype="<f4", count=c["n"], offset=c["offset_bytes"])
        meta = {k: v2 for k, v2 in c.items() if k not in ("offset_bytes", "n")}
        return SimpleNamespace(id=cid, values=v, rate_hz=float(c["rate_hz"] if "rate_hz" in c else f["rate_hz"]), meta=meta)

    def matrix(self, fid: str):
        f = self.index["files"][fid]
        a = np.fromfile(self.root / f["path"], dtype=np.uint8).reshape(f["n_frames"], f["n_channels"])
        return a, {"shape": list(a.shape), "dtype": "u8"}


class FakeWriter:
    def __init__(self):
        self.files: dict[str, str] = {}

    def text(self, rel: str, text: str):
        self.files[rel] = text


def make_ctx(params: dict | None = None, exclude: tuple[str, ...] = (), root: Path = SYNTH, slug: str = "synth"):
    from mvh.stages.viewer import STAGE

    up = FakeUpstream(root, exclude)
    p = STAGE.resolved_params("max", params or {})

    def audio(name="mix", *, sr=None, mono=False):
        from mvh.io import audio as aio

        d = aio.decode(root / "audio" / "mix.flac", mono=mono)
        return SimpleNamespace(samples=d.samples, sr=d.sr)

    ctx = SimpleNamespace(spec=STAGE, params=p, slug=slug, profile="max", writer=FakeWriter(), log=logging.getLogger("t"),
                          upstream=lambda dep: up, audio=audio)
    return ctx
