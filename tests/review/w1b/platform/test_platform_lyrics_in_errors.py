"""R-PLATFORM (W1b) finding: runtime error messages echo lyric text (NF5).

The runtime validates every JSON a stage writes (``StageWriter.json/events``) and every published file
(``validate.validate_files`` / ``mvh validate``) with jsonschema and puts the raw jsonschema messages into
StageError / report text. jsonschema messages quote the offending instance (``'<value>' is not of type
'object'``), so a single producer bug in lyrics/meaning (a line emitted as a string, a text value in a number
field) copies lyric text into: the child's ``_mvh/error.json`` -> ``.cache/<stage>/failed.json`` -> the
``[mvh] lyrics: failed - ...`` progress line on stderr -> ``run.json`` warnings -> ``mvh status`` reasons ->
``mvh validate`` stdout. CONTRACT §1 / NF5: lyric text never goes into logs, reports, run.json or error
messages. W2 builders paste exactly these messages into their reports.

Expected: messages name the path and the rule (``lines/0: not of type 'object'``) but never the instance
value, at least for lyric-bearing files (lyrics/*, meaning/*, events/singing.json, lipsync/*).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from mvh.contract.catalog import CONTRACT_VERSION
from mvh.runner.ctx import StageWriter
from mvh.runner.spec import StageError
from mvh.runner.validate import validate_folder

REPO = Path(__file__).resolve().parents[4]
FX = REPO / "tests" / "contract" / "synth"
SECRET = "SYNTHETIC SECRET LYRIC LINE nobody may log"


def _lyrics_doc() -> dict:
    p = FX / "lyrics" / "lyrics.json"
    if not p.is_file():
        pytest.skip("tests/contract/synth fixture not built")
    return json.loads(p.read_text(encoding="utf-8"))


def test_stage_writer_error_does_not_quote_lyrics(tmp_path):
    from mvh.stages.lyrics import STAGE

    job = {
        "stage": "lyrics",
        "stage_version": STAGE.version,
        "contract_version": CONTRACT_VERSION,
        "key": "k",
        "params": {},
        "timebase": None,
    }
    w = StageWriter(STAGE, tmp_path, job)
    doc = _lyrics_doc()
    doc["lines"][0] = SECRET  # a producer bug: a line written as its text
    with pytest.raises(StageError) as ei:
        w.json("lyrics/lyrics.json", doc)
    assert SECRET not in str(ei.value), f"StageError message carries lyric text: {str(ei.value)[:200]}"


def test_mvh_validate_does_not_print_lyrics(tmp_path):
    _lyrics_doc()
    song = tmp_path / "song"
    shutil.copytree(FX, song, ignore=shutil.ignore_patterns("_intermediate", "_truth"))
    doc = json.loads((song / "lyrics" / "lyrics.json").read_text(encoding="utf-8"))
    doc["lines"][0]["t"] = SECRET  # text in a number field
    (song / "lyrics" / "lyrics.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    rep = validate_folder(song)
    assert not rep.ok
    leaked = [e for e in rep.errors + rep.warnings if SECRET in e]
    assert leaked == [], f"mvh validate output carries lyric text: {leaked[0][:200]}"
