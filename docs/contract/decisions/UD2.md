# UD2: the kick source (W4 phase 0, agent ud2-kick)

User decision UD2 (docs/BUILD-STATUS.md, approved 2026-11-09). Normative text: docs/CONTRACT.md **D79** (the agent-facing
kick, meta/drums.json, manifest `summary.kick_source` / `kick_agreement`, QA flag) and **D80** (hits.kick precision).
This file records the evidence and the test rewrites. No lyric text.

## 1. Why the drum-stem kick had to be quality-gated (CR-M1-4)

On MEGAFAUNA the DrumSep kick sub-stem was mostly bleed (raw: 647 rows, 43 % of the inter-kick gaps on the 71 ms 32nd-hat
grid, median vel 0.14). Measured on the stems (scratch analysis, 30-120 Hz band of each sub-stem):

| | weak rows (vel < 0.2) | strong rows (vel >= 0.5) |
|---|---|---|
| 30-120 Hz level in the kick stem (median) | -35 dB | -17.5 dB |
| on a hat onset (+-10 ms) | 50 % | 38 % |
| a mix kick within 30 ms | 8 % | 22 % |

In the intro / instrumental sections (18-36 s) and the build (124-135 s) the kick is in the SNARE sub-stem: hits whose
30-120 Hz band dominates their 150-400 Hz band by 12-20 dB and rises 24-48 dB, which hits.kick also sees; the kick stem
there holds only vel-0.1 bleed. Some snare-stem hits there are kick + snare layered (30-120 Hz within 10 dB of the kick
reference, not bass-dominant) with a mix kick within 4 ms.

Floor toms are bass-heavy too (Jeremy, Versatile: 30-120 over 150-400 Hz +6..+16 dB), so the toms stem is recovered only
with a fast decay and a mix confirmation; on the clean songs no snare-stem hit reaches the kick level (0 candidates).

Gate parameters chosen on the four songs (`drums.kick_*` params): rise >= 3 dB, on-hat quiet 10 dB, faint 20 dB under the
p90 reference. Floors of 16-18 dB dropped real Versatile kicks (mix_in_drums 0.956 -> 0.92). A rise measured against the
loudest 5 ms before the onset (instead of the mean) dropped real kicks re-struck on long 808 tails (Newton -4, MEGAFAUNA
+148 no-rise drops) and was reverted.

## 2. Results (W4 runs, out/_wip/ud2-kick/<slug>: integrator max folders re-analysed with the UD2 code)

| song | raw kick rows | gated / recovered | kick_source | vel median | gaps < 100 ms raw -> kept | mix_in_drums / drums_in_mix | QA flag |
|---|---|---|---|---|---|---|---|
| synth | 85 | 85 / 0 | drums | 0.72 | 0.00 -> 0.00 | 0.977 / 0.988 | - |
| newton-vs-nye | 200 | 198 / 0 | drums | 0.89 | 0.01 -> 0.00 | 1.000 / 0.995 | - |
| versatile | 124 | 109 / 0 | drums | 0.82 | 0.11 -> 0.00 | 0.956 / 0.991 | - |
| jeremy | 644 | 548 / 0 | drums | 0.77 | 0.05 -> 0.00 | 0.958 / 0.916 | - |
| megafauna | 647 | 323 kept + 10 relabelled from snare + 9 layered = 342 | drums | 0.46 | 0.43 -> 0.16 | 0.463 / 0.249 | qa:kick_sources_disagree |

Before UD2 (integrator, W3): hits.kick vs all DrumSep kick rows within 30 ms: MEGAFAUNA 0.49 / 0.15, Jeremy 0.90 / 0.79,
Versatile 0.96 / 0.88, Newton 0.98 / 0.98, synth 0.98 / 0.99.

MEGAFAUNA keeps the stem: after the gate it passes every check (vel 0.46 >= 0.3, fast gaps 0.16 <= 0.25, 50 % kept >=
40 %), and the mix cannot see its sidechained drop kicks (R4-M2: the kick replaces the ducked bass, the mix low band does
not rise). The 0.75 flag threshold sits between Jeremy (0.92, the lowest clean song) and MEGAFAUNA (0.25).

## 3. hits.kick: precision over recall (D80)

