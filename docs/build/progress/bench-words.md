# bench-words progress
Started 2026-11-08. Resume from last checked item.
Run cmd: powershell.exe -NoProfile -File scripts/run.ps1 python <abs script> (Bash tool). Scripts in docs/research/spike-scripts/bench-words/ (prefix bw_).
Stems: tests/.cache/real/<slug>/sep/{lead_vocals,vocals}.wav exist from env-sep (stereo f32 44.1k) -> used, no own demucs.
- [x] 1 identity (4 songs): bw_identity_lrclib.py (done, outputs in tests/.cache/real/<slug>/{identity,http,lyrics_src})
- [x] 2 LRCLIB cascade done: jeremy 22859144 (d0.000), newton chosen by dur 25570391 (plain) but synced 3921433 (d-0.435) used for alignment; megafauna none (embedded tag 428 chars); versatile none (false friend rejected by artist gate)
- [ ] 3 whisper cpu (jeremy, newton)
- [ ] 4 MMS align + stable-ts
- [ ] 5 voices (newton)
- [ ] 6 rhubarb + mouth_open
- [ ] 7 docs/spike/bench-words.md + report
## status
- whisper done (bw_whisper.py): jeremy rtf0.104 f1 0.76 (LRCLIB lacks outro; asr ends 217s: tail is wordless vocals), newton rtf0.32 f1 0.835. Summaries in whisper_cpu/.
- MMS align done (bw_align.py <slug>): jeremy tok 0.40, medabs 0.245 after offset; newton tok 0.44, offset -1.32 s, vs-whisper med 0.11.  emission RTF 0.09.
- NEXT: stable-ts (bw_stablets.py), onset cross-check, repeated-section expansion test (jeremy/megafauna tag?), voices, rhubarb, doc.
- Run in bg: (cmd) > tests/.cache/real/_logs/bw-*.log
- stable-ts done (bw_stablets.py): jeremy rtf0.30 (96 s), newton rtf0.20 (34 s); onset check (bw_quality.py): MMS lift 1.34/1.25 > whisper 1.17/1.03 > stable-ts 1.13/1.09.
- voices done (bw_voices.py, ecapa+wespeaker, newton): ARI k3/k4 = 1.0, blocks A(0-14) B(16-30) A(31-41) C(42-50, f0 139Hz low voice) + announcer singleton from ASR-only seg; runs 5 vs shuffled 32. ECAPA chosen (silhouette .354 at k=4).
- expansion test, lipsync+mouth, gate stats DONE. NEXT: write docs/spike/bench-words.md + docs/build/reports/bench-words.md, return structured summary.
- ALL DONE. report at docs/build/reports/bench-words.md
