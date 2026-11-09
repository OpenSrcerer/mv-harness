"""Regenerate tests/fixtures/http/lrclib_synth.json from the synthetic song (invented lyrics only).

    uv run --frozen --no-sync python -m tests.synth.m5.make_http_fixtures

The synthetic LRCLIB pool for "Lanterns on the Tide" (56.5 s) reproduces the real-world traps of W0:
* ``/api/get`` answers a near miss (id 900001, 59.0 s, synced): Jeremy's case;
* search also has an exact-duration PLAIN-only entry (900002, +0.1 s) and a SYNCED entry (900003, -0.1 s) whose
  line times are 1.3 s late (another version's lead-in): newton's case -> the ranking must pick 900003 and the
  alignment must detect an offset of about -1.3 s;
* a false friend with a different artist (900004).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FX = REPO / "tests" / "contract" / "synth"
OUT = REPO / "tests" / "fixtures" / "http" / "lrclib_synth.json"
TITLE, ARTIST, ALBUM, DUR = "Lanterns on the Tide", "mv-harness fixture", "Synthetic Sessions", 56.5
SHIFT = 1.3


def _lines() -> list[tuple[float, str]]:
    out = []
    with open(FX / "_truth" / "lyrics_input.lrc", encoding="utf-8") as fh:
        for ln in fh:
            m = re.match(r"^\[(\d+):(\d+\.\d+)\]\s*(.*)$", ln.strip())
            if m:
                text = re.sub(r"<[^>]+>", "", m.group(3)).split()
                out.append((int(m.group(1)) * 60 + float(m.group(2)), " ".join(text)))
    return out


def _lrc(lines, shift: float) -> str:
    rows = []
    for t, txt in lines:
        t += shift
        rows.append(f"[{int(t // 60):02d}:{t % 60:05.2f}] {txt}")
    return "\n".join(rows) + "\n"


def entry(i: int, dur: float, synced: bool, plain: bool = True, shift: float = 0.0, title: str = TITLE, artist: str = ARTIST) -> dict:
    lines = _lines()
    return {"id": i, "name": title, "trackName": title, "artistName": artist, "albumName": ALBUM, "duration": dur,
            "instrumental": False, "hasWordSync": False, "lyricsfile": None,
            "plainLyrics": "\n".join(t for _, t in lines) if plain else None,
            "syncedLyrics": _lrc(lines, shift) if synced else None}


def build() -> dict:
    d = int(round(DUR))
    base = "https://lrclib.net/api/"
    near = entry(900001, 59.0, True)
    search = [near, entry(900002, 56.6, False), entry(900003, 56.4, True, shift=SHIFT), entry(900004, 56.5, True, title="Lanterns", artist="Somebody Else")]
    reqs = [
        {"method": "GET", "url": base + "get", "params": {"track_name": TITLE, "artist_name": ARTIST, "album_name": ALBUM, "duration": d}, "status": 200, "body": near},
        {"method": "GET", "url": base + "get", "params": {"track_name": TITLE, "artist_name": ARTIST, "duration": d}, "status": 200, "body": near},
        {"method": "GET", "url": base + "search", "params": {"track_name": TITLE, "artist_name": ARTIST}, "status": 200, "body": search},
        {"method": "GET", "url": base + "search", "params": {"q": f"{TITLE} {ARTIST}"}, "status": 200, "body": search[1:]},
    ]
    return {"description": "SYNTHETIC LRCLIB responses for the synthetic song (invented lyrics; see tests/synth/m5/make_http_fixtures.py)",
            "shift_s": SHIFT, "expected_choice": 900003, "requests": reqs}


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(build(), fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"wrote {OUT.relative_to(REPO)}")
