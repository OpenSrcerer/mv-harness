# ruff: noqa: E501  (long numeric tables / docstrings)
"""basic-pitch (ICASSP 2022, ONNX ``nmp.onnx``) on numpy arrays (owner M3b).

Recipe (docs/spike/main.md §2): the library's ``predict`` reads a PATH through librosa; we never hand it a path. Instead
we reproduce ``basic_pitch.inference.run_inference`` on an array (22.05 kHz mono, half-overlap padding, 2 s windows with
30 overlapping frames, ``unwrap_output``) with our own onnxruntime session, then decode notes with the library's own
``note_creation.output_to_notes_polyphonic`` and ``model_frames_to_time``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

SR = 22050
MODEL_ID = "basic_pitch_nmp_onnx"


@dataclass(frozen=True)
class Preset:
    onset_thresh: float = 0.5
    frame_thresh: float = 0.3
    min_note_ms: float = 127.7
    min_hz: float | None = None
    max_hz: float | None = None
    melodia: bool = True
    mono: bool = False          # monophonic reduction after decoding (bass)
    energy_tol: int = 11
    resplit: float | None = None  # split a held note where its own onset activation re-peaks above this (re-attacks)


PRESETS: dict[str, Preset] = {
    # bass: monophonic, E0..~G4; a slightly lower onset threshold keeps soft repeated notes
    "bass": Preset(onset_thresh=0.45, frame_thresh=0.3, min_note_ms=70.0, min_hz=27.0, max_hz=420.0, melodia=False,
                   mono=True),
    "guitar": Preset(onset_thresh=0.5, frame_thresh=0.3, min_note_ms=90.0, min_hz=70.0, max_hz=1600.0),
    "other": Preset(onset_thresh=0.5, frame_thresh=0.3, min_note_ms=110.0, min_hz=30.0, max_hz=4200.0),
    "piano": Preset(onset_thresh=0.5, frame_thresh=0.3, min_note_ms=60.0, min_hz=27.0, max_hz=4200.0),
}


class BasicPitch:
    def __init__(self, onnx_path: Path, threads: int = 3):
        import onnxruntime as ort

        so = ort.SessionOptions()
        so.intra_op_num_threads = int(threads)
        so.inter_op_num_threads = 1
        self.sess = ort.InferenceSession(str(onnx_path), so, providers=["CPUExecutionProvider"])

    def activations(self, y22: np.ndarray) -> dict[str, np.ndarray]:
        """{note, onset, contour} [frames x bins] for a 22.05 kHz mono signal (as basic-pitch's run_inference)."""
        from basic_pitch.constants import AUDIO_N_SAMPLES, FFT_HOP
        from basic_pitch.inference import unwrap_output, window_audio_file

        n_overlap = 30
        overlap_len = n_overlap * FFT_HOP
        hop = AUDIO_N_SAMPLES - overlap_len
        y = np.asarray(y22, np.float32).reshape(-1)
        orig = y.shape[0]
        y = np.concatenate([np.zeros(overlap_len // 2, np.float32), y])
        outs: dict[str, list[np.ndarray]] = {"note": [], "onset": [], "contour": []}
        batch: list[np.ndarray] = []

        def flush():
            if not batch:
                return
            x = np.concatenate(batch, axis=0).astype(np.float32)
            r = self.sess.run(["StatefulPartitionedCall:1", "StatefulPartitionedCall:2", "StatefulPartitionedCall:0"],
                              {"serving_default_input_2:0": x})
            for k, v in zip(("note", "onset", "contour"), r):
                outs[k].append(v)
            batch.clear()

        for window, _ in window_audio_file(y, hop):
            batch.append(np.expand_dims(window, axis=0))
            if len(batch) == 1:  # the ONNX export is batch-1 safe; batching kept at 1 for byte-stable results
                flush()
        flush()
        return {k: unwrap_output(np.concatenate(v), orig, n_overlap) for k, v in outs.items()}

    def notes(self, y22: np.ndarray, preset: Preset) -> list[tuple[float, float, int, float]]:
        """[(t_on s, t_off s, midi, amplitude 0..1)] sorted by onset."""
        from basic_pitch.constants import AUDIO_SAMPLE_RATE, FFT_HOP
        from basic_pitch.note_creation import model_frames_to_time, output_to_notes_polyphonic

        if y22.size < SR // 4 or float(np.abs(y22).max(initial=0.0)) < 1e-5:
            return []
        out = self.activations(y22)
        frames, onsets = out["note"], out["onset"]
        if frames is None or frames.shape[0] < 3:
            return []
        min_len = int(np.round(preset.min_note_ms / 1000 * (AUDIO_SAMPLE_RATE / FFT_HOP)))
        est = output_to_notes_polyphonic(frames, onsets, onset_thresh=preset.onset_thresh,
                                         frame_thresh=preset.frame_thresh, min_note_len=min_len, infer_onsets=True,
                                         max_freq=preset.max_hz, min_freq=preset.min_hz, melodia_trick=preset.melodia,
                                         energy_tol=preset.energy_tol)
        if preset.resplit:
            est = _resplit(est, onsets, frames, min_len, preset.resplit)
        times = model_frames_to_time(frames.shape[0])
        res = [(float(times[a]), float(times[min(b, len(times) - 1)]), int(m), float(amp)) for a, b, m, amp in est]
        res.sort(key=lambda x: (x[0], x[2]))
        return res


def _resplit(est, onsets: np.ndarray, frames: np.ndarray, min_len: int, thresh: float):
    """Split decoded notes at re-attacks of the same pitch: interior local maxima of that pitch's onset activation
    >= thresh, at least min_len frames from both ends (a held common tone across a chord change)."""
    from basic_pitch.note_creation import MIDI_OFFSET

    out = []
    for a, b, m, amp in est:
        col = onsets[a:b, int(m) - MIDI_OFFSET]
        cuts = [a]
        for k in range(1, col.size - 1):
            i = a + k
            if col[k] >= thresh and col[k] >= col[k - 1] and col[k] > col[k + 1] and i - cuts[-1] >= min_len and b - i >= min_len:
                cuts.append(i)
        cuts.append(b)
        for s0, s1 in zip(cuts[:-1], cuts[1:]):
            out.append((s0, s1, m, float(np.mean(frames[s0:s1, int(m) - MIDI_OFFSET])) if len(cuts) > 2 else amp))
    return out
