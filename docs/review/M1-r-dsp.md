# M1 Signal review: R-DSP minor findings (r-dsp-m1)

Reviewer r-dsp-m1, lens R-DSP (units, time alignment, frame rules, viz-port fidelity, synthetic-truth tests).
Blocker and major findings are in `docs/build/reports/r-dsp-m1.md`, each with a failing test under
`tests/review/M1/r-dsp/`. The findings below are minor. Each one was checked by running code. The scratch scripts are in
`out/_wip/r-dsp-m1/`.

What holds up (checked independently):
- The viz port tracks the real `viz/js/audio.js`. I drove `AudioEngine.update()` under Node, frame by frame, with
  causal AnalyserNode data (`tests/review/M1/r-dsp/viz_causal.cjs`). Against viz at 100 fps on the fixture song,
  `bands.{bass,mid,high}_viz` and `bands.level` correlate at 0.989 to 0.995. The hit envelopes correlate at 0.90 to
  0.95, after the documented shift. Bass, mid and high onset counts are within 3 % of viz at 100 fps. The time
  alignment is right: the offline frames are centred, and a 1 kHz step at 5.0 s reads -3.0 dB at frame 500.
- Loudness: EBU 3341 #1 to #5, #9 (short-term) and #12 (momentary) are within 0.06 LU (#4 gives -23.055). EBU 3342 #1 to #3 are within 0.2 LU
  and #4 gives 15.00 LU. Integrated loudness is within 0.08 LU of ffmpeg ebur128 on all four real songs.
- The CLI runs spectral and loudness on mono, 48 kHz, MP3, corrupt FLAC, 10 s and unicode-path inputs without errors.

