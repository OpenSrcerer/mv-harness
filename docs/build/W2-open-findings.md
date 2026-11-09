# W2 open findings (end of workflow C)

Final-round reviewer findings that are still open, blockers and majors only. Every one has a failing test at test_path.
The W3 integrator owns these. Minor findings are in docs/review/<module>-<lens>.md.

| Module | Last review round per lens | Open blockers | Open majors |
|---|---|---|---|
| M1 | R-DSP r3 (fail) | 2 | 2 |
| M2 | R-DSP r3 (fail) | 0 | 2 |
| M3a | R-ML r3 (pass-with-fixes) | 0 | 1 |
| M3b | R-ML r2 (pass) | 0 | 0 |
| M4 | R-ML r3 (pass-with-fixes) | 0 | 1 |
| M5 | R-WORDS r3 (fail) | 0 | 4 |
| M6a | R-PLATFORM r3 (pass-with-fixes) | 0 | 1 |
| M6b | R-CONTRACT r3 (fail), R-WORDS r3 (fail) | 0 | 8 |

## M1

- **[blocker] B1-R2** (R-DSP r3) `src/mvh/stages/spectral/dsp.py select_kick_events / select_hit_events (refractory 0.2 s, low-band step 6.5 dB / excess 3.5 dB rules)`
  Not fixed, and worse. On the contract fixture song, kick events fail PLAN §7 (F1 >= 0.95 at +-10 ms). The cause is not hats. Bass-note onsets (truth notes.bass, midi 29/33, 44-55 Hz, inside the viz kick band) 100 ms before a kick are emitted as kicks (viz true). The real kick after each one falls inside the refractory and is dropped: over the held bass its <=400 Hz excess is only 2-4 dB.
  Fix: - Do not let a candidate without the kick-body pitch drop (low kick_glide) open a refractory over a following candidate that has it. - Judge the kick's own attack on the kick band (about 30-120 Hz, zero-phase), not on <=400 Hz where bass harmonics dominate. - Use kick_glide in kick_conf.
  Test: `tests/review/M1/r-dsp/test_rdsp_r2_kicks.py::test_kick_events_on_the_contract_fixture_song_meet_plan (also tests/review/M1/r-dsp/test_rdsp_kick_events.py::test_kick_events_on_the_contract_fixture_song)`
- **[blocker] R3-B1** (R-DSP r3) `src/mvh/stages/spectral/dsp.py select_kick_events (<=400 Hz low-band 'own attack' plus refractory); tests/unit/spectral test_kick_events_with_sub_bass_line (bar lowered)`
  Regression from the B1-R2 fix. A <=400 Hz step belongs as much to the bass instrument as to the kick. Over a moving bass line, bass-note onsets are emitted as kicks with kick_conf up to 1.0, and through the refractory they suppress real kicks up to 363 ms later. The fixer lowered the builder's own unit-test recall bar from 0.85 to 0.7 so the test would pass.
  Fix: - Compute the kick's own attack on the kick band, not <=400 Hz. - Gate the refractory on kick_glide (see B1-R2). - Restore the unit-test bar to PLAN §7 (F1 >= 0.95) and add groove(seed=3) and the 16th riff to the unit tests.
  Test: `tests/review/M1/r-dsp/test_rdsp_r3_kicks.py::test_kicks_over_the_builders_groove_bass_line[default,seed3,four-on-the-floor] and ::test_kicks_over_a_sixteenth_bass_riff`
- **[major] R2-M1** (R-DSP r3) `src/mvh/stages/spectral/dsp.py select_kick_events (drop of candidates with v_ev <= 1e-4; low-step 6.5 dB / excess 3.5 dB within the refractory)`
  Fixed for the tested cases (8ths under a crash at 130-190 BPM; Jeremy kick-stem recall 0.97; dropped real viz hits justified). Not fixed for rock 8th-kick pairs (1, 1&, 3, 3&) over a bass note held for two beats at 140-160 BPM: the '&' kick is dropped. At 140 BPM its kick-band x is 0.37 with v_free 0, so it is discarded as envelope-less, and its excess over the held bass is 3.1 dB. At 160 BPM the low step is 3 dB.
  Fix: - Base the own-attack test on the kick band. - Keep weak episodes that have a clean low-band step instead of dropping them for v == 0.
  Test: `tests/review/M1/r-dsp/test_rdsp_r3_kicks.py::test_rock_eighth_kick_pairs_over_a_held_bass_note[140.0] and [160.0]`
