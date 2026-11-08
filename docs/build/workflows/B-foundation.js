export const meta = {
  name: 'mvh-B-foundation',
  description: 'mv-harness W1b foundation: runtime, helper libs and fixtures in parallel, then R-CONTRACT and R-PLATFORM reviews, then one fixer',
  phases: [
    { title: 'Build', detail: 'runtime (opus), lib (opus), fixtures (opus) in parallel' },
    { title: 'Review', detail: 'R-CONTRACT and R-PLATFORM write failing tests' },
    { title: 'Fix', detail: 'one fixer round if there are blockers or majors', model: 'sonnet' },
  ],
}

const COMMON = `
You are a build agent for mv-harness, at C:\\Users\\OpenSrcerer\\Desktop\\playground\\mv-harness.
mv-harness analyses one song and writes a folder of timestamped metadata so that AI agents can build an art-piece music video
(choreography, characters, stylisation) without handling the low-level analysis themselves. Quality matters more than speed.

READ FIRST: PLAN.md (in full), then docs/SPIKE.md (the W0 gate; it AMENDS the plan and wins on conflicts), then docs/CONTRACT.md
§§1-4 and its Decisions section (D1-D28; also win on conflicts), then docs/spike/main.md §1-2 (commands and verified recipes).
The contract code is in src/mvh/contract/ and src/mvh/runner/spec.py; 26 stage stubs are in src/mvh/stages/<name>/__init__.py.

ENVIRONMENT (already built; never sync or change pyproject.toml/uv.lock; put needs in change_requests):
- Every shell command starts with the env script, Python only via uv:
  PowerShell: Set-Location C:\\Users\\OpenSrcerer\\Desktop\\playground\\mv-harness; . .\\scripts\\mvh-env.ps1 -Offline; uv run --frozen --no-sync python ...
  Git Bash:   powershell.exe -NoProfile -File scripts/run.ps1 python ...   (set MVH_RUN_OFFLINE=1 first for offline)
- In PowerShell 5.1 never append 2>&1 to native commands.
- Tests: uv run --frozen --no-sync python -m pytest -q <path>. Lint: uv run --frozen --no-sync ruff check src tests.
- node 26 is on PATH (for JS tests use node --test).
- The contract unit tests (tests/unit/contract, 90 tests) must keep passing.

HARD RULES:
- No git and no WSL. Do not change system or security settings, drivers or Defender.
- Never print real-song lyric text in reports, logs or any committed file. Synthetic lyrics you invent for the fixture are fine.
- Write ONLY to your owned paths (listed below). Other agents work at the same time.
- Heavy work (real model inference, separation) only inside a heavy slot: scripts/heavy_lock.py (two slots heavy-0/heavy-1 plus gpu.lock under
  %LOCALAPPDATA%\\mvh\\locks\\), at most 6 threads inside a slot. Plain ffmpeg decoding and DSP on short clips do not need a slot.
- Long commands (over about 10 minutes): run them in the background with a log file and poll.
- Analysis output goes to out/_wip/<your-agent-name>/<song>/ or pytest tmp_path, never elsewhere.
- Servers bind 127.0.0.1 on port 0 and are stopped before you report.
- Every open() passes encoding="utf-8"; JSON written with ensure_ascii=False and newline="\\n"; pathlib everywhere; no shell strings.

PERSISTENCE (the orchestrating session may expire):
- Keep a checkpoint log at docs/build/progress/<your-agent-name>.md: what is done, what is next, commands that worked, gotchas.
  Update it after every milestone. If it already exists when you start, read it and RESUME; do not start over.
- Write deliverables to disk as you go. When finished, write your full report to docs/build/reports/<your-agent-name>.md, then return the
  structured summary.
`

