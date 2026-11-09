"""lipsync orchestration (PLAN §5 lipsync, SPIKE, bench-words §7, CONTRACT D16).

Must: ``vocal.mouth_open`` (100 Hz, 0..1, policy max) = the lead-vocal envelope (RMS, 10 ms attack / 60 ms release
one-pole, per-song p95 gain) gated by the SUSTAIN-EXTENDED word spans: every word is held to the next word's
start, a line's last word is held while the envelope stays within 20 dB of p95 (at most 1.5 s), ±80 ms pad,
5-frame soft edges. Wordless vocal regions (active voice, no word within 1 s, level within 10 dB of the sung
level) are passed ungated (the fallback for wordless singing). With >= 2 voices every voice gets
``vocal.mouth_open.<V>`` (its own words only) and ``vocal.mouth_open`` is the max over voices.

Should: Rhubarb Lip Sync 1.14 visemes (A-H, X; Preston Blair mapping in CONTRACT.md) per voice block, run on
16 kHz 16-bit WAV excerpts with ``-d`` = the block's lyric lines in a scratch file that is deleted right after
(``-f json -o file``). A decoration track: on dense rap it rarely closes the mouth.
Could: phonemes (ARPAbet, g2p-en) spread over each aligned word, vowels weighted double.
"""

from __future__ import annotations

import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from mvh.runner.spec import StageError, StageResult
from mvh.stages.lyrics import vocal_env as VE

__all__ = ["run", "find_rhubarb", "gate_for_words"]

_VOWELS = ("AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY", "IH", "IY", "OW", "OY", "UH", "UW")


def find_rhubarb() -> Path | None:
    v = os.environ.get("MVH_RHUBARB")
    if v and Path(v).is_file():
        return Path(v)
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "mvh"
    try:
        with open(base / "config.json", encoding="utf-8-sig") as fh:
            c = json.load(fh).get("rhubarb")
        if c and Path(c).is_file():
            return Path(c)
    except (OSError, ValueError, AttributeError):
        pass
    hits = sorted((base / "bin" / "rhubarb").glob("**/rhubarb.exe")) if (base / "bin" / "rhubarb").is_dir() else []
    return hits[0] if hits else None


def gate_for_words(words: list[dict[str, Any]], env: np.ndarray, floor: float, n: int, pad: float = 0.08,
                   max_hold: float = 1.5, next_line_t: float | None = None) -> np.ndarray:
    """Sustain-extended gate (0/1) for one line's words (sorted by t). The last word's hold never runs into the
    next line (of any voice): the envelope there belongs to whoever sings next."""
    g = np.zeros(n, dtype=np.float32)
    for k, w in enumerate(words):
        a = max(0, int(np.floor((w["t"] - pad) * 100)))
        if k + 1 < len(words):
            b = int(np.ceil(max(words[k + 1]["t"], w["t"] + w["d"]) * 100))
        else:
            end = w["t"] + w["d"]
            lim = end + max_hold if next_line_t is None else max(end, min(end + max_hold, next_line_t - pad))
            e2 = VE.sustain_end(env, floor, w["t"], end, lim, max_hold)
            b = int(np.ceil((e2 + pad) * 100))
            if next_line_t is not None and next_line_t > w["t"]:
                b = min(b, max(int(np.ceil(end * 100)), int(np.floor((next_line_t - pad) * 100)) - 1))
        g[a:min(n, b + 1)] = 1.0
    return g


def _soft(g: np.ndarray) -> np.ndarray:
    return np.clip(np.convolve(g, np.ones(5) / 5.0, mode="same"), 0.0, 1.0)


