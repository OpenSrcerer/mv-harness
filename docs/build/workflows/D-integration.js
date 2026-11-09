export const meta = {
  name: 'mvh-D-integration',
  description: 'mv-harness W3: integrator, then module fixers with verifiers alongside a completeness critic, then the integrator re-run',
  phases: [
    { title: 'Integrate', detail: 'apply change requests, merge decisions, real max runs on all songs, SEAMS.md' },
    { title: 'Fix', detail: 'module fixers (opus for M1/M2/M5/M6b) and the completeness critic' },
    { title: 'Verify', detail: 'opus verifier per module fix round (up to 2 rounds)' },
    { title: 'Finalize', detail: 'integrator re-run: override round trip, RUNS.md, final max runs and gate' },
  ],
}
const COMMON = `
You are a build agent for mv-harness, at C:\\Users\\OpenSrcerer\\Desktop\\playground\\mv-harness.
mv-harness analyses one song and writes a folder of timestamped metadata so that AI agents can build an ART-PIECE music video
(choreography, characters, stylisation) without handling the low-level analysis themselves. The user makes one video at a time and
wants maximum quality: default to the best models and ensembles, add human-correction hooks, never trim features for speed.

READ FIRST, in this order:
1. PLAN.md in full (your module's §5 stage specs, §7 thresholds and §12 rules matter most).
2. docs/SPIKE.md: the W0 gate. It AMENDS the plan and wins on conflicts (recipes, thresholds, tool caveats).
3. docs/CONTRACT.md §§1-7 and §§9-14 (the frozen output contract; decisions D1-D46 win over PLAN), and the catalogue entries for your stages
   in src/mvh/contract/catalog.py. The runner is in src/mvh/runner/ (read spec.py and ctx.py: the Ctx API your run(ctx) gets).
4. docs/spike/main.md §1-2 (commands and VERIFIED library recipes: arrays in, explicit local model paths) and the spike doc for your area.
5. Your stage stubs in src/mvh/stages/<name>/__init__.py: you REPLACE run(ctx) with the real implementation and may add params, models
   (ids from models.lock.json) and optional outputs. Deps, env and the catalogue outputs are frozen.

ENVIRONMENT (built; never sync or change pyproject.toml / uv.lock / models.lock.json; put needs in change_requests):
- PowerShell: Set-Location C:\\Users\\OpenSrcerer\\Desktop\\playground\\mv-harness; . .\\scripts\\mvh-env.ps1 -Offline; uv run --frozen --no-sync python ...
  Git Bash: powershell.exe -NoProfile -File scripts/run.ps1 python ...  (set MVH_RUN_OFFLINE=1 first). In PowerShell 5.1 never add 2>&1 to native commands.
- Tests: uv run --frozen --no-sync python -m pytest -q <path>. Your gate: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\\gate.ps1 <MODULE>
  (it runs your unit tests, tests/review/<module>/**, ruff, the contract check, validate, an end-to-end analyze and determinism).
- Running your stages: mvh analyze <audio> --out out\\_wip\\<agent>\\<song> --only <your stages> (see mvh analyze --help). Upstream stages you do not
  own are still stubs that copy from the fixture folder in MVH_FIXTURE_DIR: tests/contract/synth (default; complete ground truth in _truth/) or
  tests/contract/real-<slug> for megafauna, versatile, jeremy, newton-vs-nye (real W0 data; see each coverage.json and tests/contract/README.md).
  Real audio: C:\\Users\\OpenSrcerer\\Desktop\\playground\\viz\\MEGAFAUNA.flac, viz\\Versatile.flac, mv-harness\\songs\\Jeremy (Redux Version).flac,
  mv-harness\\songs\\Sir Isaac Newton vs Bill Nye.flac. Raw W0 model outputs per song are in tests/.cache/real/<slug>/ (index.music.json, index.words.json).
- Synthetic primitives (clicks, EBU signals, sweeps, rendered MIDI, vibrato sines, TTS, edge-case files) are in tests/synth/primitives.py.

HARD RULES:
- No git and no WSL. Do not change system or security settings, drivers or Defender.
- Never print real-song lyric text in reports, logs, test output or any committed file (synthetic fixture lyrics are fine).
- Write ONLY to your owned paths. Seven other module agents work at the same time.
- Do NOT edit src/mvh/contract/**, src/mvh/runner/**, docs/CONTRACT.md, tests/contract/**, scripts/** or another module's stages
  (exception: an explicit permission in your module brief). Record contract decisions you make (additive fields, interpretations) in
  docs/contract/decisions/<MODULE>.md; anything that needs a frozen-contract or runtime change goes in change_requests for the W3 integrator.
- Heavy work (real model inference) only inside a heavy slot (the runner takes it for non-stub stages that declare models; in tests use
  mvh.testing.heavy()), max 6 threads per slot; GPU work also takes gpu.lock. Unit tests must default to synthetic inputs and run fast; tests that need
  real models or real songs are marked (e.g. @pytest.mark.real / slow) and run explicitly.
- Long commands (> ~10 minutes): run in the background with a log file and poll it.
- Every open() passes encoding="utf-8"; pathlib everywhere; no shell strings; never hand a file path to a model library when the recipe says arrays;
  never use torchaudio.load/save or soundfile on original files (ffmpeg via mvh.io.audio only).

PERSISTENCE (the orchestrating session may expire):
- Checkpoint log at docs/build/progress/<your-agent-name>.md (done, next, commands that worked, gotchas), updated after every milestone.
  If it exists when you start, read it and RESUME; do not start over.
- Write code to disk as you go. When finished, write your full report to docs/build/reports/<your-agent-name>.md, then return the structured summary.
`

