// Golden vectors (docs/contract/golden-vectors.json) against lib/mvh.js.  Run: node --test tests/unit/lib/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import * as mvh from '../../../src/mvh/assets/mvh.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '..', '..', '..');
const G = JSON.parse(readFileSync(path.join(REPO, 'docs', 'contract', 'golden-vectors.json'), 'utf8'));
const TOL = G.tolerance;

export function close(actual, expected, where = '$') {
  if (expected === null) {
    assert.ok(actual === null || actual === undefined, `${where}: expected null, got ${JSON.stringify(actual)}`);
    return;
  }
  if (typeof expected === 'number') {
    assert.equal(typeof actual, 'number', `${where}: expected a number, got ${JSON.stringify(actual)}`);
    assert.ok(!Number.isNaN(actual), `${where}: NaN`);
    assert.ok(Math.abs(actual - expected) <= TOL * (1 + 1e-9) + 1e-12, `${where}: ${actual} != ${expected}`);
    return;
  }
  if (typeof expected === 'boolean' || typeof expected === 'string') {
    assert.equal(actual, expected, `${where}`);
    return;
  }
  if (Array.isArray(expected)) {
    assert.ok(Array.isArray(actual) || ArrayBuffer.isView(actual), `${where}: expected an array`);
    assert.equal(actual.length, expected.length, `${where}: length`);
    expected.forEach((e, i) => close(actual[i], e, `${where}[${i}]`));
    return;
  }
  assert.equal(typeof actual, 'object', `${where}: expected an object`);
  assert.deepEqual(Object.keys(actual).sort(), Object.keys(expected).sort(), `${where}: keys`);
  for (const k of Object.keys(expected)) close(actual[k], expected[k], `${where}.${k}`);
}

const nanify = (arr) => arr.map((x) => (x === null ? NaN : x));
const fmt = (fr) => JSON.stringify(fr);

test('golden file copy in src/mvh/assets/golden is current', () => {
  const a = readFileSync(path.join(REPO, 'docs', 'contract', 'golden-vectors.json'), 'utf8');
  const b = readFileSync(path.join(REPO, 'src', 'mvh', 'assets', 'golden', 'golden-vectors.json'), 'utf8');
  assert.equal(a, b);
});

test('frames: time_of, frame_centre, frame_window, frame_of, roundtrip, frame_count', () => {
  for (const c of G.frames) {
    const fr = c.fr;
    for (const [n, t] of c.time_of) close(mvh.timeOf(n, fr), t, `time_of ${fmt(fr)} ${n}`);
    for (const [n, t] of c.frame_centre) close(mvh.frameCentre(n, fr), t, `frame_centre ${fmt(fr)} ${n}`);
    for (const [n, w] of c.frame_window) close(mvh.frameWindow(n, fr), w, `frame_window ${fmt(fr)} ${n}`);
    for (const [t, n] of c.frame_of) assert.equal(mvh.frameOf(t, fr), n, `frame_of ${fmt(fr)} ${t}`);
    for (const [n, m] of c.roundtrip) assert.equal(mvh.frameOf(mvh.timeOf(n, fr), fr), m, `roundtrip ${fmt(fr)} ${n}`);
    for (const [d, k] of c.frame_count) assert.equal(mvh.frameCount(d, fr), k, `frame_count ${fmt(fr)} ${d}`);
  }
});

test('curve: at() and frame() under all four policies; samples_in_frame', () => {
  const v = G.curve.values;
  for (const p of mvh.POLICIES) for (const [t, y] of G.curve.at[p]) close(mvh.curveAt(v, t, 100, p), y, `at ${p} ${t}`);
  for (const c of G.curve.frame) {
    for (const p of mvh.POLICIES) {
      for (const [n, y] of c.frames[p]) close(mvh.curveFrame(v, n, c.fr, 100, p), y, `frame ${p} ${fmt(c.fr)} ${n}`);
    }
    for (const [n, se] of c.samples_in_frame) assert.deepEqual(mvh.samplesInFrame(n, c.fr, 100, v.length), se);
  }
});

test('flash rule: the event frame carries the peak', () => {
  const v = G.curve.values;
  assert.deepEqual(mvh.flashSamples(G.flash.event_t), G.flash.flash_samples);
  for (const c of G.flash.cases) {
    assert.equal(mvh.frameOf(G.flash.event_t, c.fr), c.event_frame);
    close(mvh.curveFrame(v, c.event_frame, c.fr, 100, 'max'), c.max_at_event_frame);
  }
});

