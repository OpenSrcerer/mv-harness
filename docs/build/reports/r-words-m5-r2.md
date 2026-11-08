# r-words-m5-r2: R-WORDS review of M5 Words, round 2

Reviewer: r-words-m5-r2 (independent, PLAN §11, lens R-WORDS). Scope: verify the fixes for round-1 findings A, A2,
B, C, D and E (fixer-m5, M5-D30..D34), then look for new blockers and majors, especially regressions. No production
code was changed. No real lyric text appears in this report, the tests or the probe output.

Verdict: **fail**. A, A2, D and E are fixed. B is not fixed. The fixes introduced two regressions (the C regex
deletes sung lines; the 6 s emission context drops newton, the stress test, from grade B to C). Two more majors
were found: the ASR repair still duplicates a neighbour's word (D's failure mode through another path), and
Jeremy's single singer is now split into 4 voices.

## Status of the round-1 findings

| id | status | how it was checked |
|---|---|---|
| A | fixed | Synth line-only LRC and shifts +2.5 / -4.0 s: all 53 words within 0.46 s, median 20 ms, no crossings, offsets -2.47 / +4.02 found (+4.02 flagged). Jeremy: 0 lines whose words start after the next line (round 1: 4). The group-window cap is general, not test-specific. Its side effect is minor r2-m1. |
| A2 | fixed as specified, but regresses the gate | `MIN_CTX_S = 6` is a floor applied to every call. It improves jeremy (G4 0.072 -> 0.057) but moves newton's scores out of the calibrated gate (new major R2-4). |
| B | **not fixed** | `_file_labelled` counts any bracketed `[x:y]` line as a speaker header, and every LRC ID tag (`[ar:]`, `[ti:]`, `[length:]`, `[offset:]`) is one. An ID-tagged LRC with a one-off `Time:` line behaves exactly as in round 1 (R2-1). |
| C | fixed, with a regression | Credit and outro hallucinations are dropped, and asr_only lines need no_speech_prob < 0.6. The new patterns also drop real sung lines (R2-3). |
| D | fixed in align_groups | The per-line re-alignment is clipped to the neighbouring placements; jeremy L037 no longer duplicates L036. The same failure remains in `_asr_repair` (R2-2). |
| E | fixed | Lyrics rank ahead of instrumental entries; the instrumental flag is overridden when the ASR hears at least 8 words with p >= 0.5. Both round-1 tests pass and the logic is general. |

## New and repeated majors (failing tests in tests/review/M5/r-words/)

| id | finding | test |
|---|---|---|
| R2-1 (B again) | LRC ID tags, and section headers such as `[Guitar Solo]`, make one-off `Word:` prefixes into speaker labels: the sung word is cut, the hint carries forward, and 2 hints make voices force k = 2. | `test_rw5_r2_speaker_labels.py` (5 fail, 1 guard passes) |
| R2-2 | `_asr_repair`: when the ASR misses a word that the next line repeats, LCS pairs it with the next line's occurrence. The repair re-aligns it there: the window is clipped only within the line and the acceptance bar is now <= 0.10. Two lines then claim the same audio, and the crossing check has already run. | `test_rw5_r2_asr_repair_duplicates.py` (1 fail, 1 guard) |
| R2-3 | The NONLYRIC additions (`see you (in the) next`, `please share/like`, `copyright`, whole-segment `bye bye bye` / `goodbye`) drop confident sung segments in the middle of active vocals. | `test_rw5_r2_hallucination_overreach.py` (4 fail, 3 guards) |
| R2-4 | Newton grade B -> C (G2 0.683, G4 0.198 end to end). Cause: the 6 s context changes MMS scores, and the gate was calibrated on 2 s (bench-words §5). Timing against whisper is unchanged: within 0.3 s, 0.963 vs 0.963. | `test_rw5_r2_newton_gate_regression.py` (real; 1 fail, 1 pass) |
| R2-5 | Jeremy (one singer): voices 1 -> 4. The voices code is unchanged; the line spans moved slightly. All silhouettes are 0.09-0.14, yet the best (k = 7) is taken and merge_minor leaves 4. Jittering the round-1 spans by ±0.15 s also flips the result (1 or 2 voices). | `test_rw5_r2_voices_jeremy_split.py` (real) |

## Runs (this round)

| run | result |
|---|---|
| synth, line-only LRC (voices + lipsync too) | grade A, 53/53 words, median 20 ms, max 0.46 s; voices 10/10 lines, 4/4 backing; mouth recall 0.98 / 0.96, false open 3 % / 2 % |
| synth, plain txt; shifts +2.5 / -4.0 s | grade A, same accuracy; offsets -2.47 / +4.02 (> 3 s warned) |
| synth, LRC jitter: L009 +0.5 s (seam), L006 +0.5 s, L009 +0.7 s | all A, same accuracy (the crossing repair rescues the seam case) |
| real-jeremy | LRCLIB 22859144, B (G5 0.975), last word 220.24 s (a held note to ~220 s), 0 crossing lines, **4 voices** |
| real-newton-vs-nye | LRCLIB 3921433, offset -1.305, **grade C (G2, G4 fail)**, 4 voices (announcer + 3), 4 mouth channels |
| probes | ctx 2/6 x clamp on/off on newton and jeremy, with an ASR-agreement check; voices k on round-1/round-2 spans plus jitter; seam-clamp pure probe; label, regex and repair logic |

Privacy: of 26 (jeremy) and 84 (newton) distinct lyric words of 6 or more letters, none appears in any run log,
done.json or summary of this round's runs.

## Commands

```
Git Bash, MVH_RUN_OFFLINE=1:
powershell.exe -NoProfile -File scripts/run.ps1 python out/_wip/r-words-m5-r2/scripts/run_m5.py <fixture> <work> [--lyrics f] [--seed-http out/_wip/builder-m5/h-<slug>] [--stages ...]
.venv/Scripts/python.exe out/_wip/r-words-m5-r2/scripts/score_synth.py <work>      # err_words.py, line_report.py
MVH_SKIP_MODELS=1 .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/review/M5/r-words   # 10 failed (R2-1..3), 16 passed, 7 skipped
MVH_REAL_TESTS=1 powershell.exe -NoProfile -File scripts/run.ps1 python -m pytest -q -p no:cacheprovider tests/review/M5/r-words/test_rw5_r2_newton_gate_regression.py tests/review/M5/r-words/test_rw5_r2_voices_jeremy_split.py   # 2 failed, 1 passed, 67 s
```
Minor findings: `docs/review/M5-r-words.md`, "Round 2" section (r2-m1 .. r2-m5).
