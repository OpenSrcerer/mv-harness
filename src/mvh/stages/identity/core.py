# ruff: noqa: E501
"""identity internals: tag normalisation, chromaprint, AcoustID and MusicBrainz lookups (PLAN §5 identity, SPIKE).

Pure functions over plain data plus an injected HTTP client (``mvh.runner.http.CachedHttp`` in the stage,
a recorded fake in the tests), so every rule is unit-testable offline.

MusicBrainz etiquette: at most 1 request per second, the identifying User-Agent below, back off on 503
(the runner's client honours Retry-After and retries), never more than ``MB_MAX_REQUESTS`` requests per run.
"""

from __future__ import annotations

import gzip
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

__all__ = [
    "USER_AGENT", "MB_ROOT", "ACOUSTID_ROOT", "normalise_tags", "credits_from_tags", "strip_version_tag",
    "title_key", "text_sim", "MbCandidate", "parse_recordings", "rank_candidates", "musicbrainz_lookup",
    "recording_credits", "acoustid_lookup", "chromaprint",
]

USER_AGENT = "mv-harness/0.1 (https://github.com/OpenSrcerer/mv-harness)"
MB_ROOT = "https://musicbrainz.org/ws/2/"
ACOUSTID_ROOT = "https://api.acoustid.org/v2/lookup"
MB_INTERVAL_S = 1.1           # 1 req/s with a little slack
ACOUSTID_INTERVAL_S = 0.34    # 3 req/s
MB_MAX_REQUESTS = 12

# tag keys (lower-cased ffprobe keys) -> credit role
CREDIT_TAGS: dict[str, str] = {
    "composer": "composer", "lyricist": "lyricist", "writer": "writer", "songwriter": "writer",
    "arranger": "arranger", "conductor": "conductor", "producer": "producer", "remixer": "remixer",
    "mixer": "mixer", "engineer": "engineer", "performer": "performer", "artist": "artist",
    "album_artist": "album_artist", "albumartist": "album_artist", "publisher": "publisher",
    "label": "label", "copyright": "copyright",
}
_PAREN_RE = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]")
_FEAT_RE = re.compile(r"\s+(feat\.?|featuring|ft\.?)\s+.*$", re.I)


# ------------------------------------------------------------------------------------------ tags
def _first(tags: Mapping[str, Any], *keys: str) -> str | None:
    for k in keys:
        v = tags.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _int_prefix(v: str | None) -> int | None:
    if not v:
        return None
    m = re.match(r"\s*(\d+)", v)
    return int(m.group(1)) if m else None


def normalise_tags(tags: Mapping[str, Any]) -> dict[str, Any]:
    """ffprobe tags (keys lower-cased by ingest) -> identity fields. Missing values are None."""
    t = {str(k).lower(): v for k, v in (tags or {}).items()}
    year = None
    d = _first(t, "date", "year", "originaldate", "original_date", "tdrc", "tyer")
    if d:
        m = re.search(r"(1[89]\d\d|20\d\d)", d)
        year = int(m.group(1)) if m else None
    isrc = _first(t, "isrc", "tsrc")
    if isrc:
        isrc = re.sub(r"[^A-Za-z0-9]", "", isrc).upper() or None
    return {
        "title": _first(t, "title", "tit2"),
        "artist": _first(t, "artist", "tpe1", "album_artist", "albumartist"),
        "album": _first(t, "album", "talb"),
        "album_artist": _first(t, "album_artist", "albumartist", "tpe2"),
        "year": year,
        "isrc": isrc,
        "track_no": _int_prefix(_first(t, "track", "tracknumber", "trck")),
        "genre": _first(t, "genre", "tcon"),
        "mb_recording_id": _first(t, "musicbrainz_trackid", "musicbrainz track id", "musicbrainz_recordingid"),
    }


def credits_from_tags(tags: Mapping[str, Any]) -> list[dict[str, str]]:
    """Credit-like tags as [{role, name}] (multi-value tags split on ';' / '/' / ' & ')."""
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    t = {str(k).lower(): v for k, v in (tags or {}).items()}
    for key in sorted(t):
        role = CREDIT_TAGS.get(key)
        if role is None or role in ("artist", "album_artist"):
            continue
        val = t[key]
        if not isinstance(val, str):
            continue
        for name in re.split(r"\s*;\s*|\s*/\s*|\s+&\s+", val):
            name = name.strip()
            if name and (role, name) not in seen:
                seen.add((role, name))
                out.append({"role": role, "name": name})
    return out


