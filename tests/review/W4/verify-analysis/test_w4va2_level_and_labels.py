"""W4 verifier, analysis group, round 2 (w4verify-analysis-r2): what the fixed analysis level (W4-AN-9) did not reach,
and a label regression it brought.

1. W4V2-GAIN-VOCALS. W4-AN-9 scales the mix to -10 LUFS before allin1, rhythm, harmony and structure, and makes the
   dynamics silence threshold relative. The vocals stage (M3b) still gates presence with an ABSOLUTE floor
   (``level_floor_db`` -55 dB: ``loud = level > max(-55, p99 - 35)``, src/mvh/stages/vocals/__init__.py:174), which binds
   whenever the stem's p99 is below -20 dB, so vocal notes and phrases still follow the master level.
2. W4V2-JEREMY-HOOK-VERSE. At the new fixed level allin1 relabels a Jeremy section that carries the chorus hook line
   (its only lead line belongs to the lyric text group that recurs in every chorus) from chorus to verse.

Runs: w4va_support.GAIN_PAIRS (fixer re-analyses of round 1's -12 dB copies and round 2's fresh gain
copies). Numbers and ids only, never lyric text.
"""

from __future__ import annotations

import numpy as np
import pytest
from w4va_support import GAIN_IDS, GAIN_PAIRS, base, run


def _cover(items, dur, step=0.05):
    ts = np.arange(0.0, dur, step)
    m = np.zeros(len(ts), bool)
    for x in items:
        m |= (ts >= x["t"]) & (ts < x["t"] + x["d"])
    return m


def _f(r, e, tol):
    r, e = np.asarray(r, float), np.asarray(e, float)
    if not len(r) or not len(e):
        return float(len(r) == len(e))
    rec = float(np.mean([np.min(np.abs(e - t)) <= tol for t in r]))
    pre = float(np.mean([np.min(np.abs(r - t)) <= tol for t in e]))
    return 0.0 if rec + pre == 0 else 2 * rec * pre / (rec + pre)


@pytest.mark.parametrize("slug,name", GAIN_PAIRS, ids=GAIN_IDS)
def test_w4va2_vocal_notes_and_phrases_survive_a_gain_change(slug, name):
    """A pure-gain copy must keep the vocal phrases (coverage IoU >= 0.9) and vocal note onsets (F >= 0.8 at 50 ms)."""
    g, b = run(name), base(slug)
    pa, pb = b.events("vocal_phrases"), g.events("vocal_phrases")
    na, nb = b.events("notes.vocals"), g.events("notes.vocals")
    dur = max([x["t"] + x["d"] for x in pa + pb] or [1.0]) + 1.0
    ca, cb = _cover(pa, dur), _cover(pb, dur)
    iou = float((ca & cb).sum() / max(1, (ca | cb).sum()))
    fn = _f([x["t"] for x in na], [x["t"] for x in nb], 0.05)
    assert iou >= 0.9 and fn >= 0.8, (
        f"{name} vs {slug}: vocal phrases {len(pa)} -> {len(pb)} (covered {ca.sum() * 0.05:.1f} s -> {cb.sum() * 0.05:.1f} s, "
        f"IoU {iou:.3f}); notes.vocals {len(na)} -> {len(nb)} (onset F {fn:.3f}). The vocals stage gates on an absolute "
        f"-55 dB floor (level_floor_db), outside the fixed analysis level of W4-AN-9")


@pytest.mark.parametrize("slug", ["jeremy", "megafauna", "versatile", "newton-vs-nye"])
def test_w4va2_a_section_holding_only_the_chorus_hook_is_not_a_verse(slug):
    """A section labelled verse whose lead lyric lines all belong to text groups that occur in >= 3 chorus sections
    is the chorus (the hook), not a verse. Lyric ids only."""
    f = base(slug)
    if not f.has("lyrics/lyrics.json"):
        pytest.skip(f"{slug}: no lyrics")
    lines = [ln for ln in f.json("lyrics/lyrics.json").get("lines", []) if not ln.get("backing") and ln.get("text_group")]
    secs = [(s["label"], float(s["t"]), float(s["t"]) + float(s["d"])) for s in f.events("sections")]
    groups_of = [{ln["text_group"] for ln in lines if a <= ln["t"] < e} for _, a, e in secs]
    in_chorus: dict[str, int] = {}
    for (lab, _, _), gs in zip(secs, groups_of):
        if lab == "chorus":
            for gid in gs:
                in_chorus[gid] = in_chorus.get(gid, 0) + 1
    bad = [(round(a, 2), sorted(gs)) for (lab, a, _), gs in zip(secs, groups_of)
           if lab == "verse" and gs and all(in_chorus.get(gid, 0) >= 3 for gid in gs)]
    assert not bad, (f"{slug}: verse sections holding only chorus-hook lyric groups (t, text groups): {bad}; "
                     f"chorus counts per group {in_chorus}")


# ------------------------------------------------------------------------- W4V2-GAIN-STEMACT / W4V2-GAIN-DRUMS (M3a)
def _curves(f):
    idx = f.json("curves/index.json")
    raw = {}

    def get(cid):
        ch = next((c for c in idx["channels"] if c["id"] == cid), None)
        if ch is None or idx["files"][ch["file"]]["dtype"] != "f32le":
            return None
        if ch["file"] not in raw:
            raw[ch["file"]] = np.fromfile(f.path / idx["files"][ch["file"]]["path"], dtype="<f4")
        o = ch["offset_bytes"] // 4
        return raw[ch["file"]][o:o + ch["n"]]

    return idx, get