- **[major] R2-M2** (R-DSP r3) `src/mvh/stages/spectral/dsp.py select_kick_events roll rule (own step >= 6.5 dB, excess >= 3.5 dB, click >= 15 dB)`
  Fixed only at the tested tempo. The fixed-dB roll rule is tuned to the one tested case: 16th double kicks fail above 160 BPM or under a cymbal, which masks the required >= 1 kHz click. Metal double bass plays 160-220 BPM, usually under cymbals.
  Fix: - Take dense-roll kicks from the low-band or kick-band envelope, with thresholds relative to the local inter-onset level, not fixed dB. - Do not require the click when a cymbal wash is present.
  Test: `tests/review/M1/r-dsp/test_rdsp_r3_kicks.py::test_sixteenth_double_kicks_beyond_the_tested_tempo[170bpm,180bpm,160bpm-under-crash]`

## M2

- **[major] F4-r3** (R-DSP r3) `src/mvh/stages/structure/features.py bar_pattern (slot edges) + src/mvh/stages/structure/__init__.py (merge guard merge_keep_strong, dyn gate); tests/review/M2/r-dsp/test_structure_real_upstream.py harness (fixture rhythm)`
  F4-r2 is fixed only for the fixture's exact truth rhythm. With the real rhythm (beats F1 1.0, two downbeats 18 ms late), the structure stage again misplaces sections on the synthetic song, and a 10 ms bar shift flips the result. The review test passes because the fixture rhythm is the truth rhythm, a third circular input.
  Fix: Centre the bar_pattern slots on the grid positions (offset the edges by half a slot) or use soft or overlapping pooling, so 1-2 frames of downbeat jitter do not change the fingerprint. Make the same-group merge guard less of a knife edge, for example with hysteresis or by requiring a clear margin over cost. Gate the dynamics evidence relative to the section cost. Score the structure tests with the recorded real rhythm (data/synth_real_rhythm.npz) and with ±10-20 ms bar jitter, not only with the fixture rhythm.
  Test: `tests/review/M2/r-dsp/test_structure_rhythm_jitter.py`
- **[major] F6-r3** (R-DSP r3) `src/mvh/stages/structure/__init__.py: repeat grouping (agglomerative, F4-r2 fix) feeding the same-group merge; EDM drop extent rule (while drive[j+1] >= drive[i] - 0.6, i = the drop's first section)`
  Regression from the F4-r2 fix on MEGAFAUNA, the module's named regression song: the drop now ends at 176.1 s instead of 212.7 s. Three loud-plateau sections (176.1, 185.3, 194.4 s) are labelled 'inst', against SPIKE's 'loud plateau 146-217 s', and the drop's repeat groups now mix drop and inst sections of the same material and energy.
  Fix: Make the drop extent independent of segmentation granularity: compare following sections against the drop's peak-plateau level (for example a bar-level drive threshold relative to the song's drive distribution, or the max over the first 8 bars), and extend over sections in the same repeat group as the drop's opening. Keep roles consistent within a repeat group (a group that contains a drop section should not label the same material 'inst' at equal energy).
  Test: `tests/review/M2/r-dsp/test_structure_drop_extent_real.py`

## M3a

- **[major] R3-1** (R-ML r3) `src/mvh/stages/drums/core.py drumsep_hits (cymbal_rise_db=8.0, applied as the detect() rise floor for the ride and crash sub-stems)`
  Ride and crash candidates need a broadband rise of 8 dB. A ride played in 8th notes rises only 6.4-6.5 dB over the ring of the previous stroke, so about 95 % of the strokes are lost, even on clean sub-stems. The synthetic song has only quarter-note rides 0.5 s apart, so the PLAN §7 cymbal gate never exercises a ride pattern.
  Fix: - Detect ride and crash onsets on the 4-16 kHz band, as detect_air does for hats, or set the rise floor from the stem's own ODF spread instead of a fixed 8 dB. - Keep the precision on separated stems with the ring and leak rules that already exist. - Add a synthetic 8th-note and 16th-note ride, with accents, to the module tests, both on clean sub-stems and end to end.
  Test: `tests/review/M3a/r-ml/test_r3_drums_ride_eighths.py`

