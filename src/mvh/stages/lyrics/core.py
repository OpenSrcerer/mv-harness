"""lyrics orchestration (PLAN §5 lyrics, SPIKE, bench-words §2-5). Called by ``mvh.stages.lyrics.run``.

Source cascade (PLAN R11 order): the user's ``--lyrics`` file > embedded tags (ingest's cache-only
embedded_lyrics.json, D32) > LRCLIB > faster-whisper transcription. LRCLIB is queried whenever there is no user
file: an embedded plain text that agrees with a synced LRCLIB entry (word F1 >= 0.85) takes LRCLIB's timings.

Then, always: ASR on lead_vocals (G1 match score, anchors for unsynced text, repeat expansion), MMS_FA word
alignment with global offset detection (> 0.15 s applied, > 3 s = version mismatch), the line-window
constraint, repeated-section expansion that only ADDS lines, ASR-only lines outside the supplied text (an
announcer intro), the stable-ts fallback below 0.60 coverage, overrides (lyrics.lines / lyrics.words), the
G1-G8 gate, and the exports. Lyric text never reaches a log, a warning, the summary or provenance.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np

from mvh.runner.spec import StageError, StageResult

from . import align as A
from . import asr as R
from . import exports as X
from . import grade as G
from . import lrclib as LR
from . import text as T
from . import vocal_env as VE

__all__ = ["run"]


# ------------------------------------------------------------------------------------------ helpers
def _ingest_upstream(ctx):
    """ingest's cache dir: a declared dep, or the D8 path every stage may read (ingest_dir of the job)."""
    if "ingest" in ctx.spec.deps:
        return ctx.upstream("ingest")
    d = (getattr(ctx, "job", None) or {}).get("ingest_dir")
    if not d:
        return None
    from mvh.runner.ctx import CacheUpstream

    return CacheUpstream("ingest", Path(d))


def _embedded_source(ctx) -> tuple[dict[str, Any] | None, str | None]:
    up = _ingest_upstream(ctx)
    if up is None or not up.exists("embedded_lyrics.json"):
        return None, None
    tags = (up.json("embedded_lyrics.json") or {}).get("tags") or {}
    best = None
    for k in sorted(tags):
        v = tags[k]
        if not isinstance(v, str) or not v.strip():
            continue
        src = T.parse_any(v, "")
        if not src["lines"]:
            continue
        rank = (0 if src["has_line_sync"] else 1, -len(src["lines"]), k)
        if best is None or rank < best[0]:
            best = (rank, src, k)
    return (best[1], best[2]) if best else (None, None)


def _sections_at(sections: list[dict[str, Any]], t0: float, t1: float) -> str | None:
    best, ov = None, 0.0
    for s in sections:
        a, b = float(s["t"]), float(s["t"]) + float(s["d"])
        o = min(b, t1) - max(a, t0)
        if o > ov + 1e-9:
            best, ov = s["id"], o
    if best is None:
        for s in sections:
            if float(s["t"]) <= t0 < float(s["t"]) + float(s["d"]):
                return s["id"]
    return best


def _word_conf(score: float | None, asr_ok: bool | None, placement_ok: bool) -> float:
    if score is None:
        return 0.1
    c = 0.1 + 0.9 * min(1.0, max(0.0, score) / 0.5)
    if asr_ok is False:
        c *= 0.85
    if not placement_ok:
        c *= 0.7
    return round(float(min(1.0, max(0.0, c))), 4)


def _mk_line(text: str, *, t=None, end=None, words_src=None, speaker=None, backing=False, origin="source",
             order=0, tm: T.TokenMaker) -> dict[str, Any]:
    dw = T.display_words(text)
    src_wt: list[float | None] = [None] * len(dw)
    src_wp: list[float | None] = [None] * len(dw)
    if words_src:
        # source words were split on whitespace; map onto display words by order (punctuation glued)
        k = 0
        for i, w in enumerate(dw):
            n = len(w.split())
            ts = [x.get("t") for x in words_src[k:k + n]]
            src_wt[i] = next((x for x in ts if x is not None), None)
            ps = [x.get("p") for x in words_src[k:k + n] if x.get("p") is not None]
            src_wp[i] = float(min(ps)) if ps else None
            k += n
    return {"text": text, "words": dw, "toks": [tm.tokens(w) for w in dw], "src_t": t, "src_end": end,
            "src_wt": src_wt, "src_wp": src_wp, "speaker": speaker, "backing": bool(backing), "origin": origin, "order": order,
            "wres": [None] * len(dw), "timing_source": None, "dev": None}


