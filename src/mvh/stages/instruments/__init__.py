# ruff: noqa: E501  (long catalogue tables / docstrings)
"""instruments stage (contract v1, owner M3b).

What it does (PLAN §5 instruments, docs/SPIKE.md):
1. CED-base (AudioSet tagger, ONNX; its output is already a probability) on 4 s windows centred on every second of the
   mix and of every separated stem (vocals, lead_vocals, backing_vocals, drums, bass, guitar, piano, other).
2. Each instrument slug of ``vocab.VOCAB`` (about 28: voice, drums, bass, guitar and its sub-types, piano, organ, synth,
   strings, brass, ...) gets a 1 Hz probability ``inst.<slug>`` that FUSES the tagger (max over the mix and the slug's
   stems) with the activity of the stem the separator dedicates to it (``fuse.fuse``). A vocals stem alone is weak
   evidence for ``voice`` (on MEGAFAUNA it carries synth leads), so voice needs the tagger.
3. Segments (``events/instruments.json``) come from hysteresis on those curves (on 0.5 / off 0.35, >= 2 s, gaps <= 2 s
   bridged), with edges snapped to the anchor stem's 100 Hz activity; ``evidence`` = stem | tagger | both.
4. CLAP (relative curves only, never a top-1 label): ``inst.synth_pad|synth_lead|synth_arp|synth_bass`` split the synth
   presence by CLAP prompt similarity, and every user term in ``params.vocabulary`` gets ``inst.term_<slug>`` (cosine
   above the neutral-prompt baseline, scaled; relative).
5. Vocal style (singing / speech / rap) from CED on lead_vocals plus the hip-hop context of the mix
   (``vstyle.*`` = voice probability x style share; ``events/vocal_style.json``; ``meta/instruments.json.vocal_style``).
"""

from __future__ import annotations

import re

import numpy as np

from mvh.runner.spec import StageResult, StageSpec, catalog_outputs

STAGE = StageSpec(
    "instruments",
    ('ingest', 'separate_fast', 'separate_hq', 'stem_activity'),
    "main",
    "1.0.0",
    override_keys=(),
    outputs=catalog_outputs("instruments"),
    params={'window_s': 4.0, 'hop_s': 1.0, 'vocabulary': [], 'clap_window_s': 10.0, 'clap_step_s': 2.0,
            'seg_on': 0.5, 'seg_off': 0.35, 'seg_min_s': 2.0, 'seg_max_gap_s': 2.0, 'clap': True},
    models=("ced_base_onnx", "clap_larger_music_speech_onnx", "swift_f0_onnx"),
    module="M3b",
    description='CED (4 s / 1 s hop) on mix and stems + CLAP zero-shot, fused with stem activity; vocal style.',
)

CED_STEMS = ("vocals", "lead_vocals", "backing_vocals", "drums", "bass", "guitar", "piano", "other")
STYLES = ("singing", "speech", "rap")


