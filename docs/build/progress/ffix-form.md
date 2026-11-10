# ffix-form progress (final fix pass: honest section labels)
## Done
- Read issues: S09 (rap over-labelled chorus), W4V2-JEREMY-HOOK-VERSE, W4V2-FORMRULE-NARROW.
- Dev runner out/_wip/ffix-form/devrun.py <tag> <song folders...> (structure only, cached upstreams of w4fix-analysis-r2 / w4verify-analysis-r2 folders; ~10 s/song).
  Run: MVH_RUN_OFFLINE=1 powershell.exe -NoProfile -File scripts/run.ps1 python out/_wip/ffix-form/devrun.py v1 <folders>
- structure 1.5.0: _chorus_evidence() (recurrence >=2 runs, share <=0.55, allin1 margin >=0.15; near-repeat rescue; fallback to
  allin1 next-best non-chorus label; sandwiched singleton -> bridge; hook rule verse->chorus), additive sections.label_evidence[],
  form rule without the vmin floor (param default 0.0). v1 results: Newton 0/14 chorus, Jeremy 7/18 + hook fixed, synth sr22 fixed.
## Next
- all synth variants + megafauna + versatile; unit tests; decisions F-form.md; gate M2 -SkipE2E; optional CC tracks; report.
- v2/v3: all 11 synth variants truth labels; tempo105 (copied to out/_wip/ffix-form/synth_tempo105, harmony+structure via devchain.py) truth labels;
  MEGAFAUNA/Versatile (+gain copies) sections+EDM identical; Jeremy coda rule (non-recurring run after last chorus -> outro).
- unit tests tests/unit/structure/test_form_labels.py (7) + stop_bar param test updated: 29 pass. decisions docs/contract/decisions/F-form.md written.
## Next
- gate M2 -SkipE2E (log out/_wip/ffix-form/gate.log); report.
- Gate M2 -SkipE2E PASSED (out/_wip/ffix-form/gate.log). Report docs/build/reports/ffix-form.md written. DONE.
