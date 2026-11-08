# ruff: noqa: E501
"""Claim checks for drafts and the merged meaning (PLAN §8.4): every claim typed, cited IDs and time ranges exist,
quotes of at most 10 words. Problems are reported (never with quote text: NF5) and repaired conservatively:
an unknown cited id is dropped, a long quote is cut to 10 words, an untyped claim becomes ``speculative``."""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from mvh.contract.ids import kind_of

__all__ = ["check_claims", "collect_ids", "cut_lyric_runs", "MAX_QUOTE_WORDS"]

MAX_QUOTE_WORDS = 10
SOURCES = ("user", "lyric", "audio", "external", "speculative")
#: id kinds the meaning stage can verify from its own deps (others are kept and counted as unverified)
VERIFIABLE = {"section", "line", "word", "voice", "character", "motif", "cue", "edm_role", "phrase", "text_group",
              "line_group"}


def collect_ids(*groups: Iterable[str]) -> set[str]:
    out: set[str] = set()
    for g in groups:
        out.update(str(x) for x in g if x)
    return out


def _fix_cites(cites: Any, known: set[str], duration: float, where: str, problems: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(cites, list):
        return out
    for c in cites:
        if not isinstance(c, Mapping):
            problems.append(f"{where}: a citation is not an object (dropped)")
            continue
        c = dict(c)
        cid = c.get("id")
        if cid is not None:
            k = kind_of(str(cid))
            if k is None:
                problems.append(f"{where}: a cited id is not a contract id (dropped)")
                c.pop("id")
            elif k in VERIFIABLE and str(cid) not in known:
                problems.append(f"{where}: cited id {cid} does not exist (dropped)")
                c.pop("id")
        for tk in ("t0", "t1"):
            if tk in c and not isinstance(c[tk], (int, float)):
                c.pop(tk)
        if "t0" in c and "t1" in c and (c["t0"] > c["t1"] or c["t0"] < -0.5 or c["t1"] > duration + 0.5):
            problems.append(f"{where}: cited time range is outside the song (dropped)")
            c.pop("t0")
            c.pop("t1")
        q = c.get("quote")
        if isinstance(q, str):
            words = q.split()
            if len(words) > MAX_QUOTE_WORDS:
                problems.append(f"{where}: a quote has {len(words)} words (cut to {MAX_QUOTE_WORDS})")
                c["quote"] = " ".join(words[:MAX_QUOTE_WORDS])
        elif q is not None:
            c.pop("quote")
        if any(k in c for k in ("id", "t0", "quote")):
            out.append(c)
    return out


def _fix_claim(cl: Any, known: set[str], duration: float, where: str, problems: list[str],
               status: str) -> dict[str, Any] | None:
    if isinstance(cl, str):
        cl = {"text": cl}
    if not isinstance(cl, Mapping) or not str(cl.get("text") or "").strip():
        problems.append(f"{where}: claim without text (dropped)")
        return None
    out = dict(cl)
    if out.get("source") not in SOURCES:
        problems.append(f"{where}: claim has no valid source type (set to speculative)")
        out["source"] = "speculative"
    if status == "draft" and out["source"] == "user":
        problems.append(f"{where}: a draft claim may not be typed 'user' (set to speculative)")
        out["source"] = "speculative"
    out["cites"] = _fix_cites(out.get("cites"), known, duration, where, problems)
    out["status"] = status
    return out


def check_claims(doc: Mapping[str, Any], known: set[str], duration: float, status: str = "draft") -> tuple[dict[str, Any], list[str]]:
    """Repair a meaning document (authored.json or a merge result) in place of a copy; -> (doc, problems)."""
    d = dict(doc)
    problems: list[str] = []
    for key in ("themes", "symbolism"):
        items = []
        for i, cl in enumerate(d.get(key) or []):
            fixed = _fix_claim(cl, known, duration, f"{key}[{i}]", problems, status)
            if fixed:
                items.append(fixed)
        d[key] = items
    for key in ("characters", "motifs", "sections"):
        items = []
        for i, it in enumerate(d.get(key) or []):
            if not isinstance(it, Mapping):
                problems.append(f"{key}[{i}]: not an object (dropped)")
                continue
            it = dict(it)
            prov = dict(it.get("provenance") or {})
            if prov.get("source") not in SOURCES or (status == "draft" and prov.get("source") == "user"):
                problems.append(f"{key}[{i}]: provenance.source missing or not allowed (set to speculative)")
                prov["source"] = "speculative"
            prov["status"] = status if status != "user" else prov.get("status", "user")
            prov["cites"] = _fix_cites(prov.get("cites"), known, duration, f"{key}[{i}]", problems)
            it["provenance"] = prov
            if key == "motifs":
                occ = []
                for o in it.get("occurrences") or []:
                    if isinstance(o, Mapping) and isinstance(o.get("t"), (int, float)):
                        o = dict(o)
                        if o.get("line_id") is not None and str(o["line_id"]) not in known:
                            problems.append(f"motifs[{i}]: an occurrence names a line that does not exist (dropped)")
                            continue
                        occ.append(o)
                it["occurrences"] = occ
            if key == "characters":
                it["line_ids"] = [x for x in it.get("line_ids") or [] if str(x) in known]
                it["voice_ids"] = [x for x in it.get("voice_ids") or [] if re.fullmatch(r"V[1-9]\d*", str(x))]
            items.append(it)
        d[key] = items
    return d, problems


_WORD = re.compile(r"[\w']+")
_SKIP_KEYS = {"id", "ids", "line_id", "line_ids", "voice_ids", "source", "status", "schema", "schema_version", "cites", "quote"}


def _cut_text(text: str, grams: set[str], n: int) -> tuple[str, int]:
    toks = [(m.start(), m.end(), m.group(0).lower()) for m in _WORD.finditer(text)]
    if len(toks) < n:
        return text, 0
    covered = [False] * len(toks)
    for i in range(len(toks) - n + 1):
        if " ".join(t[2] for t in toks[i:i + n]) in grams:
            for j in range(i, i + n):
                covered[j] = True
    runs: list[tuple[int, int]] = []
    i = 0
    while i < len(toks):
        if covered[i]:
            j = i
            while j + 1 < len(toks) and covered[j + 1]:
                j += 1
            runs.append((i, j))
            i = j + 1
        else:
            i += 1
    for a, b in reversed(runs):
        keep = MAX_QUOTE_WORDS - 2
        text = text[:toks[a + keep - 1][1]] + " ..." + text[toks[b][1]:]
    return text, len(runs)


def cut_lyric_runs(doc: Any, lyric_text: str, n: int = MAX_QUOTE_WORDS + 1) -> tuple[Any, int]:
    """Cut every run of more than ``MAX_QUOTE_WORDS`` consecutive lyric words out of the free-text strings of a draft
    (CONTRACT §1: quotes are at most 10 words). -> (copy, number of cuts). Never reports the text."""
    grams: set[str] = set()
    w = [m.group(0).lower() for m in _WORD.finditer(lyric_text or "")]
    for i in range(len(w) - n + 1):
        grams.add(" ".join(w[i:i + n]))
    if not grams:
        return doc, 0
    count = 0

    def walk(x: Any, key: str | None = None) -> Any:
        nonlocal count
        if isinstance(x, str):
            if key in _SKIP_KEYS or len(x.split()) < n:
                return x
            y, c = _cut_text(x, grams, n)
            count += c
            return y
        if isinstance(x, list):
            return [walk(v, key) for v in x]
        if isinstance(x, Mapping):
            return {k: walk(v, str(k)) for k, v in x.items()}
        return x

    return walk(doc), count
