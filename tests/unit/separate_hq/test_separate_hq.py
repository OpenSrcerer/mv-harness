"""separate_hq: the parent's stem assembly and invariants (with the worker replaced by the generator tracks), the
htdemucs fallback, the worker job against a fake audio-separator (configuration traps), and the real worker on a
short excerpt (``-m real``)."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import numpy as np
import pytest
from tests.synth.m3a import SYNTH, fixture_upstreams, run_stage

from mvh.contract import schemas
from mvh.contract.ids import DRUM_SUBSTEMS, STEM_NAMES
from mvh.io import audio as aio
from mvh.runner.spec import StageError
from mvh.sep import invariants


def _gen(name: str) -> np.ndarray:
    rel = f"stems/{name}.flac" if name in STEM_NAMES else f"stems/drums/{name}.flac"
    return aio.decode(SYNTH / rel).samples


def _fake_worker_outputs() -> dict[str, np.ndarray]:
    """What the worker would return if the models were perfect: the generator tracks (44.1 kHz stereo)."""
    out = {f"sw_{s}": _gen(s) for s in ("bass", "drums", "other", "vocals", "guitar", "piano")}
    out["mel_vocals"] = _gen("vocals")
    out["kar_lead"] = _gen("lead_vocals")
    out["kar_backing"] = _gen("backing_vocals")
    for s in DRUM_SUBSTEMS:
        out[f"ds_{s}"] = _gen(s)
    return out


class _Res:
    variant = "rocm"
    fallbacks: list = []
    attempts: list = []


@pytest.fixture
def fake_worker(monkeypatch):
    import mvh.stages.separate_hq as hq

    monkeypatch.setattr(hq, "_run_worker", lambda ctx, x44, skip_karaoke=False: (_fake_worker_outputs(), {"torch": "x", "audio_separator": "y"}, _Res()))
    return hq


def test_stage_assembles_exact_stems(fake_worker, tmp_path):
    ups, ing = fixture_upstreams(SYNTH)
    out, done = run_stage("separate_hq", tmp_path, ups, ing)
    with open(out / "meta/separation.json", encoding="utf-8") as fh:
        meta = json.load(fh)
    assert schemas.validate(meta, "mvh/files/separation") == []
    assert meta["variant"] == "rocm" and meta["degraded"] is False and meta["lead_backing_split"] is True
    # every stem + every drum sub-stem, same length as the mix
    mix = aio.decode(SYNTH / "audio" / "mix.flac").samples
    for name in list(STEM_NAMES) + [f"drums/{s}" for s in DRUM_SUBSTEMS]:
        x = aio.decode(out / f"stems/{name}.flac").samples
        assert x.shape == mix.shape, name
    assert (out / "sep/vocals_sw.flac").is_file()
    inv = meta["invariants"]
    assert inv["sum_error_db"] < -100                      # the generator tracks sum exactly
    assert all(abs(g) < 0.01 for g in inv["gain_db"].values() if g > -100)
    ch = meta["checks"]
    assert ch["instrumental_plus_vocals_vs_mix_db"] < -140 and ch["lead_plus_backing_vs_vocals_db"] < -140
    assert ch["sum_pass"] is True and ch["gain_pass"] is True
    assert {m["id"] for m in meta["models"]} == {"sep.bs-roformer-sw-6stem", "sep.mel-roformer-vocals-kimberley",
                                                  "sep.mel-roformer-karaoke-aufr33-viperx", "sep.mdx23c-drumsep"}
    assert done["status"] == "ok"


def test_mono_input_skips_the_karaoke_split_and_says_so(monkeypatch, tmp_path):
    """The karaoke model needs a stereo pan cue: on a mono / dual-mono song lead := vocals, backing is silent, the
    split is declared absent and flagged (it used to run and invert silently)."""
    import mvh.stages.separate_hq as hq

    seen = {}

    def worker(ctx, x44, skip_karaoke=False):
        seen["skip"] = skip_karaoke
        o = _fake_worker_outputs()
        if skip_karaoke:
            o.pop("kar_lead"), o.pop("kar_backing")
        return o, {}, _Res()

    monkeypatch.setattr(hq, "_run_worker", worker)
    monkeypatch.setattr("mvh.sep.fit.is_mono", lambda x, side_db=-30.0: True)
    ups, ing = fixture_upstreams(SYNTH)
    out, done = run_stage("separate_hq", tmp_path, ups, ing)
    with open(out / "meta/separation.json", encoding="utf-8") as fh:
        meta = json.load(fh)
    assert seen["skip"] is True
    assert meta["lead_backing_split"] is False and "sep:lead_backing_mono" in meta["flags"]
    assert schemas.validate(meta, "mvh/files/separation") == []
    voc = aio.decode(out / "stems/vocals.flac").samples
    lead = aio.decode(out / "stems/lead_vocals.flac").samples
    back = aio.decode(out / "stems/backing_vocals.flac").samples
    assert np.allclose(voc, lead, atol=1e-6) and not np.any(back)
    assert "sep.mel-roformer-karaoke-aufr33-viperx" not in {m["id"] for m in meta["models"]}


def test_is_mono_detects_mono_and_dual_mono_but_not_stereo():
    from mvh.sep import fit

    rng = np.random.default_rng(0)
    a = rng.standard_normal(20000).astype(np.float32)
    assert fit.is_mono(a[None, :]) and fit.is_mono(np.stack([a, a]))
    assert fit.is_mono(np.stack([a, a + 1e-4 * rng.standard_normal(a.size).astype(np.float32)]))
    b = rng.standard_normal(20000).astype(np.float32)
    assert not fit.is_mono(np.stack([a, 0.5 * a + 0.5 * b]))
    assert not fit.is_mono(np.stack([a, -a]))


def test_bad_variant_order_fails_fast(fake_worker, tmp_path):
    ups, ing = fixture_upstreams(SYNTH)
    with pytest.raises(Exception, match="variant_order"):
        run_stage("separate_hq", tmp_path, ups, ing, params={"variant_order": "[cpu]"})


def test_gain_gate_fails_an_inverted_stem():
    from mvh.sep import invariants

    rng = np.random.default_rng(1)
    a = rng.standard_normal((2, 8000)).astype(np.float32)
    assert invariants.gain_gate(a, {"x": a})["x"]["pass"] is True
    assert invariants.gain_gate(a, {"x": -a})["x"]["pass"] is False


def test_stage_flags_a_leaky_model(monkeypatch, tmp_path):
    import mvh.stages.separate_hq as hq

    def leaky(ctx, x44, skip_karaoke=False):
        o = _fake_worker_outputs()
        o["sw_other"] = o["sw_other"] * 0.0          # a model that drops a part: the six stems no longer sum
        return o, {}, _Res()

    monkeypatch.setattr(hq, "_run_worker", leaky)
    ups, ing = fixture_upstreams(SYNTH)
    out, done = run_stage("separate_hq", tmp_path, ups, ing)
    with open(out / "meta/separation.json", encoding="utf-8") as fh:
        meta = json.load(fh)
    assert "sep:sum_residual" in meta["flags"] and meta["checks"]["sum_pass"] is False
    assert any("sum residual" in w for w in done["result"]["warnings"])


def test_degraded_htdemucs_fallback(monkeypatch, tmp_path):
    import mvh.stages.separate_hq as hq

    def fail(ctx, x44, skip_karaoke=False):
        raise StageError("sep worker failed in every variant ['rocm', 'cpu']")

    def fallback(ctx, x44):
        o = _fake_worker_outputs()
        return {k: v for k, v in o.items() if k.startswith("sw_")}

    monkeypatch.setattr(hq, "_run_worker", fail)
    monkeypatch.setattr(hq, "_run_fallback", fallback)
    ups, ing = fixture_upstreams(SYNTH)
    out, done = run_stage("separate_hq", tmp_path, ups, ing)
    with open(out / "meta/separation.json", encoding="utf-8") as fh:
        meta = json.load(fh)
    assert meta["variant"] == "htdemucs" and meta["degraded"] is True and meta["lead_backing_split"] is False
    assert done["status"] == "degraded"
    assert {"sep:htdemucs", "lead_vocals:=vocals"} <= set(done["result"]["fallbacks"])
    back = aio.decode(out / "stems/backing_vocals.flac").samples
    assert np.max(np.abs(back)) == 0.0                     # D17: always written, silent without a split
    lead = aio.decode(out / "stems/lead_vocals.flac").samples
    voc = aio.decode(out / "stems/vocals.flac").samples
    assert np.array_equal(lead, voc)
    assert not (out / "stems/drums/kick.flac").exists()


def test_no_fallback_when_not_allowed(monkeypatch, tmp_path):
    import mvh.stages.separate_hq as hq

    monkeypatch.setattr(hq, "_run_worker", lambda ctx, x44, skip_karaoke=False: (_ for _ in ()).throw(StageError("boom")))
    ups, ing = fixture_upstreams(SYNTH)
    with pytest.raises(StageError):
        run_stage("separate_hq", tmp_path, ups, ing, params={"variant_order": ["rocm", "cpu"]})


# ------------------------------------------------------------------------------------------------ worker job
class _FakeSeparator:
    instances: list = []

    def __init__(self, **kw):
        if kw.get("normalization_threshold", 1.0) > 1.0:
            raise ValueError("normalization_threshold must be <= 1")   # the real constructor's check
        self.kw = kw
        self.normalization_threshold = kw["normalization_threshold"]
        self.amplification_threshold = kw["amplification_threshold"]
        self.torch_device = "cpu"
        self.loaded = None
        _FakeSeparator.instances.append(self)

    def load_model(self, model_filename):
        self.loaded = model_filename
        self.at_load = (self.normalization_threshold, self.amplification_threshold)

    def separate(self, path, custom_output_names=None):
        from mvh.io.wav import read_wav, write_wav

        x, sr = read_wav(path)
        names = list(dict.fromkeys(custom_output_names.values()))
        for i, base in enumerate(names):
            write_wav(Path(self.kw["output_dir"]) / f"{base}.wav", x * (0.5 if i == 0 else 0.25), sr)
        return names


def test_worker_job_configuration(monkeypatch, tmp_path):
    from mvh.io.wav import read_wav, write_wav
    from mvh.sep import hq_worker

    pkg = types.ModuleType("audio_separator")
    sub = types.ModuleType("audio_separator.separator")
    sub.Separator = _FakeSeparator
    pkg.separator = sub
    monkeypatch.setitem(sys.modules, "audio_separator", pkg)
    monkeypatch.setitem(sys.modules, "audio_separator.separator", sub)
    _FakeSeparator.instances.clear()
    mix = (np.random.default_rng(0).standard_normal((2, 44100)) * 0.1).astype(np.float32)
    write_wav(tmp_path / "mix.wav", mix, 44100)
    models = {}
    for _key, mid, _inp, _names in hq_worker.STEPS:
        d = tmp_path / "models"
        d.mkdir(exist_ok=True)
        ck = d / f"{mid}.ckpt"
        ck.write_bytes(b"x")
        models[mid] = {f"separator/{mid}.ckpt": str(ck), f"separator/{mid}.yaml": str(d / f"{mid}.yaml")}
    out = tmp_path / "out"
    out.mkdir()
    job = {"inputs": {"mix": str(tmp_path / "mix.wav")}, "models": models, "variant": "cpu", "threads": 2,
           "params": {"overlap": 4, "segment_size": 256, "heavy_locks": False}, "scratch": str(tmp_path / "scr")}
    res = hq_worker.run_job(job, out)
    files = sorted(p.name for p in out.iterdir())
    assert files == sorted([f"sw_{s}.wav" for s in hq_worker.SW_STEMS] + ["mel_vocals.wav", "kar_lead.wav", "kar_backing.wav"]
                           + [f"ds_{s}.wav" for s in ("kick", "snare", "toms", "hihat", "ride", "crash")])
    assert not (tmp_path / "scr" / "_work").exists()
    for inst in _FakeSeparator.instances:
        assert inst.at_load == (100.0, 0.0)                 # set as attributes after construction
        assert inst.kw["use_soundfile"] is True and inst.kw["output_format"] == "WAV"
        assert inst.kw["sample_rate"] == 44100 and inst.kw["mdxc_params"]["overlap"] == 4
        assert Path(inst.kw["model_file_dir"]) == tmp_path / "models"
    assert [i.loaded for i in _FakeSeparator.instances] == [f"{m}.ckpt" for _k, m, _i, _n in hq_worker.STEPS]
    # the karaoke model ran on the Mel vocals and DrumSep on the SW drums (chained inputs)
    lead, _ = read_wav(out / "kar_lead.wav")
    mel, _ = read_wav(out / "mel_vocals.wav")
    assert np.allclose(lead, mel * 0.5)
    assert res["summary"]["settings"]["normalization_threshold"] == 100.0


def test_worker_rejects_non_441_input(tmp_path):
    from mvh.io.wav import write_wav
    from mvh.sep import hq_worker

    write_wav(tmp_path / "mix.wav", np.zeros((2, 4800), dtype=np.float32), 48000)
    with pytest.raises(RuntimeError):
        hq_worker.run_job({"inputs": {"mix": str(tmp_path / "mix.wav")}, "models": {}, "variant": "cpu",
                           "params": {"heavy_locks": False}, "scratch": str(tmp_path)}, tmp_path / "o")


# ------------------------------------------------------------------------------------------------ real (explicit)
@pytest.mark.real
def test_real_worker_on_a_synthetic_excerpt(tmp_path):
    """Real models through ctx.worker (rocm, then cpu) on the first 12 s of the synthetic song."""
    from mvh.io.wav import read_wav, write_wav

    ups, ing = fixture_upstreams(SYNTH)
    x, sr = read_wav(Path(ing) / "canonical.wav")
    short = tmp_path / "ing"
    short.mkdir()
    write_wav(short / "canonical.wav", x[:, : 12 * sr], sr)
    ups["ingest"] = str(short)
    out, done = run_stage("separate_hq", tmp_path, ups, str(short), heavy_locks=True)
    with open(out / "meta/separation.json", encoding="utf-8") as fh:
        meta = json.load(fh)
    assert meta["degraded"] is False and meta["checks"]["sum_pass"] is True
    assert meta["checks"]["instrumental_plus_vocals_vs_mix_db"] < -100
    assert invariants.rms_dbfs(aio.decode(out / "stems/drums.flac").samples) > -40


def _inverted_worker(monkeypatch):
    """A worker whose karaoke output is inverted (the lead track holds the backing voice): backing > lead."""
    import mvh.stages.separate_hq as hq

    def worker(ctx, x44, skip_karaoke=False):
        o = _fake_worker_outputs()
        o["kar_lead"], o["kar_backing"] = o["kar_backing"], o["kar_lead"]
        return o, {}, _Res()

    monkeypatch.setattr(hq, "_run_worker", worker)


def test_side_to_mid_db_grades_the_stereo_width():
    from mvh.sep import fit

    rng = np.random.default_rng(0)
    a = rng.standard_normal(20000).astype(np.float32)
    b = rng.standard_normal(20000).astype(np.float32)
    assert fit.side_to_mid_db(a[None, :]) == float("-inf") and fit.side_to_mid_db(np.stack([a, a])) < -100
    narrow = fit.side_to_mid_db(np.stack([a + 0.05 * b, a - 0.05 * b]))
    wide = fit.side_to_mid_db(np.stack([a, b]))
    assert narrow < -20.0 < -3.0 < wide


def test_suspect_split_on_a_narrow_master_drops_the_split(monkeypatch, tmp_path):
    """Backing louder than the lead on a near-mono master (side 24 dB under mid, not caught by ``is_mono``): the karaoke
    pan cue failed, so lead := vocals, backing silent, split declared absent and flagged."""
    _inverted_worker(monkeypatch)
    monkeypatch.setattr("mvh.sep.fit.side_to_mid_db", lambda x: -24.0)
    ups, ing = fixture_upstreams(SYNTH)
    out, _ = run_stage("separate_hq", tmp_path, ups, ing)
    with open(out / "meta/separation.json", encoding="utf-8") as fh:
        meta = json.load(fh)
    assert meta["lead_backing_split"] is False
    assert {"sep:lead_backing_suspect", "sep:lead_backing_narrow"} <= set(meta["flags"])
    assert meta["checks"]["side_to_mid_db"] == -24.0
    assert schemas.validate(meta, "mvh/files/separation") == []
    assert not np.any(aio.decode(out / "stems/backing_vocals.flac").samples)


def test_suspect_split_on_a_wide_master_is_only_flagged(monkeypatch, tmp_path):
    """On a wide stereo master the split is kept (a duet can have two equal voices) but flagged, with the per-second lead
    share as its confidence."""
    _inverted_worker(monkeypatch)
    monkeypatch.setattr("mvh.sep.fit.side_to_mid_db", lambda x: -10.0)
    ups, ing = fixture_upstreams(SYNTH)
    out, _ = run_stage("separate_hq", tmp_path, ups, ing)
    with open(out / "meta/separation.json", encoding="utf-8") as fh:
        meta = json.load(fh)
    assert meta["lead_backing_split"] is True and "sep:lead_backing_suspect" in meta["flags"]
    assert "sep:lead_backing_narrow" not in meta["flags"]
    share = meta["checks"]["lead_share_frames"]
    assert share["seconds"] > 10 and share["clean_fraction"] is not None and share["clean_fraction"] < 0.5


def test_a_clean_split_is_not_flagged(fake_worker, tmp_path):
    ups, ing = fixture_upstreams(SYNTH)
    out, _ = run_stage("separate_hq", tmp_path, ups, ing)
    with open(out / "meta/separation.json", encoding="utf-8") as fh:
        meta = json.load(fh)
    assert "sep:lead_backing_suspect" not in meta["flags"]
    assert meta["checks"]["lead_share_frames"]["clean_fraction"] > 0.5


# ---------------------------------------------------------------- R4-2: bit-reproducible RoFormer steps
def test_deterministic_scatter_add_restores_and_falls_back_on_cpu():
    import torch

    from mvh.sep.determinism import deterministic_scatter_add

    orig = torch.Tensor.scatter_add_
    idx = torch.tensor([0, 1, 1, 2]).view(1, 1, -1, 1).expand(1, 1, 4, 3).contiguous()
    src = torch.randn(1, 1, 4, 3, dtype=torch.complex64)
    ref = torch.zeros(1, 1, 3, 3, dtype=torch.complex64).scatter_add_(2, idx, src)
    with deterministic_scatter_add():
        assert torch.Tensor.scatter_add_ is not orig
        got = torch.zeros(1, 1, 3, 3, dtype=torch.complex64).scatter_add_(2, idx, src)   # CPU: the original path
    assert torch.Tensor.scatter_add_ is orig
    assert torch.equal(ref, got)


def test_fixed_order_mask_sum_equals_scatter_add():
    """the matrix-product replacement gives the scatter_add_ sum (the CUDA-only branch, exercised on CPU tensors)"""
    import torch

    from mvh.sep import determinism

    class _T(torch.Tensor):
        pass

    orig = torch.Tensor.scatter_add_
    fn = determinism._det_scatter_add(orig)
    rng = torch.Generator().manual_seed(0)
    f_src, f_out = 40, 25
    idx = torch.randint(0, f_out, (f_src,), generator=rng)
    index = idx.view(1, 1, -1, 1).expand(2, 2, f_src, 7).contiguous()
    src = torch.randn(2, 2, f_src, 7, dtype=torch.complex64, generator=rng)
    ref = torch.zeros(2, 2, f_out, 7, dtype=torch.complex64).scatter_add_(2, index, src)
    # is_cuda is False on CPU, so the wrapper falls back; call the fixed-order branch through a stub with is_cuda True
    class _Stub:
        def __init__(self, t):
            self.t = t
            self.is_cuda = True
            self.shape = t.shape

        def is_complex(self):
            return True

        def dim(self):
            return 4

        def add_(self, v):
            self.t.add_(v)
            return self.t

    out = torch.zeros(2, 2, f_out, 7, dtype=torch.complex64)
    got = fn(_Stub(out), 2, index, src)
    assert torch.allclose(got, ref, atol=1e-5)
