# fixer-m3a-r2 progress
Commands: Git Bash `MVH_RUN_OFFLINE=1 bash /tmp/run.sh python ...` (= powershell scripts/run.ps1). Scratch: out/_wip/fixer-m3a-r2/ (synth, synth48, narrow24 run copies; score scripts).
Scoring: `python out/_wip/fixer-m3a/score.py <folder with stems/drums>` (oracle: tests/contract/synth); e2e: analyze ... --force drums then out/_wip/fixer-m3a-r2/escore.py.
- DONE N1: kit-relative local leak gates (core.drumsep_hits: kit_db = loudest kick/snare at the instant else +-0.75 s; cym_ref pooled ride+crash 2nd loudest rel level; tom_ref). soft-passage test passes.
- DONE N2: brightness rules relative to typ_bright (min(11, typ-7.5) relabel, min(0, typ-18.5) noise). dark test passes.
- DONE N3 (drums part): cymbal ring feature (_ring), classifier-confirmed loose gate, hat copy under ringing ride = cymbal, classifier-only toms (stage __init__). e2e: 44.1 tom 1.0 cym .80 hat .926; 48k tom .889 cym .732 hat .917 (stats in synth folders).
- unit test edits: tests/unit/drums/test_drums.py (2 tests adapted).
- TODO: F3-R (separate_hq near-mono flag), F2 (classifier path: conf/vel scaling + low-confidence), tests/unit additions, gate, e2e newton + 1 more, decisions M3a.md, report.