const RESULT = {
  type: 'object',
  properties: {
    agent: { type: 'string' },
    status: { type: 'string', enum: ['done', 'partial', 'failed'] },
    summary: { type: 'string' },
    deliverables: { type: 'array', items: { type: 'string' } },
    tests: { type: 'string', description: 'which test commands you ran and their pass/fail counts' },
    deviations_from_plan: { type: 'array', items: { type: 'string' } },
    change_requests: { type: 'array', items: { type: 'string' } },
    open_issues: { type: 'array', items: { type: 'string' } },
  },
  required: ['agent', 'status', 'summary', 'deliverables', 'tests', 'open_issues'],
}

const RUNTIME = COMMON + `
YOUR NAME: runtime. You build the W1b RUNTIME (PLAN §3.3 runner, §3.4 Windows rules, NF1-NF5, §12 W1b "runtime").
OWNED PATHS: src/mvh/cli.py, src/mvh/worker.py, src/mvh/testing.py, src/mvh/runner/** (spec.py: ADDITIVE changes only, each recorded as a new
decision in docs/CONTRACT.md "Decisions" and in deviations_from_plan), src/mvh/io/**, src/mvh/stages/__init__.py (create it or keep the
namespace package; decide), src/mvh/stages/ingest/** (the real ingest stage replaces its stub), scripts/gate.ps1, scripts/fetch_models.py
(may become a thin wrapper), tests/conftest.py, tests/unit/{runner,io,cli,ingest,worker}/**, docs/build/progress/runtime.md,
docs/build/reports/runtime.md. The only edit you may make in docs/CONTRACT.md is appending decisions.

BUILD:
1. Runner: build the DAG from the registered StageSpecs (src/mvh/runner/spec.py helpers), and run each stage in its own spawned process with the thread
   variables set before imports, the ORT SessionOptions patch, torch and ctranslate2 thread settings (§3.3). Implement the Ctx/Upstream/Writer protocols
   from spec.py exactly. Scheduler: share 8 physical cores across running stages; n is part of the cache key.
2. Cache: out/<slug>/.cache/<stage>/<key>/, keyed as in NF2 (use the full sha256 of uv.lock and models.lock.json for the env lock hash). Atomic writes:
   temp file then os.replace, retried with backoff on PermissionError. mvh status reports done, stale or pending with the reason.
3. Finalize (CONTRACT D20/D21): pack curves/*.f32 (column-major), write manifest.json, run.json and curves/index.json, copy lib/ (from
   src/mvh/assets/: mvh.js, mvh_load.py, mvh.glsl, written concurrently by the lib builder; copy whatever exists) and schema/.
4. Sep worker (§3.3 worker protocol, docs/spike/sep.md §6 and §10): launch envs/sep/<variant>/.venv/Scripts/python.exe -X utf8 -m mvh.worker <stage> job.json
   with PYTHONPATH=<repo>/src and the ffmpeg bin first on PATH. The default variant is rocm and the fallback is cpu (configurable). Workers and ffmpeg run in
   a Windows Job Object with KILL_ON_JOB_CLOSE. mvh.worker imports only the stdlib and numpy at module level. Keep the worker generic: the
   separate_hq inference code belongs to module M3a later (envs/sep/tools/separate_song.py is its reference), so you provide the protocol, job.json and
   result.json handling, and a tiny echo stage for tests.
5. Locks: src/mvh/runner/locks.py implements the heavy-slot protocol compatibly with scripts/heavy_lock.py (same files, same JSON). Provide
   mvh.testing.heavy() for tests. tests/conftest.py applies MVH_THREADS (default 3).
6. Models: mvh models fetch|verify|list over models.lock.json (28 entries, including the sep.* and ggml.* entries with their envs). This is the only
   downloader: temp file, SHA verify, os.replace under a per-file lock. Ignore audio-separator's download_checks.json. Port the logic from
   scripts/fetch_models.py. A ctx model-registry lookup gives stages explicit local paths.
7. Overrides: overrides.json plumbing into the keys of stages that declare override keys; record applied overrides in provenance.
   meaning/intent.md and meaning/authored.json are inputs, never overwritten or deleted.
8. io/ffmpeg.py: resolve MVH_FFMPEG, then %LOCALAPPDATA%\\mvh\\config.json (read with utf-8-sig), then PATH; put that bin first on PATH for children.
   io/audio.py: decode anything to float32 arrays with ffmpeg only (-map 0:a:0), never torchaudio.load or soundfile on originals.
9. The real ingest stage per PLAN §5 ingest and the contract: canonical audio/mix.flac (+ mix.wav twin when |x|>1, D23), preview.opus, artwork,
   source metadata. A truncated corrupt frame (Versatile.flac loses its last 2291 samples) is a warning, not an error. 48 kHz input stays 48 kHz in mix.flac.
10. CLI (mvh): analyze (--profile draft|max, --only, --force, --from), status, validate (schema-validate a folder; also run after every stage),
    doctor (§3.3 list: ffmpeg flags, env lock sync, ROCm health in sep-rocm, Vulkan whisper, Rhubarb, model SHA-256s, free disk), models.
    Module CLI verbs are discovered from optional src/mvh/stages/<name>/cli.py files, so later modules can add view, brief and frames without touching cli.py.
    The CLI reconfigures stdout to UTF-8 and works with PYTHONUTF8 and PYTHONIOENCODING removed.
11. scripts/gate.ps1 <W1b|module|all>: regenerate tests/contract/synth/ if its .done.json is missing (the fixtures builder provides the generator command
    in docs/build/reports/fixtures.md; look for it, and call it only if it exists), then run the unit tests for the target, every tests/review/** test for the
    target, ruff, python -m mvh.contract.gen --check, mvh validate on tests/contract/synth, an end-to-end mvh analyze of the walking skeleton
    (all stubs copy from the fixture) into a temp folder, the node lib tests (tests/unit/lib) and the determinism diff (analyze twice with --force and diff).
    Exit non-zero on any failure, with a short summary table.
12. Tests for all of the above, including a real CLI run on a file named "tëst ♪ 曲.flac" in a folder whose name contains spaces (make it from a synthetic tone).
The fixtures builder is creating tests/contract/synth/ at the same time. Until it exists, test the walking skeleton with your own tiny temporary fixture
(MVH_FIXTURE_DIR). If tests/contract/synth/.done.json appears before you finish, also run the full walking skeleton on it.`