## M4

- **[major] R3-M1** (R-ML r3) `src/mvh/stages/harmony/keys.py global_confidence (sources set / len(sources) < 2 cap); core.analyse_key ignores the lv-chordia no-chord share`
  M1's remaining half: when lv-chordia reports 100% no-chord, the key is still not marked as having no tonal evidence. Any input where S-KEY clears its 0.2 vote gate gets a confident key with no low-confidence flag, including noise, drones, risers and ambient pads.
  Fix: Gate the key on tonal evidence from the chord model. If the lv-chordia no-chord share in the span is about 0.9 or higher, cap confidence at about 0.3 and add key:no_tonal_evidence, whatever S-KEY says. Also count chords and phrase as a source only when the non-N share is above a floor (this fixes m13 too). Add unit tests for these paths.
  Test: `tests/review/M4/r-ml/test_key_gating_band_noise.py`

## M5

- **[major] R3-1** (R-WORDS r3) `src/mvh/stages/lyrics/text.py::_header / _file_labelled (R2-1 only partly fixed)`
  LRC ID tags no longer mark a file as labelled, and headers that contain an instrumental word no longer name a speaker. Two cases from R2-1 are still open. (1) _header recognises a section only when the section word comes first (low.startswith(SECTION_WORDS)). So [Pre Chorus] (no hyphen), [Post Chorus], [Final Chorus], [Last Chorus] and [Rap Verse] are read as speaker names. These headers recur, so the file counts as labelled, the following lines carry them as hints, and voices forces k from the hints on a one-singer song. (2) A chorus line written out twice that starts with 'Time:' counts as a recurring label, so the sung word 'Time' is cut from every chorus.
  Fix: Treat a header as a section when ANY of its words is a section word (also match 'pre chorus' / 'post chorus' without the hyphen). Do not count an inline label as recurring when it prefixes the same line text each time (a repeated lyric, not a change of speaker). Require at least 2 distinct recurring labels before a bare-header file counts as labelled.
  Test: `tests/review/M5/r-words/test_rw5_r3_speaker_labels.py`
- **[major] R3-2** (R-WORDS r3) `src/mvh/stages/lyrics/asr.py::_generic_suspect (M5-D37 second signal no_speech_prob > 0.4; R2-3 only partly fixed)`
  Generic outro phrases ('see you (in the) next', 'please like/share', bare 'bye' / 'goodbye' / 'thank you') still drop a whole confident sung segment in the middle of active vocals. The second signal no_speech_prob > 0.4 is the normal state for sung 30 s windows: faster-whisper computes no_speech_prob once per window, and singing pushes it up.
  Fix: Do not use no_speech_prob alone as the second signal. Use it only together with avg_logprob < -1 or mean word p < 0.6, as the general filter does, or rely on vocal activity / position at the audio edges. Never drop a confident segment inside active vocals.
  Test: `tests/review/M5/r-words/test_rw5_r3_hallucination_nospeech.py`
- **[major] R3-3** (R-WORDS r3) `src/mvh/stages/lyrics/text.py::_header (':' split takes the text after the colon) and _LABEL_RE (needs text after the colon)`
  Two common speaker-marker formats in user-supplied battle lyrics lose the speaker. (1) In '[Name:]' the speaker is taken from the empty text after the colon, so it is None and no line gets a hint. (2) 'Name:' alone on its own line is not a label; it becomes a SUNG lyric line, which is aligned, exported and counted in G1-G4 and in the mouth gate. Speaker hints from the text are the only route to n_source 'hints' for the rap battle, the stress test.
  Fix: In _header, when the text after the colon is empty, use the text before the colon as the speaker (unless it is a section word or a metadata key). Treat a line that is only a short capitalised name followed by ':' as a speaker marker, not a lyric line, in the same way that a bare [Name] header is treated.
  Test: `tests/review/M5/r-words/test_rw5_r3_battle_label_formats.py`
