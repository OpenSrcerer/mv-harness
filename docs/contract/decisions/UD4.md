# UD4: lyrics that follow the singing (weak lead stem) and line pins

User decision UD4 (approved 2026-11-15), merged into docs/CONTRACT.md as **D82**. lyrics 1.2.0, viewer 1.2.0.

## Why
On a song whose hook is sung by a group, the karaoke separator put the hook into the backing-vocals stem. The lyrics
stage transcribed and aligned on `lead_vocals`, which was 12 to 15 dB quieter there and half silent, so the hook's
lines had nothing to snap to: confidence about 0.15, and the second hook was placed 25 s late. The only corrections
were per-line nudges, which move a line rigidly and do not re-align anything.

## Decisions
- **UD4-1 The alignment signal follows the singing.** `vocal_env.pick_alignment_signal`: where the `vocals` stem is
  active while `lead_vocals` is at least `weak_lead_gap_db` (8 dB) quieter for at least `weak_lead_min_s` (4 s; runs
  closer than 2 s are joined; levels are 1 s mean powers), the full vocals stem replaces the lead stem (50 ms
  cross-fades). The ASR, the emissions and the activity all use that signal. `meta` `alignment.stem` is
  `lead_vocals+vocals` and `alignment.vocals_regions` lists the stretches. `weak_lead_regions = false` turns it off.
  The whole-song fallback (lead nearly silent everywhere -> `vocals`) is unchanged. A backing harmony under a lead
  line and a short ad-lib never trigger it.
- **UD4-2 Line pins.** `overrides.json` `lyrics.pins`: a list of `{index, t, key?, line?}`. `index` is the line's
  0-based position in the lyric source (`lyrics.json lines[].source_index`), `t` where the line starts, `key`
  (`lines[].pin_key`, a hash of the normalised text) guards against a changed text, `line` is the id at the time of
  pinning (for display only). Pins are keyed by the position in the source, not by the line id, because ids are
  assigned by time after the alignment and the alignment is what a pin changes.
  - A pin whose index is out of range, whose key does not match, or whose time is not after the pin of an earlier
    line is ignored with a warning.
  - **Anchors.** Untimed text: a pinned line's expected start is the pin; an ASR anchor on the wrong side of a pin is
    dropped (the same words are sung in every pass of a hook); the lines from a pin to the next known start share
    that span by word count. Timed sources: the pinned line takes the pin as its source time and a source time on
    the wrong side of a pin is re-interpolated. With pins the whole-song fallback alignment is never used.
  - **Alignment** (`align_groups(pins=...)`): a pinned line opens its own group, whose window starts `PIN_TOL`
    (0.35 s) before the pin, so no earlier line reaches past it; a pinned line that lands more than `PIN_TOL` from
    its pin is re-aligned in `[pin - PIN_TOL, ...]`; the global source offset does not move a pin; the ASR repair
    never moves a word across a pin.
  - **Fixed point.** After every pass (`_enforce_pins`): a pinned line whose first word is still more than `PIN_TOL`
    from the pin is moved as a whole onto it; an unpinned line outside the pins around it is moved to its expected
    start. Within the tolerance the aligner's own placement is kept: the pin is a hint the words snap to.
  - `lyrics.lines` / `lyrics.words` nudges still apply after the alignment, on top of the pins.
- **UD4-3 lyrics.json (additive).** `lines[].source_index` (null for a line the harness added: a repeat or an
  ASR-only line, which cannot be pinned), `lines[].pin_key`, `lines[].pinned`.
- **UD4-4 Viewer.** Edit tab, Lyrics: "pin start at playhead", "pin at start of <nearest section>", "remove pin", and
  the list of pins. Pinning removes the line's nudge. A pending pin shows the line at the pinned time; pinned lines
  carry a flag in the Lyrics lane.

## Measured (the song that prompted it; 38 lines, user text, Dutch)
| Run | Coverage | Hook lines (12) | Second hook starts at |
|---|---|---|---|
| before | 0.64 | mean confidence about 0.18 | 144.6 s (25 s late) |
| UD4-1 only | 0.88 | about 0.76 | 119.0 s |
| 4 pins only (UD4-1 off) | 0.69 | about 0.22 (the lead stem is still quiet) | 118.8 s; the pinned lines within 0.3 s of their pins |

The two reference songs the detector also fires on are unchanged: one has no lyrics, and the other's stretch is a
wordless outro (all 54 lines at the same times, no line added).

## Known limits
- Pins without UD4-1 place the lines but cannot raise the word confidence where the stem is quiet.
- After the last pin of a part there is no upper bound: when its lines still drift, pin one more line.
- A pin is tied to the lyric text: after `--lyrics` with a changed file, pins on changed lines are ignored (warning).
- Lines the harness added (repeat expansion, ASR-only) cannot be pinned.

## Tests
`tests/unit/lyrics/test_pins_and_weak_lead.py`, `tests/unit/viewer/logic.test.mjs` (line pins).