const LIB = COMMON + `
YOUR NAME: lib. You build the agent-facing HELPER LIBRARIES (PLAN §4.5, CONTRACT.md helper signature table and golden spec).
OWNED PATHS: src/mvh/assets/mvh.js, src/mvh/assets/mvh.d.ts, src/mvh/assets/mvh_load.py, src/mvh/assets/mvh.glsl, src/mvh/assets/golden/**,
docs/contract/golden-addendum.md, tests/unit/lib/**, docs/build/progress/lib.md, docs/build/reports/lib.md.

BUILD:
1. lib/mvh.js: an ES module with no dependencies that works in browsers, Node (loadSync and fs paths) and Remotion (synchronous after load).
   Implement every row of the helper table exactly as CONTRACT.md specifies (it fixes the semantics PLAN leaves open, e.g. D9/D10, D11, D12-D14, D16, D28):
   load/loadSync/ensure, curve(id).at/.frame, events(name).at/next/prev/between/inFrame (with minTier), frameOf/timeOf/frameCount with rational fps,
   frame0 and early, pulse and osc, beatPos/beatPhase/barPhase, count, lyricAt/vocalAt/singerAt, meaningAt, spectrumAt/spectrumWindow, textureData
   (wrapped layout), and vizState. Helpers never return NaN.
2. mvh.d.ts: TypeScript declarations for every export (video agents using Remotion or three.js rely on these).
3. lib/mvh_load.py: the same API in snake_case with numpy only, matching src/mvh/contract/conventions.py (the reference implementation).
4. lib/mvh.glsl: mvhCurve(sampler2D, t) for the wrapped r32f texture with manual interpolation; test its index math in JS against curve.at.
5. vizState: port the field names, shapes and decay constants of C:\\Users\\OpenSrcerer\\Desktop\\playground\\viz\\js\\audio.js (bass, mid, high, level,
   kick, kickRaw, midHit, highHit, beat, beatPulse, onset, ..., bandBytes) so the viz/ scenes can run offline unchanged. Record the constants and any
   golden cases you add in docs/contract/golden-addendum.md and src/mvh/assets/golden/.
6. Tests: both libraries pass every case in docs/contract/golden-vectors.json; JS vs Python parity within 1e-6 at 23.976, 24, 25, 29.97, 30 and
   60 fps, frame0 0 and 1, all four policies. JS tests run with node --test tests/unit/lib/; Python tests with pytest.
   The fixtures builder is creating tests/contract/synth/ (a complete song folder) at the same time. If tests/contract/synth/.done.json exists before
   you finish, add a parity test that loads it with both libraries and compares every helper on a time grid; otherwise build a small folder in a
   test temp dir with mvh.contract.curvefile and mvh.contract.events and run the same parity checks there.`

