# ruff: noqa: E501
"""``mvh meaning <folder> --draft anthropic``: draft the meaning gaps with the Claude API (PLAN §8.3).

Opt-in only (the user runs the command; it needs ANTHROPIC_API_KEY or an ``ant auth login`` profile and the network).
It sends request.md, input.json, schema.json, the user's intent.md and, unless lyrics are kept from agents,
lyrics/lines.tsv. The answer is checked (schema, citations, quotes <= 10 words, status forced to ``draft``) and
returned; the CLI writes it to ``meaning/authored.json``, then re-runs meaning and brief. Nothing is logged except
counts (NF5). Model: claude-opus-5-5, adaptive thinking (default), effort high, streaming, server-side refusal
fallbacks enabled.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

__all__ = ["draft_with_anthropic", "MODEL", "DraftError"]

MODEL = "claude-opus-5-5"
SYSTEM = (
    "You draft the meaning layer of a music-video analysis bundle. The user is the authority on what their song "
    "means: never contradict meaning/intent.md, only fill the gaps listed in facts.gaps, and turn conflicts into "
    "open_questions. Every claim is typed (source: lyric | audio | external | speculative, never user) and cites "
    "ids or time ranges from input.json; quotes are at most 10 words. Keep character ids and the voice mapping of "
    "facts.characters. Do not write do_not rules (suggest them in open_questions). Reply with one JSON object that "
    "validates against the given schema, with \"status\": \"draft\", and nothing else."
)


class DraftError(RuntimeError):
    pass


def _read(p: Path) -> str | None:
    if not p.is_file():
        return None
    with open(p, encoding="utf-8-sig") as fh:
        return fh.read()


def _extract_json(text: str) -> Any:
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", t, re.S)
    if m:
        t = m.group(1)
    else:
        a, b = t.find("{"), t.rfind("}")
        if a >= 0 and b > a:
            t = t[a:b + 1]
    return json.loads(t)


def _problems(doc: Any, folder: Path) -> tuple[Any, list[str]]:
    from mvh.contract import schemas

    from .cites import check_claims

    if not isinstance(doc, dict):
        return doc, ["the answer is not a JSON object"]
    doc["status"] = "draft"
    doc.setdefault("schema", "mvh/files/meaning")
    from mvh.contract.catalog import CONTRACT_VERSION

    doc.setdefault("schema_version", CONTRACT_VERSION)
    errs = schemas.validate(doc, "mvh/files/meaning")
    inp = json.loads(_read(folder / "meaning" / "input.json") or "{}")
    known = {s["id"] for s in inp.get("sections", [])}
    for c in (inp.get("facts") or {}).get("characters", []):
        known.add(c["id"])
        known.update(c.get("voice_ids") or [])
    lines = _read(folder / "lyrics" / "lines.tsv") or ""
    known.update(ln.split("\t", 1)[0] for ln in lines.splitlines()[1:] if ln)
    for c in (inp.get("facts") or {}).get("cues_tier1", []):
        known.add(c["id"])
    for m in (inp.get("facts") or {}).get("moments", []):
        known.add(m.get("cue_id"))
    known.update(str(c.get("id")) for c in doc.get("characters") or [] if isinstance(c, dict))
    known.update(str(m.get("id")) for m in doc.get("motifs") or [] if isinstance(m, dict))
    dur = float((inp.get("song") or {}).get("duration_s") or 1e9)
    fixed, probs = check_claims(doc, known, dur, status="draft")
    return fixed, errs[:20] + probs[:20]


def draft_with_anthropic(folder: Path | str, *, lyrics_to_agents: bool = True, effort: str = "high",
                         log=print) -> dict[str, Any]:
    """-> the checked draft (a dict for meaning/authored.json). Raises DraftError."""
    try:
        import anthropic
    except ImportError as e:  # the optional extra
        raise DraftError("the 'anthropic' package is not installed (optional extra: mvh[anthropic])") from e
    folder = Path(folder)
    req, inp, sch = (_read(folder / "meaning" / n) for n in ("request.md", "input.json", "schema.json"))
    if not (req and inp and sch):
        raise DraftError("run `mvh analyze` first: meaning/request.md, input.json and schema.json are missing")
    parts = [f"<request>\n{req}\n</request>", f"<input_json>\n{inp}\n</input_json>", f"<schema_json>\n{sch}\n</schema_json>"]
    intent = _read(folder / "meaning" / "intent.md")
    parts.append(f"<intent_md>\n{intent}\n</intent_md>" if intent else "<intent_md>(empty: the user has not answered)</intent_md>")
    if lyrics_to_agents and json.loads(inp).get("lines_file"):
        lines = _read(folder / "lyrics" / "lines.tsv")
        if lines:
            parts.append(f"<lines_tsv>\n{lines}\n</lines_tsv>")
    parts.append("Write the meaning/authored.json draft now: one JSON object only.")
    client = anthropic.Anthropic()
    messages: list[dict[str, Any]] = [{"role": "user", "content": "\n\n".join(parts)}]
    last_probs: list[str] = []
    for attempt in range(2):
        try:
            with client.beta.messages.stream(
                model=MODEL, max_tokens=64000, system=SYSTEM, messages=messages,
                output_config={"effort": effort},
                betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            ) as stream:
                msg = stream.get_final_message()
        except anthropic.AuthenticationError as e:
            raise DraftError("no Anthropic credentials (set ANTHROPIC_API_KEY or run `ant auth login`)") from e
        except anthropic.RateLimitError as e:
            raise DraftError("rate limited by the Anthropic API; try again later") from e
        except anthropic.APIStatusError as e:
            raise DraftError(f"Anthropic API error {e.status_code}") from e
        except anthropic.APIConnectionError as e:
            raise DraftError("cannot reach the Anthropic API (offline?)") from e
        if msg.stop_reason == "refusal":
            raise DraftError("the model declined to draft (stop_reason refusal)")
        if msg.stop_reason == "max_tokens":
            raise DraftError("the draft hit max_tokens")
        text = "".join(b.text for b in msg.content if b.type == "text")
        try:
            doc = _extract_json(text)
        except ValueError:
            doc, last_probs = None, ["the answer is not valid JSON"]
        else:
            doc, last_probs = _problems(doc, folder)
            schema_errs = [p for p in last_probs if "(dropped)" not in p and "(cut" not in p and "(set to" not in p]
            if not schema_errs:
                log(f"mvh meaning: draft received ({len(last_probs)} citation repairs)")
                return doc
        log(f"mvh meaning: draft attempt {attempt + 1} had {len(last_probs)} problems; asking for a fix")
        messages = messages + [{"role": "assistant", "content": msg.content},
                               {"role": "user", "content": "Fix these problems and reply with the full JSON object only:\n- "
                                + "\n- ".join(last_probs[:20])}]
    if isinstance(doc, dict):
        log("mvh meaning: using the draft with its remaining problems repaired where possible")
        return doc
    raise DraftError("the model did not return a usable JSON draft")
