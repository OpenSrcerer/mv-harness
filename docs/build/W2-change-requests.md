# W2 change requests and open issues (for the W3 integrator)

Collected from every W2 builder and fixer report: the final structured result of each step.
Change requests touch files the module did not own (runtime, contract, pyproject, other modules). Open issues are the agents' own notes.
Some items are stale because a later fixer or another module already resolved them: verify each one before applying it.

## M1

### build:M1 (builder-m1, status done)
**Change requests**
- CR-M1-1: add allin1 (or a re-published section list) to the dynamics deps so the SPIKE's allin1 fallback can run; the guarded code path already exists.
- CR-M1-2: fold the additive optional fields (env, rise_db, viz, kick_conf, the per-part evidence) and meta/dynamics.json into catalog.py.
- CR-M1-3: change the hits.* registry range from 0..1.5 to 0..1, since the viz envelope is clamped to 1.
**Open issues**
- Gate unit step: tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs still expects rhythm to be a stub; the test owner needs to update it (it fails for every module).
- Gate determinism step: 36 non-M1 files are not reproducible across runs: rhythm tables (bars/beats), sections, notes.*, lyrics, voices, lipsync, mood, meaning, brief, viewer, manifest and the shared curves/core.f32. Owners: M2/M3b/M4/M5/M6.
- The contract synth fixture's drum one-shots end abruptly, which adds broadband clicks that the viz flux reads as onsets. Onset F1 against the fixture truth is therefore unreliable (0.34-0.64); the faded one-shots in tests/synth/m1 score 0.96-1.0. The fixtures owner should fade them.
- Kick-band hits include bass-note attacks (viz semantics); consumers should filter on kick_conf or viz.
- Small crash-only impacts (+0.47 LU) are not detected as dynamics impacts.
- Real-song dynamics have no ground truth; drops and parts were only checked for plausibility against W0 notes and allin1.
- The allin1 fallback in dynamics cannot run until CR-M1-1 lands; the 4-bar-grid fallback is used meanwhile.

### fix:M1:r1 (fixer-m1, status partial)
**Change requests**
- Update tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs now that rhythm is implemented.
**Open issues**
- Gate unit step fails on tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs (asserts rhythm.run is still a stub); the W3 integrator must update that frozen test or the gate's unit set.
- Gate e2e/determinism steps did not finish in my session (machine contended); rerun scripts\gate.ps1 M1 once the machine is quiet.
- Fixture-song kick events now pass P>=0.85 and R>=0.9, but about 13 events still sit 30-400 ms off a real kick (mistimed where a bass or hat onset precedes the kick in the 400 Hz low band). A precise kick onset in dense mixes needs a better localiser.
- Quiet-master gate shortfall is relative to -6 dBFS sample peak (param gate_margin_db now means that reference); the real-song kick counts vs the viz reference were not re-measured after the B1 change.

### fix:M1:r2 (fixer-m1-r2, status partial)
**Change requests**
- W3 integrator: fuse spectral hits.kick with the drums stage's DrumSep kick stem. Spectral cannot depend on it (deps are frozen), and it would resolve the fixture-song kick-vs-bass-onset ambiguity that band envelopes cannot.
- tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs asserts rhythm is still a stub; update it now that rhythm is real.
- Determinism of the full e2e run: 28 of 180 files differ across two analyze runs (lyrics, lipsync, voices, vocal curves and others). Owners of the ML stages should check them. Spectral is bit-identical.
**Open issues**
- Fixture-song kick tests (tests/review/M1/r-dsp/test_rdsp_kick_events.py::test_kick_events_on_the_contract_fixture_song and test_rdsp_r2_kicks.py::test_kick_events_on_the_contract_fixture_song_meet_plan) still fail. I do not think the tests are wrong; I could not reach F1 0.95 from band-envelope evidence. A cross-validated gradient-boosting classifier on 20 features reached F1 0.87 at best on this song.
- Pitch drop separates the fixture's kicks from its bass notes, but only 9 % of Jeremy's kicks show it, so it cannot be made mandatory without gutting real songs.
- Syncopated 16th kicks 121 ms apart under a bass note on the same hat: the groove-with-bass recall is about 0.73, down from at least 0.85 before the fix. This is the cost of not doubling kicks on hats.
- MEGAFAUNA viz-flagged events 327 vs the viz reference 464. Its DrumSep kick stem is unusable (67 unambiguous kicks), so I could not check whether the dropped ones are real kicks.
- The gate's unit step fails on tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs, because rhythm is no longer a stub. The determinism step fails on 28 files from other modules' ML stages. Neither is M1's.

