# UD5: lyric bars, word groups, split bars and user voices

User decision UD5 (2026-11-19), merged into docs/CONTRACT.md as **D83**. lyrics 1.3.0, voices 1.4.0, viewer 1.4.0.

## Why
- Words could be dragged out of the line they belong to, and only one word could be moved at a time.
- The voice model sometimes finds too few voices and merges singers. There was no way to add a voice, remove one, or
  give part of a line to another voice (call and response, a sample laid over the line).
- Corrections were keyed by line ids (`L016`, `L016.03`), which are numbered by time after the alignment. Anything
  that reorders or splits lines renumbered them, so a correction could land on another line.

## Decisions
- **UD5-1 Stable references.** Every line from the lyric source carries `ref` = `r<source index>`; a split bar carries
  `r<source index>p<part>`; every word carries `ref` = `r<source index>w<place in the source line>`. Lines the harness
  added (repeats it heard, ASR-only lines) have none. The lyrics stage accepts `lyrics.lines` and `lyrics.words` keyed
  by these references as well as by ids; `r12` applies to every bar of source line 12, `r12p1` to its second bar.
  `voices.lines` takes them too (bar > whole line > id > intent.md). The viewer writes references when a line has
  one, and folds an old id key into the reference when it rewrites a correction.
- **UD5-2 Splits.** `overrides.json` `lyrics.splits` = `[{index, at: [k, ...], key?}]`: source line `index` becomes one
  bar per part, a new bar starting at each word place `k`. Every word keeps its timing, confidence and flags; the
  bars are lines of their own in lyrics.json (`source_part`, `source_word`). The key (the source line's `pin_key`)
  makes the split ignored, with a warning, once the text of that line changes. Splits are applied after the
  alignment, so they never change where words are placed; pins (D82) still address the source line.
- **UD5-3 User voices.** A voice in `voices.lines` that the clustering did not find is a new voice: it gets spans,
  activity and an entry in meta/voices.json, and the viewer maps it to a character like any other.
  `voices.merge` = `{V3: V1}` removes a voice: its spans go to the other voice (chains followed, cycles ignored), and
  a backing span that ends up on its line's lead voice is dropped.
- **UD5-4 Bars and groups in the viewer.**
  - A word never leaves its bar (the line's span joined with where its words show now). A group of words moves only
    as far as all of them can stay in their bars.
  - Dragging a bar's left or right edge stretches it: every word keeps its relative place (saved as word timings).
  - Selection: click, Ctrl/Cmd+click (add or remove), Shift+click (range in sung order), Esc (clear). Dragging a
    selected word, the ±ms buttons, "start at playhead" and the `<` / `>` keys move the whole selection.
  - Moving a line also moves the words of it that were placed by hand (they have absolute times).
  - "split the bar before this word", "move these words to a new bar", "join with the bar before"; pending splits
    are drawn as a dashed mark. "sung by" offers "+ new voice"; each voice has "remove voice: merge into ...".

## Tests
`tests/unit/lyrics/test_splits_and_refs.py`, `tests/unit/viewer/logic.test.mjs` (bars, groups, splits, keys).
