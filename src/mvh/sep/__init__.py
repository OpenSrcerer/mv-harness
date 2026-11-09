"""Separation helpers shared by ``separate_fast``, ``separate_hq`` and the sep worker (owner M3a).

Import rule (PLAN §3.3): modules here import only the stdlib and numpy at module level, so the sep worker env
can import them; onnxruntime (main env) and torch / audio-separator (sep env) are imported lazily inside
functions.

* ``invariants``  stems-sum residual, least-squares gains, exactness checks (numpy).
* ``demucs``      demucs-onnx through the array route with our own ORT session (main env).
* ``hq_worker``   the separate_hq worker job: BS-RoFormer-SW, Mel-RoFormer vocals, karaoke, DrumSep (sep env).
"""