# ------------------------------------------------------------------------------------------ run
def run(ctx) -> StageResult:  # noqa: C901  (one linear pipeline; each step is commented)
    p = dict(ctx.params)
    warnings: list[str] = []
    fallbacks: list[str] = []
    notes: list[str] = []
    models_used: list[str] = []

    ident = ctx.upstream("identity").json("meta/identity.json")
    title, artist, album = ident.get("title"), ident.get("artist"), ident.get("album")
    try:
        sections = [dict(s) for s in ctx.events("sections").items]
    except StageError:
        sections = []
        warnings.append("no sections events: section_id left null")
    stem_name, lead, _sr, vocals_regions = VE.pick_alignment_signal(
        ctx, 16000, gap_db=float(p.get("weak_lead_gap_db", 8.0)), min_s=float(p.get("weak_lead_min_s", 4.0)),
        enabled=bool(p.get("weak_lead_regions", True)))
    if stem_name == "vocals":
        fallbacks.append("lyrics:vocals_stem")
        warnings.append("lead_vocals is nearly silent: words aligned on the full vocals stem")
    elif vocals_regions:
        # D82: a hook sung by a group lands in the backing stem; the lead stem is nearly empty there
        notes.append(f"lead_vocals is weak in {len(vocals_regions)} stretch(es) where the vocals are active "
                     f"({sum(b - a for a, b in vocals_regions):.0f} s): the full vocals stem is used there")
    duration = float(ident.get("duration_s") or len(lead) / 16000.0)
    n100 = VE.frames_for(len(lead), 16000)
    rms = VE.rms_100hz(lead, 16000, n100)
    env = VE.one_pole(rms, 10.0, 60.0)
    p95 = float(np.percentile(env[env > 0], 95)) if np.any(env > 0) else 0.0
    sustain_floor = p95 * 10 ** (-20.0 / 20.0)
    # lead-vocal activity: stem_activity's curve OR the stem's own envelope (stem_activity judges a stem against the
    # mix, so a quiet, heavily mixed vocal - MEGAFAUNA - can be "inactive" everywhere while it is clearly sung)
    env_act = VE.activity_from_env(env)
    try:
        cur = np.asarray(ctx.curve("stem.lead_vocals.active").values, dtype=np.float32)
        m = min(len(cur), len(env_act))
        act = np.zeros(len(env_act), np.float32)
        act[:m] = np.maximum(cur[:m], env_act[:m])
        act_src = "stem_activity+envelope"
    except StageError:
        act = env_act
        act_src = "envelope"
        fallbacks.append("lyrics:activity_from_envelope")
    active_s = float(np.sum(act > 0.5)) / 100.0

    # ---------------------------------------------------------------- 1. source cascade
    src: dict[str, Any] | None = None
    kind = "none"
    lrclib_id = None
    dd = None
    lrclib_info: dict[str, Any] = {"status": "not_queried"}
    user_path = ctx.external("lyrics")
    if user_path is not None:
        txt, warn = T.read_text_file(user_path)
        if warn:
            warnings.append(warn)
        src = T.parse_any(txt, user_path.name)
        kind = "user"
        if not src["lines"]:
            warnings.append("the --lyrics file has no lyric lines")
            src, kind = None, "none"
    emb, emb_key = (None, None)
    if src is None:
        emb, emb_key = _embedded_source(ctx)
        if emb is not None:
            src, kind = emb, "embedded"
            notes.append(f"embedded lyrics from tag key {emb_key!r}")
    chosen = None
    if kind != "user" and p.get("lrclib", True) and title and artist:
        try:
            pool, log = LR.query_lrclib(ctx.http(), title=title, artist=artist, album=album, duration_s=duration)
            ranked = LR.rank(pool, title=title, artist=artist, duration_s=duration,
                             max_dd=float(p.get("lrclib_max_dd_s", 2.0)), max_dd_flag=float(p.get("lrclib_max_dd_flag_s", 5.0)))
            chosen = LR.choose(ranked)
            lrclib_info = {"status": "chosen" if chosen else "no_match", "requests": len(log),
                           "statuses": [x["status"] for x in log], "candidates": [c.summary() for c in ranked[:6]],
                           "chosen": chosen.summary() if chosen else None}
        except StageError as e:
            lrclib_info = {"status": "offline" if "offline" in str(e) else "error"}
            fallbacks.append("lyrics:lrclib_offline" if "offline" in str(e) else "lyrics:lrclib_error")
    instrumental_hint = False
    if chosen is not None:
        csrc = LR.candidate_source(chosen)
        if chosen.instrumental and not csrc["lines"]:
            instrumental_hint = True
        elif src is None:
            src, kind = csrc, "lrclib"
            lrclib_id, dd = chosen.id, chosen.duration_diff_s
        elif kind == "embedded" and not src["has_line_sync"] and csrc["has_line_sync"]:
            f1 = R.match_score([w for ln in csrc["lines"] for w in T.norm_words(ln["text"])],
                               [w for ln in src["lines"] for w in T.norm_words(ln["text"])])["f1"]
            if f1 >= 0.85:
                src, kind = csrc, "lrclib"
                lrclib_id, dd = chosen.id, chosen.duration_diff_s
                notes.append(f"embedded text agrees with LRCLIB {chosen.id} (F1 {f1:.2f}): LRCLIB timings used")
        if "version_mismatch" in chosen.flags and kind == "lrclib":
            warnings.append(f"LRCLIB entry differs from the file by {chosen.duration_diff_s:+.2f} s (version mismatch)")
    language = (src or {}).get("meta", {}).get("language") if src else None

    # ---------------------------------------------------------------- 2. ASR (always when there is a voice)
    asr: dict[str, Any] | None = None
    kept: list[dict[str, Any]] = []
    dropped: dict[str, int] = {}
    asr_engine = p.get("asr", "faster_whisper")
    if asr_engine != "off" and active_s >= float(p.get("min_active_s", 2.0)):
        try:
            if asr_engine == "ffmpeg_whisper":
                h = ctx.model(p.get("ggml_model", "ggml.whisper-large-v3-turbo-q8_0"))
                wav = ctx.scratch / "lead16k.wav"
                from mvh.io.wav import write_wav

                write_wav(wav, lead[None, :], 16000)
                asr = R.ffmpeg_whisper(wav, next(iter(h.files.values())), ctx.scratch, language=language or "en")
                models_used.append(h.id)
            else:
                h = ctx.model("faster_whisper_large_v3")
                mdir = next(iter(h.files.values())).parent
                wmodel = R.load_model(mdir, ctx.threads)
                asr = R.transcribe(lead, mdir, ctx.threads, language=language, vad=bool(p.get("asr_vad", True)),
                                   beam_size=int(p.get("asr_beam", 5)), model=wmodel)
                models_used.append(h.id)
            kept, dropped = R.filter_segments(asr["segments"], act, 100.0, min_word_p=float(p.get("asr_min_seg_p", 0.25)))
            # M5-D19: Silero VAD can discard a heavily processed voice (MEGAFAUNA: 2 words over 111 active s).
            # When the VAD pass hears far fewer words than the vocal activity implies, transcribe again without
            # VAD; the hallucination filter (activity mask included) guards the no-VAD output.
            n_vad = len(R.asr_words(kept))
            if (asr_engine == "faster_whisper" and asr.get("vad") and p.get("asr_vad_retry", True)
                    and active_s >= 10.0 and n_vad < float(p.get("asr_vad_retry_wps", 0.15)) * active_s):
                asr2 = R.transcribe(lead, mdir, ctx.threads, language=language or asr.get("language"), vad=False,
                                    beam_size=int(p.get("asr_beam", 5)), model=wmodel)
                kept2, dropped2 = R.filter_segments(asr2["segments"], act, 100.0, min_word_p=float(p.get("asr_min_seg_p", 0.25)))
                aw2 = R.asr_words(kept2)
                p2 = float(np.mean([w["p"] for w in aw2])) if aw2 else 0.0
                vad_retry = {"vad_words": n_vad, "no_vad_words": len(aw2), "no_vad_mean_p": round(p2, 4), "used": False}
                if len(aw2) > 2 * n_vad and len(aw2) >= int(p.get("min_transcribed_words", 8)) and p2 >= 0.5:
                    asr, kept, dropped = asr2, kept2, dropped2
                    vad_retry["used"] = True
                    fallbacks.append("lyrics:asr_no_vad")
                    notes.append(f"VAD kept {n_vad} ASR words over {active_s:.0f} s of vocals: transcribed again without VAD")
                asr["vad_retry"] = vad_retry
            # M5-D50: Silero VAD can also reject one long sung passage (Jeremy: nothing after 172 s of a 285 s vocal).
            # When a text exists, active lead-vocal spans >= asr_gap_min_s that no segment covers get a VAD-free
            # pass (with 1 s context); the hallucination filter guards it. Evidence for G1, the ASR repair and the
            # repeat expansion of an outro the text does not write out.
            if (asr_engine == "faster_whisper" and asr.get("vad") and src is not None and p.get("asr_gap_retry", True)
                    and not (asr.get("vad_retry") or {}).get("used")):
                regions = R.uncovered_regions(asr["segments"], act, 100.0, min_s=float(p.get("asr_gap_min_s", 6.0)))
                gap: dict[str, Any] = {"regions": len(regions), "seconds": round(sum(b - a for a, b in regions), 2),
                                       "segments": 0, "kept": 0, "words": 0}
                if regions:
                    extra = R.transcribe_regions(lead, regions, wmodel, language=language or asr.get("language"),
                                                 beam_size=int(p.get("asr_beam", 5)))
                    kx, dx = R.filter_segments(extra, act, 100.0, min_word_p=float(p.get("asr_min_seg_p", 0.25)))
                    asr["segments"] = sorted(asr["segments"] + extra, key=lambda z: (z["start"], z["end"]))
                    kept = sorted(kept + kx, key=lambda z: (z["start"], z["end"]))
                    for k_, v_ in dx.items():
                        dropped[k_] = dropped.get(k_, 0) + v_
                    dropped = dict(sorted(dropped.items()))
                    gap.update(segments=len(extra), kept=len(kx), words=len(R.asr_words(kx)))
                    if kx:
                        notes.append(f"VAD skipped {gap['seconds']:.0f} s of active vocals in {len(regions)} span(s): "
                                     f"a VAD-free pass there added {gap['words']} ASR words")
                asr["gap_retry"] = gap
        except StageError:
            raise
        except Exception as e:  # noqa: BLE001  (ASR is evidence, not a requirement)
            warnings.append(f"ASR failed ({type(e).__name__}); match score and expansion skipped")
            fallbacks.append("lyrics:asr_failed")
            asr = None
    if language is None and asr is not None and asr.get("language") and (asr.get("language_prob") or 0) >= 0.5 and len(kept) >= 2:
        language = asr["language"]
    aw = R.asr_words(kept)
    asr_mean_p = float(np.mean([w["p"] for w in aw if w["p"] is not None])) if any(w["p"] is not None for w in aw) else None

    # transcription as the source of last resort
    if instrumental_hint:
        # the flag is a user submission; trust it only when the ASR agrees (fewer than 8 confident words)
        n_conf = sum(1 for w in aw if (w.get("p") or 0.0) >= 0.5)
        if n_conf >= int(p.get("min_transcribed_words", 8)):
            instrumental_hint = False
            warnings.append(f"LRCLIB entry {chosen.id} is flagged instrumental but the ASR heard {n_conf} confident words: flag ignored")
            fallbacks.append("lyrics:instrumental_flag_ignored")
    if src is None and len(aw) >= int(p.get("min_transcribed_words", 8)) and not instrumental_hint:
        lines_t = []
        for s in kept:
            ws = [w for w in s["words"] if w["w"].strip()]
            chunk: list[dict[str, Any]] = []
            for w in ws:
                if chunk and (w["start"] - chunk[-1]["end"] > 0.8 or len(chunk) >= 14):
                    lines_t.append(chunk)
                    chunk = []
                chunk.append(w)
            if chunk:
                lines_t.append(chunk)
        src = {"format": "transcribed", "lines": [{"text": " ".join(w["w"].strip() for w in ch), "t": ch[0]["start"], "end": ch[-1]["end"],
                                                   "words": [{"text": w["w"].strip(), "t": w["start"], "p": w.get("p")} for w in ch],
                                                   "speaker": None, "backing": False, "origin": "transcribed"} for ch in lines_t],
               "meta": {}, "has_line_sync": True, "has_word_sync": True}
        kind = "transcribed"
        fallbacks.append("lyrics:transcribed")
    instrumental = src is None
    if instrumental and active_s >= 8.0:
        notes.append(f"no lyric source and {len(aw)} ASR words: treated as instrumental / wordless vocals")

    # ---------------------------------------------------------------- 3. alignment
    tm_dict: dict[str, int] | None = None
    aligner = None
    logp = None
    lines: list[dict[str, Any]] = []
    align_info: dict[str, Any] = {}
    pins: dict[int, float] = {}
    offset = 0.0
    offset_detected = None
    if not instrumental:
        h = ctx.model("mms_fa")
        models_used.append(h.id)
        aligner = A.MmsAligner(next(iter(h.files.values())), ctx.threads)
        tm_dict = aligner.dictionary
        tm = T.TokenMaker(tm_dict, language)
        for i, ln in enumerate(src["lines"]):
            lines.append(_mk_line(ln["text"], t=ln.get("t"), end=ln.get("end"), words_src=ln.get("words"),
                                  speaker=ln.get("speaker"), backing=ln.get("backing", False),
                                  origin=ln.get("origin", "source"), order=i, tm=tm))
        logp = aligner.emissions(lead, float(p.get("window_s", 30.0)), float(p.get("context_s", 2.0)))
        # D82: line pins (overrides lyrics.pins) are fixed points for everything below
        pins = _read_pins(lines, ctx.overrides, warnings)
        n_src = len(lines)
        pinned = [i in pins for i in range(n_src)]
        if pins:
            align_info["pins"] = len(pins)
            notes.append(f"{len(pins)} line start(s) pinned by the user (overrides lyrics.pins)")
        synced = bool(src.get("has_line_sync")) and all(x["src_t"] is not None for x in lines)
        if not synced and any(x["src_t"] is not None for x in lines):
            # partially timed (SRT continuation lines): interpolate the missing starts
            _fill_missing_times(lines, duration)
            synced = True
        if synced and pins:
            _pin_source_times(lines, pins, duration)
        mode = "synced" if synced else "anchored"
        ctxw = float(p.get("context_s", 2.0))
        slack = float(p.get("line_slack_s", 2.5))
        if synced:
            starts, ends = _expected(lines, duration)
        else:
            starts, ends, matched = _asr_anchors(lines, aw, act, duration, pins)
            align_info["anchor_matched_frac"] = round(matched, 3)
            if matched < float(p.get("min_anchor_frac", 0.25)) and not pins:
                mode = "whole_song"
            ctxw, slack = 3.0, 4.0
        if mode == "whole_song":
            _whole_song(lines, logp, act, duration)
            fallbacks.append("lyrics:whole_song_alignment")
            nts = {"groups": 1}
        else:
            res, n0 = A.align_groups(logp, starts, ends, [x["toks"] for x in lines], offset=0.0, ctx=ctxw, slack=slack,
                                     backing=[x["backing"] for x in lines], pins=pinned)
            nts = n0.as_dict()
            if synced and kind != "transcribed":
                devs = []
                for x, r in zip(lines, res):
                    ws = [a for a in r if a is not None]
                    if ws and x["src_t"] is not None and np.mean([a["score"] for a in ws]) >= 0.1:
                        devs.append(ws[0]["start"] - x["src_t"])
                if len(devs) >= 3:
                    offset_detected = float(np.median(devs))
                    if abs(offset_detected) > G.THRESHOLDS["offset_apply"]:
                        offset = offset_detected
                        res, n1 = A.align_groups(logp, starts, ends, [x["toks"] for x in lines], offset=offset, ctx=ctxw, slack=slack,
                                                 backing=[x["backing"] for x in lines], pins=pinned)
                        nts = n1.as_dict()
            for x, r in zip(lines, res):
                x["wres"] = r
        align_info.update({"mode": mode, "notes": nts})
        if nts.get("crossings_left") or nts.get("lines_off_gt2s"):
            warnings.append(f"alignment: {nts.get('crossings_left', 0)} adjacent line pair(s) interleave and "
                            f"{nts.get('lines_off_gt2s', 0)} line(s) start more than 2 s from the source time; review those lines")
        # ---------------- 3a. ASR-guided repair of words CTC parked far from where the ASR heard them
        if aw and kind != "transcribed" and p.get("asr_repair", True):
            bounds = None
            if mode == "synced":
                bounds = [(st - slack + offset, en + slack + offset) for st, en in zip(starts, ends)]
            if pins and mode != "whole_song":
                # no word is repaired across a pin (the same words are sung in every pass of a hook)
                bounds = _pin_bounds(bounds or [(st - slack, en + slack) for st, en in zip(starts, ends)], pins)
            align_info["asr_repaired_words"] = _asr_repair(lines, aw, logp, bounds=bounds)
            if align_info["asr_repaired_words"]:
                firsts = [next((z for z in x["wres"] if z is not None), None) for x in lines if not x.get("backing")]
                lasts = [next((z for z in reversed(x["wres"]) if z is not None), None) for x in lines if not x.get("backing")]
                n_cross = sum(1 for a, b in zip(lasts, firsts[1:]) if a is not None and b is not None and a["start"] > b["start"] + 0.05)
                if n_cross > (nts.get("crossings_left") or 0):
                    warnings.append(f"alignment: {n_cross} adjacent line pair(s) interleave after the ASR repair; review those lines")
        # ---------------- 3b. repeat expansion and ASR-only lines (only ADD lines)
        added = {"expanded": 0, "asr_only": 0}
        if p.get("expand", True) and kept and kind != "transcribed":
            new = _expansion(lines, kept, synced and mode == "synced", offset, act, tm, allow_asr_only=bool(p.get("asr_only_lines", True)))
            if new:
                st2 = [x["src_t"] for x in new]
                en2 = [x["src_end"] for x in new]
                res2, _n2 = A.align_groups(logp, st2, en2, [x["toks"] for x in new], offset=0.0, ctx=1.0, slack=2.0)
                for x, r in zip(new, res2):
                    x["wres"] = r
                    added[x["origin"]] += 1
                lines += new
        align_info["added_lines"] = added
        if added["expanded"]:
            notes.append(f"repeat expansion added {added['expanded']} line(s) from the ASR pass")
        if added["asr_only"]:
            notes.append(f"{added['asr_only']} ASR-only line(s) outside the supplied text (e.g. a spoken intro)")

        # ---------------- 3c. stable-ts fallback when coverage is low
        cov = _coverage(lines)
        if cov < float(p.get("stable_ts_below_coverage", 0.6)) and p.get("stable_ts", True) and kind != "transcribed":
            try:
                h = ctx.model("faster_whisper_large_v3")
                n_rep = _stable_ts(lines, lead, next(iter(h.files.values())).parent, ctx.threads, language)
                fallbacks.append("lyrics:stable_ts")
                align_info["stable_ts_lines"] = n_rep
                notes.append(f"stable-ts fallback replaced {n_rep} weak line(s) (coverage {cov:.2f} < 0.60)")
            except Exception as e:  # noqa: BLE001
                warnings.append(f"stable-ts fallback failed ({type(e).__name__})")

    # ---------------------------------------------------------------- 4. final word times
    if pins:
        align_info["pins_moved_lines"] = _enforce_pins(lines, pins, n_src)
    for x in lines:
        _finalise_line(x, 0.0 if x.get("pinned") else offset, env, sustain_floor, kind, mode=align_info.get("mode"))
    # D83: the ids as numbered without splits (what an id key in overrides.json means), the splits of a source line
    # into bars, then stable references for every line and word
    _assign_legacy_ids(lines)
    lines = _apply_splits(lines, ctx.overrides, warnings)
    if any(x.get("part") is not None for x in lines):
        align_info["split_lines"] = len({x["order"] for x in lines if x.get("part") is not None})
    _assign_refs(lines)
    _apply_overrides(lines, ctx.overrides, warnings)
    lines = [x for x in lines if x["wt"]]
    lines.sort(key=lambda x: (round(x["wt"][0], 3), x["order"]))
    _cap_line_tails(lines)

    # ---------------------------------------------------------------- 5. metrics, ids, groups, confidence
    asr_exact = [w["n"] for w in aw]
    ref = [(li, wi, n) for li, x in enumerate(lines) for wi, w in enumerate(x["words"]) for n in T.norm_words(w)[:1]]
    ref_norm = [n for _, _, n in ref]
    asr_norm, n_snap = asr_exact, 0
    if kind != "transcribed" and aw and ref:
        # M5-D53: near-miss spellings of the text word sung at the same place count as agreement
        asr_norm, n_snap = R.canonicalise(aw, [(lines[li]["wt"][wi], n) for li, wi, n in ref])
    ms = ms_raw = None
    g1_scope: dict[str, Any] | None = None
    if kind != "transcribed" and aw:
        # M5-D51: G1 is judged where BOTH sides have evidence. ASR words outside the span the text covers (an outro
        # without lines) and text words where the ASR heard nothing (VAD gaps) say nothing about a wrong text; the
        # missing outro is handled by expansion / ASR-only lines, the deaf ASR by the gap retry.
        ms_raw = R.match_score(asr_exact, ref_norm)
        t_spans = _merge_spans([(x["wt"][0] - 1.0, max(t + d for t, d in zip(x["wt"], x["wd"])) + 1.0) for x in lines if x["wt"]])
        a_spans = _merge_spans([(s0["start"] - 1.0, s0["end"] + 1.0) for s0 in kept])
        a_in = [n for w, n in zip(aw, asr_norm) if _inside(w["start"], t_spans)]
        r_in = [n for li, wi, n in ref if _inside(lines[li]["wt"][wi], a_spans)]
        ms = R.match_score(a_in, r_in)
        g1_scope = {"asr_words": len(a_in), "asr_words_total": len(asr_norm), "text_words": len(r_in),
                    "text_words_total": len(ref_norm), "near_miss_words": n_snap, "raw_f1": ms_raw["f1"]}
    pairs = []
    matched_word: set[tuple[int, int]] = set()
    if aw and ref and kind != "transcribed":
        for ia, ib in R.lcs_pairs(asr_exact, ref_norm):     # G7 / per-word check: exact words (calibrated)
            li, wi, _ = ref[ib]
            pairs.append((lines[li]["wt"][wi], aw[ia]["start"]))
            matched_word.add((li, wi))
    agree = G.asr_agreement(pairs) if pairs else None
    scores = [r["score"] for x in lines for r in x["wres"] if r is not None]
    toks_sc = [s for x in lines for r in x["wres"] if r is not None for s in r["tok_scores"]]
    n_words = sum(len(x["words"]) for x in lines)
    cov = (sum(1 for s in scores if s >= 0.10) / n_words) if n_words else 0.0
    hard = (sum(1 for x in lines for r in x["wres"] if r is None or r["score"] < 0.01) / n_words) if n_words else 0.0
    synced_src = kind in ("lrclib", "user", "embedded") and bool(src and src.get("has_line_sync"))
    devs = [x["dev"] for x in lines if x["dev"] is not None and x["origin"] == "source"]
    g5 = (sum(1 for d in devs if d <= 1.0) / len(devs)) if (synced_src and devs) else None
    onsets = G.vocal_onsets(lead) if lines else np.zeros(0)
    lift = G.onset_lift(onsets, [t for x in lines for t in x["wt"]]) if lines else None
    gate = G.gate({"G1": ms["f1"] if ms else None, "G2": round(cov, 4), "G3": round(float(np.mean(toks_sc)), 4) if toks_sc else 0.0,
                   "G4": round(hard, 4), "G5": round(g5, 4) if g5 is not None else None,
                   "offset_s": round(offset_detected, 3) if offset_detected is not None else None,
                   "G7": agree, "G8": lift, "transcribed": kind == "transcribed", "asr_mean_p": asr_mean_p,
                   "asr_words": (g1_scope["asr_words"] if g1_scope else len(aw)) if asr is not None else None}) if lines else None

    tg_ids: dict[str, str] = {}
    keys = [T.line_key(x["text"]) for x in lines]
    for k in keys:
        if k not in tg_ids:
            tg_ids[k] = f"T{len(tg_ids) + 1:02d}"
    lg = _repeat_groups(keys)
    out_lines, out_words = [], []
    for li, x in enumerate(lines):
        lid = f"L{li + 1:03d}"
        wconf = []
        for wi, w in enumerate(x["words"]):
            r = x["wres"][wi]
            asr_ok = None if not aw or kind == "transcribed" else ((li, wi) in matched_word)
            if kind == "transcribed" and x["wp"][wi] is not None:
                c = round(min(1.0, 0.5 * _word_conf(r["score"] if r else None, None, True) + 0.5 * x["wp"][wi]), 4)
            else:
                c = _word_conf(r["score"] if r else None, asr_ok, x["dev"] is None or x["dev"] <= 1.0)
            wconf.append(c)
            wd = {"id": f"{lid}.{wi + 1:02d}", "line_id": lid, "t": round(x["wt"][wi], 6), "d": round(max(0.02, x["wd"][wi]), 6),
                  "text": w, "conf": c}
            if x.get("ref"):
                wd["ref"] = f"r{x['order']}w{x['word0'] + wi}"   # D83: stable: the word's place in the lyric source
            fl = []
            if r is None:
                fl.append("interpolated")
            elif r.get("repaired"):
                fl.append("asr_repaired")
            if x["origin"] in ("expanded", "asr_only"):
                fl.append(x["origin"])
            if x["backing"] or (w.startswith("(") or w.endswith(")")):
                fl.append("backing")
            if fl:
                wd["flags"] = fl
            out_words.append(wd)
        t0, t1 = _line_span(x)
        conf = round(float(np.mean(wconf)) if wconf else 0.0, 4)
        out_lines.append({
            "id": lid, "t": round(t0, 6), "d": round(max(0.05, t1 - t0), 6), "text": x["text"],
            "section_id": _sections_at(sections, t0, t1) if sections else None, "text_group": tg_ids[keys[li]],
            "repeat_group": lg.get(li), "conf": conf, "grade": G.line_grade(conf), "first_word": f"{lid}.01" if x["words"] else None,
            "n_words": len(x["words"]), "backing": bool(x["backing"]), "speaker_hint": x["speaker"],
            "timing_source": x["timing_source"],
            # D82: what a pin of this line is keyed by (its position in the lyric source and a hash of its text)
            "source_index": int(x["order"]) if x["origin"] in ("source", "transcribed") else None,
            "pin_key": _pin_key(x["source_text"] if x.get("source_text") else x["text"]), "pinned": bool(x.get("pinned")),
            # D83: stable reference (r<source index>, p<part> for a split bar) and the first word's place in the source line
            "ref": x.get("ref"), "source_part": x.get("part"), "source_word": x.get("word0", 0) if x.get("ref") else None,
            "legacy_id": x.get("legacy_id"),
        })
    n_lines_out = len(out_lines)
    # M5-D52: lead-vocal activity after the last line (Jeremy's 217-300 s outro is wordless singing, SPIKE
    # bench-words §2): reported and flagged for review, never filled with invented lines.
    if out_lines:
        t_last = max(ln["t"] + ln["d"] for ln in out_lines)
        tail_s = float(np.sum(act[min(len(act), int((t_last + 2.0) * 100)):] > 0.5)) / 100.0
        align_info["vocals_after_last_line_s"] = round(tail_s, 2)
        if tail_s >= float(p.get("tail_vocals_warn_s", 20.0)):
            heard = sum(1 for w in aw if w["start"] > t_last + 2.0)
            warnings.append(f"{tail_s:.0f} s of lead vocals after the last lyric line ({heard} ASR words there): wordless "
                            f"singing or lines missing from the text; review the outro in the viewer")
    for ln in out_lines:
        if ln["n_words"] == 0:
            ln["first_word"] = None

    grade = gate["grade"] if gate else None
    coverage = round(cov, 4) if lines else 0.0
    doc = {
        "schema": "mvh/files/lyrics", "schema_version": _contract_version(),
        "source": {"kind": kind if lines else ("none" if not instrumental_hint else "lrclib"), "lrclib_id": lrclib_id,
                   "duration_diff_s": dd, "has_word_sync": bool(src and src.get("has_word_sync")),
                   # additive (docs/contract/decisions/M5.md)
                   "format": (src or {}).get("format"), "offset_s": round(offset_detected, 3) if offset_detected is not None else None,
                   "offset_applied_s": round(offset, 3), "version_mismatch": bool(offset_detected is not None and abs(offset_detected) > 3.0)
                   or bool(chosen is not None and "version_mismatch" in chosen.flags and kind == "lrclib")},
        "instrumental": bool(instrumental or not out_lines), "language": language if out_lines else None, "grade": grade,
        "lyrics_match_score": ms["f1"] if ms else None, "coverage": coverage,
        "lines": out_lines, "words": out_words,
        # additive
        "gate": gate, "asr": {"engine": (asr or {}).get("engine"), "segments": len((asr or {}).get("segments") or []),
                              "kept": len(kept), "words": len(aw), "dropped": dropped,
                              "vad": (asr or {}).get("vad"), "vad_retry": (asr or {}).get("vad_retry"),
                              "mean_word_p": round(asr_mean_p, 4) if asr_mean_p is not None else None,
                              "precision": ms["precision"] if ms else None, "recall": ms["recall"] if ms else None,
                              "g1_scope": g1_scope, "gap_retry": (asr or {}).get("gap_retry")},
        "alignment": {**align_info, "activity_source": act_src, "active_s": round(active_s, 2), "stem": stem_name,
                      "vocals_regions": [[round(a, 2), round(b, 2)] for a, b in vocals_regions]},
        "lrclib": lrclib_info,
    }
    ctx.writer.json("lyrics/lyrics.json", doc)
    meta = {"title": title, "artist": artist, "album": album, "duration_s": duration}
    ctx.writer.text("lyrics/lyrics.lrc", X.to_lrc(meta, out_lines, out_words))
    ctx.writer.text("lyrics/lyrics.vtt", X.to_vtt(out_lines, out_words))
    ctx.writer.text("lyrics/lyrics.srt", X.to_srt(out_lines))
    ctx.writer.text("lyrics/lyrics.ass", X.to_ass(meta, out_lines, out_words))

    last_word_end = max((w["t"] + w["d"] for w in out_words), default=None)
    summary = {"source": doc["source"]["kind"], "lrclib_id": lrclib_id, "grade": grade, "lines": n_lines_out,
               "words": len(out_words), "coverage": coverage, "lyrics_match_score": doc["lyrics_match_score"],
               "offset_s": doc["source"]["offset_s"], "instrumental": doc["instrumental"], "language": doc["language"],
               "last_word_end_s": round(last_word_end, 2) if last_word_end is not None else None,
               "speaker_hints": len({x["speaker_hint"] for x in out_lines if x["speaker_hint"]})}
    if grade in ("C", "D"):
        warnings.append(f"lyrics grade {grade}: check the alignment in the viewer")
    if doc["source"]["version_mismatch"]:
        warnings.append("lyrics source looks like another version (offset > 3 s or duration mismatch)")
    status = "degraded" if any(f in fallbacks for f in ("lyrics:stable_ts", "lyrics:whole_song_alignment", "lyrics:asr_failed")) else "ok"
    conf = {"A": 0.9, "B": 0.75, "C": 0.5, "D": 0.25}.get(grade or "", None)
    tools = [{"name": "uroman", "version": _ver("uroman")}, {"name": "num2words", "version": _ver("num2words")},
             {"name": "torchaudio", "version": _ver("torchaudio")}, {"name": "faster-whisper", "version": _ver("faster-whisper")}]
    return StageResult(status=status, summary=summary, warnings=warnings, fallbacks=fallbacks, confidence=conf,
                       provenance={"notes": notes, "tools": tools, "align_engine": (align_info.get("notes") or {}).get("engine")})


