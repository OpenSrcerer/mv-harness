# Review log

## Plan review, round 1 (2026-11-08)

Three independent reviewers read the draft of PLAN.md together with the research survey. They returned 2 blockers, 27 majors and 4 minors.
All blockers and majors were applied, some of them in a different form, as noted below.

### R-CONTRACT ("the video agent": Remotion, three.js, and a Blender character rig)
| # | Sev | Finding | Disposition |
|---|---|---|---|
| 0 | major | Three different frame rules let a curve flash and its event land on different frames. No `frame0`, no rational fps, no guarantee stems are aligned with the mix | Applied: centred-window frame rule, `{fps, frame0, early}`, rational fps, stem alignment and soundtrack rule (§4.2); wider golden vectors (§7) |
| 1 | major | No ID or link scheme across sections, lines, characters and cues | Applied: §4.3 IDs and links; `events/sections.json` is canonical |
| 2 | major | No lifecycle for the authored meaning; the SKILL rule let agents draft without asking the user | Applied: authored inputs are never overwritten, re-anchoring writes `orphans.json`, an interview-first agent rule, per-section hint fields (§8) |
| 3 | major | Lip-sync and characters were called first-class but were Should/Could with no stage behind them | Applied: `vocal.mouth_open` and per-line `singer` are Must, Rhubarb visemes Should, `singing.json` join, `singerAt`, a duet case (R16, §5, §8) |
| 4 | major | Lyrics access was contradictory and expensive for agents | Applied: NF5 rewritten, `lines.tsv` added, `--no-lyrics-to-agents` |
| 5 | major | Eight-counts had no anchor and the helpers were undefined off the beat grid | Applied: counts restart per phrase or section, partial counts, pickups, a virtual grid with `in_pulse` (§5 choreo, §4.4) |
| 6 | major | No convention for unvoiced f0; resampling corrupts pitch | Applied: NaN in files, never NaN from helpers, `pitch01`, `voiced` (§4.4) |
| 7 | major | `toTexture` exceeds MAX_TEXTURE_SIZE and does not fit three.js | Applied: `textureData` with wrap layout, `mvh.glsl`, `spectrumAt` / `spectrumWindow` |
| 8 | major | Helper list incomplete, bespoke, and its JS/Python contract unspecified | Applied: §4.5 signature table with generic `events().at/next/prev`, `meaningAt`, frame conversions |
| 9 | major | brief.md wasted tokens and left out characters, do-not rules and status | Applied: reordered brief (§4.7), `mvh brief --section` |
| 10 | minor | Drops and builds were defined in four places; cues duplicated every beat | Applied: tiered `cues.json`; drops and builds defined only in structure |
| 11 | minor | `load(dir)` assumes a filesystem; nothing let viz scenes run offline | Applied: URL/lazy `load`, `loadSync`, `vizState(t)`, output-latency note in RECIPES |

### R-PLATFORM + feasibility
| # | Sev | Finding | Disposition |
|---|---|---|---|
| 0 | blocker | The promised CPU fallback for the max separators had no env; `lead_vocals` could be missing | Applied in a different form: an `envs/sep` worker with **rocm and cpu** variants (keeps audio-separator's torch pins out of the main env), and `lead_vocals := vocals` as a fallback |
| 1 | major | audio-separator re-normalises the mix and the stems | Applied: thresholds disabled, stems-sum invariant test |
| 2 | major | Worker env under-specified (how mvh gets in, AMD index, model sharing) | Applied: §3.3 worker protocol, explicit AMD index, a parent that only does inference I/O, a single models.lock |
| 3 | major | The stage graph drawing missed edges stated elsewhere | Applied: §3.2 consumes/produces table, declared deps, acyclicity test |
| 4 | major | rhythm waited on the slow separators | Applied: `separate_fast` / `separate_hq` split, plus an `allin1` stage |
| 5 | major | The cache key missed external files, network responses, ffmpeg, the lock and the device | Applied: NF1 and NF2 rewritten |
| 6 | major | Library downloaders bypass SHA pins and offline mode | Applied: one downloader, cache env vars, explicit checkpoint paths, offline flags |
| 7 | major | Agents and children cannot rely on PATH | Applied: `mvh-env.ps1`, ffmpeg resolver order, absolute paths (§3.4) |
| 8 | major | No mechanism for Unicode paths or spaces | Applied: §3.4 Windows rules, plus a Unicode CLI test |
| 9 | major | The thread limits had no working mechanism | Applied: one process per stage, env vars set before import, ORT SessionOptions patch |
| 10 | major | The torchaudio and torchcodec traps from the survey were dropped; `forced_align` availability | Applied: never pass paths to model libraries, vendored CTC Viterbi, a float32 canonical WAV |
| 11 | major | The 90 % word-alignment gate was unsupported by the research | Applied: W0 sets a measured gate (initially ≥ 75 %); drum gates per class; kick event time defined |
| 12 | minor | Transcription default contradicted the survey; LRCLIB etiquette missing; W0 verify list | Applied: faster-whisper is the default and the Vulkan filter is a flag; etiquette listed; W0 smoke list |

### Build orchestration
| # | Sev | Finding | Disposition |
|---|---|---|---|
| 0 | blocker | Freezing shared files deadlocked W2; some files had no owner | Applied: StageSpec registration by convention, freeze limited to the envelope and consumed fields, the viewer server owned by M6a |
| 1 | major | The main env was missing tools that §5 needs | Applied: env additions, plus a SPIKE.md dependency row per tool as a W0 gate |
| 2 | major | A fixture that is only schema-valid cannot stand in for cross-module inputs | Applied: a synthetic multitrack whose ground truth is the fixture, plus real-song contract fixtures from the W0 cache |
| 3 | major | W1 was too big for one agent and on the critical path | Applied: W1a contract architect in parallel with W0, then three W1b builders, walking-skeleton stubs |
| 4 | major | Modules were uneven (M3 and M6 too large) | Applied: 8 modules (M3a/M3b, M6a/M6b) |
| 5 | major | Reviewer coverage gaps; W3 put all fixes on one agent | Applied: SEAMS.md, per-module W3 fixers, a completeness critic, an override round-trip acceptance test |
| 6 | major | The thread cap and GPU sharing were not real; W0 benchmarks were contended | Applied: heavy and gpu file locks, sequential benchmarks, background runs |
| 7 | major | Races on caches, the venv and output folders | Applied: offline flags, `UV_NO_SYNC`, `out/_wip/<agent>`, `tmp_path`, port 0, atomic downloads |
| 8 | major | Agents cannot find uv or ffmpeg | Applied: `mvh-env.ps1` and a preflight |
| 9 | major | No preflight for vocal songs; HTTP fixtures had no owner and would leak lyrics into git | Applied: preflight gate; W0 records HTTP into gitignored `tests/.cache/real/http/` |
| 10 | minor | Fix loops cost too many agents | Applied: reviewers write failing tests, the gate script decides, no re-check agents |
| 11 | minor | No per-module commits or ownership check; line endings; git dependencies | Applied: per-module commits, a porcelain ownership check, `.gitattributes`, tarball-pinned wheels |
