"""bench-music extra agreement probes: MEGAFAUNA tempo-octave test, madmom downbeat phase vs beat_this/allin1, local tempo per 30 s."""
import json
from pathlib import Path
import numpy as np, mir_eval
R = Path(__file__).resolve().parents[4] / "tests" / ".cache" / "real"
jl = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
F = lambda a, b, w=0.07: round(float(mir_eval.beat.f_measure(np.asarray(a), np.asarray(b), f_measure_threshold=w)), 4)
out = {}
def mid(b):
    b = np.asarray(b); return np.sort(np.r_[b, (b[:-1] + b[1:]) / 2])
def local(beats, win=30):
    b = np.asarray(beats); res = []
    for t in range(0, int(b[-1]), win):
        s = b[(b >= t) & (b < t + win)]
        res.append(round(float(60 / np.median(np.diff(s))), 1) if len(s) > 3 else None)
    return res
for slug in ("megafauna", "versatile", "jeremy", "newton-vs-nye"):
    bt, a1, md = jl(R/slug/"beat_this/beat_this.json"), jl(R/slug/"allin1/allin1.json"), jl(R/slug/"madmom_dbn/madmom_dbn.json")
    mb = np.array([t for t, p in md["bpb34"]["beats"]]); mdb = md["bpb34"]["downbeats"]
    o = {"local_bpm_30s": {"beat_this": local(bt["beats"]), "allin1": local(a1["beats"]), "madmom": local(mb)}}
    o["F70_beat_this_vs_allin1_x2"] = F(bt["beats"], mid(a1["beats"]))
    o["F70_beat_this_vs_allin1_half"] = F(bt["beats"], a1["beats"][::2])
    o["F70_madmom_vs_allin1_x2"] = F(mb, mid(a1["beats"]))
    o["F70_madmom_vs_beat_this_x2"] = F(mb, mid(bt["beats"]))
    # downbeat phase: shift madmom downbeats by k beats of its own grid
    ph = {}
    for k in range(-1, 4):
        idx = [i for i, (t, p) in enumerate(md["bpb34"]["beats"]) if p == 1]
        sh = [mb[i + k] for i in idx if 0 <= i + k < len(mb)]
        ph[k] = {"vs_beat_this": F(bt["downbeats"], sh), "vs_allin1": F(a1["downbeats"], sh)}
    o["madmom_downbeat_shift_k_beats"] = ph
    out[slug] = o
(Path(__file__).parent / "extra.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(json.dumps(out, indent=1))