def _merge_spans(spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[list[float]] = []
    for a, b in sorted(spans):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def _inside(t: float, spans: list[tuple[float, float]]) -> bool:
    return any(a <= t <= b for a, b in spans)


def _ver(pkg: str) -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(pkg)
    except PackageNotFoundError:
        return "unknown"


def _contract_version() -> str:
    from mvh.contract.catalog import CONTRACT_VERSION

    return CONTRACT_VERSION


# ------------------------------------------------------------------------------------------ expected times
def _fill_missing_times(lines: list[dict[str, Any]], duration: float) -> None:
    known = [i for i, x in enumerate(lines) if x["src_t"] is not None]
    for i, x in enumerate(lines):
        if x["src_t"] is not None:
            continue
        prev = max((k for k in known if k < i), default=None)
        nxt = min((k for k in known if k > i), default=None)
        if prev is not None and nxt is not None:
            a, b = lines[prev]["src_t"], lines[nxt]["src_t"]
            x["src_t"] = a + (b - a) * (i - prev) / (nxt - prev)
        elif prev is not None:
            x["src_t"] = min(duration, lines[prev]["src_t"] + 2.5 * (i - prev))
        elif nxt is not None:
            x["src_t"] = max(0.0, lines[nxt]["src_t"] - 2.5 * (nxt - i))


def _expected(lines: list[dict[str, Any]], duration: float) -> tuple[list[float], list[float]]:
    starts = [float(x["src_t"]) for x in lines]
    ends = []
    for i, x in enumerate(lines):
        nxt = starts[i + 1] if i + 1 < len(lines) else None
        e = x["src_end"]
        if e is None or e <= starts[i]:
            e = nxt if nxt is not None and nxt > starts[i] else starts[i] + max(2.0, 0.45 * len(x["words"]))
        e = min(e, starts[i] + max(8.0, 0.6 * len(x["words"])))
        ends.append(float(min(e, duration)))
    return starts, ends


def _pin_key(text: str) -> str:
    """A short hash of a line's normalised text: a pin stays with its line only while the text is the same."""
    import hashlib

    return hashlib.sha1(T.line_key(text).encode("utf-8")).hexdigest()[:10]


def _read_pins(lines: list[dict[str, Any]], ovr: dict[str, Any], warnings: list[str]) -> dict[int, float]:
    """overrides ``lyrics.pins`` [{index, t, key?, line?}] -> {line index in the lyric source: start time}.
    A pin whose index is out of range, whose ``key`` no longer matches the text at that index (the lyrics changed
    since it was set), or that goes backwards in time against an earlier pin is ignored with a warning."""
    pins: dict[int, float] = {}
    miss = 0
    for r in ovr.get("lyrics.pins") or []:
        try:
            i, t = int(r["index"]), float(r["t"])
        except (KeyError, TypeError, ValueError):
            miss += 1
            continue
        if not (0 <= i < len(lines)) or t < 0 or (r.get("key") and r["key"] != _pin_key(lines[i]["text"])):
            miss += 1
            continue
        pins[i] = t
    back = 0
    last = -1.0
    for i in sorted(pins):
        if pins[i] <= last:
            del pins[i]
            back += 1
        else:
            last = pins[i]
    if miss:
        warnings.append(f"{miss} lyric pin(s) no longer match the lyric text (it changed since they were set); ignored")
    if back:
        warnings.append(f"{back} lyric pin(s) are earlier than the pin of a line before them; ignored")
    for i in pins:
        lines[i]["pinned"] = True
    return pins


def _pin_span(pins: dict[int, float], i: int) -> tuple[float | None, float | None]:
    """The pin times around line ``i``: (the nearest pin at or before it, the nearest pin after it)."""
    lo = max((k for k in pins if k <= i), default=None)
    hi = min((k for k in pins if k > i), default=None)
    return (pins[lo] if lo is not None else None), (pins[hi] if hi is not None else None)


def _pin_source_times(lines: list[dict[str, Any]], pins: dict[int, float], duration: float) -> None:
    """Synced sources: a pinned line takes the pin as its source time (its own word times move with it); a source
    time of another line that falls on the wrong side of a pin is forgotten and interpolated."""
    for i, t in pins.items():
        x = lines[i]
        d = t - float(x["src_t"])
        x["src_t"] = t
        if x["src_end"] is not None:
            x["src_end"] = float(x["src_end"]) + d
        x["src_wt"] = [None if w is None else float(w) + d for w in x["src_wt"]]
    dropped = False
    for i, x in enumerate(lines):
        if i in pins:
            continue
        lo = max((pins[k] for k in pins if k < i), default=None)
        hi = min((pins[k] for k in pins if k > i), default=None)
        if (lo is not None and x["src_t"] <= lo) or (hi is not None and x["src_t"] >= hi):
            x["src_t"], x["src_end"] = None, None
            x["src_wt"] = [None] * len(x["src_wt"])
            dropped = True
    if dropped:
        _fill_missing_times(lines, duration)


def _pin_bounds(bounds: list[tuple[float, float]], pins: dict[int, float]) -> list[tuple[float, float]]:
    """Per-line (lo, hi) windows clipped to the pins around each line."""
    out = []
    for i, (lo, hi) in enumerate(bounds):
        a, b = _pin_span(pins, i)
        if a is not None:
            lo = max(lo, a - A.PIN_TOL)
        if b is not None:
            hi = min(hi, b + A.SEAM_MARGIN_S)
        out.append((lo, max(hi, lo + 0.2)))
    return out


def _enforce_pins(lines: list[dict[str, Any]], pins: dict[int, float], n_src: int) -> int:
    """A pin is a fixed point. After every alignment and repair pass: a pinned line whose first aligned word is
    more than PIN_TOL from the pin is moved as a whole so that it starts on the pin; an unpinned line that ended
    up outside the pins around it is moved to its expected start. Returns the number of lines moved."""
    moved = 0
    for i, x in enumerate(lines[:n_src]):
        ws = [r for r in x["wres"] if r is not None]
        if not ws:
            continue
        first = ws[0]["start"]
        if i in pins:
            d = pins[i] - first
            if abs(d) <= A.PIN_TOL:
                continue
        else:
            lo = max((pins[k] for k in pins if k < i), default=None)
            hi = min((pins[k] for k in pins if k > i), default=None)
            if (lo is None or first > lo) and (hi is None or first < hi):
                continue
            if x["src_t"] is None:
                continue
            d = float(x["src_t"]) - first
        for r in ws:
            r["start"] += d
            r["end"] += d
        moved += 1
    return moved


def _asr_anchors(lines: list[dict[str, Any]], aw: list[dict[str, Any]], act: np.ndarray, duration: float,
                 pins: dict[int, float] | None = None) -> tuple[list[float], list[float], float]:
    """Expected line times for an untimed text from LCS-matched ASR words; unmatched lines are spread
    between their neighbours by word count. ``pins`` (D82): {line index: start} fixed by the user; an ASR anchor on
    the wrong side of a pin is dropped (a repeated line heard in another pass), and the lines from a pin to the next
    known start share that span by word count. Returns (starts, ends, matched fraction of reference words)."""
    pins = pins or {}
    ref, owner = [], []
    for li, x in enumerate(lines):
        for wi, w in enumerate(x["words"]):
            for n in T.norm_words(w)[:1]:
                ref.append(n)
                owner.append((li, wi))
    pairs = R.lcs_pairs([w["n"] for w in aw], ref) if aw and ref else []
    per_line: dict[int, list[tuple[int, float, float]]] = {}
    for ia, ib in pairs:
        li, wi = owner[ib]
        per_line.setdefault(li, []).append((wi, aw[ia]["start"], aw[ia]["end"]))
    starts: list[float | None] = [None] * len(lines)
    ends: list[float | None] = [None] * len(lines)
    for li, lst in per_line.items():
        lst.sort()
        n = len(lines[li]["words"])
        starts[li] = max(0.0, lst[0][1] - 0.35 * lst[0][0])
        ends[li] = min(duration, lst[-1][2] + 0.35 * (n - 1 - lst[-1][0]))
    for li in range(len(lines)):
        if not pins or li in pins or starts[li] is None:
            continue
        lo = max((pins[k] for k in pins if k < li), default=None)
        hi = min((pins[k] for k in pins if k > li), default=None)
        if (lo is not None and starts[li] <= lo) or (hi is not None and (starts[li] >= hi or ends[li] > hi + 1.0)):
            starts[li] = ends[li] = None
    for li, t in pins.items():
        if starts[li] is None or abs(starts[li] - t) > 1.0 or ends[li] <= t:
            ends[li] = None  # the ASR heard this line elsewhere: its end says nothing about the pinned place
        starts[li] = t
    # monotonic clean-up: an anchor that goes backwards is dropped
    last = -1.0
    for li in range(len(lines)):
        if li in pins:
            last = max(last, starts[li])
        elif starts[li] is not None:
            if starts[li] < last - 1.0:
                starts[li] = ends[li] = None
            else:
                last = max(last, starts[li])
    for li in sorted(pins):  # a pinned line without a known end shares the span to the next known start
        if ends[li] is not None:
            continue
        nxt = next((k for k in range(li + 1, len(lines)) if starts[k] is not None), None)
        wc = max(1, len(lines[li]["words"]))
        if nxt is None:
            ends[li] = min(duration, starts[li] + 0.45 * wc)
        else:
            tot = wc + sum(max(1, len(lines[k]["words"])) for k in range(li + 1, nxt))
            ends[li] = starts[li] + (starts[nxt] - starts[li]) * wc / tot
    if pins:
        known = [i for i in range(len(lines)) if starts[i] is not None]
        for a, b in zip(known, known[1:]):
            if ends[a] > starts[b]:
                ends[a] = starts[b]
    act_t = np.flatnonzero(np.asarray(act) > 0.5) / 100.0
    first_act = float(act_t[0]) if len(act_t) else 0.0
    last_act = float(act_t[-1]) if len(act_t) else duration
    idx = [i for i in range(len(lines)) if starts[i] is not None]
    for i in range(len(lines)):
        if starts[i] is not None:
            continue
        prev = max((k for k in idx if k < i), default=None)
        nxt = min((k for k in idx if k > i), default=None)
        wc = max(1, len(lines[i]["words"]))
        if prev is not None and nxt is not None:
            a, b = ends[prev], starts[nxt]
            between = list(range(prev + 1, nxt))
            tot = sum(max(1, len(lines[k]["words"])) for k in between)
            off = sum(max(1, len(lines[k]["words"])) for k in between if k < i)
            starts[i] = a + (b - a) * off / tot
            ends[i] = a + (b - a) * (off + wc) / tot
        elif prev is not None:
            starts[i] = min(last_act, ends[prev] + 0.3)
            ends[i] = min(duration, starts[i] + 0.45 * wc)
            idx.append(i)
            idx.sort()
        elif nxt is not None:
            ends[i] = max(first_act, starts[nxt] - 0.3)
            starts[i] = max(0.0, ends[i] - 0.45 * wc)
        else:
            starts[i], ends[i] = first_act, last_act
    for i in range(len(lines)):
        lines[i]["src_t"] = float(starts[i])
        lines[i]["src_end"] = float(max(ends[i], starts[i] + 0.3))
    frac = len(pairs) / max(1, len(ref))
    return [float(s) for s in starts], [float(max(e, s + 0.3)) for s, e in zip(starts, ends)], frac


def _whole_song(lines: list[dict[str, Any]], logp: np.ndarray, act: np.ndarray, duration: float) -> None:
    act_t = np.flatnonzero(np.asarray(act) > 0.5) / 100.0
    t0 = max(0.0, (float(act_t[0]) if len(act_t) else 0.0) - 1.0)
    t1 = min(duration, (float(act_t[-1]) if len(act_t) else duration) + 1.0)
    idx = [(li, wi) for li, x in enumerate(lines) for wi, tk in enumerate(x["toks"]) if tk]
    try:
        al = A.align_window(logp, int(t0 / A.FR), int(t1 / A.FR) + 1, [lines[li]["toks"][wi] for li, wi in idx])
    except ValueError:
        al = A.align_window(logp, 0, len(logp), [lines[li]["toks"][wi] for li, wi in idx])
    for (li, wi), a in zip(idx, al):
        lines[li]["wres"][wi] = a
    for x in lines:
        ws = [r for r in x["wres"] if r is not None]
        if ws:
            x["src_t"], x["src_end"] = ws[0]["start"], ws[-1]["end"]


def _coverage(lines: list[dict[str, Any]]) -> float:
    n = sum(len(x["words"]) for x in lines)
    good = sum(1 for x in lines for r in x["wres"] if r is not None and r["score"] >= 0.10)
    return good / n if n else 1.0


# ------------------------------------------------------------------------------------------ ASR repair
def _asr_repair(lines: list[dict[str, Any]], aw: list[dict[str, Any]], logp: np.ndarray, max_dev: float = 1.0,
                bounds: list[tuple[float, float]] | None = None) -> int:
    """CTC sometimes parks a line's first (or last) word in the neighbouring silence (a word starting with the
    sound the previous word ended on). Words whose LCS-matched ASR word is more than ``max_dev`` from the CTC
    time (after removing the median bias) are re-aligned as a run in a tight window around the ASR times;
    the new placement is kept when its mean score is >= max(0.05, 0.5 x the old one) and the ASR words are confident (p >= 0.5). Returns the repaired word count."""
    ref, owner = [], []
    for li, x in enumerate(lines):
        for wi, w in enumerate(x["words"]):
            for n in T.norm_words(w)[:1]:
                ref.append(n)
                owner.append((li, wi))
    pairs = R.lcs_pairs([w["n"] for w in aw], ref)
    asr_of: dict[tuple[int, int], dict[str, Any]] = {}
    d = []
    for ia, ib in pairs:
        li, wi = owner[ib]
        r = lines[li]["wres"][wi]
        asr_of[(li, wi)] = aw[ia]
        if r is not None:
            d.append(r["start"] - aw[ia]["start"])
    if len(d) < 5:
        return 0
    bias = float(np.median(d))
    if abs(bias) > 0.5:
        return 0
    fixed = 0
    for li, x in enumerate(lines):
        bad = []
        for wi, r in enumerate(x["wres"]):
            a = asr_of.get((li, wi))
            if (r is not None and a is not None and abs(r["start"] - (a["start"] + bias)) > max_dev and x["toks"][wi]
                    and (a.get("p") is None or a["p"] >= 0.5)):
                bad.append(wi)
        if not bad:
            continue
        runs: list[list[int]] = []
        for wi in bad:
            if runs and wi == runs[-1][-1] + 1:
                runs[-1].append(wi)
            else:
                runs.append([wi])
        for run in runs:
            a0 = asr_of[(li, run[0])]["start"] + bias - 0.6
            a1 = asr_of[(li, run[-1])]["end"] + bias + 0.6
            prev = [x["wres"][k] for k in range(run[0]) if x["wres"][k] is not None and k not in bad]
            nxt = [x["wres"][k] for k in range(run[-1] + 1, len(x["wres"])) if x["wres"][k] is not None and k not in bad]
            if prev:
                a0 = max(a0, prev[-1]["end"])
            if nxt:
                a1 = min(a1, nxt[0]["start"])
            # never into a neighbouring line's audio: clip to the previous line's last / next line's first placed word
            # (backing lines may overlap their neighbours and are skipped); an ASR time on the far side of that
            # edge is another occurrence of the word
            lo_edge = next((z["end"] for lj in range(li - 1, -1, -1) if not lines[lj].get("backing")
                            for z in reversed(lines[lj]["wres"]) if z is not None), None)
            hi_edge = next((z["start"] for lj in range(li + 1, len(lines)) if not lines[lj].get("backing")
                            for z in lines[lj]["wres"] if z is not None), None)
            t_a0 = asr_of[(li, run[0])]["start"] + bias
            t_a1 = asr_of[(li, run[-1])]["start"] + bias
            if (hi_edge is not None and t_a1 > hi_edge - 0.1) or (lo_edge is not None and t_a0 < lo_edge - 0.1):
                continue
            if lo_edge is not None:
                a0 = max(a0, lo_edge)
            if hi_edge is not None:
                a1 = min(a1, hi_edge)
            if bounds is not None and li < len(bounds):
                # a synced source pins the line: an ASR match outside its window is another occurrence of the word
                if a0 + 0.6 < bounds[li][0] or a1 - 0.6 > bounds[li][1]:
                    continue
                a0, a1 = max(a0, bounds[li][0]), min(a1, bounds[li][1])
            if a1 - a0 < 0.1:
                continue
            old = float(np.mean([x["wres"][k]["score"] for k in run]))
            try:
                al = A.align_window(logp, int(a0 / A.FR), int(np.ceil(a1 / A.FR)), [x["toks"][k] for k in run])
            except ValueError:
                continue
            # judged on its own score (the misplaced words' score is inflated by the wrong placement): the ASR
            # corroborates the new time and the window is pinned by the neighbours / the source line
            if float(np.mean([z["score"] for z in al])) >= max(0.05, min(0.5 * old, 0.10)):
                for k, z in zip(run, al):
                    z["repaired"] = True
                    x["wres"][k] = z
                fixed += len(run)
    return fixed


# ------------------------------------------------------------------------------------------ expansion
def _seg_text_score(a: str, b: str) -> float:
    from rapidfuzz import fuzz

    if len(a) <= 3 or not b:
        return 0.0
    return 0.5 * fuzz.token_set_ratio(a, b) + 0.5 * fuzz.ratio(a, b)


def _expansion(lines: list[dict[str, Any]], kept: list[dict[str, Any]], synced: bool, offset: float, act: np.ndarray,
               tm: T.TokenMaker, allow_asr_only: bool = True) -> list[dict[str, Any]]:
    """ADD lines heard by the ASR that the aligned text does not cover: repeats of supplied lines (fuzzy match of
    1-3 consecutive unique lines >= 60) and, outside the lyric span or in gaps >= 4 s, confident ASR-only lines."""
    spans = []
    for x in lines:
        ws = [r for r in x["wres"] if r is not None]
        if ws:
            spans.append((ws[0]["start"] - 0.3, ws[-1]["end"] + 0.6))
        elif x["src_t"] is not None:
            spans.append((x["src_t"] + offset - 0.3, (x["src_end"] or x["src_t"] + 2) + offset + 0.3))
    spans.sort()
    if not spans:
        return []
    lyric_t0, lyric_t1 = spans[0][0], max(b for _, b in spans)
    uniq: list[tuple[str, dict[str, Any]]] = []
    seen = set()
    for x in sorted(lines, key=lambda z: z["order"]):
        k = T.line_key(x["text"])
        if k and k not in seen:
            seen.add(k)
            uniq.append((k, x))
    new: list[dict[str, Any]] = []
    order = max(x["order"] for x in lines) + 1
    for s in kept:
        ws = [w for w in s["words"] if w["w"].strip()]
        if len(ws) < 3:
            continue
        a, b = s["start"], s["end"]
        dur = max(0.05, b - a)
        cov = sum(max(0.0, min(b, e) - max(a, t)) for t, e in spans) / dur
        if cov >= 0.3:
            continue
        ps = [w["p"] for w in ws if w.get("p") is not None]
        mp = float(np.mean(ps)) if ps else 0.6
        if mp < 0.5:
            continue
        near_src = synced and any(x["src_t"] is not None and a - 2.0 <= x["src_t"] + offset <= b + 2.0 for x in lines if x["origin"] == "source")
        st = " ".join(T.norm_words(s["text"]))
        best, best_sc = None, 0.0
        for i in range(len(uniq)):
            for n in (1, 2, 3):
                if i + n > len(uniq):
                    break
                cand = " ".join(k for k, _ in uniq[i:i + n])
                sc = _seg_text_score(st, cand)
                if sc > best_sc + 1e-9:
                    best, best_sc = [x for _, x in uniq[i:i + n]], sc
        if best is not None and best_sc >= 60.0:
            if near_src:
                continue          # the source already puts a line here: this is that line heard early/late
            tot = sum(max(1, len(x["words"])) for x in best)
            cur = a
            for x in best:
                share = dur * max(1, len(x["words"])) / tot
                nl = _mk_line(x["text"], t=cur, end=cur + share, speaker=x["speaker"], backing=x["backing"],
                              origin="expanded", order=order, tm=tm)
                order += 1
                new.append(nl)
                cur += share
            spans.append((a, b))
            continue
        gap_ok = all(not (t - 4.0 < a and b < e + 4.0) for t, e in spans)
        beyond = b < lyric_t0 or a > lyric_t1
        outside = beyond or gap_ok
        # before the first / after the last lyric line (a spoken intro: newton's announcer, p 0.65, fuzzy 51 because
        # it names the rappers) anything that is not a repeat (< 60) with p >= 0.6 is added; inside the lyric span a
        # gap line needs p >= 0.7 and no resemblance (< 45) to a supplied line
        if (allow_asr_only and outside and mp >= (0.6 if beyond else 0.7) and best_sc < (60.0 if beyond else 45.0)
                and float(s.get("no_speech_prob") or 0.0) < 0.6):
            txt = " ".join(w["w"].strip() for w in ws)
            nl = _mk_line(txt, t=a, end=b, words_src=[{"text": w["w"].strip(), "t": w["start"]} for w in ws], origin="asr_only",
                          order=order, tm=tm)
            nl["asr_wt"] = [w["start"] for w in ws]
            order += 1
            new.append(nl)
            spans.append((a, b))
    return new


# ------------------------------------------------------------------------------------------ stable-ts
def _stable_ts(lines: list[dict[str, Any]], lead: np.ndarray, model_dir: Path, threads: int, language: str | None) -> int:
    import stable_whisper

    m = stable_whisper.load_faster_whisper(str(model_dir), device="cpu", compute_type="int8", cpu_threads=threads)
    order = [x for x in lines if x["origin"] == "source"]
    text = "\n".join(x["text"] for x in order)
    r = m.align(np.ascontiguousarray(lead, np.float32), text, language=language or "en", original_split=True, vad=False)
    segs = list(r.segments)
    if len(segs) != len(order):
        return 0
    n = 0
    for x, s in zip(order, segs):
        ws = [r_ for r_ in x["wres"] if r_ is not None]
        mean = float(np.mean([r_["score"] for r_ in ws])) if ws else 0.0
        sw = list(s.words)
        probs = [getattr(w, "probability", 0.0) or 0.0 for w in sw]
        if mean >= 0.1 or not sw or float(np.mean(probs)) < 0.5:
            continue
        k = len(x["words"])
        for wi in range(k):
            j = min(len(sw) - 1, int(wi * len(sw) / k))
            x["wres"][wi] = {"start": float(sw[j].start), "end": float(sw[j].end), "score": float(probs[j]) * 0.5,
                             "tok_scores": [float(probs[j]) * 0.5]}
        x["timing_source"] = "stable_ts"
        n += 1
    return n


# ------------------------------------------------------------------------------------------ finalise
def _line_span(x: dict[str, Any]) -> tuple[float, float]:
    """A line's span: its first word to its last word's end, widened (never narrowed) by a bar start or end set in
    the viewer (D84: ``lyrics.lines {key: {start, end}}``), so the span always holds every word."""
    t0 = min(x["wt"])
    t1 = max(x["wt"][i] + x["wd"][i] for i in range(len(x["wt"])))
    if x.get("bar_a") is not None:
        t0 = min(t0, max(0.0, float(x["bar_a"])))
    if x.get("bar_b") is not None:
        t1 = max(t1, float(x["bar_b"]))
    return t0, t1


def _cap_line_tails(lines: list[dict[str, Any]], gap: float = 0.01) -> int:
    """W3C-5: a lead line's held last word ends before the next lead line's first word (dense rap: the sustain
    extension ran up to 1.5 s into the next rapper's line, so two singers showed at every hand-off). Backing lines
    may overlap the lead and are neither capped nor caps. Returns the number of lines capped."""
    lead = [x for x in lines if not x.get("backing") and x["wt"]]
    n = 0
    for x, y in zip(lead, lead[1:]):
        nxt = float(y["wt"][0])
        t_last = float(x["wt"][-1])
        end = t_last + float(x["wd"][-1])
        if end > nxt - gap and nxt - gap > t_last:
            x["wd"][-1] = max(0.02, nxt - gap - t_last)
            n += 1
    return n


def _finalise_line(x: dict[str, Any], offset: float, env: np.ndarray, floor: float, kind: str, mode: str | None) -> None:
    k = len(x["words"])
    starts: list[float | None] = [None] * k
    ends: list[float | None] = [None] * k
    for i, r in enumerate(x["wres"]):
        if r is not None:
            starts[i], ends[i] = float(r["start"]), float(r["end"])
    user_words = kind == "user" and any(t is not None for t in x["src_wt"])
    if user_words:
        # the user's word timings are authoritative; alignment only informs the confidence
        for i, t in enumerate(x["src_wt"]):
            if t is not None:
                starts[i] = float(t)
                ends[i] = None
    known = [i for i in range(k) if starts[i] is not None]
    src_shift = offset if (kind != "transcribed" and x["origin"] == "source") else 0.0
    if not known:
        # nothing aligned: source word times, else source line times spread evenly
        if any(t is not None for t in x["src_wt"]):
            for i, t in enumerate(x["src_wt"]):
                if t is not None:
                    starts[i] = float(t) + src_shift
            known = [i for i in range(k) if starts[i] is not None]
            x["timing_source"] = x["timing_source"] or ("lrclib_word" if kind == "lrclib" else "interpolated")
        if not known:
            if x["src_t"] is None:
                x["wt"], x["wd"] = [], []
                return
            a = float(x["src_t"]) + src_shift
            b = float(x["src_end"] if x["src_end"] is not None else a + 0.4 * k) + src_shift
            b = max(b, a + 0.2 * k)
            for i in range(k):
                starts[i] = a + (b - a) * i / k
                ends[i] = a + (b - a) * (i + 1) / k
            known = list(range(k))
            x["timing_source"] = x["timing_source"] or ("lrclib_line" if kind == "lrclib" else "interpolated")
    # interpolate gaps between known words
    for i in range(k):
        if starts[i] is not None:
            continue
        prev = max((j for j in known if j < i), default=None)
        nxt = min((j for j in known if j > i), default=None)
        if prev is not None and nxt is not None:
            a = ends[prev] if ends[prev] is not None else starts[prev] + 0.2
            b = starts[nxt]
            n_between = nxt - prev - 1
            pos = i - prev
            starts[i] = a + (b - a) * (pos - 1) / max(1, n_between) if b > a else a
            ends[i] = a + (b - a) * pos / max(1, n_between) if b > a else a + 0.05
        elif prev is not None:
            base = ends[prev] if ends[prev] is not None else starts[prev] + 0.25
            starts[i] = base + 0.25 * (i - prev - 1)
            ends[i] = starts[i] + 0.25
        else:
            starts[i] = starts[nxt] - 0.25 * (nxt - i)
            ends[i] = starts[i] + 0.2
    # monotonic starts, ends never past the next start, sustain extension on the vocal envelope
    for i in range(1, k):
        if starts[i] < starts[i - 1]:
            starts[i] = starts[i - 1]
    wt, wd = [], []
    for i in range(k):
        e = ends[i] if ends[i] is not None else starts[i] + 0.1
        nxt = starts[i + 1] if i + 1 < k else math.inf
        limit = nxt - 0.01 if i + 1 < k else e + 1.5
        e = min(max(e, starts[i] + 0.02), max(starts[i] + 0.02, nxt))
        if floor > 0:
            e = VE.sustain_end(env, floor, starts[i], e, limit, 1.5 if i + 1 == k else 1.0)
        if i + 1 < k:
            e = min(e, max(starts[i] + 0.02, nxt))
        wt.append(max(0.0, starts[i]))
        wd.append(max(0.02, e - starts[i]))
    x["wt"], x["wd"] = wt, wd
    if x["timing_source"] is None:
        if user_words:
            x["timing_source"] = "user"
        elif kind == "transcribed":
            x["timing_source"] = "whisper" if all(r is None for r in x["wres"]) else "ctc"
        elif x["origin"] == "asr_only" and all(r is None for r in x["wres"]):
            x["timing_source"] = "whisper"
        else:
            x["timing_source"] = "ctc"
    if x["origin"] == "expanded" and all(r is None or r["score"] < 0.1 for r in x["wres"]):
        x["timing_source"] = "interpolated"
    if x["src_t"] is not None and kind not in ("transcribed",) and x["origin"] == "source" and mode == "synced":
        x["dev"] = abs(wt[0] - (float(x["src_t"]) + offset)) if wt else None
    x["wp"] = list(x.get("src_wp") or [None] * k) if kind == "transcribed" else [None] * k


#: per-word lists of an internal line (cut together when a line is split)
_PER_WORD = ("words", "toks", "wres", "wt", "wd", "src_wt", "src_wp", "wp")


def _split_points(ovr: dict[str, Any], lines: list[dict[str, Any]], n_src: int, warnings: list[str]) -> dict[int, list[int]]:
    """overrides ``lyrics.splits`` [{index, at: [k, ...], key?}] -> {source line index: sorted word positions}. A bar
    starts at each word position k (0-based place of the word in the source line, 1 <= k < number of words). An entry
    whose index is out of range or whose key no longer matches the text is ignored with a warning."""
    out: dict[int, list[int]] = {}
    bad = 0
    for r in ovr.get("lyrics.splits") or []:
        try:
            i = int(r["index"])
            at = sorted({int(k) for k in r.get("at") or []})
        except (KeyError, TypeError, ValueError):
            bad += 1
            continue
        if not (0 <= i < n_src) or (r.get("key") and r["key"] != _pin_key(lines[i]["text"])):
            bad += 1
            continue
        n = len(lines[i]["words"])
        at = [k for k in at if 0 < k < n]
        if at:
            out[i] = sorted(set(out.get(i, [])) | set(at))
    if bad:
        warnings.append(f"{bad} lyric split(s) no longer match the lyric text (it changed since they were set); ignored")
    return out


def _apply_splits(lines: list[dict[str, Any]], ovr: dict[str, Any], warnings: list[str]) -> list[dict[str, Any]]:
    """D83: a source line split by the user becomes one line per part ('bars'). Each part keeps its words' timing,
    confidence and flags; ``part`` is its 0-based number and ``word0`` the place of its first word in the source line.
    Lines the harness added (repeats, ASR-only lines) are never split."""
    n_src = sum(1 for x in lines if x["origin"] in ("source", "transcribed"))
    pts = _split_points(ovr, lines, n_src, warnings)
    out: list[dict[str, Any]] = []
    for i, x in enumerate(lines):
        x.setdefault("word0", 0)
        at = pts.get(i) if x["origin"] in ("source", "transcribed") else None
        if not at or not x.get("wt"):
            out.append(x)
            continue
        cuts = [0, *at, len(x["words"])]
        for p_, (a, b) in enumerate(zip(cuts, cuts[1:])):
            y = dict(x)
            for f in _PER_WORD:
                if isinstance(x.get(f), list) and len(x[f]) == len(x["words"]):
                    y[f] = x[f][a:b]
            y["text"] = " ".join(y["words"])
            y["source_text"] = x["text"]
            y["part"], y["word0"] = p_, a
            y["pinned"] = bool(x.get("pinned")) and p_ == 0
            out.append(y)
    return out


def _assign_legacy_ids(lines: list[dict[str, Any]]) -> None:
    """``legacy_id``: the line id as numbered after the alignment and before any split or correction (lines sorted by
    start time). An id key in overrides.json (L012, L012.03) means this numbering, so a split added later never moves
    an older correction to another line; every bar of a split line keeps its source line's legacy id."""
    order = sorted(range(len(lines)), key=lambda i: (round(lines[i]["wt"][0], 3) if lines[i]["wt"] else 1e9, lines[i]["order"]))
    for n, i in enumerate(order):
        lines[i]["legacy_id"] = f"L{n + 1:03d}"


def _assign_refs(lines: list[dict[str, Any]]) -> None:
    """D83: ``ref`` = r<source index> (p<part> for a split bar): the line's place in the lyric source, which does not
    change when lines are moved, split or renumbered. Lines the harness added have none."""
    for x in lines:
        if x["origin"] in ("source", "transcribed"):
            x["ref"] = f"r{x['order']}" + (f"p{x['part']}" if x.get("part") is not None else "")
        else:
            x["ref"] = None


_LREF = re.compile(r"^r(\d+)(?:p(\d+))?$")
_WREF = re.compile(r"^r(\d+)w(\d+)$")


def _apply_overrides(lines: list[dict[str, Any]], ovr: dict[str, Any], warnings: list[str]) -> None:
    """lyrics.lines {L001 | r12 | r12p1: {dt, start, end}} and lyrics.words {L001.03 | r12w4: {t, d, dt}}, applied after
    alignment, before the exports. ``L`` ids are the ones this run assigns (lines sorted by start time; kept for files
    written by hand); ``r`` references (D83) are stable: r12 is source line 12 (every bar of it when it is split),
    r12p1 its second bar, r12w4 its fifth word wherever that word is now."""
    lo = ovr.get("lyrics.lines") or {}
    wo = ovr.get("lyrics.words") or {}
    if not lo and not wo:
        return
    if any("legacy_id" not in x for x in lines):
        _assign_legacy_ids(lines)
    ids: dict[str, list[int]] = {}
    for i, x in enumerate(lines):
        ids.setdefault(x["legacy_id"], []).append(i)
    miss = 0

    def by_ref(key: str) -> list[int]:
        m = _LREF.match(key)
        if not m:
            return []
        src, part = int(m.group(1)), m.group(2)
        return [i for i, x in enumerate(lines) if x.get("ref") and x["order"] == src
                and (part is None or x.get("part") == int(part) or (x.get("part") is None and part == "0"))]

    def word_at(key: str) -> tuple[int, int] | None:
        m = _WREF.match(key)
        if m:
            src, k = int(m.group(1)), int(m.group(2))
            for i, x in enumerate(lines):
                if x.get("ref") and x["order"] == src and x["word0"] <= k < x["word0"] + len(x["wt"]):
                    return i, k - x["word0"]
            return None
        m = re.match(r"^(L\d{3,})\.(\d{2,})$", key)
        k = int(m.group(2)) - 1 if m else -1
        for i in ids.get(m.group(1), []) if m else []:
            x = lines[i]
            if x["word0"] <= k < x["word0"] + len(x["wt"]):
                return i, k - x["word0"]
        return None

    for lid, v in sorted(lo.items()):
        targets = by_ref(lid) if lid.startswith("r") else ids.get(lid, [])
        if not targets:
            miss += 1
            continue
        if "dt" in v:
            dt = float(v["dt"])
            for i in targets:
                lines[i]["wt"] = [t + dt for t in lines[i]["wt"]]
                lines[i]["timing_source"] = "user"
        # D84: the bar's own start and end (absolute; the words never move). A key naming every bar of a split line
        # sets the start of its first bar and the end of its last one.
        bars = sorted(targets, key=lambda i: lines[i].get("part") or 0)
        if v.get("start") is not None:
            lines[bars[0]]["bar_a"] = float(v["start"])
        if v.get("end") is not None:
            lines[bars[-1]]["bar_b"] = float(v["end"])
    for wid, v in sorted(wo.items()):
        hit = word_at(wid)
        if hit is None:
            miss += 1
            continue
        i, k = hit
        if not (0 <= k < len(lines[i]["wt"])):
            miss += 1
            continue
        if "t" in v:
            lines[i]["wt"][k] = float(v["t"])
        if "dt" in v:
            lines[i]["wt"][k] += float(v["dt"])
        if "d" in v:
            lines[i]["wd"][k] = max(0.02, float(v["d"]))
        lines[i]["timing_source"] = "user"
    if miss:
        warnings.append(f"{miss} lyrics override(s) name ids that do not exist in this run")


def _repeat_groups(keys: list[str]) -> dict[int, str]:
    """LG ids for near-identical lines (rapidfuzz ratio >= 88) that occur at least twice."""
    from rapidfuzz import fuzz

    reps: list[tuple[str, list[int]]] = []
    for i, k in enumerate(keys):
        if not k:
            continue
        for rk, members in reps:
            if rk == k or fuzz.ratio(rk, k) >= 88:
                members.append(i)
                break
        else:
            reps.append((k, [i]))
    out: dict[int, str] = {}
    n = 0
    for _, members in reps:
        if len(members) >= 2:
            n += 1
            for i in members:
                out[i] = f"LG{n:02d}"
    return out
