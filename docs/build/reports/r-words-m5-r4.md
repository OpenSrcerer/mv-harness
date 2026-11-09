# r-words-m5-r4: R-WORDS re-review of M5 Words (round 4, W3 verify)

Verdict: **pass-with-fixes**. One new major remains, R4-1: a regression of the R3-3 fix, with a failing test. Every
round-3 major and both integrator seams owned by M5 (S03, S07) are fixed in the code. No real lyric text appears in
this report.

## Verification of the earlier findings
| id | status | how verified |
|---|---|---|
| R3-1 section words in any position | fixed | review tests pass. `_section_word` checks every word (`[Final Chorus]`, `[Rap Verse]`, `[Pre Chorus]`, `[Post Chorus]`). Bare `[Name]` headers need >= 2 names with one recurring, and inline labels must recur with different text. Probes with other variants behave the same way. |
| R3-2 no_speech_prob second signal | fixed | `_generic_suspect` uses no_speech_prob only together with avg_logprob < -0.7; the review tests pass and the guards still drop real hallucinations. |
| R3-3 `[Name:]` / `Name:` markers | fixed, **with a regression (R4-1)** | `[Name:]`, `Name:` and `NAME:` give hints. However, any sung line of 1-4 words that starts and ends with a capital and ends with `:` is now deleted as a marker. |
| R3-4 unbracketed headers | fixed (a long tail of formats remains, minor r4-m1) | `Verse 1:`, `CHORUS`, `Chorus x2`, `(Chorus)` and `Verse 2: Name` are headers. `*Chorus*`, `Chorus (repeat)`, `1st Verse:` and `(x2)` alone on a line are still sung. |
| S03 jeremy graded D | fixed | My own run on the integrator upstream (`out/_wip/r-words-m5-r4/jeremy`): grade B, G1 0.7705 (raw F1 0.6917; W0 measured 0.762), G2-G7 pass, 1 voice, no words after 218.1 s. The tail warning (75 s, no lyric text) is raised. The outro is wordless: the cached W0 VAD whisper pass has 0 words after 218 s, and the VAD-free gap retry keeps 3 words in 92 s. The second S03 integration test (`sung_after < 20`) cannot pass under M5-D52 by design (r4-m3). |
| S07 versatile mouth opens | fixed | Fixer output: `vocal.mouth_open` max 0.0 (was 55 frames > 0.1). The M5-D49 suppression applies only when lyrics are instrumental and there are < 8 s of wordless vocals. |

## Regressions and real-song runs
- `out/_wip/r-words-m5-r4/scripts/m5drive.py` is the fixer's driver changed to read `out/_wip/integrator/<slug>`
  read-only and write to my folder.
- newton-vs-nye: grade B (G1 0.8786, G2 0.7537, G5 0.98, G7 0.944), offset -1.31 s, 4 voices (estimate). The output
  is identical to the fixer's run word for word.
- jeremy: grade B, 1 voice. The output is identical to the fixer's run.
- The leak scan of every non-lyrics file and the run log is clean on both songs (0 hits).
- `pytest tests/review/M5 tests/integration/M5 tests/unit/{lyrics,voices,lipsync,identity}`: 113 passed, 7 skipped,
  3 failed.
  - The 3 failures are the integration tests S03 (2) and S07. They read the integrator's pre-fix run folders and
    clear only after the integrator re-runs M5. S03 part 2 also needs a test change (r4-m3).
- G2 on newton is 0.7537 against the 0.75 threshold (round 3: 0.758). This is upstream drift (new separate_hq), not
  an M5 code change; the fixer's run is identical.

## New findings
- **R4-1 (major)**: `text._plain_header` deletes sung lines that end with a colon as speaker markers. Test:
  `tests/review/M5/r-words/test_rw5_r4_colon_lyric_lines.py` (4 fail, 1 guard passes). The cases are sentence-case
  and Title Case text in both TXT and synced LRC; LRCLIB synced lyrics are parsed by `parse_lrc`, which calls
  `_header` and then `_plain_header`.
- Minors r4-m1 to r4-m5 are in `docs/review/M5-r-words.md`, section "Round 4":
  - r4-m1: the header long tail;
  - r4-m2: a joint `[Chorus: A & B]` label adds a third voice;
  - r4-m3: the S03 part-2 test and the stale integrator outputs;
  - r4-m4: the canonicalised G1 is compared with a threshold measured on exact F1;
  - r4-m5: r3-m1, r2-m1 and r2-m2 are still open.

## Commands
- Text tests: `scripts/run.ps1 python -m pytest -q -p no:cacheprovider tests/review/M5/r-words/test_rw5_r4_colon_lyric_lines.py`
- Real runs: `sh out/_wip/r-words-m5-r4/scripts/drive.sh newton-vs-nye jeremy` (it resumes, skipping songs that are DONE).
