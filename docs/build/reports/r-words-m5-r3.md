# r-words-m5-r3: independent review (R-WORDS lens), round 3 of M5 Words

Verdict: fail (4 majors; 2 are residuals of round-2 findings, 2 are new). No blockers.

## Round-2 findings
| id | status | evidence |
|---|---|---|
| R2-1 speaker labels | PARTLY fixed (LRC ID tags and instrumental headers no longer label a file) -> R3-1 | test_rw5_r3_speaker_labels.py: 6 fail |
| R2-2 ASR repair duplicates | fixed (window clipped to neighbour lines' placed words, skip beyond edge, warning on final times) | round-2 test passes; code read; no crossings in real runs |
| R2-3 hallucination overreach | PARTLY fixed (credit strings unconditional, generic phrases need a 2nd signal) but the no_speech > 0.4 signal fires on ~half of real confident sung segments -> R3-2 | test_rw5_r3_hallucination_nospeech.py: 6 fail |
| R2-4 newton gate regression | fixed: 2 s recipe + seam window; real newton e2e grade B, G2 0.758, G4 0.109, offset -1.31 s | real-newton-vs-nye.log |
| R2-5 jeremy split | fixed: jeremy 1 voice (16 jitter trials all 1), newton 4, synth 2 (10/10 lines) | real-jeremy.log, probe_voices_k.py |

## New / remaining majors
- R3-1 `[Pre Chorus]`, `[Post Chorus]`, `[Final Chorus]`, `[Rap Verse]` (section word not first) become speaker names; a chorus line `Time: ...` written out twice counts as a recurring label and loses its sung word.
- R3-2 generic outro phrases ("see you in the next ...", "bye bye bye", "please share ...") inside confident active vocals are still dropped because no_speech_prob > 0.4 is the norm on sung 30 s windows (jeremy 0.67, newton 0.42).
- R3-3 battle label formats: `[Name:]` gives no speaker (empty text after the colon), `Name:` alone on a line becomes a sung lyric line.
- R3-4 unbracketed section headers (`Verse 1:`, `CHORUS`, `Chorus x2`, `(Chorus)`) are parsed as sung lines; synth e2e grade A with 14 lines / 58 words for 10 / 53 and no warning; headers land in lyrics.json and every caption export.

Minors: docs/review/M5-r-words.md "Round 3" (r3-m1 sustain hold past the next line on jeremy, r3-m2 open round-2 minors).

## Runs (out/_wip/r-words-m5-r3/, counts and times only)
real newton B / 4 voices; real jeremy B (LRCLIB 22859144, last word 218.1 s) / 1 voice; megafauna transcribed D (all spans review);
versatile instrumental; synth transcribed B (onset median 20 ms), synth TXT A, synth line LRC A (offset 0.02 s);
synth-plainhdr / synth-capshdr A with phantom header lines. Leak scan: no lyric text outside lyrics/* and the cache-only _http bodies.
Tests: tests/review/M5/r-words: 19 fail (all r3 findings), 35 pass, 3 skip (real). Ruff clean.
