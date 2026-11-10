# Final gate after W4 (`scripts\gate.ps1 all`, 2026-11-10 ~01:00, quiet tree)

Log: out/_wip/orchestrator/gate-all-final.log

| Step | Result |
|---|---|
| fixture, ruff, contract (gen --check), validate, lib-node | PASS |
| unit | **PASS**: 1612 passed, 97 skipped, 1 xfailed |
| e2e | PASS: full analyze of the synthetic song, 248 s |
| determinism | **PASS**: 0 of 183 files differ |
| review | FAIL: 51 failed / 369 passed / 40 skipped |

The 51 review failures fall into four groups.
1. **Stale folders (about 16):** these tests read fixed folders made with pre-W4 code (out/_wip/integrator/*, out/_wip/r-adversary/*): the W3 critic
   grooves/handoffs/hats tests, the adversary's a-cappella and real-seam tests, and some perturbation tests. The fixers report them passing on
   re-analysed copies. They need fresh max runs of those folders to confirm.
2. **Stem-stage level dependence, known and open (about 19):** W4V2-GAIN-DRUMS / STEMACT / VOCALS / SPECTRAL. Under ±6-20 dB the drum-stem kick,
   stem activity, vocal notes and phrases, and the mix onset events still change; their absolute dBFS gates do not use the W4-AN-9 analysis level.
3. **UD1 edge cases, minor (12):** verify-words r2. Rules typed with other bullet glyphs (•, *, en dash, a non-breaking space after the dash),
   and stray lines inside a do_not list, are not surfaced as rules or as an open question.
4. **Small leftovers (about 4):**
   - verify-platform: kept outputs from a different audio, kept-stage flags, a power-cut lock whose pid is now a service process (W4VP-5 family);
   - synth perturbations at tempo 1.05 and 22.05 kHz (narrow verse/chorus form rule);
   - Jeremy's hook-only section labelled verse.

Also open, with no test yet: rap songs are over-labelled `chorus` (docs/review/W3-orchestrator-viewer.md).
