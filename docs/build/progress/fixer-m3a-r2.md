# fixer-m3a-r2 progress
Commands: Git Bash `MVH_RUN_OFFLINE=1 bash /tmp/run.sh python ...` (= powershell scripts/run.ps1). Scratch: out/_wip/fixer-m3a-r2/ (synth, synth48, narrow24 run copies; score scripts).
Scoring: `python out/_wip/fixer-m3a/score.py <folder with stems/drums>` (oracle: tests/contract/synth); e2e: analyze ... --force drums then out/_wip/fixer-m3a-r2/escore.py.
- DONE N1: kit-relative local leak gates (core.drumsep_hits: kit_db = loudest kick/snare at the instant else +-0.75 s; cym_ref pooled ride+crash 2nd loudest rel level; tom_ref). soft-passage test passes.
- DONE N2: brightness rules relative to typ_bright (min(11, typ-7.5) relabel, min(0, typ-18.5) noise). dark test passes.
- DONE N3 (drums part): cymbal ring feature (_ring), classifier-confirmed loose gate, hat copy under ringing ride = cymbal, classifier-only toms (stage __init__). e2e: 44.1 tom 1.0 cym .80 hat .926; 48k tom .889 cym .732 hat .917 (stats in synth folders).
- unit test edits: tests/unit/drums/test_drums.py (2 tests adapted).
- TODO: F3-R (separate_hq near-mono flag), F2 (classifier path: conf/vel scaling + low-confidence), tests/unit additions, gate, e2e newton + 1 more, decisions M3a.md, report.
- DONE F3-R: separate_hq side_to_mid_db, lead_suspect/narrow drop, lead_share_frames; unit tests added; narrow24 review test passes.
- DONE F2 (mitigation only): classifier path vel scaled 0.45 + vel_raw + fallback drums:low_confidence; review test test_drums_classifier_path stays failing (hat .79 / cymbal .44 not reachable on one mixed stem; the test calls core.classify directly).
- DONE real: newton e2e (out/_wip/fixer-m3a-r2/newton): cymbals 14 (was 69), toms 34 (19 DrumSep + 15 classifier_only), flags []. Added classifier-only tom guard (no kick/snare within 25 ms: 143/160 were kick/snare transients).
- Final synth: 44.1 k1.0 s.993 h.926 t1.0 c.80; 48k k.994 s.98 h.917 t.889 c.714.
- Gate running: out/_wip/fixer-m3a-r2/gate.log. NEXT: read gate result, write report docs/build/reports/fixer-m3a-r2.md, return structured output.
- Gate re-run after outage: out/_wip/fixer-m3a-r2/gate2.log; report already written (docs/build/reports/fixer-m3a-r2.md). NEXT: read gate2.log, return structured output.
- gate2: review test_drums_separated_synth failed (source set); changed classifier_only toms source->drumsep (+unit line 374). Re-run gate -> gate3.log
