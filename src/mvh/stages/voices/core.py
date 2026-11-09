"""voices orchestration (PLAN §5 voices, SPIKE, bench-words §6).

1. Items: every aligned lyric line (first word start .. last word end); lines longer than ``split_s`` are also cut
   into word chunks of about ``chunk_s`` so a voice change inside a line becomes its own span.
2. ECAPA embeddings on lead_vocals (16 kHz mono); WeSpeaker ONNX when ECAPA fails.
3. k: overrides / intent count (``n_source=intent``) > speaker hints from the lyrics source (``hints``, the hint
   decides the voice) > estimate (``estimate``: 1 voice when the 2-split is not separated, else the best cosine
   silhouette at k >= the eigengap lower bound).
4. Agglomerative clustering (cosine, average); items shorter than ``min_item_s`` inherit their neighbours' voice.
5. Duets: where backing_vocals is active inside a line, the backing segment is embedded and, when it matches a
   voice other than the line's lead voice, a second span (role backing) is added.
6. ``voices.lines`` overrides and per-line assignments in intent.md force a voice (conf 1, review false).
7. Outputs: events voice_spans (per line or word span) and voice_activity (merged per voice), meta/voices.json.
   Voice ids V1..Vn in order of first appearance; the user maps voices to characters (the viewer and intent.md).
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np

from mvh.runner.spec import StageError, StageResult

from . import cluster as K
from .intent import parse_intent

__all__ = ["run"]


def _segments(words: list[dict[str, Any]], chunk_s: float) -> list[list[dict[str, Any]]]:
    out: list[list[dict[str, Any]]] = []
    cur: list[dict[str, Any]] = []
    for w in words:
        if cur and (w["t"] + w["d"] - cur[0]["t"]) > chunk_s and len(cur) >= 2:
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        if out and (cur[-1]["t"] + cur[-1]["d"] - cur[0]["t"]) < 0.5 * chunk_s:
            out[-1] += cur
        else:
            out.append(cur)
    return out


_JOINT_SPLIT = re.compile(r"\s*(?:&|\+|,|/|\band\b|\bfeat\.|\bft\.)\s*", re.I)
_JOINT_ALL = {"both", "all", "everyone", "everybody", "together", "group", "crowd", "unison", "tutti", "choir"}


def hint_parts(hint: str | None) -> list[str]:
    """Singer names in a speaker hint: 'Ann' -> ['Ann']; 'Ann & Bob' / 'Ann and Bob' / 'Ann, Bob' -> ['Ann', 'Bob'];
    'Both' / 'All' -> [] (a joint line whose singers the text does not name)."""
    if not hint or not hint.strip():
        return []
    if hint.strip().lower().strip(".!") in _JOINT_ALL:
        return []
    parts = [x.strip(" .") for x in _JOINT_SPLIT.split(hint) if x and x.strip(" .")]
    out: list[str] = []
    for x in parts:
        if x.lower() not in _JOINT_ALL and x not in out:
            out.append(x)
    return out


def _env_db(x: np.ndarray, t0: float, t1: float, sr: int = 16000) -> float:
    a, b = max(0, int(t0 * sr)), min(len(x), int(t1 * sr))
    if b <= a:
        return -120.0
    e = float(np.mean(np.square(x[a:b], dtype=np.float64)))
    return 10 * np.log10(max(e, 1e-12))


def _backing_activity(ctx, warnings: list[str]) -> list[tuple[float, float]] | None:
    """backing_vocals segments of stem_activity, or None (no gating) when the events cannot be read."""
    try:
        items = ctx.upstream("stem_activity").events("stem_activity").items
    except Exception as e:  # noqa: BLE001 - a missing optional view: duet spans fall back to the line window
        warnings.append(f"stem_activity events unavailable ({type(e).__name__}): backing spans are not gated by the stem")
        return None
    return sorted((float(x["t"]), float(x["t"]) + float(x["d"])) for x in items if x.get("stem") == "backing_vocals")


def backing_window(segs: list[tuple[float, float]] | None, t0: float, t1: float, min_support: float,
                   min_s: float) -> tuple[float, float, float | None] | None:
    """Where a line's backing span may sit, judged by the backing_vocals stem activity (S16, W4).

    ``segs``: backing_vocals activity segments (s, e), or None when stem_activity is unavailable (no gating).
    -> (a, b, support) or None (no backing voice in the stem here). A line whose time is backed at least
    ``min_support`` keeps the whole line; otherwise the span is trimmed to the hull of the active parts, which must
    last ``min_s`` and be backed ``min_support`` itself (a short burst under a long line opens no second mouth)."""
    if segs is None:
        return t0, t1, None
    parts = [(max(t0, a), min(t1, b)) for a, b in segs if b > t0 and a < t1]
    parts = [(a, b) for a, b in parts if b > a]
    if not parts or t1 <= t0:
        return None
    active = sum(b - a for a, b in parts)
    if active / (t1 - t0) >= min_support:
        return t0, t1, active / (t1 - t0)
    a, b = min(x for x, _ in parts), max(y for _, y in parts)
    if b - a < min_s or active / (b - a) < min_support:
        return None
    return a, b, active / (b - a)


def run(ctx) -> StageResult:  # noqa: C901
    p = dict(ctx.params)
    warnings: list[str] = []
    fallbacks: list[str] = []
    notes: list[str] = []
    lyr = ctx.upstream("lyrics").json("lyrics/lyrics.json")
    lines = [ln for ln in lyr.get("lines", []) if ln.get("n_words", 0) > 0]
    words_by: dict[str, list[dict[str, Any]]] = {}
    for w in lyr.get("words", []):
        words_by.setdefault(w["line_id"], []).append(w)
    intent_path = ctx.external("intent")
    intent = parse_intent(intent_path.read_text(encoding="utf-8", errors="replace") if intent_path else None)
    ovr = dict(ctx.overrides.get("voices.lines") or {})
    forced: dict[str, str] = {**intent["line_voice"], **ovr}

    def empty(reason: str, status: str = "skipped") -> StageResult:
        ctx.writer.events("voice_spans", [])
        ctx.writer.events("voice_activity", [])
        ctx.writer.json("meta/voices.json", {"n_voices": 0, "method": reason, "n_source": "estimate", "voices": []})
        return StageResult(status=status, summary={"n_voices": 0, "reason": reason}, warnings=warnings, fallbacks=fallbacks)

    if not lines:
        return empty("no aligned lyric lines")

    from mvh.stages.lyrics.vocal_env import pick_vocal_stem

    stem_name, lead, _sr = pick_vocal_stem(ctx, 16000)
    if stem_name != "lead_vocals":
        fallbacks.append("voices:vocals_stem")
    try:
        back = np.asarray(ctx.audio("backing_vocals", sr=16000, mono=True).samples[0], dtype=np.float32)
    except StageError:
        back = np.zeros_like(lead)
    sep = ctx.upstream("separate_hq").json("meta/separation.json") if ctx.upstream("separate_hq").exists("meta/separation.json") else {}
    split = bool(sep.get("lead_backing_split", True)) and stem_name == "lead_vocals"

    # ---------------------------------------------------------------- 1. items
    items: list[dict[str, Any]] = []
    min_item = float(p.get("min_item_s", 1.0))
    for ln in lines:
        ws = words_by.get(ln["id"], [])
        if not ws:
            continue
        t0, t1 = ws[0]["t"], max(w["t"] + w["d"] for w in ws)
        chunks = _segments(ws, float(p.get("chunk_s", 4.0))) if (t1 - t0) > float(p.get("split_s", 8.0)) and len(ws) >= 6 else [ws]
        for ch in chunks:
            a, b = ch[0]["t"], max(w["t"] + w["d"] for w in ch)
            items.append({"line_id": ln["id"], "t0": a, "t1": b, "first_word": ch[0]["id"], "last_word": ch[-1]["id"],
                          "hint": ln.get("speaker_hint"), "embed": (b - a) >= min_item, "chunked": len(chunks) > 1})
    emb_items = [it for it in items if it["embed"]]

    # ---------------------------------------------------------------- 2. embeddings
    from .embed import load_embedder

    try:
        emb, models_used, fb = load_embedder(ctx, p.get("model", "ecapa"))
    except RuntimeError as e:
        raise StageError(str(e)) from e
    fallbacks += fb
    E = emb.many([lead[int(it["t0"] * 16000):int(it["t1"] * 16000)] for it in emb_items]) if emb_items else np.zeros((0, emb.dim))
    w = np.array([it["t1"] - it["t0"] for it in emb_items])

    # ---------------------------------------------------------------- 3. k and labels
    # joint labels ('Ann & Bob', 'Both') are not voices of their own (M5-D55): k counts the single names
    for it in items:
        it["parts"] = hint_parts(it["hint"])
        it["solo"] = it["parts"][0] if len(it["parts"]) == 1 else None
    # every named singer, including one whose lines are all too short to embed (R5-2: a 0.6 s announcer line)
    hints = sorted({pt for it in items for pt in it["parts"]})
    n_int = intent.get("n_voices") or intent.get("n_characters")
    n_min = int(intent.get("n_voices_min") or 0)
    k_info: dict[str, Any] = {}
    if len(emb_items) == 0:
        labels = np.zeros(0, dtype=np.int64)
        k, n_source = 1, "estimate"
        k_info["reason"] = "all lines shorter than min_item_s: one voice"
    elif n_int:
        k = max(1, min(max(int(n_int), n_min), len(emb_items)))
        n_source = "intent"
        labels = K.agglo(E, k)
        k_info["reason"] = f"user count from intent.md ({int(n_int)})"
        if k < int(n_int):
            warnings.append(f"intent names {int(n_int)} voices but only {len(emb_items)} line items exist")
    elif len(hints) >= 2:
        n_source = "hints"
        k = len(hints)
        hid = {h: i for i, h in enumerate(hints)}
        C = []
        for h in hints:
            m = np.array([it["solo"] == h for it in emb_items])
            if not m.any():   # a name heard only in joint lines
                m = np.array([h in it["parts"] for it in emb_items])
            v = (E[m] * w[m][:, None]).sum(0) if m.any() else np.zeros(E.shape[1])   # a name with no embedded line
            C.append(v / (np.linalg.norm(v) + 1e-9))
        C = np.asarray(C)

        def _lab(it: dict[str, Any], e: np.ndarray) -> int:
            if it["solo"]:
                return hid[it["solo"]]
            cand = [hid[pt] for pt in it["parts"]] or list(range(k))   # joint line: nearest of its singers
            return int(cand[int(np.argmax(C[cand] @ e))])

        labels = np.array([_lab(it, e) for it, e in zip(emb_items, E)], dtype=np.int64)
        k_info["reason"] = "speaker labels in the lyrics source"
    else:
        n_source = "estimate"
        k, k_info = K.estimate_k(E, w, k_max=int(p.get("k_max", 8)), same_voice_cos=float(p.get("same_voice_cos", 0.6)),
                                 min_silhouette=float(p.get("min_silhouette", 0.08)), small_n=int(p.get("small_n", 24)))
        labels = K.agglo(E, k)
        if p.get("merge_minor", True) and k >= 2:
            labels, merged = K.merge_minor(E, labels, w)
            if merged:
                k_info["merged_minor"] = merged
                k_info["k_before_merge"] = k
        if n_min and int(labels.max()) + 1 < n_min <= len(emb_items):
            # the voices the user mapped in the viewer are a floor (D51)
            k_info["floor"] = n_min
            k_info["k_estimated"] = int(labels.max()) + 1
            labels = K.agglo(E, n_min)
    for it, lab in zip(emb_items, labels):
        it["label"] = int(lab)
    k = int(labels.max()) + 1 if len(labels) else 1
    C = K.centroids(E, labels, w) if len(labels) else np.zeros((1, emb.dim))
    # confidence: margin between the best and the second-best centroid similarity
    for it, e in zip(emb_items, E):
        sims = C @ e
        o = np.sort(sims)[::-1]
        margin = float(o[0] - o[1]) if len(o) > 1 else 1.0
        it["sim"] = float(sims[it["label"]])
        it["conf"] = float(np.clip(0.5 + 1.5 * margin, 0.0, 1.0)) if k > 1 else float(np.clip(0.4 + 0.6 * max(0.0, it["sim"]), 0, 1))
        it["source"] = "hint" if (n_source == "hints" and it["solo"]) else "embedding"
        if it["source"] == "hint":
            it["conf"] = max(it["conf"], 0.9)
    # short items inherit the voice of the nearest embedded neighbour (previous first)
    for i, it in enumerate(items):
        if it["embed"]:
            continue
        prev = next((items[j] for j in range(i - 1, -1, -1) if items[j]["embed"]), None)
        nxt = next((items[j] for j in range(i + 1, len(items)) if items[j]["embed"]), None)
        nb = prev if prev is not None and (nxt is None or it["t0"] - prev["t1"] <= nxt["t0"] - it["t1"]) else nxt
        it["label"] = nb["label"] if nb is not None else 0
        it["conf"] = round(0.5 * (nb["conf"] if nb is not None else 0.5), 4)
        it["source"] = "neighbour"
        if it["solo"] and n_source == "hints":
            it["label"] = hints.index(it["solo"])
            it["source"], it["conf"] = "hint", 0.9
        elif it["parts"] and n_source == "hints" and it["label"] not in [hints.index(pt) for pt in it["parts"]]:
            it["label"] = hints.index(it["parts"][0])   # joint line: one of its singers

    # ---------------------------------------------------------------- 4. voice ids by first appearance
    order: dict[int, int] = {}
    for it in sorted(items, key=lambda x: x["t0"]):
        order.setdefault(it["label"], len(order))
    vid = {lab: f"V{n + 1}" for lab, n in order.items()}
    for lab in range(k):
        if lab not in vid:
            vid[lab] = f"V{len(vid) + 1}"
    for it in items:
        it["voice"] = vid[it["label"]]

    # ---------------------------------------------------------------- 5. forced assignments (overrides > intent lines)
    n_forced = 0
    for it in items:
        v = forced.get(it["line_id"])
        if v:
            it["voice"], it["conf"], it["source"] = v, 1.0, "override" if it["line_id"] in ovr else "intent"
            n_forced += 1

    # ---------------------------------------------------------------- 6. spans (merge consecutive same-voice chunks)
    spans: list[dict[str, Any]] = []
    for it in items:
        last = spans[-1] if spans else None
        if last and last["line_id"] == it["line_id"] and last["voice_id"] == it["voice"] and last["role"] == "lead":
            last["d"] = max(last["d"], it["t1"] - last["t"])
            last["last_word"] = it["last_word"]
            last["_c"].append(it["conf"])
            continue
        spans.append({"t": it["t0"], "d": max(0.02, it["t1"] - it["t0"]), "line_id": it["line_id"], "first_word": it["first_word"],
                      "last_word": it["last_word"], "voice_id": it["voice"], "_c": [it["conf"]], "role": "lead",
                      "source": it["source"]})
    # duets: backing voice spans
    n_backing = 0
    n_unbacked = 0
    if split and np.any(np.abs(back) > 1e-6) and len(E) and k >= 2 and p.get("backing_spans", True):
        bmin = float(p.get("backing_rel_db", -15.0))
        bsegs = _backing_activity(ctx, warnings)
        bsup = float(p.get("backing_min_support", 0.5))
        for ln in lines:
            ws = words_by.get(ln["id"], [])
            if not ws:
                continue
            t0, t1 = ws[0]["t"], max(x["t"] + x["d"] for x in ws)
            if t1 - t0 < min_item:
                continue
            win = backing_window(bsegs, t0, t1, bsup, min_item)
            if win is None:
                n_unbacked += 1
                continue
            t0, t1 = win[0], win[1]
            ws = [x for x in ws if x["t"] < t1 and x["t"] + x["d"] > t0] or ws
            bl, ll = _env_db(back, t0, t1), _env_db(lead, t0, t1)
            if bl < -45.0 or bl - ll < bmin:
                continue
            e = emb.one(back[int(t0 * 16000):int(t1 * 16000)])
            sims = C @ e
            lead_v = next((s["voice_id"] for s in spans if s["line_id"] == ln["id"] and s["role"] == "lead"), None)
            ordered = np.argsort(-sims)
            best = next((int(c) for c in ordered if vid[int(c)] != lead_v), None)
            if best is None or float(sims[best]) < float(p.get("backing_min_sim", 0.25)):
                continue
            if vid[int(ordered[0])] == lead_v and float(sims[ordered[0]] - sims[best]) > 0.25:
                continue   # the backing track is a double of the lead voice
            conf = float(np.clip(0.3 + float(sims[best]), 0.0, 0.95))
            spans.append({"t": t0, "d": t1 - t0, "line_id": ln["id"], "first_word": ws[0]["id"], "last_word": ws[-1]["id"],
                          "voice_id": vid[best], "_c": [conf], "role": "backing", "source": "embedding"})
            n_backing += 1
    review_thr = float(p.get("review_below", 0.5))
    # M5-D22: a grade-D lyrics alignment puts the embedding windows on unreliable spans: every estimated span
    # is flagged for review (forced voices from overrides / intent are the user's and stay unflagged)
    # (m2, W3: with ONE voice there is no singer to get wrong, so grade D alone flags nothing)
    weak_words = lyr.get("grade") == "D" and len({s["voice_id"] for s in spans}) > 1
    if weak_words:
        warnings.append("lyrics alignment grade D: every estimated voice span is flagged for review")
    out_spans = []
    for s in sorted(spans, key=lambda s: (s["t"], s["role"] != "lead", s["voice_id"])):
        c = round(float(np.mean(s.pop("_c"))), 4)
        out_spans.append({**{k_: v for k_, v in s.items()}, "t": round(s["t"], 6), "d": round(s["d"], 6), "conf": c,
                          "review": bool(c < review_thr or s["source"] == "neighbour"
                                         or (weak_words and s["source"] not in ("override", "intent")))})

    # ---------------------------------------------------------------- 7. activity, meta
    voices_all = sorted({s["voice_id"] for s in out_spans}, key=lambda v: int(v[1:]))
    act = []
    for v in voices_all:
        segs = sorted((s["t"], s["t"] + s["d"]) for s in out_spans if s["voice_id"] == v)
        cur = None
        for a, b in segs:
            if cur and a <= cur[1] + float(p.get("activity_gap_s", 0.35)):
                cur[1] = max(cur[1], b)
            else:
                if cur:
                    act.append({"t": cur[0], "d": cur[1] - cur[0], "voice_id": v})
                cur = [a, b]
        if cur:
            act.append({"t": cur[0], "d": cur[1] - cur[0], "voice_id": v})
    act = [{**a, "t": round(a["t"], 6), "d": round(max(a["d"], 0.01), 6)} for a in act]
    v2c = intent.get("voice_to_character") or {}
    if not v2c and intent.get("n_characters") and intent["n_characters"] == len(voices_all):
        v2c = {v: f"C{i + 1}" for i, v in enumerate(voices_all)}
        notes.append("proposed V_k -> C_k by order of first appearance (intent names as many characters as voices)")
    hint_of = {}
    for it in items:
        if it["solo"]:
            hint_of.setdefault(it["voice"], {}).setdefault(it["solo"], 0)
            hint_of[it["voice"]][it["solo"]] += 1
    meta_voices = []
    for v in voices_all:
        sec = sum(a["d"] for a in act if a["voice_id"] == v)
        nl = len({s["line_id"] for s in out_spans if s["voice_id"] == v})
        h = max(hint_of.get(v, {}).items(), key=lambda kv: (kv[1], kv[0]))[0] if hint_of.get(v) else None
        meta_voices.append({"id": v, "seconds": round(sec, 3), "n_lines": nl, "proposed_character_id": v2c.get(v), "hint": h,
                            "lead_lines": len({s["line_id"] for s in out_spans if s["voice_id"] == v and s["role"] == "lead"})})
    method = f"{emb.name} embeddings per line/word span on lead_vocals; agglomerative clustering (cosine, average linkage)"
    sim_mat = (C @ C.T).round(4).tolist() if len(C) > 1 else None
    doc = {"n_voices": len(voices_all), "method": method, "n_source": n_source, "voices": meta_voices,
           # additive (docs/contract/decisions/M5.md)
           "model": emb.name, "k_selection": k_info, "centroid_cos": sim_mat, "items": len(items), "embedded_items": len(emb_items),
           "backing_spans": n_backing, "backing_unbacked_lines": n_unbacked, "forced_lines": n_forced, "stem": stem_name, "review_spans": sum(1 for s in out_spans if s["review"])}
    span_fields = {"role": {"unit": None, "type": "enum", "description": "lead or backing"},
                   "source": {"unit": None, "type": "enum", "description": "embedding, hint, neighbour, override, intent"}}
    ctx.writer.events("voice_spans", out_spans, fields=span_fields)
    ctx.writer.events("voice_activity", act)
    ctx.writer.json("meta/voices.json", doc)
    summary = {"n_voices": len(voices_all), "n_source": n_source, "model": emb.name, "spans": len(out_spans),
               "review": doc["review_spans"], "backing_spans": n_backing,
               "seconds": {m["id"]: m["seconds"] for m in meta_voices}}
    if doc["review_spans"]:
        notes.append(f"{doc['review_spans']} span(s) flagged for review")
    conf = float(np.mean([s["conf"] for s in out_spans])) if out_spans else None
    return StageResult(status="degraded" if fallbacks else "ok", summary=summary, warnings=warnings, fallbacks=fallbacks,
                       confidence=round(conf, 4) if conf is not None else None,
                       provenance={"notes": notes, "embedding_model": emb.name})