const BUILD_DONE = `
DEFINITION OF DONE:
- Real implementations of all your stages, honouring every frozen output and field in the catalogue, with provenance (models, versions, params,
  fallbacks used, confidence) and QA flags where the data is unreliable.
- Unit tests in tests/unit/<stage>/ scored against synthetic ground truth with the PLAN §7 / SPIKE thresholds (assert them).
- Each of your stages run on ALL FOUR real songs (upstream from tests/contract/real-<slug>) plus the synthetic song; record per-song results,
  timings and sanity checks in your report. Real-song tests that assert snapshots use tolerances.
- scripts\\gate.ps1 <MODULE> passes.
- Report: what each stage does, measured accuracy vs thresholds, real-song observations, decisions, change requests, open issues.`

const RESULT = {
  type: 'object',
  properties: {
    agent: { type: 'string' },
    module: { type: 'string' },
    status: { type: 'string', enum: ['done', 'partial', 'failed'] },
    summary: { type: 'string' },
    deliverables: { type: 'array', items: { type: 'string' } },
    tests: { type: 'string', description: 'test commands run with pass/fail counts, and the gate result' },
    accuracy: { type: 'string', description: 'measured numbers vs thresholds on synthetic and real songs' },
    decisions: { type: 'array', items: { type: 'string' } },
    change_requests: { type: 'array', items: { type: 'string' } },
    open_issues: { type: 'array', items: { type: 'string' } },
  },
  required: ['agent', 'module', 'status', 'summary', 'deliverables', 'tests', 'open_issues'],
}

