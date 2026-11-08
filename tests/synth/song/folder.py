# ruff: noqa: E501  (long data tables / docstrings in generated-fixture code)
"""Write the complete contract song folder for the synthetic song (tests/contract/synth/) from the ground truth.

Every catalogue output of every stage is written (public files at their contract path, cache-only outputs under
_intermediate/<stage>/), plus the runner's finalize files (manifest.json, run.json, curves/*, schema/**), the
user inputs (meaning/intent.md, meaning/authored.json), the ground-truth sidecar (_truth/) and finally .done.json.
Every JSON document is validated against its contract schema while it is written; events use
mvh.contract.events (make_envelope + dumps_events) and curves use mvh.contract.curvefile.assemble.

Provenance marks each file as `fixture` (from the generator ground truth), `measured` (reference measurement of the
rendered audio, tests/synth/song/analysis.py) or `synthetic` (no physical truth: plausible, internally consistent values).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np

from mvh.contract import catalog, curvefile, schemas
from mvh.contract.catalog import CONTRACT_VERSION
from mvh.contract.events import dumps_events, dumps_json, make_envelope

from .. import audio_io, dsp
from ..midi import write_smf
from . import analysis as A
from . import score as S
from . import truth as T
from .render import Render, render

__all__ = ["build_folder", "DEPS"]

#: PLAN §3.2 / CONTRACT §11 deps (for deterministic provenance.upstream; not read from the live stage packages)
DEPS = {
    "ingest": (),
    "identity": ("ingest",),
    "separate_fast": ("ingest",),
    "separate_hq": ("ingest",),
    "allin1": ("separate_fast",),
    "spectral": ("ingest",),
    "loudness": ("ingest",),
    "rhythm": ("ingest", "allin1", "spectral"),
    "harmony": ("ingest", "rhythm"),
    "dynamics": ("loudness", "spectral", "rhythm"),
    "structure": ("allin1", "rhythm", "harmony", "dynamics"),
    "stem_activity": ("ingest", "separate_fast", "separate_hq"),
    "drums": ("separate_hq", "stem_activity"),
    "instruments": ("ingest", "separate_fast", "separate_hq", "stem_activity"),
    "notes": ("separate_hq", "stem_activity", "rhythm"),
    "vocals": ("separate_hq", "stem_activity", "instruments", "rhythm"),
    "mood": ("ingest", "structure"),
    "lyrics": ("identity", "separate_hq", "stem_activity", "structure"),
    "voices": ("lyrics", "separate_hq", "stem_activity"),
    "lipsync": ("lyrics", "voices", "separate_hq"),
    "choreo": ("rhythm", "structure", "drums", "spectral", "vocals", "harmony", "dynamics"),
    "cues": ("choreo", "structure", "dynamics", "rhythm", "drums"),
    "meaning": ("identity", "lyrics", "voices", "structure", "mood", "vocals", "instruments", "cues"),
}
_ANALYSIS = list(DEPS)
DEPS.update({k: tuple(_ANALYSIS) for k in ("brief", "viewer", "frames")})
SLUG = "synth"
INPUT_NAME = "synth-song.flac"
TAGS = {
    "title": S.TITLE,
    "artist": S.ARTIST,
    "album": S.ALBUM,
    "date": "2026",
    "genre": "Synthetic",
    "comment": "mv-harness synthetic fixture (tests/synth)",
}


def _key(stage: str) -> str:
    return hashlib.sha256(f"mvh-fixture/{SLUG}/{stage}/{S.GENERATOR_VERSION}".encode()).hexdigest()


def prov(
    stage: str, kind: str = "fixture", notes: list[str] | None = None, params: dict | None = None
) -> dict[str, Any]:
    base = {
        "fixture": "values from the generator ground truth (tests/synth/song)",
        "measured": "reference measurement of the rendered audio (tests/synth/song/analysis.py), not the production algorithm",
        "synthetic": "SYNTHETIC: no physical truth; plausible, internally consistent values",
    }[kind]
    return {
        "stage": stage,
        "stage_version": S.GENERATOR_VERSION,
        "contract_version": CONTRACT_VERSION,
        "key": _key(stage),
        "params": {"fixture": SLUG, "truth": kind, **(params or {})},
        "models": [],
        "tools": [{"name": "tests.synth", "version": S.GENERATOR_VERSION}],
        "device": "cpu",
        "upstream": {d: _key(d) for d in DEPS[stage]},
        "overrides_applied": [],
        "fallbacks": [],
        "notes": [f"fixture: {base}", *(notes or [])],
    }


class Out:
    """Writes into the fixture folder, validating every JSON against its schema; records file -> stage for the manifest."""

    def __init__(self, root: Path):
        self.root = root
        self.files: dict[str, dict[str, Any]] = {}
        self.errors: list[str] = []

    def _p(self, rel: str) -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def note(self, rel: str, kind: str, stage: str, events: str | None = None) -> None:
        if rel.startswith("_"):
            return
        e: dict[str, Any] = {"path": rel, "kind": kind, "stage": stage}
        if events and rel != f"events/{events}.json":
            e["events"] = events
        self.files[rel] = e

    def text(self, rel: str, text: str, stage: str, kind: str = "text") -> None:
        audio_io.atomic_bytes(self._p(rel), text.encode("utf-8"))
        self.note(rel, kind, stage)

    def json(self, rel: str, obj: Any, stage: str, schema: str | None = None) -> None:
        if schema:
            errs = schemas.validate(obj, schema)
            self.errors += [f"{rel}: {e}" for e in errs]
        self.text(rel, dumps_json(obj), stage, "json")

    def events(
        self,
        name: str,
        items: list[dict],
        stage: str,
        kind: str = "fixture",
        notes: list[str] | None = None,
        fields: dict | None = None,
        rel: str | None = None,
    ) -> dict:
        env = make_envelope(name, items, prov(stage, kind, notes), fields=fields)
        errs = schemas.validate(env, env["schema"])
        self.errors += [f"{name}: {e}" for e in errs]
        path = rel or catalog.event_def(name).file.replace("{src}", name.split(".", 1)[-1])
        audio_io.atomic_bytes(self._p(path), dumps_events(env).encode("utf-8"))
        self.note(path, "events", stage, name)
        return env

    def table(
        self, rel: str, rows: list[dict], columns: list[str], stage: str, schema: str, sep: str = ","
    ) -> None:
        sch = schemas.load(schema)
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=sep, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
        w.writerow(columns)
        for r in rows:
            cells = []
            for c in columns:
                v = r.get(c)
                if v is None:
                    cells.append("")
                elif isinstance(v, bool):
                    cells.append("1" if v else "0")
                elif isinstance(v, float):
                    cells.append(repr(round(v, 6)))
                else:
                    cells.append(str(v).replace("\t", " ").replace("\n", " "))
            w.writerow(cells)
            typed = schemas.coerce_row({c: cells[i] for i, c in enumerate(columns)}, sch)
            errs = schemas.validate(typed, schema)
            self.errors += [f"{rel}: {e}" for e in errs]
        self.text(rel, buf.getvalue(), stage, "table")

    def bytes(self, rel: str, data: bytes, stage: str, kind: str) -> None:
        audio_io.atomic_bytes(self._p(rel), data)
        self.note(rel, kind, stage)

    def audio(self, rel: str, x: np.ndarray, stage: str, codec: str = "flac24", **kw) -> None:
        audio_io.encode(self._p(rel), x, S.SR, codec, **kw)
        self.note(rel, "audio", stage)


# ================================================================================================ helpers
def _r6(x: float) -> float:
    return round(float(x), 6)


def _f(x: float, nd: int = 4) -> float:
    return round(float(x), nd)


def _cover(path: Path) -> None:
    """A 256x256 cover with the PALETTE colours in blocks of decreasing area (largest first)."""
    from PIL import Image

    img = np.zeros((256, 256, 3), dtype=np.uint8)
    rgb = [tuple(int(h[i : i + 2], 16) for i in (1, 3, 5)) for h in S.PALETTE]
    img[:, :] = rgb[0]  # 256*256 minus the rest
    img[160:, :] = rgb[1]  # 96 x 256
    img[160:, 192:] = rgb[2]  # 96 x 64
    img[20:80, 20:80] = rgb[3]  # 60 x 60
    img[100:140, 180:220] = rgb[4]  # 40 x 40
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    Image.fromarray(img, "RGB").save(buf, format="JPEG", quality=92, optimize=False, progressive=False)
    audio_io.atomic_bytes(path, buf.getvalue())


def _pcm_sha(x2: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(x2.T).astype("<f4").tobytes()).hexdigest()


def _lrc_ts(t: float) -> str:
    m, s = divmod(max(0.0, t), 60)
    return f"{int(m):02d}:{s:05.2f}"


def _vtt_ts(t: float, comma: bool = False) -> str:
    h, rem = divmod(max(0.0, t), 3600)
    m, s = divmod(rem, 60)
    ms = int(round((s - int(s)) * 1000))
    si = int(s)
    if ms == 1000:
        si, ms = si + 1, 0
    return f"{int(h):02d}:{int(m):02d}:{si:02d}{',' if comma else '.'}{ms:03d}"


def _ass_ts(t: float) -> str:
    h, rem = divmod(max(0.0, t), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


# ================================================================================================ main
def build_folder(out_dir: Path, *, log=print) -> dict[str, Any]:
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    o = Out(out_dir)
    log("render ...")
    r = render()
    fr = A.frames_of(S.N_SAMPLES, S.SR)
    n = fr.n
    ch: dict[str, np.ndarray] = {}  # curve channel id -> values
    cmeta: dict[str, dict] = {}  # channel id -> per-song meta (lo/hi ...)
    truth: dict[str, Any] = {
        "generator": "tests.synth.build",
        "version": S.GENERATOR_VERSION,
        "seed": S.SEED,
        "sr": S.SR,
        "n_samples": S.N_SAMPLES,
        "duration_s": S.DURATION,
        "bpm": S.BPM,
        "key": S.KEY,
        "formulas": T.FORMULAS,
        "render_gain": r.gain,
    }
    mix = r.tracks["mix"]
    mono = mix.mean(axis=0)

    # ------------------------------------------------------------------ inputs and ingest
    log("ingest / audio ...")
    cover = out_dir / "artwork" / "cover.jpg"
    _cover(cover)
    o.note("artwork/cover.jpg", "audio", "ingest")
    o.audio(f"_truth/{INPUT_NAME}", mix, "_truth", tags=TAGS, cover=cover)
    o.audio("audio/mix.flac", mix, "ingest")
    o.audio("audio/preview.opus", mix, "ingest", codec="opus", in_sr=S.SR, extra=["-ar", "48000"])
    audio_io.write_wav(out_dir / "_intermediate/ingest/canonical.wav", mix, S.SR, "f32")
    peak = float(np.max(np.abs(mix)))
    source = {
        "file_name": INPUT_NAME,
        "codec": "flac",
        "sample_rate": S.SR,
        "channels": 2,
        "n_samples": S.N_SAMPLES,
        "duration_s": S.DURATION,
        "pcm_sha256": _pcm_sha(mix),
        "lossless": True,
        "peak_abs": _r6(peak),
        "decode_warnings": 0,
        "tags": dict(TAGS),
        "has_cover": True,
        "palette": list(S.PALETTE),
        "soundtrack": "audio/mix.flac",
    }
    o.json("meta/source.json", source, "ingest", "mvh/files/source")
    o.json(
        "meta/identity.json",
        {
            "title": S.TITLE,
            "artist": S.ARTIST,
            "album": S.ALBUM,
            "duration_s": S.DURATION,
            "source": "tags",
            "conf": 1.0,
            "credits": [
                {"role": "composer", "name": "tests/synth generator"},
                {"role": "vocals", "name": "Microsoft David (SAPI, resynthesised)"},
                {"role": "vocals", "name": "Microsoft Zira (SAPI, resynthesised)"},
            ],
            "album_artist": S.ARTIST,
            "year": 2026,
            "isrc": None,
            "track_no": 1,
            "genre": "Synthetic",
        },
        "identity",
        "mvh/files/identity",
    )

    # ------------------------------------------------------------------ separation
    log("stems ...")
    for st in (
        "vocals",
        "lead_vocals",
        "backing_vocals",
        "drums",
        "bass",
        "guitar",
        "piano",
        "other",
        "instrumental",
    ):
        o.audio(f"stems/{st}.flac", r.tracks[st], "separate_hq")
    for sub in ("kick", "snare", "toms", "hihat", "ride", "crash"):
        o.audio(f"stems/drums/{sub}.flac", r.tracks[f"drums_{sub}"], "separate_hq")
    sep_models = [
        {"id": "fixture.generator", "licence": "synthetic (tests/synth): the stems are the generator tracks"}
    ]
    stems_map = {
        st: {"model": "fixture.generator", "file": f"stems/{st}.flac"}
        for st in (
            "vocals",
            "lead_vocals",
            "backing_vocals",
            "drums",
            "bass",
            "guitar",
            "piano",
            "other",
            "instrumental",
        )
    }
    stems_map.update(
        {
            f"drums_{s}": {"model": "fixture.generator", "file": f"stems/drums/{s}.flac"}
            for s in ("kick", "snare", "toms", "hihat", "ride", "crash")
        }
    )
    o.json(
        "meta/separation.json",
        {
            "variant": "rocm",
            "degraded": False,
            "lead_backing_split": True,
            "stems": stems_map,
            "models": sep_models,
            "invariants": {"sum_error_db": -120.0, "gain_db": {k: 0.0 for k in stems_map}},
        },
        "separate_hq",
        "mvh/files/separation",
    )
    fast = {
        "vocals": r.tracks["vocals"],
        "drums": r.tracks["drums"],
        "bass": r.tracks["bass"],
        "other": r.tracks["guitar"] + r.tracks["piano"] + r.tracks["other"],
    }
    for k, v in fast.items():
        audio_io.write_wav(out_dir / f"_intermediate/separate_fast/fast/{k}.wav", v, S.SR, "f32")
    o.json(
        "_intermediate/separate_fast/fast/separation.json",
        {
            "variant": "fast",
            "degraded": False,
            "lead_backing_split": False,
            "stems": {k: {"model": "fixture.generator", "file": f"fast/{k}.wav"} for k in fast},
            "models": [
                {
                    "id": "fixture.generator",
                    "licence": "synthetic (tests/synth): exact generator sums, no bleed",
                }
            ],
        },
        "separate_fast",
        "mvh/files/separation",
    )

    # ------------------------------------------------------------------ spectral (measured + event-driven)
    log("spectral ...")
    P, freqs = A.stft_power(mono, fr)
    from mvh.contract.registry import FINE_BANDS, KICK_BAND, VIZ_BANDS

    for b, (lo, hi) in VIZ_BANDS.items():
        db = A.band_db(P, freqs, lo, hi)
        ch[f"bands.{b}_db"] = db
        ch[f"bands.{b}"], l_, h_ = A.pnorm(db)
        cmeta[f"bands.{b}"] = {"lo": l_, "hi": h_}
    kdb = A.band_db(P, freqs, *KICK_BAND)
    ch["bands.kick_db"] = kdb
    ch["bands.kick"], l_, h_ = A.pnorm(kdb)
    cmeta["bands.kick"] = {"lo": l_, "hi": h_}
    for b, (lo, hi) in FINE_BANDS.items():
        db = A.band_db(P, freqs, lo, hi)
        ch[f"fine.{b}_db"] = db
        ch[f"fine.{b}"], l_, h_ = A.pnorm(db)
        cmeta[f"fine.{b}"] = {"lo": l_, "hi": h_}
    V, edges = A.viz_bands(P, freqs)
    fc = np.sqrt(edges[:-1] * edges[1:])
    for b, (lo, hi) in VIZ_BANDS.items():
        ch[f"bands.{b}_viz"] = V[:, (fc >= lo) & (fc < hi)].mean(axis=1)
    ch["bands.level"] = V.mean(axis=1)
    spec_u8 = np.round(V * 255).astype(np.uint8)
    for b, (lo, hi) in VIZ_BANDS.items():
        fl = A.flux(P, freqs, lo, hi)
        ch[f"flux.{b}"], l_, h_ = A.pnorm(fl)
        cmeta[f"flux.{b}"] = {"lo": l_, "hi": h_}
    tb = A.timbre(P, freqs)
    ch["timbre.centroid_hz"] = tb["centroid_hz"]
    ch["timbre.centroid"], l_, h_ = A.pnorm(tb["centroid_hz"])
    cmeta["timbre.centroid"] = {"lo": l_, "hi": h_}
    ch["timbre.rolloff_hz"] = tb["rolloff_hz"]
    ch["timbre.rolloff"], l_, h_ = A.pnorm(tb["rolloff_hz"])
    cmeta["timbre.rolloff"] = {"lo": l_, "hi": h_}
    ch["timbre.flatness"] = tb["flatness"]
    ch["timbre.slope_db_oct"] = tb["slope_db_oct"]
    stv = A.stereo(mix, fr)
    ch["stereo.width"], ch["stereo.balance"], ch["stereo.correlation"] = (
        stv["width"],
        stv["balance"],
        stv["correlation"],
    )

    # hit events from the truth drum hits (spectral's band hit detectors would fire on these one-shots)
    hits_def = {"kick": ("kick",), "mid": ("snare", "tom"), "high": ("hat", "cymbal")}
    band_for = {"kick": ch["bands.kick_db"], "mid": ch["bands.mid_db"], "high": ch["bands.high_db"]}
    for hname, drums_ in hits_def.items():
        evs = [h for h in r.drum_hits if h["drum"] in drums_]
        items, env_ev = [], []
        for h in evs:
            i = min(n - 1, int(round(h["t"] * 100)))
            j = min(n - 1, i + 2)
            items.append(
                {
                    "t": h["t"],
                    "t_peak": _r6(h["t"] + 0.005),
                    "strength": _f(h["vel"] / 0.85),
                    "db": _f(float(np.max(band_for[hname][i : j + 1])), 2),
                }
            )
            env_ev.append((h["t"], min(1.5, h["vel"])))  # peak 0.85 * strength = vel
        o.events(
            f"hits.{hname}",
            items,
            "spectral",
            "fixture",
            notes=[
                f"hits.{hname} = truth one-shot onsets of {', '.join(drums_)} (t = first sample); db measured"
            ],
        )
        ch[f"hits.{hname}"] = A.flash_envelope(n, env_ev, 0.18)
        ch[f"hits.{hname}_raw"] = A.flash_envelope(n, env_ev, 0.03)
    onset_src = {
        "bass": [(h["t"], h["vel"]) for h in r.drum_hits if h["drum"] == "kick"]
        + [(x["t"], x["vel"]) for x in r.notes["bass"]],
        "mid": [(h["t"], h["vel"]) for h in r.drum_hits if h["drum"] in ("snare", "tom")]
        + [(x["t"], x["vel"]) for x in r.notes["piano"]]
        + [(w["t"], 0.8) for w in r.words]
        + [(x["t"], x["vel"]) for x in r.notes["other"]],
        "high": [(h["t"], h["vel"]) for h in r.drum_hits if h["drum"] in ("hat", "cymbal")],
    }
    for b, lst in onset_src.items():
        merged: dict[float, float] = {}
        for t, v in lst:
            merged[t] = max(merged.get(t, 0.0), v)
        items = [{"t": t, "strength": _f(min(1.0, v))} for t, v in sorted(merged.items())]
        o.events(
            f"onsets.{b}",
            items,
            "spectral",
            "fixture",
            notes=[
                f"onsets.{b} = truth onsets of every source with energy in the {b} band (deduplicated by time)"
            ],
        )
    truth["onsets"] = {b: sorted({t for t, _ in lst}) for b, lst in onset_src.items()}

    # ------------------------------------------------------------------ loudness
    log("loudness ...")
    lc = A.loudness_curves(mix, fr)
    for name in ("momentary_lufs", "short_term_lufs"):
        ch[f"loud.{name}"] = lc[name]
        base = name.rsplit("_", 1)[0]
        ch[f"loud.{base}"], l_, h_ = A.pnorm(lc[name])
        cmeta[f"loud.{base}"] = {"lo": l_, "hi": h_}
    rms_mix, pk_mix = A.rms_peak_db(mix, fr)
    ch["loud.rms_db"] = rms_mix
    ch["loud.rms"], l_, h_ = A.pnorm(rms_mix)
    cmeta["loud.rms"] = {"lo": l_, "hi": h_}
    ch["loud.peak_db"] = pk_mix
    ch["loud.crest_db"] = np.where(rms_mix > A.DB_FLOOR, np.clip(pk_mix - rms_mix, 0, 60), 0.0)
    il = A.integrated_and_lra(mix, S.SR)
    tp = A.true_peak_db(mix)
    sp = float(20 * np.log10(peak))
    loud = {
        "integrated_lufs": _f(il["integrated_lufs"], 3),
        "lra_lu": _f(il["lra_lu"], 3),
        "lra_low_lufs": _f(il["lra_low_lufs"], 3),
        "lra_high_lufs": _f(il["lra_high_lufs"], 3),
        "true_peak_dbtp": _f(tp, 3),
        "sample_peak_db": _f(sp, 3),
        "plr_db": _f(tp - il["integrated_lufs"], 3),
        "clipped_samples": 0,
        "curve_offsets_s": {"momentary": 0.0, "short_term": 0.0},
    }
    o.json("meta/loudness.json", loud, "loudness", "mvh/files/loudness")
    integ = il["integrated_lufs"]

    # ------------------------------------------------------------------ rhythm
    log("rhythm ...")
    acc = T.accents(r.drum_hits, r.words)
    beats = T.beats()
    for b in beats:
        bi = b["beat_index"]
        b["strength"] = 0.0 if not b["in_pulse"] else (0.95 if b["beat_in_bar"] == 1 else 0.85)
        b["conf"] = 1.0 if b["in_pulse"] else 0.5
    o.events(
        "beats",
        beats,
        "rhythm",
        "fixture",
        notes=[
            "beat times exact (programmed grid, 120 BPM); strength/conf are synthetic tracker-like values"
        ],
    )
    bars = T.bars()
    o.events(
        "bars",
        [
            {k: v for k, v in b.items() if k != "swing"} | {"conf": 1.0 if b["in_pulse"] else 0.5}
            for b in bars
        ],
        "rhythm",
        "fixture",
    )
    o.events(
        "tempo_segments", [{"t": 0.0, "d": S.DURATION, "bpm": S.BPM, "stable": True}], "rhythm", "fixture"
    )
    o.events(
        "pulse_regions",
        [{"t": a, "d": _r6(b - a), "in_pulse": p} for a, b, p in S.PULSE_REGIONS],
        "rhythm",
        "fixture",
    )
    o.json(
        "meta/tempo.json",
        {
            "bpm": S.BPM,
            "confidence": 0.95,
            "feel": "normal",
            "is_variable": False,
            "candidates": [
                {"bpm": 120.0, "score": 1.0, "relation": "x1"},
                {"bpm": 60.0, "score": 0.35, "relation": "x0.5"},
                {"bpm": 240.0, "score": 0.2, "relation": "x2"},
                {"bpm": 80.0, "score": 0.1, "relation": "x0.667"},
                {"bpm": 180.0, "score": 0.08, "relation": "x1.5"},
            ],
            "meter": {
                "time_signature": "4/4",
                "beats_per_bar": 4,
                "confidence": 0.9,
                "changes": [
                    {"t": S.BAR[16].t, "bar": 16, "beats_per_bar": 3},
                    {"t": S.BAR[17].t, "bar": 17, "beats_per_bar": 4},
                ],
            },
            "qa": {"beat_agreement_f": 1.0, "downbeat_agreement_f": 1.0, "flags": []},
            "estimates": {"beat_this": 120.0, "allin1": 120.0, "librosa": 120.0},
            "agreement": "agree",
        },
        "rhythm",
        "mvh/files/tempo",
    )
    ch["tempo.bpm"] = np.full(n, S.BPM)
    ch["rhythm.beat_act"] = A.flash_envelope(
        n, [(b["t"], b["strength"]) for b in beats if b["in_pulse"]], 0.05
    )
    ch["rhythm.downbeat_act"] = A.flash_envelope(
        n, [(b["t"], 0.95) for b in beats if b["in_pulse"] and b["beat_in_bar"] == 1], 0.05
    )
    ip = np.zeros(n)
    for a, b, p in S.PULSE_REGIONS:
        if p:
            ip[(fr.t >= a) & (fr.t < b)] = 1.0
    ch["rhythm.in_pulse"] = ip

    # ------------------------------------------------------------------ allin1 intermediates (synthetic model outputs)
    log("allin1 ...")
    labels10 = ["start", "end", "intro", "outro", "break", "bridge", "inst", "solo", "verse", "chorus"]
    sec_lab = {"intro": "intro", "verse": "verse", "chorus": "chorus", "bridge": "bridge", "outro": "outro"}
    act = np.zeros((n, 3 + len(labels10)), dtype=np.float32)
    act[:, 0] = ch["rhythm.beat_act"]
    act[:, 1] = ch["rhythm.downbeat_act"]
    for s in S.SECTIONS:
        i = int(round(s.t * 100))
        act[max(0, i - 3) : i + 4, 2] = np.exp(-0.5 * ((np.arange(max(0, i - 3), i + 4) - i) / 1.5) ** 2)
        m = (fr.t >= s.t) & (fr.t < s.end)
        li = labels10.index(sec_lab[s.label])
        act[m, 3:] = 0.02
        act[m, 3 + li] = 0.8
    act[fr.t < S.SECTIONS[0].t, 3 + labels10.index("start")] = 0.9
    a1 = out_dir / "_intermediate/allin1"
    a1.mkdir(parents=True, exist_ok=True)
    audio_io.atomic_bytes(a1 / "activations.f32", np.ascontiguousarray(act).astype("<f4").tobytes())
    g = np.random.default_rng(S.SEED + 11)
    emb = np.zeros((n, 24), dtype=np.float32)
    proto = {grp: g.standard_normal(24) for grp in sorted({s.repeat_group for s in S.SECTIONS})}
    for s in S.SECTIONS:
        m = (fr.t >= s.t) & (fr.t < s.end)
        emb[m] = proto[s.repeat_group]
    emb += (0.1 * g.standard_normal(emb.shape)).astype(np.float32)
    audio_io.atomic_bytes(a1 / "embeddings.f32", np.ascontiguousarray(emb).astype("<f4").tobytes())
    inpulse_beats = [b for b in beats if b["in_pulse"]]
    o.json(
        "_intermediate/allin1/allin1.json",
        {
            "bpm": S.BPM,
            "beats": [b["t"] for b in inpulse_beats],
            "downbeats": [b["t"] for b in inpulse_beats if b["beat_in_bar"] == 1],
            "beat_positions": [b["beat_in_bar"] for b in inpulse_beats],
            "segments": [{"start": 0.0, "end": S.SECTIONS[0].t, "label": "start"}]
            + [{"start": s.t, "end": s.end, "label": sec_lab[s.label]} for s in S.SECTIONS],
            "labels": labels10,
            "activations": {
                "file": "activations.f32",
                "rate_hz": 100,
                "columns": ["beat", "downbeat", "boundary", *labels10],
                "frames": n,
            },
            "embeddings": {"file": "embeddings.f32", "rate_hz": 100, "dim": 24, "frames": n},
        },
        "allin1",
        "mvh/intermediate/allin1",
    )

    # ------------------------------------------------------------------ harmony
    log("harmony ...")
    o.events("key", [{"t": 0.0, "d": S.DURATION, **S.KEY, "conf": 0.9, "agree": True}], "harmony", "fixture")
    o.json(
        "meta/key.json",
        {
            "global": {**S.KEY, "conf": 0.9},
            "agreement": "agree",
            "flags": [],
            "methods": {"fixture": {"key": S.KEY["key"]}},
        },
        "harmony",
        "mvh/files/key",
    )
    chords = T.chords()
    o.events("chords", chords, "harmony", "fixture")
    chroma = np.zeros((n, 12))
    for src in ("bass", "other", "piano", "vocals"):
        for x in r.notes[src]:
            m = (fr.t >= x["t"]) & (fr.t < x["t"] + x["d"])
            chroma[m, x["midi"] % 12] += x["vel"]
    for x in r.backing_words:
        m = (fr.t >= x["t"]) & (fr.t < x["t"] + x["d"])
        chroma[m, x["midi"] % 12] += 0.6
    mx = chroma.max(axis=1, keepdims=True)
    chroma = np.where(mx > 0, chroma / np.maximum(mx, 1e-12), 0.0)
    for pc in range(12):
        ch[f"chroma.{pc}"] = chroma[:, pc]

    # ------------------------------------------------------------------ dynamics
    log("dynamics ...")
    st = lc["short_term_lufs"]
    mom = lc["momentary_lufs"]

    def mean_lufs(t0, t1, guard=0.2):
        m = (fr.t >= t0 + guard) & (fr.t < t1 - guard)  # windows fully inside the segment (momentary = 0.4 s)
        if not m.any():
            m = (fr.t >= t0) & (fr.t < t1)
        v = mom[m]
        e = np.mean(10 ** (v / 10)) if v.size else 1e-7
        return float(10 * np.log10(e)) if e > 0 else A.LUFS_FLOOR

    def level_of(rel, abs_):
        if abs_ <= -60:
            return "silence"
        return (
            "quiet"
            if rel < -12
            else "soft"
            if rel < -6
            else "medium"
            if rel < -2
            else "loud"
            if rel < 1.5
            else "peak"
        )

    dyn_bounds = (
        [0.0, S.SECTIONS[0].t]
        + [s.t for s in S.SECTIONS[1:4]]
        + [S.BAR[17].t, S.BAR[18].t, S.SECTIONS[5].t, S.DURATION]
    )
    dyn_items = []
    for a, b in zip(dyn_bounds[:-1], dyn_bounds[1:]):
        ml = mean_lufs(a, b)
        rel = ml - integ
        dyn_items.append(
            {
                "t": a,
                "d": _r6(b - a),
                "level": level_of(rel, ml),
                "rel_lu": _f(rel, 2),
                "mean_lufs": _f(ml, 2),
                "conf": 0.9,
            }
        )
    o.events(
        "dynamics",
        dyn_items,
        "dynamics",
        "measured",
        notes=[
            "boundaries = section starts + the silent bar (truth); levels measured (momentary LUFS energy mean vs integrated; "
            "thresholds quiet<-12, soft<-6, medium<-2, loud<+1.5 LU, else peak; silence below -60 LUFS)"
        ],
    )
    impacts = []
    for i, bar in enumerate((9, 18, 27), start=1):
        t = S.BAR[bar].t
        before, after = mean_lufs(t - 0.5, t, 0.0), mean_lufs(t, t + 0.5, 0.0)
        bi = int(round(t * 100))
        bb = float(
            np.mean(ch["bands.bass_db"][bi : bi + 50]) - np.mean(ch["bands.bass_db"][max(0, bi - 50) : bi])
        )
        impacts.append(
            {
                "id": f"I{i:03d}",
                "t": t,
                "strength": {9: 0.7, 18: 1.0, 27: 0.8}[bar],
                "delta_lu": _f(after - before, 2),
                "delta_bass_db": _f(bb, 2),
                "bar": bar,
            }
        )
    o.events(
        "impacts",
        impacts,
        "dynamics",
        "fixture",
        notes=["impact times = programmed crash+kick entries (bars 9, 18, 27); deltas measured"],
    )
    stop = {"id": "X001", "t": S.BAR[17].t, "strength": 1.0, "gap_s": 2.0}
    o.events(
        "stops",
        [stop],
        "dynamics",
        "fixture",
        notes=["hard cut to digital silence at the end of the 3/4 bar"],
    )
    silence = {"id": "Z001", "t": S.BAR[17].t, "d": 2.0, "depth_db": _f(integ - A.LUFS_FLOOR, 2)}
    o.events(
        "silences",
        [silence],
        "dynamics",
        "fixture",
        notes=["the only silence >= 1 s (the 0.5 s pre-roll before the pickup is below the 1 s minimum)"],
    )
    decay = {"id": "Y001", "t": S.BAR[27].t, "d": _r6(S.DURATION - S.BAR[27].t), "strength": 0.8}
    o.events(
        "decay_tails",
        [decay],
        "dynamics",
        "fixture",
        notes=["final hit (crash, kick, held A minor chord) ringing out to the end"],
    )
    stn, _, _ = A.pnorm(st)
    dens = A.flash_envelope(n, [(h["t"], 1.0) for h in r.drum_hits], 0.25)
    dens = np.convolve(dens, np.ones(100) / 100, mode="same")
    ch["dyn.intensity"] = np.clip(
        0.6 * stn + 0.25 * ch["bands.bass"] + 0.15 * np.clip(dens / max(dens.max(), 1e-9), 0, 1), 0, 1
    )
    nov = np.zeros(n)
    for s in S.SECTIONS:
        nov = np.maximum(
            nov, np.exp(-0.5 * ((fr.t - s.t) / 0.25) ** 2) * (1.0 if s.id in ("S03", "S05") else 0.8)
        )
    nov = np.maximum(nov, np.exp(-0.5 * ((fr.t - S.BAR[17].t) / 0.25) ** 2) * 0.9)
    ch["dyn.novelty"] = nov

    # ------------------------------------------------------------------ structure
    log("structure ...")
    sec_items = []
    for s in S.SECTIONS:
        lp = {s.label: 0.85, **{lab: 0.05 for lab in ("verse", "chorus", "bridge") if lab != s.label}}
        sec_items.append(
            {
                "id": s.id,
                "t": s.t,
                "d": s.d,
                "label": s.label,
                "occurrence": s.occurrence,
                "occurrence_label": s.occurrence_label,
                "repeat_group": s.repeat_group,
                "start_bar": s.start_bar,
                "n_bars": s.n_bars,
                "label_probs": lp,
                "conf": 0.9,
                "boundary_conf": 0.95,
            }
        )
    o.events(
        "sections",
        sec_items,
        "structure",
        "fixture",
        notes=["label_probs/conf synthetic; boundaries, labels, bars exact"],
    )
    o.events(
        "phrases",
        [
            {
                "id": p.id,
                "t": S.BAR[p.start_bar].t,
                "d": _r6(S.BAR[p.start_bar + p.n_bars - 1].end - S.BAR[p.start_bar].t),
                "start_bar": p.start_bar,
                "n_bars": p.n_bars,
                "section_id": p.section_id,
            }
            for p in S.PHRASES
        ],
        "structure",
        "fixture",
    )
    roles = []
    for rid, role, sb, nb, sid in S.EDM_ROLES:
        roles.append(
            {
                "id": rid,
                "t": S.BAR[sb].t,
                "d": _r6(S.BAR[sb + nb - 1].end - S.BAR[sb].t),
                "role": role,
                "start_bar": sb,
                "n_bars": nb,
                "section_id": sid,
                "conf": 0.95,
                "evidence": ["snare roll", "riser", "stop"]
                if role == "build"
                else ["impact I002", "four-on-the-floor kick"],
            }
        )
    o.events("edm_roles", roles, "structure", "fixture")
    groups: dict[str, list[str]] = {}
    for s in S.SECTIONS:
        groups.setdefault(s.repeat_group, []).append(s.id)
    o.json(
        "meta/structure.json",
        {
            "repeat_groups": {
                g_: {
                    "label": next(s.label for s in S.SECTIONS if s.repeat_group == g_),
                    "section_ids": ids,
                    "similarity": 1.0 if len(ids) > 1 else 0.0,
                }
                for g_, ids in groups.items()
            },
            "phrase_bars": 4,
            "n_sections": len(S.SECTIONS),
        },
        "structure",
        "mvh/files/structure",
    )

    # ------------------------------------------------------------------ stem activity
    log("stem activity ...")
    stem_names = [
        "vocals",
        "lead_vocals",
        "backing_vocals",
        "drums",
        "bass",
        "guitar",
        "piano",
        "other",
        "instrumental",
    ]
    sub_names = [f"drums_{s}" for s in ("kick", "snare", "toms", "hihat", "ride", "crash")]
    pooled = []
    stem_rms = {}
    for st_ in stem_names + sub_names:
        rms_s, pk_s = A.rms_peak_db(r.tracks[st_], fr)
        stem_rms[st_] = (rms_s, pk_s)
        pooled.append(rms_s[rms_s > A.DB_FLOOR])
    pool = np.concatenate([p for p in pooled if p.size])
    plo, phi = float(np.percentile(pool, 2)), float(np.percentile(pool, 99.5))
    sa_items = []
    stems_meta = {}
    mix_e = float(np.sum(mix**2))
    for st_ in stem_names + sub_names:
        rms_s, pk_s = stem_rms[st_]
        rel = np.where(rms_s > A.DB_FLOOR, np.clip(rms_s - rms_mix, A.DB_FLOOR, 12.0), A.DB_FLOOR)
        act_ = A.activity(rms_s, rel)
        ch[f"stem.{st_}.rms_db"] = rms_s
        ch[f"stem.{st_}.level"] = np.where(
            rms_s > A.DB_FLOOR, np.clip((rms_s - plo) / (phi - plo), 0, 1), 0.0
        )
        cmeta[f"stem.{st_}.level"] = {"lo": plo, "hi": phi}
        ch[f"stem.{st_}.rel_db"] = rel
        ch[f"stem.{st_}.active"] = act_.astype(np.float64)
        for t0, d0 in A.segments(act_):
            m = (fr.t >= t0) & (fr.t < t0 + d0)
            sa_items.append(
                {
                    "t": t0,
                    "d": d0,
                    "stem": st_,
                    "mean_db": _f(10 * np.log10(np.mean(10 ** (rms_s[m] / 10))), 2),
                }
            )
        e = float(np.sum(r.tracks[st_] ** 2))
        stems_meta[st_] = {
            "present": bool(act_.mean() > 0.01),
            "active_ratio": _f(act_.mean()),
            "median_rms_db": _f(np.median(rms_s[act_]) if act_.any() else A.DB_FLOOR, 2),
            "peak_db": _f(20 * np.log10(max(np.max(np.abs(r.tracks[st_])), 1e-6)), 2),
            "share_of_mix_db": _f(10 * np.log10(e / mix_e) if e > 0 else A.DB_FLOOR, 2),
        }
    sa_items.sort(key=lambda x: (x["t"], (stem_names + sub_names).index(x["stem"])))
    o.events(
        "stem_activity",
        sa_items,
        "stem_activity",
        "measured",
        notes=[
            "activity rule applied to the exact generator stems (> -45 dBFS, within 18 dB of the mix, 300/500 ms)"
        ],
    )
    o.json(
        "meta/stems.json",
        {
            "stems": stems_meta,
            "thresholds": {"active_db": -45.0, "within_db": 18.0, "attack_ms": 300.0, "release_ms": 500.0},
        },
        "stem_activity",
        "mvh/files/stems",
    )

    # ------------------------------------------------------------------ drums
    log("drums ...")
    dh_items = []
    for h in r.drum_hits:
        i = min(n - 1, int(round(h["t"] * 100)))
        lvl = float(np.max(stem_rms[f"drums_{h['sub']}"][0][i : i + 3]))
        dh_items.append(
            {
                "t": h["t"],
                "drum": h["drum"],
                "vel": h["vel"],
                "level_db": _f(lvl, 2),
                "conf": 1.0,
                "source": "drumsep",
                "sub_stem": h["sub"],
            }
        )
    o.events(
        "drum_hits",
        dh_items,
        "drums",
        "fixture",
        fields={"sub_stem": {"unit": None, "type": "string"}},
        notes=[
            "truth: every one-shot (t = its first sample); vel = programmed velocity; level_db measured on its sub-stem"
        ],
    )
    for d in ("kick", "snare", "hat", "tom", "cymbal", "perc"):
        ch[f"drums.{d}"] = A.flash_envelope(
            n, [(h["t"], h["vel"]) for h in r.drum_hits if h["drum"] == d], 0.1
        )

    # ------------------------------------------------------------------ instruments
    log("instruments ...")
    n1 = int(np.ceil(S.N_SAMPLES / S.SR))
    inst_act = {}
    for slug, x in r.inst_tracks.items():
        rms_i, _ = A.rms_peak_db(x, fr)
        inst_act[slug] = rms_i > -50.0
    inst_items = []
    stem_of = {
        "drums": "drums",
        "bass": "bass",
        "synth_pad": "other",
        "synth_fx": "other",
        "piano": "piano",
        "voice": "vocals",
    }
    for slug, m in inst_act.items():
        a_ = A.activity(np.where(m, 0.0, -120.0), np.zeros(n), attack_ms=300, release_ms=500)
        for t0, d0 in A.segments(a_):
            inst_items.append(
                {
                    "t": t0,
                    "d": d0,
                    "instrument": slug,
                    "conf": 0.9,
                    "evidence": "both" if slug in ("synth_pad", "synth_fx") else "stem",
                    "stem": stem_of[slug],
                }
            )
        frac = np.array([m[(fr.t >= i - 2.0) & (fr.t < i + 2.0)].mean() for i in range(n1)])
        ch[f"inst.{slug}"] = np.round(0.04 + 0.92 * frac, 4)
    inst_items.sort(key=lambda x: (x["t"], x["instrument"]))
    o.events(
        "instruments",
        inst_items,
        "instruments",
        "synthetic",
        notes=[
            "segments from the generator tracks' activity (> -50 dBFS); conf and 1 Hz probabilities synthetic"
        ],
    )
    vfrac = np.array([inst_act["voice"][(fr.t >= i - 2.0) & (fr.t < i + 2.0)].mean() for i in range(n1)])
    ch["vstyle.singing"] = np.round(0.03 + 0.9 * vfrac, 4)
    ch["vstyle.speech"] = np.round(0.03 + 0.05 * vfrac, 4)
    ch["vstyle.rap"] = np.round(0.02 + 0.03 * vfrac, 4)
    vs_items = []
    for line in S.LINES:
        ws = [w for w in r.words if w["line_id"] == line.id]
        vs_items.append(
            {
                "t": ws[0]["t"],
                "d": _r6(ws[-1]["t"] + ws[-1]["d"] - ws[0]["t"]),
                "style": "singing",
                "conf": 0.9,
            }
        )
    o.events(
        "vocal_style",
        vs_items,
        "instruments",
        "fixture",
        notes=["every lead line is sung (LPC-resynthesised TTS at programmed notes)"],
    )
    total = {slug: float(m.mean()) for slug, m in inst_act.items()}
    o.json(
        "meta/instruments.json",
        {
            "summary": [
                {"instrument": k, "coverage": _f(v), "mean_conf": 0.9}
                for k, v in sorted(total.items(), key=lambda kv: -kv[1])
            ],
            "vocabulary": sorted(inst_act),
            "vocal_style": {"dominant": "singing", "shares": {"singing": 1.0, "speech": 0.0, "rap": 0.0}},
            "top_tags": [
                {"label": "Music", "p": 0.95},
                {"label": "Singing", "p": 0.7},
                {"label": "Drum machine", "p": 0.6},
            ],
        },
        "instruments",
        "mvh/files/instruments",
    )

    # ------------------------------------------------------------------ notes
    log("notes ...")
    tempo_map = [(0.0, S.BPM)]
    sigs = [(0.0, 4, 4), (S.BAR[16].t, 3, 4), (S.BAR[17].t, 4, 4)]
    nidx = {}
    for src in ("bass", "piano", "guitar", "other"):
        items = [
            {
                "t": x["t"],
                "d": x["d"],
                "midi": x["midi"],
                "name": dsp.note_name(x["midi"]),
                "vel": x["vel"],
                "conf": 1.0,
            }
            for x in r.notes[src]
        ]
        o.events(f"notes.{src}", items, "notes", "fixture", rel=f"events/notes.{src}.json")
        ms = [x["midi"] for x in r.notes[src]]
        hist = [0.0] * 12
        for m_ in ms:
            hist[m_ % 12] += 1
        tot = sum(hist) or 1.0
        midi_rel = f"notes/{src}.mid" if ms else None
        if ms:
            o.bytes(
                midi_rel,
                write_smf(
                    [(src, [(x["t"], x["d"], x["midi"], x["vel"]) for x in r.notes[src]])], tempo_map, sigs
                ),
                "notes",
                "midi",
            )
        nidx[src] = {
            "events": f"events/notes.{src}.json",
            "midi": midi_rel,
            "count": len(ms),
            "lowest": min(ms) if ms else None,
            "highest": max(ms) if ms else None,
            "pc_histogram": [round(h / tot, 4) for h in hist],
            "density_per_s": _f(len(ms) / S.DURATION),
        }
    o.bytes(
        "notes/notes.mid",
        write_smf(
            [
                (s_, [(x["t"], x["d"], x["midi"], x["vel"]) for x in r.notes[s_]])
                for s_ in ("bass", "piano", "guitar", "other")
            ],
            tempo_map,
            sigs,
        ),
        "notes",
        "midi",
    )
    o.json(
        "notes/notes.json",
        {
            "sources": nidx,
            "tempo_map": "constant 120 BPM from the beat grid; time signatures 4/4, 3/4 at bar 16, "
            "4/4 at bar 17; PPQ 480; t = 0 is the first sample of audio/mix.flac",
        },
        "notes",
        "mvh/files/notes_index",
    )

    # ------------------------------------------------------------------ vocals
    log("vocals ...")
    lead = T.lead_notes(r.words)
    o.events(
        "notes.vocals",
        [
            {
                "t": x["t"],
                "d": x["d"],
                "midi": x["midi"],
                "name": dsp.note_name(x["midi"]),
                "vel": x["vel"],
                "conf": 1.0,
            }
            for x in lead
        ],
        "vocals",
        "fixture",
        rel="events/notes.vocals.json",
        notes=["one note per sung word of the lead voice (V1, or V2 in its call-and-response lines)"],
    )
    o.bytes(
        "notes/vocals.mid",
        write_smf([("vocals", [(x["t"], x["d"], x["midi"], x["vel"]) for x in lead])], tempo_map, sigs),
        "vocals",
        "midi",
    )
    vph = T.vocal_phrases(r.words)
    lv = r.tracks["lead_vocals"]
    lv_rms, _ = A.rms_peak_db(lv, fr)
    for p in vph:
        m = (fr.t >= p["t"]) & (fr.t < p["t"] + p["d"])
        p["mean_db"] = _f(10 * np.log10(np.mean(10 ** (lv_rms[m] / 10))), 2)
    o.events(
        "vocal_phrases",
        [{k: v for k, v in p.items() if k not in ("line_id", "voice")} for p in vph],
        "vocals",
        "fixture",
    )
    midi_c = r.f0_midi[np.clip(fr.centres, 0, S.N_SAMPLES - 1)]
    ch["vocal.midi"] = midi_c
    ch["vocal.f0_hz"] = np.where(np.isfinite(midi_c), 440.0 * 2 ** ((midi_c - 69) / 12), np.nan)
    voiced = np.isfinite(midi_c)
    ch["vocal.voiced"] = voiced.astype(np.float64)
    ch["vocal.conf"] = np.where(voiced, 0.95, 0.05)
    vm = midi_c[voiced]
    p2, p98, p10, p90 = (float(np.percentile(vm, q)) for q in (2, 98, 10, 90))
    pitch = np.zeros(n)
    last = None
    idx_v = np.nonzero(voiced)[0]
    for i in range(n):
        if voiced[i]:
            last = (midi_c[i] - p2) / (p98 - p2)
            pitch[i] = last
        else:
            nxt = idx_v[idx_v > i]
            hold = last if last is not None else ((midi_c[nxt[0]] - p2) / (p98 - p2) if nxt.size else 0.0)
            if nxt.size and nxt[0] - i <= 15 and last is not None:
                tgt = (midi_c[nxt[0]] - p2) / (p98 - p2)
                w_ = 1.0 - (nxt[0] - i) / 15.0
                hold = hold + (tgt - hold) * w_
            pitch[i] = hold
    ch["vocal.pitch01"] = np.clip(pitch, 0, 1)
    cmeta["vocal.pitch01"] = {"lo": p2, "hi": p98}
    # lowest / highest sustained notes (programmed notes held >= 0.4 s)
    sus = [x for x in lead if x["d"] >= 0.4]
    lo_n = min(sus, key=lambda x: (x["midi"], x["t"]))
    hi_n = max(sus, key=lambda x: (x["midi"], -x["t"]))

    def nstat(x):
        return {
            "midi": x["midi"],
            "name": dsp.note_name(x["midi"]),
            "hz": _f(440.0 * 2 ** ((x["midi"] - 69) / 12), 2),
            "t": x["t"],
        }

    o.json(
        "meta/vocal_range.json",
        {
            "present": True,
            "voiced_s": _f(voiced.sum() / 100.0, 2),
            "lowest": nstat(lo_n),
            "highest": nstat(hi_n),
            "p2": _f(p2, 3),
            "p98": _f(p98, 3),
            "p10": _f(p10, 3),
            "p90": _f(p90, 3),
            "median_midi": _f(np.median(vm), 3),
            "span_semitones": _f(p98 - p2, 3),
            "register": "tenor",
            "conf": 0.6,
        },
        "vocals",
        "mvh/files/vocal_range",
    )

    # ------------------------------------------------------------------ mood (synthetic)
    log("mood ...")
    inten1 = np.array([ch["dyn.intensity"][(fr.t >= i - 2.0) & (fr.t < i + 2.0)].mean() for i in range(n1)])
    ch["mood.arousal"] = np.round(0.2 + 0.65 * inten1, 4)
    ch["mood.valence"] = np.round(0.32 + 0.12 * inten1, 4)
    tags = {
        "energetic": 0.15 + 0.7 * inten1,
        "dark": 0.45 - 0.1 * inten1,
        "epic": 0.1 + 0.6 * inten1**2,
        "melancholic": 0.4 - 0.15 * inten1,
        "dreamy": 0.35 - 0.2 * inten1,
    }
    for k, v in tags.items():
        ch[f"mood.tag.{k}"] = np.round(np.clip(v, 0, 1), 4)
    mood_items = []
    for s in S.SECTIONS:
        m = (np.arange(n1) >= s.t) & (np.arange(n1) < s.end)
        top = sorted(tags, key=lambda k: -float(np.mean(ch[f"mood.tag.{k}"][m])))[:3]
        mood_items.append(
            {
                "t": s.t,
                "d": s.d,
                "section_id": s.id,
                "valence": _f(np.mean(ch["mood.valence"][m])),
                "arousal": _f(np.mean(ch["mood.arousal"][m])),
                "valence_conf": 0.4,
                "arousal_conf": 0.7,
                "tags": top,
            }
        )
    o.events(
        "mood",
        mood_items,
        "mood",
        "synthetic",
        notes=["valence/arousal follow the measured intensity; tags invented"],
    )
    gtags = sorted(({"tag": k, "p": _f(np.mean(v))} for k, v in tags.items()), key=lambda d: -d["p"])
    o.json(
        "meta/mood.json",
        {
            "global": {
                "valence": _f(np.mean(ch["mood.valence"])),
                "arousal": _f(np.mean(ch["mood.arousal"])),
                "valence_conf": 0.4,
                "arousal_conf": 0.7,
                "tags": gtags,
            },
            "models": ["fixture.synthetic"],
        },
        "mood",
        "mvh/files/mood",
    )

    # ------------------------------------------------------------------ lyrics
    log("lyrics ...")
    words_by_line = {line.id: [w for w in r.words if w["line_id"] == line.id] for line in S.LINES}
    lines = []
    for line in S.LINES:
        ws = words_by_line[line.id]
        lines.append(
            {
                "id": line.id,
                "t": ws[0]["t"],
                "d": _r6(ws[-1]["t"] + ws[-1]["d"] - ws[0]["t"]),
                "text": line.text,
                "section_id": line.section_id,
                "text_group": line.text_group,
                "repeat_group": line.repeat_group,
                "conf": 0.95,
                "grade": "A",
                "first_word": ws[0]["id"],
                "n_words": len(ws),
                "backing": False,
                "speaker_hint": None,
                "timing_source": "user",
            }
        )
    lyr = {
        "schema": "mvh/files/lyrics",
        "schema_version": CONTRACT_VERSION,
        "provenance": prov("lyrics", "fixture"),
        "source": {"kind": "user", "lrclib_id": None, "duration_diff_s": None, "has_word_sync": True},
        "instrumental": False,
        "language": "en",
        "grade": "A",
        "lyrics_match_score": 1.0,
        "coverage": 1.0,
        "lines": lines,
        "words": [
            {
                "id": w["id"],
                "line_id": w["line_id"],
                "t": w["t"],
                "d": w["d"],
                "text": w["text"],
                "conf": 0.95,
            }
            for w in r.words
        ],
    }
    lyr = json.loads(json.dumps(lyr), parse_float=lambda s: round(float(s), 6))
    o.json("lyrics/lyrics.json", lyr, "lyrics", "mvh/files/lyrics")
    lrc = [
        f"[ti:{S.TITLE}]",
        f"[ar:{S.ARTIST}]",
        f"[al:{S.ALBUM}]",
        f"[length:{int(S.DURATION // 60):02d}:{S.DURATION % 60:05.2f}]",
    ]
    for ln in lines:
        ws = words_by_line[ln["id"]]
        body = " ".join(f"<{_lrc_ts(w['t'])}> {w['text']}" for w in ws)
        lrc.append(f"[{_lrc_ts(ln['t'])}] {body} <{_lrc_ts(ws[-1]['t'] + ws[-1]['d'])}>")
    lrc_text = "\n".join(lrc) + "\n"
    o.text("lyrics/lyrics.lrc", lrc_text, "lyrics")
    vtt = ["WEBVTT", ""]
    srt = []
    for i, ln in enumerate(lines, start=1):
        ws = words_by_line[ln["id"]]
        end = ln["t"] + ln["d"]
        vtt += [
            ln["id"],
            f"{_vtt_ts(ln['t'])} --> {_vtt_ts(end)}",
            " ".join(f"<{_vtt_ts(w['t'])}>{w['text']}" for w in ws),
            "",
        ]
        srt += [str(i), f"{_vtt_ts(ln['t'], True)} --> {_vtt_ts(end, True)}", ln["text"], ""]
    o.text("lyrics/lyrics.vtt", "\n".join(vtt), "lyrics")
    o.text("lyrics/lyrics.srt", "\n".join(srt), "lyrics")
    ass = [
        "[Script Info]",
        f"Title: {S.TITLE}",
        "ScriptType: v4.00+",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
        "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,Arial,48,&H00FFFFFF,&H000088FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,2,0,2,20,20,40,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for ln in lines:
        ws = words_by_line[ln["id"]]
        parts = []
        for k, w in enumerate(ws):
            nxt = ws[k + 1]["t"] if k + 1 < len(ws) else w["t"] + w["d"]
            parts.append(f"{{\\k{int(round((nxt - w['t']) * 100))}}}{w['text']} ")
        ass.append(
            f"Dialogue: 0,{_ass_ts(ln['t'])},{_ass_ts(ln['t'] + ln['d'])},Default,,0,0,0,,{''.join(parts).rstrip()}"
        )
    o.text("lyrics/lyrics.ass", "\n".join(ass) + "\n", "lyrics")
    o.text("_truth/lyrics_input.lrc", lrc_text, "_truth")
    o.text("_truth/lyrics_input.txt", "\n".join(ln["text"] for ln in lines) + "\n", "_truth")

    # ------------------------------------------------------------------ voices
    log("voices ...")
    spans, sing_items = [], []
    char_of = {"V1": "C1", "V2": "C2"}
    for line in S.LINES:
        ws = words_by_line[line.id]
        t0, t1 = ws[0]["t"], ws[-1]["t"] + ws[-1]["d"]
        spans.append(
            {
                "t": t0,
                "d": _r6(t1 - t0),
                "line_id": line.id,
                "first_word": ws[0]["id"],
                "last_word": ws[-1]["id"],
                "voice_id": line.voice,
                "conf": 0.9,
                "review": False,
            }
        )
        sing_items.append(
            {
                "t": t0,
                "d": _r6(t1 - t0),
                "character_id": char_of[line.voice],
                "voice_id": line.voice,
                "line_id": line.id,
                "lead_backing": "lead",
            }
        )
        if line.duet:
            bw = [w for w in r.backing_words if w["line_id"] == line.id]
            b0, b1 = bw[0]["t"], bw[-1]["t"] + bw[-1]["d"]
            spans.append(
                {
                    "t": b0,
                    "d": _r6(b1 - b0),
                    "line_id": line.id,
                    "first_word": bw[0]["id"],
                    "last_word": bw[-1]["id"],
                    "voice_id": "V2",
                    "conf": 0.75,
                    "review": False,
                }
            )
            sing_items.append(
                {
                    "t": b0,
                    "d": _r6(b1 - b0),
                    "character_id": "C2",
                    "voice_id": "V2",
                    "line_id": line.id,
                    "lead_backing": "backing",
                }
            )
    o.events(
        "voice_spans",
        spans,
        "voices",
        "fixture",
        notes=["duet lines carry two spans: the lead (V1) and the harmony (V2, backing_vocals)"],
    )
    va = []
    for v in ("V1", "V2"):
        segs = sorted((s["t"], s["t"] + s["d"]) for s in spans if s["voice_id"] == v)
        merged = []
        for a, b in segs:
            if merged and a - merged[-1][1] < 0.3:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        va += [{"t": a, "d": _r6(b - a), "voice_id": v} for a, b in merged]
    va.sort(key=lambda x: (x["t"], x["voice_id"]))
    o.events("voice_activity", va, "voices", "fixture")
    o.json(
        "meta/voices.json",
        {
            "n_voices": 2,
            "method": "fixture truth (ECAPA + agglomerative in production)",
            "n_source": "intent",
            "voices": [
                {
                    "id": v,
                    "seconds": _f(sum(x["d"] for x in va if x["voice_id"] == v), 3),
                    "n_lines": len({s["line_id"] for s in spans if s["voice_id"] == v}),
                    "proposed_character_id": char_of[v],
                    "hint": None,
                }
                for v in ("V1", "V2")
            ],
        },
        "voices",
        "mvh/files/voices",
    )

    # ------------------------------------------------------------------ lipsync
    log("lipsync ...")
    mouth = {}
    for v in ("V1", "V2"):
        x = r.voice_tracks[v].mean(axis=0)
        env = A.env_follower(x, S.SR)  # 1 ms steps
        te = np.arange(env.size) / 1000.0
        ws = [w for w in r.words if w["voice"] == v] + ([w for w in r.backing_words] if v == "V2" else [])
        ws.sort(key=lambda w: w["t"])
        gate = np.zeros(env.size, dtype=bool)
        p95 = float(np.percentile(env[env > 0], 95)) if (env > 0).any() else 1.0
        for k, w in enumerate(ws):
            end = w["t"] + w["d"]
            nxt = ws[k + 1] if k + 1 < len(ws) else None
            if nxt is not None and nxt["line_id"] == w["line_id"]:
                end = max(end, nxt["t"])
            else:
                j = int(end * 1000)
                lim = min(env.size, j + 1500)
                while j < lim and env[j] >= p95 * 0.1:
                    j += 1
                end = max(end, j / 1000.0)
            gate[(te >= w["t"]) & (te < end)] = True
        ref = float(np.percentile(env[gate], 99)) if gate.any() else 1.0
        mo = np.clip(np.where(gate, env, 0.0) / ref, 0, 1)
        m100 = np.zeros(n)
        for i in range(n):
            a_, b_ = max(0, i * 10 - 5), min(mo.size, i * 10 + 5)
            m100[i] = mo[a_:b_].max() if b_ > a_ else 0.0
        mouth[v] = m100
        ch[f"vocal.mouth_open.{v}"] = m100
    ch["vocal.mouth_open"] = np.maximum(mouth["V1"], mouth["V2"])
    vis, phs = [], []
    vmap = {
        "P": "A",
        "B": "A",
        "M": "A",
        "F": "G",
        "V": "G",
        "L": "H",
        "W": "F",
        "UW": "F",
        "UH": "F",
        "AO": "E",
        "OW": "E",
        "ER": "E",
        "OY": "E",
        "AA": "D",
        "AY": "D",
        "AH": "D",
        "AW": "D",
        "AE": "C",
        "EH": "C",
        "EY": "C",
        "IY": "B",
        "IH": "B",
    }
    for v in ("V1", "V2"):
        ws = [w for w in r.words if w["voice"] == v] + ([w for w in r.backing_words] if v == "V2" else [])
        ws.sort(key=lambda w: w["t"])
        prev_end = 0.0
        for w in ws:
            text = next(x["text"] for x in r.words if x["id"] == w["id"])
            ph = S.ARPABET[text.lower()].split()
            wts = [3.0 if p[-1].isdigit() else 1.0 for p in ph]
            tot = sum(wts)
            if w["t"] - prev_end >= 0.1:
                vis.append(
                    {
                        "t": prev_end,
                        "d": _r6(w["t"] - prev_end),
                        "viseme": "X",
                        "voice_id": v,
                        "line_id": None,
                    }
                )
            t = w["t"]
            for p, wt in zip(ph, wts):
                d = w["d"] * wt / tot
                base = p.rstrip("012")
                phs.append({"t": _r6(t), "d": _r6(d), "phoneme": p, "voice_id": v, "word_id": w["id"]})
                vis.append(
                    {
                        "t": _r6(t),
                        "d": _r6(d),
                        "viseme": vmap.get(base, "B"),
                        "voice_id": v,
                        "line_id": w["line_id"],
                    }
                )
                t += d
            prev_end = w["t"] + w["d"]
        if S.DURATION - prev_end > 0.1:
            vis.append(
                {
                    "t": _r6(prev_end),
                    "d": _r6(S.DURATION - prev_end),
                    "viseme": "X",
                    "voice_id": v,
                    "line_id": None,
                }
            )
    vis.sort(key=lambda x: (x["t"], x["voice_id"]))
    phs.sort(key=lambda x: (x["t"], x["voice_id"]))
    o.events(
        "visemes",
        vis,
        "lipsync",
        "synthetic",
        rel="lipsync/visemes.json",
        notes=[
            "phonemes from a hand-written ARPAbet dictionary, timed proportionally inside each truth word; Preston Blair mapping"
        ],
    )
    o.events("phonemes", phs, "lipsync", "synthetic", rel="lipsync/phonemes.json")

    # ------------------------------------------------------------------ choreo
    log("choreo ...")
    cnts = T.counts(acc)
    o.events("counts", cnts, "choreo", "fixture", notes=[f"accents: {T.FORMULAS['accent']}"])
    grv = T.grooves()
    o.events("grooves", grv, "choreo", "fixture", notes=[f"syncopation: {T.FORMULAS['syncopation']}"])
    protos = T.groove_protos()
    o.json(
        "meta/grooves.json",
        {"grooves": [{k: v for k, v in p.items() if k != "pattern_name"} for p in protos]},
        "choreo",
        "mvh/files/grooves",
    )
    hps = T.hit_points(acc, r.drum_hits, r.words, impacts, stop)
    o.events("hit_points", hps, "choreo", "fixture", notes=[T.FORMULAS["hit_point"]])
    hl = T.holds(r.words, vph, decay, silence)
    o.events("holds", hl, "choreo", "fixture", notes=[T.FORMULAS["holds"]])
    ch["choreo.accent"] = A.flash_envelope(
        n, [(b.t, acc[b.beat_index]) for b in S.BEATS if acc[b.beat_index] > 0], 0.12
    )
    ch["choreo.movement"] = np.clip(
        0.5 * ch["dyn.intensity"] + 0.5 * np.clip(dens / max(dens.max(), 1e-9), 0, 1), 0, 1
    )
    # tables (D2)
    sec_of_bar = {b: s for s in S.SECTIONS for b in range(s.start_bar, s.start_bar + s.n_bars)}
    phr_of_bar = {b: p for p in S.PHRASES for b in range(p.start_bar, p.start_bar + p.n_bars)}
    grv_of_bar = {g_["bar"]: g_ for g_ in grv}
    cnt_of_beat = {}
    for c in cnts:
        for k in range(c["len"]):
            cnt_of_beat[c["start_beat"] + k] = (c["id"], c["first_count"] + k)
    brow = []
    for b in beats:
        e_ = cnt_of_beat.get(b["beat_index"])
        brow.append(
            {
                **{
                    k: b[k]
                    for k in ("beat_index", "t", "bar", "beat_in_bar", "beats_in_bar", "in_pulse", "strength")
                },
                "section_id": sec_of_bar[b["bar"]].id if b["bar"] in sec_of_bar else None,
                "phrase_id": phr_of_bar[b["bar"]].id if b["bar"] in phr_of_bar else None,
                "eight_id": e_[0] if e_ else None,
                "count": e_[1] if e_ else None,
                "accent": acc[b["beat_index"]],
            }
        )
    tdef = catalog.TABLES_BY_PATH
    o.table(
        "tables/beats.csv",
        brow,
        [c.name for c in tdef["tables/beats.csv"].columns],
        "choreo",
        "mvh/tables/beats",
    )
    barrow = []
    for b in bars:
        g_ = grv_of_bar.get(b["bar"])
        barrow.append(
            {
                **{k: b[k] for k in ("bar", "t", "d", "beats_in_bar", "n_beats", "pickup", "in_pulse")},
                "section_id": sec_of_bar[b["bar"]].id if b["bar"] in sec_of_bar else None,
                "phrase_id": phr_of_bar[b["bar"]].id if b["bar"] in phr_of_bar else None,
                "groove_id": g_["groove_id"] if g_ else None,
                "swing": g_["swing"] if g_ else None,
                "syncopation": g_["syncopation"] if g_ else None,
            }
        )
    o.table(
        "tables/bars.csv",
        barrow,
        [c.name for c in tdef["tables/bars.csv"].columns],
        "choreo",
        "mvh/tables/bars",
    )
    role_of = {sid: role for _, role, _, _, sid in S.EDM_ROLES}
    srow = []
    for s, di in zip(S.SECTIONS, sec_items):
        dy = next(d for d in dyn_items if abs(d["t"] - s.t) < 1e-6)
        srow.append(
            {
                "id": s.id,
                "t": s.t,
                "d": s.d,
                "label": s.label,
                "occurrence": s.occurrence,
                "repeat_group": s.repeat_group,
                "start_bar": s.start_bar,
                "n_bars": s.n_bars,
                "edm_role": role_of.get(s.id),
                "level": dy["level"],
                "mean_lufs": dy["mean_lufs"],
            }
        )
    o.table(
        "tables/sections.csv",
        srow,
        [c.name for c in tdef["tables/sections.csv"].columns],
        "choreo",
        "mvh/tables/sections",
    )

    # ------------------------------------------------------------------ cues
    log("cues ...")
    cue = T.cues(hps, impacts, stop, silence)
    o.events("cues", cue, "cues", "fixture", notes=[T.FORMULAS["cues"]])
    by_src = {(s["file"], s["id"]): c for c in cue for s in c["sources"]}
    mom_spec = [
        (
            ("events/edm_roles.json", "R02"),
            1.0,
            16.0,
            "the drop: four-on-the-floor kick, crash and bass after the silent bar",
        ),
        (("events/sections.json", "S03"), 0.95, 8.0, "first chorus: crash, ride and the duet of both voices"),
        (
            ("events/stops.json", "X001"),
            0.9,
            2.0,
            "hard stop into one bar of digital silence after the 3/4 bar",
        ),
        (
            ("events/impacts.json", "I003"),
            0.85,
            4.0,
            "final hit: crash, kick and a held A minor chord ringing out",
        ),
        (("events/edm_roles.json", "R01"), 0.8, 7.5, "the build: snare roll accelerating, riser sweeping up"),
        (
            ("events/sections.json", "S02"),
            0.75,
            8.0,
            "verse: swung groove and the call-and-response between V1 and V2",
        ),
        (("events/phrases.json", "P07"), 0.7, 8.0, "instrumental half of the drop (no vocals)"),
        (("events/sections.json", "S06"), 0.6, 6.0, "outro: light swung groove before the last hit"),
        (
            ("events/sections.json", "S01"),
            0.55,
            8.0,
            "intro: kick, straight hats and the pad, tom fill into the verse",
        ),
        (("events/bars.json", "bar:16"), 0.5, 1.5, "the single 3/4 bar closing the build"),
    ]
    moments = []
    for rank, (key, stg, d, desc) in enumerate(mom_spec, start=1):
        c = by_src[key]
        moments.append(
            {
                "rank": rank,
                "t": c["t"],
                "d": d,
                "cue_id": c["id"],
                "kind": c["kind"],
                "strength": stg,
                "description": desc,
            }
        )
    o.events("moments", moments, "cues", "synthetic", notes=["ranking hand-picked for the fixture"])

    # ------------------------------------------------------------------ meaning (user inputs, draft, merged)
    log("meaning ...")
    _meaning(o, r, lines, sec_items, mood_items, cue, moments, spans)

    # ------------------------------------------------------------------ brief / viewer / frames
    log("brief / viewer / frames ...")
    vr = json.loads((out_dir / "meta/vocal_range.json").read_text(encoding="utf-8"))
    _brief(o, loud, lines, sec_items, dyn_items, hps, moments, cnts, protos, vr, total)
    o.text(
        "viewer.html",
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><title>mvh viewer (fixture)</title></head>\n'
        "<body><p>Fixture placeholder for the viewer stage (M6a owns the real viewer). Song: synth.</p></body></html>\n",
        "viewer",
    )

    # ------------------------------------------------------------------ curves (runner finalize)
    log("curves ...")
    entries = []
    for cid, v in ch.items():
        entries.append(curvefile.ChannelData(cid, np.asarray(v, dtype=np.float32), cmeta.get(cid)))
    entries.append(
        curvefile.ChannelData("spectrum128", spec_u8, {"band_edges_hz": [float(e) for e in edges]})
    )
    index = curvefile.assemble(out_dir, entries)
    errs = schemas.validate(index, "mvh/envelope/curves_index")
    o.errors += [f"curves/index.json: {e}" for e in errs]
    o.note("curves/index.json", "json", "_runner")
    from mvh.contract.registry import CURVE_FILES

    for fid, cf in CURVE_FILES.items():
        if fid in index["files"]:
            o.note(cf.path, "matrix" if cf.layout == "row-major" else "curve", "_runner")

    # frames (on demand): 24 fps sample export
    _frames(o, index, out_dir)

    # schema copies (runner finalize)
    for p in schemas.iter_schema_files():
        rel = "schema/" + p.relative_to(schemas.SCHEMA_DIR).as_posix()
        o.bytes(rel, p.read_bytes(), "_runner", "json")

    # ------------------------------------------------------------------ truth sidecar
    log("truth ...")
    for v in ("V1", "V2"):
        o.audio(f"_truth/voices/{v}.flac", r.voice_tracks[v], "_truth")
    truth.update(
        {
            "sections": [
                {
                    "id": s.id,
                    "label": s.label,
                    "t": s.t,
                    "d": s.d,
                    "start_bar": s.start_bar,
                    "n_bars": s.n_bars,
                    "repeat_group": s.repeat_group,
                }
                for s in S.SECTIONS
            ],
            "phrases": [
                {"id": p.id, "start_bar": p.start_bar, "n_bars": p.n_bars, "section_id": p.section_id}
                for p in S.PHRASES
            ],
            "edm_roles": roles,
            "pulse_regions": [{"t": a, "end": b, "in_pulse": p} for a, b, p in S.PULSE_REGIONS],
            "bars": bars,
            "beats": [
                {k: b[k] for k in ("beat_index", "t", "bar", "beat_in_bar", "beats_in_bar", "in_pulse")}
                for b in beats
            ],
            "drum_hits": [dict(h, sample=int(round(h["t"] * S.SR))) for h in r.drum_hits],
            "notes": r.notes,
            "words": r.words,
            "backing_words": r.backing_words,
            "chords": chords,
            "patterns": {k: [list(x) for x in v] for k, v in S.PATTERNS.items()},
            "bar_pattern": S.BAR_PATTERN,
            "groove_ids": S.GROOVE_IDS,
            "grooves": protos,
            "accents": {str(k): v for k, v in acc.items()},
            "counts": cnts,
            "loudness": loud,
            "vocal_range": {"p2": p2, "p98": p98, "lowest": nstat(lo_n), "highest": nstat(hi_n)},
            "impacts": impacts,
            "stops": [stop],
            "silences": [silence],
            "decay_tails": [decay],
            "characters": S.CHARACTERS,
            "voices": {"V1": S.VOICE_TTS["V1"], "V2": S.VOICE_TTS["V2"]},
            "stems_sum": "exact: every base track is on the 24-bit grid; vocals=lead+backing, drums=sum(sub-stems), "
            "mix=vocals+drums+bass+guitar+piano+other, instrumental=mix-vocals",
            "files": {
                "input": f"_truth/{INPUT_NAME}",
                "lyrics_input": "_truth/lyrics_input.lrc",
                "voices": "_truth/voices/{V1,V2}.flac",
            },
        }
    )
    truth = json.loads(json.dumps(truth, allow_nan=False), parse_float=lambda s: round(float(s), 6))
    o.text("_truth/truth.json", dumps_json(truth), "_truth")

    # ------------------------------------------------------------------ manifest + run (runner finalize)
    _manifest(o, source, loud, vr, total)
    return {"errors": o.errors, "n_files": len(o.files)}


# ================================================================================================ meaning
INTENT_MD = """# What this song means to me (meaning/intent.md)

