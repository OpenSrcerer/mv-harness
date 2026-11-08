# ruff: noqa: E501  (long lines)
"""viewer stage (contract v1, owner M6a): ``viewer.html``, the one-page song viewer (PLAN §9).

``viewer.html`` is a single self-contained file: styles, the viewer script, an inline copy of ``lib/mvh.js`` (loaded
through a Blob URL, because ES-module imports do not work from ``file://``) and a size-capped data bundle (events,
meta, lyrics, meaning, the curve channels the lanes draw, the spectrogram, a waveform base and, when small, the
opus preview).  Opened from the disk it is read-only and shows everything.  Served by ``mvh view <song>``
(``cli.py``, ``server.py``) it loads the song folder through ``fetch`` and switches on EDIT MODE: corrections are
POSTed to ``overrides.json`` (and the singer / meaning notes to a managed block in ``meaning/intent.md``).

Deps, env and the catalogue output are FROZEN by docs/CONTRACT.md. Decisions: docs/contract/decisions/M6a.md.
"""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from typing import Any

from mvh.contract.stages import ANALYSIS_STAGES
from mvh.runner.spec import StageResult, StageSpec, catalog_outputs

ASSET_DIR = Path(__file__).resolve().parents[2] / "assets" / "viewer"
LIB_JS = Path(__file__).resolve().parents[2] / "assets" / "mvh.js"
#: concatenation order of the viewer scripts
SCRIPTS = ("logic.js", "util.js", "data.js", "audio.js", "view.js", "lanes.js", "panels.js", "edit.js", "main.js")
#: placeholder the edit-mode server replaces with the session token script (the comment is inert in file://)
EDIT_MARK = "<!--MVH-EDIT-->"


def _assets_digest() -> str:
    h = hashlib.sha256()
    for p in [ASSET_DIR / "template.html", ASSET_DIR / "viewer.css", *(ASSET_DIR / s for s in SCRIPTS), LIB_JS]:
        try:
            h.update(p.name.encode())
            h.update(p.read_bytes())
        except OSError:
            h.update(b"-")
    return h.hexdigest()[:16]


STAGE = StageSpec(
    "viewer",
    ANALYSIS_STAGES,
    "main",
    "1.0.0",
    override_keys=(),
    outputs=catalog_outputs("viewer"),
    params={
        "inline_cap_mb": 28.0,         # target size of the inlined data bundle (base64, compressed)
        "inline_audio_max_mb": 8.0,    # inline audio/preview.opus only when it is at most this big
        "inline_spectrogram": True,    # inline curves/spectrum128.u8 when it fits the cap
        "inline_lyrics": True,         # False: lyric text is not written into viewer.html (served mode still shows it)
        "waveform_hz": 1000,           # base resolution of the inlined min/max waveform
        "assets": _assets_digest(),    # viewer sources are part of the cache key
    },
    module="M6a",
    description="viewer.html with inlined preview data (read-only from file://; edit mode under mvh view).",
)


def _read_asset(name: str) -> str:
    return (ASSET_DIR / name).read_text(encoding="utf-8")


def assemble_html(data: dict[str, Any], title: str) -> str:
    """Fill the template. ``data`` is the JSON bundle (see build_data)."""
    tpl = _read_asset("template.html")
    css = _read_asset("viewer.css")
    js = "\n".join(_read_asset(s) for s in SCRIPTS)
    lib = LIB_JS.read_text(encoding="utf-8")
    if "</script" in lib.lower() or "</script" in js.lower():
        raise ValueError("a script contains '</script'")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False).replace("</", "<\\/")
    out = tpl
    for k, v in (
        ("@@TITLE@@", html.escape(title)),
        ("/*@@CSS@@*/", css),
        ("@@MVHJS@@", lib),
        ("@@DATA@@", payload),
        ("/*@@JS@@*/", js),
    ):
        if k not in out:
            raise ValueError(f"template misses {k}")
        out = out.replace(k, v, 1) if k != "@@TITLE@@" else out.replace(k, v)
    return out


def run(ctx) -> StageResult:
    from . import bundle as bd
    from .data import build_data

    res = build_data(ctx, bd)
    title = res["title"]
    page = assemble_html(res["data"], title)
    ctx.writer.text("viewer.html", page)
    sizes = res["sizes"]
    return StageResult(
        status="ok",
        summary={
            "html_bytes": len(page.encode("utf-8")),
            "inline_bytes": sizes["total"],
            "inlined": res["inlined"],
            "lanes_without_data": res["missing"],
        },
        warnings=res["warnings"],
        fallbacks=res["fallbacks"],
        provenance={
            "tools": [{"name": "mvh-viewer", "version": STAGE.version}],
            "notes": [f"inlined {len(res['inlined'])} data items ({sizes['total']} bytes encoded)"],
            "overrides_applied": [],
        },
        confidence=1.0 if not res["missing"] else round(1.0 - min(0.5, 0.05 * len(res["missing"])), 2),
    )
