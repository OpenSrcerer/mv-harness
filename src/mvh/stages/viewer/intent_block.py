"""The managed block the viewer writes into ``meaning/intent.md`` (the whole-song meaning, group and per-section
meaning, voice -> character mapping).

``meaning/intent.md`` is the user's own file (CONTRACT §1: never overwritten by ``mvh analyze``).  The viewer must
not disturb what the user wrote, so everything it adds lives between two HTML comment markers; text outside the
markers is preserved byte for byte.  Grammar (documented in docs/contract/decisions/M6a.md and UD3.md), read by M5
voices and M6b meaning as the user's authoritative words::

    <!-- mvh-viewer:begin v1 -->
    ## Viewer corrections
    ### Song
    - logline: ...
    - summary: ...
    - setting: ...
    - tone: ...
    - theme: ...             (one line per theme)
    - palette: #1b2a49, night blue
    - do not: ...            (one line per rule)
    ### Voices
    - V1 = C1 The Lamplighter
    ### Every section
    - feel: ...
    ### Every drop
    - movement: ...
    ### S02 verse#1 9.000-17.000 s
    - feel: ...
    - meaning: ...
    - movement: ...
    - camera: ...
    - palette: #1b2a49, #f2a541
    - do not: ...            (one line per rule)
    <!-- mvh-viewer:end -->

``### Song`` is the whole-song box. ``### Every section`` is the default for every section and ``### Every <label>``
the default for the sections with that label; a single section overrides its group (D81).
A section is anchored by its time range so ``mvh meaning`` can re-anchor it by overlap when boundaries move.
Single-line values: a line break inside a value is stored as `` / ``.
"""
from __future__ import annotations

import re
from typing import Any

BEGIN = "<!-- mvh-viewer:begin v1 -->"
END = "<!-- mvh-viewer:end -->"
_BLOCK_RE = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", re.S)
_VOICE_RE = re.compile(r"^- (V[1-9]\d*) = (C[1-9]\d*)(?: (.*))?$")
_SEC_RE = re.compile(r"^### (S\d{2,})(?: (\S.*?))? (-?\d+(?:\.\d+)?)-(-?\d+(?:\.\d+)?) s$")
_GROUP_RE = re.compile(r"^### Every (\S.*?)$")
_KV_RE = re.compile(r"^- (feel|meaning|movement|camera|palette|do not): ?(.*)$")
_SONG_KV_RE = re.compile(r"^- (logline|summary|setting|tone|theme|palette|do not): ?(.*)$")
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_GROUP_KEY_RE = re.compile(r"^[a-z][a-z\-]{0,39}$")
FIELDS = ("feel", "meaning", "movement", "camera", "palette", "do_not")
SONG_TEXT = ("logline", "summary", "setting", "tone")
SONG_FIELDS = SONG_TEXT + ("themes", "palette", "do_not")
GROUP_FIELDS = ("feel", "meaning", "movement", "camera", "palette")
MAX_LEN = 2000


class IntentError(ValueError):
    pass


# every separator str.splitlines() honours: \n \r VT FF FS GS RS NEL LS PS
_LINE_SEPS = "\n\r\x0b\x0c\x1c\x1d\x1e\x85  "
_SEP_RE = re.compile(r"\s*[" + _LINE_SEPS + r"]+\s*")


def _one_line(s: Any) -> str:
    text = _SEP_RE.sub(" / ", str(s or "").strip())
    return text.replace("<!--", "<! --").replace("-->", "-- >")  # a value can never open or close the block


def _items(v: Any) -> list[str]:
    """A list field given as a list or as text with one item per line."""
    if isinstance(v, str):
        v = re.split("[" + _LINE_SEPS + "]", v)
    if not isinstance(v, (list, tuple)):
        return []
    return [_one_line(x)[:MAX_LEN] for x in v if str(x or "").strip()]


def empty() -> dict[str, Any]:
    return {"voices": {}, "sections": {}, "song": {}, "groups": {}}