def strip_version_tag(title: str | None) -> str | None:
    """'Jeremy (Redux Version)' -> 'Jeremy'; also drops 'feat. X' suffixes. None when nothing changes."""
    if not title:
        return None
    s = _FEAT_RE.sub("", _PAREN_RE.sub("", title)).strip(" -")
    s = re.sub(r"\s+-\s+(.*(version|remaster(ed)?|mix|edit|live|demo|redux).*)$", "", s, flags=re.I).strip()
    return s if s and s != title.strip() else None


def title_key(s: str | None) -> str:
    """Comparison key: NFKD, ASCII-folded, parentheses and punctuation removed, lower case."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = _PAREN_RE.sub("", s)
    s = re.sub(r"[^\w\s]", " ", s.lower())
    return " ".join(s.split())


def text_sim(a: str | None, b: str | None) -> float:
    """token-set similarity 0..100 on title keys (rapidfuzz)."""
    from rapidfuzz import fuzz

    ka, kb = title_key(a), title_key(b)
    if not ka or not kb:
        return 0.0
    return float(fuzz.token_set_ratio(ka, kb))


def _lucene(s: str) -> str:
    return re.sub(r'([+\-&|!(){}\[\]^"~*?:\\/])', r"\\\1", s)


# ------------------------------------------------------------------------------------------ MusicBrainz
@dataclass
class MbCandidate:
    id: str
    title: str
    score: int
    length_s: float | None
    artists: list[str]
    artist_ids: list[str]
    releases: list[dict[str, Any]]
    isrcs: list[str] = field(default_factory=list)
    query: str = ""
    duration_diff_s: float | None = None
    title_sim: float = 0.0
    artist_sim: float = 0.0
    release_sim: float = 0.0
    accepted: bool = False

    def summary(self) -> dict[str, Any]:
        return {"id": self.id, "score": self.score, "duration_diff_s": self.duration_diff_s,
                "title_sim": round(self.title_sim, 1), "artist_sim": round(self.artist_sim, 1),
                "release_sim": round(self.release_sim, 1), "accepted": self.accepted, "query": self.query}


def parse_recordings(obj: Mapping[str, Any] | None, query: str = "") -> list[MbCandidate]:
    out: list[MbCandidate] = []
    recs = (obj or {}).get("recordings") or []
    for r in recs:
        ac = r.get("artist-credit") or []
        out.append(MbCandidate(
            id=str(r.get("id")),
            title=str(r.get("title") or ""),
            score=int(r.get("score") or (100 if "score" not in r else 0)),
            length_s=(float(r["length"]) / 1000.0) if r.get("length") else None,
            artists=[str(a.get("name") or (a.get("artist") or {}).get("name") or "") for a in ac if isinstance(a, dict)],
            artist_ids=[str((a.get("artist") or {}).get("id")) for a in ac if isinstance(a, dict) and (a.get("artist") or {}).get("id")],
            releases=[{"id": x.get("id"), "title": x.get("title"), "date": x.get("date")} for x in (r.get("releases") or [])],
            isrcs=list(r.get("isrcs") or []),
            query=query,
        ))
    return out


def rank_candidates(cands: Iterable[MbCandidate], *, title: str | None, artist: str | None, album: str | None,
                    duration_s: float, min_score: int = 90, max_dd: float = 3.0) -> list[MbCandidate]:
    """Score every candidate against the tags; accepted = score >= min_score, |Δdur| <= max_dd, title and
    artist gates (token-set >= 90 / >= 85, version tags ignored). Order: accepted first, then release-title
    agreement with the album tag, smallest |Δdur|, MB score, id (deterministic)."""
    seen: dict[str, MbCandidate] = {}
    for c in cands:
        if c.id in seen:
            continue
        c.duration_diff_s = round(c.length_s - duration_s, 3) if c.length_s else None
        c.title_sim = max(text_sim(title, c.title), text_sim(strip_version_tag(title) or title, c.title))
        c.artist_sim = max([text_sim(artist, a) for a in c.artists] + [text_sim(artist, " ".join(c.artists))]) if c.artists else 0.0
        c.release_sim = max([text_sim(album, r.get("title")) for r in c.releases] or [0.0]) if album else 0.0
        c.accepted = (c.score >= min_score and c.duration_diff_s is not None and abs(c.duration_diff_s) <= max_dd
                      and c.title_sim >= 90 and (not artist or c.artist_sim >= 85))
        seen[c.id] = c
    return sorted(seen.values(), key=lambda c: (not c.accepted, -round(c.release_sim / 10),
                                                abs(c.duration_diff_s) if c.duration_diff_s is not None else 1e9,
                                                -c.score, c.id))


def _mb_get(http, path: str, params: Mapping[str, Any], log: list[dict[str, Any]]):
    p = dict(params)
    p["fmt"] = "json"
    r = http.get(MB_ROOT + path, params=p, headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                 min_interval_s=MB_INTERVAL_S)
    log.append({"api": "musicbrainz", "path": path.split("/")[0], "status": r.status_code,
                "cached": bool(getattr(r, "from_cache", False))})
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except ValueError:
        return None


def musicbrainz_lookup(http, *, title: str | None, artist: str | None, album: str | None, isrc: str | None,
                       duration_s: float, min_score: int = 90, max_dd: float = 3.0,
                       max_requests: int = MB_MAX_REQUESTS) -> dict[str, Any]:
    """Find the recording. Order: ISRC lookup; recording search with a ±max_dd duration window (full title,
    then the title without its parenthesised version tag); then plain searches paged past the first results
    (limit 100, two pages). Stops at the first accepted candidate. Returns {best, candidates, log, queries}."""
    log: list[dict[str, Any]] = []
    pool: list[MbCandidate] = []
    queries: list[str] = []

    def budget() -> bool:
        return len(log) < max_requests

    def accepted() -> MbCandidate | None:
        ranked = rank_candidates(pool, title=title, artist=artist, album=album, duration_s=duration_s,
                                 min_score=min_score, max_dd=max_dd)
        return ranked[0] if ranked and ranked[0].accepted else None

    if isrc and budget():
        o = _mb_get(http, f"isrc/{isrc}", {"inc": "artist-credits+releases"}, log)
        queries.append("isrc")
        found = parse_recordings(o, "isrc")
        for c in found:
            c.score = 100   # an ISRC hit is exact by construction
        pool += found
        if accepted():
            return _finish(pool, title, artist, album, duration_s, min_score, max_dd, log, queries)
    if not title:
        return _finish(pool, title, artist, album, duration_s, min_score, max_dd, log, queries)
    titles = [title]
    base = strip_version_tag(title)
    if base:
        titles.append(base)
    lo, hi = int(max(0.0, duration_s - max_dd) * 1000), int((duration_s + max_dd) * 1000)
    for i, ti in enumerate(titles):
        if not budget():
            break
        q = f'recording:"{_lucene(ti)}"'
        if artist:
            q += f' AND artist:"{_lucene(artist)}"'
        q += f" AND dur:[{lo} TO {hi}]"
        name = "title+dur" if i == 0 else "base_title+dur"
        o = _mb_get(http, "recording", {"query": q, "limit": 25}, log)
        queries.append(name)
        pool += parse_recordings(o, name)
        if accepted():
            return _finish(pool, title, artist, album, duration_s, min_score, max_dd, log, queries)
    # plain searches, paged past the first results (MusicBrainz's relevance order buries versions)
    ti = base or title
    q = f'recording:"{_lucene(ti)}"' + (f' AND artist:"{_lucene(artist)}"' if artist else "")
    for page in range(2):
        if not budget():
            break
        o = _mb_get(http, "recording", {"query": q, "limit": 100, "offset": page * 100}, log)
        queries.append(f"base_title_page{page + 1}")
        got = parse_recordings(o, f"base_title_page{page + 1}")
        pool += got
        if accepted() or len(got) < 100:
            break
    return _finish(pool, title, artist, album, duration_s, min_score, max_dd, log, queries)


def _finish(pool, title, artist, album, duration_s, min_score, max_dd, log, queries) -> dict[str, Any]:
    ranked = rank_candidates(pool, title=title, artist=artist, album=album, duration_s=duration_s,
                             min_score=min_score, max_dd=max_dd)
    best = ranked[0] if ranked and ranked[0].accepted else None
    return {"best": best, "candidates": ranked[:8], "log": log, "queries": queries, "n_candidates": len(ranked)}


def recording_credits(http, rec_id: str, log: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Credits of one recording: artist relationships (vocals, instruments, production) and, through its
    work, composer / lyricist / writer. Two to three MusicBrainz requests."""
    log = log if log is not None else []
    credits: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    o = _mb_get(http, f"recording/{rec_id}", {"inc": "artist-credits+artist-rels+work-rels+isrcs+releases"}, log)
    if not o:
        return {"credits": [], "isrcs": [], "artist_ids": [], "release": None}

    def add(role: str, name: str) -> None:
        role, name = role.strip(), name.strip()
        if role and name and (role, name) not in seen:
            seen.add((role, name))
            credits.append({"role": role, "name": name})

    work_ids: list[str] = []
    for rel in o.get("relations") or []:
        tt = str(rel.get("type") or "")
        if rel.get("artist"):
            attrs = [a for a in (rel.get("attributes") or []) if isinstance(a, str)]
            role = tt if not attrs else f"{tt} ({', '.join(attrs)})"
            add(role, str(rel["artist"].get("name") or ""))
        if rel.get("work") and rel["work"].get("id"):
            work_ids.append(str(rel["work"]["id"]))
    for wid in sorted(set(work_ids))[:1]:
        w = _mb_get(http, f"work/{wid}", {"inc": "artist-rels"}, log)
        for rel in (w or {}).get("relations") or []:
            if rel.get("artist"):
                add(str(rel.get("type") or "writer"), str(rel["artist"].get("name") or ""))
    artist_ids = [str((a.get("artist") or {}).get("id")) for a in (o.get("artist-credit") or [])
                  if isinstance(a, dict) and (a.get("artist") or {}).get("id")]
    rel0 = (o.get("releases") or [None])[0]
    return {"credits": credits, "isrcs": list(o.get("isrcs") or []), "artist_ids": artist_ids,
            "release": {"id": rel0.get("id"), "title": rel0.get("title")} if rel0 else None}


