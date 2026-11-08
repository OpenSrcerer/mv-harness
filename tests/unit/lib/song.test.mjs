// Song-level behaviour of lib/mvh.js: loadSync, async load from a path, load from URLs with a custom fetch (lazy
// resources must be ensured first, as in Remotion), missing files, textures and vizState.  Run: node --test tests/unit/lib/
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import * as mvh from '../../../src/mvh/assets/mvh.js';

let DIR;
const DUR = 4.0;
const N = 400;

function writeJson(rel, obj) {
  const p = path.join(DIR, ...rel.split('/'));
  mkdirSync(path.dirname(p), { recursive: true });
  writeFileSync(p, JSON.stringify(obj), 'utf8');
}

/** A minimal song folder in the contract layout (column-major f32, row-major u8, event envelopes). */
function buildSong() {
  DIR = mkdtempSync(path.join(os.tmpdir(), 'mvh-lib-'));
  const chans = {
    'hits.kick': Array.from({ length: N }, (_, i) => (i % 50 === 10 || i % 50 === 11 ? 1.2 : Math.max(0, 1 - (i % 50) / 20) * 0.3)),
    'bands.bass_viz': Array.from({ length: N }, (_, i) => 0.5 + 0.4 * Math.sin(i / 30)),
    'tempo.bpm': Array.from({ length: N }, () => 120),
    'rhythm.in_pulse': Array.from({ length: N }, (_, i) => (i < 200 ? 1 : 0)),
  };
  const meta = { 'hits.kick': ['max', null], 'bands.bass_viz': ['mean', null], 'tempo.bpm': ['linear', null], 'rhythm.in_pulse': ['hold', null] };
  const vocal = { 'vocal.midi': Array.from({ length: N }, (_, i) => (i >= 100 && i < 150 ? NaN : 60 + i / 100)) };
  const files = {}, channels = [];
  const pack = (fid, rel, map, rate) => {
    const ids = Object.keys(map);
    const n = map[ids[0]].length;
    const buf = new Float32Array(n * ids.length);
    ids.forEach((id, j) => {
      buf.set(map[id], j * n);
      const m = meta[id] || ['linear', { nan: 'unvoiced' }];
      channels.push({ id, file: fid, offset_bytes: 4 * n * j, n, rate_hz: rate, unit: 'x', range: [0, 1], norm: null, resample: m[0],
        special: m[1], twin: null, stage: 'test', description: '' });
    });
    mkdirSync(path.join(DIR, 'curves'), { recursive: true });
    writeFileSync(path.join(DIR, ...rel.split('/')), Buffer.from(buf.buffer));
    files[fid] = { path: rel, dtype: 'f32le', layout: 'column-major', rate_hz: rate, n_frames: n, n_channels: ids.length };
  };
  pack('core', 'curves/core.f32', chans, 100);
  pack('vocal', 'curves/vocal.f32', vocal, 100);
  const spec = new Uint8Array(N * 128).map((_, k) => (Math.floor(k / 128) + (k % 128)) % 256);
  writeFileSync(path.join(DIR, 'curves', 'spectrum128.u8'), spec);
  files.spectrum128 = { path: 'curves/spectrum128.u8', dtype: 'u8', layout: 'row-major', rate_hz: 100, n_frames: N, n_channels: 128,
    quant: { scale: 1 / 255, offset: 0 } };
  channels.push({ id: 'spectrum128', file: 'spectrum128', offset_bytes: 0, n: N, rate_hz: 100, resample: 'hold' });
  writeJson('curves/index.json', { schema: 'mvh/curves_index', schema_version: '1.0.0-rc.1', files, channels });
  const ev = (name, kind, items) => writeJson(`events/${name}.json`, { schema: `mvh/events/${name}`, name, kind, fields: {}, provenance: {}, items });
  ev('beats', 'event', Array.from({ length: 8 }, (_, i) => ({ beat_index: i, t: 0.25 + 0.5 * i, bar: Math.floor(i / 4) + 1,
    beat_in_bar: (i % 4) + 1, beats_in_bar: 4, in_pulse: true })));
  ev('onsets.bass', 'event', [{ t: 0.1, strength: 1 }, { t: 0.6, strength: 0.5 }, { t: 1.1 }]);
  ev('onsets.mid', 'event', [{ t: 0.3, strength: 0 }]);
  ev('sections', 'segment', [{ id: 'S02', t: 2, d: 2 }, { id: 'S01', t: 0, d: 2 }]);   // unsorted on purpose
  writeJson('manifest.json', { schema: 'mvh/manifest', slug: 't', source: { duration_s: DUR },
    files: ['beats', 'onsets.bass', 'onsets.mid', 'sections'].map((n) => ({ path: `events/${n}.json`, kind: 'events', stage: 't', events: n })) });
}