| id | location | claim | evidence | suggested fix |
|---|---|---|---|---|
| m1 | `loudness/r128.py:true_peak` | The stage's own true peak overshoots on EBU Tech 3341 cases 17 and 18, beyond the +0.2 dB tolerance. PLAN §5 says ffmpeg ebur128 *gives* the true peak. | Stereo sines at -6 dBFS, 48 kHz: fs/6 at 60 deg reads -5.62 dBTP, and fs/8 at 67.5 deg reads -5.32 dBTP (expected -6.0). ffmpeg reads -6.0 and -5.9. The excess is Gibbs ringing of the long Kaiser-10 interpolator at an abrupt signal edge, so it also hits a cut-off decode (Versatile loses its last 52 ms) and trimmed excerpts. | Report ffmpeg's true peak (PLAN §5) and keep our own value as an additive field. Otherwise use the BS.1770-4 Annex 2 48-tap interpolator. |
| m2 | `spectral/dsp.py:select_hit_events` (mid/high) | `hits.mid` and `hits.high` events go far beyond what viz registers, and against the fixture's own definition (mid = snare/tom, high = hat/cymbal) they are weak. | Fixture song at ±20 ms: hits.mid F1 0.37 (P 0.30, R 0.50); hits.high F1 0.65 (P 0.84, R 0.53). Events vs real-viz hits at 100 fps: groove 101 vs 23, MEGAFAUNA 521 vs 222, Versatile 351 vs 244, newton 624 vs 476. | The `viz` flag lets readers filter. Document in the catalogue that `hits.mid/high` include non-viz weak attacks, or emit only the viz hits and move the weak ones to an additive field. |
| m3 | `dynamics/detect.py:detect_impacts` | On the scored fixture, impacts have precision 2/5 and recall 2/3. | Truth I001 17.0 (chorus crash), I002 34.5 and I003 52.5. Detected: 5.0, 9.0, 29.0, 34.5 and 52.5, so the chorus entry at 17.0 is missed. | Score impacts on the fixture in a unit test and tune the bass-only term. A crash plus a bass step at a section start should qualify. |
| m4 | `dynamics/stage.py:role_hints` | The fixture build (R01, 25.0-32.5 s) is not separated. It is merged into a 23.5 s 'loud' part (9.0-32.5), and a false 'build' hint is put on 5.0-9.0 s. Jeremy gets a single 96.8 s part (113.0-209.8 s). | `out/_wip/r-dsp-m1/run_synth.py` gives parts (0,5) soft, (5,4) medium build, (9,23.5) loud, (32.5,2) silence, (34.5,8) peak drop, and so on. The fixture's build is a snare roll plus a riser with a flat LU, and the onset-density trend is not strong enough to split it. | Add an onset-density / snare-roll acceleration feature to the novelty matrix, and use the stop at the end of a part as build evidence even without an LU rise. |
| m5 | `dynamics/stage.py:_classify` | A 'silence' part can report rel_lu of -11 LU. | MEGAFAUNA part 94.6-96.1 s is level 'silence' with rel_lu -11.06. Its silence event is 94.59-95.96 s, but the part runs 0.13 s into the drop, and the momentary power mean is dominated by the loud frames at the edges. | For silence parts, take rel_lu from the silence event (or the median momentary loudness inside it), not from the power mean over the part. |
| m6 | `dynamics/*` | `run()` raises ValueError on inputs of 2 s or less. | A 0.5 to 1.5 s tone fails with 'all input arrays must have the same shape'. A 2.0 s tone fails with a shape mismatch, (200,) vs (201,), at `segment.py:325` (intensity filtfilt). A 3 s tone works. | Guard the short-input path: one part, no novelty. |
| m7 | `dynamics` deps | SPIKE says to fall back to allin1 sections, but dynamics cannot read allin1 (frozen deps), so Jeremy-like masters fall back to a 4-bar grid. | The builder already filed CR-M1-1. Listed so the W3 integrator sees it confirmed. | CR-M1-1. |
| m8 | `spectral` onsets / vizState docs | viz's own onset counts depend on the frame rate. The offline port matches viz at 100 fps, not at the 60 fps a browser usually runs. | Real viz, bass onsets on the fixture song: 139 / 168 / 187 / 197 at 30 / 60 / 100 / 144 fps. Offline gives 184. On MEGAFAUNA: viz@60 681, viz@100 772, offline 757. | One sentence in the golden addendum or SKILL: vizState onsets equal viz at 100 fps (about 10 % more than a 60 fps browser). |
| m9 | `spectral/stage.py` spectrum128 vs CONTRACT §5 | The contract says both 'u8 = round(255·value)' and 'same as the R channel of viz bandBytes'. viz writes `bands*255` into a Uint8Array, which truncates. | At most 1 LSB of difference. The stage follows the registry (round). | Contract wording (W3): say 'round', and drop 'same as viz bandBytes' or add 'up to 1 LSB'. |
| m10 | `spectral/dsp.py:analyse_frames` physical bands | The Blackman STFT bands have limited selectivity at low frequencies. The 35-100 Hz `bands.kick_db` picks up out-of-band tones. | A -20 dBFS sine at 110 Hz reads -30.9 dBFS in kick_db (8 dB below the in-band level). At 130 Hz, bands.mid_db reads -29.4. At 160 Hz, bands.bass_db reads -34.9. | Fine for a level feature. Document it. For physical kick/bass dB, a longer (or rectangular-mainlobe) analysis window would separate the bands. |
| m11 | `loudness` mono | A mono file reads 3 LU lower than the same content as stereo: -26.11 vs -23.10 LUFS. This is BS.1770 single-channel behaviour, and ffmpeg agrees. Players upmix mono to both speakers, so the perceived loudness is the dual-mono figure. | Edge cases mono_44k vs stereo_48k (same music). | Decision M1-L3 is defensible. Mention it in `meta/loudness.json` (`channels: 1, dual_mono_lufs`) so readers do not compare mono and stereo songs blindly. |
| m12 | `spectral/stage.py` warnings | Every normal-level song without kick-band energy gets the warning 'quiet master: kick gate set relative to the song (-92 dB)'. | All six CLI edge-case clips (-23 LUFS) warn. This is the major kick-free finding seen from the warning side. | Fixed by the kick-gate fix. Warn only when the song is actually quiet (integrated loudness or sample peak), not when the kick band is. |