const MODULES = [
  {
    key: 'M1', name: 'Signal', stages: ['spectral', 'loudness', 'dynamics'], model: undefined, reviewers: ['R-DSP'],
    brief: `MODULE M1 Signal: stages spectral, loudness, dynamics (PLAN §5).
OWNED PATHS: src/mvh/stages/{spectral,loudness,dynamics}/**, tests/unit/{spectral,loudness,dynamics}/**, tests/synth/m1/**, docs/contract/decisions/M1.md.
KEY POINTS:
- spectral: the bands (bass, mids, highs and the rest), kick envelope and hits, onsets/flux, spectrum128 and the viz-compatible channels. Port the band
  mapping and envelopes of C:\\Users\\OpenSrcerer\\Desktop\\playground\\viz\\js\\audio.js FAITHFULLY (lib's vizState depends on these channels; see
  docs/contract/golden-addendum.md). Start from docs/research/prototypes/spectral/ (W0: kick counts within 1-10 % of the offline reference).
  Resample policies and absolute twins (dB) per CONTRACT §4-5; hit envelopes use policy max. Kick events F1 >= 0.95 at ±10 ms on synthetic one-shots.
- loudness: EBU R128 momentary/short-term/integrated, LRA, true peak; ±0.1 LU on EBU 3341/3342 signals and ±0.5 LU vs ffmpeg ebur128 on real songs.
  Loud/quiet parts are a user requirement: make them explicit and easy to read.
- dynamics: drops, builds' energy, breakdowns, silences and the I/X/Z/Y events (D4). SPIKE: fixed-threshold Foote segmentation fails on limited
  masters (Jeremy got 3 segments). Use adaptive thresholds plus bass and kick features, falling back to allin1 sections. MEGAFAUNA must find its drops.`,
  },
  {
    key: 'M2', name: 'Rhythm', stages: ['allin1', 'rhythm', 'structure', 'choreo', 'cues'], model: undefined, reviewers: ['R-DSP'],
    brief: `MODULE M2 Rhythm: stages allin1, rhythm, structure, choreo, cues (PLAN §5). This is the backbone choreography agents dance to.
OWNED PATHS: src/mvh/stages/{allin1,rhythm,structure,choreo,cues}/**, tests/unit/{allin1,rhythm,structure,choreo,cues}/**, tests/synth/m2/**,
docs/contract/decisions/M2.md.
KEY POINTS:
- allin1: all-in-one-infer 3.1.0 has no AllInOneSession; call analyze(stems_input=StemsInput(...)) with four float32 stem WAVs you write
  (docs/spike/main.md §2). Keep activations and embeddings (cache-only per D18).
- rhythm: fuse beat_this logits, allin1 and the tempogram/PLP. SPIKE: beat_this flips half/double tempo and madmom's downbeat phase is one beat off on
  2 of 4 songs. Carry TEMPO CANDIDATES and a per-segment feel, arbitrate the tempo octave against kick evidence, and FUSE DOWNBEATS BY A 2-OF-3 VOTE
  (beat_this, allin1, madmom-infer DBN). MEGAFAUNA (≈105 / 143.6 / 193-200 BPM) is the regression case; decide with evidence and record the
  alternatives so the user can override (override keys rhythm.bpm, rhythm.beat_offset_s, rhythm.downbeat_phase). Thresholds: beats F1 >= 0.98 at ±70 ms
  on clicks, tempo error <= 0.5 BPM, pickups, 3/4 bars, no-pulse regions (in_pulse false, D11/D12).
- structure: sections S01.. with label, occurrence and repeat_group, phrases, and DROPS AND BUILDS (defined only here). allin1 labels are
  uninformative on electronic songs, so combine them with self-similarity and M1-style energy features you compute yourself or read from deps.
- choreo: eight-counts E### (D13, 5-6-7-8 lead-in E000), sub-counts (D14), grooves G##, accents, hit_points, holds, tables/{beats,bars,sections}.csv (D2).
  Think like a choreographer: counts must be danceable and consistent across repeated sections.
- cues: tiers 1-4 with source citations {file, id} (D4, D15). Use mvh.contract.conventions.merge_cues so there is one cue per time (D37) and write the
  optional kinds[] and sources[]. Keep cues.json context-cheap (r-contract found tier-4 beat refs were 63 % of it).`,
  },
  {
    key: 'M3a', name: 'Separation', stages: ['separate_fast', 'separate_hq', 'stem_activity', 'drums'], model: undefined, reviewers: ['R-ML'],
    brief: `MODULE M3a Separation: stages separate_fast, separate_hq (+ the envs/sep worker code), stem_activity, drums (PLAN §5, §3.3 worker protocol).
OWNED PATHS: src/mvh/stages/{separate_fast,separate_hq,stem_activity,drums}/**, src/mvh/sep/** (worker-side code, stdlib+numpy at import, torch
lazily), envs/sep/tools/** (reference scripts), tests/unit/{separate_fast,separate_hq,stem_activity,drums}/**, tests/synth/m3a/**, docs/contract/decisions/M3a.md.
EXTRA PERMISSION: the models.lock.json envelope schema mismatch (the lock has 'schema': 1, env labels sep-rocm / sep-cpu / ffmpeg-whisper and extra keys,
which the mvh/envelope/models_lock schema rejects). Fix the SCHEMA side only (src/mvh/contract catalogue/schema for models_lock, then
python -m mvh.contract.gen to regenerate, keeping gen --check and tests/unit/contract green); do not edit models.lock.json.
KEY POINTS:
- separate_fast: demucs-onnx via the ARRAY route with our own ORT session (_chunked_separate_single, fp16 weights; docs/spike/main.md §2).
  No -30 dB sum invariant here (2-10 % RMS).
- separate_hq: lift envs/sep/tools/separate_song.py into the worker (ctx.worker; docs/spike/sep.md §6, §10). Default variant rocm, cpu fallback.
  BS-RoFormer-SW 6-stem, Mel-RoFormer vocals, karaoke lead/backing on the Mel vocals, MDX23C DrumSep. Set normalization_threshold=100.0 AS AN
  ATTRIBUTE after Separator() construction and amplification_threshold=0.0; float WAV; pass explicit model paths from ctx models. Lock per model
  (ctx.worker hold_slot=False) like the reference. Invariants: six-stem sum residual <= -20 dB; per-stem gain 0.1 dB within 6 dB of the mix and
  0.5 dB within 20 dB; instrumental = mix - vocals exactly; lead + backing = vocals. backing_vocals is always written (D17).
- stem_activity: per-stem activity curves and segments. SPIKE: on MEGAFAUNA the vocals stem picks up synth leads (-12.8 dB), so vocal presence must
  not rely on stem energy alone; expose confidence so M3b/M5 can combine it with the tagger and lyrics.
- drums: per-piece hits (kick, snare, toms, hihat, ride, crash) from DrumSep sub-stems plus onset detection; F1 >= 0.9 kick/snare/hat and >= 0.7
  tom/cymbal on the synthetic song; velocities; event time = the one-shot's sample onset.
- Real separation takes ~1x real time on ROCm. The W0 stems already exist in tests/.cache/real/<slug>/sep/; reuse them for development and run
  the real stage end to end at least on newton-vs-nye (shortest) and one more song.`,
  },
  {
    key: 'M3b', name: 'Pitch & timbre', stages: ['notes', 'vocals', 'instruments'], model: undefined, reviewers: ['R-ML'],
    brief: `MODULE M3b Pitch & timbre: stages notes, vocals, instruments (PLAN §5). Notes, instruments and vocal range are explicit user requirements.
OWNED PATHS: src/mvh/stages/{notes,vocals,instruments}/**, tests/unit/{notes,vocals,instruments}/**, tests/synth/m3b/**, docs/contract/decisions/M3b.md.
KEY POINTS:
- notes: basic-pitch (onnxruntime, nmp.onnx) on bass, guitar, other; piano_transcription ONLY when the piano stem is active AND CED reports piano (on a
  silent stem it invents notes). notes/notes.mid (bass, piano, guitar, other; tempo map from the beat grid), notes/<src>.mid, events/notes.<src>.json.
  D6/D39: vocals notes belong to the vocals stage. Bass monophonic note F1 >= 0.8.
- vocals: RMVPE is the arbiter gated on confidence 0.3; SwiftF0 second opinion; never use SwiftF0 for vocal presence on rap. f0 NaN when unvoiced,
  vocal.pitch01 from p2-p98 with a 150 ms ease, vocal.voiced (policy max), vocal range (±1 semitone on the synthetic vibrato sines; Jeremy's sustained
  range was G3-G#4 in W0), events/notes.vocals.json and notes/vocals.mid, phrases. Vocal presence combines stem activity, the instruments tagger and
  lyrics coverage when available (MEGAFAUNA's vocals stem is mostly synth leads).
- instruments: CED-base ONNX (output is ALREADY a probability; never apply a sigmoid) on the mix and stems, over time (instruments_1hz curves and
  segments); CLAP (Xenova larger_clap_music_and_speech) only for relative curves and user-supplied terms, never a top-1 label.`,
  },
  {
    key: 'M4', name: 'Harmony & mood', stages: ['harmony', 'mood'], model: 'sonnet', reviewers: ['R-ML'],
    brief: `MODULE M4 Harmony & mood: stages harmony, mood (PLAN §5).
OWNED PATHS: src/mvh/stages/{harmony,mood}/**, tests/unit/{harmony,mood}/**, tests/synth/m4/**, docs/contract/decisions/M4.md.
KEY POINTS:
- harmony: lv-chordia chords (it takes a path to a float32 WAV you write; major/minor vocabulary; no-chord share 4.5-22 % on real songs), chroma12,
  key and modulations. S-KEY ONNX (22.05 kHz mono peak-normalised) gives a FLAT probability, so derive confidence from windowed agreement with a
  Krumhansl-Schmuckler/Temperley profile ensemble; report the key with its alternatives. Score chords and key on the synthetic song (A minor, known
  progression in _truth/).
- mood: Essentia ONNX heads (msd-musicnn embeddings into emoMusic / DEAM; mtg_jamendo moodtheme; numpy mel port in
  docs/research/prototypes/lyrics-meaning/mood_onnx.py). Arousal is fairly reliable; valence is low confidence (the heads disagree): expose per-head
  values and a confidence. mood_1hz curves plus section-level summaries a director can use. Mood is a hint; the user's meaning wins.`,
  },
  {
    key: 'M5', name: 'Words', stages: ['identity', 'lyrics', 'voices', 'lipsync'], model: undefined, reviewers: ['R-WORDS'],
    brief: `MODULE M5 Words: stages identity, lyrics, voices, lipsync (PLAN §5). Timestamped lyrics and multi-voice sync are core user requirements;
the rap battle (newton-vs-nye: 3 rappers plus an announcer) is the stress test.
OWNED PATHS: src/mvh/stages/{identity,lyrics,voices,lipsync}/**, tests/unit/{identity,lyrics,voices,lipsync}/**, tests/synth/m5/**,
tests/fixtures/http/** (SYNTHETIC recorded HTTP only; real responses with lyrics stay in gitignored tests/.cache/), docs/contract/decisions/M5.md.
EXTRA PERMISSION: you may add 'ingest' to the lyrics stage's deps (runtime change request: embedded lyric tags live only in ingest's cache-only
embedded_lyrics.json, D32). Record it as a decision; keep tests/unit/contract green (update nothing there; if a contract DAG test pins the deps,
put the needed test change in change_requests instead and keep the dep change).
KEY POINTS:
- identity: ffprobe tags, chromaprint, MusicBrainz (1 req/s, UA "mv-harness/0.1 (https://github.com/OpenSrcerer/mv-harness)"); for version-tagged
  titles retry without the parenthesised tag, page past 8 results, back off on 503. AcoustID only if a key is configured.
- lyrics cascade: LRCLIB (get with album, get without album, ALWAYS search; after the title/artist gate prefer has_synced among candidates within 2 s,
  then smallest |Δdur|), then embedded tags, then user-supplied lyrics, then Whisper transcription (faster-whisper large-v3 int8 CPU on lead_vocals,
  arrays only, VAD, hallucination filter; ffmpeg Vulkan whisper filter without vad_model only as a draft flag). Global offset detection is a MUST
  (apply when |offset| > 0.15 s, flag a version mismatch above 3 s; newton is -1.33 s). Word alignment with torchaudio MMS_FA forced_align (vendored
  CTC Viterbi fallback, then stable-ts), 30 s windows with context, line-window constraints, uroman + num2words, repeated-section expansion that only
  ADDS repeats. Grade with the measured gate G1-G8 (docs/spike/bench-words.md §5); never gate on per-line mean score. Outputs per catalogue (lyrics.json
  with speaker_hint per D3, .lrc/.vtt/.srt/.ass). Jeremy: LRCLIB 22859144 and no lyric words after ~217 s. Word alignment on TTS: median onset error < 80 ms.
- voices: SpeechBrain ECAPA (LocalStrategy.COPY, explicit pretrained_path; no symlink privilege on this machine) primary, WeSpeaker ONNX fallback;
  per-line embeddings on lead_vocals, agglomerative clustering, eigengap is only a lower bound and the user's character count wins (intent.md /
  overrides). Propose V# per line and voice_spans; the user maps voices to characters in the viewer.
- lipsync: vocal.mouth_open gated by the SUSTAIN-EXTENDED word span (word end held to the next word start; a line's last word held while the envelope
  stays within 20 dB of p95, at most 1.5 s) plus an ungated fallback for wordless vocals; per-voice mouth_open.<V> when 2+ voices (D16). Rhubarb 1.14.0
  (-f json -o file, 16 kHz 16-bit WAV, -d dialog file in scratch, deleted after) is a decoration track for visemes/phonemes; on dense rap it rarely
  closes the mouth.
- Privacy: lyric text never in logs, errors, reports or test output (the runner already strips schema-error values).`,
  },
  {
    key: 'M6a', name: 'Viewer', stages: ['viewer'], model: 'sonnet', reviewers: ['R-PLATFORM'],
    brief: `MODULE M6a Viewer: the viewer stage, src/mvh/assets/viewer/, the mvh view server and edit-mode POST (PLAN §9).
OWNED PATHS: src/mvh/stages/viewer/** (including an optional cli.py that registers the 'view' verb, D35), src/mvh/assets/viewer/**,
tests/unit/viewer/**, docs/contract/decisions/M6a.md.
KEY POINTS:
- The user explicitly wants to VIEW: notes, beats, instruments, vocal range, loud/quiet parts, lyrics (timestamped, per singer), sections and
  cues, and the song's true meaning. Build a polished single-page viewer that plays audio/mix (or preview.opus) and scrolls synced lanes for all of
  these, with a stem solo/mute, click-track metronome for listening checks, and zoom.
- viewer.html works from file:// read-only with preview data inlined (size-capped), and through 'mvh view <song>' (127.0.0.1, port 0, idle timeout)
  in EDIT MODE: corrections (beat offset, BPM, downbeat phase, section boundaries and labels, lyric line/word timing, voice to character mapping,
  meaning per section) are POSTed to overrides.json (atomic write, validated against its schema) and the user is told which stages will re-run.
- Use lib/mvh.js from the song folder for all data access (do not reimplement helpers).
- Verify in a real browser with the Claude_Browser preview tools (mcp__Claude_Browser__*, load via ToolSearch) on the synthetic folder and at
  least one real-song folder from out/_wip; take screenshots and check console errors. Stop servers before reporting.`,
  },
  {
    key: 'M6b', name: 'Agent delivery', stages: ['meaning', 'brief', 'frames'], model: undefined, reviewers: ['R-CONTRACT', 'R-WORDS'],
    brief: `MODULE M6b Agent delivery: stages meaning, brief, frames, plus skill/mv-harness/ (PLAN §8, §4.7, §10).
OWNED PATHS: src/mvh/stages/{meaning,brief,frames}/** (optional cli.py files registering 'brief', 'frames', 'meaning' verbs, D35),
skill/mv-harness/**, tests/unit/{meaning,brief,frames}/**, docs/contract/decisions/M6b.md.
KEY POINTS:
- meaning lifecycle (§8, D3, D5, D7): interview.md (questions for the user), intent.md and authored.json are INPUTS never overwritten or deleted;
  meaning.json / meaning.md merged output with provenance (user > authored draft > pending); re-anchoring when sections change, leftovers to
  orphans.json; request.md, input.json and schema.json for an LLM/agent drafting pass (labelled as a draft). Produces events/singing.json and
  lyrics/lines.tsv with the singer column written as 'C1+C2' for multi-singer lines (D38). Characters C# from intent/meaning mapped to voices.
- brief.md: the LLM entry point, <= 4k tokens (target 2.5k), exactly per CONTRACT §12 / PLAN §4.7; 'mvh brief --section S05' zooms <= 1.5k tokens.
  Every number in it must trace back to a file.
- frames: on-demand <fps>fps.csv export (D19) using the frame rules (rational fps, frame0, early) via conventions; never NaN.
- skill/mv-harness/SKILL.md + references/{CONTRACT.md (generated copy), RECIPES.md}: how a video agent (Remotion, three.js, Blender, ComfyUI) uses
  one output folder for choreography, characters and stylisation; point to CONTRACT §§2-4 and §9 and brief.md, not the whole 25k-token contract.
  Recipes: dancing on counts and hits, lip sync per singer, camera on cues, palette and meaning per section, viz/ scenes via vizState.`,
  },
]

