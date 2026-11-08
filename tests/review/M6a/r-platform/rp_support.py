# ruff: noqa: E501  (long lines)
"""R-PLATFORM review helpers for M6a: build a served song folder from the synthetic fixture with the REAL viewer stage,
start ``mvh view``'s server, and drive the page in a real headless browser (cdp_viewer.mjs).

Self-contained on purpose (does not import the builder's test helpers).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SYNTH = ROOT / "tests" / "contract" / "synth"
SKIP = {"_intermediate", "_truth", ".cache", ".done.json", "viewer.html", "frames", "overrides.json"}


def find_browser() -> str | None:
    for p in (
        os.environ.get("MVH_REVIEW_BROWSER"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    ):
        if p and Path(p).is_file():
            return p
    return None


def find_node() -> str | None:
    p = shutil.which("node")
    if p:
        return p
    q = Path(r"C:\Program Files\nodejs\node.exe")
    return str(q) if q.is_file() else None


class _Up:
    """The slice of the runner's CacheUpstream the viewer stage reads, backed by a fixture folder."""

    def __init__(self, root: Path, exclude: tuple[str, ...]):
        self.root = root
        outs: dict[str, dict] = {}
        for p in sorted(root.glob("events/*.json")) + sorted(root.glob("lipsync/*.json")):
            outs[p.relative_to(root).as_posix()] = {"kind": "events", "public": True, "events": p.stem}
        for p in sorted((root / "meta").glob("*.json")):
            outs[f"meta/{p.name}"] = {"kind": "json", "public": True}
        for rel in ("lyrics/lyrics.json", "meaning/meaning.json"):
            if (root / rel).is_file():
                outs[rel] = {"kind": "json", "public": True}
        for p in sorted((root / "stems").glob("*.flac")):
            outs[f"stems/{p.name}"] = {"kind": "audio", "public": True}
        outs["audio/mix.flac"] = {"kind": "audio", "public": True}
        outs["audio/preview.opus"] = {"kind": "audio", "public": True}
        self.record_outputs = {k: v for k, v in outs.items() if not any(k == x or k.startswith(x) for x in exclude)}
        self.index = json.loads((root / "curves" / "index.json").read_text(encoding="utf-8"))
        curves: dict[str, dict] = {}
        for c in self.index["channels"]:
            if c["file"] != "spectrum128":
                curves.setdefault(c["file"], {})[c["id"]] = {"n": c["n"]}
        self.record = {"outputs": self.record_outputs, "curves": curves, "matrices": {"spectrum128": {}}}

    def path(self, rel: str) -> Path:
        if rel not in self.record_outputs:
            raise FileNotFoundError(rel)
        return self.root / rel

    def exists(self, rel: str) -> bool:
        return rel in self.record_outputs

    def curve(self, cid: str):
        c = next(c for c in self.index["channels"] if c["id"] == cid)
        f = self.index["files"][c["file"]]
        v = np.fromfile(self.root / f["path"], dtype="<f4", count=c["n"], offset=c["offset_bytes"])
        meta = {k: x for k, x in c.items() if k not in ("offset_bytes", "n")}
        return SimpleNamespace(id=cid, values=v, rate_hz=float(c.get("rate_hz", f["rate_hz"])), meta=meta)

    def matrix(self, fid: str):
        f = self.index["files"][fid]
        a = np.fromfile(self.root / f["path"], dtype=np.uint8).reshape(f["n_frames"], f["n_channels"])
        return a, {"shape": list(a.shape), "dtype": "u8"}


def build_viewer_html(exclude: tuple[str, ...] = (), root: Path = SYNTH) -> str:
    from mvh.io import audio as aio
    from mvh.stages.viewer import STAGE, run

    up = _Up(root, exclude)
    files: dict[str, str] = {}
    writer = SimpleNamespace(text=lambda rel, text: files.__setitem__(rel, text))

    def audio(name="mix", *, sr=None, mono=False):
        d = aio.decode(root / "audio" / "mix.flac", mono=mono)
        return SimpleNamespace(samples=d.samples, sr=d.sr)

    ctx = SimpleNamespace(spec=STAGE, params=STAGE.resolved_params("max", {}), slug="synth", profile="max", writer=writer,
                          log=logging.getLogger("rp"), upstream=lambda dep: up, audio=audio)
    run(ctx)
    return files["viewer.html"]


def _link_tree(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for p in sorted(src.iterdir()):
        if p.name in SKIP:
            continue
        q = dst / p.name
        if p.is_dir():
            _link_tree(p, q)
        elif not q.exists():
            try:
                os.link(p, q)
            except OSError:
                shutil.copy2(p, q)


def build_song_folder(dest: Path, exclude: tuple[str, ...] = ()) -> Path:
    """A song folder like `mvh analyze` publishes (fixture files + real viewer.html + lib/mvh.js); ``exclude`` files are
    absent from the folder, its manifest and the viewer bundle, as when a stage did not produce them."""
    _link_tree(SYNTH, dest)
    (dest / "lib").mkdir(exist_ok=True)
    shutil.copyfile(ROOT / "src" / "mvh" / "assets" / "mvh.js", dest / "lib" / "mvh.js")
    for rel in exclude:
        p = dest / rel
        if p.is_file():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(p)
    mp = dest / "manifest.json"
    if mp.is_file():
        m = json.loads(mp.read_text(encoding="utf-8"))
        m["files"] = [f for f in m.get("files", []) if not any(f.get("path") == x or f.get("path", "").startswith(x) for x in exclude)]
        tmp = dest / "manifest.json.tmp"
        tmp.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        os.replace(tmp, mp)  # replace the hard link, never write through it into the fixture
    (dest / "viewer.html").write_text(build_viewer_html(exclude), encoding="utf-8", newline="\n")
    return dest


def drive(url: str, scenario: str, profile: Path, timeout: float = 120.0) -> dict:
    node, browser = find_node(), find_browser()
    assert node and browser
    profile = Path(profile).resolve()
    profile.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([node, str(HERE / "cdp_viewer.mjs"), browser, str(profile), url, scenario], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=timeout)
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith("{")]
    assert lines, f"cdp harness printed nothing: rc={r.returncode} {r.stderr[-800:]}"
    res = json.loads(lines[-1])
    assert "harnessError" not in res, res["harnessError"]
    return res
