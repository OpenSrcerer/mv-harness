# r-ml-m3a: R-ML review of M3a Separation (separate_fast, separate_hq, stem_activity, drums)

Independent reviewer, lens R-ML (PLAN §11). Findings were formed by running the code before the builder report was read
(it was then used only to locate things). No lyric text is printed anywhere.

## Verdict: pass-with-fixes

The separation plumbing is sound: separate_hq reproduces the W0 reference stems, keeps the gain invariants, handles
48 kHz and mono with zero lag, and the CPU fallback works through the stage. Three majors concern what the models
deliver downstream: the drum stage misses the PLAN §7 gates on the stems the separators really produce (the
builder's tests use oracle stems), the classifier fallback misses them even on oracle stems, and the karaoke split
silently routes the lead voice into backing_vocals on mono input.

## Majors (each has a failing test)

| id | location | claim | test |
|---|---|---|---|
| F1 | src/mvh/stages/drums/core.py `drumsep_hits` (+ separate_hq DrumSep) | On the synthetic song run end to end (mix -> BS-RoFormer-SW -> DrumSep -> drums) F1 at +-10 ms is kick 1.000, snare 0.979, **hat 0.749**, tom 0.800, **cymbal 0.615** (PLAN: >= 0.9 / >= 0.7). The crashes at 34.5 s (drop) and 52.5 s (final hit), velocity 1.0, come out as `hat`. Unit tests score only the generator's clean sub-stems (oracle separation). | tests/review/M3a/r-ml/test_drums_separated_synth.py |
| F2 | src/mvh/stages/drums/core.py `classify` | The classifier path (degraded fallback / no sub-stems) is far below the PLAN gates even on the clean generator drum stem: kick .977, snare .943, **hat .795, tom .421, cymbal .160** (on the SW drum stem: hat .787, tom .222, cymbal .242). The unit test relaxes the gate. | tests/review/M3a/r-ml/test_drums_classifier_path.py |
| F3 | src/mvh/stages/separate_hq/__init__.py + src/mvh/sep/fit.py `stereo44` (karaoke step) | A mono song is fed as dual mono to a karaoke model trained on stereo (pan cue). On the synth 17-29 s excerpt the lead lands in backing: lead_vocals SDR 0.52 dB vs 8.31 dB in stereo; lead -18.8 dB / backing -5.1 dB vs the mix; `lead_backing_split: true`, no flag. lyrics/voices/lipsync read lead_vocals. newton-vs-nye (40 s, mono) keeps the lead but backing rises from -30.2 to -17.0 dB. | tests/review/M3a/r-ml/test_karaoke_mono.py |

Suggested fixes:
- F1: score the drum stage on separated stems in the module's own tests; label by spectral shape and decay, not only by the
  sub-stem DrumSep chose (a broadband, slowly decaying onset in the hi-hat stem coinciding with a kick is a crash: re-label
  it as cymbal); recover quiet hats with a spectral-flux onset path on the hi-hat stem (the builder already names it);
  use the full drum stem's high band to confirm or re-label.
- F2: improve the classifier (cymbal decay/brightness, tom pitch tracking) or, when the degraded path runs, emit only the
  classes that meet the gate (kick/snare) and mark hat/tom/cymbal as low confidence and record it in summary/flags.
- F3: detect mono or dual-mono input (L/R correlation > 0.999 or channels == 1) and either skip the split
  (`lead_vocals := vocals`, `lead_backing_split=false`, flag `sep:lead_backing_mono`), or keep it with a flag and a
  per-segment lead-share confidence; also sanity-gate any song where backing carries much more energy than lead.

## Minors
In docs/review/M3a-r-ml.md: m1 provenance (duplicate + unused models, no SHA-256 pin, hard-coded DrumSep licence),
m2 guitar/piano "confirmation" by htdemucs `other` is not independent, m3 MEGAFAUNA vocal verdict hangs on one vote,
m4 faint drum hits keep conf ~0.84 (hat velocity corr 0.26 on separated stems), m5 synthetic piano activity
under-detected (0.079 vs 0.283), m6 separate_hq params unused/unvalidated (`variant_order` string silently ran ROCm),
m7 `gain_gate` ignores polarity, m8 karaoke output least deterministic (ROCm-to-ROCm -43 dB, CPU vs ROCm -40 dB).

## What was run
- Synthetic song end to end: `mvh analyze tests/contract/synth/_truth/synth-song.flac --out out/_wip/r-ml-m3a/synth
  --no-network --only ingest,separate_fast,separate_hq,stem_activity,drums` (ROCm, separate_hq 156 s). Scored with
  `out/_wip/r-ml-m3a/scripts/score_synth.py`: SDR vocals 16.2, drums 18.7, bass 19.7, other 8.8, instrumental 22.1,
  lead 7.1, backing -0.4, piano 2.3 dB; invariants sum -35.3 dB, gains <= 0.03 dB, exactness -150 dB.
- newton-vs-nye end to end (real audio): stems equal the W0 reference to -84..-122 dB; sum residual -36.0 dB; vocals conf 0.989.
- stem_activity on all four real fixtures with the SW vocals vote (`scripts/sa_real.py`): MEGAFAUNA vocals present=false
  (conf 0.298; 0.594 without the SW vote), newton/jeremy/versatile present (0.99/0.99/0.70).
- 12 s excerpts (44.1 kHz, 48 kHz, mono; newton stereo/mono 40 s): zero lag, same SDR; mono karaoke failure (F3).
- CPU variant via `MVH_SEP_VARIANTS=cpu` on the 12 s excerpt: works (333 s), -84..-117 dB vs ROCm, lead/backing -40/-36 dB.
- Review tests: `tests/review/M3a/r-ml/` 4 tests, all failing for the stated reason (F1 two tests, F2, F3). The
  `synth_e2e` fixture runs the five stages through `python -m mvh.cli analyze` (about 3-12 min with slot waits;
  `MVH_REVIEW_M3A_SYNTH=<folder>` reuses a run); `synth_mono_e2e` runs ingest + separate_hq on a mono excerpt (about 50 s).

## Change requests (W3)
- Runner: `models_prov` lists every declared model, including fallbacks that did not run; let stages report the models used.
- Contract: allow `sha256` in `envelope/provenance` models items (the separator revision is a mutable tag).
- `MVH_SEP_VARIANTS` is not part of the cache key (a cached ROCm entry serves a CPU request); intended?
