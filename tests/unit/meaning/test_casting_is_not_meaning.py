"""D85: naming the characters behind voices (casting, as the viewer writes it) is not an answer about the song's
meaning. A song whose intent.md only casts stays "pending", so an agent interviews the user before building; the
characters stay the user's. A character described in the user's words does count."""
from __future__ import annotations

import json
from pathlib import Path

CAST_ONLY = """<!-- mvh-viewer:begin v1 -->
_Written by `mvh view`._

- V1 = C1 Gorgax
- V2 = C2 Narrator
<!-- mvh-viewer:end -->
"""

DESCRIBED = """```yaml
characters:
  C1: {name: "Gorgax", description: "a tired space pirate", voices: [V1], lead_backing: lead}
```
"""


def _run(make_devrun, text):
    dr = make_devrun()
    (dr.song_dir / "meaning" / "intent.md").write_text(text, encoding="utf-8")
    done = dr.run("meaning")
    assert done["status"] in ("ok", "degraded"), done
    with open(Path(dr.upstream["meaning"]["dir"]) / "meaning" / "meaning.json", encoding="utf-8") as fh:
        return done, json.load(fh)


def test_casting_alone_leaves_the_meaning_pending(make_devrun):
    done, m = _run(make_devrun, CAST_ONLY)
    assert m["status"] == "pending"
    assert {c["id"]: c["name"] for c in m["characters"] if c["provenance"]["status"] == "user"} == \
        {"C1": "Gorgax", "C2": "Narrator"}                                   # the casting is kept as the user's
    assert not any("no answer was recognised" in w for w in done["result"].get("warnings", []))
    assert m["open_questions"][0].startswith("The meaning is pending")


def test_a_described_character_is_an_answer(make_devrun):
    _, m = _run(make_devrun, DESCRIBED)
    assert m["status"] == "user"
