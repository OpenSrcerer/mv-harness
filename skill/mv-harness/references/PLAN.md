# The video plan (write it before you build anything)

Nothing gets built, installed, generated or paid for until the user has read this plan and said yes. The plan is how
the user sees, before any work, what you think the video will look like and how you will make it. Write it to
`<project>/PLAN.md`, show the user a short summary (concept, look, tools, cost, open questions) and ask them to approve
it or change it. A change means a revised plan and a new question, not a build.

Base every claim on the song folder: cite section ids (`S04`), times, cue ids (`Q0017`), line ids (`L012`) and the
user's words. Mark each choice as **the user's** (`field_sources` = `user`, line notes, do-not rules), **a draft's**
(`draft`) or **your proposal**. Never present your proposal as the user's direction.

## 1. Concept

- The song in one line, in the user's words (`logline`), and what you take from `summary`, `themes`, `notes` and
  `line_notes`. If the meaning is `pending`, stop: the interview comes first (SKILL.md §3).
- Your interpretation: the idea that holds the video together, in two or three sentences.

## 2. Look

- Style (live action, 3D, 2D animation, generative imagery, abstract, collage ...), palette (the user's, else the
  cover-art placeholder, said so), light, texture, references.
- The do-not rules, verbatim, and how the plan respects each one.

## 3. Characters

One row per character (`song.meaning.characters`): who, look, which voice (`V2`), lead or backing, where they appear.
Say which descriptions are the user's and which are yours.

## 4. Storyboard

One row per section (or per group of repeated sections that share a look, `repeat_group`):

| Section | Time | The music here | What we see | Camera and cuts | Movement |
|---|---|---|---|---|---|

The music column comes from the data (energy, build/drop role, vocals, the mood heard); cuts come from tier 1-2 cues;
movement from counts, grooves and hit points. Sections carry no meaning of their own: their look follows the music
and the song's meaning. Lines with a user note get their own row or a remark in the section's row.

## 5. Hero moments and words

- The top moments (`events('moments')` by `rank`): what happens on screen at each.
- Words on screen or not; if so, how (karaoke, captions, the subtitle files) and how weak lines (grade C/D) are shown.

## 6. Tools and pipeline

Choose the tools that best make this look. The engines in RECIPES.md are examples, not a list: any renderer,
generative image or video model, 3D package, compositor, editor or library is fair game when it serves the plan better.

- For each tool: what it does in this pipeline, why it beats the alternatives here, and what it needs. **List every
  install, account, API key, licence and expected cost** (money, GPU time, hours of rendering): approving the plan
  approves exactly these; anything new later needs a new yes.
- The pipeline from the song folder to the final file: how the data reaches each tool (lib/mvh.js, lib/mvh_load.py,
  `mvh frames` CSV or Deforum schedules, `mvh pack`), how pieces are joined, and how the soundtrack
  (`song.soundtrack`) is muxed at the end.
- Output: resolution, aspect ratio, fps (the frame rule), length, format.

## 7. Work split: agents and models

Split the work into tasks that can run on their own and say who does each:

| Task | Agent | Model tier | Input | Output | Runs after |
|---|---|---|---|---|---|

- **Spawn other agents** for independent pieces (one per scene or section group, one per asset type, one for the
  pipeline and the final mux) and run them in parallel where nothing depends on another's result.
- **Match the model to the task**: the most capable model for the concept, art direction, integration and reviewing
  renders against the plan; a balanced model for writing scene and pipeline code; the fastest, cheapest model for
  mechanical work (converting files, batch renders, checking frame timing, renaming assets). Use the model choice your
  agent tooling offers (for example a per-agent model setting) and name the tier in the table.
- Every agent's brief carries: the song folder path, its sections and times, the frame rule, the soundtrack, the
  do-not rules verbatim, and the rule to load data through lib/ instead of reading files into context.
- One agent (you) integrates the pieces and checks them against the plan.

## 8. Risks and checks

- Shaky data from the status line flags (`singers:review`, lyrics grade C/D, `degraded:*`, `fallback:*`, `qa:*`) and
  how the plan works around each (coarser cues, no word wipe, a character confirmed by the user).
- How you will check the result: scrub the render against `mvh view`, frame-exact checks of cuts and kicks, lip-sync
  spot checks per singer.

## 9. Questions for the user

Everything you had to guess (fps, aspect ratio, budget, a character's look, a section the user may want directed).

Then stop and ask: **approve the plan, or say what to change.**
