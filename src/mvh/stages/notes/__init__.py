"""notes stage (contract v1, owner M3b).

What it does (PLAN §5 notes, docs/SPIKE.md):
- bass, guitar, other: basic-pitch (ONNX, arrays in; ``bp.py``) with a preset per source (bass is monophonic and limited to
  27-420 Hz), note onsets snapped to the stem's own audio onsets, re-triggered fragments merged, then masked by the stem's
  activity (``stem.<src>.active``).
- piano: piano_transcription_inference (ByteDance CRNN) ONLY when the piano stem is active (>= 10 % of the song) AND CED
  reports piano on it (on a silent stem the model invents notes: 378 spurious notes on MEGAFAUNA in W0). An active piano
  stem without CED piano evidence (synth keys, bleed) is transcribed by basic-pitch instead (fallback ``piano:basic_pitch``).
  Human correction: ``--param notes.piano_mode="crnn"|"basic_pitch"|"off"`` replaces the gate (default ``"auto"``).
- Velocities come from the stem level at each onset (0..1, per-source normalised); ``conf`` is the model's evidence.
- notes/notes.mid has one track per source (bass, piano, guitar, other) and a tempo map from the beat grid (``midi.py``);
  notes/<src>.mid per source with notes; notes/notes.json has the statistics. Vocal notes belong to the vocals stage (D6).
"""

from __future__ import annotations

import numpy as np

from mvh.runner.spec import StageResult, StageSpec, catalog_outputs

STAGE = StageSpec(
    "notes",
    ('separate_hq', 'stem_activity', 'rhythm'),
    "main",
    "1.0.0",
    override_keys=(),
    outputs=catalog_outputs("notes"),
    params={'piano_min_active_s': 1.0, 'piano_ced_mean': 0.05, 'piano_ced_p95': 0.25, 'mask_min_frac': 0.5,
            'snap_onsets': True, 'piano_mode': 'auto'},
    models=("basic_pitch_nmp_onnx", "piano_transcription_crnn", "ced_base_onnx"),
    module="M3b",
    description='basic-pitch per active stem; piano_transcription_inference on piano; MIDI with a tempo map.',
)

SOURCES = ("bass", "piano", "guitar", "other")


def _stem_present(stems_meta: dict, src: str, active: np.ndarray | None) -> tuple[bool, float]:
    m = stems_meta.get(src) or {}
    ratio = float(m.get("active_ratio", float(np.mean(active > 0.5)) if active is not None else 0.0))
    present = bool(m.get("present", ratio > 0.01))
    return present and ratio > 0.0, ratio


def _items(notes, y: np.ndarray, sr: int, conf: np.ndarray | None = None, vel: np.ndarray | None = None) -> list[dict]:
    from . import post

    if not notes:
        return []
    amp = np.array([n[3] for n in notes], np.float64)
    if vel is None:
        vel = post.velocities(post.onset_levels_db(notes, y, sr), amp)
    if conf is None:
        conf = np.clip(amp, 0.0, 1.0)
    out = []
    for (t0, t1, m, _a), v, c in zip(notes, vel, conf):
        out.append({"t": round(float(t0), 4), "d": round(max(float(t1 - t0), 0.01), 4), "midi": int(m),
                    "name": post.note_name(int(m)), "vel": round(float(v), 4), "conf": round(float(c), 4)})
    return out


