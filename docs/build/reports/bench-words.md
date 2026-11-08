# bench-words report

Status: **done**. Full findings, tables and the proposed measured gate: `docs/spike/bench-words.md`.

## Deliverables
- `docs/spike/bench-words.md` (timings, quality numbers, gate G1-G8, voices and Rhubarb verdicts, go/no-go, change requests, reproduce commands).
- Scripts: `docs/research/spike-scripts/bench-words/bw_*.py` (identity_lrclib, whisper, whisper_tail, align, stablets, quality, expand, gate, voices, lipsync, mouth, common).
- Gitignored artefacts under `tests/.cache/real/<slug>/{http,identity,lyrics_src,whisper_cpu,align_mms,align_stablets,voices,rhubarb,mouth_open}` and `tests/.cache/real/index.words.json`.
- Progress log `docs/build/progress/bench-words.md`.

## Headline numbers (jeremy / newton-vs-nye)
- LRCLIB: jeremy 22859144 confirmed (delta 0.000 s; `/get` alone was 2.4 s off); newton chosen 3921433 (synced) although 25570391 (plain) has the smaller delta; megafauna and versatile have no entry.
- Whisper large-v3 int8: RTF 0.104 / 0.321; lyrics_match_score F1 0.762 / 0.835.
- MMS_FA (torchaudio op): emissions RTF 0.09, Viterbi 0.07 s; mean token score 0.399 / 0.443; coverage (score >= 0.1) 0.80 / 0.78; median |CTC - LRCLIB line start| 0.19 s / 1.32 s raw; global offset -0.11 s / -1.33 s.
- stable-ts align: RTF 0.30 / 0.20; line level fine, word level weaker; fallback only.
- Voices (newton): ECAPA and WeSpeaker give identical partitions at k=3 and 4 (ARI 1.0); ECAPA picked; k=4 sequence is blocks A(0-14) B(16-30) A(31-41) C(42-50) plus an announcer probe; plausible, not verified against labels.
- Rhubarb 1.14.0: 6 s per 20 s sung (RTF 0.33), 11 s per 20 s rap; usable as a decoration track.
- mouth_open: raw CTC word spans discard up to 29 % of sung energy; use a sustain-extended gate plus an ungated fallback for wordless vocals.

## Deviations
- No own htdemucs stem; env-sep `lead_vocals` was used (checked equal to `vocals` over the sung range).
- AcoustID skipped (no key). MusicBrainz release-filter query for Jeremy returned 503 twice and was not pursued.
- Whisper hallucination filter dropped nothing, so it was not exercised on a real hallucination.
- Repeated-section expansion was tested synthetically (neither song needs it).