<!-- Synthetic fixture: an example of the user's answers to meaning/interview.md. Invented for tests. -->

## The story
Two figures keep a harbour town lit through one long night. The Lamplighter (the low voice, V1) walks the river
with paper lanterns; the Tide (the high voice, V2) answers him from the water. In the choruses they finally sing
together. The silence before the drop is the moment the last lantern goes out - and then the whole harbour lights up.

## Characters
- C1 The Lamplighter = voice V1 (the low voice). Lead.
- C2 The Tide = voice V2 (the high voice). Answers in the verse, harmony in the choruses.

## Look and feel
- Palette: night blue, lantern amber, harbour blue, rust red, paper white.
- Intro: slow drift over dark water. Verse: call and response, cut between the two characters on each line.
- Build: everything tightens and speeds up; the 3/4 bar is a stumble.
- Drop: wide shots, every lantern at once.

## Never show
- Never show fire burning a person or a boat.
- No text on screen except the lyrics.
"""


def _claim(text, source, cites, status="user"):
    return {"text": text, "source": source, "cites": cites, "status": status}


def _meaning_doc(status: str, lines, sec_items, mood_items) -> dict:
    user = status == "user"
    cprov = {
        "source": "user" if user else "speculative",
        "status": "user" if user else "draft",
        "cites": [{"id": "S02"}, {"id": "L001"}],
    }
    feel = {
        "S01": (
            "slow drift over dark water",
            "still",
            "slow drifting camera, low over the water",
            "wide, slow push-in",
        ),
        "S02": (
            "call and response between the two keepers",
            "longing",
            "alternate between the two characters per line",
            "cut on every line change",
        ),
        "S03": (
            "the two voices meet",
            "warm",
            "both characters move together, mirrored",
            "two-shot, gentle orbit",
        ),
        "S04": (
            "tension winds up; the last lantern goes out",
            "anxious",
            "faster and tighter, freeze on the silent bar",
            "accelerating cuts, black frame in the silence",
        ),
        "S05": (
            "release: the harbour lights up",
            "euphoric",
            "big unison movement on every kick",
            "wide crane shots",
        ),
        "S06": (
            "morning comes; the light fades",
            "calm",
            "slow down, hold the last pose through the decay",
            "slow pull-out",
        ),
    }
    secs = []
    for s, m in zip(sec_items, mood_items):
        f, emo, mv, cam = feel[s["id"]]
        sec_lines = [x for x in S.LINES if x.section_id == s["id"]]
        present = sorted(
            {"C1" if x.voice == "V1" else "C2" for x in sec_lines}
            | ({"C2"} if any(x.duet for x in sec_lines) else set())
        )
        secs.append(
            {
                "section_id": s["id"],
                "t0": s["t"],
                "t1": round(s["t"] + s["d"], 6),
                "occurrence_label": s["occurrence_label"],
                "feel": f,
                "meaning": f if user else None,
                "emotion": {
                    "lyric": emo,
                    "audio": "energetic" if m["arousal"] > 0.5 else "calm",
                    "agree": True,
                },
                "palette_hint": [S.PALETTE[0], S.PALETTE[1]]
                if s["id"] != "S05"
                else [S.PALETTE[1], S.PALETTE[4]],
                "movement_hint": mv,
                "camera_hint": cam,
                "characters_present": present,
                "do_not": ["Never show fire burning a person or a boat."] if s["id"] == "S05" else [],
                "provenance": {
                    "source": "user" if user else "speculative",
                    "status": "user" if user else "draft",
                    "cites": [{"id": s["id"], "t0": s["t"], "t1": round(s["t"] + s["d"], 6)}],
                },
            }
        )
    return {
        "schema": "mvh/files/meaning",
        "schema_version": CONTRACT_VERSION,
        "status": status,
        "logline": "Two keepers light a harbour through one night; when the last lantern goes out, the whole town lights up.",
        "summary": "A call-and-response between a lamplighter and the tide that becomes a duet, breaks into silence and returns as a drop.",
        "themes": [
            _claim(
                "light carried through darkness",
                "user" if user else "lyric",
                [{"id": "L001"}, {"id": "L002"}],
                "user" if user else "draft",
            ),
            _claim(
                "two voices becoming one",
                "user" if user else "audio",
                [{"id": "S03"}, {"id": "L005"}],
                "user" if user else "draft",
            ),
        ],
        "perspective": {"narrator": "C1", "addressee": "C2"},
        "characters": [
            {
                "id": cid,
                "name": c["name"],
                "description": c["description"],
                "voice_ids": [c["voice"]],
                "lead_backing": c["lead_backing"],
                "line_ids": [x.id for x in S.LINES if x.voice == c["voice"] or (cid == "C2" and x.duet)],
                "section_ids": sorted(
                    {x.section_id for x in S.LINES if x.voice == c["voice"] or (cid == "C2" and x.duet)}
                ),
                "provenance": cprov,
            }
            for cid, c in S.CHARACTERS.items()
        ],
        "setting": "a harbour town at night, paper lanterns over a river",
        "motifs": [
            {
                "id": "M1",
                "name": "lanterns / light",
                "occurrences": [
                    {"t": next(ln["t"] for ln in lines if ln["id"] == lid), "line_id": lid}
                    for lid in ("L001", "L002")
                ],
                "provenance": {
                    "source": "lyric",
                    "status": "user" if user else "draft",
                    "cites": [{"id": "L001"}, {"id": "L002"}],
                },
            },
            {
                "id": "M2",
                "name": "water / tide",
                "occurrences": [
                    {"t": next(ln["t"] for ln in lines if ln["id"] == lid), "line_id": lid}
                    for lid in ("L001", "L006", "L010")
                ],
                "provenance": {
                    "source": "lyric",
                    "status": "user" if user else "draft",
                    "cites": [{"id": "L006"}],
                },
            },
        ],
        "symbolism": [
            _claim(
                "the silent bar is the last lantern going out",
                "user" if user else "audio",
                [{"id": "Z001", "t0": 32.5, "t1": 34.5}],
                "user" if user else "draft",
            )
        ],
        "sections": secs,
        "palette": list(S.PALETTE),
        "tone": "nocturnal, warm, building to euphoric",
        "do_not": ["Never show fire burning a person or a boat.", "No text on screen except the lyrics."]
        if user
        else [],
        "open_questions": [] if user else ["Which character is the narrator?"],
    }


def _meaning(o: Out, r: Render, lines, sec_items, mood_items, cue, moments, spans) -> None:
    o.text("meaning/intent.md", INTENT_MD, "_user")
    draft = _meaning_doc("draft", lines, sec_items, mood_items)
    o.json("meaning/authored.json", draft, "_user", "mvh/files/meaning")
    merged = _meaning_doc("user", lines, sec_items, mood_items)
    merged["provenance"] = prov(
        "meaning", "synthetic", ["merged: user (intent.md) > lyric > audio > draft (authored.json)"]
    )
    o.json("meaning/meaning.json", merged, "meaning", "mvh/files/meaning")
    o.json("meaning/orphans.json", {"orphans": []}, "meaning", "mvh/files/orphans")
    o.json("meaning/schema.json", schemas.load("mvh/files/meaning"), "meaning")
    o.json(
        "meaning/input.json",
        {
            "schema_version": CONTRACT_VERSION,
            "song": {"title": S.TITLE, "artist": S.ARTIST, "duration_s": S.DURATION},
            "sections": [{"id": s["id"], "t": s["t"], "d": s["d"], "label": s["label"]} for s in sec_items],
            "facts": {
                "bpm": S.BPM,
                "key": S.KEY["key"],
                "voices": ["V1", "V2"],
                "n_lines": len(lines),
                "cues_tier1": [c["id"] for c in cue if c["tier"] == 1],
                "moments": [m["cue_id"] for m in moments[:5]],
            },
            "lines_file": "lyrics/lines.tsv",
        },
        "meaning",
        "mvh/files/meaning_input",
    )
    sing = []
    for s_ in spans:
        sing.append(
            {
                "t": s_["t"],
                "d": s_["d"],
                "character_id": "C1" if s_["voice_id"] == "V1" else "C2",
                "voice_id": s_["voice_id"],
                "line_id": s_["line_id"],
                "lead_backing": "backing" if s_["conf"] < 0.8 else "lead",
            }
        )
    o.events(
        "singing",
        sing,
        "meaning",
        "fixture",
        notes=["lines joined with voices (voice_spans) and characters (intent.md)"],
    )
    # D38: the singer cell lists every character singing the line, lead first, joined with "+" (e.g. C1+C2)
    by_line: dict[str, list[dict]] = {}
    for s_ in sing:
        by_line.setdefault(s_["line_id"], []).append(s_)

    def _singer_cell(line_id: str) -> str:
        ss = sorted(by_line[line_id], key=lambda s_: (s_["lead_backing"] != "lead", s_["voice_id"]))
        return "+".join(dict.fromkeys(s_["character_id"] for s_ in ss))

    singer = {ln.id: _singer_cell(ln.id) for ln in S.LINES}
    rows = [
        {
            "id": ln["id"],
            "t": ln["t"],
            "d": ln["d"],
            "section_id": ln["section_id"],
            "singer": singer[ln["id"]],
            "repeat_group": ln["repeat_group"],
            "grade": ln["grade"],
            "text": ln["text"],
        }
        for ln in lines
    ]
    o.table(
        "lyrics/lines.tsv",
        rows,
        ["id", "t", "d", "section_id", "singer", "repeat_group", "grade", "text"],
        "meaning",
        "mvh/tables/lines",
        sep="\t",
    )
    o.text(
        "meaning/interview.md",
        "# Interview (synthetic fixture)\n\n"
        "1. What does this song mean to you?\n2. Who sings to whom? Two voices were found: V1 (low) and V2 (high). "
        "Which character is each voice?\n3. Where and when does the video take place?\n4. How should each section feel and move "
        "(S01 intro ... S06 outro)?\n5. Which colours belong to the song?\n6. What must never appear on screen?\n",
        "meaning",
    )
    o.text(
        "meaning/request.md",
        "# Draft request (synthetic fixture)\n\nRead meaning/input.json and lyrics/lines.tsv. Fill only the "
        "gaps the user left in meaning/intent.md. Write meaning/authored.json with status 'draft' following meaning/schema.json. "
        "Cite IDs (S.., L.., Q....) for every claim; quotes of at most 10 words.\n",
        "meaning",
    )
    md = [f"# Meaning: {S.TITLE}", "", f"Status: user. {merged['logline']}", "", "## Characters"]
    md += [
        f"- {c['id']} {c['name']} (voice {', '.join(c['voice_ids'])}): {c['description']}"
        for c in merged["characters"]
    ]
    md += ["", "## Sections"] + [
        f"- {s['section_id']} ({s['occurrence_label']}, {s['t0']:.1f}-{s['t1']:.1f} s): {s['feel']}"
        for s in merged["sections"]
    ]
    md += ["", "## Never show"] + [f"- {d}" for d in merged["do_not"]]
    o.text("meaning/meaning.md", "\n".join(md) + "\n", "meaning")


def _mmss(t: float) -> str:
    m, s = divmod(t, 60)
    return f"{int(m)}:{s:04.1f}"


def _brief(o: Out, loud, lines, sec_items, dyn_items, hps, moments, cnts, protos, vr, total) -> None:
    out = [
        f"# {S.TITLE} - {S.ARTIST}",
        "",
        "meaning: user · lyrics: grade A · stems: hq · visemes: yes · flags: none (synthetic fixture)",
        "",
        "| field | value |",
        "|---|---|",
        f"| duration | {S.DURATION:.1f} s ({_mmss(S.DURATION)}) |",
        f"| tempo | {S.BPM:.0f} BPM, normal feel (meta/tempo.json) |",
        "| meter | 4/4, one 3/4 bar (bar 16), pickup bar 0 |",
        f"| key | {S.KEY['key']} (conf 0.90, meta/key.json) |",
        f"| loudness | {loud['integrated_lufs']:.1f} LUFS, LRA {loud['lra_lu']:.1f} LU, TP {loud['true_peak_dbtp']:.1f} dBTP (meta/loudness.json) |",
        f"| vocal range | {vr['lowest']['name']}-{vr['highest']['name']}, {vr['register']} (meta/vocal_range.json) |",
        f"| instrumentation | {', '.join(k for k, _ in sorted(total.items(), key=lambda kv: -kv[1]))} (meta/instruments.json) |",
        "",
        "## Meaning",
        "Two keepers light a harbour through one night; when the last lantern goes out, the whole town lights up.",
        "",
        "| ID | description | voice | sections |",
        "|---|---|---|---|",
        "| C1 | The Lamplighter (low voice) | V1 | S02, S03, S04, S05 |",
        "| C2 | The Tide (high voice) | V2 | S02, S03, S04, S05 |",
        "",
        'Do not: "Never show fire burning a person or a boat." "No text on screen except the lyrics."',
        "",
        "Palette: " + " ".join(S.PALETTE),
        "",
        "## Sections (events/sections.json)",
        "| ID | t | bars | label | group | level | lines |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in sec_items:
        dy = next(d for d in dyn_items if abs(d["t"] - s["t"]) < 1e-6)
        ls = [ln["id"] for ln in lines if ln["section_id"] == s["id"]]
        out.append(
            f"| {s['id']} | {s['t']:.1f} ({_mmss(s['t'])}) | {s['start_bar']}-{s['start_bar'] + s['n_bars'] - 1} | "
            f"{s['occurrence_label']} | {s['repeat_group']} | {dy['level']} | {(ls[0] + '-' + ls[-1]) if ls else '-'} |"
        )
    out += [
        "",
        "## Choreography (events/counts.json, meta/grooves.json, events/hit_points.json)",
        f"{len(cnts) - 1} eight-counts plus the E000 lead-in; partial counts: "
        + ", ".join(c["id"] for c in cnts if c["partial"])
        + ".",
        "Grooves: "
        + ", ".join(f"{p['id']} swing {p['swing']} sync {p['syncopation']}" for p in protos[:6])
        + ", ...",
        "Strongest hit points: "
        + ", ".join(f"{h['id']} {h['t']:.2f}s" for h in sorted(hps, key=lambda h: h["rank"])[:5]),
        "",
        "## Top moments (events/moments.json)",
        "| rank | t | cue | kind | description |",
        "|---|---|---|---|---|",
    ]
    out += [
        f"| {m['rank']} | {m['t']:.2f} | {m['cue_id']} | {m['kind']} | {m['description']} |" for m in moments
    ]
    out += ["", "Loaders and file catalogue: SKILL.md and CONTRACT.md (lib/mvh.js, lib/mvh_load.py).", ""]
    o.text("brief.md", "\n".join(out), "brief")


def _frames(o: Out, index: dict, out_dir: Path) -> None:
    from mvh.contract.conventions import curve_frame, frame_count

    ids = ["bands.bass", "hits.kick", "loud.short_term", "vocal.pitch01", "vocal.mouth_open", "choreo.accent"]
    fr = {"fps": 24, "frame0": 0, "early": False}
    vals = {}
    for cid in ids:
        v, meta = curvefile.read_channel(out_dir, index, cid)
        vals[cid] = (v.astype(np.float64), meta)
    rows = []
    from mvh.contract.conventions import time_of

    for k in range(frame_count(S.DURATION, fr)):
        row: dict[str, Any] = {"frame": k, "t": round(time_of(k, fr), 6)}
        for cid in ids:
            v, meta = vals[cid]
            nan_aware = bool(meta.get("special") and meta["special"].get("nan"))
            row[cid] = round(float(curve_frame(v, k, fr, 100, meta["resample"], nan_aware=nan_aware)), 6)
        rows.append(row)
    o.table("frames/24fps.csv", rows, ["frame", "t", *ids], "frames", "mvh/tables/frames")


def _manifest(o: Out, source, loud, vr, total) -> None:
    stages = sorted(set(DEPS))
    files = sorted(
        (e for e in o.files.values() if not e["path"].startswith("schema/")), key=lambda e: e["path"]
    )
    files.append({"path": "manifest.json", "kind": "json", "stage": "_runner"})
    files.append({"path": "run.json", "kind": "json", "stage": "_runner"})
    files.sort(key=lambda e: e["path"])
    man = {
        "schema": "mvh/manifest",
        "schema_version": CONTRACT_VERSION,
        "mvh_version": "0.1.0",
        "contract_version": CONTRACT_VERSION,
        "slug": SLUG,
        "source": {
            k: source[k]
            for k in ("file_name", "pcm_sha256", "duration_s", "sample_rate", "channels", "n_samples")
        },
        "timebase": {
            "unit": "s",
            "origin": "first sample of audio/mix.flac",
            "soundtrack": "audio/mix.flac",
            "curve_rate_hz": 100,
            "frame_rule": "centred",
        },
        "status": {
            "stages": {s: "done" for s in stages if s != "frames"} | {"frames": "done"},
            "meaning": "user",
            "lyrics_grade": "A",
            "stems": True,
            "visemes": True,
            "flags": ["synthetic_fixture"],
        },
        "summary": {
            "title": S.TITLE,
            "artist": S.ARTIST,
            "duration_s": S.DURATION,
            "bpm": S.BPM,
            "feel": "normal",
            "meter": "4/4",
            "key": S.KEY["key"],
            "integrated_lufs": loud["integrated_lufs"],
            "lra_lu": loud["lra_lu"],
            "true_peak_dbtp": loud["true_peak_dbtp"],
            "vocal_range": {"low": vr["lowest"]["name"], "high": vr["highest"]["name"]},
            "instrumentation": [k for k, _ in sorted(total.items(), key=lambda kv: -kv[1])],
            "palette": list(S.PALETTE),
            "stages": {s: {"fixture": True} for s in stages},
        },
        "files": files,
        "warnings": [
            "synthetic fixture: values are ground truth, measurements or SYNTHETIC (see provenance)"
        ],
    }
    if len(json.dumps(man, ensure_ascii=False, indent=1)) / 4 > 2900:  # D34: trim stage summaries, flag it
        man["summary"]["stages"] = {}
        man["status"]["flags"].append("manifest:stage_summaries_trimmed")
    o.json("manifest.json", man, "_runner", "mvh/envelope/manifest")
    run = {
        "schema": "mvh/run",
        "schema_version": CONTRACT_VERSION,
        "mvh_version": "0.1.0",
        "contract_version": CONTRACT_VERSION,
        "started": "fixture",
        "finished": None,
        "profile": "max",
        "host": {"os": "fixture", "cpu": "fixture", "threads": 1},
        "device": {"class": "cpu", "gpu": None},
        "versions": {"python": "fixture", "ffmpeg": {"version": "fixture", "buildconf": []}, "packages": {}},
        "stages": {
            s: {
                "status": "done",
                "cache": "miss",
                "key": _key(s),
                "seconds": None,
                "threads": 1,
                "device": "cpu",
                "env": "sep" if s == "separate_hq" else "main",
                "variant": None,
                "fallbacks": [],
                "warnings": [],
            }
            for s in stages
        },
        "licences": [],
        "fallbacks_used": [],
        "warnings": ["synthetic fixture (tests/synth): run.json is not a real run"],
    }
    o.json("run.json", run, "_runner", "mvh/envelope/run")
