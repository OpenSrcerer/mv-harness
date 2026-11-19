// song.soundtrack, song.meaning and song.linesAt(t) (karaoke with overlapping lines) in lib/mvh.js; the Python twin is
// tests/unit/lib/test_lib_lines.py.  Run: node --test tests/unit/lib/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import * as mvh from '../../../src/mvh/assets/mvh.js';

export const LINES = [
  { id: 'L001', t: 1.0, d: 2.0, text: 'a b', grade: 'A' },
  { id: 'L002', t: 2.5, d: 1.5, text: 'c d', grade: 'D' },      // overlaps L001 from 2.5 to 3.0 (a second singer)
];
export const WORDS = [
  { id: 'L001.01', line_id: 'L001', t: 1.0, d: 0.5, text: 'a', conf: 0.9 },
  { id: 'L001.02', line_id: 'L001', t: 2.0, d: 0.9, text: 'b', conf: 0.9 },
  { id: 'L002.01', line_id: 'L002', t: 2.5, d: 0.4, text: 'c', conf: 0.3 },
  { id: 'L002.02', line_id: 'L002', t: 3.2, d: 0.5, text: 'd', conf: 0.3 },
];
export const SINGING = [
  { t: 1.0, d: 2.0, line_id: 'L001', voice_id: 'V1', character_id: 'C1', lead_backing: 'lead' },
  { t: 2.5, d: 1.5, line_id: 'L002', voice_id: 'V2', character_id: 'C2', lead_backing: 'lead' },
];

function folder(soundtrack) {
  const dir = mkdtempSync(path.join(os.tmpdir(), 'mvh-lines-'));
  for (const d of ['events', 'lyrics', 'meaning']) mkdirSync(path.join(dir, d));
  const man = { schema: 'mvh/manifest', source: { duration_s: 5 }, summary: { duration_s: 5 },
    files: [{ path: 'events/singing.json', kind: 'events', stage: 'x' }] };
  if (soundtrack) man.timebase = { soundtrack };
  writeFileSync(path.join(dir, 'manifest.json'), JSON.stringify(man), 'utf8');
  writeFileSync(path.join(dir, 'lyrics', 'lyrics.json'), JSON.stringify({ lines: LINES, words: WORDS }), 'utf8');
  writeFileSync(path.join(dir, 'events', 'singing.json'), JSON.stringify({ kind: 'segment', items: SINGING }), 'utf8');
  writeFileSync(path.join(dir, 'meaning', 'meaning.json'),
    JSON.stringify({ status: 'pending', characters: [{ id: 'C1', name: 'One' }, { id: 'C2', name: 'Two' }], do_not: [] }), 'utf8');
  return dir;
}

test('soundtrack follows the manifest timebase, mix.flac by default', () => {
  assert.equal(mvh.loadSync(folder('audio/mix.wav')).soundtrack, 'audio/mix.wav');
  assert.equal(mvh.loadSync(folder(null)).soundtrack, 'audio/mix.flac');
});

test('meaning is the parsed meaning.json', () => {
  const m = mvh.loadSync(folder(null)).meaning;
  assert.deepEqual(m.characters.map((c) => c.id), ['C1', 'C2']);
});

test('linesAt returns every line sounding at t, with all its words and its singers', () => {
  const s = mvh.loadSync(folder(null));
  assert.deepEqual(s.linesAt(0.5), []);
  const one = s.linesAt(1.2);
  assert.equal(one.length, 1);
  assert.equal(one[0].line.id, 'L001');
  assert.deepEqual(one[0].words.map((w) => w.id), ['L001.01', 'L001.02']);
  assert.equal(one[0].word.id, 'L001.01');
  assert.ok(Math.abs(one[0].progress - 0.1) < 1e-9);
  const both = s.linesAt(2.7);                                   // the overlap: lyricAt shows only the later line
  assert.deepEqual(both.map((x) => x.line.id), ['L001', 'L002']);
  assert.deepEqual(both.map((x) => x.line.singer), [['C1'], ['C2']]);
  assert.equal(s.lyricAt(2.7).line.id, 'L002');
  assert.equal(both[1].word.id, 'L002.01');
  assert.equal(both[0].word.id, 'L001.02');
  const gap = s.linesAt(3.05);                                   // inside L002, between its words
  assert.equal(gap.length, 1);
  assert.equal(gap[0].word, null);
  assert.equal(gap[0].word_progress, null);
});

test('helper:linesAt loads what linesAt needs', () => {
  assert.deepEqual(mvh.HELPER_NEEDS.linesAt, ['lyrics', 'events:singing']);
});