## M2

### build:M2 (builder-m2, status done)
**Change requests**
- CR M2-1: moments.d is catalogued as required number|null, but the events envelope types any d as a number, so null can never validate. cues writes 0.0. Make d nullable for kind:event, or make moments.d a plain number.
- CR M2-2: run_stub copies cache-only matrices with writer.copy, so stub records have no matrices entry and Upstream.matrix('activations') fails. M2 reads the raw file via mvh.stages.allin1.read. Stubs should call writer.matrix instead.
- CR M2-3: in madmom-infer 0.2.0, RNNBeatTrackingObservationModel.log_densities calls np.asarray(..., ndmin=1), which numpy 2.5 rejects. rhythm subclasses it as a workaround. Needs an upstream fix or a vendored patch.
- CR M2-5: tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs asserts that mvh.stages.rhythm.run calls run_stub. It fails every module's gate now that rhythm is real. It should test a stage that is still a stub, or test the stub mechanism directly.
- CR M2-6: cues.json stays 63-118 KB on real songs because every frozen field is required. Add an optional tiers 1-3 view (events/cues.major.json), or make tier-4's null fields optional.
- CR M2-4 (info): tables/sections.csv level/mean_lufs and the impact/stop/silence cues need the dynamics stage; they are null on the real fixtures.
**Open issues**
- The gate cannot pass until three things outside M2 are fixed: the contract stub test (CR M2-5), the ruff errors in tests/review/M4, and nondeterministic separation (M3a), which also changes the downstream files.
- Structure without informative allin1 labels misses section changes carried only by harmony. On the full-pipeline synthetic song boundary F is 0.67 (allin1 found only 2 segments there). The structure unit tests run on a fixture whose allin1 stub encodes the true sections, so they are optimistic. The correction hook is the structure.boundaries override.
- The first section can be a single intro bar before the phrase grid (S01 on MEGAFAUNA and Jeremy). This is deliberate, but a choreographer may want it merged into S02.
- MEGAFAUNA's tempo level is a judgement call: 105.1 BPM chosen, with 139.9, 84.0, 209.7 and 52.5 kept as override alternatives. It is now flagged tempo_trackers_disagree for the user to confirm.
- On the real fixtures there are no drums or dynamics outputs, so choreo runs its own percussive classifier and RMS intensity (status degraded), and sections.csv level/mean_lufs and the impact/stop cues are null. This resolves once those stages are in the pipeline.
- cues.json is 63-118 KB on the real songs, mostly tier-4 beat references (see CR M2-6).
- The real-song test has not been re-run end to end since the dict-key fix. The out/_wip MEGAFAUNA rhythm folder predates the new tempo_trackers_disagree flag, so check_chain fails its flag assertion on that folder only; the pytest-run output has the flag.

### fix:M2:r1 (fixer-m2, status partial)
**Change requests**
- CR M2-7 (W3, src/mvh/contract/conventions.py): move 'pinned' to the front of CUE_KIND_PRIORITY. The cues stage works around the current order locally by promoting a merged pin to kind 'pinned'.
- CR M2-5 (still open): update the obsolete test tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs, which asserts that rhythm.run calls run_stub.
- Other modules' ruff errors: the unused or unsorted-import fixes in src/mvh/sep/fit.py, src/mvh/stages/drums/core.py and tests/review/M5/r-words/test_rw5_alignment_synth.py, which fail the gate's ruff step for every module.
**Open issues**
- Gate M2 does not exit 0: tests/unit/contract::test_stub_files_are_stubs (CR M2-5, W3 must update it), ruff errors in other modules' files (sep/fit.py, stages/drums/core.py, tests/review/M5), and the determinism re-run failed in spectral (KeyError 'kick_step_db', M1's stage). The determinism check of the M2 stages themselves was not completed.
- Repeat groups on the synthetic song are still imperfect: intro and verse both land in group A, where the truth has them in separate groups. The review tests only require the boundaries (F >= 0.95) and chorus#1 == chorus#2, and both pass.
- The melodic-fingerprint repeat feature and the merge_keep_strong parameter (1.4) are tuned on the synthetic song only. They have not been checked against the real songs, which have no ground truth.

