"""``mvh frames <song folder> --fps 24 [--fps 30000/1001] [--frame0 1] [--early] [--curves a,b] [--events ...]``
(D35 module verb, D19 on-demand stage).

Runs the ``frames`` stage on an analysed song folder (``mvh analyze <folder> --only frames`` with these params) and
prints the written CSV paths. Earlier exports are kept: the new rates are added to the ones recorded for the folder
(``--replace`` starts over), so ``24fps.csv`` survives a later ``--fps 30``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

__all__ = ["register", "cmd_frames"]


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("frames", help="export frames/<fps>fps.csv (one row per video frame) for a song folder")
    p.add_argument("folder", help="song folder (out/<slug>) made by mvh analyze")
    p.add_argument("--fps", action="append", required=True,
                   help="24, 23.976 (literal), 24000/1001 (NTSC); repeat for several exports")
    p.add_argument("--frame0", type=int, default=0, help="number of the first frame (Blender: 1)")
    p.add_argument("--early", action="store_true", help="frame n covers [t_n, t_n + 1/F) instead of the centred window")
    p.add_argument("--curves", default="", help="comma-separated channel ids or patterns ('*' = all, 'drums.*', "
                   "'spectrum128'); default: the video set")
    p.add_argument("--events", default="default", help="'default', 'none' or comma-separated event columns")
    p.add_argument("--format", choices=("csv", "deforum"), default="csv")
    p.add_argument("--replace", action="store_true", help="forget the exports made before")
    p.add_argument("--threads", type=int, default=None)
    p.set_defaults(func=cmd_frames)


def cmd_frames(a: argparse.Namespace) -> int:
    from mvh.runner import run as rr

    folder = Path(a.folder)
    prev = rr.load_run_settings(folder)
    if not prev.get("params_ext", {}).get("input"):
        print(f"mvh frames: {folder} is not a song folder made by mvh analyze", file=sys.stderr)
        return 2
    cli_params = {k: dict(v) for k, v in (prev.get("cli_params") or {}).items()}
    old = cli_params.get("frames") or {}
    rules = [] if a.replace else list(old.get("fps") if isinstance(old.get("fps"), list) else [])
    for f in a.fps:
        r = {"fps": f.strip(), "frame0": a.frame0, "early": bool(a.early)}
        if r not in rules:
            rules.append(r)
    curves = [c.strip() for c in a.curves.split(",") if c.strip()]
    events = "default" if a.events == "default" else ([] if a.events == "none" else
                                                        [e.strip() for e in a.events.split(",") if e.strip()])
    cli_params["frames"] = {"fps": rules, "curves": curves, "events": events, "format": a.format}
    s = rr.Settings(
        song=None, song_dir=folder.resolve(), slug=prev.get("slug") or folder.name,
        profile=prev.get("profile", "max"), threads=a.threads or rr._env_threads(), only=("frames",),
        offline=True, heavy_locks=os.environ.get("MVH_HEAVY_LOCKS", "1") != "0",
        params_ext=dict(prev.get("params_ext", {})), cli_params=cli_params,
    )
    res = rr.analyze(s)
    out = sorted(str(p) for p in (folder / "frames").glob("*fps.*")) if (folder / "frames").is_dir() else []
    report: dict = {"frames": out, "warnings": res.get("warnings", []), "failed": res.get("failed")}
    # an earlier export may still be on disk while this run left the stage pending (stale/failed upstream)
    blocked = _not_run_reason(rr, folder)
    if blocked:
        # on-demand stages are left out of run.json when they did not run: say why here instead of exiting silently
        report["not_run"] = blocked
        print(f"mvh frames: frames did not run: {blocked}. Run `mvh analyze` on the folder first.", file=sys.stderr)
    print(json.dumps(report, ensure_ascii=False))
    return 1 if (res.get("failed") or blocked) else 0


def _not_run_reason(rr, folder: Path) -> str | None:
    """Why the frames stage produced nothing (its upstream is not cached / is stale), or None when it ran."""
    try:
        states = rr.status(folder)
    except Exception as e:  # noqa: BLE001 - only a diagnostic
        return f"status unavailable ({type(e).__name__})"
    ok = ("done", "degraded", "skipped")
    st = states.get("frames")
    if st is not None and st.status in ok:
        return None
    from mvh.stages.frames import STAGE

    bad = [f"{d} ({states[d].status})" for d in STAGE.deps if d in states and states[d].status not in ok]
    if bad:
        return "upstream not done: " + ", ".join(bad)
    return (st.reason if st is not None and st.reason else "frames is not done") if st is not None else "unknown stage"
