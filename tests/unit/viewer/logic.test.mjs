// Unit tests for the DOM-free viewer logic (src/mvh/assets/viewer/logic.js). Run: node --test tests/unit/viewer/
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const L = require('../../../src/mvh/assets/viewer/logic.js');

const near = (a, b, e = 1e-6) => assert.ok(Math.abs(a - b) <= e, `${a} != ${b}`);

test('moveBoundary: a first move records the original time; moving it again keeps ONE entry anchored at the original', () => {
  let l = L.moveBoundary([], 17.0, 17.4);
  assert.deepEqual(l, [{ action: 'move', t: 17, to_t: 17.4 }]);
  l = L.moveBoundary(l, 17.4, 18.0);
  assert.deepEqual(l, [{ action: 'move', t: 17, to_t: 18 }]);
  l = L.moveBoundary(l, 18.0, 17.0); // back to where it was: the edit disappears
  assert.deepEqual(l, []);
});

test('moveBoundary: moving an added boundary moves the add', () => {
  let l = L.addBoundary([], 12.5);
  l = L.moveBoundary(l, 12.5, 13.0);
  assert.deepEqual(l, [{ action: 'add', t: 13 }]);
});

test('removeBoundary: removes an add; turns a move into a remove of the ORIGINAL; is idempotent', () => {
  assert.deepEqual(L.removeBoundary(L.addBoundary([], 5), 5), []);
  const mv = L.moveBoundary([], 17, 18);
  assert.deepEqual(L.removeBoundary(mv, 18), [{ action: 'remove', t: 17 }]);
  const rm = L.removeBoundary([], 9);
  assert.deepEqual(L.removeBoundary(rm, 9), rm);
});

test('addBoundary: re-adding a removed boundary cancels the removal', () => {
  const rm = L.removeBoundary([], 9);
  assert.deepEqual(L.addBoundary(rm, 9.02), []);
});

test('setSectionLabel anchors in the middle of the section and replaces a previous label', () => {
  let l = L.setSectionLabel([], 9, 17, 'verse');
  assert.deepEqual(l, [{ t: 13, label: 'verse' }]);
  l = L.setSectionLabel(l, 9, 17, 'drop');
  assert.deepEqual(l, [{ t: 13, label: 'drop' }]);
  assert.deepEqual(L.setSectionLabel(l, 9, 17, ''), []);
  assert.equal(L.cleanLabel('Pre Chorus'), 'pre-chorus');
  assert.equal(L.cleanLabel('123'), null);
});

test('lineDt is relative to the original time even when the analysis already applied a nudge', () => {
  // shown at 10.30 with 0.10 already applied (original 10.20); want it at 10.50 -> total dt = 0.30
  assert.equal(L.lineDt(10.3, 0.1, 10.5), 0.3);
  const lines = L.setLineNudge({}, 'L001', 10.3, 0.1, 10.5);
  assert.deepEqual(lines, { L001: { dt: 0.3 } });
  assert.deepEqual(L.setLineNudge(lines, 'L001', 10.3, 0.1, 10.2), {}); // back to the original removes the entry
});

test('setWord merges and clamps the duration', () => {
  let w = L.setWord({}, 'L001.02', { t: 9.4567 });
  w = L.setWord(w, 'L001.02', { d: -1 });
  assert.deepEqual(w, { 'L001.02': { t: 9.457, d: 0 } });
});

const grid = (n, bpb = 4, t0 = 0.5, dt = 0.5) => Array.from({ length: n }, (_, i) => ({ t: t0 + i * dt, beat_index: i, beat_in_bar: (i % bpb) + 1, beats_in_bar: bpb, bar: Math.floor(i / bpb) + 1, in_pulse: true }));

test('previewGrid: offset shifts, bpm regenerates, phase rotates the bar numbering', () => {
  const g = grid(16);
  const shifted = L.previewGrid(g, { offset: 0.02, appliedOffset: 0 });
  near(shifted[3].t, g[3].t + 0.02);
  const doubled = L.previewGrid(g, { bpm: 240, baseBpm: 120, duration: 8.5 });
  near(doubled[1].t - doubled[0].t, 0.25);
  assert.ok(doubled.every((b) => b.preview));
  const ph = L.previewGrid(g, { phase: 1, appliedPhase: 0 });
  assert.equal(ph[0].beat_in_bar, 2);
  assert.equal(ph.find((b) => b.beat_in_bar === 1).t, g[3].t); // the downbeat moves one beat earlier
  assert.deepEqual(L.previewGrid(g, { offset: 0, appliedOffset: 0 }).map((b) => b.t), g.map((b) => b.t));
});

test('alignOffset puts the nearest (down)beat on the playhead', () => {
  const g = grid(16);
  near(L.alignOffset(g, 1.04, false), 0.04);
  near(L.alignOffset(g, 2.6, true), 0.6 - 0.5 + 0.0, 1e-9 + 0.5); // nearest downbeat of 0.5, 2.5, 4.5 is 2.5 -> +0.1
  near(L.alignOffset(g, 2.6, true), 0.1, 1e-9);
});

test('poolCurve: min/max/mean per pixel column and interpolation when zoomed in', () => {
  const v = new Float32Array(1000).map((_, i) => i % 100); // 10 s at 100 Hz, sawtooth 0..99
  const p = L.poolCurve(v, 100, 0, 10, 10);
  assert.equal(p.min[0], 0); assert.equal(p.max[0], 99);
  near(p.mean[3], 49.5, 1e-4);
  const z = L.poolCurve(v, 100, 0, 0.1, 4); // fewer samples than pixels: interpolated, never NaN
  assert.ok(Array.from(z.mean).every((x) => Number.isFinite(x)));
  const nan = new Float32Array([NaN, NaN, 5, 5]);
  const q = L.poolCurve(nan, 1, 0, 4, 4);
  assert.ok(Number.isNaN(q.mean[0]) === false || Number.isFinite(q.mean[2]));
});

test('wavePyramid halves the bin count per level and keeps extremes', () => {
  const q = new Int8Array(2 * 4096);
  for (let i = 0; i < 4096; i++) { q[2 * i] = -(i % 50); q[2 * i + 1] = i % 70; }
  const lv = L.wavePyramid(q);
  assert.ok(lv.length > 2);
  assert.equal(lv[1].length, q.length / 2);
  assert.equal(Math.max(...lv[lv.length - 1].filter((_, i) => i % 2)), 69);
});

test('formatting helpers', () => {
  assert.equal(L.fmtTime(75.5, 1), '1:15.5');
  assert.equal(L.fmtTime(5, 0), '0:05');
  assert.equal(L.midiName(60), 'C4');
  assert.equal(L.midiName(69), 'A4');
  assert.equal(L.niceStep(60, 6), 10);
  const secs = [{ t: 1, d: 8 }, { t: 9, d: 8 }];
  assert.equal(L.sectionIndexAt(secs, 9), 1);
  assert.equal(L.sectionIndexAt(secs, 0.5), -1);
  assert.equal(L.sectionIndexAt(secs, 17.5), -1);
  assert.equal(L.wordIndexAt([{ t: 1 }, { t: 2 }, { t: 3 }], 2.5), 1);
});