## Round 2 (r-dsp-m1-r2)

Reviewer r-dsp-m1-r2 checked the fixes for B1, M1 and M2 by running code. The scratch scripts are in
`out/_wip/r-dsp-m1-r2/`. Blockers and majors are in `docs/build/reports/r-dsp-m1-r2.md`, each with a failing test in
`tests/review/M1/r-dsp/test_rdsp_r2_kicks.py`.

Fix status:
- **M1 (kick gate on kick-free material): fixed.** Piano and snare-plus-hats material gives 0 kick events at 0, -12, -20
  and -30 dBFS peak. Quiet kicks over bass keep recall 1.0 down to -40 dBFS. The quiet-master rule now uses the sample
  peak.
- **M2 (drop hint lost after the downbeat snap): fixed.** On the breakdown-into-drop signal, the drop part is hinted
  'drop' at grid offsets from 0.3 to 1.7 s (2 s bars). On Versatile the drop hints are 51.72 and 162.48 s (round 1 had
  only 162.48).
- **B1 (kick doubling): not fixed.** The isolated kick-over-bass texture now scores F1 1.0, but closed hats bring the
  doubling back. The fix also introduced a recall regression (refractory). Both are in the report.

Minor findings, round 2:

| id | location | claim | evidence | suggested fix |
|---|---|---|---|---|
| m13 | `spectral/stage.py` `viz` flag with the quiet-master gate | For a quiet master, `viz=true` is set on hits that the real viz never registers. viz gates on the raw kick band at -46 dB, but the flag is computed with the lowered gate. | Kicks over bass scaled to -30 and -40 dB: 44 events, all `viz=true`. The real `audio.js` in Node registers 0 hits at both levels (47 at 0 dB). | Compute `viz_hit` with viz's own -46 dB gate, or document that `viz` means "viz logic with the song-relative gate". |
| m14 | `docs/contract/decisions/M1.md` | The round-1 fix rows reuse IDs that are already taken: a second M1-S6 (kick events) and a second M1-D3 (`t_event`). They sit below the change requests, outside the tables. M1-S5 still says the kick onset score uses 0.5 × the click step, but the stage uses `kick_click_w` = 1.0. | Read the file. | Renumber them (M1-S12, M1-D10), move them into their tables and update the M1-S5 wording. |
| m15 | `dynamics/stage.py` boundaries vs `t_event` | The drop *part* still starts at the snapped downbeat. With a grid 0.95 s off, the part starts at 28.95 s for a drop at 28.0 s. `t_event` is kept internally but never written. | `out/_wip/r-dsp-m1-r2/probe_m2.py` gives parts (28.95, 'drop') at offset 0.95 and (27.1, 'drop') at offset 1.1. | Write `t_event` (additive optional field, the unsnapped impact time) on the dynamics item. Otherwise snap major impacts only within a beat. |

## Round 3 (r-dsp-m1-r3)

Reviewer r-dsp-m1-r3 checked fixer-m1-r2's changes to `spectral` (`dsp.select_kick_events`: the low band's own attack
replaces the click refractory; pitch-drop evidence; a roll rule for double kicks) by running code. The scratch scripts are
in `out/_wip/r-dsp-m1-r3/`. Blockers and majors are in `docs/build/reports/r-dsp-m1-r3.md`, each with a failing test in
`tests/review/M1/r-dsp/test_rdsp_r3_kicks.py` (or the existing round-2 test).

Fix status:
- **B1-R2: not fixed.** The hat cases pass: F1 0.989, 0.989 and 1.0. The contract fixture song gets *worse*: F1 0.864
  (P 0.835, R 0.894; round 2 had 0.880). The round-1 floor test (P >= 0.85, R >= 0.9) now fails as well. The cause is not
  the hat but the bass line. The truth has a bass note (`notes.bass`, A1/F1, inside the 35-100 Hz kick band) 100 ms
  before each lost kick. Its onset is emitted as a kick (viz true), and the 0.2 s refractory then drops the real kick:
  over the held bass, the kick's ≤ 400 Hz excess is about 2 dB, below the 3.5 dB needed.