def _slug(term: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", term.lower()).strip("_")[:40] or "term"


def run(ctx) -> StageResult:
    from . import fuse as F
    from .ced import CedTagger, n_frames_1hz
    from .vocab import CLAP_NEUTRAL, SYNTH_SUBTYPES, VOCAB

    prm = ctx.params
    warnings: list[str] = []
    notes: list[str] = []
    mix_full = ctx.audio("mix")
    n_samples, sr = int(mix_full.samples.shape[1]), int(mix_full.sr)
    del mix_full
    duration = n_samples / sr
    n = n_frames_1hz(n_samples, sr)
    win = float(prm.get("window_s", 4.0))

    # ---------------------------------------------------------------- CED on mix + stems
    tagger = CedTagger(dict(ctx.model("ced_base_onnx").files), threads=ctx.threads)
    ced: dict[str, np.ndarray] = {"mix": tagger.frames(ctx.audio("mix", sr=16000, mono=True).samples[0], n, win)}
    act100: dict[str, np.ndarray | None] = {}
    for s in CED_STEMS:
        try:
            y = ctx.audio(s, sr=16000, mono=True).samples[0]
        except Exception as e:  # noqa: BLE001
            warnings.append(f"stem {s} unavailable ({type(e).__name__})")
            continue
        ced[s] = tagger.frames(y, n, win)
        try:
            act100[s] = np.asarray(ctx.curve(f"stem.{s}.active").values)
        except Exception:  # noqa: BLE001
            act100[s] = None
    act1 = {s: F.window_activity(a, n, win) for s, a in act100.items()}

    # ---------------------------------------------------------------- fused curves + segments
    curves: dict[str, np.ndarray] = {}
    meta: dict[str, dict] = {}
    evid: dict[str, F.Evidence] = {}
    items: list[dict] = []
    on, off = float(prm.get("seg_on", F.ON)), float(prm.get("seg_off", F.OFF))
    min_s, gap_s = float(prm.get("seg_min_s", F.MIN_SEG_S)), float(prm.get("seg_max_gap_s", F.MAX_GAP_S))
    for inst in VOCAB:
        e_tag, src_idx, sources = F.tag_evidence(inst, ced, tagger.idx(inst.labels))
        e_stem = act1.get(inst.anchor) if inst.anchor else None
        parent = curves.get(f"inst.{inst.parent}") if inst.parent else None
        p = F.fuse(inst, e_tag, e_stem, parent)
        curves[f"inst.{inst.slug}"] = p
        evid[inst.slug] = F.Evidence(p, e_tag, e_stem if e_stem is not None else np.zeros(n, np.float32), src_idx, sources)
        for a, b in F.segments_1hz(p, duration, on, off, min_s, gap_s):
            t0, t1 = F.frames_to_span(a, b, duration)
            es = float(np.mean(e_stem[a:b + 1])) if e_stem is not None else 0.0
            et = float(np.mean(e_tag[a:b + 1]))
            if e_stem is not None and es >= 0.5:
                evidence = "both" if et >= 0.5 else "stem"
                stem = inst.anchor
                t0, t1 = F.snap_to_activity(t0, t1, act100.get(inst.anchor))
            else:
                evidence = "tagger"
                srcs = [sources[k] for k in src_idx[a:b + 1]]
                stem_srcs = [x for x in srcs if x != "mix"]
                stem = max(set(stem_srcs), key=stem_srcs.count) if len(stem_srcs) * 2 > len(srcs) else None
            items.append({"t": round(t0, 3), "d": round(max(t1 - t0, 0.01), 3), "instrument": inst.slug,
                          "conf": round(float(np.mean(p[a:b + 1])), 4), "evidence": evidence, "stem": stem})

    # QA: a vocals stem that is active without vocal tags (synth leads in the vocal stem, docs/SPIKE.md)
    v = evid["voice"]
    stem_only = float(np.sum((v.stem >= 0.5) & (v.tag < 0.3)))
    if stem_only >= 8:
        warnings.append(f"vocals stem active for about {stem_only:.0f} s without vocal tags (non-vocal content in the vocal stem); not counted as voice")
        notes.append(f"qa:vocals_stem_non_vocal_s={stem_only:.0f}")

    # ---------------------------------------------------------------- CLAP relative curves
    clap_used = False
    terms = [str(t) for t in (prm.get("vocabulary") or []) if str(t).strip()]
    if prm.get("clap", True):
        try:
            from .clap import Clap

            clap = Clap(dict(ctx.model("clap_larger_music_speech_onnx").files), threads=ctx.threads)
            cw, cs = float(prm.get("clap_window_s", 10.0)), float(prm.get("clap_step_s", 2.0))
            emb = {"mix": clap.audio_grid(ctx.audio("mix", sr=48000, mono=True).samples[0], n, cw, cs)}
            if "other" in ced and float(np.max(act1.get("other", np.zeros(1)), initial=0.0)) > 0:
                emb["other"] = clap.audio_grid(ctx.audio("other", sr=48000, mono=True).samples[0], n, cw, cs)
            neutral = clap.text(CLAP_NEUTRAL)
            sub_names = list(SYNTH_SUBTYPES)
            sub = clap.text([SYNTH_SUBTYPES[k] for k in sub_names])
            E = emb.get("other", emb["mix"])
            sims = E @ sub.T  # [n, k]
            z = (sims - sims.mean(axis=1, keepdims=True)) / 0.01
            share = np.exp(z - z.max(axis=1, keepdims=True))
            share /= share.sum(axis=1, keepdims=True)
            synth = curves["inst.synth"].astype(np.float64)
            for j, k in enumerate(sub_names):
                curves[f"inst.{k}"] = np.clip(synth * share[:, j], 0, 1).astype(np.float32)
                meta[f"inst.{k}"] = {"description": f"RELATIVE (CLAP): share of inst.synth attributed to '{SYNTH_SUBTYPES[k]}'; not a calibrated probability",
                                     "norm": {"method": "model"}}
            if terms:
                te = clap.text(terms)
                for term, vec in zip(terms, te):
                    zz = np.max(np.stack([(Em @ vec) - (Em @ neutral.T).mean(axis=1) for Em in emb.values()]), axis=0)
                    cid = f"inst.term_{_slug(term)}"
                    curves[cid] = np.clip(zz / 0.1, 0, 1).astype(np.float32)
                    meta[cid] = {"description": f"RELATIVE (CLAP): user term '{term[:60]}' vs neutral prompts; not a calibrated probability"}
            clap_used = True
        except Exception as e:  # noqa: BLE001
            warnings.append(f"CLAP failed ({type(e).__name__}: {str(e)[:120]}); sub-type and user-term curves skipped")
    for k in SYNTH_SUBTYPES:
        curves.setdefault(f"inst.{k}", np.zeros(n, np.float32))

    # ---------------------------------------------------------------- vocal style
    lead = ced.get("lead_vocals", ced.get("vocals"))
    if lead is not None and "vocals" in ced:  # windows where the karaoke split left the lead stem silent: use vocals
        lead = np.where(lead.max(axis=1, keepdims=True) > 0, lead, ced["vocals"])
    voice_p = curves["inst.voice"].astype(np.float64)
    sustain = vsec = None
    try:
        from swift_f0 import SwiftF0

        lead_name = "lead_vocals" if "lead_vocals" in ced else "vocals"
        y = ctx.audio(lead_name, sr=16000, mono=True).samples[0]
        r = SwiftF0(threads=ctx.threads).detect(y, 16000, fmin=65.0, fmax=1400.0)
        hz = np.asarray(r.pitch_hz, np.float64)
        ok = (np.asarray(r.confidence) >= 0.9) & (hz > 0)
        midi = np.where(ok, 69 + 12 * np.log2(np.maximum(hz, 1e-6) / 440.0), np.nan)
        sustain, vsec = F.pitch_sustain(midi, ok, n, win)
        notes.append("vocal style uses SwiftF0 pitch sustain on the lead stem (style only, never presence)")
    except Exception as e:  # noqa: BLE001
        warnings.append(f"SwiftF0 sustain feature unavailable ({type(e).__name__}); style from CED only")
    if lead is not None:
        shares = F.vocal_style_shares(lead, ced["mix"], tagger.index, sustain, vsec)
    else:
        shares = np.zeros((n, 3))
    for j, s in enumerate(STYLES):
        curves[f"vstyle.{s}"] = np.clip(voice_p * shares[:, j], 0, 1).astype(np.float32)
    style_items = []
    lab = np.where((voice_p >= off) & (shares.sum(axis=1) > 0), shares.argmax(axis=1), -1)
    lab = F.smooth_labels(lab, 5)
    for a, b in F.segments_1hz(curves["inst.voice"], duration, on, off, min_s, gap_s):
        i = a
        while i <= b:
            if lab[i] < 0:
                i += 1
                continue
            j = i
            while j + 1 <= b and lab[j + 1] == lab[i]:
                j += 1
            t0, t1 = F.frames_to_span(i, j, duration)
            style_items.append({"t": round(t0, 3), "d": round(max(t1 - t0, 0.01), 3), "style": STYLES[int(lab[i])],
                                "conf": round(float(np.mean(shares[i:j + 1, int(lab[i])])), 4)})
            i = j + 1
    secs = np.array([sum(it["d"] for it in style_items if it["style"] == st) for st in STYLES], np.float64)
    if secs.sum() > 0:
        sh = secs / secs.sum()  # shares = time shares of the vocal_style segments (consistent with the events)
        dominant = STYLES[int(np.argmax(sh))]
    else:
        sh, dominant = np.zeros(3), "none"

    # ---------------------------------------------------------------- write
    ctx.writer.curves("instruments_1hz", curves, meta=meta)
    ctx.writer.events("instruments", sorted(items, key=lambda it: (it["t"], it["instrument"])))
    ctx.writer.events("vocal_style", style_items)
    summary = []
    for inst in VOCAB:
        segs = [it for it in items if it["instrument"] == inst.slug]
        if not segs:
            continue
        cov = sum(it["d"] for it in segs) / max(duration, 1e-9)
        summary.append({"instrument": inst.slug, "coverage": round(min(cov, 1.0), 4),
                        "mean_conf": round(float(np.mean([it["conf"] for it in segs])), 4)})
    summary.sort(key=lambda r: (-r["coverage"], r["instrument"]))
    m = ced["mix"].mean(axis=0)
    top = [{"label": tagger.labels[i], "p": round(float(m[i]), 4)} for i in np.argsort(-m, kind="stable")[:10]]
    vocab_list = [i.slug for i in VOCAB] + list(SYNTH_SUBTYPES) + [f"term_{_slug(t)}" for t in terms if clap_used]
    ctx.writer.json("meta/instruments.json", {
        "summary": summary, "vocabulary": vocab_list,
        "vocal_style": {"dominant": dominant, "shares": {s: round(float(sh[j]), 4) for j, s in enumerate(STYLES)}},
        "top_tags": top,
    })
    import onnxruntime as ort

    notes += [
        "CED-base ONNX output used as probability (no sigmoid); 4 s windows centred on every second",
        "inst.<slug> fuses tagger evidence (max over mix and stems) with anchor-stem activity (see docs/contract/decisions/M3b.md)",
        "CLAP curves are relative (never top-1 labels)",
        f"CED sources: {', '.join(sorted(ced))}",
    ]
    present = [r["instrument"] for r in summary[:8]]
    return StageResult(
        status="ok" if clap_used or not prm.get("clap", True) else "degraded",
        summary={"instruments": present, "vocal_style": dominant, "n_segments": len(items)},
        warnings=warnings,
        fallbacks=[] if clap_used or not prm.get("clap", True) else ["instruments:no_clap"],
        provenance={"tools": [{"name": "onnxruntime", "version": ort.__version__}], "notes": notes},
        confidence=round(float(np.mean([r["mean_conf"] for r in summary])) if summary else 0.0, 4),
    )

