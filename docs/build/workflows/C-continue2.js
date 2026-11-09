export const meta = {
  name: 'mvh-C-continue2',
  description: 'mv-harness W2: 8 module builders in a pipeline, each followed by its lens reviewer(s), a fixer and a re-review',
  phases: [
    { title: 'Build', detail: '8 module builders in parallel (6 opus, M4 and M6a sonnet)' },
    { title: 'Review', detail: 'lens reviewers write failing tests (opus)' },
    { title: 'Fix', detail: 'fixer per module when blockers/majors exist (sonnet)', model: 'sonnet' },
    { title: 'Re-review', detail: 'same lens verifies fixes and looks again (opus)' },
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


// CONTINUATION after the 2026-11-09 power outage: only the remaining steps of each unfinished module (round-2 fix and/or round-3 re-review).
// findings = round-2 re-review blockers/majors from wf_bb5257ef-656's journal. M3b and M6a had finished. args.resume adds the RESUMED suffix.
const CONT = [{"key":"M2","step":"rereview","lenses":["R-DSP"],"findings":[{"reviewer":"r-dsp-m2-r2","id":"F4-r2","severity":"major","location":"src/mvh/stages/structure/__init__.py (boundary score: dyn_b/imp_b/nov_dyn weighting, the same-group merge; repeat grouping) and tests/unit/structure + tests/review/M2/r-dsp/test_structure_real_allin1.py (fixture dynamics = truth)","claim":"F4 is not fixed. With realistic upstream, the structure stage still misses the synthetic song's chorus#1 and outro and splits the choruses into different repeat groups. The round-1 fix (melodic fingerprint, merge_keep_strong) passes the round-1 test only because that test keeps the fixture's dynamics and harmony. The fixture's events/dynamics.json segments start exactly at the truth sections (1.0/9.0/17.0/25.0/34.5/50.5 s), which is a second circular input.","evidence":"Setup: recorded real allin1 plus the fixture's exact rhythm. The real harmony and dynamics come from a full mvh analyze of the synthetic song (out/_wip/r-dsp-m2-r2/synth).\n- Real harmony chroma only: sections 1.0/9.0 (8 bars)/25.0/34.5/50.5 s, boundary F 0.909. Chorus#1 at 17.0 s is missed and the choruses fall in groups B and D.\n- Real harmony plus real dynamics: 1.0/5.0/9.0/25.0/34.5/42.5/52.5 s, F 0.615.\n- The full mvh analyze after the fix gives the same 0.615 (round 1: 0.667).\n- Either real input on its own breaks the result (p_struct_mix.py).\n- The real dynamics stage emits segments at 0/5/32.5/34.5/42.5 s and impacts at 5.0/9.0/29.0/34.5/52.5 s. The stage turns these into section boundaries, while the strong drum-pattern change at 17.0 s is not found.\n- The new test fails 4/5. The fifth test passes and demonstrates the circularity.","suggested_fix":"Score the structure tests with the recorded real upstream: real allin1, harmony and dynamics (data/*.npz). Strengthen the stage's own boundary evidence: drum and onset-pattern novelty (the 17.0 s groove change from verse to chorus) and allin1 per-stem embedding novelty. Treat dynamics segments and impacts as weak, confirmatory evidence rather than boundary sources. Calibrate the cost and the repeat threshold on the realistic synthetic upstream, not on the truth-derived fixture.","test_path":"tests/review/M2/r-dsp/test_structure_real_upstream.py"}]},{"key":"M3a","step":"fix","lenses":["R-ML"],"findings":[{"reviewer":"r-ml-m3a-r2","id":"F2","severity":"major","location":"src/mvh/stages/drums/core.py classify; src/mvh/stages/drums/__init__.py (classifier branch: conf cap 0.45)","claim":"Re-reported from round 1, still not fixed. On the clean synthetic drum stem the classifier path is still below the PLAN §7 gates for hat and cymbal. The fix marks these classes as low confidence, but only through conf, evidence and summary, which the consumers do not read.","evidence":"- core.classify on the generator drums.flac at ±10 ms: kick 0.977, snare 0.967, hat 0.793 (gate 0.9), tom 1.000, cymbal 0.444 (gate 0.7). The review test fails.\n- The choreo and cues packs project events:drum_hits to (t, drum, vel) only (src/mvh/contract/catalog.py lines 803 and 818).\n- curve:drums.{hat,cymbal} is scaled by velocity, not conf, so the unreliable hat and cymbal hits reach those agents with full weight.","suggested_fix":"Do one of these:\n- Leave hat and cymbal out of events and curves on the classifier path, as only kick, snare and tom meet the gate.\n- Scale the drums.hat and drums.cymbal envelopes and vel by the confidence cap.\n- Add a manifest-level flag such as drums:low_confidence_classes.\n\nThen update the review test to check the chosen behaviour.","test_path":"tests/review/M3a/r-ml/test_drums_classifier_path.py"},{"reviewer":"r-ml-m3a-r2","id":"F3-R","severity":"major","location":"src/mvh/sep/fit.py is_mono (side_db=-30); src/mvh/stages/separate_hq/__init__.py run (karaoke step)","claim":"F3 is only fixed for exact mono. The mono check (is_mono) switches at side energy 30 dB under mid, and anything above that is treated as stereo. A near-mono master, with side energy 24 dB under mid (L/R correlation 0.992), still makes the karaoke split invert silently. The sanity flag for backing louder than lead, asked for in round 1, was not added.","evidence":"Synthetic 17-29 s excerpt with side energy scaled to 24 dB under mid, run through ingest,separate_hq (ROCm):\n- lead_vocals -11.08 dB vs the mix, backing_vocals -6.34 dB. The truth lead is 6.4 dB over backing.\n- lead SDR 2.08 dB (8.31 dB in full stereo).\n- lead_backing_split true, flags [].\n\nWith side energy 18 dB under mid, lead and backing come out level: -8.2 / -8.0 dB.\n\nReal stereo songs measure backing 9-22 dB under lead: jeremy -7.6 / -16.8 dB, newton-vs-nye -6.6 / -29.0 dB.","suggested_fix":"- Flag sep:lead_backing_suspect, or set lead := vocals, when backing RMS is within about 3 dB of lead or above it, song-wide or per section.\n- Make the mono decision graded, not a -30 dB cliff, for example by also flagging when side energy is more than 20 dB under mid.\n- Expose a per-segment lead share of the vocal energy as the split confidence.","test_path":"tests/review/M3a/r-ml/test_r2_karaoke_near_mono.py"},{"reviewer":"r-ml-m3a-r2","id":"N1","severity":"major","location":"src/mvh/stages/drums/core.py drumsep_hits (cym_gate_db=12.0, cym_ref = 2nd loudest stroke of the sub-stem)","claim":"Regression from the F1 fix. Ride and crash hits more than 12 dB under the 2nd loudest stroke of their sub-stem are dropped, song-wide. A passage played 13 dB softer therefore loses every cymbal, even on clean sub-stems. Kick, snare and hat in the same passage are only gated at the general 30 dB level.","evidence":"Generator clean sub-stems, whole kit attenuated in 16.9-20.95 s, recall in that window:\n- Cymbal recall stays 8/9 at 0, 6 and 10 dB down, then drops to 0/9 at 13, 16, 20 and 24 dB down (cymbal_leak_dropped=9).\n- Song cymbal F1 goes from 0.974 to 0.687.\n- Kick, snare and hat recall stays 1.0 down to 20 dB.\n\nOn jeremy, lifting the gates to 30 dB brings back 52 cymbal and 96 tom hits. There is no truth there to say which of these are real.","suggested_fix":"Make the leak gate local, relative to the drum stem's own level around the hit (for example a 4-8 s window), or relative to the other sub-stems at that instant. Do not use the song's loudest strokes as the reference. Apply the same change to tom_gate_db.","test_path":"tests/review/M3a/r-ml/test_r2_drums_soft_passage.py"},{"reviewer":"r-ml-m3a-r2","id":"N2","severity":"major","location":"src/mvh/stages/drums/core.py drumsep_hits (hi-hat shape rule: cym_bright_db=11.0, absolute; weak_dull drop)","claim":"Regression from the F1 fix. A hi-hat-stem hit is relabelled cymbal, or dropped as weak_dull, when its brightness (energy above 7 kHz over 1.5-6 kHz) is under an absolute 11 dB and it decays slowly. The synthetic hats measure about 18.5 dB, but real hi-hat stems sit below 11 dB. On such a stem every open hat becomes a cymbal.","evidence":"- Typical hi-hat brightness on the fixer's real runs: newton 10.45 dB (52 relabelled to cymbal), jeremy 4.93 dB (138 relabelled, 210 dropped as weak_dull).\n- Clean generator hi-hat stem darkened to a typical brightness of 4.98 dB (15 dB cut above 6.5 kHz): all 32 open hats become cymbals and another 32 hats are dropped as weak_dull.\n- Hat F1 falls from 0.997 to 0.783, cymbal from 0.974 to 0.535.\n- With 3-12 dB of cut nothing changes; the rule switches abruptly once the typical brightness falls near 11 dB.","suggested_fix":"- Make the brightness threshold relative to the stem's own typical brightness (typ_bright minus X dB).\n- Ask for a stronger cue before relabelling an open hat, for example a coincident onset in the ride or crash stem, or a decay longer than an open hat's.\n- Test the rule on darkened and EQ'd sub-stems.","test_path":"tests/review/M3a/r-ml/test_r2_drums_dark_hihat.py"},{"reviewer":"r-ml-m3a-r2","id":"N3","severity":"major","location":"src/mvh/stages/drums/core.py drumsep_hits / src/mvh/stages/drums/__init__.py (classifier cross-check only raises conf); separate_hq DrumSep output","claim":"The F1 gates hold only for one exact separation output. The same synthetic song resampled to 48 kHz, a PLAN §7 edge case, misses the tom and cymbal gates by wide margins. The drum detector is not the cause: the DrumSep output changes between the runs, and nothing recovers the strokes it loses.","evidence":"End-to-end ROCm run of synth48.flac (fresh fixture run: 147 s, fails identically):\n- kick 0.994, snare 0.980, hat 0.908, tom 0.545, cymbal 0.514.\n- At 44.1 kHz: tom 0.857, cymbal 0.769.\n\nCross-check (sr_cross.py):\n- The 44.1 kHz sub-stems resampled to 48 kHz keep the 44.1 kHz scores; the 48 kHz sub-stems resampled to 44.1 kHz keep the 48 kHz scores. So the detector does not depend on the sample rate.\n- Differences between the two runs' stems: ride -2.8 dB, crash -5.2 dB, hihat -9.1 dB.\n- At 48 kHz, 10 of 16 rides and 5 of 8 toms are not even candidates.\n- The classifier cross-check never adds a hit.\n\nThe 44.1 kHz pass rests on margins of 1-2 hits per class.","suggested_fix":"- Recover strokes DrumSep drops: add classifier hits (tom and cymbal) with no DrumSep counterpart at low conf with evidence classifier_only.\n- Or ensemble DrumSep with a second pass (shifted chunking, or overlap 8) and take the union.\n- Score the synthetic song at both 44.1 and 48 kHz in a module test.","test_path":"tests/review/M3a/r-ml/test_r2_drums_separated_synth_48k.py"}]}]
const results = await pipeline(
  CONT,
  async c => {
    const m = MODULES.find(x => x.key === c.key)
    let fixer = null
    if (c.step === 'fix') {
      fixer = await agent(fixPrompt(m, c.findings, 2), { label: `fix:${m.key}:r2`, phase: 'Fix', schema: RESULT, model: 'sonnet' })
      if (!fixer) throw new Error(`${m.key} fix r2 null`)
    }
    const rr = await parallel(c.lenses.map(lens => () =>
      agent(reviewPrompt(m, lens, 3, c.findings), { label: `rereview:${m.key}:${lens}:r3`, phase: 'Re-review', schema: REVIEW_SCHEMA })))
    if (rr.some(r => !r)) throw new Error(`${m.key} rereview r3 null`)
    const all = rr.concat(Object.values(c.cached || {}))
    const s = serious(all)
    log(`${m.key}: final, ${s.length} blocker/major remain`)
    return { module: m.key, fixer_r2: fixer, rereview_r3: all, open_serious: s }
  },
)
return results