const LENS = {
  'R-DSP': 'Signal and rhythm correctness: units, time alignment, frame rules, viz-port fidelity (viz/js/audio.js), beat_this/allin1 pre-processing, fusion logic, synthetic-truth tests that actually test behaviour.',
  'R-ML': 'Model use: pre- and post-processing matching how each model was trained (sample rate, channels, normalisation, windowing), ensemble arbitration, licences and SHA pins in provenance, CPU vs ROCm behaviour, the separator gain invariants, gating against hallucinated output.',
  'R-WORDS': 'Lyrics and meaning: the source cascade, LRCLIB etiquette, alignment quality and its gate, hallucination filtering, offset detection, voices and character mapping, citation validation, the meaning lifecycle (inputs never overwritten), lyrics privacy (no lyric text in logs, errors, reports, tests).',
  'R-PLATFORM': 'Windows platform and the viewer: paths and Unicode, the local server (127.0.0.1, port 0, idle timeout, no path traversal, POST validation, atomic overrides writes), file:// mode, and the viewer itself in a real browser via the mcp__Claude_Browser__* tools (load via ToolSearch): every required lane present and synced to audio, no console errors.',
  'R-CONTRACT': '"The video agent": act as a Remotion, three.js, Blender or ComfyUI agent building a choreographed, character-driven video from one output folder plus skill/mv-harness/SKILL.md. Check that what it needs is present, unambiguous, cheap to load and safe for context; that brief.md is within caps and every number traces to a file; that frames exports obey the frame rules.',
}

