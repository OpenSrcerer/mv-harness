"""Collect the inlined preview data of viewer.html from the upstream caches (see bundle.py)."""
from __future__ import annotations

import json
from typing import Any

#: lanes and the data each needs; a lane whose files are all absent is reported in ``lanes_without_data``
LANE_NEEDS: dict[str, tuple[str, ...]] = {
    "sections": ("events/sections.json",),
    "meaning": ("meaning/meaning.json",),
    "lyrics": ("lyrics/lyrics.json",),
    "beats": ("events/beats.json",),
    "hits": ("events/drum_hits.json", "events/hit_points.json"),
    "bands": ("curves:bands.bass",),
    "loudness": ("curves:loud.short_term_lufs", "events/dynamics.json"),
    "instruments": ("events/instruments.json", "events/stem_activity.json", "curves:stem.bass.level"),
    "notes": ("events/notes.bass.json", "events/notes.piano.json", "events/notes.guitar.json", "events/notes.other.json",
              "events/notes.vocals.json"),
    "vocal": ("curves:vocal.midi", "meta/vocal_range.json"),
    "cues": ("events/cues.json",),
}


def _is_text_output(rel: str, kind: str) -> bool:
    return kind in ("events", "json") and rel.endswith(".json")


def build_data(ctx: Any, bd: Any) -> dict[str, Any]:
    p = ctx.params
    bundle = bd.Bundle()
    warnings: list[str] = []
    fallbacks: list[str] = []
    present: set[str] = set()
    events_list: list[dict[str, str]] = []
    audio_files: list[str] = []

    inline_lyrics = bool(p.get("inline_lyrics", True))
    skip = set() if inline_lyrics else {"lyrics/lyrics.json"}

    # ---- JSON documents and events from every upstream stage
    for dep in ctx.spec.deps:
        try:
            up = ctx.upstream(dep)
        except Exception:  # noqa: BLE001
            continue
        for rel, info in sorted(bd.upstream_outputs(up).items()):
            kind = info.get("kind", "")
            if kind == "audio" and rel.startswith(("stems/", "audio/")) and rel.endswith((".flac", ".opus", ".wav")):
                audio_files.append(rel)
            if not _is_text_output(rel, kind) or rel in skip:
                continue
            if rel.startswith(("lipsync/", "events/", "meta/", "lyrics/", "meaning/")) and not rel.endswith(
                ("input.json", "schema.json", "authored.json", "orphans.json")
            ):
                try:
                    raw = up.path(rel).read_bytes()
                except Exception:  # noqa: BLE001
                    continue
                bundle.add(rel, "json", raw)
                present.add(rel)
                if kind == "events":
                    events_list.append({"kind": "events", "path": rel, "events": info.get("events") or rel.split("/")[-1][:-5]})

    # ---- curves (reduced) and the spectrogram
    patterns = tuple(p.get("channels") or bd.DEFAULT_CHANNELS)
    chans, files_meta = bd.collect_curves(ctx, patterns)
    index, blobs = bd.pack_curves(chans, files_meta)
    for rel, raw in blobs.items():
        bundle.add(rel, "bin", raw)
    bundle.add("curves/index.json", "json", bd.dumps(index))
    for cid in chans:
        present.add(f"curves:{cid}")

    duration = 0.0
    src_meta: dict[str, Any] = {}
    try:
        src_meta = json.loads(bundle.files["meta/source.json"][1].decode("utf-8"))
        duration = float(src_meta.get("duration_s") or 0.0)
    except (KeyError, ValueError):
        pass

    # ---- waveform base from the canonical mix
    wave: dict[str, Any] | None = None
    try:
        a = ctx.audio("mix", mono=True)
        wave = bd.waveform_base(a.samples, a.sr, int(p.get("waveform_hz", 1000)))
        if not duration:
            duration = float(a.samples.shape[-1]) / float(a.sr)
    except Exception as e:  # noqa: BLE001
        warnings.append(f"waveform unavailable: {type(e).__name__}")
        fallbacks.append("viewer:no_waveform")

    # ---- manifest (mini) so lib/mvh.js can resolve events paths and the duration
    manifest = {
        "schema": "mvh/envelope/manifest",
        "source": {"duration_s": duration},
        "timebase": {"soundtrack": "audio/mix.flac"},
        "files": sorted(events_list, key=lambda d: d["path"]),
        "inline": True,
    }
    bundle.add("manifest.json", "json", bd.dumps(manifest))

    # ---- sized extras, in priority order, under the cap
    cap = int(float(p.get("inline_cap_mb", 28.0)) * 1024 * 1024)
    enc = bundle.encode()
    total = sum(bundle.sizes.values())
    inlined = ["data"]
    sp = bd.collect_spectrogram(ctx) if p.get("inline_spectrogram", True) else None
    extra: dict[str, list[Any]] = {}
    if sp is not None:
        arr, info = sp
        raw = arr.tobytes()
        import base64
        import zlib

        z = base64.b64encode(zlib.compress(raw, 9)).decode("ascii")
        if total + len(z) <= cap:
            extra["curves/spectrum128.u8"] = ["bin", len(raw), z]
            total += len(z)
            inlined.append("spectrogram")
            idx = json.loads(bundle.files["curves/index.json"][1].decode("utf-8"))
            idx["files"]["spectrum128"] = {
                "path": "curves/spectrum128.u8", "dtype": "u8", "layout": "row-major", "rate_hz": 100,
                "n_frames": int(arr.shape[0]), "n_channels": int(arr.shape[1]),
                "quant": {"scale": 1 / 255, "offset": 0},
            }
            raw_idx = bd.dumps(idx)
            enc["curves/index.json"] = ["json", len(raw_idx), base64.b64encode(zlib.compress(raw_idx, 9)).decode("ascii")]
            present.add("curves:spectrum128")
        else:
            fallbacks.append("viewer:spectrogram_not_inlined")
    audio_inline: str | None = None
    try:
        up = ctx.upstream("ingest")
        if up.exists("audio/preview.opus"):
            raw = up.path("audio/preview.opus").read_bytes()
            import base64

            b64 = base64.b64encode(raw).decode("ascii")
            if len(raw) <= float(p.get("inline_audio_max_mb", 8.0)) * 1024 * 1024 and total + len(b64) <= cap:
                audio_inline = b64
                total += len(b64)
                inlined.append("preview_audio")
            else:
                fallbacks.append("viewer:preview_not_inlined")
            present.add("audio/preview.opus")
    except Exception:  # noqa: BLE001
        pass
    enc.update(extra)

    missing = []
    for lane, needs in LANE_NEEDS.items():
        if not any(n in present for n in needs):
            missing.append(lane)

    title = str((src_meta.get("tags") or {}).get("title") or "")
    ident = bundle.files.get("meta/identity.json")
    if ident:
        try:
            j = json.loads(ident[1].decode("utf-8"))
            title = str(j.get("title") or title)
        except ValueError:
            pass
    if not title:
        title = ctx.slug

    stem_names = sorted({r.split("/")[-1][:-5] for r in audio_files if r.startswith("stems/") and r.endswith(".flac")
                         and "/" not in r[len("stems/"):]})
    data = {
        "v": 1,
        "slug": ctx.slug,
        "title": title,
        "duration": duration,
        "files": enc,
        "wave": wave,
        "audio_preview": audio_inline,
        "stems": stem_names,
        "has_mix": any(r.startswith("audio/mix.") for r in audio_files),
        "info": {
            "stage_version": ctx.spec.version,
            "inlined": inlined,
            "lanes_without_data": missing,
            "fallbacks": fallbacks,
            "inline_lyrics": inline_lyrics,
            "cap_bytes": cap,
            "contract": "1.0.0-rc.2",
        },
    }
    return {
        "data": data, "title": title, "sizes": {"total": total}, "inlined": inlined, "missing": missing,
        "warnings": warnings, "fallbacks": fallbacks,
    }
