# ruff: noqa: E501
"""R-WORDS M6b round 2: draft text still presented as the user's (residuals of round-1 F1 / r-contract F2).

N5 (major): meaning.singing.build_characters fills a user character's missing ``name`` / ``description`` from the
draft (``filled_by_draft``), but that marker never reaches meaning.json: the character keeps
``provenance.status: user`` with no per-field source, and brief.md prints the draft's name and description in the
character table with no ``(draft)`` label. The interview's YAML template then prefills the draft's name as the
user's answer (``name: "<draft name>"``), so pasting it back turns the draft into a user claim.

N6 (major): the fix labels draft fields in brief.md only. skill/mv-harness (SKILL.md, references/RECIPES.md) still
tells agents that ``provenance.status === 'draft'`` / ``meaning: draft`` is how to recognise agent text, and
``song.meaningAt(t)`` returns no per-field source. On the synthetic song (intent.md + authored.json) sections whose
provenance.status is ``user`` carry draft camera / movement / palette hints, which an agent following the recipe
treats as the user's directions. ``field_sources`` is not mentioned anywhere under skill/.
"""
from __future__ import annotations

import re

from rw_m6b_support import ROOT, SYNTH, authored, brief_for, source

from mvh.stages.meaning.stage import build

INTENT = "```yaml\ncharacters:\n  C1: {voices: [V1]}\n  C2: {name: \"The Tide\", voices: [V2]}\n```\n"


def _res():
    return build(source(), INTENT, authored(), {})


def test_draft_filled_character_fields_are_labelled_in_the_brief():
    res = _res()
    c1 = next(c for c in res["meaning"]["characters"] if c["id"] == "C1")
    draft_c1 = next(c for c in authored()["characters"] if c["id"] == "C1")
    assert c1["name"] == draft_c1["name"] and c1["description"] == draft_c1["description"]  # came from the draft
    rows = [ln for ln in brief_for(res).splitlines() if re.match(r"\| C[12] \|", ln)]
    unlabelled = [ln.split("|")[1].strip() for ln in rows if "draft" not in ln.lower()]
    assert not unlabelled, f"draft name/description shown as the user's for {unlabelled}"


def test_draft_filled_character_is_not_marked_entirely_user_in_meaning_json():
    res = _res()
    c1 = next(c for c in res["meaning"]["characters"] if c["id"] == "C1")
    marked = (c1["provenance"]["status"] != "user") or ("draft" in str(c1.get("field_sources") or {}))
    assert marked, "meaning.json gives no sign that C1's name and description are the draft's (status user, no field_sources)"


def test_template_does_not_prefill_a_draft_name_as_the_users_answer():
    res = _res()
    iv = res["interview"]
    tpl = iv[iv.index("```yaml"):]
    c1 = next(ln for ln in tpl.splitlines() if ln.strip().startswith("C1:"))
    draft_name = next(c for c in authored()["characters"] if c["id"] == "C1")["name"]
    assert draft_name not in c1, "the template prefills the draft's character name as if the user had written it"


def test_skill_tells_agents_how_to_spot_draft_fields_in_user_sections():
    with open(SYNTH / "meaning" / "intent.md", encoding="utf-8") as fh:
        intent = fh.read()
    res = build(source(), intent, authored(), {})
    mixed = [s["section_id"] for s in res["meaning"]["sections"]
             if s["provenance"]["status"] == "user" and "draft" in (s.get("field_sources") or {}).values()]
    assert mixed, "control: the synthetic song has sections mixing user and draft fields"
    skill = ""
    for p in (ROOT / "skill" / "mv-harness" / "SKILL.md", ROOT / "skill" / "mv-harness" / "references" / "RECIPES.md"):
        with open(p, encoding="utf-8") as fh:
            skill += fh.read()
    assert "field_sources" in skill, (
        f"sections {mixed} have provenance.status 'user' but draft fields; SKILL/RECIPES only tell agents to check "
        "provenance.status === 'draft', so these draft hints are used as the user's")
