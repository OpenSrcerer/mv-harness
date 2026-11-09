# W3 orchestrator viewer check (2026-11-09, after workflow D)

PLAN §12 gates W3 on the orchestrator checking songs in the viewer. I opened `mvh view <folder> --read-only` in the browser preview for the
integrator's max runs. I looked at the lanes, ran "fit the whole song", and checked the console.

| Song | Loads | Console errors | Observations |
|---|---|---|---|
| newton-vs-nye | yes | none | All lanes draw. 54 lyric lines from 1.2 to 123 s. Singers: C1 (intro, outro, and one doubled line), C2 (two verse blocks, 13.7-41 s and 69-91 s), C3 (42-69 s), C4 (93-123 s). The hand-offs fall on section boundaries, which looks like an announcer plus three rappers. **Section labels:** 7 of 12 sections are labelled `chorus`, but a rap battle has no chorus. These are Harmonix labels from allin1 (compare Jeremy, 12/20 chorus, SEAMS S09). Several lines grade D (31-41 s, 62-68 s). |
| megafauna | yes | none | All lanes draw. 105.1 BPM, D minor. Sections run intro → inst → breaks → build → drops from about 2:20. The drum-hit lanes are nearly empty until about 1:55 (ambient intro and breaks: plausible). 14 lyric lines, a single voice, in the second half. |

Notes for W4 (R-DOGFOOD / R-ADVERSARY, and the fixers through them):
- **Section labels on rap songs:** `chorus` is over-used. Consider a song-form-aware relabel: repeat structure plus voice hand-offs, so verse-per-rapper on battles. Or expose the label's confidence, so agents can ignore it.
- Everything else looked consistent at whole-song zoom. Audio sync was not checked by ear in this pass: R-DOGFOOD checks it.
