"""LRCLIB cascade (PLAN §5 lyrics 1.3, SPIKE ranking rule).

Requests, sequential and 0.4 s apart with the identifying User-Agent (Retry-After honoured by the client):
``/api/get`` with album and duration, ``/api/get`` without the album, and ALWAYS ``/api/search`` (track + artist,
then a free ``q`` query). ``/api/get-cached`` is never called.

Ranking: the title/artist gate (rapidfuzz token-set on parenthesis-free keys: title >= 90, artist >= 85), then
among the candidates within 2 s of the file prefer one with synced lyrics, then the smallest |Δdur| (newton:
the smallest-Δ entry is plain only). 2-5 s is accepted with a ``version_mismatch`` flag, > 5 s is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

__all__ = ["LRCLIB_ROOT", "Candidate", "query_lrclib", "rank", "choose", "candidate_source"]

LRCLIB_ROOT = "https://lrclib.net/api/"
USER_AGENT = "mv-harness/0.1 (https://github.com/OpenSrcerer/mv-harness)"
INTERVAL_S = 0.4


@dataclass
class Candidate:
    id: int
    obj: dict[str, Any]
    via: str
    title_sim: float = 0.0
    artist_sim: float = 0.0
    duration_diff_s: float | None = None
    has_synced: bool = False
    has_plain: bool = False
    has_word_sync: bool = False
    instrumental: bool = False
    gate: bool = False
    verdict: str = "reject"
    flags: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {"id": self.id, "via": self.via, "title_sim": round(self.title_sim, 1), "artist_sim": round(self.artist_sim, 1),
                "duration_diff_s": self.duration_diff_s, "has_synced": self.has_synced, "has_word_sync": self.has_word_sync,
                "instrumental": self.instrumental, "verdict": self.verdict}


def _get(http, path: str, params: Mapping[str, Any], log: list[dict[str, Any]]):
    r = http.get(LRCLIB_ROOT + path, params=dict(params), headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                 min_interval_s=INTERVAL_S)
    log.append({"step": path, "status": r.status_code, "cached": bool(getattr(r, "from_cache", False))})
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except ValueError:
        return None


def query_lrclib(http, *, title: str, artist: str, album: str | None, duration_s: float) -> tuple[dict[int, Candidate], list[dict[str, Any]]]:
    """Every LRCLIB request of the cascade; returns the pooled candidates (by id, first source wins) and a log."""
    log: list[dict[str, Any]] = []
    pool: dict[int, Candidate] = {}

    def add(o: Any, via: str) -> None:
        if isinstance(o, dict) and o.get("id") is not None:
            pool.setdefault(int(o["id"]), Candidate(int(o["id"]), o, via))

    d = int(round(duration_s))
    base = {"track_name": title, "artist_name": artist}
    if album:
        add(_get(http, "get", {**base, "album_name": album, "duration": d}, log), "get_album")
    add(_get(http, "get", {**base, "duration": d}, log), "get")
    for o in _get(http, "search", base, log) or []:
        add(o, "search")
    for o in _get(http, "search", {"q": f"{title} {artist}"}, log) or []:
        add(o, "search_q")
    return pool, log


def rank(pool: Mapping[int, Candidate], *, title: str, artist: str, duration_s: float,
         max_dd: float = 2.0, max_dd_flag: float = 5.0) -> list[Candidate]:
    from mvh.stages.identity.core import strip_version_tag, text_sim

    out = []
    for c in pool.values():
        o = c.obj
        c.title_sim = max(text_sim(title, o.get("trackName") or o.get("name")),
                          text_sim(strip_version_tag(title) or title, o.get("trackName") or o.get("name")))
        c.artist_sim = text_sim(artist, o.get("artistName"))
        dur = o.get("duration")
        c.duration_diff_s = round(float(dur) - duration_s, 3) if dur is not None else None
        c.has_synced = bool((o.get("syncedLyrics") or "").strip())
        c.has_plain = bool((o.get("plainLyrics") or "").strip())
        c.has_word_sync = bool(o.get("hasWordSync")) and bool(o.get("lyricsfile"))
        c.instrumental = bool(o.get("instrumental"))
        c.gate = c.title_sim >= 90 and c.artist_sim >= 85
        ad = abs(c.duration_diff_s) if c.duration_diff_s is not None else 1e9
        if not c.gate:
            c.verdict = "reject_text"
        elif ad <= max_dd:
            c.verdict = "accept"
        elif ad <= max_dd_flag:
            c.verdict = "accept_flag"
            c.flags.append("version_mismatch")
        else:
            c.verdict = "reject_duration"
        out.append(c)

    def key(c: Candidate):
        ad = abs(c.duration_diff_s) if c.duration_diff_s is not None else 1e9
        tier = {"accept": 0, "accept_flag": 1}.get(c.verdict, 2)
        usable = c.has_synced or c.has_plain
        # entries with lyrics rank ahead of instrumental-only ones within a tier (LRCLIB holds duplicates wrongly
        # flagged instrumental); an instrumental entry is chosen only when nothing with lyrics is acceptable
        return (tier, not usable, not c.has_synced if tier == 0 else False, not c.has_word_sync if tier == 0 else False,
                round(ad, 3), c.id)

    return sorted(out, key=key)


def choose(ranked: list[Candidate]) -> Candidate | None:
    ok = [c for c in ranked if c.verdict in ("accept", "accept_flag")]
    for c in ok:
        if c.has_synced or c.has_plain:
            return c
    return next((c for c in ok if c.instrumental), None)


def candidate_source(c: Candidate) -> dict[str, Any]:
    """Parse a chosen candidate into the text module's source shape (Lyricsfile words when hasWordSync,
    else the synced LRC, else the plain text)."""
    from . import text as T

    o = c.obj
    if c.has_word_sync:
        try:
            src = T.parse_lyricsfile(str(o["lyricsfile"]))
            if src["lines"] and src["has_word_sync"]:
                return src
        except Exception:  # noqa: BLE001  (fall back to the LRC text)
            pass
    if c.has_synced:
        return T.parse_lrc(str(o["syncedLyrics"]))
    if c.has_plain:
        return T.parse_txt(str(o["plainLyrics"]))
    return {"format": "none", "lines": [], "meta": {}, "has_line_sync": False, "has_word_sync": False}
