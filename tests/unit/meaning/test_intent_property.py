"""Property-style tests of the intent grammar (UD1, mvh-intent v2) over generated answers (seeded, no extra deps).

1. Template answers: a random set of answers is written as a template in a random style (fenced or not, marker or
   not, flow or block maps and lists, quoted or plain values, unquoted hex colours, hint comments, voice mapping as
   ``characters.*.voices`` or ``voices: V1: C1``, line singers as a map or bullets, shuffled key order, free text
   before / after). Parsing it gives exactly the generated answers, and the free text exactly as notes.
2. The exact round trip through the interview: build -> regenerated template -> build gives the same user claims, and
   the template of the template is the template (a fixed point).
3. Free text: random markdown made of the shapes the old heuristic grammar parsed (do-not headings and labels, bold
   labels, section notes, character and voice lines, per-line singers) is never a field or a rule, and every line of
   it is kept verbatim in the notes.
Synthetic text only."""
from __future__ import annotations

import json
import random
from typing import Any

import pytest

from mvh.stages.meaning.colors import parse_palette
from mvh.stages.meaning.intent import parse_intent
from mvh.stages.meaning.stage import build

WORDS = ["harbour", "lantern", "night", "tide", "keeper", "dawn", "salt", "rust", "paper", "river", "café", "naïve",
         "it's", "1920s", "50%", "#1 hit", "fog: thick", "yes", "slow,", "warm", "x:", "@home", "a/b", "(soft)", "!",
         "brass & smoke", "what?", "on"]
HEXES = ["#c93523", "#0e2346", "#f2a541", "#faf8f3", "#2a5ea3", "#112233"]
COLOURS = ["night blue", "rust red", "lantern amber", "paper white", "harbour blue", "deep teal"]
LABELS = ["intro", "verse", "chorus", "chorus#2", "last chorus", "bridge", "drop", "outro"]
FREE_BEFORE = ["## The story\nA keeper waits for the light.", "Some thoughts first: keep it slow."]
FREE_AFTER = ["The end should be quiet.", "## Never show\n- No confetti.", "## Notes\nChorus: everything glows."]


def _text(rng: random.Random, n: tuple[int, int] = (1, 6)) -> str:
    return " ".join(rng.choice(WORDS) for _ in range(rng.randint(*n)))


def _texts(rng: random.Random, k: int, n: tuple[int, int] = (1, 6)) -> list[str]:
    """k distinct texts (list answers are unions: a repeated rule or note is kept once)."""
    out: list[str] = []
    while len(out) < k:
        t = _text(rng, n)
        if t not in out:
            out.append(t)
    return out