const REVIEW_SCHEMA = {
  type: 'object',
  properties: {
    reviewer: { type: 'string' },
    module: { type: 'string' },
    verdict: { type: 'string', enum: ['pass', 'pass-with-fixes', 'fail'] },
    summary: { type: 'string' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          severity: { type: 'string', enum: ['blocker', 'major', 'minor'] },
          location: { type: 'string' },
          claim: { type: 'string' },
          evidence: { type: 'string' },
          suggested_fix: { type: 'string' },
          test_path: { type: 'string' },
        },
        required: ['severity', 'location', 'claim', 'evidence'],
      },
    },
  },
  required: ['reviewer', 'module', 'verdict', 'summary', 'findings'],
}

// RESUME (see docs/BUILD-STATUS.md): args = {resume: {M5: 'build', M6b: 'fix', ...}}. For a listed module, every prompt from that step on gets a
// suffix, so its cache key changes and the agent reruns live (agents that died on the usage limit were journalled as null). Unlisted modules and
// earlier steps keep identical prompts, so they come back from the cache.
// Order: build 0, review 1, fix r = 2r, rereview after fix r = 2r+1.
const ORD = (step, r) => step === 'build' ? 0 : step === 'review' ? 1 : step === 'fix' ? 2 * r : 2 * r + 1
const RESUME = (args && args.resume) || {}
function rs(m, step, round) {
  const from = RESUME[m.key]
  if (!from) return ''
  const [s, r] = String(from).split(':')            // e.g. 'fix:2' = from fix round 2
  const at = ORD(step, round || 1), want = ORD(s, Number(r) || 1)
  return at >= want ? `\nRESUMED after an interruption: if docs/build/progress/<your name>.md exists, read it first and continue from it; do not redo finished work.` : ''
}

function reviewPrompt(m, lens, round, prior) {
  const slug = lens.toLowerCase()
  const name = `${slug}-${m.key.toLowerCase()}${round > 1 ? '-r' + round : ''}`
  return COMMON + `
YOUR NAME: ${name}. You are an INDEPENDENT REVIEWER (PLAN §11) of module ${m.key} ${m.name} (stages: ${m.stages.join(', ')}).
LENS ${lens}: ${LENS[lens]}
The module brief the builder worked from:
${m.brief}
You get the code and the spec, not the builder's conclusions: form your own findings before reading docs/build/reports/, and then use it only to locate
things. Run the code: on the synthetic song (score against tests/contract/synth/_truth/) and on real songs (tests/contract/real-<slug> upstream).
Probe edge cases (tests/synth/primitives.py has mono, 48 kHz, MP3 with encoder delay, corrupt FLAC, 10 s, unicode paths). Compare against the PLAN §7 /
SPIKE thresholds and the contract.
A finding is {id, severity: blocker|major|minor, location, claim, evidence, suggested_fix}. For EVERY blocker or major, write the evidence as a FAILING
test under tests/review/${m.key}/${slug}/ (pytest or node --test), verify it fails now for the stated reason, and put its path in test_path.
Do not fix production code. Minor findings go in docs/review/${m.key}-${slug}.md${round > 1 ? ' (append a "Round ' + round + '" section)' : ''}.
Do not pad with style nits; verify every claim by running code.
OWNED PATHS: tests/review/${m.key}/${slug}/**, docs/review/${m.key}-${slug}.md, out/_wip/${name}/**, docs/build/progress/${name}.md, docs/build/reports/${name}.md.
${rs(m, round > 1 ? "rereview" : "review", round > 1 ? round - 1 : 1)}${round > 1 ? `ROUND ${round}: a fixer has addressed these earlier findings:\n${JSON.stringify(prior, null, 1)}\nFirst verify each is truly fixed (the test passing is necessary, not sufficient: check the fix is real and not a test-specific hack). Report any that are not fixed as findings again. Then look for NEW blockers and majors, especially regressions introduced by the fixes.` : ''}`
}

