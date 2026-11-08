# ruff: noqa: E501  (long data tables / docstrings in generated-fixture code)
"""Windows SAPI TTS (voices David and Zira) and LPC "singing" resynthesis.

Word clips
  ``word(voice, text)`` returns the raw SAPI rendering (22.05 kHz, 16-bit mono) as float64. Clips are stored
  as int16 ``.npy`` assets under ``tests/synth/assets/tts/<voice>/<word>.npy`` (committed), so regeneration
  never depends on the installed voices; a missing asset is rendered with SAPI (recipe of
  scripts/smoke/make_clips.ps1, fixed SpeechAudioFormatInfo) and saved. SAPI output is byte-identical
  across runs on this machine (checked 2026-11-08).

Sentences (natural TTS with word-start truth) are rendered on demand into ``tests/.cache/synth/tts/``.

Singing
  ``sing(x, notes...)`` analyses a word clip with LPC (order 22, 20 ms window, 5 ms hop), keeps its formant
  envelope and voicing, and resynthesises it with a band-limited pulse excitation at a programmed f0 (note +
  vibrato + glide). The voicing mask used for synthesis is returned, so f0 truth is exact: f0 = the programmed
  trajectory where the excitation was voiced, NaN elsewhere.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import signal

from .audio_io import read_wav

__all__ = ["VOICES", "ASSET_DIR", "word", "render_words", "sentence", "SungWord", "sing", "TTS_SR"]

REPO = Path(__file__).resolve().parents[2]
ASSET_DIR = Path(__file__).resolve().parent / "assets" / "tts"
CACHE_DIR = REPO / "tests" / ".cache" / "synth" / "tts"
TTS_SR = 22050
VOICES = {"david": "Microsoft David Desktop", "zira": "Microsoft Zira Desktop"}

_PS_WORDS = r"""
param([string]$ListFile)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(22050, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$lines = [System.IO.File]::ReadAllLines($ListFile, (New-Object System.Text.UTF8Encoding($false)))
foreach ($ln in $lines) {
  if (-not $ln) { continue }
  $p = $ln -split "`t"
  $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
  $s.SelectVoice($p[0])
  $script:marks = New-Object System.Collections.Generic.List[string]
  $s.add_SpeakProgress({ param($snd, $e) $script:marks.Add(("{0}`t{1}`t{2}" -f $e.AudioPosition.Ticks, $e.CharacterPosition, $e.CharacterCount)) })
  $s.SetOutputToWaveFile($p[2], $fmt)
  $s.Speak($p[1])
  $s.Dispose()
  [System.IO.File]::WriteAllLines($p[2] + '.marks', $script:marks, (New-Object System.Text.UTF8Encoding($false)))
}
"""


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s or "x"


def _powershell() -> str:
    root = os.environ.get("SystemRoot", r"C:\Windows")
    p = Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return str(p) if p.exists() else "powershell.exe"


def render_words(jobs: list[tuple[str, str, Path]]) -> None:
    """jobs: [(voice key, text, out wav path)]. One PowerShell process renders all of them (with SAPI marks)."""
    if not jobs:
        return
    with tempfile.TemporaryDirectory(prefix="mvh-tts-") as td:
        ps1 = Path(td) / "render.ps1"
        ps1.write_text(_PS_WORDS, encoding="utf-8-sig")
        lst = Path(td) / "jobs.txt"
        lst.write_text("\n".join(f"{VOICES[v]}\t{t}\t{p}" for v, t, p in jobs) + "\n", encoding="utf-8")
        for _, _, p in jobs:
            Path(p).parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(
            [
                _powershell(),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ps1),
                "-ListFile",
                str(lst),
            ],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        if r.returncode != 0:
            raise RuntimeError(f"SAPI rendering failed: {r.stderr[-800:]}")


def word(voice: str, text: str) -> np.ndarray:
    """Raw SAPI clip of one word (float64 at TTS_SR), from the committed asset or rendered on demand."""
    asset = ASSET_DIR / voice / f"{_slug(text)}.npy"
    if not asset.exists():
        tmp = CACHE_DIR / "words" / voice / f"{_slug(text)}.wav"
        render_words([(voice, text, tmp)])
        x, sr = read_wav(tmp)
        assert sr == TTS_SR, sr
        asset.parent.mkdir(parents=True, exist_ok=True)
        np.save(asset, np.round(x[0] * 32768.0).astype("<i2"), allow_pickle=False)
    a = np.load(asset, allow_pickle=False)
    return a.astype(np.float64) / 32768.0


def sentence(voice: str, text: str) -> tuple[np.ndarray, int, list[dict]]:
    """Natural TTS sentence (cached under tests/.cache/synth/tts/). Returns (x float64 at 22.05 kHz, sr, words)
    where words = [{text, t (SAPI word-start, s), char_pos}] from SAPI SpeakProgress (AudioPosition)."""
    key = hashlib.sha256(f"{voice}\t{text}".encode()).hexdigest()[:16]
    wav = CACHE_DIR / "sentences" / f"{voice}_{key}.wav"
    if not wav.exists():
        render_words([(voice, text, wav)])
    x, sr = read_wav(wav)
    marks = []
    mfile = Path(str(wav) + ".marks")
    if mfile.exists():
        for ln in mfile.read_text(encoding="utf-8-sig").splitlines():
            if not ln.strip():
                continue
            ticks, pos, cnt = (int(v) for v in ln.split("\t"))
            marks.append({"text": text[pos : pos + cnt], "t": round(ticks / 1e7, 6), "char_pos": pos})
    return x[0], sr, marks


# ------------------------------------------------------------------------------------------------ LPC singing
ORDER = 22
HOP = 110  # 5 ms at 22.05 kHz
WIN = 441  # 20 ms
PRE = 0.97


def _levinson(r: np.ndarray, order: int) -> tuple[np.ndarray, float]:
    """Reflection coefficients k[1..order] and the prediction error from autocorrelation r[0..order]."""
    a = np.zeros(order + 1)
    a[0] = 1.0
    k = np.zeros(order)
    err = r[0]
    for i in range(1, order + 1):
        acc = r[i] + np.dot(a[1:i], r[i - 1 : 0 : -1])
        ki = -acc / err if err > 0 else 0.0
        ki = float(np.clip(ki, -0.999, 0.999))
        k[i - 1] = ki
        a_prev = a.copy()
        a[1:i] = a_prev[1:i] + ki * a_prev[i - 1 : 0 : -1]
        a[i] = ki
        err *= 1.0 - ki * ki
    return k, float(err)


def _step_up(k: np.ndarray) -> np.ndarray:
    a = np.array([1.0])
    for ki in k:
        a = np.concatenate([a, [0.0]])
        a = a + ki * a[::-1]
    return a


@dataclass
class _Analysis:
    k: np.ndarray  # [F, ORDER]
    log_g: np.ndarray  # [F]
    voiced: np.ndarray  # [F] bool
    rms_db: np.ndarray  # [F]


def _analyse(x: np.ndarray) -> _Analysis:
    y = np.append(x[0], x[1:] - PRE * x[:-1])
    w = np.hanning(WIN)
    pad = np.pad(y, (WIN // 2, WIN // 2))
    VW = 2 * WIN  # 40 ms voicing window (two periods of a 100 Hz voice incl. the longest lag)
    xpad = np.pad(x, (VW // 2, VW // 2))
    nf = 1 + (len(y) - 1) // HOP
    ks, gs, vs, rd = [], [], [], []
    wsum = float(np.sum(w * w))
    lag_lo, lag_hi = TTS_SR // 400, TTS_SR // 70
    lagw = np.exp(-0.5 * (2 * np.pi * 60.0 * np.arange(ORDER + 1) / TTS_SR) ** 2)  # 60 Hz lag window
    for f in range(nf):
        seg = pad[f * HOP : f * HOP + WIN] * w
        r = np.correlate(seg, seg, "full")[WIN - 1 : WIN + ORDER]
        r[0] *= 1.0 + 1e-6
        r[0] += 1e-12
        k, err = _levinson(r * lagw, ORDER)
        ks.append(k)
        gs.append(0.5 * np.log(max(err, 1e-20) / wsum))
        raw = xpad[f * HOP : f * HOP + VW]
        mid = raw[VW // 2 - WIN // 2 : VW // 2 + WIN // 2 + 1] * w
        rd.append(10 * np.log10(float(np.dot(mid, mid)) / wsum + 1e-20))
        best = 0.0
        if float(np.dot(raw, raw)) > 1e-10:
            L = raw.size
            ac = np.correlate(raw, raw, "full")[L - 1 :]
            cs = np.concatenate([[0.0], np.cumsum(raw * raw)])
            lags = np.arange(lag_lo, lag_hi)
            den = np.sqrt(cs[L - lags] * (cs[L] - cs[lags]))
            ok = den > 0
            if ok.any():
                best = float(np.max(ac[lags][ok] / den[ok]))
        vs.append(best)
    rms_db = np.array(rd)
    per = np.array(vs)
    voiced = (per > 0.6) & (rms_db > rms_db.max() - 32.0)
    return _Analysis(np.array(ks), np.array(gs), voiced, rms_db)


@dataclass
class SungWord:
    audio: np.ndarray  # float64 at 44.1 kHz, length = round(dur * 44100)
    voiced: np.ndarray  # bool per 44.1 kHz sample (excitation voiced)
    midi: np.ndarray  # programmed fractional MIDI per 44.1 kHz sample
    nucleus: tuple[float, float]  # (start, end) s of the stretched vowel nucleus, relative to the word start


def _trim(x: np.ndarray) -> np.ndarray:
    fr = np.lib.stride_tricks.sliding_window_view(np.pad(x, (0, HOP)), HOP)[::HOP]
    db = 10 * np.log10(np.mean(fr**2, axis=1) + 1e-20)
    on = np.nonzero(db > db.max() - 45.0)[0]
    a, b = int(on[0]) * HOP, min(len(x), (int(on[-1]) + 1) * HOP)
    return x[a:b]


def _longest_run(mask: np.ndarray) -> tuple[int, int]:
    best, cur, start = (0, 0), 0, 0
    for i, v in enumerate(list(mask) + [False]):
        if v:
            if cur == 0:
                start = i
            cur += 1
        else:
            if cur > best[1] - best[0]:
                best = (start, start + cur)
            cur = 0
    return best


def sing(
    x: np.ndarray,
    midi_note: float,
    dur_s: float,
    *,
    prev_midi: float | None = None,
    vib_cents: float = 30.0,
    vib_hz: float = 5.5,
    seed: int = 0,
    target_db: float = -18.0,
) -> SungWord:
    """Resynthesise word clip x (TTS_SR) as a sung note of length dur_s at 44.1 kHz."""
    x = _trim(np.asarray(x, dtype=np.float64))
    an = _analyse(x)
    F = len(an.log_g)
    T = max(4, int(round(dur_s * TTS_SR / HOP)))
    a0, b0 = _longest_run(an.voiced)
    if b0 - a0 < 2:
        a0, b0 = 0, F
    onset, coda = a0, F - b0
    cons = onset + coda
    s = (
        min(1.0, 0.7 * T / cons) if cons > 0 else 1.0
    )  # consonant parts keep their speed unless the note is short
    on_t, co_t = onset * s, coda * s
    nuc_t = T - on_t - co_t  # the vowel nucleus takes the rest (>= 30 % of the note)
    j = np.arange(T, dtype=np.float64)
    src = np.where(
        j < on_t,
        j / s,
        np.where(
            j < on_t + nuc_t, a0 + (j - on_t) * (b0 - 1 - a0) / max(nuc_t - 1, 1), b0 + (j - on_t - nuc_t) / s
        ),
    )
    nuc = (on_t * HOP / TTS_SR, (on_t + nuc_t) * HOP / TTS_SR)
    src = np.clip(src, 0, F - 1)
    i0 = np.floor(src).astype(int)
    i1 = np.minimum(i0 + 1, F - 1)
    fr = (src - i0)[:, None]
    K = an.k[i0] * (1 - fr) + an.k[i1] * fr
    G = np.exp(an.log_g[i0] * (1 - fr[:, 0]) + an.log_g[i1] * fr[:, 0])
    V = an.voiced[np.round(src).astype(int)]

    n = T * HOP
    t = np.arange(n) / TTS_SR
    cents = np.zeros(n)
    if prev_midi is not None:
        cents += (prev_midi - midi_note) * 100.0 * np.clip(1.0 - t / 0.04, 0, 1)
    ramp = np.clip((t - 0.15) / 0.2, 0, 1)
    cents += vib_cents * ramp * np.sin(2 * np.pi * vib_hz * t)
    midi_tr = midi_note + cents / 100.0
    f0 = 440.0 * 2 ** ((midi_tr - 69) / 12)
    ph = 2 * np.pi * np.cumsum(f0) / TTS_SR
    kmax = max(1, int(0.45 * TTS_SR / float(f0.max())))
    g = np.random.default_rng(seed)
    phases = g.uniform(
        0, 2 * np.pi, kmax
    )  # fixed random harmonic phases: lower crest factor than a pulse train
    pulse = np.zeros(n)
    for kk in range(1, kmax + 1):
        pulse += np.cos(kk * ph + phases[kk - 1])
    pulse /= np.sqrt(kmax / 2.0)
    noise = g.standard_normal(n)
    vmask = np.repeat(V, HOP)
    exc = np.where(vmask, pulse + 0.06 * noise, noise)

    out = np.zeros(n)
    zi = np.zeros(ORDER)
    for j in range(T):
        a = _step_up(K[j])
        seg = exc[j * HOP : (j + 1) * HOP] * G[j]
        y, zi = signal.lfilter([1.0], a, seg, zi=zi)
        out[j * HOP : (j + 1) * HOP] = y
    out = signal.lfilter([1.0], [1.0, -PRE], out)
    nf_in, nf_out = int(0.004 * TTS_SR), int(0.02 * TTS_SR)
    out[:nf_in] *= np.linspace(0, 1, nf_in, endpoint=False)
    out[-nf_out:] *= np.linspace(1, 0, nf_out) ** 2
    vr = out[vmask] if vmask.any() else out
    rms = np.sqrt(np.mean(vr**2)) + 1e-12
    out *= 10 ** (target_db / 20) / rms
    # 22.05 kHz -> 44.1 kHz (exact factor 2)
    up = signal.resample_poly(out, 2, 1)
    n44 = int(round(dur_s * 44100))
    up = np.pad(up, (0, max(0, n44 - up.size)))[:n44]
    v44 = np.pad(np.repeat(vmask, 2), (0, max(0, n44 - 2 * n)))[:n44]
    m44 = np.pad(np.repeat(midi_tr, 2), (0, max(0, n44 - 2 * n)), mode="edge")[:n44]
    return SungWord(up, v44.astype(bool), m44, (round(nuc[0], 6), round(nuc[1], 6)))


def asset_manifest() -> dict:
    """Name -> sha256 of every committed TTS asset (for the report and the determinism test)."""
    out = {}
    for p in sorted(ASSET_DIR.rglob("*.npy")):
        out[p.relative_to(ASSET_DIR).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


if __name__ == "__main__":  # quick check: render (or load) one word per voice
    for v in VOICES:
        w = word(v, "lanterns")
        print(v, w.shape, json.dumps({"peak": round(float(np.max(np.abs(w))), 4)}))
