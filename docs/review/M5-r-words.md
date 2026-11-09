# M5 Words: R-WORDS review, minor findings (r-words-m5)

Reviewer: r-words-m5 (independent, PLAN §11). Module M5 (identity, lyrics, voices, lipsync). Blockers and majors
are failing tests under `tests/review/M5/r-words/` (see `docs/build/reports/r-words-m5.md`). Minor findings are
listed here; each was checked by running code (scripts in `out/_wip/r-words-m5/scripts/`, gitignored). No real
lyric text appears in this file.

| id | location | claim | evidence | suggested fix |
|---|---|---|---|---|
| m1 | `lyrics/core.py::_finalise_line` + `lipsync/core.py::gate_for_words` | A line's last word is sustain-held twice: lyrics extends the word end up to 1.5 s (M5-D7) and lipsync extends the already-extended end by up to another 1.5 s, so the mouth gate can stay open about 3 s past the CTC end (spec: "while within 20 dB of p95, at most 1.5 s"). | `probe_hold.py`: a note sustained 1-9 s, CTC end 1.50 s -> lyrics word end 3.00 s -> lipsync gate end 4.58 s (3.08 s past the CTC end). | Hold from the CTC end once (store the raw end, or have lipsync hold only when `d` was not already extended), or cap lipsync's hold at `1.5 s - (d - raw d)`. |
| m2 | `lyrics/text.py::TokenMaker._n2w` | Years are read as cardinals: `1999` -> "one thousand, nine hundred and ninety-nine" (35 MMS tokens) where it is sung "nineteen ninety-nine" (~22); superscript digits (`²`) are dropped after folding; for a non-English language whose num2words call fails (`ja`) the digits stay digits and the word gets no tokens (interpolated). | `probe_tokens.py` output. | `to="year"` for 4-digit 1100-2099 numbers (as num2words supports), run the digit pass again after NFKD folding, fall back to English number words when the language is unsupported. |
| m3 | `lyrics/core.py::_apply_overrides` | Line overrides are keyed by the pre-override start order, but the output ids are assigned after the override is applied and the lines re-sorted: a nudge that moves a line past its neighbour renames both lines in lyrics.json, so the next viewer edit (keyed by the displayed id) hits the other line, and `voices.lines` keyed by line id silently follows the wrong line. | Code path: `ids` from the pre-override order (line 922), `lines.sort` after `_apply_overrides` (line 380), ids `L{li+1:03d}` from the sorted list (line 419). | Keep the ids from the pre-override order in the output (sort for export only after the ids are fixed), or key overrides by a stable source index. |
| m4 | `lyrics/core.py::_stable_ts` | The stable-ts fallback maps our words to stable-ts words by proportion (`j = int(wi * len(sw) / k)`): when the counts differ several words get identical times. | Code (lines 815-819); not triggered on the four songs (lowest coverage MEGAFAUNA 0.68). | Map by LCS of normalised words, interpolate the unmatched ones. |
| m5 | `lyrics/asr.py::ffmpeg_whisper`, `lyrics/grade.py::gate` | Draft path: the whisper filter writes its transcript (lyric text) into the shared models folder (`cwd` = model dir, relative destination); a killed run leaves it there. Its words carry `p = None`, so a transcribed draft song always grades D (`asr_mean_p or 0.0` < 0.6) and voices then flags every span (M5-D22). | Code (asr.py `dest = mdir / dest_name`; grade.py transcribed branch). | Write the destination under `ctx.scratch` (an absolute path is fine for the filter's `destination` when the model name is relative), and grade drafts without word probabilities on G2-G4 only. |
| m6 | `lyrics/__init__.py` deps | The module brief allowed adding `ingest` to the lyrics deps and said to keep the dep change and move the contract-test change into change_requests; the builder kept the deps and reads `embedded_lyrics.json` through the undeclared D8 path (CR-M5-1). Works (the key follows ingest transitively), but the read is undeclared. | `docs/contract/decisions/M5.md` M5-D1; `STAGE.deps`. | W3: apply CR-M5-1 as briefed. |
| m7 | `lipsync/core.py::run` | Per-voice `mouth_open.<V>` always uses the lead_vocals envelope; on a duet the backing voice's mouth follows the lead singer's syllables (the backing words have their own timing in the synth truth). | Synth: V2 backing lines L005/L006/L009/L010 are gated by V2's spans but valued by the lead envelope (code: `base = env/p95` for every voice). | For backing-role spans use the backing_vocals envelope (the stem voices already uses for duet spans). |
| m8 | `lipsync/core.py` ungated fallback | Wordless vocal regions with no sung line within 8 s go to `voices[0]` (the first voice to appear). On newton the 131-138 s outro (no ASR words) is given to V1, the announcer, which is right only by coincidence. | `real-newton-vs-nye` run: `vocal.mouth_open.V1` open 131.2-137.9 s. | Assign to the nearest voice regardless of distance and mark it (provenance / a review flag), or leave it in `vocal.mouth_open` only. |
| m9 | `lyrics/lrclib.py::rank` | PLAN's tie rule "ties go to the candidate with the best alignment coverage" is not implemented (ties fall to the smallest id). | Code (`key()`). | Align the top two tied candidates and keep the better G2, or record the tie in `lrclib`. |
| m10 | `voices/core.py` meta `hint` | `speaker_hint` text is copied into `meta/voices.json` (`voices[].hint`, read by brief). With legitimate labels it is a name; with the pseudo-labels of finding B it is a sung lyric word outside `lyrics/*` (NF5). | `test_rw5_speaker_labels.py`. | Fixed by B; optionally only copy hints that recur. |

Checked and fine (no finding): LRCLIB etiquette (get+album, get, two searches, 0.4 s, UA, never get-cached, Retry-After),
synced-within-2 s preference (newton 3921433), Jeremy 22859144 and no words after 218.1 s, MusicBrainz version-tag retry
(Jeremy accepted on `base_title+dur`, Δ -0.088 s), global offset detection (synth +-1.3 / 2.5 / 4 s recovered to 0.04 s;
> 3 s flagged; newton -1.32 s), TTS median onset error 20 ms (plain text) / 0 ms (A2), newton voices = W0 blocks plus the
announcer, 4 mouth channels with 3 % overlap, synth voices 10/10 lines and 4/4 duet backing spans, mouth_open recall
0.98 / 0.96 with 2-3 % false opening, Rhubarb dialog files deleted, no lyric text in any result, provenance, warning or
the run logs of the four runs.

## Round 2 (r-words-m5-r2)

Re-review after the fixer round (fixer-m5, M5-D30..D34). Verified by running code: the 15 round-1 tests pass;
synth line-only LRC and shifts +2.5 / -4.0 s now place every word within 0.46 s (median 20 ms, no crossings);
jeremy has 0 lines whose words start after the next line (round 1: 4) and L037 no longer duplicates L036 (A, A2, D
fixed in align_groups); LRCLIB lyrics-before-instrumental ranking and the ASR veto of the instrumental flag work (E);
the new Whisper credit patterns are caught and asr_only lines need no_speech_prob < 0.6 (C). Not fixed or regressed
(majors, failing tests): B (LRC ID tags make every file "labelled"; section headers become speakers), the ASR repair
duplicates a neighbour's word, the C regex deletes sung lyric lines, the 6 s emission context drops newton to grade C,
and Jeremy's one singer is split into 4 voices. See `docs/build/reports/r-words-m5-r2.md`. Probes:
`out/_wip/r-words-m5-r2/scripts/`. No real lyric text here.

| id | location | claim | evidence | suggested fix |
|---|---|---|---|---|
| r2-m1 | `lyrics/align.py::align_groups` (`SEAM_MARGIN_S` floor/cap) | A group's window now starts at most 0.15 s before its first line's LRC time and the previous group's window ends 0.15 s after it, so a group-first line sung earlier than its timestamp can only be recovered by the crossing repair (it is not flagged: `lines_off_gt2s` needs > 2 s). | Pure probe `probe_seam_clamp2.py` (spiky emissions, distinct text): group-first line sung 0.5 s early -> the whole second group is misplaced (a word 7 s late, scores ~0) with no note. Real models: synth L009 LRC +0.5 / +0.7 s late is rescued by the crossing repair; on newton the clamp alone raises words > 1 s from the LCS-matched whisper word from 6 to 9 and lowers within-0.3 s from 0.963 to 0.942 (`probe_ctx2_newton-vs-nye.log`); jeremy L039 moves 0.5 s. | Floor at the previous group's last placed word end (not its expected end), or keep the 2 s context and resolve overlaps with the order repair only. |
| r2-m2 | `lyrics/core.py::run` (warning after align_groups) | `crossings_left` / `lines_off_gt2s` and their warning are computed before the ASR repair, the repeat expansion and the sustain hold, which can all move words again; a crossing they create is never counted (see test_rw5_r2_asr_repair_duplicates.py). `lines_off_gt2s` (and G5) look at the first word only, so a line whose later words spill several seconds is not counted. | Code order in `run`; `probe_seam_clamp2.py` (second word +7 s, `lines_off_gt2s` 0). | Run the order / deviation checks on the final word times (after `_finalise_line`) and on every word, and feed them to the gate. |
| r2-m3 | `lyrics/core.py::_finalise_line` | The last word's sustain hold is not capped at the next line's first word: jeremy L039's last word ends 1.34 s after L040 starts (the mouth gate and voice_spans overlap there). Related to round-1 m1 (still open). | `line_report.py r-words-m5-r2/real-jeremy`: L039 end 213.28 s, L040 start 211.94 s. | Cap the hold at the next non-backing line's first word start. |
| r2-m4 | round-1 finding A evidence | Correction: round 1 called jeremy L033.03 (9.44 s, 175.52-184.96 s) a misplacement. The lead stem stays at -14 to -18 dBFS from 174.5 to 184.5 s with no whisper word inside, i.e. one held note; the long word is plausible. The other A evidence stands and is fixed. | 0.5 s RMS of `tests/contract/real-jeremy/stems/lead_vocals.flac`; cached whisper words at 174.39 and 185.09 s only. | None. |
| r2-m5 | round-1 minors m1-m10 | Not addressed in the fix round (fixer report: "not cheap/safe"); m6 stays a change request. | fixer-m5 report. | W3 / next M5 round. |

## Round 3 (r-words-m5-r3)

Re-review after fixer round 2 (M5-D35..D38). Verified by running code (session resumed after a power outage; the
interrupted real-versatile and header runs were redone). R2-2 (ASR repair clipped to neighbour lines, warning on the
final times), R2-4 (SPIKE 2 s recipe plus seam-window replacement: real newton end to end grade B, G2 0.758, G4 0.109,
offset -1.31 s) and R2-5 (jeremy 1 voice; 16 jittered trials all 1; newton 4; synth 2 with 10/10 lines) are fixed.
R2-1 and R2-3 are only partly fixed (majors R3-1, R3-2), and there are two new majors on the user-supplied text path
(R3-3 `[Name:]` / `Name:` battle markers, R3-4 unbracketed section headers sung as words). Failing tests:
`tests/review/M5/r-words/test_rw5_r3_*.py`. Probes: `out/_wip/r-words-m5-r3/scripts/`. No real lyric text here.

| id | location | claim | evidence | suggested fix |
|---|---|---|---|---|
| r3-m1 | `lyrics/core.py::_finalise_line` (r2-m3 still open) | The last word's sustain hold still runs past the next line's first word: real jeremy has 7 non-backing line pairs where the line's last word ends after the next line starts (L010 by 1.48 s, L039 by 1.36 s). `crossings_left` is 0 because it looks at starts only. voice_spans of consecutive lines overlap there. | `lyrics.json` of `out/_wip/r-words-m5-r3/real-jeremy` (times only). | Cap the hold at the next non-backing line's first word start (minus a frame). |
| r3-m2 | round-2 minors r2-m1, r2-m2, r2-m5 | Not addressed in fixer round 2 (the warning for r2-m2 now runs after the ASR repair only; the repeat expansion and the sustain hold are still not checked). | Code read of `core.py::run`. | W3 / next M5 round. |

Checked and fine this round: no lyric text in any log, record, warning or non-lyric output of the newton and jeremy runs
(scan of every file except `lyrics/*` and the cache-only `_http/` bodies: 0 hits); user TXT on synth grade A, line-only
LRC grade A with offset 0.02 s; versatile instrumental (source none, voices skipped, lipsync ungated 0.68 s);
megafauna transcribed on the vocals stem with grade D and every voice span flagged for review.

## Round 4 (r-words-m5-r4, W3 verify)

Re-review after the W3 fix round (fixer-m5-r3, M5-D47..D53). Verified by running code: the 17 round-3 review tests
pass, and the fixes are general rather than test-shaped (probes `out/_wip/r-words-m5-r4/scripts/probe_text*.py`:
`[Final Chorus]`, `[Pre Chorus]`, `[Name:]`, `Name:` and `NAME:` lines, `Verse 2: Name`, `CHORUS`, `Chorus x2`,
`(Chorus)` behave; `Chorus of angels ...` stays a lyric). R3-2: `_generic_suspect` no longer fires on
`no_speech_prob` alone. S07: versatile `vocal.mouth_open` max 0.0 (was 55 frames > 0.1). S03: G1 is scoped to mutual
spans (M5-D51) with near-miss snapping (M5-D53); jeremy grades B with G1 0.7705, close to the W0 raw value of 0.762.
The cached W0 VAD whisper pass has 0 words after 218 s, and the VAD-free gap retry keeps 3 words in 92 s. So the outro
is mostly wordless, and the M5-D52 warning is the honest outcome. One new major: R4-1, a regression of the R3-3 fix in
which sung lines that end in `Word:` are deleted as speaker markers (`test_rw5_r4_colon_lyric_lines.py`). No real
lyric text appears here.

| id | location | claim | evidence | suggested fix |
|---|---|---|---|---|
| r4-m1 | `lyrics/text.py::_plain_header` / `_header` (long tail of R3-3/R3-4) | Several header and marker variants are still read as SUNG lines or lose the speaker: `*Chorus*`, `Chorus (repeat)`, `1st Verse:` / `2nd Verse:`, `Isaac Newton (Verse 1):`, and a 5-word `Bill Nye the Science Guy:` become lyric lines. `[Verse 1 - Isaac Newton]` (hyphen) gives speaker None. `(x2)` on its own line after a block becomes a backing lyric line `(x2)` (this predates the fix). No warning is raised when an aligned line consists only of section and repeat words. | `probe_text.py` / `probe_text2.py` (synthetic text): line counts and hints printed per case. | Strip `*`/`_` decorations, accept `(repeat)` and ordinal prefixes in `_PLAIN_SEC_RE`, split `-` like `:` in bracketed headers, treat a lone `(xN)` line as a repeat of the previous block or line, and warn when an aligned line has only section and repeat words. |
| r4-m2 | `voices/core.py` (`n_source = "hints"`), `lyrics/text.py` joint labels | A joint label (`[Chorus: Ann & Bob]`, `Both`, `All`) is a separate hint, so a Genius-style duet gives 3 hints and voices forces k = 3: the joint lines become their own voice. This predates the W3 round. | `parse_txt` of a 2-singer text gives hints `['Ann', 'Ann & Bob', 'Bob']`; voices `k = len(hints)`. | Split joint hints on `&` / `and` / `,` / `+`. k counts the single names, and a joint line is assigned to the nearest single-name centroid and flagged as a multi-singer line (or proposed as `line_singers`). |
| r4-m3 | `tests/integration/M5/test_real_lyrics_grade.py::test_real_jeremy_sung_outro_is_not_wordless` | The second S03 test (`sung_after < 20`) cannot pass under M5-D52, which flags the outro and does not invent lines. The integration tests also read the integrator's pre-fix run (`out/_wip/integrator/<slug>`), so the S03 and S07 tests still fail until the integrator re-runs M5. | M5-D52; cached W0 VAD whisper has 0 words after 218 s, and the M5-D50 gap retry keeps 3 words. | The integrator re-runs M5 on the real songs and changes the second S03 test to accept the `vocals_after_last_line_s` warning. |
| r4-m4 | `lyrics/asr.py::canonicalise` (M5-D53) | G1 now counts near-miss spellings (ratio >= 80 within ±3 s) as agreement. Lyric changes between versions (`loving`/`living`, `spoken`/`spoke`) therefore count as agreement, while the 0.70 threshold was measured on the exact F1. The wrong-text controls (0.064 / 0.042) are far below the threshold, so no wrong text passes today. Only a partly different version (a live or alternate take) moves closer to passing. | Code; `asr.g1_scope.raw_f1` keeps the exact value (jeremy 0.6917, scoped and snapped 0.7705). | Report `raw_f1` next to G1 in the brief, and add a partial-version control (for example the text with every 5th line replaced) to the M5 unit tests. |
| r4-m5 | round-3 / round-2 minors | r3-m1 (the last word's sustain hold runs past the next line's start), r2-m1 and r2-m2 are not addressed in this round. | Code read of `core.py::_finalise_line` and `run`. | W4 / next M5 round. |

## Round 5 (r-words-m5-r5, W3 verify)

Re-review after fixer-m5-r4 (M5-D54, M5-D55; D56 withdrawn). R4-1 is only partly fixed: `test_rw5_r4_colon_lyric_lines.py`
passes, but the `recurring` branch of `text._scan_labels` accepts every lone `Name:` candidate in the file without the
pronoun / verb check or the Title Case guard, so the same deletion happens as soon as one quote-introducing line is
sung twice (major R5-1, `test_rw5_r5_recurring_colon_lines.py`). New major R5-2: `voices` raises `ValueError` when a
speaker hint (or a joint hint's singer) occurs only on lines shorter than `min_item_s`, as a battle announcer's short
shout does (`test_rw5_r5_short_hint_crash.py`). Probes: `out/_wip/r-words-m5-r5/scripts/probe_*.py` (synthetic text
only). No real lyric text appears here.

| id | location | claim | evidence | suggested fix |
|---|---|---|---|---|
| r5-m1 | `voices/core.py::hint_parts` (M5-D55) | The joint split runs on every `,` / `and` / `&` / `+`, so one act's name becomes several singers: `Tyler, The Creator` -> `Tyler`, `The Creator`; `Earth, Wind & Fire` -> 3; `Florence and the Machine` -> 2. With a fake embedder, a `Tyler, The Creator` + `Bob` song still gives 2 voices (label order luck), but the Tyler voice loses its `hint` (None in meta), and if the phantom name takes a label of its own k grows by one. | `probe_joint.py` | Split only when every part is itself a name seen as a solo hint elsewhere in the file (or a credited artist); otherwise keep the hint whole. |
| r5-m2 | `lyrics/text.py::_scan_labels` strict branch | `All:` / `Him:` / `Her:` are in `_NOT_NAME`, so a short duet whose `Ann:` / `Bob:` / `All:` markers occur once each (no recurrence) keeps all three marker lines as SUNG lyric lines (8/8 kept, no hints), and they are aligned as words. Conversely `Dear John:` / `Dear Mary:` letter lines in a sentence-case file are accepted as markers. | `probe_markers.py` (`duet_ann_bob_all_once`, `duet_him_her_once`, `sc_dear_letters`) | Treat the joint words (`All`, `Both`, `Everyone`) and the duet pronoun labels (`He`/`She`/`Him`/`Her`) as label-compatible single-word candidates; require a credited artist / intent character for non-recurring multi-word names. |
| r5-m3 | `lyrics/text.py::parse_txt` lone `(x2)` | `(x2)` on its own line after a block repeats only the block's last line: `[Chorus] a b (x2)` gives `a b b` (Genius usage is usually the block, `a b a b`). Before round 4 it was a backing lyric line `(x2)`; both are wrong, the new one silently adds a wrong-text line that alignment must place. | `probe_x2.py` | When the lone `(xN)` closes a bracketed block (blank line or next header follows), repeat the block; repeat the line only when it follows a line inside running text. Or emit a warning and do nothing. |
| r5-m4 | `tests/integration/M5/*` (r4-m3 still open) | The S03 (both) and S07 integration tests still read `out/_wip/integrator/<slug>` written 05:10 (before the M5 W3 fixes) and fail; the S03 part-2 test (`sung_after < 20`) cannot pass under M5-D52. | `pytest tests/integration/M5`: 3 failed, 2 passed. | Integrator re-runs M5 on the real songs; change S03 part 2 to accept the `vocals_after_last_line_s` warning. |
| r5-m5 | round-2/3 minors | r3-m1 (sustain hold past the next line start; D56 withdrawn), r2-m1, r2-m2 remain open. | fixer-m5-r4 report; code read. | Next M5 round (voices item windows from word starts first). |