test('voicing: NaN-aware sampling, vocalAt, NaN-aware frames', () => {
  const V = G.voicing;
  const ch = Object.fromEntries(Object.entries(V.channels).map(([k, a]) => [k, Float32Array.from(nanify(a))]));
  const chd = Object.fromEntries(Object.entries(V.channels).map(([k, a]) => [k, nanify(a)]));
  for (const [t, y] of V.midi_at) close(mvh.curveAt(chd['vocal.midi'], t, 100, 'linear', true), y, `midi_at ${t}`);
  for (const [t, r] of V.vocal_at) close(mvh.vocalAt(t, chd, 100, V.phrases, V.notes), r, `vocal_at ${t}`);
  // float32 storage (as in curves/vocal.f32) stays within tolerance of the float64 reference
  for (const [t, r] of V.vocal_at) {
    const a = mvh.vocalAt(t, ch, 100, V.phrases, V.notes);
    assert.equal(a.voiced, r.voiced);
    assert.ok(Math.abs(a.midi - r.midi) < 1e-4);
  }
  for (const c of V.frames) {
    for (const p of mvh.POLICIES) {
      for (const [n, y] of c.frames[p]) close(mvh.curveFrame(chd['vocal.midi'], n, c.fr, 100, p, true), y, `vframe ${p} ${n}`);
    }
  }
});

test('beats: beat_pos, beat_phase, bar_phase, count (pickup bar, odd section), no beats, osc', () => {
  const B = G.beats;
  for (const [t, r] of B.beat_pos) close(mvh.beatPos(t, B.beats), r, `beat_pos ${t}`);
  for (const [t, r] of B.beat_phase) close(mvh.beatPhase(t, B.beats), r, `beat_phase ${t}`);
  for (const [t, r] of B.bar_phase) close(mvh.barPhase(t, B.beats), r, `bar_phase ${t}`);
  for (const [t, r] of B.count) close(mvh.countAt(t, B.beats, B.counts), r, `count ${t}`);
  for (const [t, r] of B.no_beats) close(mvh.beatPos(t, []), r, `no_beats ${t}`);
  for (const [t, shapes, pb, ph] of B.osc) {
    for (const [s, y] of Object.entries(shapes)) close(mvh.osc(t, B.beats, { shape: s, periodBeats: pb, phase: ph }), y, `osc ${s} ${t}`);
  }
});

test('events: at, next, prev, between, inFrame', () => {
  const E = G.events;
  for (const [t, r] of E.at) {
    const a = mvh.eventAt(E.segments, t);
    close(a === null ? null : { id: a.item.id, progress: a.progress, t_in: a.t_in, t_left: a.t_left }, r, `at ${t}`);
  }
  for (const [t, mt, id] of E.next) close((mvh.eventNext(E.cues, t, mt) || { id: null }).id, id, `next ${t} ${mt}`);
  for (const [t, mt, id] of E.prev) close((mvh.eventPrev(E.cues, t, mt) || { id: null }).id, id, `prev ${t} ${mt}`);
  for (const [t, ids] of E.all_at) assert.deepEqual(mvh.eventAllAt(E.segments, t).map((x) => x.id), ids, `all_at ${t}`);
  for (const [a, b, ids] of E.between) assert.deepEqual(mvh.eventBetween(E.cues, a, b).map((x) => x.id), ids);
  for (const [fr, n, ids] of E.in_frame) assert.deepEqual(mvh.eventInFrame(E.cues, n, fr).map((x) => x.id), ids, `${fmt(fr)} ${n}`);
});

test('pulse: defaults, attack + linear, beats unit + smooth', () => {
  const P = G.pulse;
  for (const [t, kw, y] of P.cases) close(mvh.pulse(t, P.items, G.beats.beats, kw), y, `pulse ${t} ${JSON.stringify(kw)}`);
});

test('singerAt: three voices, duet overlap, backing', () => {
  const S = G.singer_at;
  const mo = (voice, t) => {
    const key = voice && S.mouth_open[`vocal.mouth_open.${voice}`] ? `vocal.mouth_open.${voice}` : 'vocal.mouth_open';
    return mvh.curveAt(S.mouth_open[key], t, S.rate, 'max');
  };
  for (const [t, r] of S.cases) close(mvh.singerAt(t, S.singing, mo), r, `singer_at ${t}`);
});

function textureChannels() {
  const a = Array.from({ length: G.texture.channels.a.n }, (_, i) => Number((Math.sin(i * 0.013) * 0.5 + 0.5).toFixed(6)));
  const b = Array.from({ length: G.texture.channels.b.n }, (_, i) => Number(((i % 100) / 100).toFixed(6)));
  return [a, b];
}

test('texture: wrapped layout, texels, sampling equals curve.at', () => {
  const T = G.texture;
  const chans = textureChannels();
  const { data, height, layout } = mvh.packTexture(chans, T.width);
  assert.equal(height, T.height);
  assert.deepEqual(layout, T.layout);
  for (const [c, i, y] of T.texels) close(data[(layout[c].row0 + Math.floor(i / T.width)) * T.width + (i % T.width)], y, `texel ${c} ${i}`);
  for (const [c, t, ts, ca] of T.sample) {
    close(mvh.textureSample(data, layout[c], t), ts, `sample ${c} ${t}`);
    close(mvh.curveAt(chans[c], t), ca, `curve_at ${c} ${t}`);
  }
});

test('spectrum rows', () => {
  for (const [t, s, rows] of G.spectrum_rows.cases) assert.deepEqual(mvh.spectrumRows(t, s, G.spectrum_rows.n_frames), rows);
});