const FIXTURES = COMMON + `
YOUR NAME: fixtures. You build the TEST FIXTURES that 8 module builders will code against next (PLAN §7.1, §12 W1b "fixtures", CONTRACT.md
catalogue and src/mvh/contract/fixture.py, which defines how stubs copy from the fixture). This is ground truth for the whole project: be exact.
OWNED PATHS: tests/synth/**, tests/contract/synth/** (generated, gitignored), tests/contract/real-*/** (generated, gitignored),
tests/contract/README.md, tests/unit/fixtures/**, docs/build/progress/fixtures.md, docs/build/reports/fixtures.md.

BUILD:
1. tests/synth/ primitives (deterministic, seeded): click tracks (tempo ramp, swing), EBU loudness test signals, sweeps, MIDI rendered with simple
   synths, vibrato "sung" sines, two Windows SAPI TTS voices (David and Zira; recipe in scripts/smoke/make_clips.ps1; read .txt as utf-8-sig), and the edge
   cases (mono, 48 kHz, MP3 with encoder delay, a corrupt FLAC, 10 s and 10 min files). Large files are generated on demand into tests/.cache/synth/.
2. THE SYNTHETIC SONG (45-60 s, 44.1 kHz stereo): a drum loop with programmed swing and syncopation (kick, snare, toms, hihat, ride, crash as
   separate one-shots), bass, a chord pad, a TTS vocal line with invented lyrics, a build into a drop, a silence, one 3/4 bar and a pickup,
   and two singers (a duet and a call-and-response). Its stems are the generator tracks and must sum to the mix.
3. tests/contract/synth/: the complete song folder generated FROM THE GENERATOR'S GROUND TRUTH. It holds EVERY output that every stage
   declares in the catalogue (src/mvh/contract/catalog.py), including _intermediate/<stage>/ for non-public outputs, so that every stub copies
   successfully and mvh analyze runs end to end. Beats, bars, counts, sections, phrases, notes, chords, key, drum hits, loudness, lyrics words and lines,
   voices and singers, visemes, drops and builds come from the ground truth. Fields with no physical truth (mood, instrument probabilities, CLAP terms,
   meaning) get plausible, internally consistent values marked as synthetic in provenance. Include an example meaning/intent.md and authored.json.
   All IDs must link (sections ↔ phrases ↔ bars ↔ counts ↔ lines ↔ voices ↔ characters ↔ cues). Every file must validate against its schema
   (src/mvh/contract/schemas.py) and use the contract readers and writers (curvefile.py, events.py).
   Write a ground-truth sidecar (e.g. tests/contract/synth/_truth/) that tests can score against, and finish by writing .done.json.
4. One generator command regenerates everything deterministically (byte-identical on rerun); document it at the top of your report and in
   tests/contract/README.md. The gate script calls it when .done.json is missing.
5. tests/contract/real-<slug>/ for megafauna, versatile, jeremy and newton-vs-nye: thin adapters that convert the raw W0 outputs in tests/.cache/real/
   (see index.music.json, index.words.json and each sep/index.json) into contract-layout files for the stages that have real data. Write an index of
   which stages each real folder covers. Lyric text stays only in these gitignored folders and is never printed.
6. tests/unit/fixtures/: tests that the synthetic folder validates, IDs link, stems sum to the mix, the truth matches the audio (e.g. click onsets),
   regeneration is deterministic, and a stub run of every stage succeeds against it.`

