# r-words-m5 progress (independent reviewer, M5 Words, lens R-WORDS)

## Done
- started fresh (no prior progress file)

## Next
- read PLAN/SPIKE/CONTRACT/catalog/stages; run synth + real; write failing tests

## Commands
## Gotchas
- 1: synth runs (out/_wip/r-words-m5/synth-{lrc,txt,lines,shift*}); scripts in out/_wip/r-words-m5/scripts (run_m5.py, score_synth.py)
  - txt path median 20 ms OK; offsets +-4 s detected and flagged OK
  - FINDING A (major): line-synced LRC (exact times, no word tags) -> L008 misplaced 5.6 s, overlaps L009, grade A.
    causes: emissions blank before 30 s seam with 2 s ctx (probe_emissions.py: ctx4 fixes), group window tail runs
    into next group's first line, repair rejects (0.5x inflated old score). probe_seams.py running for generality.
  - probe_seams.py: words ending <3 s before a 30 s seam: score 0.51-0.61 (prod ctx 2 s) vs 0.67-0.70 (ctx 6 s), 5-10% < 0.1
- 2: probe_logic.py: FINDING B (major) one-off "Word:" lines become speaker labels (word deleted, hint persists, 2 -> voices hints k=2)
  FINDING C (major) hallucination filter keeps "Thank you for watching.", otter.ai, "Copyright WDR 2021" (asr_only path adds them)
- real runs started in background: out/_wip/r-words-m5/real-{newton-vs-nye,jeremy}.log
- 3: real newton (B, offset -1.32, 4 voices = W0 blocks + announcer, 4 mouth channels OK) and jeremy (22859144, B,
  last word 218.1 s, 1 voice) runs done. FINDING D (major): per-line realign duplicates neighbour audio (jeremy L037/L039,
  debug_jeremy.py) -> test_rw5_line_realign_duplicates.py (pure, fails). tests written: speaker_labels, hallucination,
  alignment_synth (models), line_realign_duplicates.
- 4: FINDING E (major): LRCLIB instrumental duplicate beats lyrics entry; instrumental_hint blocks transcription
  -> test_rw5_lrclib_instrumental.py (pure + models; both fail). minor probes: probe_hold.py (3.08 s hold), probe_tokens.py
  (1999 -> cardinal), override id drift (logic).
- 5: DONE. tests/review/M5 -> 12 failed (intended), 3 passed (guards), 55 s; ruff clean.
  docs/review/M5-r-words.md (minors m1-m10), docs/build/reports/r-words-m5.md written. Structured summary returned.
