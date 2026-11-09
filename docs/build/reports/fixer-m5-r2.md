# fixer-m5-r2 report (M5 Words, review round 2)

Fixes (decisions M5-D31 revised, D35-D38 in docs/contract/decisions/M5.md):
- R2-1 text.py: LRC ID tags are never speaker headers; a file is "labelled" only via `[Section: Name]` or a recurring label / bare `[Name]`; bare headers with instrumental words are never speakers. Unit test test_lrc_repeats_offset_and_labels now repeats its label (the old one-off label was finding B itself).
- R2-2 core._asr_repair: window clipped to neighbouring lines' placed words, ASR matches beyond that edge skipped; warning if repair leaves more interleaving pairs.
- R2-3 asr.py: credit strings unconditional; generic outro phrases (see you next, please like/share, bare bye/thank you, copyright) only with a second signal (no_speech, logprob, word p, activity, audio edge).
- R2-4 align.MmsAligner.emissions: SPIKE 2 s recipe restored for all central frames; the 3 s before each seam replaced by frames from a seam-centred window (8 s context). Real newton: offset test and G2/G4 gate test pass.
- R2-5 voices.cluster.estimate_k: k = 1 when best silhouette < 0.2 (min_best_silhouette). Real jeremy test passes.

Tests: tests/review/M5 passes (synthetic); real r2 tests (newton gate, jeremy voices): 3 passed; unit lyrics/voices pass.
Gate: see docs/build/progress/fixer-m5-r2.gate.log. tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs fails because M2 replaced the rhythm stub (not M5's file; needs integrator update).

Gate status at hand-over: fixture PASS; unit FAIL only through tests/unit/contract::test_stub_files_are_stubs (M2 replaced the rhythm stub; identity, lyrics, voices, lipsync unit pytest exit 0); the review/ruff/contract/validate/e2e/determinism steps were still queued behind other agents' heavy slots (log: docs/build/progress/fixer-m5-r2.gate.log). Separately verified: tests/review/M5 + unit lyrics/voices passed (exit 0), ruff clean on lyrics/voices.
Change request: update tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs (stop pinning rhythm as a stub); add 'ingest' to lyrics deps (M5 brief permission) if not yet applied.
