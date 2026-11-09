# W4 R-DOGFOOD review (r-dogfood)

Method: only `skill/mv-harness/SKILL.md` and what it points to plus ONE output folder (`out/_wip/ud2-kick/newton-vs-nye`, post-UD2;
the `integrator/` folders are pre-UD2 and their lib has no `kicks()`), then a 20 s responsive canvas sketch
(`out/_wip/r-dogfood/sketch/index.html`, window 84-104 s = S06 -> S07 -> S08 with the singer change C2 -> C4 and the S07/S08 drop).
Second pass on MEGAFAUNA (`?song=song-mega&t0=124&t1=146`, build -> drop at 141.84 s). No lyric text appears in this report.

The sketch has: two stick figures posed from `song.count(t)` (eight poses by count, blended with `beatPhase`), jump/stomp on
`song.pulse('kick', t)`, ring flash on `pulse('hit_points')`, the lyric line from `lyricAt` in the singer's colour, `meaningAt`
palette/feel/meaning/camera/movement for the look, a dark build over `cues.next(t, {minTier:1}).lead_in_s` and a flash + shake + zoom burst on the
tier-1 cue. Everything worked once the friction below was worked around; the data was usable.

## Verified (no finding)
- Audio clock: browser-decoded `mix.flac` duration 170.434792 s vs manifest 170.434807 s (0.015 ms); `preview.opus` lags the mix by 0 ms
  (cross-correlation, 60-64 s); median broadband onset offset of 177 `song.kicks()` (vel > 0.4) is +1.8 ms (10-90 %: -23..+50 ms, kick body ~50 ms).
- Live playback: `audio.currentTime` and the render clock agree to < 10 ms over 20 s; section, 8-count and cue transitions land together
  (E027 count 8 at 93.985 s, E028 count 1 at ~94.0 s, S08 and cue Q0220 at 93.99 s).
- Load cost in a browser: 30 requests, 6.9 MB of data plus the 21 MB flac; `load()` errors name the missing include (good).
- `song.kicks()` / `pulse('kick')` / `kickSource` work (Newton 198 kicks, source drums); MEGAFAUNA drop cue Q0176 has `lead_in_s` 18.3 s, ideal for a build.

## Findings (ids W4D-n; blockers/majors have a failing test in tests/review/W4/dogfood/)
| id | sev | owner | claim |
|---|---|---|---|
| W4D-1 | major | RUNTIME | `mvh meaning <folder>` / `analyze --only meaning,brief` on a folder with stale stages reports "not run" but deletes `curves/` (finalize.pack_curves unlinks every curve file no current stage produced). Events, brief and manifest stay and point at curves that are gone. Hit for real after the rc.2 -> rc.3 bump: my copy of the Newton folder lost all 8 curve files on the first `mvh meaning`. Test: test_w4d_stale_folder_keeps_curves.py (6 s). |
| W4D-2 | major | M6a | RECIPES.md teaches `song.curve('drums.kick')` (ungated stem curve) and never shows `song.kicks()`; SKILL.md says cut on `song.kicks()` only (UD2). The recipe page is what an agent copies from. Test: test_w4d_skill_docs.py. |
| W4D-3 | major | M6a | Every new song is `meaning: pending`: `meaningAt().palette_hint` and `meaning.palette` are `[]`. The cover-art palette (manifest.summary.palette) is the only colour and appears in no recipe; the palette recipe's fallback chain stops at the empty `meaning.palette`. Test: test_w4d_skill_docs.py. |
| W4D-4 | major | M6a | No word on how to use the folder in a browser: `load('out/slug/')` needs HTTP (file:// fails), the server must support Range (python -m http.server does not: `audio.currentTime = 84` silently stays 0 and the clip plays from 0:00), and the folder is 1.1 GB (stems 635 MB, .cache 395 MB, viewer.html 8 MB) while a page needs ~7 MB + mix.flac; no verb exports a slim web bundle. Test: test_w4d_skill_docs.py. |
| W4D-5 | minor | M6b | Contract has no per-character colour or look; characters are `Voice V1 (proposed)` with `lead_backing: both` on C1. The agent invents colours (the lyric "singer colour" has no source). Suggest an optional `characters[].color` in the intent template. |
| W4D-6 | minor | M6a | "Drop" outside EDM: `edm_roles` exists but is empty for Newton; SKILL section 5 lists it for build/drop and says nothing on what to use for a rap song. What worked: tier-1 `cues` (kind section/drop) with `lead_in_s`, `moments` rank 1. Say so. |
| W4D-7 | minor | RUNTIME | The integrator reference folders are stale vs the current code (rc.2, pre-UD2 lib; the code is rc.3 so every stage is stale and a 45 min re-run is needed before `mvh meaning` can merge an intent). Also "not a song folder made by mvh analyze" fires when `.cache` is missing, so a slimmed copy of a folder cannot be re-merged. |
| W4D-8 | minor | M5 | L045 starts at 93.30 s but its `section_id` is S08 (starts 93.99): `meaningAt(93.5)` says S07 ("held breath") while the S08 singer is already rapping. Pickup lines straddle the boundary; document or let `meaningAt` take the line's section. |
| W4D-9 | minor | M6a | Clock guidance: the three.js recipe only shows AudioContext `getOutputTimestamp`; an `<audio>` element sketch (the easy path) gets no latency note (`outputLatency` read 0 here). |
| W4D-10 | minor | M6b | `emotion.audio` prints `energetic (energetic)` (label repeated) in meaning.json/brief; `interview.md` is 8.5 KB and its template block repeats 11 empty lines x 14 sections even though the user usually fills 3-4. |
| W4D-11 | minor | M6a | RECIPES three.js and frames examples use `hits.kick` (the lower-quality mix fallback) as the kick texture; fine as a "flash" but the SKILL table and RECIPES disagree on which kick to feed shaders. |

## Not verified
Real-time audible sync by ear (the preview tool has no audio output); only decode/onset analysis. Re-merging my stand-in intent through `mvh meaning`
was impossible (W4D-1/W4D-7), so S06-S08 meaning fields were written by hand into the sketch's copy of meaning.json.
