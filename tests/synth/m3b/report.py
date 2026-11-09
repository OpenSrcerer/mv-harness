"""Print a compact summary of the M3b outputs of a song folder (no lyric text). Owner builder-m3b.

    uv run --frozen --no-sync python -m tests.synth.m3b.report out/_wip/builder-m3b/<slug> [...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _j(p: Path):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def report(d: Path) -> None:
    print(f"## {d.name}")
    if (d / "meta/instruments.json").exists():
        m = _j(d / "meta/instruments.json")
        print("  instruments:", ", ".join(f"{r['instrument']} {r['coverage']:.2f}/{r['mean_conf']:.2f}" for r in m["summary"]))
        print("  vocal_style:", m["vocal_style"])
        print("  top_tags:", ", ".join(f"{t['label']} {t['p']:.2f}" for t in m.get("top_tags", [])[:6]))
        ev = _j(d / "events/vocal_style.json")["items"]
        print("  style segs:", [(round(i["t"], 1), round(i["d"], 1), i["style"], i["conf"]) for i in ev][:12])
        ev = _j(d / "events/instruments.json")["items"]
        voice = [(round(i["t"], 1), round(i["d"], 1), i["evidence"]) for i in ev if i["instrument"] == "voice"]
        print("  voice segs:", voice[:12])
    if (d / "notes/notes.json").exists():
        m = _j(d / "notes/notes.json")
        for k, v in m["sources"].items():
            print(f"  notes.{k}: n={v['count']} range={v['lowest']}-{v['highest']} dens={v['density_per_s']}")
    if (d / "meta/vocal_range.json").exists():
        m = _j(d / "meta/vocal_range.json")
        print("  vocal_range:", {k: m[k] for k in ("present", "voiced_s", "p2", "p98", "p10", "p90", "register", "conf")})
        print("  lowest/highest:", m["lowest"], m["highest"])
        print("  phrases:", len(_j(d / "events/vocal_phrases.json")["items"]),
              "vocal notes:", len(_j(d / "events/notes.vocals.json")["items"]))


if __name__ == "__main__":
    for a in sys.argv[1:]:
        report(Path(a))
