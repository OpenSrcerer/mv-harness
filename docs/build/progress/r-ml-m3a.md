# r-ml-m3a progress (independent R-ML reviewer of M3a)

## Done
- started; reading docs

## Next
- read PLAN/SPIKE/CONTRACT/catalog/stage code; run synth + real; write failing tests for majors

## Milestone 1 (synth end to end done)
- Synth run: out/_wip/r-ml-m3a/synth (mvh analyze --only ingest,separate_fast,separate_hq,stem_activity,drums; ROCm sep 156 s)
- Scoring script: out/_wip/r-ml-m3a/scripts/score_synth.py <outdir>  (SDR per stem, SA flags, drum F1 vs truth)
- RESULT: drums end-to-end on separated stems: kick 1.0, snare 0.979, hat 0.749 (<0.9), tom 0.80, cymbal 0.615 (<0.7)
  -> MAJOR (unit test only scores oracle generator sub-stems)
- separate_hq invariants fine on synth: sum -35.3 dB, gains <0.03 dB, exactness -150 dB
- provenance: separate_hq lists 9 model entries (4 dup + unused htdemucs_6s); separate_fast lists unused htdemucs_6s; no sha256 (minor)
- stem_activity real songs (scripts/sa_real.py <slug> sw): megafauna vocals conf 0.298 present=false (good); guitar conf via htdemucs:other always ~1 (minor/non-informative)
- Edge runs started: out/_wip/r-ml-m3a/edge (44k/48k/mono 12 s excerpts of synth 17-29 s)

## Milestone 2 (failing tests written)
- tests/review/M3a/r-ml/{conftest.py,m3a_rml_util.py,test_drums_separated_synth.py,test_drums_classifier_path.py}
  verified failing (MVH_REVIEW_M3A_SYNTH=out/_wip/r-ml-m3a/synth to reuse my run): F1 hat .749 cym .615; crashes 34.5/52.5 -> hat;
  classifier path clean: hat .795 tom .421 cym .160
- Edge (48k, mono): alignment lag 0, SDR same as 44.1k, invariants pass; mono lead SDR 0.5 dB (karaoke relies on stereo cues) -> minor
- newton real run started: out/_wip/r-ml-m3a/newton-vs-nye (compare vs tests/.cache/real/newton-vs-nye/sep)

## Milestone 3
- MAJOR F3 karaoke mono: tests/review/M3a/r-ml/test_karaoke_mono.py (fixture synth_mono_e2e runs ingest,separate_hq, ~50 s) FAILS: lead SDR 0.52 (stereo 8.3), lead -18.8 / backing -5.1, no flag
- newton full run matches W0 stems (-58..-122 dB; flac clip explains drums -58, .wav twin exists); invariants -36.0 dB
- --param with PowerShell quoting turned variant_order into string "[cpu]" -> stage silently ran rocm (minor: no validation)
- CPU run (MVH_SEP_VARIANTS=cpu) on 12 s excerpt -> out/_wip/r-ml-m3a/edge/out_44k_cpu; compare with scripts/cpu_cmp.py

## DONE
- CPU variant verified (-84..-117 dB vs ROCm; lead/backing -40/-36 dB)
- docs/review/M3a-r-ml.md (minors m1-m8), docs/build/reports/r-ml-m3a.md written
- Remaining: only the StructuredOutput return
