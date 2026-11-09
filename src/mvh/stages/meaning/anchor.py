"""Anchor per-section claims to the current canonical sections (PLAN §8.5, CONTRACT §7).

A claim addresses sections by id (``S03``, with the ``t0``/``t1`` it was written against), by occurrence
(``chorus#2``), by label (``chorus``: every chorus), by ordinal (``last chorus``) or by EDM role (``drop``,
``build``, ``breakdown``: the sections that hold that role). Claims written against times are **re-anchored
by time overlap** when the sections moved; claims that lose their section become orphans.

Rules (time-anchored claims, claim span C = [t0, t1)):
* every section that lies mostly inside C (overlap >= 50 % of the section) receives the claim (a split section
  keeps the note on both halves);
* otherwise the one section holding most of C (overlap >= 50 % of C) receives it (sections were merged);
* otherwise the claim is an orphan (``reason`` says why).
Specificity (used when several claims fill the same field of one section): id/time > occurrence > ordinal >
EDM role > label.
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

__all__ = ["anchor_claim", "SPECIFICITY", "norm_label"]

SPECIFICITY = {"id": 5, "occurrence": 4, "ordinal": 3, "role": 2, "label": 1}
ROLE_WORDS = {"build": "build", "buildup": "build", "build-up": "build", "drop": "drop", "breakdown": "breakdown"}
LABEL_ALIASES = {"prechorus": "pre-chorus", "instrumental": "inst", "hook": "chorus", "refrain": "chorus",
                 "interlude": "inst"}
ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "last": -1, "final": -1}


_KNOWN = {"intro", "verse", "pre-chorus", "chorus", "post-chorus", "bridge", "inst", "solo", "break", "breakdown",
          "build", "drop", "outro", "silence", "hook", "refrain", "interlude", "instrumental", "prechorus"}


def norm_label(s: str) -> str:
    s = s.strip().lower()
    if s not in _KNOWN and s.endswith("es") and s[:-2] in _KNOWN:
        s = s[:-2]  # choruses
    elif s not in _KNOWN and s.endswith("s") and s[:-1] in _KNOWN:
        s = s[:-1]  # verses, drops
    return LABEL_ALIASES.get(s, s)


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _by_time(t0: float, t1: float, sections: Sequence[Mapping[str, Any]]) -> tuple[list[str], str | None]:
    span = max(1e-9, t1 - t0)
    inside = [s["id"] for s in sections if _overlap(t0, t1, s["t"], s["t"] + s["d"]) >= 0.5 * s["d"] > 0]
    if inside:
        return inside, None
    best = max(sections, key=lambda s: _overlap(t0, t1, s["t"], s["t"] + s["d"]), default=None)
    if best is not None and _overlap(t0, t1, best["t"], best["t"] + best["d"]) >= 0.5 * span:
        return [best["id"]], None
    return [], "no current section overlaps the claim's time range by 50 % (sections changed)"


def anchor_claim(claim: Mapping[str, Any], sections: Sequence[Mapping[str, Any]],
                 roles: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """-> {section_ids: [...], how: id|time|occurrence|ordinal|role|label, specificity, reanchored: bool,
    orphan_reason: str|None, old_section_id: str|None}."""
    key = str(claim.get("key") or claim.get("section_id") or "").strip()
    t0, t1 = claim.get("t0"), claim.get("t1")
    ids = {s["id"]: s for s in sections}
    res: dict[str, Any] = {"section_ids": [], "how": None, "specificity": 0, "reanchored": False,
                           "orphan_reason": None, "old_section_id": None}
    if re.fullmatch(r"S\d{2,}", key):
        res["old_section_id"] = key
        res["specificity"] = SPECIFICITY["id"]
        if t0 is not None and t1 is not None and t1 > t0:
            got, why = _by_time(float(t0), float(t1), sections)
            res["how"] = "time"
            res["section_ids"] = got
            res["orphan_reason"] = why
            s = ids.get(key)
            same = s is not None and abs(s["t"] - t0) < 0.05 and abs(s["t"] + s["d"] - t1) < 0.05
            res["reanchored"] = bool(got) and not (same and got == [key])
            return res
        res["how"] = "id"
        if key in ids:
            res["section_ids"] = [key]
        else:
            res["orphan_reason"] = f"section {key} no longer exists and the claim has no time range"
        return res
    k = key.lower()
    m = re.fullmatch(r"([a-z\-]+)\s*(?:#|\s)(\d+)", k)
    if m:
        lab, occ = norm_label(m.group(1)), int(m.group(2))
        res["how"], res["specificity"] = "occurrence", SPECIFICITY["occurrence"]
        res["section_ids"] = [s["id"] for s in sections
                              if norm_label(s.get("label", "")) == lab and int(s.get("occurrence", 0)) == occ]
        if not res["section_ids"]:
            res["orphan_reason"] = f"no section {lab}#{occ}"
        return res
    m = re.fullmatch(r"(first|second|third|fourth|fifth|last|final)\s+([a-z\-]+)", k)
    if m:
        n, word = ORDINALS[m.group(1)], m.group(2)
        res["how"], res["specificity"] = "ordinal", SPECIFICITY["ordinal"]
        cands = _label_or_role(word, sections, roles)
        if cands:
            pick = cands[n - 1] if 0 < n <= len(cands) else (cands[-1] if n == -1 else None)
            res["section_ids"] = [pick] if pick else []
        if not res["section_ids"]:
            res["orphan_reason"] = f"no {m.group(1)} {word}"
        return res
    word = norm_label(k)
    if k in ROLE_WORDS or word in ROLE_WORDS:
        res["how"], res["specificity"] = "role", SPECIFICITY["role"]
    else:
        res["how"], res["specificity"] = "label", SPECIFICITY["label"]
    res["section_ids"] = _label_or_role(k, sections, roles)
    if not res["section_ids"]:
        res["orphan_reason"] = f"no section is a {word}"
    return res


def _label_or_role(word: str, sections: Sequence[Mapping[str, Any]], roles: Sequence[Mapping[str, Any]]) -> list[str]:
    w = norm_label(word)
    role = ROLE_WORDS.get(word.lower()) or ROLE_WORDS.get(w)
    if role:
        out: list[str] = []
        for r in roles:
            if r.get("role") != role:
                continue
            r0, r1 = float(r["t"]), float(r["t"]) + float(r["d"])
            for s in sections:
                ov = _overlap(r0, r1, s["t"], s["t"] + s["d"])
                if (ov >= 0.5 * s["d"] or ov >= 0.5 * (r1 - r0) or s["id"] == r.get("section_id")) and s["id"] not in out:
                    out.append(s["id"])
        if out:
            return sorted(out, key=lambda i: next(s["t"] for s in sections if s["id"] == i))
        # no EDM role found: a section labelled like the role (e.g. 'break' for breakdown) still counts
    return [s["id"] for s in sections if norm_label(s.get("label", "")) == w]
