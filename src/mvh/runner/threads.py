"""Thread control for stage processes (PLAN §3.3 "Process model"). Stdlib only (the sep worker uses it too).

* ``thread_env(n)``: the variables set in a child's environment BEFORE anything is imported
  (OMP/OPENBLAS/MKL/NUMBA/VECLIB/NUMEXPR thread counts, MVH_THREADS).
* ``install(n)``: post-import hooks, so whichever library a stage imports is configured the moment it loads:
    - onnxruntime: ``SessionOptions`` is replaced by a subclass with intra_op_num_threads = n and
      inter_op_num_threads = 1, and ``InferenceSession`` gets those options when a caller passes none;
    - torch: ``set_num_threads(n)`` and ``set_num_interop_threads(1)``;
    - ctranslate2: model classes default to ``intra_threads = n`` (faster-whisper passes 0 = "default").
  Stages can also read ``ctx.threads`` and pass it explicitly.
"""

from __future__ import annotations

import importlib.abc
import os
import sys
from typing import Callable

__all__ = ["THREAD_VARS", "thread_env", "install", "configure_loaded", "applied"]

THREAD_VARS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMBA_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)
_N = 0
applied: dict[str, int] = {}


def thread_env(n: int) -> dict[str, str]:
    n = max(1, int(n))
    env = {v: str(n) for v in THREAD_VARS}
    env["MVH_THREADS"] = str(n)
    env["TOKENIZERS_PARALLELISM"] = "false"
    return env


# ------------------------------------------------------------------------------------------- patches
def _patch_onnxruntime(mod) -> None:
    n = _N
    base = mod.SessionOptions
    if getattr(base, "_mvh_patched", False):
        return

    class SessionOptions(base):  # type: ignore[misc, valid-type]
        _mvh_patched = True

        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.intra_op_num_threads = n
            self.inter_op_num_threads = 1

    mod.SessionOptions = SessionOptions
    try:
        from onnxruntime.capi import onnxruntime_inference_collection as coll  # type: ignore

        sess = coll.InferenceSession
        orig = sess.__init__
        if not getattr(orig, "_mvh_patched", False):

            def __init__(self, path_or_bytes, sess_options=None, *a, **kw):
                if sess_options is None:
                    sess_options = SessionOptions()
                orig(self, path_or_bytes, sess_options, *a, **kw)

            __init__._mvh_patched = True  # type: ignore[attr-defined]
            sess.__init__ = __init__
    except Exception:  # noqa: BLE001
        pass
    applied["onnxruntime"] = n


def _patch_torch(mod) -> None:
    try:
        mod.set_num_threads(_N)
    except Exception:  # noqa: BLE001
        pass
    try:
        mod.set_num_interop_threads(1)
    except Exception:  # noqa: BLE001  (raises if parallel work already started)
        pass
    applied["torch"] = _N


def _patch_ctranslate2(mod) -> None:
    n = _N
    models = getattr(mod, "models", None)
    if models is None:
        return
    for name in ("Whisper", "Wav2Vec2", "Wav2Vec2Bert"):
        cls = getattr(models, name, None)
        if cls is None or getattr(cls, "_mvh_patched", False):
            continue

        def make(c):
            class Patched(c):  # type: ignore[misc, valid-type]
                _mvh_patched = True

                def __init__(self, *a, **kw):
                    if not kw.get("intra_threads"):
                        kw["intra_threads"] = n
                    super().__init__(*a, **kw)

            Patched.__name__ = c.__name__
            Patched.__qualname__ = c.__qualname__
            return Patched

        try:
            setattr(models, name, make(cls))
        except TypeError:
            pass
    applied["ctranslate2"] = n


_HOOKS: dict[str, Callable] = {
    "onnxruntime": _patch_onnxruntime,
    "torch": _patch_torch,
    "ctranslate2": _patch_ctranslate2,
}


class _Loader(importlib.abc.Loader):
    def __init__(self, inner, hook):
        self.inner, self.hook = inner, hook

    def create_module(self, spec):
        return self.inner.create_module(spec)

    def exec_module(self, module):
        self.inner.exec_module(module)
        try:
            self.hook(module)
        except Exception:  # noqa: BLE001  (a failed patch must never break the import)
            pass


class _Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        hook = _HOOKS.get(fullname)
        if hook is None:
            return None
        for f in sys.meta_path:
            if f is self:
                continue
            try:
                spec = f.find_spec(fullname, path, target)  # type: ignore[attr-defined]
            except (AttributeError, ImportError):
                continue
            if spec is not None and spec.loader is not None:
                spec.loader = _Loader(spec.loader, hook)
                return spec
        return None


def install(n: int) -> None:
    """Set the thread env vars (for libraries that read them late) and hook onnxruntime/torch/ctranslate2."""
    global _N
    _N = max(1, int(n))
    os.environ.update(thread_env(_N))
    if not any(isinstance(f, _Finder) for f in sys.meta_path):
        sys.meta_path.insert(0, _Finder())
    configure_loaded()


def configure_loaded() -> None:
    """Apply the patches to libraries that were imported before ``install``."""
    for name, hook in _HOOKS.items():
        mod = sys.modules.get(name)
        if mod is not None:
            try:
                hook(mod)
            except Exception:  # noqa: BLE001
                pass