function fixPrompt(m, findings, round) {
  const name = `fixer-${m.key.toLowerCase()}${round > 1 ? '-r' + round : ''}`
  return COMMON + `
YOUR NAME: ${name}. Module ${m.key} ${m.name} (stages: ${m.stages.join(', ')}). Reviewers wrote failing tests under tests/review/${m.key}/** and review
files docs/review/${m.key}-*.md. Their blocker and major findings are below.
The module brief:
${m.brief}
OWNED PATHS: the module's owned paths above, plus docs/build/progress/${name}.md and docs/build/reports/${name}.md. Do NOT edit tests/review/**.
If a review test is demonstrably wrong, leave it failing and explain why under open_issues. Fixes that need another module's or the runtime's files go in
change_requests (the W3 integrator applies them).
GOAL: every tests/review/${m.key}/** test passes with a REAL fix (no test-specific special cases), the module's unit tests still pass, and
scripts\\gate.ps1 ${m.key} exits 0. Also fix cheap, safe minor findings. One round: fix, run the gate, report.
FINDINGS:
${JSON.stringify(findings, null, 1)}${rs(m, "fix", round)}`
}

const serious = rs => rs.filter(Boolean).flatMap(r => (r.findings || []).filter(f => f.severity !== 'minor').map(f => ({ reviewer: r.reviewer, ...f })))


// ======================================================================================= W3 INTEGRATION (workflow D)
const W3 = `
W3 INTEGRATION CONTEXT (this OVERRIDES any W2-era statement above, e.g. "upstream stages are still stubs"):
- Workflow C (W2) is finished. All stages have real implementations; no stubs remain. Real upstream for any stage comes from real runs, not fixtures.
- Read docs/BUILD-STATUS.md first. Then:
  - docs/build/W2-open-findings.md (+ .json): 2 blockers and 21 majors still open after W2, each with a failing test under tests/review/**;
  - docs/build/W2-change-requests.md: 59 change requests and 104 open issues from the W2 builders and fixers. Some are stale; verify each one.
- The orchestrator's full gate after W2: out/_wip/orchestrator/gate-all-W2.log.
- The integrator's real-song outputs (once phase 1 is done) are in out/_wip/integrator/<slug>/ and the integration notes are in docs/SEAMS.md.
- The power has failed twice tonight: checkpoint your progress file after EVERY milestone and keep long runs resumable (stage caching does this).
`

const INTEGRATOR_SCHEMA = {
  type: 'object',
  properties: {
    ...RESULT.properties,
    seams: {
      type: 'array', items: {
        type: 'object', properties: {
          id: { type: 'string' }, module: { type: 'string', enum: ['M1', 'M2', 'M3a', 'M3b', 'M4', 'M5', 'M6a', 'M6b', 'RUNTIME'] },
          severity: { type: 'string', enum: ['blocker', 'major', 'minor'] }, summary: { type: 'string' }, test_path: { type: 'string' },
          status: { type: 'string', enum: ['open', 'fixed'] },
        }, required: ['id', 'module', 'severity', 'summary', 'status'],
      },
    },
    songs: {
      type: 'array', items: {
        type: 'object', properties: {
          slug: { type: 'string' }, profile: { type: 'string' }, status: { type: 'string' }, minutes: { type: 'number' }, out_dir: { type: 'string' },
          notes: { type: 'string' },
        }, required: ['slug', 'profile', 'status'],
      },
    },
  },
  required: [...RESULT.required, 'seams', 'songs'],
}

const INTEGRATOR_RULES = `
YOU ARE THE ONLY AGENT RUNNING IN THIS PHASE, so the W2 ownership rule is lifted for you. You may edit src/mvh/contract/**, src/mvh/runner/**,
docs/CONTRACT.md, tests/contract/**, scripts/** and any module's files, to apply a change request or fix an integration seam.
Still forbidden: git/WSL, syncing envs or editing pyproject.toml dependencies / uv.lock / models.lock.json entries (record such needs as change_requests
for the orchestrator), and system/security settings. Keep every existing test meaningful: never weaken a review test to make it pass.`

