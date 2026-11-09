"""The meaning stage through the runner's child entry point (Ctx, Writer, schema validation, done.json), the
inputs-are-never-written rule, and the real-song runs (opt-in)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mvh.contract import schemas

ROOT = Path(__file__).resolve().parents[3]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_stage_run_synth_never_writes_inputs(make_devrun):
    dr = make_devrun(intent=True, authored=True)
    ins = {p: _sha(p) for p in (dr.song_dir / "meaning").iterdir()}
    done = dr.run("meaning")
    assert done["status"] == "ok" and done["result"]["summary"]["status"] == "user"
    out = Path(dr.upstream["meaning"]["dir"])
    for rel in ("events/singing.json", "lyrics/lines.tsv", "meaning/meaning.json", "meaning/orphans.json",
                "meaning/input.json", "meaning/schema.json", "meaning/interview.md", "meaning/request.md",
                "meaning/meaning.md"):
        assert (out / rel).is_file(), rel
    assert {p: _sha(p) for p in (dr.song_dir / "meaning").iterdir()} == ins  # inputs untouched
    assert "meaning/intent.md" not in done["outputs"] and "meaning/authored.json" not in done["outputs"]
    with open(out / "events/singing.json", encoding="utf-8") as fh:
        env = json.load(fh)
    assert schemas.validate(env, "mvh/events/singing") == []
    assert {"conf", "source", "review"} <= set(env["fields"])  # additive fields are documented
    tsv = (out / "lyrics/lines.tsv").read_text(encoding="utf-8").splitlines()
    assert tsv[0].split("\t") == ["id", "t", "d", "section_id", "singer", "repeat_group", "grade", "text"]


def test_writer_refuses_user_inputs(make_devrun):
    from mvh.runner.ctx import StageWriter
    from mvh.runner.spec import UndeclaredOutput, load_stage_specs

    spec = load_stage_specs()["meaning"]
    dr = make_devrun()
    w = StageWriter(spec, dr.work / "x", dr._job("meaning", spec, dr.work / "x", {}))
    for rel in ("meaning/intent.md", "meaning/authored.json"):
        with pytest.raises(UndeclaredOutput):
            w.text(rel, "x")


def test_deterministic(make_devrun, tmp_path):
    dr = make_devrun(intent=True)
    a = dr.run("meaning")
    b = dr.run("meaning")
    assert {k: v["sha256"] for k, v in a["outputs"].items()} == {k: v["sha256"] for k, v in b["outputs"].items()}


REAL_EXPECT = {  # snapshot counts (tolerances: exact for counts read from fixtures)
    "megafauna": {"n_lines": 0, "characters": 0, "status": "pending"},
    "versatile": {"n_lines": 0, "characters": 0, "status": "pending"},
    "jeremy": {"n_lines": 40, "characters": 1, "status": "pending"},
    "newton-vs-nye": {"n_lines": 51, "characters": 2, "status": "pending"},
}


@pytest.mark.real
@pytest.mark.parametrize("slug", sorted(REAL_EXPECT))
def test_real_song(make_devrun, slug):
    fx = ROOT / "tests" / "contract" / f"real-{slug}"
    if not fx.is_dir():
        pytest.skip(f"{fx} missing")
    dr = make_devrun(fixture=fx)
    done = dr.run("meaning")
    s = done["result"]["summary"]
    exp = REAL_EXPECT[slug]
    assert s["n_lines"] == exp["n_lines"] and s["n_characters"] == exp["characters"] and s["status"] == exp["status"]
    out = Path(dr.upstream["meaning"]["dir"])
    with open(out / "events/singing.json", encoding="utf-8") as fh:
        items = json.load(fh)["items"]
    lines = (out / "lyrics/lines.tsv").read_text(encoding="utf-8").splitlines()[1:]
    assert len(lines) == exp["n_lines"]
    assert all(ln.split("\t")[4] for ln in lines)  # every line has a singer
    assert {i["line_id"] for i in items} == {ln.split("\t")[0] for ln in lines}
    if slug == "newton-vs-nye":
        assert {i["voice_id"] for i in items} == {"V1", "V2"}
        assert s["review_lines"] >= 40  # the W0 voice spans are all flagged for review
