# r-adversary report (W4 independent reviewer, lens R-ADVERSARY)

Full review: docs/review/W4-adversary.md. Progress log: docs/build/progress/r-adversary.md. No lyric text appears
here. `scripts/lyricscan.py` finds 0 matches in my files.

## Verdict: fail. Blockers: 0. Majors: 10, each with a failing test. Minors: 14.

### What I did
- **Real songs.** I re-measured the open W3 seams on the post-UD2 runs (`out/_wip/ud2-kick/<slug>`):
  - S06, S16, S17, S18 and S19;
  - minors m3, m4 and m5;
  - Newton's lyrics grade.
- **Independent checks on the real songs:**
  - tempo by autocorrelation of the stems;
  - vocal activity from the stems' own RMS;
  - kick and hat positions against the beat grid;
  - key against the chords and the bass notes;
  - brief and manifest numbers traced back to their source files.
- **Perturbations.** I ran 7 perturbed copies of the synthetic song at the max profile and scored them against the
  generator truth: ±12 dB, 48 kHz, MP3, a 0.9x time-stretch, an a cappella, and silence. Mono, the 10 s clip and the
  delay were dropped because r-platform's runs held the heavy slots.
- **UD2.** I ran the fallback twice: a whole run with `kick_source=mix`, and the drums stage alone on MEGAFAUNA's
  cached upstreams.
- **UD1.** I probed `parse_intent` with ordinary ways of typing a template.

### What survives the attack
- Beats, downbeats and tempo are exact under every edit.
- MP3 decoding is gapless.
- Kick, snare and toms are stable, and so are the key, the lyrics grade, the word F-score and the voice count.
- Silence degrades gracefully.
- The brief and manifest numbers trace correctly to their sources.
- UD2's main path works: the lib, the manifest, the brief and the fallback switch are consistent.
- UD1 never turned free text into a rule.

### Majors (tests in tests/review/W4/adversary/)

| ID | Owner | One line |
|---|---|---|
| W4A-GAIN | M2 allin1/structure | -12 dB: verse/chorus become inst. +12 dB: the bridge and build start one bar late |
| W4A-STABLE | M2 structure (+M1 dynamics) | 0.9x tempo loses both EDM roles; 48 kHz moves the outro one bar |
| W4A-ACAP | M1 spectral (+M3a QA, M2 choreo) | An a cappella gets 13 agent kicks, no QA flag, and 7 `drum` hit points |
| W4A-KICKCURVE | M3a drums | Under the mix fallback, the `drums.kick` curve still follows the stem kicks (0.47 / 0.28 agreement) |
| W4A-UD1 | M6b intent.py | Tab indent, a trailing indented sentence, or a blank line after `do_not:` turns every hard rule into a note |
| W4A-VOCPHR | M3b vocals | MEGAFAUNA: vocal phrases cover 19 % of the sung line time (S04 is half fixed) |
| W4A-S16 | M5 voices | Newton's backing span has 22 % backing-stem support; two mouths are open for 2.1 s |
| W4A-S17 | M2 choreo (+M3a) | Groove ids: MEGAFAUNA 48 for 62 bars, with 61 distinct kick/snare patterns |
| W4A-S18 | M2 rhythm | Newton: 76 % of the snares on beat 3, yet `feel = normal` (needs the decision) |
| W4A-S19 | M3a drums | Jeremy's hats are 37 % on the grid; the hats that hits.high confirms are 88 % on the grid |

Resolved or not real: S06 (as decided by UD2), m3 (0.2 s now).

### Files
- Tests:
  - tests/review/W4/adversary/conftest.py
  - tests/review/W4/adversary/w4a_support.py
  - tests/review/W4/adversary/test_w4a_ud1_do_not.py
  - tests/review/W4/adversary/test_w4a_real_seams.py
  - tests/review/W4/adversary/test_w4a_ud2_kick_curve.py (slow, about 12 s)
  - tests/review/W4/adversary/test_w4a_perturbations.py
- Test results: 17 fail as intended, 4 controls pass, ruff is clean.
- The real-song tests read the newest max folder per song. `$MVH_REVIEW_RUNS` overrides it, so after the fixers' re-run,
  point it at the new folders.
- Runs, probes and comparisons: out/_wip/r-adversary/.

### Notes for the fixers
- **Perturbation tests.** They read out/_wip/r-adversary/<name>. To re-check a fix, delete the folder and its
  `.done.json` and re-run `run_queue.ps1 -NameList <name>`. One synth max run takes about 8 minutes on a free machine.
- **Contract changes.** W4A-GAIN suggests a level-normalised analysis copy for allin1 (and other level-dependent
  models). That is a stage-internal change; no contract change is needed.
- **W4A-ACAP** needs the UD2 QA rule to cover the case "mix kicks with no drum-stem kick at all", and fewer invented
  kicks on vocals.