const REVIEW_SCHEMA = {
  type: 'object',
  properties: {
    reviewer: { type: 'string' },
    verdict: { type: 'string', enum: ['pass', 'pass-with-fixes', 'fail'] },
    summary: { type: 'string' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          severity: { type: 'string', enum: ['blocker', 'major', 'minor'] },
          location: { type: 'string' },
          claim: { type: 'string' },
          evidence: { type: 'string' },
          suggested_fix: { type: 'string' },
          test_path: { type: 'string', description: 'failing test written for this finding (blockers and majors)' },
        },
        required: ['severity', 'location', 'claim', 'evidence'],
      },
    },
  },
  required: ['reviewer', 'verdict', 'summary', 'findings'],
}

const REVIEW_COMMON = COMMON + `
You are an INDEPENDENT REVIEWER (PLAN §11). Three builders (runtime, lib, fixtures) just built the W1b foundation. You get the code and the spec, not
the builders' conclusions: do not read docs/build/reports/ until you have formed your own findings, and then only to locate things.
A finding is {severity: blocker|major|minor, location, claim, evidence, suggested_fix}. For EVERY blocker or major, write the evidence as a FAILING
pytest (or node --test) under your owned test folder, and verify that it fails now for the stated reason. Do not fix production code.
Minor findings go only in your review file. Be concrete and verify each claim by running code. Do not pad with style nits.
`

const R_CONTRACT = REVIEW_COMMON + `
YOUR NAME: r-contract. LENS: "the video agent" (PLAN §11 R-CONTRACT). Act as a Remotion, three.js, Blender or ComfyUI agent building a choreographed,
character-driven video from one output folder. Check that what it needs is present, unambiguous, cheap to load and safe for context, including choreo
and cue semantics.
OWNED PATHS: tests/review/w1b/contract/**, docs/review/w1b-r-contract.md, out/_wip/r-contract/**, docs/build/progress/r-contract.md.
CHECK AT LEAST:
- Run the walking skeleton (mvh analyze on the synthetic fixture into out/_wip/r-contract/) and open the result as a video agent would: manifest, curves
  index, events, lib/mvh.js (in Node) and mvh_load.py. Do the helpers in the copied lib/ work against the real folder? Do mvh.d.ts types match behaviour?
- Golden vectors and JS/Python parity: try cases the golden set misses (fps edge cases, frame0=1, early mode, events at exact boundaries, pickup bar,
  no-pulse regions, NaN pitch, singerAt with overlapping voices, textureData wrap edges, vizState vs viz/js/audio.js field names).
- The synthetic fixture: is it a faithful, internally consistent ground truth (IDs link, counts and bars agree with beats, lyrics words inside lines,
  singers map to voices and characters, cues cite real ids)? Could a module builder test real behaviour against it, not just copy it?
- Is anything an agent needs for choreography or characters missing, ambiguous or too expensive to load?`

