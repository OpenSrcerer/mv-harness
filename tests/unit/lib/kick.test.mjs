// D79 (user decision UD2): song.kickSource / song.kicks() / events('kick') / pulse('kick') in lib/mvh.js; the Python twin is
// tests/unit/lib/test_lib_kick.py.  Run: node --test tests/unit/lib/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import * as mvh from '../../../src/mvh/assets/mvh.js';

const DRUM_HITS = [{ t: 0.5, drum: 'kick', vel: 0.9, conf: 0.8 }, { t: 0.5, drum: 'hat', vel: 0.4, conf: 0.9 },
  { t: 1.0, drum: 'kick', vel: 0.7, conf: 1.0 }, { t: 1.25, drum: 'snare', vel: 0.7, conf: 1.0 }];
const HITS_KICK = [{ t: 0.502, strength: 1.4, env: 0.95, kick_conf: 0.9 }, { t: 1.26, strength: 0.4, env: 0.3 }];

function song(kickSource, files = ['drum_hits', 'hits.kick']) {
  const dir = mkdtempSync(path.join(os.tmpdir(), 'mvh-kick-'));
  mkdirSync(path.join(dir, 'events'));
  const man = { schema: 'mvh/manifest', source: { duration_s: 2 }, summary: { duration_s: 2 },
    files: files.map((n) => ({ path: `events/${n}.json`, kind: 'events', stage: 'x' })) };
  if (kickSource) man.summary.kick_source = kickSource;
  writeFileSync(path.join(dir, 'manifest.json'), JSON.stringify(man), 'utf8');
  for (const [n, items] of [['drum_hits', DRUM_HITS], ['hits.kick', HITS_KICK]]) {
    if (files.includes(n)) writeFileSync(path.join(dir, 'events', `${n}.json`), JSON.stringify({ kind: 'event', items }), 'utf8');
  }
  return dir;
}

for (const [ks, expect] of [['drums', [0.5, 1.0]], ['mix', [0.502, 1.26]]]) {
  test(`kicks follow the manifest kick_source = ${ks}`, () => {
    const s = mvh.loadSync(song(ks));
    assert.equal(s.kickSource, ks);
    const k = s.kicks();
    assert.deepEqual(k.items.map((it) => it.t), expect);
    assert.ok(k.items.every((it) => it.source === ks));
    assert.equal(s.events('kick'), k);
    assert.ok(k.exists);
    assert.equal(k.name, 'kick');
    assert.deepEqual(s.resolve('kick'), [`events:${ks === 'drums' ? 'drum_hits' : 'hits.kick'}`]);
    assert.ok(Math.abs(s.pulse('kick', expect[0]) - k.items[0].vel) < 1e-12);
    assert.equal(k.next(0.6).t, expect[1]);
  });
}

test('kick source is inferred for older folders', () => {
  assert.equal(mvh.loadSync(song(null)).kickSource, 'drums');
  const s = mvh.loadSync(song(null, ['hits.kick']));
  assert.equal(s.kickSource, 'mix');
  assert.deepEqual(s.kicks().items.map((it) => it.t), [0.502, 1.26]);
  const e = mvh.loadSync(song('drums', [])).kicks();
  assert.equal(e.exists, false);
  assert.deepEqual(e.items, []);
});

test('browser-style load: ensure("kick") loads just the chosen file', async () => {
  const dir = song('mix');
  const read = [];
  const fetchFn = async (url) => {
    const rel = url.replace('mem://song/', '');
    read.push(rel);
    const { readFileSync } = await import('node:fs');
    try { return new Response(readFileSync(path.join(dir, ...rel.split('/')))); } catch { return new Response('', { status: 404 }); }
  };
  const s = await mvh.load('mem://song/', { fetch: fetchFn });
  await s.ensure('kick');
  assert.ok(read.includes('events/hits.kick.json') && !read.includes('events/drum_hits.json'), read.join(','));
  assert.deepEqual(s.kicks().items.map((it) => it.t), [0.502, 1.26]);
});
