"""Task 5: speaker embeddings per aligned line on newton-vs-nye (ECAPA and WeSpeaker), agglomerative clustering k=3,4 + eigengap.
Line ids only on stdout.  Usage: bw_voices.py [stem]"""
import sys, os, time, json, re
sys.path.insert(0, r"C:\Users\OpenSrcerer\Desktop\playground\mv-harness\scripts"); sys.path.insert(0, os.path.dirname(__file__))
from heavy_lock import heavy, apply_thread_limits
apply_thread_limits(6)
import numpy as np, torch
from bw_common import *
SLUG = "newton-vs-nye"; STEM = sys.argv[1] if len(sys.argv) > 1 else "lead_vocals"
OUT = sdir(SLUG, "voices")
MODELS = os.environ["MVH_MODELS_DIR"]
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import silhouette_score, adjusted_rand_score


def line_spans():
    words = json.load(open(os.path.join(sdir(SLUG, "align_mms"), f"{SLUG}_lead_vocals_mms_words.json"), encoding="utf-8"))
    by = {}
    for w in words:
        if "start" in w:
            by.setdefault(w["line"], []).append(w)
    return {li: (min(x["start"] for x in ws), max(x["end"] for x in ws)) for li, ws in by.items()}


def asr_extra_spans(first_line_t, last_line_t):
    """whisper segments outside the aligned lines (announcer intro / outro candidates), as extra probes"""
    W = json.load(open(os.path.join(sdir(SLUG, "whisper_cpu"), f"{SLUG}_whisper_lead_vocals.json"), encoding="utf-8"))["segments"]
    return [(s["start"], s["end"]) for s in W if (s["end"] < first_line_t - 0.2 or s["start"] > last_line_t + 0.2) and s["end"] - s["start"] > 0.8]


def eigengap(E, kmax=8):
    S = np.clip(E @ E.T, 0, None); np.fill_diagonal(S, 0)
    d = S.sum(1); L = np.eye(len(S)) - (S / np.sqrt(np.outer(d, d)))
    ev = np.sort(np.linalg.eigvalsh(L))[:kmax + 1]
    gaps = np.diff(ev)
    return int(np.argmax(gaps[1:]) + 2), [round(float(x), 3) for x in ev[:kmax + 1]]  # k>=2


def seq_stats(labels, rng, n_perm=500):
    runs = 1 + int((labels[1:] != labels[:-1]).sum())
    perm = [1 + int((p[1:] != p[:-1]).sum()) for p in (rng.permutation(labels) for _ in range(n_perm))]
    return runs, round(float(np.mean(perm)), 1), round(float(np.percentile(perm, 2.5)), 1)


def analyse(name, E, ids, spans, f0med=None):
    rng = np.random.default_rng(0); res = {"model": name, "n_items": len(ids), "dim": int(E.shape[1])}
    En = E / np.linalg.norm(E, axis=1, keepdims=True)
    k_eg, ev = eigengap(En); res["eigengap_k"] = k_eg; res["laplacian_eigs"] = ev
    res["clusterings"] = {}; lab_by_k = {}
    for k in (2, 3, 4, 5):
        lab = AgglomerativeClustering(n_clusters=k, metric="cosine", linkage="average").fit_predict(En)
        # relabel by first appearance
        order = {}
        for x in lab:
            order.setdefault(int(x), len(order))
        lab = np.array([order[int(x)] for x in lab]); lab_by_k[k] = lab
        runs, perm_mean, perm_lo = seq_stats(lab, rng)
        sil = float(silhouette_score(En, lab, metric="cosine")) if len(set(lab)) > 1 and min(np.bincount(lab)) > 0 else None
        dur_by = [round(float(sum(spans[i][1] - spans[i][0] for i, l in zip(ids, lab) if l == c)), 1) for c in range(k)]
        item = {"sizes": [int((lab == c).sum()) for c in range(k)], "voiced_s": dur_by, "silhouette": round(sil, 3) if sil is not None else None,
                "runs": runs, "runs_shuffled_mean": perm_mean, "runs_shuffled_p2.5": perm_lo,
                "seq": " ".join(f"{i}:{'ABCDE'[l]}" for i, l in zip(ids, lab))}
        if f0med is not None:
            item["median_f0_hz_by_cluster"] = [round(float(np.nanmedian([f0med[i] for i, l in zip(ids, lab) if l == c])), 0) for c in range(k)]
        # first appearance of each cluster (late joiner?)
        item["first_item_of_cluster"] = [int(ids[int(np.argmax(lab == c))]) for c in range(k)]
        res["clusterings"][k] = item
    return res, lab_by_k


