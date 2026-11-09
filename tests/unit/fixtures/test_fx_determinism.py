"""Regeneration is deterministic: a fresh build into tmp_path is byte-identical to the committed .done.json hashes."""

import json

import pytest

pytestmark = pytest.mark.timeout(900)


def test_rebuild_is_byte_identical(synth, tmp_path):
    from tests.synth.build import build_synth

    ref = json.loads((synth / ".done.json").read_text(encoding="utf-8"))
    done = build_synth(tmp_path / "synth", log=lambda *a: None)
    diff = sorted(
        k for k in set(ref["files"]) | set(done["files"]) if ref["files"].get(k) != done["files"].get(k)
    )
    assert not diff, diff[:20]


def test_tts_assets_cover_every_sung_word():
    from tests.synth import tts
    from tests.synth.song import score as S

    for line in S.LINES:
        for w in line.words:
            voices = {S.VOICE_TTS[line.voice]} | ({"zira"} if line.duet else set())
            for v in voices:
                assert (tts.ASSET_DIR / v / f"{w.text.lower()}.npy").exists(), (v, w.text)
