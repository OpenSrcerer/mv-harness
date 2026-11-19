# UD6: a bar's own start and end

User decision UD6 (2026-11-19), merged into docs/CONTRACT.md as **D84**. lyrics 1.4.0, viewer 1.5.0.

## Why
Dragging a bar's edge stretched the bar and moved every word in it with it (UD5). Resizing a bar should change only
the bar: the words keep their timing, and an edge must not leave a word outside the bar.

## Decisions
- **UD6-1 Bar edges in overrides.json.** `lyrics.lines {key: {dt?, start?, end?}}`. `start` and `end` are absolute
  times of the line's bar. The lyrics stage writes `lines[].t` / `d` as the words' span widened by them (never
  narrowed), so the span always holds every word. No word moves.
- **UD6-2 Split lines.** A key that names every bar of a split line (`r12`, an old id) sets the start of its first bar
  and the end of its last one; `r12p1` sets that bar only.
- **UD6-3 Viewer.** Dragging a bar's left or right edge resizes only the bar. The left edge stops at the first word's
  start, the right edge at the last word's end. Moving a line moves its saved edges with it.
- The UD5 stretching (words scaled with the bar) is removed.

## Tests
`tests/unit/lyrics/test_bar_edges.py`, `tests/unit/viewer/logic.test.mjs` (bar edges).
