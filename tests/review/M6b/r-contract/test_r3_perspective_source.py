"""R-CONTRACT (M6b) round 3, R3-5 (major; same class as R2-4/R2-5 and N5/N6, on a field the fix missed).

SKILL.md §3 now says: "A `user` section or character can still hold draft text: meaning.json
sections[].field_sources and characters[].field_sources (and the top-level field_sources) give each field's
origin, user or draft. Treat every draft field as a suggestion, whatever provenance.status says".

``perspective`` (narrator / addressee: who sings to whom) is filled from authored.json when the user did not give
it, but it gets no entry in the top-level ``field_sources`` (logline, summary, setting, tone, themes, symbolism,
motifs and palette do). With a user story plus the synth draft, meaning.json has status ``user`` and perspective
``{narrator: C1, addressee: C2}`` from the draft, with nothing that marks it as the draft's. An agent that follows
the SKILL (and RECIPES' ``isDraft`` fallback to the status) takes the draft's narrator/addressee as the user's
direction. meaning.md prints it unlabelled too.
"""
from __future__ import annotations

from rc2_support import authored, source

from mvh.stages.meaning.stage import build


def test_draft_perspective_is_marked_as_draft() -> None:
    a = authored()
    assert (a.get("perspective") or {}).get("narrator"), "precondition: the synth draft has a perspective"
    m = build(source(), "## The story\nA keeper waits for the light.\n", a, {})["meaning"]
    assert m["status"] == "user" and m["perspective"]["narrator"] == a["perspective"]["narrator"], "precondition"
    fs = m.get("field_sources") or {}
    marks = {k: v for k, v in fs.items() if k.startswith("perspective")}
    assert marks and all(v == "draft" for v in marks.values()), (
        f"perspective {m['perspective']} comes from authored.json but field_sources has no perspective entry "
        f"(field_sources={fs}); with status 'user' an agent reads it as the user's")
