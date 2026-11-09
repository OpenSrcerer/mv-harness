"""R-PLATFORM round 4 (W3 verify) for M6a: the viewer's voice -> character edit, as the voices stage reads it back (seam S10).

The viewer writes ``- Vn = Cm Name`` lines into the managed block of meaning/intent.md (decision V7). D51 says the highest
voice mapped there is a FLOOR for the voice count. The voices stage turns it into an EXACT count (``n_source=intent``,
``K.agglo(E, k)``), so mapping the first few voices of a song in the viewer makes the next run drop the others.

Fast and synthetic: a fake ctx with four clearly separated singers (10 lines each) and a fake embedder that reads the singer
from the samples. No model, no real song.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from mvh.stages.viewer import intent_block as IB

SR = 16000
DIM = 8


class _FakeEmb:
    name = "fake"
    dim = DIM

    def __init__(self, seed: int = 7):
        self.rng = np.random.default_rng(seed)
        self.base = np.eye(DIM)

    def one(self, x: np.ndarray) -> np.ndarray:
        c = int(round(float(np.median(x)))) - 1
        v = self.base[c] + 0.05 * self.rng.standard_normal(DIM)
        return v / np.linalg.norm(v)

    def many(self, xs):
        return np.stack([self.one(x) for x in xs])


class _Up:
    def __init__(self, docs: dict):
        self.docs = docs

    def json(self, rel: str):
        return self.docs[rel]

    def exists(self, rel: str) -> bool:
        return rel in self.docs


class _Writer:
    def __init__(self):
        self.out: dict = {}

    def events(self, name, rows, fields=None):
        self.out[f"events/{name}"] = rows

    def json(self, rel, doc):
        self.out[rel] = doc


def _song(n_per_voice: int = 10, n_voices: int = 4):
    """Lines L001.. sung in turn by four singers (round robin), 3 words over 2.4 s each, 3 s apart."""
    lines, words = [], []
    n = n_per_voice * n_voices
    dur = 3.0 * n + 2.0
    lead = np.zeros(int(dur * SR), dtype=np.float32)
    for i in range(n):
        lid, t = f"L{i + 1:03d}", 1.0 + 3.0 * i
        singer = i % n_voices + 1
        lead[int(t * SR):int((t + 2.4) * SR)] = singer
        lines.append({"id": lid, "t": t, "d": 2.4, "n_words": 3, "speaker_hint": None})
        for j in range(3):
            words.append({"id": f"{lid}.{j + 1:02d}", "line_id": lid, "t": t + 0.8 * j, "d": 0.8})
    return {"lines": lines, "words": words, "grade": "B"}, lead


def _run_voices(tmp_path: Path, intent_text: str | None, monkeypatch) -> dict:
    from mvh.stages.lyrics import vocal_env
    from mvh.stages.voices import STAGE, core, embed

    lyr, lead = _song()
    monkeypatch.setattr(embed, "load_embedder", lambda ctx, name: (_FakeEmb(), ["fake"], []))
    monkeypatch.setattr(vocal_env, "pick_vocal_stem", lambda ctx, sr: ("lead_vocals", lead, sr))
    ip = None
    if intent_text is not None:
        ip = tmp_path / "intent.md"
        ip.write_text(intent_text, encoding="utf-8", newline="\n")
    ups = {"lyrics": _Up({"lyrics/lyrics.json": lyr}), "separate_hq": _Up({"meta/separation.json": {"lead_backing_split": True}})}
    w = _Writer()
    ctx = SimpleNamespace(
        params=STAGE.resolved_params("max", {}), upstream=lambda name: ups[name], external=lambda name: ip,
        overrides={}, writer=w, audio=lambda *a, **k: SimpleNamespace(samples=np.zeros((1, len(lead)), dtype=np.float32), sr=SR),
        log=SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None, debug=lambda *a, **k: None),
    )
    core.run(ctx)
    return w.out["meta/voices.json"]


def _viewer_saved(voices: dict) -> str:
    """meaning/intent.md exactly as `mvh view` writes it after the user maps voices in the Voices panel."""
    st = IB.merge(IB.empty(), {"voices": voices})
    return IB.apply("", st)  # the function server.write_intent uses


def test_baseline_the_fake_song_has_four_voices(tmp_path, monkeypatch):
    doc = _run_voices(tmp_path, None, monkeypatch)
    assert doc["n_voices"] == 4, doc["k_selection"]


@pytest.mark.parametrize("mapped", [("V1",), ("V1", "V2"), ("V2", "V3")])
def test_mapping_some_voices_in_the_viewer_does_not_drop_the_others(tmp_path, monkeypatch, mapped):
    """F-R4-VOICE-FLOOR: the user maps the first voices of a 4-voice song to characters in the viewer (the rest are
    left for later). On the next run the voices stage must still find 4 voices (D51: the mapped voices are a floor).
    It clusters into exactly the highest mapped voice and folds the other singers' lines into those voices."""
    text = _viewer_saved({v: {"character_id": f"C{i + 1}", "name": f"Char {i + 1}"} for i, v in enumerate(mapped)})
    doc = _run_voices(tmp_path, text, monkeypatch)
    assert doc["n_voices"] == 4, (
        f"mapping {list(mapped)} in the viewer made the voices stage cluster into {doc['n_voices']} voices "
        f"(n_source={doc['n_source']}, k_selection={doc['k_selection']}); D51 promises a floor, not an exact count")