def run(ctx) -> StageResult:  # noqa: C901
    p = dict(ctx.params)
    warnings: list[str] = []
    fallbacks: list[str] = []
    notes: list[str] = []
    lyr = ctx.upstream("lyrics").json("lyrics/lyrics.json")
    words = sorted(lyr.get("words", []), key=lambda w: (w["t"], w["id"]))
    lines = {ln["id"]: ln for ln in lyr.get("lines", [])}
    spans = [dict(s) for s in ctx.events("voice_spans").items]
    vmeta = ctx.upstream("voices").json("meta/voices.json")
    voice_ids = [v["id"] for v in vmeta.get("voices", [])]

    stem_name, x, a_sr = VE.pick_vocal_stem(ctx, None)
    if stem_name != "lead_vocals":
        fallbacks.append("lipsync:vocals_stem")
    tb = (getattr(ctx, "job", None) or {}).get("timebase") or {}
    n = VE.frames_for(int(tb["n_samples"]), int(tb["sample_rate"])) if tb else VE.frames_for(len(x), a_sr)
    rms = VE.rms_100hz(x, a_sr, n)
    env = VE.one_pole(rms, float(p.get("attack_ms", 10)), float(p.get("release_ms", 60)))
    pos = env[env > 1e-6]
    p95 = float(np.percentile(pos, 95)) if len(pos) else 0.0
    floor = p95 * 10 ** (-float(p.get("hold_within_db", 20.0)) / 20.0)
    pad = float(p.get("pad_s", 0.08))
    max_hold = float(p.get("max_hold_s", 1.5))

    # ---------------------------------------------------------------- word -> voices
    line_words: dict[str, list[dict[str, Any]]] = {}
    for w in words:
        line_words.setdefault(w["line_id"], []).append(w)
    word_voices: dict[str, set[str]] = {}
    for s in spans:
        ws = line_words.get(s["line_id"], [])
        ids = [w["id"] for w in ws]
        lo = ids.index(s["first_word"]) if s.get("first_word") in ids else 0
        hi = ids.index(s["last_word"]) if s.get("last_word") in ids else len(ids) - 1
        for w in ws[lo:hi + 1]:
            word_voices.setdefault(w["id"], set()).add(s["voice_id"])
    default_v = voice_ids[0] if voice_ids else "V1"
    per_voice_words: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for w in words:
        for v in sorted(word_voices.get(w["id"], {default_v})):
            per_voice_words.setdefault(v, {}).setdefault(w["line_id"], []).append(w)
    voices = sorted(set(per_voice_words) | set(voice_ids), key=lambda v: int(v[1:])) if (per_voice_words or voice_ids) else []

    # ---------------------------------------------------------------- gates
    starts = sorted((ws[0]["t"], lid) for lid, ws in line_words.items() if ws)
    next_start: dict[str, float | None] = {}
    for lid, ws in line_words.items():
        if ws:
            later = [t for t, other in starts if other != lid and t > ws[0]["t"] + 0.05]
            next_start[lid] = later[0] if later else None
    gates: dict[str, np.ndarray] = {}
    for v in voices:
        g = np.zeros(n, dtype=np.float32)
        for lid, ws in per_voice_words.get(v, {}).items():
            g = np.maximum(g, gate_for_words(ws, env, floor, n, pad, max_hold, next_start.get(lid)))
        gates[v] = g
    any_gate = np.zeros(n, dtype=np.float32)
    for g in gates.values():
        any_gate = np.maximum(any_gate, g)
    # ---------------------------------------------------------------- ungated fallback for wordless vocals
    fb_gate = np.zeros(n, dtype=np.float32)
    fb_voice: dict[str, np.ndarray] = {}
    fb_seconds = 0.0
    if p.get("ungated_fallback", True) and p95 > 0:
        act = VE.activity_from_env(env, below_p95_db=float(p.get("fallback_below_p95_db", 25.0)))
        near = np.convolve(any_gate, np.ones(201), mode="same") > 0      # a word within ±1 s
        cand = (act > 0.5) & ~near
        sung = env[any_gate > 0.5]
        ref = float(np.median(sung)) if len(sung) else p95 * 10 ** (-6 / 20)
        thr = ref * 10 ** (-float(p.get("fallback_within_db", 10.0)) / 20.0)
        i = 0
        while i < n:
            if not cand[i]:
                i += 1
                continue
            j = i
            while j < n and cand[j]:
                j += 1
            if (j - i) >= int(float(p.get("fallback_min_s", 0.5)) * 100) and float(np.median(env[i:j])) >= thr:
                fb_gate[i:j] = 1.0
                fb_seconds += (j - i) / 100.0
                # the voice of the nearest sung line within 8 s, else the first voice
                t = (i + j) / 200.0
                best, bd = None, 8.0
                for s in spans:
                    if s.get("role", "lead") != "lead":
                        continue
                    d = min(abs(t - s["t"]), abs(t - (s["t"] + s["d"])))
                    if d < bd:
                        best, bd = s["voice_id"], d
                v = best or (voices[0] if voices else None)
                if v is not None:
                    fb_voice.setdefault(v, np.zeros(n, dtype=np.float32))[i:j] = 1.0
            i = j
        # M5-D49: lyrics says instrumental (no lines, no voices): a vocal chop or sample is no singing character.
        # The fallback stays only for a substantial wordless vocal (a vocalise), >= instrumental_fallback_min_s.
        min_instr = float(p.get("instrumental_fallback_min_s", 8.0))
        if fb_seconds and lyr.get("instrumental") and not words and fb_seconds < min_instr:
            notes.append(f"ungated fallback suppressed: lyrics is instrumental and only {fb_seconds:.1f} s of "
                         f"wordless vocals (< {min_instr:.0f} s)")
            fb_gate[:] = 0.0
            fb_voice = {}
            fb_seconds = 0.0
        if fb_seconds:
            notes.append(f"ungated fallback over {fb_seconds:.1f} s of wordless vocals")
            fallbacks.append("lipsync:ungated_wordless")
    norm = p95 if p95 > 0 else 1.0
    base = np.clip(env / norm, 0.0, 1.0)
    chans: dict[str, np.ndarray] = {}
    mo = np.zeros(n, dtype=np.float32)
    for v in voices:
        gv = np.maximum(gates[v], fb_voice.get(v, np.zeros(n, np.float32)))
        mv = (base * _soft(gv)).astype(np.float32)
        chans[v] = mv
        mo = np.maximum(mo, mv)
    if not voices:
        mo = (base * _soft(fb_gate)).astype(np.float32)
    else:
        mo = np.maximum(mo, (base * _soft(fb_gate)).astype(np.float32))
    out = {"vocal.mouth_open": mo}
    if len(voices) >= 2:
        for v in voices:
            out[f"vocal.mouth_open.{v}"] = chans[v]
    ctx.writer.curves("vocal", out)
    tot = float((env ** 2).sum()) or 1.0
    outside = float((env[_soft(np.maximum(any_gate, fb_gate)) == 0] ** 2).sum()) / tot

    # ---------------------------------------------------------------- Rhubarb visemes (Should)
    vis_items: list[dict[str, Any]] = []
    rb_info: dict[str, Any] = {"status": "skipped"}
    if p.get("visemes", True) and words and spans:
        exe = find_rhubarb()
        if exe is None:
            rb_info = {"status": "missing"}
            warnings.append("Rhubarb not found: visemes skipped (optional output)")
        else:
            try:
                vis_items, rb_info = _rhubarb(ctx, exe, spans, lines, line_words, n / 100.0, p, stem_name)
            except Exception as e:  # noqa: BLE001  (visemes are a decoration track)
                rb_info = {"status": f"failed: {type(e).__name__}"}
                warnings.append("Rhubarb failed: visemes skipped")
    if vis_items:
        ctx.writer.events("visemes", vis_items)
    # ---------------------------------------------------------------- phonemes (Could)
    ph_items: list[dict[str, Any]] = []
    ph_info: dict[str, Any] = {"status": "skipped"}
    if p.get("phonemes", True) and words:
        try:
            ph_items = _phonemes(words, word_voices, default_v)
            ph_info = {"status": "ok", "engine": "g2p-en", "items": len(ph_items)}
        except Exception as e:  # noqa: BLE001
            ph_info = {"status": f"failed: {type(e).__name__}"}
            warnings.append("g2p phonemes failed: phonemes skipped")
    if ph_items:
        ctx.writer.events("phonemes", ph_items)

    summary = {"stem": stem_name, "voices": len(voices), "channels": sorted(out), "frac_open": round(float(np.mean(mo > 0.05)), 4),
               "energy_outside_gate": round(outside, 4), "ungated_fallback_s": round(fb_seconds, 2),
               "visemes": len(vis_items), "rhubarb": rb_info.get("status"), "phonemes": len(ph_items)}
    if len(voices) >= 2:
        both = sum((chans[v] > 0.05).astype(np.int32) for v in voices)
        summary["overlap_frac"] = round(float(np.sum(both > 1) / max(1, np.sum(both > 0))), 4)
    tools = [{"name": "rhubarb", "version": "1.14.0"}] if vis_items else []
    return StageResult(status="ok", summary=summary, warnings=warnings, fallbacks=fallbacks,
                       provenance={"notes": notes, "tools": tools, "rhubarb": rb_info, "phonemes": ph_info,
                                   "gate": {"pad_s": pad, "hold_within_db": float(p.get("hold_within_db", 20.0)),
                                            "max_hold_s": max_hold, "p95": round(p95, 6)}})


