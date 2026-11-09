"""R-WORDS M5 round 5 (major): voices crashes with ValueError when a speaker hint occurs only on short lines.

``voices.core.run`` builds ``hints`` from the EMBEDDED items only (lines >= ``min_item_s``), then labels the short
items with ``hints.index(it["solo"])`` (and ``hints.index(pt)`` for joint ones). A speaker who only has short lines
(a battle announcer's 'Begin!', a one-word shout by a featured singer) is not in ``hints`` -> ``ValueError`` and the
whole voices stage fails, which takes lipsync's per-voice tracks with it. The rap-battle stress case (3 rappers plus
an announcer) is exactly this shape. Fake ctx and a fake embedder (as in tests/unit/voices/test_joint_hints.py);
synthetic text only.
"""
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


def _run(plan, monkeypatch):
    """plan: [(hint, n_words, word_d)]; returns (result, writer.out)."""
    lines, words, t = [], [], 1.0
    sr = 16000
    spans = []
    for i, (hint, nw, d) in enumerate(plan):
        lid = f"L{i + 1:03d}"
        lines.append({"id": lid, "n_words": nw, "speaker_hint": hint})
        for j in range(nw):
            words.append({"id": f"W{len(words) + 1:04d}", "line_id": lid, "t": t + (d + 0.1) * j, "d": d})
        spans.append((t, hint))
        t += 3.0
    lead = np.zeros(int((t + 1) * sr), np.float32)
    for t0, hint in spans:
        a = int(t0 * sr)
        lead[a:a + int(1.7 * sr)] = -0.5 if hint == "Bob" else 0.5
    lyr = {"lines": lines, "words": words, "grade": "B"}
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
    return res, ctx.writer.out


def test_speaker_with_only_short_lines_does_not_crash_voices(monkeypatch):
    # announcer: one 2-word line of 0.6 s (< min_item_s 1.0); Ann and Bob rap full lines
    plan = [("Announcer", 2, 0.25), ("Ann", 3, 0.5), ("Bob", 3, 0.5), ("Ann", 3, 0.5), ("Bob", 3, 0.5)]
    try:
        res, out = _run(plan, monkeypatch)
    except ValueError as e:
        raise AssertionError(f"voices crashed on a short-only speaker hint: ValueError({e.__class__.__name__})") from None
    spans = {s["line_id"]: s for s in out["voice_spans"] if s["role"] == "lead"}
    assert "L001" in spans, "the announcer line got no voice span"


def test_joint_short_line_with_unseen_singer_does_not_crash(monkeypatch):
    # a short joint shout 'Ann & Cid' where Cid never has an embedded line of his own
    plan = [("Ann", 3, 0.5), ("Bob", 3, 0.5), ("Ann & Cid", 2, 0.25), ("Ann", 3, 0.5), ("Bob", 3, 0.5)]
    try:
        _run(plan, monkeypatch)
    except ValueError:
        raise AssertionError("voices crashed on a short joint line naming a singer with no embedded line") from None


def test_guard_all_long_lines_work(monkeypatch):
    plan = [("Ann", 3, 0.5), ("Bob", 3, 0.5), ("Ann", 3, 0.5), ("Bob", 3, 0.5)]
    _res, out = _run(plan, monkeypatch)
    assert out["meta/voices.json"]["n_voices"] == 2