def _q(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def _plain_ok(s: str) -> bool:
    """Plain (unquoted) is allowed when the grammar's tolerance must keep it as typed."""
    return not s.startswith(("'", '"', "[", "{", "|", ">", "- ")) and s == s.strip() and s not in ("~", "null")


def _scalar(rng: random.Random, s: str) -> str:
    return s if rng.random() < 0.5 and _plain_ok(s) else _q(s)


def _comment(rng: random.Random) -> str:
    return rng.choice(["", "", "   # " + _text(rng, (1, 3)), "\t# note"])


def gen_answers(rng: random.Random, line_ids: list[str], section_keys: list[str]) -> dict[str, Any]:
    a: dict[str, Any] = {}
    for k in ("logline", "summary", "setting", "tone"):
        if rng.random() < 0.6:
            a[k] = _text(rng)
    for k in ("themes", "references", "symbolism", "notes"):
        if rng.random() < 0.5:
            a[k] = _texts(rng, rng.randint(1, 3), (1, 4))
    if "notes" in a and rng.random() < 0.3:
        a["notes"].append(_text(rng) + "\n" + _text(rng))  # a multi-line note
    nc = rng.randint(0, 3)
    voices = [f"V{i}" for i in range(1, 5)]
    rng.shuffle(voices)
    chars = {}
    for i in range(1, nc + 1):
        vs = sorted([voices.pop() for _ in range(rng.randint(0, min(2, len(voices))))], key=lambda v: int(v[1:]))
        chars[f"C{i}"] = {"name": _text(rng, (1, 3)), "description": _text(rng) if rng.random() < 0.5 else None,
                          "voices": vs, "lead_backing": rng.choice([None, "lead", "backing", "both"])}
    if chars:
        a["characters"] = chars
        a["voice_style"] = rng.choice(["lists", "voices_map", "voices_bullets"])
        if rng.random() < 0.5:
            ids = list(chars)
            a["perspective"] = {"narrator": rng.choice(ids), "addressee": rng.choice(ids + ["the sea"])}
        ls = {}
        for lid in rng.sample(line_ids, rng.randint(0, 3)):
            ls[lid] = sorted(rng.sample(list(chars), rng.randint(1, min(2, len(chars)))), key=lambda c: int(c[1:]))
        if ls:
            a["line_singers"] = ls
    elif rng.random() < 0.3:
        a["n_voices"] = rng.randint(1, 4)
    if rng.random() < 0.6:
        a["palette"] = rng.sample(HEXES, rng.randint(0, 2)) + rng.sample(COLOURS, rng.randint(0, 2))
        if not a["palette"]:
            del a["palette"]
    if rng.random() < 0.6:
        a["do_not"] = _texts(rng, rng.randint(1, 3))
    if rng.random() < 0.4:
        a["motifs"] = [{"name": _text(rng, (1, 2)), "lines": sorted(rng.sample(line_ids, rng.randint(0, 2))),
                        "note": _text(rng) if rng.random() < 0.5 else None} for _ in range(rng.randint(1, 2))]
    secs = {}
    for key in rng.sample(section_keys, rng.randint(0, 3)):
        s = {f: _text(rng) for f in ("feel", "meaning", "emotion", "movement", "camera") if rng.random() < 0.5}
        if rng.random() < 0.4:
            s["palette"] = rng.sample(HEXES, rng.randint(1, 2))
        if chars and rng.random() < 0.4:
            s["characters"] = sorted(rng.sample(list(chars), 1))
        if rng.random() < 0.4:
            s["do_not"] = [_text(rng)]
        if s:
            secs[key] = s
    if secs:
        a["sections"] = secs
    return a


def render(rng: random.Random, a: dict[str, Any]) -> tuple[str, list[str]]:
    """-> (intent.md text, the free-text notes it carries)."""
    blocks: list[list[str]] = []
    for k in ("logline", "summary", "setting", "tone"):
        if k in a:
            blocks.append([f"{k}: {_scalar(rng, a[k])}{_comment(rng)}"])
    for k in ("themes", "references", "symbolism", "notes"):
        if k in a:
            if rng.random() < 0.5 or any("\n" in x for x in a[k]):
                blocks.append([f"{k}: [" + ", ".join(_q(x) for x in a[k]) + "]" + _comment(rng)])
            else:
                blocks.append([f"{k}:{_comment(rng)}"] + [f"  - {_scalar(rng, x)}" for x in a[k]])
    if "perspective" in a:
        p = a["perspective"]
        blocks.append([f"perspective: {{narrator: {_q(p['narrator'])}, addressee: {_q(p['addressee'])}}}"]
                      if rng.random() < 0.5 else
                      ["perspective:", f"  narrator: {p['narrator']}", f"  addressee: {_scalar(rng, p['addressee'])}"])
    vmap_lines: list[str] = []
    if "characters" in a:
        style = a["voice_style"]
        lines = ["characters:" + _comment(rng)]
        for cid, c in a["characters"].items():
            vs = c["voices"] if style == "lists" else []
            if style != "lists":
                vmap_lines += [(f"  {v}: {cid}" if style == "voices_map" else f"  - {v} = {cid}") for v in c["voices"]]
            if rng.random() < 0.5:
                lines.append(f"  {cid}: {{name: {_q(c['name'])}, description: {_q(c['description'] or '')}, "
                             f"voices: [{', '.join(vs)}], lead_backing: {_q(c['lead_backing'] or '')}}}{_comment(rng)}")
            else:
                lines += [f"  {cid}:", f"    name: {_scalar(rng, c['name'])}"]
                if c["description"]:
                    lines.append(f"    description: {_scalar(rng, c['description'])}")
                lines.append(f"    voices: [{', '.join(vs)}]")
                if c["lead_backing"]:
                    lines.append(f"    lead_backing: {c['lead_backing']}")
        blocks.append(lines)
    if vmap_lines:
        blocks.append(["voices:" + _comment(rng)] + vmap_lines)
    elif "n_voices" in a:
        blocks.append([f"voices: {a['n_voices']}{_comment(rng)}"])
    if "line_singers" in a:
        items = list(a["line_singers"].items())
        r = rng.random()
        if r < 0.33:
            blocks.append(["line_singers: {" + ", ".join(f"{k}: {'+'.join(v)}" for k, v in items) + "}"])
        elif r < 0.66:
            blocks.append(["line_singers:" + _comment(rng)] + [f"  {k}: {'+'.join(v)}" for k, v in items])
        else:
            blocks.append(["line_singers:"] + [f"  - {k}: {' & '.join(v)}" for k, v in items])
    if "palette" in a:
        if rng.random() < 0.5:
            blocks.append(["palette: [" + ", ".join(a["palette"]) + "]" + _comment(rng)])
        else:
            blocks.append(["palette:"] + [f"  - {x}" for x in a["palette"]])
    if "do_not" in a:
        blocks.append(["do_not:" + _comment(rng)] + [f"  - {_scalar(rng, x)}" for x in a["do_not"]])
    if "motifs" in a:
        blocks.append(["motifs:"] + [f"  - {{name: {_q(m['name'])}, lines: [{', '.join(m['lines'])}], "
                                     f"note: {_q(m['note'] or '')}}}" for m in a["motifs"]])
    if "sections" in a:
        lines = ["sections:"]
        for key, s in a["sections"].items():
            lines.append(f"  {key}:{_comment(rng)}")
            for f in ("feel", "meaning", "emotion", "movement", "camera"):
                if f in s:
                    lines.append(f"    {f}: {_scalar(rng, s[f])}")
            if "palette" in s:
                lines.append(f"    palette: [{', '.join(s['palette'])}]")
            if "characters" in s:
                lines.append(f"    characters: [{', '.join(s['characters'])}]")
            if "do_not" in s:
                lines.append(f"    do_not: [{', '.join(_q(x) for x in s['do_not'])}]")
        blocks.append(lines)
    rng.shuffle(blocks)
    body = [ln for b in blocks for ln in b]
    head = rng.choice(["fenced", "fenced_marker", "unfenced", "unfenced_marker"])
    if head.endswith("marker"):
        body = ["# mvh-intent v2"] + body
    if head.startswith("fenced"):
        body = [rng.choice(["```yaml", "```yml", "```mvh-intent"])] + body + ["```"]
    notes: list[str] = []
    pre, post = [], []
    if rng.random() < 0.4:
        notes.append(rng.choice(FREE_BEFORE))
        pre = [notes[-1], ""]
    if rng.random() < 0.4:
        notes.append(rng.choice(FREE_AFTER))
        post = ["", notes[-1]]
    return "\n".join(pre + body + post) + "\n", notes


def _expected_sections(a: dict[str, Any]) -> list[tuple]:
    out = []
    for key, s in (a.get("sections") or {}).items():
        out.append((key, s.get("feel"), s.get("meaning"), s.get("emotion"), s.get("movement"), s.get("camera"),
                    s.get("palette") or [], s.get("characters") or [], s.get("do_not") or []))
    return out


def _got_sections(o: dict[str, Any]) -> list[tuple]:
    return [(s["key"], s["feel"], s["meaning"], s["emotion"], s["movement"], s["camera"], s["palette"], s["characters"],
             s["do_not"]) for s in o["sections"]]


LINE_IDS = [f"L{i:03d}" for i in range(1, 13)]
SECTION_KEYS = [f"S{i:02d}" for i in range(1, 7)] + LABELS


@pytest.mark.parametrize("seed", range(300))
def test_generated_template_answers_parse_exactly(seed):
    rng = random.Random(seed)
    a = gen_answers(rng, LINE_IDS, SECTION_KEYS)
    text, free = render(rng, a)
    o = parse_intent(text)
    ctx = f"seed {seed}:\n{text}"
    assert not o["warnings"], (o["warnings"], ctx)
    for k in ("logline", "summary", "setting", "tone"):
        assert o[k] == a.get(k), (k, ctx)
    for k in ("themes", "references", "symbolism"):
        assert o[k] == a.get(k, []), (k, ctx)
    assert o["notes"] == a.get("notes", []) + free, ctx
    assert o["free_notes"] == free, ctx
    assert o["perspective"] == (a.get("perspective") or {"narrator": None, "addressee": None}), ctx
    want_chars = {cid: dict(c) for cid, c in (a.get("characters") or {}).items()}
    assert o["characters"] == want_chars, ctx
    assert o["n_characters"] == (len(want_chars) or None)
    assert o["n_voices"] == a.get("n_voices"), ctx
    assert o["line_singers"] == a.get("line_singers", {}), ctx
    hexes, names, bad = parse_palette(a.get("palette", []))
    assert (o["palette"], o["palette_names"], o["palette_unparsed"]) == (hexes, names, bad), ctx
    assert o["do_not"] == a.get("do_not", []), ctx
    assert [(m["name"], m["lines"], m["note"]) for m in o["motifs"]] == [
        (m["name"], m["lines"], m["note"]) for m in a.get("motifs", [])], ctx
    assert _got_sections(o) == _expected_sections(a), ctx


@pytest.mark.parametrize("seed", range(40))
def test_generated_answers_round_trip_through_the_interview(synth_source, synth_source_parts, seed):
    from test_intent_grammar import _template, _user_claims

    files, events = synth_source_parts
    line_ids = [ln["id"] for ln in files["lyrics/lyrics.json"]["lines"]]
    section_keys = [s["id"] for s in events["sections"]] + ["intro", "chorus", "drop", "last chorus"]
    rng = random.Random(1000 + seed)
    text, _free = render(rng, gen_answers(rng, line_ids, section_keys))
    first = build(synth_source(), text, None, {})
    t1 = _template(first)
    again = build(synth_source(), t1, None, {})
    assert not again["intent"]["warnings"], again["intent"]["warnings"]
    assert _user_claims(again) == _user_claims(first), text
    assert _template(again) == t1


FREE_SHAPES = [
    "## Never show", "## What I don't want", "## Avoid at all costs", "**Never show:**", "**Avoid**", "Never show: blood",
    "- **Never show**: blood", "9. **Never show**: blood", "**Story:**", "Story: two keepers", "**Tone:** grey",
    "Palette: night blue, #f2a541", "**Palette:**", "- night blue", "Intro: slow drift. Verse: call and response",
    "- Chorus: wide shots", "C1 The Keeper = V1 (low). Lead.", "- C2: The Tide = V2", "V1 = C1 The Keeper",
    "V2 is C2, the Child.", "L005: C1+C2", "Narrator: C1", "Themes: loss, light", "# Never Let Me Go",
    "## The story: a night that never ends", "Logline: A night watch.", "- blood", "- lens flares", "",
    "Two keepers wait for a ship that never returns.",
]


@pytest.mark.parametrize("seed", range(200))
def test_generated_free_text_is_only_notes(seed):
    rng = random.Random(5000 + seed)
    lines = [rng.choice(FREE_SHAPES) for _ in range(rng.randint(1, 14))]
    text = "\n".join(lines) + "\n"
    o = parse_intent(text)
    ctx = f"seed {seed}:\n{text}"
    assert o["do_not"] == [] and o["sections"] == [] and o["characters"] == {} and o["line_singers"] == {}, ctx
    assert not any(o[k] for k in ("logline", "summary", "setting", "tone", "themes", "symbolism", "palette",
                                  "palette_unparsed", "motifs", "references")), ctx
    assert o["perspective"] == {"narrator": None, "addressee": None} and o["n_voices"] is None, ctx
    joined = "\n".join(o["notes"])
    for ln in lines:
        assert ln.rstrip() in joined, (ln, ctx)
    assert o["notes"] == o["free_notes"] and not o["warnings"], ctx
