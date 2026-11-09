"""identity stage (PLAN §5 identity, SPIKE; owner M5).

Reads the ffprobe tags that ingest recorded in ``meta/source.json`` and normalises them (title, artist, album,
album artist, year, ISRC, track, genre, credit tags). When the tags are incomplete, or with ``verify`` (on in
the ``max`` profile), it looks the recording up:

* AcoustID (only when ``ACOUSTID_API_KEY`` or config.json ``acoustid_api_key`` is set): ffmpeg chromaprint of
  the canonical WAV, gzip POST, <= 3 req/s;
* MusicBrainz WS/2 at 1 req/s with the identifying User-Agent: ISRC lookup, then a recording search with a
  ±3 s duration window (full title, then without the parenthesised version tag, e.g. "Jeremy (Redux
  Version)"), then plain searches paged past the first results. A match needs score >= 90, |Δdur| <= 3 s and
  the title/artist gates. Credits come from the recording's artist and work relationships.

Every response goes through ``ctx.http()`` (cached, hashed into the cache key). Offline without a cached
response the stage falls back to the tags (fallback ``identity:offline``); it never fails for lack of network.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from mvh.runner.spec import ExternalInput, StageError, StageResult, StageSpec, catalog_outputs

STAGE = StageSpec(
    "identity",
    ('ingest',),
    "main",
    "1.0.0",
    override_keys=(),
    outputs=catalog_outputs("identity"),
    params={'verify': True, 'mb_min_score': 90, 'max_duration_diff_s': 3.0, 'fetch_credits': True,
            'chromaprint_seconds': 120.0},
    params_by_profile={"draft": {"verify": False, "fetch_credits": False}},
    external_inputs=(ExternalInput("acoustid", "http:acoustid"), ExternalInput("musicbrainz", "http:musicbrainz"),),
    network=True,
    uses_ffmpeg=True,
    module="M5",
    description='Normalise tags; chromaprint + AcoustID + MusicBrainz when tags are missing or --verify-identity.',
)


def _acoustid_key() -> str | None:
    k = os.environ.get("ACOUSTID_API_KEY")
    if k:
        return k.strip() or None
    cfg = Path(os.environ.get("LOCALAPPDATA", "")) / "mvh" / "config.json"
    try:
        with open(cfg, encoding="utf-8-sig") as fh:
            v = json.load(fh).get("acoustid_api_key")
        return str(v).strip() or None if v else None
    except (OSError, ValueError, AttributeError):
        return None


def run(ctx) -> StageResult:
    from . import core

    p = ctx.params
    src = ctx.upstream("ingest").json("meta/source.json")
    tags = src.get("tags") or {}
    duration = float(src.get("duration_s") or 0.0)
    norm = core.normalise_tags(tags)
    warnings: list[str] = []
    fallbacks: list[str] = []
    notes: list[str] = []
    tags_complete = bool(norm["title"] and norm["artist"])
    lookup = (not tags_complete) or bool(p.get("verify"))

    mb_info: dict[str, Any] = {"status": "skipped" if not lookup else "pending"}
    ac_info: dict[str, Any] = {"status": "skipped"}
    best = None
    rec_credits: dict[str, Any] = {"credits": [], "isrcs": [], "artist_ids": [], "release": None}
    if lookup:
        try:
            http = ctx.http()
            key = _acoustid_key()
            ac_ids: list[str] = []
            if key:
                try:
                    wav = ctx.upstream("ingest").path("canonical.wav")
                    fp, note = core.chromaprint(wav, float(p.get("chromaprint_seconds", 120.0)))
                    if fp:
                        a = core.acoustid_lookup(http, key, fp, duration)
                        ac_info = {"status": "ok" if a.get("id") else f"no_match ({a.get('status')})",
                                   "id": a.get("id"), "score": a.get("score")}
                        ac_ids = list(a.get("recording_ids") or [])
                    else:
                        ac_info = {"status": note}
                except StageError:
                    raise
                except Exception as e:  # noqa: BLE001  (a lookup problem never fails the stage)
                    ac_info = {"status": f"error: {type(e).__name__}"}
            else:
                ac_info = {"status": "no_key"}
            r = core.musicbrainz_lookup(http, title=norm["title"], artist=norm["artist"], album=norm["album"],
                                        isrc=norm["isrc"], duration_s=duration, min_score=int(p.get("mb_min_score", 90)),
                                        max_dd=float(p.get("max_duration_diff_s", 3.0)))
            best = r["best"]
            if best is None and ac_ids:
                # AcoustID named recordings: look them up directly (titles may be missing from the tags)
                for rid in ac_ids[:3]:
                    o = core._mb_get(http, f"recording/{rid}", {"inc": "artist-credits+releases"}, r["log"])
                    if o:
                        o2 = {"recordings": [dict(o, score=100)]}
                        cands = core.rank_candidates(core.parse_recordings(o2, "acoustid"), title=norm["title"] or o.get("title"),
                                                     artist=norm["artist"] or None, album=norm["album"], duration_s=duration,
                                                     min_score=int(p.get("mb_min_score", 90)), max_dd=float(p.get("max_duration_diff_s", 3.0)))
                        if cands and cands[0].accepted:
                            best = cands[0]
                            break
            mb_info = {"status": "accepted" if best else "not_found", "queries": r["queries"],
                       "requests": len(r["log"]), "n_candidates": r["n_candidates"],
                       "candidates": [c.summary() for c in r["candidates"][:5]]}
            if best is not None:
                mb_info.update({"recording_id": best.id, "score": best.score, "duration_diff_s": best.duration_diff_s,
                                "release": next((x for x in best.releases if core.text_sim(norm["album"], x.get("title")) >= 80),
                                                best.releases[0] if best.releases else None)})
                if p.get("fetch_credits"):
                    rec_credits = core.recording_credits(http, best.id, r["log"])
                    mb_info["requests"] = len(r["log"])
            if any(x["status"] == 503 for x in r["log"]):
                warnings.append("MusicBrainz answered 503 (rate limited) at least once")
        except StageError as e:
            # offline and nothing cached, or the network failed: the tags stay authoritative
            msg = str(e)
            mb_info = {"status": "offline" if "offline" in msg else "error"}
            fallbacks.append("identity:offline" if "offline" in msg else "identity:network_error")
            warnings.append("identity lookup skipped: " + ("offline (no cached response)" if "offline" in msg else "network error"))

    title, artist, album = norm["title"], norm["artist"], norm["album"]
    source = "tags"
    if best is not None:
        if not title:
            title = best.title
            source = "acoustid" if best.query == "acoustid" else "musicbrainz"
        if not artist and best.artists:
            artist = " & ".join(best.artists)
            source = "acoustid" if best.query == "acoustid" else "musicbrainz"
        if not album and best.releases:
            album = best.releases[0].get("title")

    if tags_complete and best is not None:
        conf = 0.98
    elif tags_complete:
        conf = 0.9 if mb_info["status"] in ("skipped", "offline", "error") else 0.85
        if mb_info["status"] == "not_found":
            notes.append("tags kept; no MusicBrainz recording matched within the duration window")
    elif best is not None:
        conf = round(min(0.95, (ac_info.get("score") or 0.8) if source == "acoustid" else 0.8 * best.score / 100.0), 3)
    else:
        conf = 0.0 if not title else 0.5
    credits = core.merge_credits(core.credits_from_tags(tags), rec_credits["credits"])
    doc: dict[str, Any] = {
        "title": title, "artist": artist, "album": album, "duration_s": round(duration, 6), "source": source,
        "conf": float(conf), "credits": credits,
        "album_artist": norm["album_artist"], "year": norm["year"], "isrc": norm["isrc"] or (rec_credits["isrcs"][0] if rec_credits["isrcs"] else None),
        "track_no": norm["track_no"], "genre": norm["genre"],
        "mb_recording_id": best.id if best is not None else norm["mb_recording_id"],
        "mb_artist_ids": (rec_credits["artist_ids"] or (best.artist_ids if best is not None else [])),
        "acoustid_id": ac_info.get("id"), "acoustid_score": ac_info.get("score"),
        # additive (contract additions, docs/contract/decisions/M5.md)
        "tags_complete": tags_complete,
        "lookup": {"musicbrainz": mb_info, "acoustid": ac_info},
    }
    ctx.writer.json("meta/identity.json", doc)
    if not title:
        warnings.append("no title: neither tags nor a lookup named the recording")
    summary = {"title": title, "artist": artist, "source": source, "conf": float(conf),
               "musicbrainz": mb_info["status"], "acoustid": ac_info["status"], "credits": len(credits)}
    return StageResult(status="degraded" if fallbacks and not tags_complete else "ok", summary=summary,
                       warnings=warnings, fallbacks=fallbacks, confidence=float(conf),
                       provenance={"notes": notes + [f"lookup={'yes' if lookup else 'no'}"],
                                   "tools": [{"name": "musicbrainz-ws2", "version": "2"}] if lookup else []})