function integratorPrompt() {
  return COMMON + W3 + INTEGRATOR_RULES + `
YOUR NAME: integrator. You run W3 step 1-3 of PLAN §12.
1. Apply the change requests in docs/build/W2-change-requests.md. Verify each one against the current code first; skip stale ones and say why.
   Known ones include:
   - move the '# ruff: noqa: E501' file headers into pyproject [tool.ruff] per-file-ignores (that file section is not a dependency change);
   - fix tests/unit/contract::test_stub_files_are_stubs, now that no stubs remain;
   - lyrics deps += ingest;
   - the M5 voices and M6b meaning stages must read the viewer's managed intent.md block and apply overrides.voices.lines;
   - --no-lyrics-to-agents → viewer.inline_lyrics=false;
   - moments.d nullable vs the events envelope;
   - the lib→finalize copy of mvh.d.ts.
   Do not try to fix the open review findings (docs/build/W2-open-findings.md): the module fixers in the next phase own them. Fix one only when it is
   purely a cross-module or runtime seam that no module can fix alone, and say so.
2. Merge docs/contract/decisions/*.md into docs/CONTRACT.md as numbered decisions after D46. Keep them additive; the frozen contract changes only
   where a change request requires it, recorded as a decision. Bump the contract to v1.0.0-rc.2 and regenerate the schemas
   (python -m mvh.contract.gen) so 'gen --check' passes. Keep the per-module decision files as history.
3. Gate: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\\gate.ps1 all. Everything must pass except the tests/review/** tests that belong to
   the still-open findings; list exactly which tests fail and why.
4. Real runs:
   - mvh analyze --profile draft on Jeremy (Redux Version) first (fast sanity check), into out\\_wip\\integrator\\jeremy-draft.
   - Then mvh analyze --profile max on ALL FOUR real songs and the synthetic song (tests/contract/synth audio or the synth build output),
     into out\\_wip\\integrator\\<slug>. Run them in the background with logs. They share two heavy slots, so expect around an hour or more.
   - Wait for them all, then mvh validate each folder.
   - Record per song and per stage: wall time, status, degraded/QA flags, sizes and token caps (manifest/brief caps).
5. Inspect the real outputs as a choreography or character agent would (brief.md, manifest, counts, hits, sections, lyrics lines.tsv, singers,
   meaning), and look for seams:
   - modules disagreeing (e.g. section boundaries vs downbeats, hits vs counts, singers vs voices vs lyrics);
   - missing or empty data on real songs;
   - wrong units or offsets; things only visible end to end;
   - runtime problems: caching, re-runs, locks, worker, timings, determinism, disk.
   Never quote lyric text.
6. Write docs/SEAMS.md: each item gets an id (S01..), its owning module (M1..M6b, or RUNTIME for runner/contract/lib/CLI issues you fix
   yourself), severity, evidence, and a failing test under tests/integration/<module>/ where one is feasible. Fix the RUNTIME items yourself now and
   mark them fixed.
7. Report to docs/build/reports/integrator.md. Return the structured result: seams lists every SEAMS item with its status; songs lists every run.
OWNED PATHS (outputs): docs/SEAMS.md, tests/integration/**, out/_wip/integrator/**, docs/build/progress/integrator.md, docs/build/reports/integrator.md, plus the
edits above.`
}

const FIX_MODEL = { M1: undefined, M2: undefined, M5: undefined, M6b: undefined, M3a: 'sonnet', M3b: 'sonnet', M4: 'sonnet', M6a: 'sonnet' }   // undefined = opus (session model)
const HARD = {
  M1: `NOTE: kick detection (hits.kick) has failed two fix rounds. Each fix traded one failure for another: bass/kick beating counted as double kicks,
then real kicks dropped under busy top end, plus missed 16th double kicks at 160 BPM. Step back and design it from first principles against ALL the
review tests at once (tests/review/M1/**). Consider transient shape plus sub-band onset coherence, not a single click heuristic. If kicks are
fundamentally better taken from the drums stage's kick sub-stem, you cannot change deps: put that proposal in change_requests with evidence, and still
make spectral's own path as good as you can.`,
  M2: `NOTE: structure fixes have repeatedly passed only on circular inputs (fixture rhythm = truth). Test with the recorded REAL rhythm and with
±10-20 ms bar jitter (see tests/review/M2/r-dsp/test_structure_rhythm_jitter.py). Keep MEGAFAUNA's drop plateau intact
(test_structure_drop_extent_real.py).`,
  M5: `NOTE: lyric-alignment fixes have caused regressions: newton grade B→C, Jeremy split into 4 voices, LRC ID tags read as speakers, and the
hallucination filter dropping real lines. Every change must keep or improve the grades on all real songs. Re-run the lyrics and voices stages on
all four real songs and compare against the W2 numbers before you report.`,
  M6b: `NOTE: parsing the user's meaning (intent.md) has not converged: each fix opened new cases (fence or no fence, hex colours read as YAML
comments, do-not detection too greedy or too narrow, untouched template counted as answered). Replace the heuristics with ONE documented,
tolerant grammar that the interview template round-trips exactly. Add a property-style test over the template variants in the review tests.
Also read the viewer's managed block (docs/contract/decisions/M6a.md).`,
}

function w3FixPrompt(m, findings, seams, round) {
  return fixPrompt(m, findings, round + 2) + `
${W3}
W3 MODULE FIX (round ${round} of at most 2). Besides the open W2 findings above, the integrator routed these integration seams to your module
(see docs/SEAMS.md; failing tests under tests/integration/${m.key}/ where present):
${JSON.stringify(seams, null, 1)}
${HARD[m.key] || ''}
GOAL:
- Every tests/review/${m.key}/** and tests/integration/${m.key}/** test passes with a REAL fix.
- Re-run your stages on all four real songs and the synthetic song, using the integrator's max outputs as upstream (copy the folder to
  out\\_wip\\<your name>\\<slug> and use --only / --force for your stages), and compare against the integrator's results. Show no regression.
- scripts\\gate.ps1 ${m.key} passes.
A test you believe is wrong: leave it failing, with the reason in open_issues. Cross-module needs go in change_requests (the integrator applies them
next).`
}