def _blocks(spans: list[dict[str, Any]], gap: float = 2.0, max_len: float = 40.0) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for role in ("lead", "backing"):
        for v in sorted({s["voice_id"] for s in spans if s.get("role", "lead") == role}, key=lambda z: int(z[1:])):
            ss = sorted((s for s in spans if s["voice_id"] == v and s.get("role", "lead") == role), key=lambda s: s["t"])
            cur = None
            for s in ss:
                a, b = s["t"], s["t"] + s["d"]
                if cur and a - cur["t1"] <= gap and b - cur["t0"] <= max_len:
                    cur["t1"] = max(cur["t1"], b)
                    if s["line_id"] not in cur["lines"]:
                        cur["lines"].append(s["line_id"])
                else:
                    if cur:
                        out.append(cur)
                    cur = {"voice": v, "role": role, "t0": a, "t1": b, "lines": [s["line_id"]]}
            if cur:
                out.append(cur)
    return out


def _rhubarb(ctx, exe: Path, spans, lines, line_words, duration: float, p, stem_name: str = "lead_vocals") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from mvh.io import proc

    lead16 = np.asarray(ctx.audio(stem_name, sr=16000, mono=True).samples[0], dtype=np.float32)
    try:
        back16 = np.asarray(ctx.audio("backing_vocals", sr=16000, mono=True).samples[0], dtype=np.float32)
    except StageError:
        back16 = lead16
    blocks = _blocks(spans, float(p.get("rhubarb_block_gap_s", 2.0)))
    work = Path(ctx.scratch) / "rhubarb"
    work.mkdir(parents=True, exist_ok=True)

    def one(i: int, b: dict[str, Any]) -> list[dict[str, Any]]:
        t0 = max(0.0, b["t0"] - 0.3)
        t1 = min(duration, b["t1"] + 0.5)
        src = back16 if b["role"] == "backing" else lead16
        seg = src[int(t0 * 16000):int(t1 * 16000)]
        pk = float(np.max(np.abs(seg))) if len(seg) else 0.0
        if pk < 1e-5:
            return []
        seg16 = np.round(np.clip(seg / max(pk, 1e-9) * 0.9, -1, 1) * 32767).astype("<i2")
        wav = work / f"b{i:03d}.wav"
        _write_pcm16(wav, seg16)
        dlg = work / f"b{i:03d}.txt"
        with open(dlg, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines[lid]["text"] for lid in b["lines"] if lid in lines))
        js = work / f"b{i:03d}.json"
        try:
            r = proc.run([exe, "-f", "json", "-o", js, "-d", dlg, "--threads", "1", "--consoleLevel", "Error", wav],
                         cwd=str(exe.parent), timeout=1800)
        finally:
            try:
                dlg.unlink()          # the dialog file holds lyric text: deleted right after the run
            except OSError:
                pass
        if r.returncode != 0 or not js.is_file():
            raise RuntimeError(f"rhubarb exit {r.returncode}")
        with open(js, encoding="utf-8") as fh:
            cues = json.load(fh).get("mouthCues", [])
        out = []
        for c in cues:
            a, e = t0 + float(c["start"]), t0 + float(c["end"])
            if e <= a:
                continue
            mid = 0.5 * (a + e)
            lid = next((s["line_id"] for s in spans if s["voice_id"] == b["voice"] and s["t"] - 0.3 <= mid < s["t"] + s["d"] + 0.5), None)
            out.append({"t": a, "d": e - a, "viseme": str(c["value"]), "voice_id": b["voice"], "line_id": lid})
        return out

    with ThreadPoolExecutor(max_workers=max(1, int(ctx.threads))) as ex:
        res = list(ex.map(lambda ib: one(*ib), enumerate(blocks)))
    shutil.rmtree(work, ignore_errors=True)
    items: list[dict[str, Any]] = []
    for r in res:
        items += r
    # fill each voice's timeline with rest (X) outside its cues, so allAt(t) returns one item per voice
    filled: list[dict[str, Any]] = []
    for v in sorted({it["voice_id"] for it in items}, key=lambda z: int(z[1:])):
        vs = sorted((it for it in items if it["voice_id"] == v), key=lambda it: it["t"])
        cur = 0.0
        for it in vs:
            if it["t"] < cur - 1e-6:          # overlapping blocks (lead and backing of one voice): trim
                it = {**it, "d": it["d"] - (cur - it["t"]), "t": cur}
                if it["d"] <= 0.005:
                    continue
            if it["t"] - cur > 0.005:
                filled.append({"t": cur, "d": it["t"] - cur, "viseme": "X", "voice_id": v, "line_id": None})
            filled.append(it)
            cur = it["t"] + it["d"]
        if duration - cur > 0.005:
            filled.append({"t": cur, "d": duration - cur, "viseme": "X", "voice_id": v, "line_id": None})
    filled = [{**it, "t": round(it["t"], 6), "d": round(max(it["d"], 0.001), 6)} for it in filled]
    counts: dict[str, int] = {}
    for it in filled:
        counts[it["viseme"]] = counts.get(it["viseme"], 0) + 1
    return filled, {"status": "ok", "blocks": len(blocks), "cues": len(filled), "shapes": dict(sorted(counts.items()))}


