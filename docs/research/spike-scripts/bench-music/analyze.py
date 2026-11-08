"""bench-music: cross-tool agreement + timings tables + index.music.json from the raw cache (no inference, no lyrics).

    run: scripts\\run.ps1 python docs\\research\\spike-scripts\\bench-music\\analyze.py
Writes tests/.cache/real/index.music.json and docs/research/spike-scripts/bench-music/analysis.json (numbers only).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[4]
CACHE = REPO / "tests" / ".cache" / "real"
SLUGS = ["megafauna", "versatile", "jeremy", "newton-vs-nye"]
STEPS = ["decode", "demucs", "beat_this", "allin1", "librosa", "spectral_proto", "chords", "key", "notes", "pitch", "instruments", "mood", "madmom_dbn", "piano"]
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT = {"Bb": "A#", "Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#"}


def jl(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def fm(ref, est, w=0.07):
    import mir_eval
    ref, est = np.asarray(ref, float), np.asarray(est, float)
    if len(ref) < 2 or len(est) < 2:
        return None
    return round(float(mir_eval.beat.f_measure(ref, est, f_measure_threshold=w)), 4)


def fm_shift(ref, est, w=0.07):
    """best F over estimate shifted by -2..+2 beats (index shift on the estimate) -> catches phase (offbeat) disagreement."""
    ref, est = np.asarray(ref, float), np.asarray(est, float)
    best = (0, None)
    for k in range(-2, 3):
        e = est[k:] if k >= 0 else est[:k]
        # shift by k beats == compare est[i+k] to ref positions via time shifting est by median IBI*k
        ibi = np.median(np.diff(est))
        f = fm(ref, est + k * ibi, w)
        if f is not None and f > best[0]:
            best = (f, k)
    return best


def key_norm(s):
    """'Bb Major' / 'A# minor' / 'C:maj' -> (pc, 'major'|'minor')"""
    s = s.strip()
    if ":" in s:
        root, q = s.split(":")[0], s.split(":")[1]
        mode = "minor" if q.startswith("min") else "major"
    else:
        root, mode = s.split()[0], s.split()[1].lower()
    root = FLAT.get(root, root)
    return NAMES.index(root), mode


def key_relation(a, b):
    (pa, ma), (pb, mb) = key_norm(a), key_norm(b)
    if (pa, ma) == (pb, mb):
        return "exact"
    if ma != mb:
        maj, mino = ((pa, pb) if ma == "major" else (pb, pa))
        if (maj - mino) % 12 == 3:
            return "relative"
        if pa == pb:
            return "parallel"
    if ma == mb and (pa - pb) % 12 in (5, 7):
        return "fifth"
    return "other"


def bar_assign(downbeats, beats):
    return None


def main():
    A = {}
    index = {"schema": "index.music.v1", "root": "tests/.cache/real/<slug>/", "songs": {}}
    models_lock = jl(REPO / "models.lock.json")
    rev = {}
    for m in models_lock["models"]:
        f = m["files"][0]
        rev[m["id"]] = {"revision": f.get("revision"), "sha256": f["sha256"][:12]}
    ARTS = {
        "decode": [("decode/mix.wav", "ffmpeg 9.0.2", "-", "float32 WAV native sr stereo"), ("decode/decode.json", "ffprobe", "-", "json")],
        "demucs": [("demucs/htdemucs/*.wav", "demucs_onnx_htdemucs", rev.get("demucs_onnx_htdemucs"), "float32 WAV 44.1k stereo"), ("demucs/htdemucs_6s/*.wav", "demucs_onnx_htdemucs_6s", rev.get("demucs_onnx_htdemucs_6s"), "float32 WAV 44.1k stereo")],
        "beat_this": [("beat_this/logits_beat.npy", "beat_this final0", rev.get("beat_this"), "npy float32 [T] 50 fps raw logits"), ("beat_this/logits_downbeat.npy", "beat_this final0", rev.get("beat_this"), "npy float32 [T] 50 fps"), ("beat_this/beat_this.json", "beat_this final0", rev.get("beat_this"), "json beats/downbeats/beat_numbers (s)")],
        "allin1": [("allin1/allin1.json", "allin1_harmonix", rev.get("allin1_harmonix"), "json segments/labels/beats"), ("allin1/activations.npz", "allin1_harmonix", rev.get("allin1_harmonix"), "npz beat/downbeat/segment[T], label[10,T] 100 fps"), ("allin1/embeddings.npy", "allin1_harmonix", rev.get("allin1_harmonix"), "npy float32 [4,T,24,8]")],
        "librosa": [("librosa/librosa.json", "librosa 1.0.0", "-", "json tempo/candidates/beats/onsets"), ("librosa/tempogram.npz", "librosa 1.0.0", "-", "npz float16 [384,T]"), ("librosa/plp.npy", "librosa 1.0.0", "-", "npy [T] 43.07 fps")],
        "spectral_proto": [("spectral_proto/curves.f32", "prototype spectral/proto.py", "-", "float32 LE [frames,34] 100 Hz, columns in curve_columns.json"), ("spectral_proto/spectrum128.u8", "prototype", "-", "uint8 [frames,128]"), ("spectral_proto/summary.json", "prototype", "-", "json"), ("spectral_proto/dynamics_segments.json", "prototype spectral/seg.py", "-", "json")],
        "chords": [("chords/chords.json", "lv_chordia_ismir2019_chordnet", rev.get("lv_chordia_ismir2019_chordnet"), "json [{start_time,end_time,chord}]")],
        "key": [("key/key.json", "skey_onnx + KS/Temperley profiles", rev.get("skey_onnx"), "json probs[24], windows")],
        "notes": [("notes/*.json", "basic_pitch_nmp_onnx", rev.get("basic_pitch_nmp_onnx"), "json [start,end,midi,amp]"), ("notes/*.mid", "basic_pitch_nmp_onnx", rev.get("basic_pitch_nmp_onnx"), "MIDI")],
        "pitch": [("pitch/swiftf0.npz", "swift_f0_onnx", rev.get("swift_f0_onnx"), "npz t/hz/conf/loudness_db"), ("pitch/rmvpe.npz", "rmvpe_onnx", rev.get("rmvpe_onnx"), "npz t/hz/conf"), ("pitch/pitch.json", "-", "-", "json stats")],
        "instruments": [("instruments/ced_*.npz", "ced_base_onnx", rev.get("ced_base_onnx"), "npz probs float16 [W,527]"), ("instruments/clap_*.npz", "clap_larger_music_speech_onnx", rev.get("clap_larger_music_speech_onnx"), "npz embeds/sims"), ("instruments/instruments.json", "-", "-", "json summary")],
        "mood": [("mood/mood.npz", "essentia msd-musicnn/emomusic/deam/discogs-effnet", rev.get("essentia_msd_musicnn"), "npz"), ("mood/mood.json", "-", "-", "json")],
        "madmom_dbn": [("madmom_dbn/madmom_dbn.json", "madmom_downbeats_blstm", rev.get("madmom_downbeats_blstm"), "json beats [t,pos]"), ("madmom_dbn/rnn_activations.npy", "madmom_downbeats_blstm", rev.get("madmom_downbeats_blstm"), "npy float32 [T,2] 100 fps")],
        "piano": [("piano/presence.json", "-", "-", "json"), ("piano/piano.json", "piano_transcription_crnn", rev.get("piano_transcription_crnn"), "json notes (only if piano present)"), ("piano/piano.mid", "piano_transcription_crnn", rev.get("piano_transcription_crnn"), "MIDI")],
    }
    for slug in SLUGS:
        r = CACHE / slug
        if not r.exists():
            continue
        a = {"timings": {}}
        idx = {}
        for st in STEPS:
            d = r / st
            done = d / "_done.json"
            if done.exists():
                dj = jl(done)
                a["timings"][st] = {"wall_s": dj["wall_s"], "proc_cpu_s": dj.get("proc_cpu_s"), "sys_cpu": dj.get("system_cpu_busy_frac_during"),
                                    "locks": sorted(set(dj.get("concurrent_locks_start", []) + dj.get("concurrent_locks_end", [])))}
            elif (d / "_error.json").exists():
                a["timings"][st] = {"error": jl(d / "_error.json")["error"]}
            files = []
            for pat, model, rv, fmt in ARTS.get(st, []):
                hits = sorted(r.glob(pat))
                if hits:
                    files.append({"path": str(Path("tests/.cache/real") / slug / pat).replace("\\", "/"), "n_files": len(hits), "model": model, "revision": rv, "format": fmt})
            if files:
                idx[st] = {"status": "done" if done.exists() else "partial", "artefacts": files}
        index["songs"][slug] = idx
        # --- rhythm agreement
        bt = jl(r / "beat_this" / "beat_this.json") if (r / "beat_this" / "beat_this.json").exists() else None
        a1 = jl(r / "allin1" / "allin1.json") if (r / "allin1" / "allin1.json").exists() else None
        md = jl(r / "madmom_dbn" / "madmom_dbn.json") if (r / "madmom_dbn" / "madmom_dbn.json").exists() else None
        lb = jl(r / "librosa" / "librosa.json") if (r / "librosa" / "librosa.json").exists() else None
        tempo = {}
        trk = {}
        if bt:
            trk["beat_this"] = (np.array(bt["beats"]), np.array(bt["downbeats"]))
            tempo["beat_this_median_bpm"] = round(bt["median_bpm"], 2) if bt["median_bpm"] else None
            ib = np.diff(bt["beats"])
            tempo["beat_this_bpm_p10_p90"] = [round(float(60 / np.percentile(ib, 90)), 1), round(float(60 / np.percentile(ib, 10)), 1)]
            tempo["beat_this_n_beats"], tempo["beat_this_n_downbeats"] = len(bt["beats"]), len(bt["downbeats"])
            if bt["downbeat" if False else "downbeats"]:
                bpb = np.diff(np.searchsorted(bt["beats"], bt["downbeats"]))
                vals, cnt = np.unique(bpb, return_counts=True)
                tempo["beat_this_beats_per_bar_hist"] = {int(v): int(c) for v, c in zip(vals, cnt)}
        if a1:
            trk["allin1"] = (np.array(a1["beats"]), np.array(a1["downbeats"]))
            tempo["allin1_bpm"] = a1["bpm"]
            ib = np.diff(a1["beats"])
            tempo["allin1_median_bpm_from_beats"] = round(float(60 / np.median(ib)), 2)
            tempo["allin1_n_beats"], tempo["allin1_n_downbeats"] = len(a1["beats"]), len(a1["downbeats"])
            bpb = np.diff(np.searchsorted(a1["beats"], a1["downbeats"])) if a1["downbeats"] else []
            if len(bpb):
                vals, cnt = np.unique(bpb, return_counts=True)
                tempo["allin1_beats_per_bar_hist"] = {int(v): int(c) for v, c in zip(vals, cnt)}
        if md:
            for tag in ("bpb34", "bpb4"):
                b = np.array([t for t, p in md[tag]["beats"]])
                trk[f"madmom_{tag}"] = (b, np.array(md[tag]["downbeats"]))
            tempo["madmom_bpb34_median_bpm"] = round(float(60 / np.median(np.diff(trk["madmom_bpb34"][0]))), 2)
            tempo["madmom_bpb4_median_bpm"] = round(float(60 / np.median(np.diff(trk["madmom_bpb4"][0]))), 2)
            tempo["madmom_bpb34_n_beats"], tempo["madmom_bpb34_n_downbeats"] = len(trk["madmom_bpb34"][0]), len(trk["madmom_bpb34"][1])
        if lb:
            trk["librosa_beat_track"] = (np.array(lb["beat_track_beats"]), np.array([]))
            tempo["librosa_tempo_mean_agg"] = round(lb["tempo_global_mean_agg"], 2)
            tempo["librosa_tempo_dynamic_median"] = round(lb["tempo_dynamic_median"], 2)
            tempo["librosa_beat_track_tempo"] = round(lb["beat_track_tempo"], 2)
            tempo["librosa_tempogram_candidates"] = lb["tempogram_candidates_bpm_salience"][:6]
        a["tempo"] = tempo
        pairs = {}
        names = list(trk)
        for i, x in enumerate(names):
            for y in names[i + 1:]:
                bx, by = trk[x][0], trk[y][0]
                p = {"beat_f_70ms": fm(bx, by), "beat_f_150ms": fm(bx, by, 0.15)}
                fs, k = fm_shift(bx, by)
                p["beat_f_70ms_best_beat_shift"] = [fs, k]
                dx, dy = trk[x][1], trk[y][1]
                if len(dx) > 1 and len(dy) > 1:
                    p["downbeat_f_70ms"] = fm(dx, dy)
                # half/double tempo relation: F of x against y subsampled / x against y interpolated
                if len(bx) > 3 and len(by) > 3:
                    ratio = np.median(np.diff(bx)) / np.median(np.diff(by))
                    p["median_ibi_ratio_x_over_y"] = round(float(ratio), 3)
                pairs[f"{x}|{y}"] = p
        a["beat_agreement"] = pairs
        # --- key
        if (r / "key" / "key.json").exists():
            k = jl(r / "key" / "key.json")
            ent = {"skey_global_top3": k.get("skey_global_top3"), "ks_top3": k.get("profile_global_ks_top3"), "temperley_top3": k.get("profile_global_temperley_top3")}
            # chord-histogram key: from lv-chordia durations -> root pitch-class weights (major/minor chord) -> KS
            sk = k.get("skey_global_top3", [[None]])[0][0]
            ks = k["profile_global_ks_top3"][0][0]
            tp = k["profile_global_temperley_top3"][0][0]
            ent["relations"] = {"skey_vs_ks": key_relation(sk, ks) if sk else None, "skey_vs_temperley": key_relation(sk, tp) if sk else None, "ks_vs_temperley": key_relation(ks, tp)}
            wins = k.get("skey_windows_30s_hop15s", [])
            if wins:
                from collections import Counter
                cnt = Counter(w["top"] for w in wins)
                ent["skey_window_votes"] = cnt.most_common(4)
                ent["skey_window_n"] = len(wins)
            pw = k.get("profile_windows_ks_30s_hop15s", [])
            if pw:
                from collections import Counter
                ent["ks_window_votes"] = Counter(w["top"] for w in pw).most_common(4)
            if sk and wins:
                ent["skey_window_agreement_with_global"] = round(float(np.mean([w["top"] == sk for w in wins])), 3)
            if (r / "chords" / "chords.json").exists():
                ch = jl(r / "chords" / "chords.json")["segments"]
                w = np.zeros(24)
                for s in ch:
                    if s["chord"] in ("N", "X"):
                        continue
                    root, q = s["chord"].split(":")[0], s["chord"].split(":")[1] if ":" in s["chord"] else "maj"
                    root = FLAT.get(root, root)
                    if root not in NAMES:
                        continue
                    w[NAMES.index(root) + (12 if q.startswith("min") else 0)] += s["end_time"] - s["start_time"]
                # key from chord durations: score = chords diatonic to each key (I ii iii IV V vi for major etc.) weighted
                sc = []
                for pc in range(12):
                    for mode in ("major", "minor"):
                        if mode == "major":
                            good = [(pc, 0), ((pc + 5) % 12, 0), ((pc + 7) % 12, 0), ((pc + 2) % 12, 1), ((pc + 4) % 12, 1), ((pc + 9) % 12, 1)]
                        else:
                            good = [(pc, 1), ((pc + 5) % 12, 1), ((pc + 7) % 12, 1), ((pc + 3) % 12, 0), ((pc + 8) % 12, 0), ((pc + 10) % 12, 0)]
                        sc.append((sum(w[r_ + 12 * m_] for r_, m_ in good) / max(w.sum(), 1e-9), f"{NAMES[pc]} {mode}"))
                sc.sort(reverse=True)
                ent["chord_diatonic_top3"] = [[n, round(s, 3)] for s, n in sc[:3]]
                ent["chord_hist_top5"] = [[f"{NAMES[i % 12]}{'m' if i >= 12 else ''}", round(float(w[i]), 1)] for i in np.argsort(-w)[:5]]
                dist = {}
                for s in ch:
                    dist[s["chord"]] = dist.get(s["chord"], 0) + s["end_time"] - s["start_time"]
                ent["chord_vocab_n"] = len(dist)
                ent["chord_n_segments"] = len(ch)
                ent["chord_no_chord_frac"] = round(dist.get("N", 0) / max(1e-9, sum(dist.values())), 3)
            a["key"] = ent
        # --- vocals / pitch
        if (r / "pitch" / "pitch.json").exists():
            a["pitch"] = jl(r / "pitch" / "pitch.json")
        if (r / "spectral_proto" / "summary.json").exists():
            s = jl(r / "spectral_proto" / "summary.json")
            a["spectral"] = {k: s.get(k) for k in ("integrated_lufs", "lra_lu", "sample_peak_dbfs", "kick_events_port", "kick_events_offline_ref", "onsets", "corr_median", "width_median", "timings_s", "first_kicks")}
        if (r / "spectral_proto" / "dynamics_segments.json").exists():
            a["dynamics"] = jl(r / "spectral_proto" / "dynamics_segments.json")["segments"]
        if a1:
            a["allin1_segments"] = [[round(s["start"], 1), round(s["end"], 1), s["label"]] for s in a1["segments"]]
        if (r / "mood" / "mood.json").exists():
            m = jl(r / "mood" / "mood.json")
            a["mood"] = {k: m[k] for k in ("emomusic_va_mean", "deam_va_mean", "top_moodtheme_mean")}
        if (r / "instruments" / "instruments.json").exists():
            i = jl(r / "instruments" / "instruments.json")
            a["instruments"] = {k: v for k, v in i.items() if k.endswith("_top12_mean") or k.endswith("_top8_mean_cos")}
        if (r / "piano" / "presence.json").exists():
            a["piano_presence"] = jl(r / "piano" / "presence.json")
        if (r / "demucs" / "demucs.json").exists():
            a["demucs"] = jl(r / "demucs" / "demucs.json")["models"]
        if (r / "decode" / "decode.json").exists():
            dj = jl(r / "decode" / "decode.json")
            a["decode"] = {k: dj[k] for k in ("sr", "channels", "duration_s", "peak_dbfs", "rms_dbfs", "decoder_warning_count")}
        A[slug] = a
    (CACHE / "index.music.json").write_text(json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8")
    (Path(__file__).parent / "analysis.json").write_text(json.dumps(A, indent=1, ensure_ascii=False), encoding="utf-8")
    print("wrote index.music.json and analysis.json for", list(A))


if __name__ == "__main__":
    main()