if __name__ == "__main__":
    import torchaudio
    spans = line_spans()
    ids = sorted(spans)
    first_t = min(s[0] for s in spans.values()); last_t = max(s[1] for s in spans.values())
    extra = asr_extra_spans(first_t, last_t)
    # items: aligned lines then extras (ids 1000+k); skip very short items
    items = [(i, spans[i]) for i in ids if spans[i][1] - spans[i][0] >= 1.0] + [(1000 + k, e) for k, e in enumerate(extra)]
    short = [i for i in ids if spans[i][1] - spans[i][0] < 1.0]
    for i, s in items:
        spans[i] = s
    wav = load_stem16k(SLUG, STEM)
    with heavy("bench-words", threads=6):
        torch.set_num_threads(6)
        from speechbrain.inference.speaker import EncoderClassifier
        from speechbrain.utils.fetching import LocalStrategy
        d = os.path.join(MODELS, "speaker", "ecapa-voxceleb")
        t0 = time.time()
        clf = EncoderClassifier.from_hparams(source=d, savedir=os.path.join(OUT, "ecapa_savedir"), run_opts={"device": "cpu"}, local_strategy=LocalStrategy.COPY, overrides={"pretrained_path": d})
        E_ec = np.stack([clf.encode_batch(torch.from_numpy(wav[int(spans[i][0] * 16000):int(spans[i][1] * 16000)])[None]).squeeze().numpy() for i, _ in items])
        t_ec = time.time() - t0
        import onnxruntime as ort
        so = ort.SessionOptions(); so.intra_op_num_threads = 6; so.inter_op_num_threads = 1
        s = ort.InferenceSession(os.path.join(MODELS, "speaker", "wespeaker-resnet34-lm", "voxceleb_resnet34_LM.onnx"), so, providers=["CPUExecutionProvider"])

        def wsp(w):
            f = torchaudio.compliance.kaldi.fbank(torch.from_numpy(w)[None, :] * 32768, num_mel_bins=80, frame_length=25, frame_shift=10, dither=0.0, sample_frequency=16000, window_type="hamming", use_energy=False)
            f = f - f.mean(0, keepdim=True)
            return s.run(None, {"feats": f[None].numpy().astype(np.float32)})[0][0]
        t0 = time.time()
        E_ws = np.stack([wsp(wav[int(spans[i][0] * 16000):int(spans[i][1] * 16000)]) for i, _ in items])
        t_ws = time.time() - t0
        # median f0 per item (SwiftF0) as an independent plausibility cue (male voices differ in register)
        from swift_f0 import SwiftF0
        det = SwiftF0(threads=6)
        f0med = {}
        for i, _ in items:
            r = det.detect(wav[int(spans[i][0] * 16000):int(spans[i][1] * 16000)], 16000, fmin=65, fmax=500)
            hz = np.asarray(r.pitch_hz)[np.asarray(r.confidence) > 0.6]
            f0med[i] = float(np.median(hz)) if len(hz) else float("nan")
    ids_all = [i for i, _ in items]
    out = {"stem": STEM, "aligned_lines": len(ids), "items": len(items), "skipped_short_lines(<1s)": short, "extra_asr_items": [1000 + k for k in range(len(extra))],
           "ecapa_embed_s": round(t_ec, 1), "wespeaker_embed_s": round(t_ws, 1)}
    ra, la = analyse("ecapa", E_ec, ids_all, spans, f0med)
    rb, lb = analyse("wespeaker", E_ws, ids_all, spans, f0med)
    out["ecapa"] = ra; out["wespeaker"] = rb
    out["agreement_ARI_ecapa_vs_wespeaker"] = {k: round(float(adjusted_rand_score(la[k], lb[k])), 3) for k in (2, 3, 4, 5)}
    # voices clustered on lines only (no extras), for the contract-relevant answer
    np.save(os.path.join(OUT, f"emb_ecapa_{STEM}.npy"), E_ec); np.save(os.path.join(OUT, f"emb_wespeaker_{STEM}.npy"), E_ws)
    json.dump({"ids": ids_all, "spans": {str(i): spans[i] for i in ids_all}}, open(os.path.join(OUT, "items.json"), "w"))
    json.dump(out, open(os.path.join(OUT, f"voices_{STEM}_summary.json"), "w"), indent=1)
    print(json.dumps(out))