const R_PLATFORM = REVIEW_COMMON + `
YOUR NAME: r-platform. LENS: Windows platform (PLAN §11 R-PLATFORM): paths and Unicode, subprocesses, the ffmpeg resolver, env and lock hygiene,
the sep worker, locks, determinism, cache keys, supply chain.
OWNED PATHS: tests/review/w1b/platform/**, docs/review/w1b-r-platform.md, out/_wip/r-platform/**, docs/build/progress/r-platform.md.
CHECK AT LEAST:
- mvh CLI with PYTHONUTF8 and PYTHONIOENCODING removed, on "tëst ♪ 曲.flac" in a folder with spaces; a 48 kHz file; an MP3; Versatile.flac
  (C:\\Users\\OpenSrcerer\\Desktop\\playground\\viz\\Versatile.flac, corrupt last frame).
- Cache keys (NF2): does changing a param, an override, a model SHA, MVH_THREADS or the env lock invalidate exactly the right stages? Does mvh status
  explain it? Are writes atomic and safe under PermissionError? Is determinism (analyze twice with --force) real?
- The sep worker: Job Object kill-on-close (kill the parent mid-job and check no orphan python.exe or ffmpeg remains), PYTHONPATH, ffmpeg on PATH,
  rocm/cpu variant selection and fallback, worker imports only stdlib+numpy at module level. Use the echo stage, not a real separation.
- Locks: compatible with scripts/heavy_lock.py, stale detection, two slots, gpu lock ordering.
- mvh models verify/fetch: offline behaviour, SHA mismatch handling, never downloading outside mvh models fetch.
- mvh doctor output is truthful. scripts/gate.ps1 W1b actually fails when something fails.`

const FIXER = COMMON + `
YOUR NAME: w1b-fixer. Two reviewers wrote failing tests under tests/review/w1b/** and review files docs/review/w1b-r-contract.md and
docs/review/w1b-r-platform.md. Their blocker and major findings are below.
OWNED PATHS: everything the three W1b builders owned (src/mvh/cli.py, worker.py, testing.py, runner/**, io/**, stages/__init__.py, stages/ingest/**,
src/mvh/assets/**, scripts/gate.ps1, scripts/fetch_models.py, tests/conftest.py, tests/unit/**, tests/synth/**, tests/contract/**,
docs/contract/golden-addendum.md, appending decisions to docs/CONTRACT.md), plus docs/build/progress/w1b-fixer.md and docs/build/reports/w1b-fixer.md.
Do NOT edit tests/review/**. If a review test is demonstrably wrong, leave it failing and explain why in your report under open_issues.
GOAL: every tests/review/w1b/** test passes, the earlier unit tests still pass, and scripts/gate.ps1 W1b exits 0. One round: fix, run the gate, report.
Also fix minor findings when the fix is cheap and safe.
FINDINGS:
`

phase('Build')
const builders = await parallel([
  () => agent(RUNTIME, { label: 'runtime', phase: 'Build', schema: RESULT }),
  () => agent(LIB, { label: 'lib', phase: 'Build', schema: RESULT }),
  () => agent(FIXTURES, { label: 'fixtures', phase: 'Build', schema: RESULT }),
])
const [runtime, lib, fixtures] = builders
if (!runtime || !lib || !fixtures) log('A builder returned null; reviewers will still run on what exists')

phase('Review')
const reviews = await parallel([
  () => agent(R_CONTRACT, { label: 'r-contract', phase: 'Review', schema: REVIEW_SCHEMA }),
  () => agent(R_PLATFORM, { label: 'r-platform', phase: 'Review', schema: REVIEW_SCHEMA }),
])
const serious = reviews.filter(Boolean).flatMap(r => r.findings.filter(f => f.severity !== 'minor').map(f => ({ reviewer: r.reviewer, ...f })))
log(`${serious.length} blocker/major findings`)

let fixer = null
if (serious.length) {
  phase('Fix')
  fixer = await agent(FIXER + JSON.stringify(serious, null, 1), { label: 'w1b-fixer', phase: 'Fix', schema: RESULT, model: 'sonnet' })
}
return { runtime, lib, fixtures, reviews, fixer }