def parse(text: str) -> dict[str, Any]:
    """The viewer-managed state inside ``text`` (empty when there is no block)."""
    state = empty()
    m = _BLOCK_RE.search(text or "")
    if not m:
        return state
    cur: dict[str, Any] | None = None
    song: dict[str, Any] | None = None
    for raw in m.group(0).split("\n"):
        line = raw.rstrip()
        vm = _VOICE_RE.match(line)
        if vm:
            state["voices"][vm.group(1)] = {"character_id": vm.group(2), "name": (vm.group(3) or vm.group(2)).strip()}
            continue
        if line.startswith("### "):
            cur = song = None
            if line == "### Song":
                song = state["song"]
                continue
            sm = _SEC_RE.match(line)
            if sm:
                cur = {"t0": float(sm.group(3)), "t1": float(sm.group(4)), "label": sm.group(2) or "", "do_not": []}
                state["sections"][sm.group(1)] = cur
                continue
            gm = _GROUP_RE.match(line)
            if gm:
                key = "all" if gm.group(1).lower() == "section" else gm.group(1).lower()
                cur = state["groups"].setdefault(key, {})
            continue
        if song is not None:
            km = _SONG_KV_RE.match(line)
            v = km.group(2).strip() if km else ""
            if not v:
                continue
            k = km.group(1)
            if k == "theme":
                song.setdefault("themes", []).append(v)
            elif k == "do not":
                song.setdefault("do_not", []).append(v)
            else:
                song[k] = v
            continue
        km = _KV_RE.match(line)
        if km and cur is not None:
            k, v = km.group(1).replace(" ", "_"), km.group(2).strip()
            if k == "do_not":
                if v:
                    cur.setdefault("do_not", []).append(v)
            else:
                cur[k] = v
    return state


def _text(rec: dict[str, Any], k: str) -> str:
    v = _one_line(rec.get(k, ""))
    if len(v) > MAX_LEN:
        raise IntentError(f"{k} is longer than {MAX_LEN} characters")
    return v


def _hex_palette(rec: dict[str, Any]) -> str:
    pal = [p.strip() for p in re.split(r"[,\s]+", str(rec.get("palette") or "")) if p.strip()]
    for p in pal:
        if not _HEX_RE.match(p):
            raise IntentError(f"palette entries are #rrggbb colours, got {p[:12]!r}")
    return ", ".join(p.lower() for p in pal)


