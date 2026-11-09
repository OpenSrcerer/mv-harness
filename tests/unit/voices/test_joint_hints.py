"""r4-m2 / M5-D55: a joint speaker label ('Ann & Bob') is not a voice of its own. Fake ctx and a fake embedder
(2 orthogonal timbres), so the test is fast and needs no model. Synthetic text only."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from mvh.runner.spec import StageError
from mvh.stages.voices import core as VC


class _Emb:
    name = "fake"
    dim = 4

    def many(self, xs):
        return np.stack([self.one(x) for x in xs])

    def one(self, x):
        # the timbre is encoded in the sign of the first sample of the span: + -> Ann, - -> Bob
        v = np.array([1.0, 0.05, 0.0, 0.0]) if float(x[0]) > 0 else np.array([0.05, 1.0, 0.0, 0.0])
        return v / np.linalg.norm(v)


class _Up:
    def __init__(self, docs):
        self.docs = docs

    def json(self, rel):
        return self.docs[rel]

    def exists(self, rel):
        return rel in self.docs


class _Writer:
    def __init__(self):
        self.out = {}

    def events(self, name, items, fields=None):
        self.out[name] = items

    def json(self, rel, doc):
        self.out[rel] = doc


def _lyrics(plan):
    lines, words, t = [], [], 1.0
    for i, hint in enumerate(plan):
        lid = f"L{i + 1:03d}"
        lines.append({"id": lid, "n_words": 3, "speaker_hint": hint})
        for j in range(3):
            words.append({"id": f"W{len(words) + 1:04d}", "line_id": lid, "t": t + 0.6 * j, "d": 0.5})
        t += 3.0
    return {"lines": lines, "words": words, "grade": "B"}, t


def test_joint_label_is_not_a_third_voice(monkeypatch):
    plan = ["Ann", "Bob", "Ann & Bob", "Ann", "Bob", "Both"]
    lyr, dur = _lyrics(plan)
    sr = 16000
    lead = np.zeros(int((dur + 1) * sr), np.float32)
    for i, hint in enumerate(plan):
        a = int((1.0 + 3.0 * i) * sr)
        lead[a:a + int(1.7 * sr)] = 0.5 if hint in ("Ann", "Ann & Bob") else -0.5
    ctx = SimpleNamespace(
        params={"min_item_s": 1.0, "backing_spans": False},
        upstream=lambda name: _Up({"lyrics/lyrics.json": lyr} if name == "lyrics" else {}),
        external=lambda name: None,
        overrides={},
        writer=_Writer(),
    )

    def _audio(name, sr=16000, mono=True):
        raise StageError("no stem")

    ctx.audio = _audio
    monkeypatch.setattr("mvh.stages.lyrics.vocal_env.pick_vocal_stem", lambda c, s: ("lead_vocals", lead, sr))
    monkeypatch.setattr("mvh.stages.voices.embed.load_embedder", lambda c, prefer="ecapa": (_Emb(), [], []))
    res = VC.run(ctx)
    meta = ctx.writer.out["meta/voices.json"]
    assert meta["n_source"] == "hints" and meta["n_voices"] == 2, (meta["n_source"], meta["n_voices"], res.summary)
    spans = {s["line_id"]: s for s in ctx.writer.out["voice_spans"] if s["role"] == "lead"}
    assert spans["L003"]["voice_id"] == spans["L001"]["voice_id"]          # joint line -> nearest of its singers
    assert spans["L003"]["source"] == "embedding" and spans["L001"]["source"] == "hint"
    assert spans["L006"]["voice_id"] == spans["L002"]["voice_id"]          # 'Both' -> nearest centroid
    assert sorted(v["hint"] for v in meta["voices"]) == ["Ann", "Bob"]