before(buildSong);
after(() => rmSync(DIR, { recursive: true, force: true }));

test('loadSync: curves, policies, events sorted, missing files are empty', () => {
  const s = mvh.loadSync(DIR);
  assert.equal(s.duration, DUR);
  assert.equal(s.frameCount({ fps: 24 }), 96);
  assert.equal(s.curve('hits.kick').frame(mvh.frameOf(0.105, { fps: 24 }), { fps: 24 }), Math.fround(1.2));
  assert.equal(s.curve('rhythm.in_pulse').at(1.994), 1);
  assert.equal(s.curve('rhythm.in_pulse').at(1.996), 0);
  assert.equal(s.curve('vocal.midi').at(1.2), Math.fround(60.99));       // held through the unvoiced gap
  assert.deepEqual(s.events('sections').items.map((x) => x.id), ['S01', 'S02']);
  assert.equal(s.events('sections').at(2.5).item.id, 'S02');
  const missing = s.events('counts');
  assert.equal(missing.exists, false);
  assert.equal(missing.at(1), null);
  assert.deepEqual(s.count(1.0), { eight_id: null, count: null, sub: 2, phase: null, accent: 0, partial: false, lead_in: false, in_pulse: true });
  assert.deepEqual(s.lyricAt(1), { line: null, word: null, progress: null, word_progress: null });
  assert.deepEqual(s.singerAt(1), []);
  assert.equal(s.meaningAt(1).section_id, 'S01');
  assert.deepEqual(s.meaningAt(1).do_not, []);
  assert.throws(() => s.curve('no.such'), /unknown curve channel/);
  assert.throws(() => s.curve('spectrum128'), /spectrumAt/);
  assert.throws(() => s.curve('hits.kick').at(NaN), /finite/);
});

test('helpers never return NaN on a dense grid', () => {
  const s = mvh.loadSync(DIR);
  const finite = (x, where) => {
    if (typeof x === 'number') assert.ok(Number.isFinite(x), where);
    else if (x && typeof x === 'object') for (const [k, v] of Object.entries(x)) finite(v, `${where}.${k}`);
  };
  for (let t = -1; t < DUR + 1; t += 0.0371) {
    for (const id of s.channelIds.filter((c) => c !== 'spectrum128')) finite(s.curve(id).at(t), `${id}@${t}`);
    finite(s.vocalAt(t), `vocalAt@${t}`);
    finite(s.beatPos(t), 'beatPos'); finite(s.barPhase(t), 'barPhase'); finite(s.count(t), 'count');
    finite(s.pulse('onsets.bass', t), 'pulse'); finite(s.osc(t, { shape: 'triangle' }), 'osc');
    finite(s.vizState(t, { fps: 30 }), `vizState@${t}`);
  }
});

test('async load from a path with include; ensure accepts helper names', async () => {
  const s = await mvh.load(DIR, { include: ['helper:vizState', 'helper:count'] });
  assert.ok(s.isLoaded('helper:vizState'));
  assert.ok(s.isLoaded('events:counts'));          // a missing file is "loaded" as empty
  assert.equal(s.events('counts').exists, false);
  assert.ok(s.resolve('bands.bass_viz').includes('curves:core'));
  assert.deepEqual(s.resolve('helper:viz_state'), mvh.HELPER_NEEDS.vizState);
});

