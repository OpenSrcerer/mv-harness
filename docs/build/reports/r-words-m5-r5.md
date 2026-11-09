# r-words-m5-r5 report (R-WORDS round 5 / W3 verify of M5 Words)

Scope: verify R4-1 (fixed by fixer-m5-r4, M5-D54/D55), look for regressions, re-run M5 on two real songs.
No real lyric text appears in this report, the tests or the probes.

## Verdict: fail (2 majors)

### R5-1 (major): R4-1 is only partly fixed
- `test_rw5_r4_colon_lyric_lines.py` passes (5/5), but the fix is narrower than the finding.
- In `lyrics/text.py::_scan_labels`, the lone `Name:` candidates are accepted when `recurring or strict`.
  The `recurring` branch never runs `_strict_name`, which is the pronoun and verb check, or the Title Case guard.
- If one colon-ending sung line occurs twice with different text after it, EVERY candidate in the file becomes a marker.
  Two examples:
  - `I said to John:` sung before two different quotes. This is the R4 example with one recurrence.
  - Title Case `She Said:` / `He Said:`.
- Result (txt and synced LRC alike): 4 of 7 lines kept, and the deleted lyric text becomes the speaker hints
  (`probe_markers.py`).
- Test: `tests/review/M5/r-words/test_rw5_r5_recurring_colon_lines.py` (4 fail; the battle guard passes).

### R5-2 (major): voices crashes on a speaker who has only short lines
- In `voices/core.py::run`, `hints` is built from the embedded items only (>= `min_item_s`).
- Short items are then labelled with `hints.index(it["solo"])`, and with `hints.index(pt)` for joint parts.
- A speaker with only short lines raises `ValueError`, and the stage fails. Examples: a battle announcer's 0.6 s
  shout, or a joint shout that names a singer with no long line.
- Test: `tests/review/M5/r-words/test_rw5_r5_short_hint_crash.py` (2 fail; the guard passes).
- It is reachable with user-supplied Genius-style battle text. The cached LRCLIB text for newton has no labels,
  so it does not fire on the real runs.

### Minors (docs/review/M5-r-words.md, Round 5)
| id | finding |
|---|---|
| r5-m1 | `hint_parts` splits one act's name into several singers (`Tyler, The Creator` and similar names). |
| r5-m2 | `All:` / `Him:` / `Her:` duet markers that each occur once stay as sung lines, while `Dear John:` / `Dear Mary:` are accepted as markers. |
| r5-m3 | A lone `(x2)` after a block repeats only the block's last line. |
| r5-m4 | The S03/S07 integration tests still read the pre-fix integrator folders, and the S03 part-2 test cannot pass under M5-D52. |
| r5-m5 | r3-m1, r2-m1 and r2-m2 are still open. |

## Real-song re-runs (no regression)
- Driver: `out/_wip/r-words-m5-r5/scripts/m5drive.py`, run through `drive.sh`. It uses the integrator's cached upstream
  and runs lyrics, voices and lipsync in a heavy slot.
- Every number matches fixer-m5-r4:

| song | grade | G1 | G2 | lines / words | voices | mouth frames > 0.1 |
|---|---|---|---|---|---|---|
| newton-vs-nye | B | 0.8786 | 0.7537 | 53 / 479 | 4 | 12185 |
| jeremy | B | 0.7705 (raw 0.6917) | 0.7835 | 40 / 194 | 1 | 22838 |

- Jeremy's tail warning is present: `vocals_after_last_line_s` 75.45.
- Leak scan (`leak_scan.py`) of every non-lyrics output and drive log: 0 hits for both songs.

## Tests run
- `pytest tests/review/M5` (models skipped): 57 pass, 6 fail. The 6 failures are exactly the new R5-1 and R5-2 tests.
- `pytest tests/unit/{identity,lyrics,voices,lipsync}`: 118 pass with tests/review/M5/r-words.
- Integration `tests/integration/M5`: 3 fail. These are the pre-fix integrator folders plus the S03 part-2 design
  issue (r5-m4); 2 pass.
- ruff on `tests/review/M5/r-words`: clean.