def _write_pcm16(path: Path, x: np.ndarray, sr: int = 16000) -> None:
    import struct

    data = np.ascontiguousarray(x, dtype="<i2").tobytes()
    hdr = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, sr, sr * 2, 2, 16) \
        + b"data" + struct.pack("<I", len(data))
    with open(path, "wb") as fh:
        fh.write(hdr + data)


def _phonemes(words: list[dict[str, Any]], word_voices: dict[str, set[str]], default_v: str) -> list[dict[str, Any]]:
    from g2p_en import G2p

    g2p = G2p()
    items = []
    cache: dict[str, list[str]] = {}
    for w in words:
        key = w["text"].lower()
        if key not in cache:
            ph = [q for q in g2p(w["text"]) if q and q[0].isalpha()]
            cache[key] = [q.rstrip("012") for q in ph]
        ph = cache[key]
        if not ph:
            continue
        wts = np.array([2.0 if q in _VOWELS else 1.0 for q in ph])
        dur = max(0.02, float(w["d"]))
        edges = np.concatenate([[0.0], np.cumsum(wts) / wts.sum()]) * dur
        for v in sorted(word_voices.get(w["id"], {default_v})):
            for q, a, b in zip(ph, edges[:-1], edges[1:]):
                items.append({"t": round(w["t"] + float(a), 6), "d": round(max(0.001, float(b - a)), 6), "phoneme": q,
                              "voice_id": v, "word_id": w["id"]})
    return items
