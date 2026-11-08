// R-CONTRACT (W1b) failing tests for lib/mvh.js: the video-agent lens (PLAN §11).
//   node --test tests/review/w1b/contract/rcontract_video_agent.test.mjs
// Evidence for findings F1, F4 and F5 in docs/review/w1b-r-contract.md (the Python side is test_rcontract_video_agent.py).
// Reads the synthetic fixture tests/contract/synth (read-only). Prints ids, times and counts only, never lyric text.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '../../../..');
const SYNTH = path.join(REPO, 'tests', 'contract', 'synth');
const mvh = await import(pathToFileURL(path.join(REPO, 'src', 'mvh', 'assets', 'mvh.js')).href);
const song = mvh.loadSync(SYNTH);

test('F1: stepping through cues with next(t, {minTier: 1}) reaches every tier-1 cue', () => {
  const cues = song.events('cues');
  const want = cues.items.filter((c) => c.tier === 1).map((c) => c.id);
  const got = [];
  let t = -1;
  for (let c = cues.next(t, { minTier: 1 }); c !== null; c = cues.next(t, { minTier: 1 })) { got.push(c.id); t = c.t; }
  const missing = want.filter((id) => !got.includes(id)).map((id) => { const c = cues.byId(id); return `${id}@${c.t}:${c.kind}`; });
  assert.deepEqual(missing, [], `tier-1 cues unreachable by next()-iteration: ${missing.join(', ')}`);
});

test('F4: song.vizState(t) as documented never drops an onset frame at 30 fps', () => {
  const fr = { fps: 30 };
  let threw = null;
  try { song.vizState(1.0); } catch (e) { threw = e; }
  if (threw) { assert.match(String(threw.message), /fr|frame|fps/); return; }   // a mandatory frame rule is a valid fix
  const want = new Set(song.events('onsets.bass').items.map((it) => mvh.frameOf(it.t, fr)));
  const seen = new Set();
  for (let n = 0; n < song.frameCount(fr); n++) if (song.vizState(mvh.timeOf(n, fr)).onset) seen.add(n);
  const lost = [...want].filter((n) => !seen.has(n));
  assert.equal(lost.length, 0, `${lost.length} of ${want.size} bass-onset frames at 30 fps never report onset=true (first ${lost.slice(0, 5)})`);
});

test('F5: every segment containing t is queryable (duet visemes, chords)', () => {
  const vis = song.events('visemes');
  assert.equal(typeof vis.allAt, 'function', 'Events has no allAt(t): overlapping segments are unreachable');
  assert.deepEqual([...new Set(vis.allAt(17.3).map((it) => it.voice_id))].sort(), ['V1', 'V2']);
  assert.equal(song.events('notes.other').allAt(1.0).length, 3);
});