const CRITIC_PROMPT = COMMON + W3 + `
YOUR NAME: critic-w3. You are the W3 COMPLETENESS CRITIC (PLAN §11/§12, lens R-CONTRACT: "the video agent").
Act as an agent building a choreographed, character-driven art-piece music video in Remotion, three.js, Blender or ComfyUI, using ONLY the output
folders in out/_wip/integrator/<slug>/ (the max runs), skill/mv-harness/SKILL.md and the lib (src/mvh/assets/mvh.js, mvh_load.py, mvh.glsl).
Fill a matrix in docs/review/W3-completeness.md. One row per PLAN requirement R1–R20 and per §4 output file. Columns:
- producing stage;
- test that covers it;
- present and plausible in EACH real song's output (check the actual numbers, e.g. do beats line up with audible kicks? do sections match the
  song's form? do singers switch where the voices change?);
- usable by a choreography or character agent (unambiguous, cheap to load, context-safe);
- licence recorded.
Every Must that is missing, broken or unusable becomes a finding (blocker if a Must is absent or wrong, major if it is present but unusable). Write a
failing test under tests/review/W3/critic/ for each. Put the owning module (M1..M6b or RUNTIME) first in the finding's location, e.g.
"M2: src/mvh/stages/cues/...". Do not fix production code. Never quote lyric text.
OWNED PATHS: docs/review/W3-completeness.md, tests/review/W3/critic/**, out/_wip/critic-w3/**, docs/build/progress/critic-w3.md, docs/build/reports/critic-w3.md.`

function finalPrompt(phase1, fixes, critic) {
  return COMMON + W3 + INTEGRATOR_RULES + `
YOUR NAME: integrator-r2. You are the W3 integrator's re-run (PLAN §12 W3 steps 4-6). Read docs/build/progress/integrator.md and
docs/build/reports/integrator.md first: that is your own phase-1 work.
Phase-2 results:
- module fixer and verifier outcomes: ${JSON.stringify(fixes, null, 1)}
- completeness critic: ${JSON.stringify(critic, null, 1)}
DO:
1. Apply the fixers' change_requests, and fix the critic's findings plus any fixer or verifier issues still open that are cross-module or small and
   safe. You are the only agent running now. Leave hard algorithmic work for W4 only when you can't fix it, recorded in SEAMS with the reason.
2. The override round-trip test (R19, a W3 acceptance test) as tests/integration/test_override_roundtrip.py, run on real stages (synth plus one real
   song). It must cover:
   - a viewer-style POST to the edit server, or a direct write of overrides.json and of the managed intent.md block;
   - mvh analyze re-running ONLY the affected stages (assert it from run.json/provenance);
   - the change appearing in the outputs: a section boundary edit, a BPM or downbeat edit, a singer/voice mapping edit, a pinned cue, and a meaning
     edit re-anchored to the edited sections.
3. Re-run --profile max on all four real songs and the synthetic song (stage caching re-runs only what changed), then mvh validate each.
   Then run the full gate (scripts\\gate.ps1 all) and a determinism re-run.
4. Write docs/RUNS.md:
   - commands, profiles, timings per stage and song (draft vs max), disk use, the heavy-slot behaviour;
   - CPU vs ROCm, re-run and correction workflow, troubleshooting;
   - which known-weak areas are flagged in the outputs.
5. Update docs/SEAMS.md statuses and docs/CONTRACT.md for any new decisions. Report to docs/build/reports/integrator-r2.md. In the structured result,
   seams = every item still open (for W4), and songs = the final runs.`
}

phase('Integrate')
const p1 = await agent(integratorPrompt(), { label: 'integrator', phase: 'Integrate', schema: INTEGRATOR_SCHEMA })
if (!p1) throw new Error('integrator returned null (interrupted?): relaunch; it resumes from docs/build/progress/integrator.md')
log(`integrator: ${p1.status}; ${p1.seams.length} seams (${p1.seams.filter(s => s.status === 'open' && s.severity !== 'minor').length} open blocker/major); ${p1.songs.length} runs`)

const OPEN = args && args.open_findings ? args.open_findings : {}
const seamsBy = {}
for (const s of p1.seams) if (s.module !== 'RUNTIME' && s.status === 'open') (seamsBy[s.module] = seamsBy[s.module] || []).push(s)
const targets = MODULES.filter(m => (OPEN[m.key] || []).length || (seamsBy[m.key] || []).length)
log(`fixing modules: ${targets.map(m => m.key).join(', ')}; critic in parallel`)

phase('Fix')
const fixesP = pipeline(targets, async m => {
  const findings = OPEN[m.key] || [], seams = seamsBy[m.key] || []
  const lens = m.reviewers[m.reviewers.length - 1]
  const rounds = []
  let open = findings.concat(seams.map(s => ({ reviewer: 'integrator', ...s })))
  for (let round = 1; round <= 2 && open.length; round++) {
    const fx = await agent(w3FixPrompt(m, findings, seams, round), { label: `w3fix:${m.key}:r${round}`, phase: 'Fix', schema: RESULT, ...(FIX_MODEL[m.key] ? { model: FIX_MODEL[m.key] } : {}) })
    if (!fx) throw new Error(`${m.key} w3 fixer null`)
    const vr = await agent(reviewPrompt(m, lens, round + 3, open) + W3 + `
W3 VERIFY: also check tests/integration/${m.key}/** and the seams above, and re-run the module on at least two real songs from the integrator's
outputs to look for regressions.`, { label: `w3verify:${m.key}:r${round}`, phase: 'Verify', schema: REVIEW_SCHEMA })
    if (!vr) throw new Error(`${m.key} w3 verifier null`)
    rounds.push({ fixer: fx, verify: vr })
    open = serious([vr])
    log(`${m.key}: after W3 fix round ${round}, ${open.length} blocker/major remain`)
  }
  return { module: m.key, rounds: rounds.map(r => ({ fixer_status: r.fixer.status, change_requests: r.fixer.change_requests || [], fixer_open: r.fixer.open_issues, verdict: r.verify.verdict })), open_serious: open }
})
const criticP = agent(CRITIC_PROMPT, { label: 'critic-w3', phase: 'Fix', schema: REVIEW_SCHEMA })
const [fixes, critic] = await Promise.all([fixesP, criticP])

phase('Finalize')
const p3 = await agent(finalPrompt(p1, fixes, critic), { label: 'integrator-r2', phase: 'Finalize', schema: INTEGRATOR_SCHEMA })
return { integrator: { status: p1.status, seams: p1.seams, songs: p1.songs }, fixes, critic: critic && { verdict: critic.verdict, findings: critic.findings }, final: p3 }