- **R2-M1: fixed for the tested cases, not over a held bass note.** The crash cases pass (130 and 150 BPM: 1.0; 170 and
  190: 1.0 and 0.99). Jeremy's kick-stem recall is 0.97 (opt-in test passes). On real songs, the viz-registered hits that
  are now dropped look like non-kicks: their median DrumSep kick-stem rise is 2.3 / 0.1 / 3.5 dB on Versatile, Jeremy and
  newton, against 57 / 51 / 84 dB for the kept ones (`real3.py`). But rock 8th-kick pairs over a held bass note lose the
  '&' kick at 140-160 BPM (major, new test).
- **R2-M2: fixed only at the tested tempo.** 16th double kicks are found at 150 and 160 BPM with the tight, clicky kick,
  but not at 170 BPM (R 0.81) or 180 BPM (3 of 96), nor under a crash (42 of 96).

Minor findings, round 3:

| id | location | claim | evidence | suggested fix |
|---|---|---|---|---|
| m16 | `spectral/dsp.py:select_kick_events` docstring | The docstring describes two rules the code does not implement: a `glide_song` rule ("in a song whose events mostly show it every hit needs it"), and "a click-less hit within the refractory is a kick when it has it" (the pitch drop). The kept loop applies the glide only to weak hits (v ≤ 0.3), and the refractory branch never looks at the glide. | `grep glide_song` finds only the docstring. `probe_glide_song.py` shows what such a veto would do (share 0.5, veto below 1.1). Four-on-the-floor over off-beat bass goes 0.88 → 0.978. The hat cases and kicks_over_bass go to 1.0. The fixture song and the syncopated groove barely move, because their misses come from the refractory. | Implement the documented rules, or delete them from the docstring. See the bass-line blocker in the report. |
| m17 | `kick_conf` (CONTRACT decision M1-S8) and `tests/unit/spectral::test_kick_events_with_sub_bass_line` | M1-S8 says sustained bass notes "read low" in `kick_conf`, and the unit test's docstring says `kick_conf` separates them. On the builder's four-on-the-floor groove(), the 12 bass-note onsets emitted as kicks have kick_conf 0.965-1.0 (median 1.0, the same as the true kicks). On the default groove the extras have median 0.948 against 1.0 for the true kicks, so the test's `median(tp) >= median(fp)` passes with almost no margin. | `kc.py`, `probe_groove2.py`. | Put the pitch drop (`kick_glide`) into `kick_conf`: kicks median 1.93, bass-note extras ≤ 1.29 on these signals. Make the test strict (`median(fp) <= 0.5`). |
| m18 | `tests/unit/spectral::test_real_song_kick_counts` | The fixer widened the bar from ±10 % of the W0 viz reference to [-35 %, +10 %]. For Versatile, Jeremy and newton the kick-stem evidence supports the widening. For MEGAFAUNA, 164 of its 503 viz-registered kick-band hits are dropped, and its DrumSep stem cannot tell whether they are kicks: the share of attacks with a clear kick-stem attack is 0.35 for the dropped ones and 0.31 for the kept ones. A -35 % band would hide a future recall regression. | `out/_wip/r-dsp-m1-r3/real3.log`. | Replace the count band with a per-song kick-stem recall test (strict attacks, as in `test_jeremy_unambiguous_kicks_are_kept`) for Jeremy, newton and Versatile. Keep MEGAFAUNA count-only with a note. |
| m19 | `docs/contract/decisions/M1.md` | m14 still stands. There are still two M1-S6 rows (the flash rule at line 16, and the kick-event rule rewritten by the fixer at line 59), outside the table. | Read the file. | Renumber the kick-event row (e.g. M1-S12) and move it into the spectral table. |