### fix:M2:r2 (fixer-m2-r2, status partial)
**Change requests**
- tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs: drop rhythm (and any other implemented stage) from the stub list (contract-owned test, stale).
- Determinism: the M3 separation owner should make separate_fast/separate_hq and the vocal stems byte-deterministic (seeds, deterministic ops), or the gate's diff should exclude float-noisy stem-derived files.
**Open issues**
- Gate unit step fails on tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs: it still asserts that rhythm.run contains 'run_stub', which is stale now that rhythm is implemented. This is a contract-owned test; the W3 integrator should remove rhythm (and any other implemented stage) from its stub list.
- Gate determinism step fails with 34 of 180 files differing between two analyze --force runs. None are M2 outputs. The files are stems/*.flac, meta/separation|stems|voices|instruments, curves/core|stems|vocal|instruments_1hz, lyrics/*, lipsync/*, events/instruments|singing|stem_activity|vocal_*|voice_*, notes/vocals.mid, meaning/input.json, manifest.json and viewer.html. The likely root is separation or vocal-stem nondeterminism (M3-owned) propagating downstream.
- Group letters and 8-bar versus 4+4 splits shift slightly on real-song replays, with no regressions seen; there is no ground truth for those songs.

## M3a

### build:M3a (builder-m3a, status done)
**Change requests**
- tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs asserts that rhythm (M2) is still a stub and now fails every module's gate. It needs updating now that real stages have replaced the stubs.
- Determinism: tables/beats.csv and bars.csv (rhythm or allin1, M2) differ between two --force runs, and everything downstream follows (structure, cues, mood, lyrics, meaning, viewer, manifest, curves/core.f32). The M3a outputs and the htdemucs stems that allin1 reads are bitwise identical, so the divergence starts in M2.
- mvh.runner.locks: stage-level heavy-slot waiters poll every 15 s, while other holders re-acquire within 2 s. The 15 s waiters starve: separate_fast waited up to 31 min. A FIFO ticket or a shorter poll would fix it.
- Optional: register the pytest 'real' marker in the project config. M3a registers it only in its own conftests.
**Open issues**
- Hat F1 (0.749) and cymbal F1 (0.615) on real DrumSep stems of the synthetic song are below the PLAN thresholds; on the generator stems they pass. A spectral-flux onset path for the hi-hat stem might recover the soft closed hats that follow an open hat.
- On MEGAFAUNA, whether vocals are present is decided by the cross-model vote alone (conf 0.30, so not present). M3b/M5 should combine conf with the tagger and lyrics as planned.
- perc is always empty because DrumSep has no percussion class.
- Gate unit and determinism steps fail only on non-M3a items (see change requests 1 and 2).

### fix:M3a:r1 (fixer-m3a, status partial)
**Open issues**
- F2 is not fixed. On the generator's clean drum stem the classifier path gives kick 0.977, snare 0.967, tom 1.000, hat 0.793, cymbal 0.444 against gates of 0.9/0.9/0.7/0.9/0.7. About 25 closed hats of the drop sit under the decaying snare tail in the mixed stem with no onset, and a hat under a snare and a ride under a snare differ by about 0.3 dB in every band ratio I tried. A rule that separates them would be a threshold fitted to the synthetic samples, so I did not add one. The review test is not wrong; the PLAN gate looks unreachable for the mixed-stem classifier. Decision for the integrator: relax the classifier-path gate in PLAN/the review test, or fund a real source-separation fallback for the htdemucs-only case.
- The drumsep hat margin is thin (0.918 against 0.9) and ROCm separation is not bit-reproducible, so a re-run can land slightly differently.
- scripts\gate.ps1 M3a cannot exit 0 for reasons outside M3a: the tests/unit/contract stub test, the ruff error in the spectral stage, and determinism differences in other modules' curves (spectral fails with KeyError kick_viz_excess_db).
- Minor findings not done: m1 (provenance lists declared but unused models and has no sha256, needs the runner and provenance schema), m2 (guitar/piano 'confirmation' from htdemucs other is not independent), m3 (per-alternative agreement in meta/stems.json), m5 (piano activity under-detected), m8 beyond mono (no per-segment lead/backing confidence).
- The classifier cross-check inside the drumsep path (classifier_agrees evidence) now runs the heavier classify; no accuracy issue seen, only a few seconds more per song.

### fix:M3a:r2 (fixer-m3a-r2, status partial)
**Change requests**
- W3 integrator: update tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs. It still asserts that rhythm.run contains 'run_stub', and M2's real implementation broke it. Point it at a stage that is still a stub, or remove the assertion; this blocks gate.ps1 for every module.
- W3 integrator: decide the intended behaviour of the drum classifier path, and revise or retire tests/review/M3a/r-ml/test_drums_classifier_path.py to match (see open_issues).
**Open issues**
- F2 not fixed: test_drums_classifier_path calls core.classify directly and requires hat >= 0.9 and cymbal >= 0.7 on the clean mixed drum stem. That is not reachable with the single-stem classifier (hat 0.793, cymbal 0.444). I only mitigated it: on the classifier path vel is scaled by 0.45, vel_raw is kept, and a drums:low_confidence fallback is flagged. The reviewer's other suggested fix was to leave hat and cymbal out of events on that path, which would also fail an F1 test. The test needs revising or an explicit decision; tests/review is not mine to edit.
- scripts\gate.ps1 M3a fails at the unit step because tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs asserts rhythm.run still contains 'run_stub'. M2 has since replaced that stub. This is stale-test drift in the contract tests, not an M3a defect, and I may not edit that file.
- Gate steps after unit (ruff, contract check, validate, e2e analyze, determinism) were not reached in the final gate run, and the last source change (classifier_only toms source set to drumsep) was only verified by the review and unit tests. Only the newton real-song e2e was run; a second real song was not.
- The 44.1 kHz and 48 kHz cymbal scores still rest on small margins (about 1-2 hits per class).

## M3b

### build:M3b (builder-m3b, status done)
**Change requests**
- CR-M3b-1: let vocals read lyrics coverage (file:lyrics/lyrics.json lines t/d, as an optional dependency), or combine vocal.voiced with lyric coverage downstream, as the brief asks for presence
- CR-M3b-2: add instruments as a dependency of notes (read curve:inst.piano) so the piano gate no longer needs its own CED pass
- CR-M3b-3: promote notes.piano_mode, vocals.present, vocals.style and instruments.vocabulary to overrides.json keys so the viewer's edit mode can set them
- CR-M3b-4: fold the additive fields (vocal_range basis/spoken_pitch/style, CLAP index descriptions) into catalog.py as a minor bump
- Integrator: update or remove tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs (it asserts rhythm is a stub), which fails every module gate
**Open issues**
- The gate exits 1 only because of the stale contract test test_stub_files_are_stubs, which is outside the M3b paths
- The real-song fixtures have no stem_activity, instruments or spectral outputs. The real-song numbers use a reference stem_activity overlay (tests/synth/m3b/stem_overlay.py) until M3a's stage runs upstream
- Register (male/female, baritone/tenor) is a weak, low-confidence cue; Jeremy sits on the baritone/tenor border
- Jeremy's sustained extremes (E3/C#5) are wider than W0's conservative G3-G#4 because of harmony bleed in the lead stem; p10/p90 (A3-A4) is the better tessitura for agents
- CED tags low sung verses as speech (28 % of Jeremy). For singing-dominant leads the range statistics use every voiced frame, so the range is not affected
- No tests/review/M3b folder exists yet (the gate's review step was SKIP)

### fix:M3b:r1 (fixer-m3b, status partial)
**Change requests**
- Update tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs. It still expects mvh.stages.rhythm to be a stub, but rhythm is implemented, so the gate's contract unit step fails for every module.
**Open issues**
- Gate not confirmed: the tests/unit/vocals step ran for more than 90 minutes with the machine loaded by other agents' heavy jobs, and I stopped it. Rerun scripts\gate.ps1 M3b when the machine is quiet.
- tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs asserts that mvh.stages.rhythm.run contains 'run_stub'. It now fails because the rhythm module has been implemented. The test is in the frozen contract area, so I left it. It will make the gate fail for any module until it is updated.
- I did not re-check the CLAP-derived synth_* sub-type curves, the minor finding m1 that the reviewer suggested checking after the fix. Please recheck them on Versatile.

## M4

### build:M4 (builder-m4, status partial)
**Change requests**
- CR-M4-1: add harmony and mood sections to overrides.json (harmony.key, harmony.chords) and to STAGE.override_keys so viewer corrections can be applied.
- CR-M4-2: docs/CONTRACT.md lists a mean_db field under chords that the catalogue does not declare; harmony does not write it.
- CR-M4-3: tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs asserts the rhythm stub is still a stub and fails now that M2 has landed. Update or drop it; it also fails gate.ps1 for every module that includes tests/unit/contract.
- Provide dynamics fixtures in tests/contract/real-<slug> so mood can run on real songs without overlay fixtures.
**Open issues**
- gate.ps1 M4 not completed end to end: the unit step fails on the unrelated shared contract test, and the later steps (review, contract check, validate, e2e, determinism) were not run.
- Heavy slots were contended by the other agents, with 10+ minute waits; the 600 s default pytest timeout fails tests that wait for a heavy slot.
- Valence is inherently low confidence. Key confidence stays at 0.5 on loop-based songs (megafauna, versatile).
- Per-chord human correction needs CR-M4-1.
- Mood on real songs ran with overlay dynamics fixtures built by out/_wip/builder-m4/mkfx.py, because the real fixtures lack dynamics.

### fix:M4:r1 (fixer-m4, status partial)
**Open issues**
- The gate cannot pass for M4 because of other modules' files. ruff fails in src/mvh/sep/fit.py (ambiguous variable name l), src/mvh/stages/drums/core.py:359 (unused variable k) and tests/review/M5/r-words/test_rw5_alignment_synth.py (unsorted imports).
- tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs fails because the rhythm stage is no longer a stub (M2's files).
- The determinism step differs on events/drum_hits.json (M3a drums), manifest.json and viewer.html, none of them M4 outputs.
- The S-KEY score fed to the ensemble is linear p, not log p as the suggested fix said. With log p one window's runner-up at about 1e-4 dominated the z-score and moved the A minor to D minor modulation boundary 8.5 s early, so test_modulation_is_found_near_the_truth failed. Linear p matches the old exported behaviour.
- docs/SPIKE.md and bench-music sections 3 and 7 still say S-KEY is flat. I am not an owner of those files, so the integrator should amend them. Only the methods.skey.note text and docs/contract/decisions/M4.md were updated.

### fix:M4:r2 (fixer-m4-r2, status partial)
**Open issues**
- gate.ps1 M4 exits non-zero because tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs requires rhythm to be a stub, but M2 has implemented it (needs a W3 integrator update to that test).
- Real-marked review tests (real S-KEY/lv-chordia on noise) and the gate's e2e/determinism stages were not run.
- No new unit tests added for absent/unsure/sure S-KEY paths; covered by the review tests only.

## M5

### build:M5 (builder-m5, status done)
**Change requests**
- CR-M5-1: add 'ingest' to lyrics deps and to PLAN_DEPS in tests/unit/contract/test_catalog_dag.py (embedded_lyrics.json is a cache-only ingest output, D32); the lyrics code switches over automatically
- CR-M5-2: fold M5's additive fields into catalog.py: lyrics source.format/offset_s/offset_applied_s/version_mismatch, gate, asr (incl. vad, vad_retry), alignment, lrclib, words[].flags values; voices meta extras; voice_spans role/source
- CR-M5-3: tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs asserts mvh.stages.rhythm.run still calls run_stub; M2 replaced that stub, so the contract unit folder now fails every module's gate
- CR-M5-4: gate determinism fails upstream (stems/drums/*.flac from M3a drums, curves/stems.f32, events/sections.json differ between two analyze --force runs); M5 files differ only downstream of these
**Open issues**
- MEGAFAUNA lyrics are grade D: MMS mean token score is 0.22 on the processed EDM voice, and coverage 0.68 is above the 0.60 stable-ts trigger, so stable-ts never runs. The user should check it in the viewer or supply a timed --lyrics file.
- tests/contract/real-* fixtures have no stem_activity, so the M5 harness synthesises stem.*.active with the PLAN rule; real M3a stem_activity may differ slightly. M5 ORs it with the stem's own envelope (M5-D14b), which limits the impact.
- Versatile (an instrumental) still gets 0.7 s of ungated mouth on a vocal chop; this could be suppressed when instrumental=true if the user prefers.
- g2p-en emits a SyntaxWarning on import (library issue, harmless).
- The ffmpeg Vulkan whisper draft path (no VAD) has only been exercised on the synth song.

### fix:M5:r1 (fixer-m5, status partial)
**Change requests**
- CR-M5-1: add 'ingest' to lyrics deps and the PLAN_DEPS row in tests/unit/contract/test_catalog_dag.py.
- CR-M5-3: tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs must not use rhythm (no longer a stub).
- CR-M5-4: upstream nondeterminism in M3a drums stems / curves/stems.f32 / events/sections.json breaks the gate determinism check for every module.
- Spectral stage fails with KeyError 'kick_own_step_db' in the e2e analyze (owner of spectral).
**Open issues**
- Gate M5 cannot exit 0 for reasons outside M5: spectral KeyError 'kick_own_step_db' breaks the end-to-end analyze; tests/unit/contract test_stub_files_are_stubs asserts rhythm is still a stub; run-to-run determinism fails upstream (stems/curves).
- Minor review findings m1-m5, m7-m10 not addressed this round (double sustain hold, year reading, override id order, stable-ts mapping, draft-path scratch, backing envelope, ungated fallback voice, tie rule, hint copy).
- 'ingest' not yet added to lyrics deps (m6/CR-M5-1); left for W3 to avoid touching contract DAG test.
- Real-song re-run (jeremy, newton) not done after the alignment fix; expected to remove the 4 interleaving pairs and the 9.44 s word but unverified.

### fix:M5:r2 (fixer-m5-r2, status partial)
**Open issues**
- scripts/gate.ps1 M5 cannot exit 0 until tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs is updated: it still pins rhythm as a stub and M2 replaced it. Not an M5 file.
- The gate's review, ruff, contract, validate, e2e and determinism steps did not complete in my session; they were waiting on heavy slots held by other agents. Please re-run the gate at integration.
- Newton alignment after the seam fix measured only through the review test (G2 >= 0.75, G4 <= 0.12 pass); the full end-to-end grade was not re-run.
- Unit test test_lrc_repeats_offset_and_labels was changed to repeat its label, because the one-off 'Ann:' it asserted is exactly the finding-B behaviour the review test forbids.

## M6a

### build:M6a (builder-m6a, status done)
**Change requests**
- Update tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs, because rhythm and other stages are now real.
- M2, M5 and M6b should read the managed block in meaning/intent.md and apply the overrides.json keys the viewer writes (beat offset, BPM, downbeat phase, section boundaries and labels, lyric timing, voice-to-character mapping), as described in docs/contract/decisions/M6a.md.
**Open issues**
- Gate e2e and determinism results are not yet known; check out/_wip/builder-m6a-gate.log.
- The contract unit test test_stub_files_are_stubs needs updating by the integrator, since rhythm is no longer a stub.
- A literal file:// open was not verified. The Browser pane refuses file://, so only the equivalent inline-bundle code path was exercised, via ?inline=1.
- The stem mixer uses media elements, so it is not sample-accurate. Mobile layout is only a media-query fallback.
- Edit panel limits: BPM preview regenerates a constant grid from the first beat, and lyric text and word text are read-only.
- The real override round trip (stages re-running and the change appearing in the output) depends on M2, M5 and M6b reading the managed intent block and applying the override keys.

### fix:M6a:r1 (fixer-m6a, status partial)
**Change requests**
- tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs: drop rhythm from the stub list, or assert on a different stage.
- Determinism: upstream stage outputs differ between runs; the viewer.html diff may disappear once those are stable.
**Open issues**
- The test_stub_files_are_stubs assertion in tests/unit/contract needs updating by the integrator, now that rhythm has a real run().
- The determinism diff across upstream stages (stems, notes, meta, tables, meaning) is outside my paths. The integrator should check whether the separation and ensemble outputs can be made byte-stable.
- The viewer was checked only through the review browser tests and the gate. I did not do a fresh manual Claude_Browser pass this round.

### fix:M6a:r2 (fixer-m6a-r2, status partial)
**Open issues**
- The gate did not exit 0. The unit step fails on tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs, which is not M6a's file: it needs updating now that rhythm is real.
- The gate hung at the review step (tests/review/M6a) for about 30 minutes. The same tests pass in 53s when run directly. The cause is probably contention with other agents (browser or heavy slot); I did not diagnose it.
- A background gate run I started may still be running (output at %TEMP%\gate2.log). I could not safely kill it; the integrator may need to.
- The viewer page does not yet display the new warning field on /api/intent for a non-UTF-8 intent.md. The page loads and the POST error shows as a toast.
- Gate ruff failures in other modules' tests (23 errors, mostly outside M6a) are not mine.

## M6b

### build:M6b (builder-m6b, status done)
**Change requests**
- CR-1: tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs assumes rhythm is still a stub; it fails every module gate.
- CR-2: add the PLAN §10 flags to `mvh analyze` (--intent, --meaning-draft, --no-lyrics-to-agents), and merge cli_params on re-run instead of replacing them.
- CR-3: fold the M6b additive fields and outputs into catalog.py (singing conf/source/review, meaning field_sources and related fields, frames/{fps}fps.deforum.json, frames event columns).
- CR-4: make PyYAML a direct dependency (the intent parser uses yaml.safe_load).
- CR-5: have M5 voices use mvh.stages.meaning.intent.parse_intent for the user's character count.
- CR-6: confirm finalize keeps on-demand frames outputs from earlier runs listed in the manifest.
- CR-7 (M3a/W3): separate_hq drum sub-stems (drumsep on ROCm) differ between two `--force` runs, so 44 downstream files differ and the determinism gate fails; needs deterministic GPU settings or a fixed seed.
- CR-8 (runtime): `--only` silently drops a stage with stale upstream, and on-demand stages are missing from run.json when not run; print the reason on stdout and in run.json.
**Open issues**
- 15 failing reviewer tests (R-CONTRACT F1-F3, R-WORDS F1-F6: draft fields shown as the user's in the brief and zoom, the unfenced YAML template parsed as free text, do-not rules turned into section feels, the voice mapping absorbing a second voice, draft citation text echoed in warnings, the Remotion recipe include list) are left for the fix round.
- A clean `mvh frames` CLI run on a current runner-built folder is not done yet: the folder went stale twice because other modules edited params during W2. Re-check in W3 once the code is stable.
- `--draft anthropic` has not been tested against the live API (offline build, no key).
- The real-song fixtures lack mood, cues, choreo and instruments (voices only for newton); the W3 full runs are the real check of brief content on real songs.
- The section zoom labels harness-derived audio facts as 'draft' even when no draft exists, which may confuse readers; this overlaps R-CONTRACT F2.

### fix:M6b:r1 (fixer-m6b, status partial)
**Change requests**
- Update tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs, since rhythm is no longer a stub.
- M5 or W3: make the voices stage parse the 'voices: [..]' lists of the intent YAML template for proposed_character_id. M6b no longer depends on it but the proposals would be more accurate.
- M4 or W3: find the nondeterminism in key and chord output (events/key.json, meta/key.json, events/chords.json), which makes the gate's determinism step fail. Also check whether viewer.html and manifest.json differ only because of it.
**Open issues**
- Gate unit step fails in tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs: it asserts that the rhythm stage is still a stub, but rhythm is now implemented. It needs a W3 integrator fix and is not an M6b file.
- Gate determinism step fails: events/key.json, meta/key.json and events/chords.json differ between two runs of the same input. That looks like nondeterminism in the harmony stage (M4). viewer.html and manifest.json differ too. brief.md also differs; I did not confirm that it is only derived from the key and chord data. Please check this one.
- The gate's ruff step failed in the gate run, but ruff check src tests passes when run alone afterwards. Re-run the gate once the other modules settle.
- Gate wall time is about 25 minutes under load; the e2e step alone took about 15 minutes, probably because other agents were using the heavy slots at the same time.
- The voices stage (M5) does not parse the voices lists in the YAML template. M6b now ignores a proposal that would add a voice to a character whose voices the user named, so the duet no longer collapses. M5 or W3 should still make the voices stage parse those lists.

### fix:M6b:r2 (fixer-m6b-r2, status partial)
**Change requests**
- W3/M7: song.meaningAt(t) in lib/mvh.js and lib/mvh_load.py should also return the section's field_sources, so code-path agents can tell draft fields in user sections without re-reading meaning.json. The skill now documents the meaning.json route.
- W3: update tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs, since rhythm and other stages are real now.
**Open issues**
- Gate unit step fails in tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs because rhythm is no longer a stub. That test needs W3 to update it.
- Gate determinism step fails: 54 of 180 files differ between two forced runs. The list includes upstream outputs (meta/tempo.json, meta/structure.json, lyrics/lyrics.json, events/beats.json, events/sections.json). The meaning files and brief.md differ too. I did not verify that M6b is deterministic given identical upstream, so the integrator needs to check that. The upstream non-determinism should go to M1/M2/M3 owners.
- The gate's ruff step failed on one over-long line in tests/unit/frames/test_frames_cli.py. I fixed it after the run and ruff check src tests is now clean, but the gate was not re-run (a full run takes about 20 minutes of heavy slots).