def _validate_section(rec: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        out["t0"], out["t1"] = round(float(rec["t0"]), 3), round(float(rec["t1"]), 3)
    except (KeyError, TypeError, ValueError) as e:
        raise IntentError("a section needs numeric t0 and t1") from e
    if not out["t1"] > out["t0"]:
        raise IntentError("a section needs t1 > t0")
    out["label"] = _one_line(rec.get("label", ""))[:80]
    for k in ("feel", "meaning", "movement", "camera"):
        out[k] = _text(rec, k)
    out["palette"] = _hex_palette(rec)
    out["do_not"] = _items(rec.get("do_not", []))
    return out


def _validate_group(rec: Any) -> dict[str, Any]:
    """A group record (every section / every <label>): only the fields that have a value."""
    if not isinstance(rec, dict):
        raise IntentError("a group must be an object")
    out = {k: _text(rec, k) for k in ("feel", "meaning", "movement", "camera")}
    out["palette"] = _hex_palette(rec)
    return {k: v for k, v in out.items() if v}


def _validate_song(rec: Any) -> dict[str, Any]:
    """The whole-song record: only the fields that have a value. The song palette takes colour words too."""
    if not isinstance(rec, dict):
        raise IntentError("song must be an object")
    out: dict[str, Any] = {k: _text(rec, k) for k in SONG_TEXT}
    pal = rec.get("palette") or ""
    if isinstance(pal, (list, tuple)):
        pal = ", ".join(str(p) for p in pal)
    toks = [_one_line(p)[:40] for p in re.split("[," + _LINE_SEPS + "]", str(pal)) if p.strip()]
    out["palette"] = ", ".join(toks)
    out["themes"] = [t[:200] for t in _items(rec.get("themes", []))]
    out["do_not"] = _items(rec.get("do_not", []))
    return {k: v for k, v in out.items() if v}


def merge(state: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Apply a viewer patch: ``voices`` {V1: {character_id, name} | None}, ``sections`` {S02: {...} | None},
    ``song`` {...} | None (replaces the whole-song record) and ``groups`` {all | <label>: {...} | None}."""
    out = {"voices": dict(state.get("voices", {})), "sections": dict(state.get("sections", {})),
           "song": dict(state.get("song", {})), "groups": dict(state.get("groups", {}))}
    for vid, rec in (patch.get("voices") or {}).items():
        if not re.fullmatch(r"V[1-9]\d*", str(vid)):
            raise IntentError(f"bad voice id {str(vid)[:12]!r}")
        if rec is None:
            out["voices"].pop(vid, None)
            continue
        cid = str(rec.get("character_id", ""))
        if not re.fullmatch(r"C[1-9]\d*", cid):
            raise IntentError(f"bad character id {cid[:12]!r}")
        out["voices"][vid] = {"character_id": cid, "name": _one_line(rec.get("name") or cid)[:80] or cid}
    for sid, rec in (patch.get("sections") or {}).items():
        if not re.fullmatch(r"S\d{2,}", str(sid)):
            raise IntentError(f"bad section id {str(sid)[:12]!r}")
        if rec is None:
            out["sections"].pop(sid, None)
            continue
        clean = _validate_section(rec)
        if not any(clean[k] for k in ("feel", "meaning", "movement", "camera", "palette")) and not clean["do_not"]:
            out["sections"].pop(sid, None)
        else:
            out["sections"][sid] = clean
    if "song" in patch:
        out["song"] = {} if patch["song"] is None else _validate_song(patch["song"])
    for key, rec in (patch.get("groups") or {}).items():
        key = str(key).strip().lower()
        if key in ("section", "sections") or not _GROUP_KEY_RE.match(key):
            raise IntentError(f"bad group {key[:12]!r}")
        clean = {} if rec is None else _validate_group(rec)
        if clean:
            out["groups"][key] = clean
        else:
            out["groups"].pop(key, None)
    return out


def _sid_key(s: str) -> int:
    return int(s[1:])


def render(state: dict[str, Any]) -> str:
    lines = [BEGIN, "## Viewer corrections",
             "_Written by `mvh view`. This block is the latest edit, so it wins over the template above. Change these values in the viewer, or right here._"]
    song = state.get("song") or {}
    if song:
        lines += ["", "### Song"]
        for k in SONG_TEXT:
            if song.get(k):
                lines.append(f"- {k}: {song[k]}")
        for t in song.get("themes", []):
            lines.append(f"- theme: {t}")
        if song.get("palette"):
            lines.append(f"- palette: {song['palette']}")
        for d in song.get("do_not", []):
            lines.append(f"- do not: {d}")
    if state.get("voices"):
        lines += ["", "### Voices"]
        for vid in sorted(state["voices"], key=lambda v: int(v[1:])):
            r = state["voices"][vid]
            lines.append(f"- {vid} = {r['character_id']} {r.get('name') or r['character_id']}")
    groups = state.get("groups") or {}
    for key in sorted(groups, key=lambda k: (k != "all", k)):
        lines += ["", "### Every " + ("section" if key == "all" else key)]
        for k in GROUP_FIELDS:
            if groups[key].get(k):
                lines.append(f"- {k}: {groups[key][k]}")
    for sid in sorted(state.get("sections", {}), key=_sid_key):
        r = state["sections"][sid]
        head = f"### {sid}" + (f" {r['label']}" if r.get("label") else "") + f" {r['t0']:.3f}-{r['t1']:.3f} s"
        lines += ["", head]
        for k, name in (("feel", "feel"), ("meaning", "meaning"), ("movement", "movement"), ("camera", "camera"), ("palette", "palette")):
            if r.get(k):
                lines.append(f"- {name}: {r[k]}")
        for d in r.get("do_not", []):
            lines.append(f"- do not: {d}")
    lines.append(END)
    return "\n".join(lines) + "\n"


def apply(text: str, state: dict[str, Any]) -> str:
    """Replace (or append) the managed block in ``text``; everything outside it is untouched."""
    empty_state = not any(state.get(k) for k in ("voices", "sections", "song", "groups"))
    if _BLOCK_RE.search(text or ""):
        if empty_state:
            return _BLOCK_RE.sub("", text, count=1).rstrip("\n") + ("\n" if text.strip() else "")
        # a lambda keeps backslashes in the block literal
        block = render(state)
        return _BLOCK_RE.sub(lambda _m: block, text, count=1)
    if empty_state:
        return text
    base = text or "# What this song means to me (meaning/intent.md)\n"
    if not base.endswith("\n"):
        base += "\n"
    return base + "\n" + render(state)