function fakeFetch(log) {
  return async (url) => {
    log.push(url);
    const rel = decodeURIComponent(new URL(url).pathname.replace(/^\/song\//, ''));
    let body;
    try { body = readFileSync(path.join(DIR, ...rel.split('/'))); } catch { return { ok: false, status: 404 }; }
    return { ok: true, status: 200, text: async () => body.toString('utf8'),
      arrayBuffer: async () => body.buffer.slice(body.byteOffset, body.byteOffset + body.byteLength) };
  };
}

test('URL mode (browser / Remotion): lazy parts must be ensured, then everything is synchronous', async () => {
  const log = [];
  const s = await mvh.load('https://example.test/song', { fetch: fakeFetch(log) });
  assert.deepEqual(log.map((u) => new URL(u).pathname).sort(), ['/song/curves/index.json', '/song/manifest.json']);
  assert.throws(() => s.curve('hits.kick'), /not loaded; call await song.ensure\('curves:core'\)/);
  assert.throws(() => s.beatPos(1), /ensure\('events:beats'\)/);
  await s.ensure(['hits.kick', 'helper:beatPos', 'helper:lyricAt']);
  assert.equal(s.curve('hits.kick').at(0.1), Math.fround(1.2));
  assert.equal(s.beatPos(0.25).value, 0);
  assert.deepEqual(s.lyricAt(1).line, null);                // 404 -> missing -> empty, no throw
  const n = log.length;
  await s.ensure('curves:core');                            // already loaded: no new request
  assert.equal(log.length, n);
});

test('textureData: wrap layout info, r32f and r8', () => {
  const s = mvh.loadSync(DIR);
  const td = s.textureData(['hits.kick', 'vocal.midi'], { width: 128 });
  assert.equal(td.width, 128);
  assert.equal(td.height, 8);
  assert.deepEqual(td.layout.map((l) => l.info), [[100, 400, 128, 0], [100, 400, 128, 4]]);
  assert.ok(td.data instanceof Float32Array);
  assert.ok(td.data.every((x) => Number.isFinite(x)));      // NaN-aware channel filled with held values
  const k = 4 * 128 + 120;                                  // vocal.midi sample 120 (unvoiced) holds sample 99
  assert.equal(td.data[k], Math.fround(60.99));
  const r8 = s.textureData('bands.bass_viz', { format: 'r8' });
  assert.ok(r8.data instanceof Uint8Array);
  assert.equal(r8.data[0], Math.round(Math.fround(0.5) * 255));
  assert.throws(() => s.textureData('hits.kick', { layout: 'strip' }), /layout/);
});

test('spectrumAt / spectrumWindow: nearest row, oldest first, zero rows outside', () => {
  const s = mvh.loadSync(DIR);
  const row = s.spectrumAt(0.123);
  assert.equal(row.length, 128);
  assert.equal(row[5], 12 + 5);
  assert.equal(s.spectrumAt(-5)[0], 0);
  assert.equal(s.spectrumAt(99)[0], 399 % 256);
  const w = s.spectrumWindow(0.01, 0.03);                   // rows -2, -1, 0, 1
  assert.equal(w.length, 4 * 128);
  assert.equal(w[0], 0);
  assert.equal(w[2 * 128 + 3], 3);
  assert.equal(w[3 * 128 + 3], 4);
});

test('vizState: viz field names and shapes, onset frame, pulse decay, recentBeats', () => {
  const s = mvh.loadSync(DIR);
  const fr = { fps: 60 };
  const st = s.vizState(0.6, fr);
  for (const k of ['bands', 'bandsRaw', 'peaks']) assert.ok(st[k] instanceof Float32Array && st[k].length === 128, k);
  assert.ok(st.bandBytes instanceof Uint8Array && st.bandBytes.length === 512);
  assert.ok(st.waveBytes.every((b) => b === 128) && st.waveBytes.length === 512 && st.wave.length === 512);
  assert.equal(st.bandBytes[3], 255);
  assert.equal(st.bandBytes[0], st.bandBytes[1]);
  assert.equal(st.onset, true);
  assert.equal(st.beatCount, 2);
  assert.equal(st.beatPulse, 1);                            // the onset frame reads a full pulse
  assert.ok(Math.abs(st.beat - Math.max(0.55 + 0.45 * 0.5, 1 * Math.exp(-0.5 / 0.3))) < 1e-12);
  assert.deepEqual(Array.from(st.recentBeats.slice(0, 6)), [-100, -100, -100, -100, -100, -100]);
  assert.deepEqual(Array.from(st.recentBeats.slice(6)), [Math.fround(0.1), Math.fround(0.6)]);
  const later = s.vizState(0.71, fr);
  assert.equal(later.onset, false);
  assert.ok(Math.abs(later.beatPulse - Math.exp(-(mvh.frameCentre(mvh.frameOf(0.71, fr), fr) - 0.6) / 0.11)) < 1e-12);
  assert.equal(st.midOnset, false);
  assert.ok(Math.abs(st.midPulse - 0.6 * Math.exp(-(st.t - 0.3) / 0.11)) < 1e-12);  // strength 0 -> 0.6
  assert.equal(st.bpm, 120);
  assert.equal(typeof st.bandLow(0.5), 'number');
  assert.deepEqual(st.ranges.bass, [0, 32]);
  assert.ok(st.peaks.every((p, k) => p >= st.bands[k]));
});

test('frame rules: rational fps, frame0, validation', () => {
  assert.equal(mvh.timeOf(25, { fps: [24000, 1001], frame0: 1 }), 1.001);
  assert.equal(mvh.frameOf(1.0, { fps: 23.976, early: true }), 23);
  assert.equal(mvh.frameOf(1.0, 24), 24);
  assert.equal(mvh.frameOf(1.0, [24000, 1001]), 24);
  assert.throws(() => mvh.frameOf(1, { fps: 0 }), /positive/);
  assert.throws(() => mvh.frameOf(1, { fps: 24, frame0: 0.5 }), /integer/);
  assert.throws(() => mvh.frameOf(1), /frame rule/);
});
