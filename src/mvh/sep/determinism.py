"""Deterministic replacement for the Mel-RoFormer ``scatter_add_`` (CONTRACT D47, R4-2).

audio-separator's Mel-Band RoFormer sums the per-band complex masks onto the STFT bins with
``zeros.scatter_add_(2, freq_indices, masks)``. On a GPU that is an atomic floating-point add, so the order of the
additions (and therefore the last bits of every mask, about 1e-7) changes from run to run: the vocals, and through the
karaoke model the lead / backing stems, are not bit-reproducible (NF1). The mask-to-bin map is a constant, so the same
sum is a matrix product with a 0/1 matrix, which has a fixed accumulation order. Torch only at call time.

``deterministic_roformer`` bundles the fixes.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

__all__ = ["deterministic_scatter_add", "deterministic_roformer", "prefer_rocblas", "STATS"]

STATS = {"patched": 0, "fallback": 0}


def _det_scatter_add(orig):
    import torch

    def scatter_add_(self, dim, index, src):
        try:
            ok = (self.is_cuda and self.is_complex() and src.is_complex() and dim in (2, -2) and self.dim() == 4
                  and index.shape == src.shape and index.shape[2] == src.shape[2])
            if ok:
                idx = index[0, 0, :, 0]
                ok = bool(torch.equal(index, idx.view(1, 1, -1, 1).expand_as(index)))   # one map for every batch/stem/frame
        except Exception:  # noqa: BLE001
            ok = False
        STATS["patched" if ok else "fallback"] += 1
        if not ok:
            return orig(self, dim, index, src)
        b, n, f_src, t = src.shape
        f_out = self.shape[2]
        real = torch.view_as_real(src)                                   # b n f t 2
        m = torch.zeros(f_out, f_src, dtype=real.dtype, device=real.device)
        m[idx.long(), torch.arange(f_src, device=real.device)] = 1.0     # unique (row, column) pairs: no race
        flat = real.permute(2, 0, 1, 3, 4).reshape(f_src, -1)
        summed = (m @ flat).reshape(f_out, b, n, t, 2).permute(1, 2, 0, 3, 4).contiguous()
        return self.add_(torch.view_as_complex(summed))

    return scatter_add_


@contextmanager
def deterministic_scatter_add() -> Iterator[None]:
    import torch

    orig = torch.Tensor.scatter_add_
    torch.Tensor.scatter_add_ = _det_scatter_add(orig)   # type: ignore[method-assign]
    try:
        yield
    finally:
        torch.Tensor.scatter_add_ = orig   # type: ignore[method-assign]


def prefer_rocblas() -> None:
    """Take hipBLASLt out of the GEMM path on ROCm. hipBLASLt picks its algorithm from the free GPU workspace, so a
    process holding GPU memory (or a different start state) changed the last bits of a RoFormer run (6e-7, two distinct
    outputs); with plain rocBLAS (Tensile) six of six runs were identical at every memory level (measured). Torch's
    ``preferred_blas_library("cublas")`` alone still routes through hipBLASLt, so rocBLAS's own switch
    ``ROCBLAS_USE_HIPBLASLT=0`` is set as well: call this before the first GEMM of the process (the worker calls it before
    importing torch). A no-op off ROCm / on the CPU variant (the env var is harmless there)."""
    import os

    os.environ["ROCBLAS_USE_HIPBLASLT"] = "0"
    try:
        import torch

        if getattr(torch.version, "hip", None) and torch.cuda.is_available():
            torch.backends.cuda.preferred_blas_library("cublas")   # the name of the rocBLAS backend on ROCm builds
    except Exception:  # noqa: BLE001
        pass


@contextmanager
def deterministic_roformer() -> Iterator[None]:
    """Everything a RoFormer run needs to be bit-reproducible on a GPU: the fixed-order mask sum above and the plain
    ``math`` attention backend. audio-separator lets SDPA pick the memory-efficient kernel for float32 on ROCm, and
    that kernel's tiling / split choice differs from process to process (measured: two distinct outputs of the same
    Mel-RoFormer run, one in three processes), so the stems changed in the last bits (1e-7, -130 dB)."""
    import contextlib

    with contextlib.ExitStack() as st:
        st.enter_context(deterministic_scatter_add())
        try:
            from audio_separator.separator.uvr_lib_v5.roformer import attend
            from torch.nn.attention import SDPBackend

            orig = attend._sdpa_backends
            attend._sdpa_backends = lambda config: [SDPBackend.MATH]
            st.callback(setattr, attend, "_sdpa_backends", orig)
        except ImportError:   # not the sep env (unit tests): nothing to patch
            pass
        yield
