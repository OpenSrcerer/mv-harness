# builder-m6a: M6a Viewer (report)

Owned paths only. Checkpoint log: `docs/build/progress/builder-m6a.md`. Decisions and change requests: `docs/contract/decisions/M6a.md`.

## What was built
| Path | What |
|---|---|
| `src/mvh/stages/viewer/__init__.py`, `data.py`, `bundle.py` | the `viewer` stage (replaces the stub): collects events, meta, lyrics, meaning, reduced curves, spectrogram, 1 kHz waveform base and the opus preview from the upstream caches, size-caps them, and assembles one self-contained `viewer.html` (cache key includes a digest of the viewer sources). Params: `inline_cap_mb` 28, `inline_audio_max_mb` 8, `inline_spectrogram`, `inline_lyrics`, `waveform_hz`. |
| `src/mvh/stages/viewer/server.py`, `cli.py` | `mvh view <folder or slug>` (127.0.0.1, port 0, idle timeout 900 s, `--no-open --read-only --no-rerun`), the edit-mode API and the Range-capable static server. |
| `src/mvh/stages/viewer/intent_block.py` | managed block in `meaning/intent.md` (voice to character, per-section meaning), user text preserved byte for byte. |
| `src/mvh/assets/viewer/` | `template.html`, `viewer.css`, `logic.js` (pure, node-tested), `util/data/audio/view/lanes/panels/edit/main.js`. |
| `tests/unit/viewer/` | 51 pytest tests + 12 node tests (run through pytest), `build_view.py` (builds a viewer folder from any contract fixture). |

## The viewer
Lanes on one zoomable time axis (ctrl+wheel zoom, shift+wheel / drag pan, click seeks, follow page/centre/off, loop section): whole-song waveform overview tinted by bass/mid/high with a window rectangle; Sections (IDs, EDM roles, phrases); Meaning (feel, meaning, palette, characters, do-not, lyric/audio disagreement); Lyrics and singers (blocks by character/voice, rows per voice, confidence shading, word ticks when zoomed, karaoke in the status bar); Beats and counts (beats, downbeats, bar numbers, eight-count digits with accents, partial/lead-in/off-pulse flags, meter changes, tempo curve); Hits (six drum classes by velocity, onsets, hit points, holds); Bands (bass/mid/high + kick envelope, optional spectrogram); Loud and quiet (short-term/momentary LUFS, dynamics segments, integrated LUFS/LRA/TP, impacts, stops, silences); Instruments and stems (stem levels and activity, tagged instruments, S/M per stem); Notes (piano roll per source with toggles, key, chords); Vocal range (f0 on a note axis, tessitura and p2-p98 lines, lowest/highest markers that jump on click, vocal style, mouth_open, visemes); Cues (tiers 1-3 with lead-in, pins). Side panel: Meaning (logline, summary, themes, characters, palette, per-section cards), Values (frame rule fps/frame0/early and the same helper outputs a video agent gets), Edit, Help. Playback: mix.flac or preview.opus, speed, stem solo/mute mixer, click track (beats, downbeats, optional drum-hit sounds, clicks-only, latency offset).

Edit mode (`mvh view`): beat offset (typed, nudges, align nearest (down)beat to playhead), BPM override (candidate chips), downbeat phase, drag/add/remove section boundaries (snap to bars, Alt disables), relabel sections, drag lyric lines and words, nudge buttons, voice per line, voice to character mapping, per-section meaning, pinned moments, undo, "Check stages", "Re-run affected stages". Each commit POSTs, the response names the stages that will re-run.

## Verification
- Browser (Claude_Browser pane, 1000-1100 px wide): synthetic fixture folder and all four real-song fixture folders loaded in served/edit mode: no lane errors while stepping through 4 zoom levels each, console clean apart from fixture-only 404 probes for absent optional files (a real folder has a manifest, so nothing is probed). The inline-bundle path (the code path of `file://`: blob import, DecompressionStream, fetch shim) was verified with `?inline=1` on Jeremy (13 MB bundle with spectrogram and preview): only `lib/mvh.js` and the two edit APIs were requested, all lanes and the spectrogram rendered.
- The Browser pane refused `file://` URLs ("declined access"), so a literal `file://` open was NOT done; the claude-in-chrome extension was not used so as not to touch the user's own browser.
- Playback verified in the pane: playhead tracks the audio, karaoke highlights, click scheduling leads the audio clock by 21-146 ms (never late), stem solo mutes the mix and plays the stem within ~35 ms.
- Edit round trip verified: beat offset, boundary drag (real mouse drag), line nudge, voice per line, label, pin, intent block: `overrides.json` written atomically and `mvh validate` on the folder says valid.

## Per-song results (stage run against `tests/contract/<fixture>/` upstream; `tests/unit/viewer/build_view.py`)
| song | html size | stage time | lanes without data (fixture is partial) |
|---|---|---|---|
| synth (56.5 s) | 2.6 MB | 0.4 s | none |
| jeremy | 13.4 MB | 0.8 s | meaning, hits, instruments, cues |
| megafauna | 9.0 MB | 0.7 s | meaning, lyrics, hits, ... (as the fixture) |
| versatile | 9.5 MB | 0.8 s | as the fixture |
| newton-vs-nye | 7.2 MB | 0.6 s | meaning, hits, instruments, cues |
Other stages are now real and heavy, so the runner end to end was left to the gate (below).

## Thresholds
The viewer has no accuracy thresholds. Asserted instead: inlined arrays are bit-identical to the fixture (including NaN positions), waveform base scaled to peak with a flat pre-roll, spectrogram bytes identical, byte-identical output on re-run, caps drop the spectrogram first, lyrics switch removes lyric text, missing lanes do not fail the stage (confidence drops 0.05 per lane), server rejects bad Host/Origin/token/body/schema/typo/etag, hidden paths and `..` (9 variants) are 404, idle timeout stops the server.

## Gate
`scripts\gate.ps1 M6a`: viewer unit tests 51/51, contract-gen PASS, `mvh validate` on the fixture PASS, fixture PASS. Two steps fail for reasons outside M6a: `tests/unit/contract::test_stub_files_are_stubs` (asserts `rhythm` is still a stub; M2 replaced it) and `ruff check src tests` (E501 in other modules' files such as `src/mvh/sep/*`); all viewer files are ruff-clean. The e2e/determinism steps queue behind other agents' heavy slots (separate_fast); see the final status in the structured result.

## Open issues
- No literal `file://` test (see above); mobile layout is only a media-query fallback.
- Stem mixer uses media elements, not sample-accurate (documented in Help).
- BPM preview regenerates a constant grid from the first beat; the stage result may differ.
- The edit panel does not edit word text, lyrics text or section time of the meaning-only anchors; lyric text is read-only by design.
- Real override round trip (stages re-running and the change appearing in the output) needs M2/M5/M6b to read the managed block and to apply keys; see change requests.