@pytest.mark.parametrize("slug,name", GAIN_PAIRS, ids=GAIN_IDS)
def test_w4va2_stem_activity_survives_a_gain_change(slug, name):
    """stem_activity gates on an ABSOLUTE -45 dBFS (``active_db``), so a quieter master turns stems off. For every stem
    active >= 5 % of the original, the stem.<s>.active curve must agree on >= 97 % of frames, and the present flags must
    be identical."""
    g, b = run(name), base(slug)
    ib, get_b = _curves(b)
    _, get_g = _curves(g)
    bad = {}
    for ch in ib["channels"]:
        cid = ch["id"]
        if not (cid.startswith("stem.") and cid.endswith(".active")):
            continue
        a, c = get_b(cid), get_g(cid)
        if a is None or c is None or float(np.mean(a > 0.5)) < 0.05:
            continue
        n = min(a.size, c.size)
        agree = float(np.mean((a[:n] > 0.5) == (c[:n] > 0.5)))
        if agree < 0.97:
            bad[cid] = (round(float(np.mean(a > 0.5)), 3), round(float(np.mean(c > 0.5)), 3), round(agree, 3))
    pres_b = {k: v.get("present") for k, v in b.json("meta/stems.json")["stems"].items()}
    pres_g = {k: v.get("present") for k, v in g.json("meta/stems.json")["stems"].items()}
    flips = {k: (pres_b[k], pres_g.get(k)) for k in pres_b if pres_b[k] != pres_g.get(k)}
    assert not bad and not flips, (f"{name} vs {slug}: stem activity (active share original, gain copy, frame agreement) "
                                   f"{bad}; present flips {flips}")


@pytest.mark.parametrize("slug,name", GAIN_PAIRS, ids=GAIN_IDS)
def test_w4va2_agent_kick_and_drum_hits_survive_a_gain_change(slug, name):
    """The UD2 agent-facing kick (drum-stem kick when kick_source = drums) and the strong drum-stem hits must not depend
    on the master level: kick F >= 0.97 at 30 ms, and at most 2 % of the strong (vel >= 0.5) kick / snare / crash hits
    of either run without a same-drum partner in the other. DrumSep runs on the master-level drum stem
    (separate_hq: normalization off), and at -12 dB it routes kick energy to toms (Versatile)."""
    g, b = run(name), base(slug)

    def agent(f):
        if f.json("meta/drums.json").get("kick_source") == "mix":
            return [h["t"] for h in f.events("hits.kick")]
        return [h["t"] for h in f.events("drum_hits") if h["drum"] == "kick"]

    fk = _f(agent(b), agent(g), 0.03)
    report = {}
    for drum in ("kick", "snare", "cymbal"):
        hb = [h for h in b.events("drum_hits") if h["drum"] == drum]
        hg = [h for h in g.events("drum_hits") if h["drum"] == drum]
        tb, tg = np.array([h["t"] for h in hb]), np.array([h["t"] for h in hg])
        lost = [h for h in hb if h["vel"] >= 0.5 and (not len(tg) or np.min(np.abs(tg - h["t"])) > 0.03)]
        added = [h for h in hg if h["vel"] >= 0.5 and (not len(tb) or np.min(np.abs(tb - h["t"])) > 0.03)]
        strong = max(1, sum(h["vel"] >= 0.5 for h in hb))
        if (len(lost) + len(added)) / strong > 0.02:
            report[drum] = {"strong": strong, "lost": len(lost), "added": len(added)}
    assert fk >= 0.97 and not report, (f"{name} vs {slug}: agent kick F {fk:.3f} (30 ms); strong drum-stem hits without "
                                       f"a partner {report}")


# ------------------------------------------------------------------------------------------- W4V2-GAIN-SPECTRAL (M1)
@pytest.mark.parametrize("slug,name", GAIN_PAIRS, ids=GAIN_IDS)
def test_w4va2_spectral_onsets_and_hits_survive_a_gain_change(slug, name):
    """The mix onset / hit events (spectral) of a pure-gain copy must match the original: strong events (strength
    >= 0.6, the ones choreo and agents act on) F >= 0.9 at 30 ms per lane. spectral gates on an absolute -46 dB
    (``gate_db``, only partly lowered for quiet masters by ``gate_margin_db``), outside W4-AN-9's analysis level."""
    g, b = run(name), base(slug)
    bad = {}
    for lane in ("onsets.bass", "onsets.mid", "onsets.high", "hits.mid", "hits.high"):
        sa = [x["t"] for x in b.events(lane) if float(x.get("strength", 0.0)) >= 0.6]
        sb = [x["t"] for x in g.events(lane) if float(x.get("strength", 0.0)) >= 0.6]
        if len(sa) < 10:
            continue
        fv = _f(sa, sb, 0.03)
        if fv < 0.9:
            bad[lane] = (len(sa), len(sb), round(fv, 3))
    assert not bad, f"{name} vs {slug}: strong mix events (n original, n gain copy, F at 30 ms): {bad}"
