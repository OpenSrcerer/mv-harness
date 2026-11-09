"""allin1 stage (contract v1, owner M2): all-in-one-infer ``harmonix-all`` (8 folds) on the separate_fast stems.

Recipe (docs/spike/main.md §2, SPIKE "Tool recipes"): all-in-one-infer 3.1.0 has no ``AllInOneSession``; we call
``allin1_infer.analyze(stems_input=StemsInput(...))`` with the four htdemucs stems written by us as float32 WAVs
into the stage scratch dir (never a user file). Model folds resolve offline through the HF-cache layout that
``mvh models fetch`` hard-links under ``HF_HOME`` (model id ``allin1_harmonix``; its SHA-256s are in the key).

Outputs (cache only, D18), read by rhythm and structure through ``mvh.stages.allin1.read``:

* ``allin1.json`` (``mvh/intermediate/allin1``): beats, downbeats, beat_positions, segments, label order,
  the activation/embedding layouts. Additive keys: ``bpm_from_beats`` (allin1's own ``bpm`` is an integer and can be
  off by 2 BPM, bench-music §2), ``embeddings_layout``, ``model``.
* ``activations.f32``: row-major float32 [frames x 13] at 100 Hz: beat, downbeat, boundary (segment), then the
  10 Harmonix label probabilities (softmax over labels per frame).
* ``embeddings.f32``: row-major float32 [frames x 768] at 10 Hz: the per-stem 24x8 embeddings of bass, drums,
  other, vocals concatenated (in that order) and mean-pooled over 10 frames (decision M2-D3: 4x smaller than the
  100 Hz stem mean and keeps the per-stem information; consumers read ``rate_hz`` and ``dim``).
"""
from __future__ import annotations

import contextlib
import sys

import numpy as np

from mvh.runner.spec import StageError, StageResult, StageSpec, catalog_outputs

STAGE = StageSpec(
    "allin1",
    ('separate_fast',),
    "main",
    "1.2.0",
    override_keys=(),
    outputs=catalog_outputs("allin1"),
    params={'model': 'harmonix-all', 'folds': 8, 'stems': ['bass', 'drums', 'other', 'vocals'],
            'embeddings_rate_hz': 10, 'embeddings_layout': 'stems_concat',
            # W4A-GAIN / W4V-GAIN-REAL (W4-AN-9): the stems are scaled by ONE common gain that puts the canonical mix's
            # integrated loudness (BS.1770) at this fixed level (commercial masters, allin1's training material), so
            # the same song at any master level reaches the model at the same level (a band left real masters at their
            # own level: a -12 dB copy moved MEGAFAUNA's sections). A list [lo, hi] is a band; null = master level
            'level_target_lufs': -10.0, 'level_max_gain_db': 40.0},
    models=("allin1_harmonix",),
    module="M2",
    description="all-in-one-infer harmonix-all (8 folds) on separate_fast stems; schema'd intermediates for rhythm and structure.",
)

HARMONIX = ["start", "end", "intro", "outro", "break", "bridge", "inst", "solo", "verse", "chorus"]
STEMS = ("bass", "drums", "other", "vocals")


