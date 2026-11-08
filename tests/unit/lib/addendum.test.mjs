// Addendum golden cases (src/mvh/assets/golden/addendum-vectors.json) against lib/mvh.js: vizState, the lyricAt singer
// join, the meaningAt merge, the texture NaN fill and spectrumWindow bytes.  Run: node --test tests/unit/lib/
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import os from 'node:os';
import path from 'node:path';
import * as mvh from '../../../src/mvh/assets/mvh.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '..', '..', '..');
const A = JSON.parse(readFileSync(path.join(REPO, 'src', 'mvh', 'assets', 'golden', 'addendum-vectors.json'), 'utf8'));
const TOL = A.tolerance;
let DIR, song;

function close(actual, expected, where = '$') {
  if (expected === null) { assert.ok(actual === null || actual === undefined, `${where}: expected null, got ${JSON.stringify(actual)}`); return; }
  if (typeof expected === 'number') {
    assert.equal(typeof actual, 'number', `${where}: ${JSON.stringify(actual)}`);
    assert.ok(Math.abs(actual - expected) <= TOL * (1 + 1e-9) + 1e-12, `${where}: ${actual} != ${expected}`);
    return;
  }
  if (typeof expected !== 'object') { assert.equal(actual, expected, where); return; }
  if (Array.isArray(expected)) {
    assert.equal(actual.length, expected.length, `${where}: length`);
    expected.forEach((e, i) => close(actual[i], e, `${where}[${i}]`));
    return;
  }
  for (const k of Object.keys(expected)) { assert.ok(k in actual, `${where}: missing ${k}`); close(actual[k], expected[k], `${where}.${k}`); }
}

function writeSong(inp) {
  DIR = mkdtempSync(path.join(os.tmpdir(), 'mvh-add-'));
  const put = (rel, data) => {
    const p = path.join(DIR, ...rel.split('/'));
    mkdirSync(path.dirname(p), { recursive: true });
    writeFileSync(p, data);
  };
  const files = {}, channels = [];
  for (const fid of ['core', 'vocal']) {
    const ids = Object.keys(inp.channels).filter((c) => inp.file[c] === fid);
    const n = inp.channels[ids[0]].length;
    const buf = new Float32Array(n * ids.length);
    ids.forEach((id, j) => {
      buf.set(inp.channels[id].map((x) => (x === null ? NaN : x)), j * n);
      channels.push({ id, file: fid, offset_bytes: 4 * n * j, n, rate_hz: 100, resample: inp.policy[id],
        special: id === 'vocal.midi' || id === 'vocal.f0_hz' ? { nan: 'unvoiced' } : null });
    });
    put(`curves/${fid}.f32`, Buffer.from(buf.buffer));
    files[fid] = { path: `curves/${fid}.f32`, dtype: 'f32le', layout: 'column-major', rate_hz: 100, n_frames: n, n_channels: ids.length };
  }
  put('curves/spectrum128.u8', Uint8Array.from(inp.spectrum.flat()));
  files.spectrum128 = { path: 'curves/spectrum128.u8', dtype: 'u8', layout: 'row-major', rate_hz: 100, n_frames: inp.spectrum.length, n_channels: 128 };
  channels.push({ id: 'spectrum128', file: 'spectrum128', offset_bytes: 0, n: inp.spectrum.length, rate_hz: 100, resample: 'hold' });
  put('curves/index.json', JSON.stringify({ files, channels }));
  for (const [name, items] of Object.entries(inp.events)) put(`events/${name}.json`, JSON.stringify({ name, kind: 'event', items }));
  put('lyrics/lyrics.json', JSON.stringify(inp.lyrics));
  put('meaning/meaning.json', JSON.stringify(inp.meaning));
  put('manifest.json', JSON.stringify({ source: { duration_s: inp.duration_s },
    files: Object.keys(inp.events).map((n) => ({ path: `events/${n}.json`, kind: 'events', stage: 't', events: n })) }));
}

before(() => { writeSong(A.song); song = mvh.loadSync(DIR); });
after(() => rmSync(DIR, { recursive: true, force: true }));

test('vizState addendum cases', () => {
  for (const [t, fr, exp] of A.viz_state) close(song.vizState(t, fr), exp, `viz ${t} ${JSON.stringify(fr)}`);
});

test('lyricAt: singer / voice_ids join (lead first)', () => {
  for (const [t, exp] of A.lyric_at) {
    const got = song.lyricAt(t);
    close(got, exp, `lyric ${t}`);
    if (exp.line) assert.deepEqual(Object.keys(got.line).sort(), Object.keys(exp.line).sort());
  }
});

test('meaningAt: section entry by id, else by time; global + section do_not', () => {
  for (const [t, exp] of A.meaning_at) {
    const got = song.meaningAt(t);
    assert.deepEqual(Object.keys(got).sort(), Object.keys(exp).sort());
    close(got, exp, `meaning ${t}`);
  }
});

test('textureData fills NaN-aware channels with the held value', () => {
  const x = A.texture_nan_fill;
  const td = song.textureData(x.ids, { width: x.width });
  assert.equal(td.height, x.height);
  close(Array.from(td.data), x.data);
});

test('spectrumWindow bytes', () => {
  for (const [t, s, exp] of A.spectrum_window) assert.deepEqual(Array.from(song.spectrumWindow(t, s)), exp);
});