| texture | before (spectral 1.2.0) | after (1.3.0) |
|---|---|---|
| kick-free: pluck bass + hats / low piano chords / snare on a new bass note (review R5-M3) | 50 / 21 / 7 kicks | 0 / 0 / 0 |
| kick-free, independent generator (unit test, other tempo / registers) | - | 0 / 0 / 0 |
| contract fixture kick, 4-on-the-floor over a held bass / 909 / ducked sub / quiet intro / fade-out / 16ths at 180 BPM | F1 >= 0.95 | F1 >= 0.95 (unchanged) |
| Jeremy: precision / recall against the drum-stem kick (vel >= 0.3) | 0.89 / 0.95 (559 events) | 0.95 / 0.95 (524) |
| Newton, Versatile, synth, MEGAFAUNA | - | <= 4 events each change |

Costs, all on mix-only hard textures the drum-stem kick covers in practice (precision stays 1.0 at +-30 ms everywhere):
acoustic kick over a held bass recall 1.0 -> 0.63 (unit design 0.725), TR-808 over a held bass at 120 BPM F1 0.968 ->
0.945, 808 at 140 BPM recall 0.40 -> 0.25, acoustic at bass 0.7 0.71 -> 0.23.

Known limit (documented, not tested as a target): a staccato low piano chord whose fundamental sits in the 30-100 Hz kick
band (E2 = 82 Hz) shows the body route's evidence (30-150 Hz onset centred >= 68 Hz decaying >= 8 dB in 90 ms) and is
reported as a kick; the glide cannot separate it (Jeremy's real acoustic kicks have glide < 0.85 on 12 % of the body-route
kicks, all matched by the drum stem). Songs with drum stems use the drum-stem kick.

## 4. Test rewrites (why)

Chasing full recall on mix-only textures kept trading one false-kick case for another (rounds 2-5: every new route that
recovered a hard texture invented kicks somewhere else; R5-M3 is the click route's). Under UD2 hits.kick is a fallback
used only without drum stems, and an invented kick is worse for a video cut than a missed one.

| test | was | now |
|---|---|---|
| tests/review/M1/r-dsp/test_rdsp_r5_kicks.py R5-M1 (808 100/140 BPM, acoustic bass 0.7) | F1 >= 0.95 at +-10 ms | precision >= 0.95 (808 100 BPM at +-30 ms with recall >= 0.6: its ~10 ms early anchor is a timing limit, not an invented kick) |
| R5-M2 acoustic / ducked subs + quiet lead chord | F1 >= 0.95 | precision >= 0.95 (acoustic: recall >= 0.3, plus the fixture kick in the same mix at F1 >= 0.95) |
| R5-M3 kick-free textures | <= 2 events | unchanged (now 0) |
| R5-M4 quiet intros (808, acoustic over bass) | intro recall >= 0.95 | precision >= 0.95 in and after the intro; 808 recall guards 0.5 / 0.8 |
| test_rdsp_r4_kicks.py R4-M1 acoustic / 808 over a held bass | F1 >= 0.95 | precision >= 0.95, recall >= 0.5, fixture kick in the same mix F1 >= 0.95 |
| tests/unit/spectral held-acoustic | F1 >= 0.95 | precision >= 0.95, recall >= 0.5 (every other design keeps F1 >= 0.95) |
| tests/unit/spectral (new) test_no_invented_kicks_on_kick_free_material | - | <= 1 event on 3 independent kick-free textures |
| tests/integration/M1/test_real_kick_sources_agree.py (S06) | both timelines agree >= 0.7 on MEGAFAUNA | MEGAFAUNA: agent kick clean (fast gaps <= 0.25, vel median >= 0.3), agreement recorded and flagged; clean songs: drums, agreement >= 0.85-0.9, no flag |

New unit tests: tests/unit/drums/test_kick_source.py (gate, recovery, choice, stage meta/drums.json, param override),
tests/unit/lib/test_lib_kick.py + kick.test.mjs (lib parity), golden section 6b (`kick`).

## 5. Interpretations

- UD2-I1: "agent-facing kick = drum-stem kick whenever the drums stage produced it" is read as "and it passes the per-song
  check": the raw MEGAFAUNA stem would fail it (vel 0.14, 43 % fast gaps), the gated one passes.
- UD2-I2: the classifier path (htdemucs drum stem without sub-stems) counts as a drum-stem kick (it is events/drum_hits from
  the drum stem); it is not gated (its kick class is band-based already) and must pass the same check.
- UD2-I3: brief "kick counts" = a `kick` header row (source, count, agreement, QA) and a `kicks` column per section.
- UD2-I4: the viewer is built before the manifest, so it reads `meta/drums.json` for the source (data.js sets
  `song.manifest.summary.kick_source` from it before any kick helper runs).
- UD2-I5: rhythm, dynamics, structure, choreo and cues keep their inputs (choreo/cues already read drum_hits, which is now
  gated: MEGAFAUNA's groove clustering sees far less hat bleed in its kick row, S17).
