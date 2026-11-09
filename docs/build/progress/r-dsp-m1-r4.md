# r-dsp-m1-r4 progress (round 4 / W3 verify reviewer, M1 Signal, lens R-DSP)

## Done
- started 2026-11-09; no prior progress file.

## Next
- read W2-gate, W2-open-findings, fixer progress (latest M1 fixer), SEAMS; run review suite; verify B1-R2, R3-B1, R2-M1, R2-M2, S06.
- suite: review M1 + unit spectral/loudness/dynamics: 99 pass, 12 skip (3m22)
- probes in out/_wip/r-dsp-m1-r4/ (kinds.py = kick designs; probe_kinds*.py; dbg*.py)
- NEW-1 candidate: non-fixture kick designs over a held bass note (kicks_over_bass texture): acoustic R .42 (bass .5), .08 (bass .7);
  tr808 R .27-.40 and events 11-21 ms EARLY. Without bass all designs 1.0. Cause: body route decay>=8 / f1>=68 on total level;
  sweep route needs a sweep starting >150 Hz (dsp.kick). Fixture/909/distorted/lowtuned/trap808 fine.
- NEW-2 candidate (confirmed): global kick_rel_db=12 (median of ALL accepted kicks' body_db) drops every kick in a section >=14 dB
  quieter (quiet intro 0/16 at -14 dB; 16/16 with kick_rel_db=60) and fade-out kicks below -12 dB. probe_quiet*.py
- S06 check (s06.py, mega_strong.py on fixer-m1-r3 outputs): MEGAFAUNA strong DrumSep kicks (vel>=0.5, n=165, not bleed) matched by
  hits.kick only 0.21 (old 0.27). At the 131 missed: drums stem 30-150 rises 11.4 dB, bass stem falls 8 dB (sidechain duck), mix flat
  (-1.8 dB). Mostly 140-220 s (drop sections). Jeremy/Versatile/Newton strong-kick recall .95/.99/.99 (good).
  Next: synthetic sidechain-duck test; rerun (bg b7hvo7tic) megafauna+newton into out/_wip/r-dsp-m1-r4/<slug>.
- earlier findings B1-R2, R3-B1, R2-M1, R2-M2: FIXED (review suite passes; variants: fixture 16ths 160/180 ok, tight 200/220 under crash ok,
  rock pairs 120/170 ok; fixture 180 under crash .927 = minor). Edges: 22.05/48/96k, mono ok; kick at t=0 missed (minor).
- NEW-3 (S06 synthetic): sidechain-ducked sub bass: fixture kick R .5 (bass .7), 0 (bass 1.0); 909 R .06 at .7. Cause: kick_route
  'adds' rule (max(low_ex, body_ex, body_add) >= 1 dB) false under ducking although attack 6-9, glide ~2, click 49. probe_duck.py
- Next: write tests/review/M1/r-dsp/test_rdsp_r4_kicks.py (+ rdsp_r4_signals.py), verify failing.
- Milestone: tests/review/M1/r-dsp/test_rdsp_r4_kicks.py (+ rdsp_r4_signals.py) written: 6 FAIL as intended
  (acoustic/tr808 over held bass; sidechain fixture .7/1.0, 909 .7; quiet intro -14 dB). ruff clean.
- Next: rerun results (megafauna/newton), S06 integration test, minors to docs/review/M1-r-dsp.md Round 4, report.
- minors so far: m20 kick at t=0 never a candidate (find_peaks skips edges), m21 fixture 16ths 180 BPM under crash F1 .927; 28.7 s MEGAFAUNA drop loss not a finding (allin1/edm_roles: no drop there; impact 1.7 LU)
- m22: Jeremy 56/560 hits.kick (10%) have silent kick stem (-54.7 dB) and a 20 dB snare-stem rise: snares as kicks, kick_conf .61 vs .78 (improved from ~107). jeremy_snare.py
- dyn_harness.py (in-process, integrator bars): megafauna/newton loudness, impacts, silences, stops identical to integrator; megafauna
  28.7 weak drop hint lost, decay_tails 3->2 (matches fixer). m23: dynamics role_score (contract unit 0..1) reaches 1.2 for builds
  (0.4a+0.3b+0.3c+0.2): newton 1.104, versatile 1.071 in integrator outputs (pre-existing, not from fix).
- Next: Round 4 section in docs/review/M1-r-dsp.md, report, StructuredOutput.
- DONE: report docs/build/reports/r-dsp-m1-r4.md, Round 4 minors in docs/review/M1-r-dsp.md; newton rerun stopped (harness used). Only StructuredOutput left.