- **[major] R3-4** (R-WORDS r3) `src/mvh/stages/lyrics/text.py::parse_txt (section headers only recognised inside [...] / {...} via _HEADER_RE)`
  Section headers without brackets in user-supplied or embedded plain-text lyrics become sung lyric lines: 'Verse 1:', 'Chorus:', 'Bridge:', 'VERSE 1' / 'CHORUS' in capitals, 'Chorus x2' (which becomes TWO lines 'Chorus'), and '(Chorus)' (which becomes a backing lyric line instead of re-inserting the chorus). The header words are force-aligned onto the vocals and written to lyrics.json, to every caption export and to the mouth gate. The grade gate does not notice, and no warning is given.
  Fix: In parse_txt, treat a line as a header when the whole line is a section word with an optional number, colon, 'xN' or parentheses (for example ^\(?(verse|chorus|bridge|pre-?chorus|hook|intro|outro|refrain)\s*\d*\s*:?\s*(x\s*\d)?\)?$, any case). Treat '(Chorus)' like '(Repeat chorus)'. Optionally warn when an aligned line consists only of section words.
  Test: `tests/review/M5/r-words/test_rw5_r3_unbracketed_headers.py`

## M6a

- **[major] F-R3-UNDO-FAIL** (R-PLATFORM r3) `src/mvh/assets/viewer/edit.js save() failure branch (`if (isUndo) st.history.push(J(clean(prev)))`) and undo()`
  When an Undo's POST fails, save() pushes the CURRENT document back onto the history instead of the entry undo() popped. The state Undo was restoring is lost. The next Undo rewrites the current state ('Saved: undo', nothing changes) and the Undo after it skips a step, so a correction is silently discarded. This is the same symptom as F-R2-UNDO, reached through the fixer's new failure branch.
  Fix: Have undo() pass the entry it popped to save() (e.g. save(doc, 'undo', poppedEntry)), and have the failure branch push back that entry, not J(clean(prev)). Also ignore or queue Undo and Ctrl+Z while st.saving, so a second Undo never goes out with a stale etag.
  Test: `tests/review/M6a/r-platform/test_r3_platform.py::test_a_failed_undo_keeps_the_state_it_was_restoring`

## M6b

- **[major] R3-1** (R-CONTRACT r3) `src/mvh/stages/meaning/docs.py yaml_template (palette hint) + intent.py parse_intent`
  The template's own palette hint (`palette: [] # hex (#1b2a49) or colour words`) leads users to type `[#c93523, night blue]`. In YAML that is a ParserError, so the whole template is dropped and the user's characters and do_not rules are lost. Fenced: the status goes back to pending. Unfenced: the file falls back to free text with the R3-2 junk.
  Fix: Quote hex values before loading (or pre-process `[#...` inside flow lists), show a quoted example in the hint (`["#1b2a49", night blue]`), and on a ParserError parse the template line by line so the other answers are kept.
  Test: `tests/review/M6b/r-contract/test_r3_intent_parsing.py`
- **[major] R3-2** (R-CONTRACT r3) `src/mvh/stages/meaning/intent.py parse_intent free-text fallback (reopens R2-2 / N3)`
  When the unfenced template does not parse (R3-1, or a template without the '# mvh-intent' marker plus any `Key:` note), the file is re-read as free text and the template's example comments become user claims. `line_singers: # ... {L005: C1+C2}` gives L005 to C1+C2 at user precedence, and the hint makes #1b2a49 the user's palette.
  Fix: Never feed template-shaped lines (YAML comment lines, `key: # ...` lines, flow maps) to the free-text parser. Strip each template line's trailing `# ...` comment before free-text parsing.
  Test: `tests/review/M6b/r-contract/test_r3_intent_parsing.py`
- **[major] R3-3** (R-CONTRACT r3) `src/mvh/stages/meaning/intent.py _parse_text do-not label block (regression from the N2 fix)`
  A do-not label line (`Never show: blood`, `Avoid: lens flares`) opens a block that keeps every following bullet, even after a blank line. Character bullets and section-note bullets become do-not rules, which SKILL.md treats as hard constraints on every frame, and the characters or section feels are lost.
  Fix: An inline label (`Never show: X`) is a one-line rule. A bare label opens a block that ends at the first blank line, heading, or line that parses as a character or section note.
  Test: `tests/review/M6b/r-contract/test_r3_intent_parsing.py`
