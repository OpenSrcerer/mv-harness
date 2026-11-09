# W4 words-group decisions (w4fix-words, M5 + M6b)

## W4-W1 (S16, W4A-S16): a backing voice span must be backed by the backing_vocals stem
- voices 1.3.0. A duet (role `backing`) span is placed only where `stem_activity` marks `backing_vocals` active.
  A line backed for at least `backing_min_support` (new param, 0.5) of its time keeps the whole-line span (unchanged
  behaviour: the synthetic duet lines are 100 % backed). Otherwise the span is trimmed to the hull of the active
  parts, which must last `min_item_s` (1.0 s) and be backed `backing_min_support` itself; the embedding is taken on
  that window and `first_word` / `last_word` are the words overlapping it. Else no backing span.
- When stem_activity events cannot be read the spans are not gated (warning).
- Additive: `meta/voices.json` `backing_unbacked_lines` (lines whose backing check was skipped because the stem had
  no backing voice there).
- Newton L021 (V1 under V3, 1.97 s, 0.44 s of backing activity) is no longer a backing span: one mouth at a time.

## W4-W2 (W4A-UD1): template entries are parsed one at a time; demotions are surfaced
- Grammar (mvh-intent v2, D78) tolerances added; no rule is ever inferred from free text (UD1 unchanged):
  - tabs in the indentation (and between `-` and the item) count as spaces to the next multiple of 4; a plain value
    holding a tab is quoted;
  - blank lines between a valueless key and its column-0 `- ` items (and between items) keep the region going
    (valid YAML);
  - when a key does not parse, each entry of `do_not`, `symbolism`, `notes`, `themes`, `references`, `palette`
    is parsed on its own too (as `characters`, `voices`, `sections`, `line_singers`, `motifs` already were), and an
    entry starts at EVERY line at the entries' indent, so one stray line never takes its neighbours with it.
- Additive: `parse_intent()["unparsed_keys"]` (template key of each entry kept as a note), meaning.json
  `intent_unparsed: [{key, entries}]`, the first open question names them, and brief.md prints a bold line when any
  entry did not parse (saying rules typed under do_not may be missing).

## W4-W3 (round 2, VWU1-a / VWU1-b): mixed entries under one key; '-<TAB>item' at column 0
- A key whose body mixes `- ` items and bare `key: value` lines (YAML fails, so it is parsed entry by entry) never lets
  one form replace the other (it used to keep only the map entries, so a stray `Also: fog please` line under `do_not`
  became the ONLY rule and the typed rules vanished, silently):
  - list keys (`do_not`, `symbolism`, `themes`, `references`, `palette`, `motifs`): the `- ` items are the answer; each
    bare `key: value` line is kept verbatim as a note, with a warning, and the key goes into `unparsed_keys` (so
    meaning.json `intent_unparsed`, the open question and brief.md report it). It is never promoted to a rule: a
    stray line may be a wish ("Also: ...") or a rule ("chorus: no close-ups"); the user decides, by adding `- `.
  - `notes`: every entry is kept as a note, in the order typed (a note is text either way; no warning).
  - map keys (`characters`, `voices`, `sections`, `line_singers`): every entry is kept, read as bullets in the order
    typed (`_list_answer`), so `- C1 Ann = V1` plus `C2: Bob = V2` keeps both characters.
- Column-0 items: a dash followed by a space, a TAB or nothing (`-`, `- item`, `-<TAB>item`) continues the region
  under a valueless key (it used to need `- `, so `do_not:` then `-<TAB>rule` became a free-text note, silently).
- Demoted entries stay verbatim (indent included), as `test_intent_grammar` requires.