def pool_embeddings(emb: np.ndarray, factor: int) -> np.ndarray:
    """[stems, T, 24, 8] (or [stems, T, D]) -> [ceil(T/factor), stems*D] float32, mean over blocks of ``factor`` frames."""
    e = np.asarray(emb, dtype=np.float32)
    if e.ndim == 4:
        e = e.reshape(e.shape[0], e.shape[1], -1)
    if e.ndim == 2:
        e = e[None]
    s, t, d = e.shape
    cat = np.transpose(e, (1, 0, 2)).reshape(t, s * d)
    if factor <= 1:
        return np.ascontiguousarray(cat)
    nb = -(-t // factor)
    pad = nb * factor - t
    if pad:
        cat = np.concatenate([cat, np.repeat(cat[-1:], pad, axis=0)], axis=0)
    return np.ascontiguousarray(cat.reshape(nb, factor, s * d).mean(axis=1, dtype=np.float64).astype(np.float32))


def activation_matrix(acts: dict) -> np.ndarray:
    beat = np.asarray(acts["beat"], np.float32).reshape(-1)
    down = np.asarray(acts["downbeat"], np.float32).reshape(-1)
    seg = np.asarray(acts["segment"], np.float32).reshape(-1)
    lab = np.asarray(acts["label"], np.float32)
    if lab.shape[0] != len(HARMONIX) and lab.shape[-1] == len(HARMONIX):
        lab = lab.T
    t = min(len(beat), len(down), len(seg), lab.shape[1])
    return np.ascontiguousarray(np.column_stack([beat[:t], down[:t], seg[:t], lab[:, :t].T]).astype("<f4"))


def bpm_from_beats(beats) -> float | None:
    b = np.asarray(beats, float)
    if len(b) < 3:
        return None
    ibi = np.diff(b)
    ibi = ibi[ibi > 0]
    return round(float(60.0 / np.median(ibi)), 3) if len(ibi) else None


def level_gain_db(stems: dict[str, np.ndarray], sr: int, band_lufs, max_gain_db: float = 40.0) -> tuple[float, float]:
    """(gain dB, measured LUFS): one common gain that puts the sum of the stems inside ``band_lufs`` = [lo, hi] (W4A-GAIN);
    a single number is a fixed target.

    allin1's front end (log(1 + |STFT|) of each stem) is level dependent: the synthetic song 12 dB quieter (-32 LUFS) was
    labelled 'intro' throughout. The htdemucs stems scale with the master level, so the analysis copy is brought into the
    level range of commercial masters (its training material); the timing is untouched (a pure gain). Inside the band
    nothing changes (the four real songs, -6.1 .. -11.0 LUFS). The stems are written as float32, so a positive gain cannot
    clip. Silence (below the absolute gate) is left as it is."""
    from mvh.stages.loudness.r128 import LUFS_FLOOR, integrated

    if band_lufs is None:
        return 0.0, float("nan")
    if isinstance(band_lufs, (int, float)):
        lo = hi = float(band_lufs)
    else:
        lo, hi = float(min(band_lufs)), float(max(band_lufs))
    arrs = [np.asarray(v, np.float64) for v in stems.values()]
    arrs = [a if a.ndim == 2 else a.reshape(1, -1) for a in arrs]
    n = min(a.shape[1] for a in arrs)
    ch = max(a.shape[0] for a in arrs)
    tot = np.zeros((ch, n))
    for a in arrs:
        tot += a[:, :n] if a.shape[0] == ch else np.repeat(a[:1, :n], ch, axis=0)
    lv = integrated(tot, sr)
    if lv <= LUFS_FLOOR + 1e-6:
        return 0.0, lv
    return float(np.clip(float(np.clip(lv, lo, hi)) - lv, -abs(max_gain_db), abs(max_gain_db))), lv


def run(ctx) -> StageResult:
    from mvh.io.wav import write_wav

    p = ctx.params
    up = ctx.upstream("separate_fast")
    sep = up.json("fast/separation.json")
    have = set((sep.get("stems") or {}).keys())
    missing = [s for s in STEMS if s not in have and not up.exists(f"fast/{s}.wav")]
    if missing:
        raise StageError(f"allin1 needs the htdemucs stems {list(STEMS)}; separate_fast lacks {missing}")
    stem_dir = ctx.scratch / "stems"
    stem_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    sr = None
    raw: dict[str, np.ndarray] = {}
    for s in STEMS:
        a = ctx.audio(f"fast:{s}")
        sr = a.sr
        raw[s] = np.asarray(a.samples, np.float32)
    tgt = p.get("level_target_lufs")
    if isinstance(tgt, (list, tuple)):
        gain_db, level_lufs = level_gain_db(raw, int(sr), tgt, float(p.get("level_max_gain_db", 40.0)))
    else:
        from mvh.stages.loudness.level import gain_db_for

        mix = ctx.audio("mix")
        gain_db, level_lufs = gain_db_for(np.asarray(mix.samples), int(mix.sr), tgt, float(p.get("level_max_gain_db", 40.0)))
        del mix
    g = np.float32(10.0 ** (gain_db / 20.0))
    for s in STEMS:
        paths[s] = write_wav(stem_dir / f"{s}.wav", raw[s] * g if gain_db else raw[s], int(sr))
    del raw
    handle = ctx.model("allin1_harmonix")  # verifies the fold files exist (sizes) and records their SHA-256s

    import torch

    torch.set_num_threads(int(ctx.threads))
    import allin1_infer
    from allin1_infer import analyze
    from allin1_infer.stems_input import StemsInput

    work = ctx.scratch / "allin1"
    # allin1 prints progress on stdout; keep the child's stdout clean
    with contextlib.redirect_stdout(sys.stderr):
        r = analyze(
            stems_input=StemsInput(bass=paths["bass"], drums=paths["drums"], other=paths["other"],
                                   vocals=paths["vocals"], identifier="song"),
            model=str(p["model"]), device="cpu", include_activations=True, include_embeddings=True,
            demix_dir=work / "demix", spec_dir=work / "spec", multiprocess=False,
        )
    r = r[0] if isinstance(r, list) else r
    acts = {k: np.asarray(v, np.float32) for k, v in (r.activations or {}).items()}
    if not acts:
        raise StageError("allin1 returned no activations")
    mat = activation_matrix(acts)
    fps = float(r.activation_fps or 100.0)
    ctx.writer.matrix("activations", mat, meta={"rate_hz": fps, "columns": ["beat", "downbeat", "boundary", *HARMONIX]})
    emb_doc = None
    if r.embeddings is not None:
        factor = max(1, int(round(fps / float(p.get("embeddings_rate_hz", 10)))))
        emb = pool_embeddings(np.asarray(r.embeddings), factor)
        ctx.writer.matrix("embeddings", emb, meta={"rate_hz": fps / factor, "layout": "stems_concat"})
        emb_doc = {"file": "embeddings.f32", "rate_hz": fps / factor, "dim": int(emb.shape[1]), "frames": int(emb.shape[0])}
    beats = [round(float(b), 4) for b in r.beats]
    downbeats = [round(float(b), 4) for b in r.downbeats]
    segs = [{"start": round(float(s.start), 4), "end": round(float(s.end), 4), "label": str(s.label)} for s in r.segments]
    doc = {
        "bpm": float(r.bpm) if r.bpm is not None else None,
        "bpm_from_beats": bpm_from_beats(beats),
        "beats": beats,
        "downbeats": downbeats,
        "beat_positions": [int(b) for b in r.beat_positions],
        "segments": segs,
        "labels": list(HARMONIX),
        "activations": {"file": "activations.f32", "rate_hz": fps, "columns": ["beat", "downbeat", "boundary", *HARMONIX],
                        "frames": int(mat.shape[0])},
        "embeddings": emb_doc,
        "embeddings_layout": "stems_concat:" + ",".join(STEMS) if emb_doc else None,
        "model": {"name": str(p["model"]), "folds": int(p.get("folds", 8)), "package": "all-in-one-infer",
                  "version": getattr(allin1_infer, "__version__", "3.1.0"), "stems_sr": int(sr or 44100)},
        # additive (W4A-GAIN, W4-AN-9): the analysis-copy level normalisation (measured on the canonical mix, or on
        # the stem sum when a band is configured)
        "level": {"measured_lufs": None if not np.isfinite(level_lufs) else round(float(level_lufs), 2),
                  "measured_on": "stems" if isinstance(tgt, (list, tuple)) else "mix",
                  "target_lufs": tgt, "gain_db": round(float(gain_db), 2)},
    }
    ctx.writer.json("allin1.json", doc)
    labels_used = sorted({s["label"] for s in segs})
    summary = {"bpm": doc["bpm"], "bpm_from_beats": doc["bpm_from_beats"], "n_beats": len(beats), "gain_db": doc["level"]["gain_db"],
               "n_downbeats": len(downbeats), "n_segments": len(segs), "labels": labels_used}
    return StageResult(
        status="ok", summary=summary,
        provenance={"models": [{"id": handle.id, "licence": handle.licence, "revision": handle.revision}],
                    "tools": [{"name": "all-in-one-infer", "version": doc["model"]["version"]}],
                    "notes": ["harmonix-all 8-fold ensemble on separate_fast (htdemucs) stems written as float32 WAVs",
                              "embeddings: stems concatenated (bass, drums, other, vocals), mean-pooled to "
                              f"{doc['embeddings']['rate_hz'] if emb_doc else 'n/a'} Hz"]},
    )
