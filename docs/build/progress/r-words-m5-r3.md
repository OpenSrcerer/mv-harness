# r-words-m5-r3 progress (review round 3 of M5 Words)
- started; no prior progress. Plan: verify R2-1..R2-5 fixes, then hunt regressions.
- 1: tests/review/M5 all pass (30 pass, 3 skip real). Scripts copied to out/_wip/r-words-m5-r3/scripts (run_m5.py etc).
  batch1.sh (real newton, jeremy, synth, synth-lines, megafauna, versatile) -> $W/*.log, status batch1.status
  R2-1 residual: bare "[Pre Chorus]"/"[Post Chorus]"/"[Final Chorus]"/"[Rap Verse]" headers become speakers; chorus "Time:" x2 -> labelled.
- 2: R3-1 (R2-1 residual) test_rw5_r3_speaker_labels.py: 6 fail, 1 guard pass. R3-2 (R2-3 residual: no_speech>0.4 second
  signal fires on ~50% of real sung confident segments) test_rw5_r3_hallucination_nospeech.py: 6 fail, 2 guards pass.
  R2-2 code-read: neighbour-edge clip + skip + post-repair crossing warning: looks real. R2-4/R2-5 await batch1.
- 3: R2-4 FIXED (real newton e2e grade B, G2 .758, G4 .109, offset -1.31; voices 4 estimate). R2-5 FIXED (jeremy 1 voice; 16 jitter
  trials all 1; k2 sil 0.16). R2-2 fixed by code read. NEW major R3-3: "[Name:]" headers give no speaker, "Name:" alone line
  becomes sung words -> test_rw5_r3_battle_label_formats.py (2 fail, 1 guard pass). unit tests + ruff green.
  waiting: synth, synth-lines, megafauna, versatile in batch1.
- 4: synth (transcribed) B, onset median 20 ms, voices 10/10. NEW candidate: unbracketed headers ("Chorus:", "Verse 1:", "CHORUS",
  "(Chorus)" -> backing line, "Chorus x2" -> 2 lines) become sung lines in parse_txt. batch2.sh running synth-txt / synth-plainhdr / synth-capshdr.
- 5 (resumed after power outage): synth-txt done (user TXT grade A). parse_txt probe confirms "Verse 1:"/"CHORUS"/"Chorus x2"
  become sung lines, "(Chorus)" a backing line. Re-running batch3.sh (synth-plainhdr, synth-capshdr) to measure impact.
- 6: NEW major R3-4 unbracketed headers: synth-plainhdr / synth-capshdr grade A, 14 lines / 58 words (truth 10/53), headers
  placed as words, in SRT; test_rw5_r3_unbracketed_headers.py (5 fail, 1 guard pass). real-versatile was cut by the outage
  mid-lyrics: re-running (batch4.sh -> real-versatile.log). Next: probe D31 seam replacement, offset, lipsync; write report.
- 7: versatile rerun ok (instrumental). leak scan clean. Review doc Round 3 appended (r3-m1, r3-m2). Writing report + structured output.
