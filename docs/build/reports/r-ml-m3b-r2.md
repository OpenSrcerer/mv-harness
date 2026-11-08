# r-ml-m3b-r2: R-ML review of M3b (round 2)

## Verdict: pass. Both round-1 majors are fixed, and no new blocker or major was found.

| round-1 finding | status | how verified |
|---|---|---|
| R-ML-M3b-1: CLAP prompts embedded in a padded batch with no attention mask | fixed | `Clap.text` now runs each prompt alone (batch 1, no padding), for the synth sub-types, the neutral prompts and the user terms. The review test passes. On Versatile, the synth sub-type argmax moved from 148/158 frames `synth_bass` to 7/28/56/67 (pad/lead/arp/bass). |
| R-ML-M3b-2: piano floor of 10 % of the song dropped short piano parts | fixed | The floor is now 1 s of activity; CED only picks CRNN vs basic-pitch; a warning is written. The review test passes. Synthetic song end to end: piano 0 -> 25 notes (18 correct, P 0.72) through the basic-pitch fallback. |

What I ran:
- `pytest tests/review/M3b/r-ml`: 3 passed (401 s). `pytest tests/unit/instruments tests/unit/notes`: 24 passed. ruff on the M3b paths: clean.
- Synthetic song: I copied the round-1 folder to `out/_wip/r-ml-m3b-r2/synth`, then ran `mvh analyze <folder> --only spectral,rhythm,notes,vocals --force notes,vocals`
  and, separately, `--only instruments`. Results: bass F1 0.858, piano 25 notes (P 0.72; recall is limited upstream because the separate_hq piano stem is silent from 17 to 37 s), vocal range G3-A4.
- Determinism: re-running instruments, notes and vocals gave byte-identical results for all 17 M3b output files.
- Real songs: in the real `stem_activity` output (builder-m3a), piano is `present: false` on all 4 songs, so the lower floor adds no hallucinated piano notes there.
  On a copy of `builder-m3a/versatile`, I ran `--only instruments` (log in `out/_wip/r-ml-m3b-r2/versatile.err`).

New findings: two minors, in docs/review/M3b-r-ml.md under "Round 2":
- r2-m1: round-1 minor m1 persists. The synth sub-type softmax at T = 0.01 is still near one-hot (0.849 of frames on the synthetic song, 0.778 on Versatile).
- r2-m2: the 1 s floor and its warning are unreachable in the pipeline, because `stem_activity` already requires 2 s of activity. A piano part with `present_energy` true but `present` false is dropped without a warning.

Note: the fixer did not finish the gate. I checked its unconfirmed steps that touch M3b myself: ruff, the instruments unit tests and determinism all pass. The vocals code is unchanged since round 1.