# ------------------------------------------------------------------------------------------ AcoustID
def acoustid_lookup(http, key: str, fingerprint: str, duration_s: float) -> dict[str, Any]:
    """AcoustID v2 lookup as a gzip-compressed POST (PLAN: gzip POST, <= 3 req/s). Returns the best result
    {id, score, recording_ids} or {} on failure."""
    from urllib.parse import urlencode

    body = urlencode({"client": key, "duration": str(int(round(duration_s))), "fingerprint": fingerprint,
                      "meta": "recordingids", "format": "json"}).encode("ascii")
    r = http.post(ACOUSTID_ROOT, data=gzip.compress(body, mtime=0),
                  headers={"User-Agent": USER_AGENT, "Content-Encoding": "gzip",
                           "Content-Type": "application/x-www-form-urlencoded"},
                  min_interval_s=ACOUSTID_INTERVAL_S)
    if r.status_code != 200:
        return {"status": r.status_code}
    try:
        o = r.json()
    except ValueError:
        return {"status": r.status_code}
    res = sorted((o.get("results") or []), key=lambda x: (-float(x.get("score") or 0), str(x.get("id"))))
    if not res:
        return {"status": 200}
    b = res[0]
    return {"status": 200, "id": b.get("id"), "score": float(b.get("score") or 0.0),
            "recording_ids": [str(x.get("id")) for x in (b.get("recordings") or []) if x.get("id")]}


# ------------------------------------------------------------------------------------------ chromaprint
def chromaprint(wav_path, seconds: float = 120.0, timeout: float = 120.0) -> tuple[str | None, str]:
    """ffmpeg's chromaprint muxer on our own canonical WAV (first ``seconds``). Returns (base64 fp, note)."""
    from mvh.io.ffmpeg import run_ffmpeg

    r = run_ffmpeg(["-i", str(wav_path), "-map", "0:a:0", "-vn", "-t", f"{seconds:g}", "-f", "chromaprint",
                    "-fp_format", "base64", "-"], timeout=timeout, loglevel="error")
    fp = (r.stdout or b"").decode("ascii", errors="replace").strip()
    if r.returncode != 0 or not fp:
        return None, f"chromaprint failed (exit {r.returncode})"
    return fp, "ok"


def merge_credits(*lists: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for lst in lists:
        for c in lst:
            k = (str(c.get("role", "")), str(c.get("name", "")))
            if k[0] and k[1] and k not in seen:
                seen.add(k)
                out.append({"role": k[0], "name": k[1]})
    return out