def run(ctx) -> StageResult:
    from . import post
    from .bp import PRESETS, BasicPitch
    from .midi import smf_bytes, tempo_map_from_ctx

    prm = ctx.params
    warnings: list[str] = []
    fallbacks: list[str] = []
    notes_prov: list[str] = []
    mix = ctx.audio("mix")
    n_samples, sr_mix = int(mix.samples.shape[1]), int(mix.sr)
    del mix
    duration = n_samples / sr_mix
    try:
        stems_meta = ctx.upstream("stem_activity").json("meta/stems.json").get("stems", {})
    except Exception:  # noqa: BLE001
        stems_meta = {}
        warnings.append("meta/stems.json unreadable; presence from the activity curves")
    tmap = tempo_map_from_ctx(ctx, duration)
    bp_files = ctx.model("basic_pitch_nmp_onnx").files
    bp = BasicPitch(next(iter(bp_files.values())), threads=ctx.threads)

    results: dict[str, list[dict]] = {}
    methods: dict[str, str] = {}
    for src in SOURCES:
        try:
            active = np.asarray(ctx.curve(f"stem.{src}.active").values)
        except Exception:  # noqa: BLE001
            active = None
        present, ratio = _stem_present(stems_meta, src, active)
        if not present:
            results[src], methods[src] = [], "none (stem inactive)"
            continue
        a22 = ctx.audio(src, sr=22050, mono=True).samples[0]
        if src == "piano":
            # human-correction hook: --param notes.piano_mode="crnn" | "basic_pitch" | "off" (default "auto" = the gate)
            mode = str(prm.get("piano_mode", "auto") or "auto")
            if mode == "off":
                results[src], methods[src] = [], "none (piano_mode=off, set by the user)"
                notes_prov.append("piano gate: piano_mode=off (user)")
                continue
            if mode == "crnn":
                use_pt, why = True, f"stem active {ratio:.3f}; piano_mode=crnn (user) -> run"
            elif mode == "basic_pitch":
                use_pt, why = False, f"stem active {ratio:.3f}; piano_mode=basic_pitch (user)"
            else:
                use_pt, why = _piano_gate(ctx, prm, ratio, active, n_samples, sr_mix)
            notes_prov.append(f"piano gate: {why}")
            if use_pt:
                results[src] = _piano_transcription(ctx, active, prm)
                methods[src] = "piano_transcription_inference (CRNN, note_F1=0.9677)"
                continue
            if mode != "basic_pitch":
                if _active_seconds(ratio, n_samples, sr_mix) < float(prm.get("piano_min_active_s", 1.0)):
                    results[src], methods[src] = [], "none (piano stem active under the floor)"
                    warnings.append(f"piano stem active only {_active_seconds(ratio, n_samples, sr_mix):.2f} s "
                                    f"(< notes.piano_min_active_s): no piano notes written")
                    continue
                fallbacks.append("piano:basic_pitch")
                warnings.append("piano stem active but CED finds no piano: transcribed with basic-pitch (synth keys or bleed)")
        preset = PRESETS[src]
        raw = bp.notes(a22, preset)
        ons = post.audio_onsets(a22, 22050, 600.0 if src == "bass" else None) if prm.get("snap_onsets", True) else None
        ns = post.snap_onsets(raw, ons) if ons is not None else raw
        if preset.mono:
            ns = post.monophonic(ns)
        ns = post.merge_fragments(ns, ons)
        if preset.mono:
            ns = post.monophonic(ns)
        ns = post.mask_by_activity(ns, active, float(prm.get("mask_min_frac", 0.5)))
        results[src] = _items(ns, a22, 22050)
        methods[src] = f"basic-pitch 0.4.0 ICASSP-2022 ONNX, preset {src if src in PRESETS else 'default'}"
        notes_prov.append(f"{src}: {len(raw)} raw -> {len(results[src])} notes after snap/merge/mono/mask")

    sources_meta = {}
    for src in SOURCES:
        items = sorted(results[src], key=lambda it: (it["t"], it["midi"]))
        ctx.writer.events(f"notes.{src}", items)
        midi_rel = None
        if items:
            midi_rel = f"notes/{src}.mid"
            ctx.writer.midi(midi_rel, smf_bytes({src: items}, tmap))
        sources_meta[src] = {"events": f"events/notes.{src}.json", "midi": midi_rel, **post.stats(items, duration)}
    ctx.writer.midi("notes/notes.mid", smf_bytes({s: results[s] for s in SOURCES}, tmap))
    ctx.writer.json("notes/notes.json", {"sources": sources_meta, "tempo_map": tmap.description})
    for src in SOURCES:
        notes_prov.append(f"{src}: {methods.get(src)}")
    counts = {s: sources_meta[s]["count"] for s in SOURCES}
    return StageResult(status="degraded" if fallbacks else "ok", summary={"counts": counts}, warnings=warnings,
                       fallbacks=fallbacks, provenance={"notes": notes_prov})


def _active_seconds(ratio: float, n_samples: int, sr: int) -> float:
    return float(ratio) * float(n_samples) / float(max(sr, 1))


def _piano_gate(ctx, prm, ratio: float, active, n_samples: int, sr: int) -> tuple[bool, str]:
    """Run piano_transcription only when the piano stem is active AND CED reports piano (docs/SPIKE.md)."""
    from mvh.stages.instruments.ced import CedTagger, n_frames_1hz
    from mvh.stages.instruments.fuse import window_activity

    min_s = float(prm.get("piano_min_active_s", 1.0))
    act_s = _active_seconds(ratio, n_samples, sr)
    if act_s < min_s:
        return False, f"stem active {ratio:.3f} ({act_s:.2f} s) < {min_s} s"
    tagger = CedTagger(dict(ctx.model("ced_base_onnx").files), threads=ctx.threads)
    n = n_frames_1hz(n_samples, sr)
    pi = tagger.idx(["Piano"])[0]
    stem_p = tagger.frames(ctx.audio("piano", sr=16000, mono=True).samples[0], n)[:, pi]
    mix_p = tagger.frames(ctx.audio("mix", sr=16000, mono=True).samples[0], n)[:, pi]
    act = window_activity(active, n) >= 0.5
    sel = act if act.any() else np.ones(n, bool)
    p = np.maximum(stem_p[sel], mix_p[sel])
    mean, p95 = float(p.mean()), float(np.percentile(p, 95))
    ok = mean >= float(prm.get("piano_ced_mean", 0.05)) or p95 >= float(prm.get("piano_ced_p95", 0.25))
    return ok, f"stem active {ratio:.3f}; CED piano mean {mean:.3f}, p95 {p95:.3f} over active windows -> {'run' if ok else 'skip'}"


def _piano_transcription(ctx, active, prm) -> list[dict]:
    import torch
    from piano_transcription_inference import PianoTranscription

    from . import post

    ckpt = next(iter(ctx.model("piano_transcription_crnn").files.values()))
    torch.set_num_threads(int(ctx.threads))
    y = ctx.audio("piano", sr=16000, mono=True).samples[0].astype(np.float32)
    pt = PianoTranscription(checkpoint_path=str(ckpt), device=torch.device("cpu"))
    with torch.no_grad():
        res = pt.transcribe(y, None)
    ev = res.get("est_note_events", [])
    ns = [(float(e["onset_time"]), float(e["offset_time"]), int(e["midi_note"]), float(e["velocity"]) / 127.0) for e in ev]
    ns = post.mask_by_activity(sorted(ns), active, float(prm.get("mask_min_frac", 0.5)))
    vel = np.array([n[3] for n in ns]) if ns else None
    conf = np.full(len(ns), 0.85) if ns else None
    return _items(ns, y, 16000, conf=conf, vel=vel)