- **[major] R3-4** (R-CONTRACT r3) `src/mvh/stages/meaning/intent.py _DO_NOT_HEAD (heading regex widened by the N2 fix)`
  The do-not heading regex matches never/don't anywhere in a heading. A title heading such as `# Never Let Me Go` or `# Don't Stop Me Now: my notes` therefore turns the story, the character lines and the section notes under it into do-not rules.
  Fix: Anchor the regex to the whole heading text (e.g. ^(never show|do not|don'?ts|avoid|no-?gos)\b.*$ with a short length limit) and do not apply it to an H1 title.
  Test: `tests/review/M6b/r-contract/test_r3_intent_parsing.py`
- **[major] R3-5** (R-CONTRACT r3) `src/mvh/stages/meaning/stage.py top-level field_sources (perspective)`
  `perspective` (narrator/addressee: who sings to whom) is filled from authored.json when the user does not give it, but the top-level field_sources has no entry for it. Under status 'user', an agent that follows SKILL §3 and RECIPES isDraft takes the draft's narrator and addressee as the user's direction. meaning.md prints it unlabelled too.
  Fix: Add field_sources['perspective'] (or perspective.narrator and perspective.addressee) set to user or draft, and label it in meaning.md and brief.md.
  Test: `tests/review/M6b/r-contract/test_r3_perspective_source.py`
- **[major] R3-1** (R-WORDS r3) `src/mvh/stages/meaning/docs.py yaml_template (motifs/symbolism/sections[].do_not lines)`
  The interview template always writes 'motifs: []', 'symbolism: []' and per-section 'do_not: []', although its docstring says it carries the user's answers so it 'can replace the free text without losing anything', and the template tells the user to copy it into intent.md. Copying the regenerated template back silently drops the user's section-level prohibitions, motifs and symbolism. The same loss happens to symbolism given as free text.
  Fix: Prefill motifs (name/lines/note), symbolism, references, notes and every user section do_not in yaml_template (from intent/meaning user-sourced fields). Add a unit test that a parse -> template -> parse round trip is the identity for user claims.
  Test: `tests/review/M6b/r-words/test_rw3_template_roundtrip.py`
- **[major] R3-2** (R-WORDS r3) `src/mvh/stages/meaning/intent.py _parse_yaml / parse_intent; docs.py yaml_template palette line ('# hex (#1b2a49) ...')`
  Hex colours typed the way the template comment suggests (palette: [#0e2346, #f2a541, rust red]) start YAML comments. Fenced (the form the interview shows): the block fails to parse and is also removed from the free text, so every answer, including the user's do_not rule and logline, is lost and the status stays pending. The warning wrongly says 'free text used'. Unfenced: the logline and do_not are lost, and the comment's example #1b2a49 becomes a user colour. Block list '- #0e2346': the items load as null and are dropped with no warning.
  Fix: Before the YAML parse, quote bare hex tokens (#[0-9a-fA-F]{3,8} after '[', ',', '- ' or ': '). In the template, show quoted hex (palette: ["#1b2a49"]). When a fenced block fails, parse it with the lenient region parser or line by line instead of discarding it, and never take colours from YAML comments. Warn on null list items.
  Test: `tests/review/M6b/r-words/test_rw3_template_hex.py`
- **[major] R3-3** (R-WORDS r3) `src/mvh/stages/meaning/intent.py _blocks (_DO_NOT_LABEL open block) and _DO_NOT_HEAD`
  Do-not detection now captures too much. (a) Regression from the N2 fix: a label line ('Avoid: cliches.') keeps the do-not block open across blank lines and every following bullet. A list of section notes after a blank line becomes verbatim do_not rules, which are hard constraints copied to every agent, and the section notes are lost. (b) _DO_NOT_HEAD matches a do-not word anywhere in a heading, so '## The story: a night that never ends' makes the story paragraph a do_not rule and loses the logline and summary.
  Fix: Close a label-opened do-not block at the first blank line, unless the label has no inline text and is followed directly by bullets. Do not treat bullets that start with a section key as rules. Anchor _DO_NOT_HEAD to headings that start with a do-not phrase ('Never show', 'Do not', 'Avoid', "Don'ts", 'No-gos'), not ones that merely contain it, and check story/meaning headings first.
  Test: `tests/review/M6b/r-words/test_rw3_do_not_overcapture.py`
