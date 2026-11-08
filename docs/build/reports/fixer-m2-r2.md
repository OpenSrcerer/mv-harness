# fixer-m2-r2 report (M2 Rhythm, review round 2)

Finding F4-r2 (major): structure missed the synthetic song's chorus#1 and outro and split choruses into different repeat
groups when the upstream is realistic (real allin1, real harmony chroma, real dynamics).

## Root causes found
1. Dynamics segments / impacts / `dyn.novelty` were scored as boundary sources (0.4 + 0.4 + 0.3). Real dynamics
   emitted a segment and an impact at 5.0 s and 42.5 s (not section starts) and none at 17.0 s, creating two false
   splits and masking chorus#1.
2. The end-of-song decay tail got the top novelty (one-sided Foote kernel), producing a 2-bar tail section at 52.5 s.
3. The 17.0 s step (same chords, new groove/arrangement) had too little single-bar evidence to beat the DP cost
   (verse -> chorus#1 ranks below in-section bars on every single feature).
4. Greedy first-fit grouping joined chorus#1 to the adjacent verse, whose arrangement is similar.

## Changes (src/mvh/stages/structure/)
- features.py: `hat` (5-16 kHz percussive flux) curve; `bar_pattern` (kick / onset / hat in 16 slots per bar).
- boundary score: drum-pattern novelty and allin1-embedding novelty added; signal novelty damped at the first/last
  bars; dynamics evidence gated by the bar's own evidence (weak, confirmatory).
- phrase-grid refinement: sections >= 8 bars are split on the 4-bar grid where 4-bar-window novelty of the combined SSM
  (timbre, harmony, embeddings, pattern) >= `split_min_novelty` (0.5).
- repeat groups: agglomerative average linkage, neighbour penalty (`repeat_adjacent_penalty` 0.85), length exponent 0.15.
- meta/structure.json: additive `boundary_components` (per-bar evidence terms, for debugging and overrides).
- New unit tests tests/unit/structure/test_pattern_features.py. Decisions in docs/contract/decisions/M2.md.

## Results
Synthetic song with the recorded real upstream (real allin1 + real harmony [+ real dynamics]): sections 1/9/17/25/34.5/50.5,
boundary F 1.0 in both variants (was 0.909 / 0.615); chorus#1 and chorus#2 share repeat group C, verse is separate.
tests/review/M2 + tests/unit/{structure,choreo,cues} pass (incl. -m real). Real-song replays (structure only, same
rhythm): section counts unchanged (megafauna 17->18, versatile 18, jeremy 19, newton 14); small group-letter and 8->4+4
changes, no regressions seen.

## Caveats
- The 17.0 s evidence is intrinsically weak in this synthetic song (verse and chorus#1 share chords, similar drums); the
  grid refinement threshold (0.5) was chosen with the synthetic song and sanity-checked on the four real songs.
- The bridge is labelled `verse` (structural labels; allin1 labels uninformative): not covered by a test.
