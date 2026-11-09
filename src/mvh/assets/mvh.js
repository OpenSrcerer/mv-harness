/* mvh.js - loader and helpers for an mv-harness song folder (contract v1.0.0-rc.2).
 *
 * ES module, no dependencies. Works in browsers (fetch), Node (loadSync / fs) and Remotion (call
 * `await load(...)` / `await song.ensure(...)` first; afterwards every helper is synchronous).
 * The semantics are defined by src/mvh/contract/conventions.py (the reference) and docs/CONTRACT.md §9;
 * lib/mvh_load.py implements the same API in Python (snake_case). Golden vectors: docs/contract/golden-vectors.json.
 *
 *   import { load, loadSync, frameOf, timeOf } from './lib/mvh.js';
 *   const song = await load('out/my-song', { include: ['helper:vizState', 'helper:count'] });
 *   song.curve('bands.bass').frame(n, { fps: 24 });   song.events('cues').next(t, { minTier: 2 });
 *
 * Every time is in seconds from the first sample of audio/mix.flac. A frame rule `fr` is {fps, frame0 = 0, early = false};
 * fps is a number (taken literally) or [num, den] (e.g. [24000, 1001]). Helpers never return NaN.
 */

export const VERSION = '1.0.0-rc.2';
export const CONTRACT_VERSION = '1.0.0-rc.2';
export const EPS = 1e-9;
export const POLICIES = Object.freeze(['linear', 'mean', 'max', 'hold']);
export const CURVE_RATE_HZ = 100;
export const SUB_NAMES = Object.freeze(['', 'e', '&', 'a']);

// ============================================================================================ small utils
const LN100 = Math.log(100);
const DEFAULT_IBI = 0.5;

function num(t, what = 't') {
  if (typeof t !== 'number' || !Number.isFinite(t)) throw new TypeError(`mvh: ${what} must be a finite number, got ${t}`);
  return t;
}
const frac = (x) => x - Math.floor(x);
const pymod = (a, b) => ((a % b) + b) % b;
const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
const isFiniteNum = (x) => typeof x === 'number' && Number.isFinite(x);

/** Python's round() for a float: half to even. */
export function roundHalfEven(x) {
  const f = Math.floor(x);
  const d = x - f;
  if (d > 0.5) return f + 1;
  if (d < 0.5) return f;
  return f % 2 === 0 ? f : f + 1;
}

function bisectRight(a, x) {
  let lo = 0, hi = a.length;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (x < a[mid]) hi = mid; else lo = mid + 1; }
  return lo;
}
function bisectLeft(a, x) {
  let lo = 0, hi = a.length;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (a[mid] < x) lo = mid + 1; else hi = mid; }
  return lo;
}
/** First index i in [0, n) with pred(i) true, for a monotone (false..., true...) predicate; n when none. */
function firstTrue(n, pred) {
  let lo = 0, hi = n;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (pred(mid)) hi = mid; else lo = mid + 1; }
  return lo;
}

/** Neumaier-compensated sum (close to Python's math.fsum). */
function fsum(vals) {
  let s = 0, c = 0;
  for (const v of vals) {
    const t = s + v;
    c += Math.abs(s) >= Math.abs(v) ? (s - t) + v : (v - t) + s;
    s = t;
  }
  return s + c;
}

// cached per items array: sorted times, max duration
const _timesCache = new WeakMap();
function timesOf(items) {
  let c = _timesCache.get(items);
  if (!c) {
    const times = new Float64Array(items.length);
    let maxD = 0;
    for (let i = 0; i < items.length; i++) {
      times[i] = +items[i].t;
      const d = items[i].d;
      if (d != null && d > maxD) maxD = +d;
    }
    c = { times, maxD };
    _timesCache.set(items, c);
  }
  return c;
}

// ============================================================================================ frames
/** Normalise a frame rule: {fps, frame0, early}, a number, or [num, den]. */
export function frameRule(fr) {
  if (fr == null) throw new TypeError('mvh: a frame rule {fps, frame0, early} is required');
  if (fr.__mvhRule) return fr;
  let fps = fr, frame0 = 0, early = false;
  if (typeof fr === 'object' && !Array.isArray(fr)) {
    fps = fr.fps;
    frame0 = fr.frame0 == null ? 0 : fr.frame0;
    early = !!fr.early;
  }
  let n, d;
  if (Array.isArray(fps)) { n = Number(fps[0]); d = Number(fps[1]); } else { n = Number(fps); d = 1; }
  if (!(n > 0 && d > 0) || !Number.isFinite(n) || !Number.isFinite(d)) throw new RangeError(`mvh: fps must be positive: ${fps}`);
  if (!Number.isInteger(frame0)) throw new RangeError('mvh: frame0 must be an integer');
  return Object.freeze({ __mvhRule: true, num: n, den: d, frame0, early, fps: n / d, half: 0.5 * d / n });
}

/** t_n = (n - frame0) / F: the nominal time of video frame n. */
export function timeOf(n, fr) { const r = frameRule(fr); return (n - r.frame0) * r.den / r.num; }
/** Sampling instant of frame n: t_n (centred) or t_n + 1/(2F) (early). */
export function frameCentre(n, fr) { const r = frameRule(fr); return timeOf(n, r) + (r.early ? r.half : 0); }
/** Half-open window [a, b) of frame n. */
export function frameWindow(n, fr) { const r = frameRule(fr); const c = frameCentre(n, r); return [c - r.half, c + r.half]; }
/** The frame whose window contains t (events, curve samples and the playhead all use this). */
export function frameOf(t, fr) {
  const r = frameRule(fr);
  return Math.floor(num(t) * r.num / r.den + (r.early ? 0 : 0.5) + EPS) + r.frame0;
}
/** Number of frames n = frame0 .. frame0+count-1 with time_of(n) < duration. */
export function frameCount(duration, fr) {
  const r = frameRule(fr);
  return Math.max(0, Math.ceil(num(duration, 'duration') * r.num / r.den - EPS));
}

// ============================================================================================ curves
/** Curve sample indices [start, stop) that belong to frame n. */
export function samplesInFrame(n, fr, rate, nSamples) {
  const r = frameRule(fr);
  const [a, b] = frameWindow(n, r);
  const lo = Math.max(0, Math.floor(a * rate) - 1);
  const hi = Math.min(nSamples, Math.ceil(b * rate) + 2);
  let first = -1, last = -1;
  for (let i = lo; i < hi; i++) {
    if (frameOf(i / rate, r) === n) { if (first < 0) first = i; last = i; }
  }
  return first < 0 ? [0, 0] : [first, last + 1];
}

export function lerpAt(v, x) {
  const n = v.length;
  if (n === 0) return 0;
  if (x <= 0) return +v[0];
  if (x >= n - 1) return +v[n - 1];
  const i = Math.floor(x);
  const f = x - i;
  const a = +v[i], b = +v[i + 1];
  return a + (b - a) * f;
}

function nearest(n, x) {
  const k = Math.floor(x + 0.5 + EPS);
  return k < 0 ? 0 : k > n - 1 ? n - 1 : k;
}

export function holdAt(v, x) {
  if (v.length === 0) return 0;
  return +v[nearest(v.length, x)];
}

/** NaN-aware pitch sampling (NaN = unvoiced); NaN only when no sample is voiced. */
export function nanAwareAt(v, x) {
  const n = v.length;
  if (n === 0) return NaN;
  const xc = x < 0 ? 0 : x > n - 1 ? n - 1 : x;
  const i = Math.floor(xc);
  const j = Math.min(i + 1, n - 1);
  const a = +v[i], b = +v[j];
  if (Number.isFinite(a) && Number.isFinite(b)) return a + (b - a) * (xc - i);
  const k = nearest(n, x);
  if (Number.isFinite(+v[k])) return +v[k];
  for (let m = k - 1; m >= 0; m--) if (Number.isFinite(+v[m])) return +v[m];
  for (let m = k + 1; m < n; m++) if (Number.isFinite(+v[m])) return +v[m];
  return NaN;
}

function checkPolicy(policy) {
  if (!POLICIES.includes(policy)) throw new RangeError(`mvh: unknown resample policy '${policy}'`);
}

/** Point value at t: lerp (linear/mean/max), nearest (hold), NaN-aware for pitch channels. Never NaN. */
export function curveAt(v, t, rate = CURVE_RATE_HZ, policy = 'linear', nanAware = false) {
  checkPolicy(policy);
  const x = num(t) * rate;
  let y;
  if (nanAware) y = nanAwareAt(v, x);
  else if (policy === 'hold') y = holdAt(v, x);
  else y = lerpAt(v, x);
  return Number.isNaN(y) ? 0 : y;
}

/** Value of video frame n under the channel's resample policy. Never NaN. */
export function curveFrame(v, n, fr, rate = CURVE_RATE_HZ, policy = 'linear', nanAware = false) {
  checkPolicy(policy);
  const r = frameRule(fr);
  const c = frameCentre(n, r);
  const x = c * rate;
  if (policy === 'mean' || policy === 'max') {
    const [s0, s1] = samplesInFrame(n, r, rate, v.length);
    let vals = [];
    for (let i = s0; i < s1; i++) vals.push(+v[i]);
    if (nanAware) vals = vals.filter((a) => Number.isFinite(a));
    if (vals.length) {
      if (policy === 'mean') return fsum(vals) / vals.length;
      let m = -Infinity;
      for (const a of vals) if (a > m) m = a;
      return m;
    }
    return curveAt(v, c, rate, 'linear', nanAware);
  }
  if (nanAware) { const y = nanAwareAt(v, x); return Number.isNaN(y) ? 0 : y; }
  return policy === 'hold' ? holdAt(v, x) : lerpAt(v, x);
}

/** Writer rule for event-driven max channels: [floor(t*rate), ceil(t*rate)]. */
export function flashSamples(tEvent, rate = CURVE_RATE_HZ) {
  const x = tEvent * rate;
  const k = roundHalfEven(x);
  if (Math.abs(x - k) < EPS) return [k, k];
  return [Math.floor(x), Math.ceil(x)];
}

// ============================================================================================ beats
function ibi(beats, i) {
  if (beats.length < 2) return DEFAULT_IBI;
  i = Math.max(0, Math.min(i, beats.length - 2));
  return +beats[i + 1].t - +beats[i].t;
}
const inPulse = (b) => (b.in_pulse == null ? true : !!b.in_pulse);

/** Fractional beat index at t: {value, in_pulse}. Outside the grid: extended at the first / last interval. */
export function beatPos(t, beats) {
  num(t);
  const n = beats.length;
  if (n === 0) return { value: t / DEFAULT_IBI, in_pulse: false };
  const { times } = timesOf(beats);
  if (t < times[0]) return { value: (t - times[0]) / ibi(beats, 0), in_pulse: false };
  if (t >= times[n - 1]) return { value: (n - 1) + (t - times[n - 1]) / ibi(beats, n - 2), in_pulse: false };
  const i = bisectRight(times, t) - 1;
  const val = i + (t - times[i]) / (times[i + 1] - times[i]);
  return { value: val, in_pulse: inPulse(beats[i]) && inPulse(beats[i + 1]) };
}

export function beatPhase(t, beats) {
  const p = beatPos(t, beats);
  return { value: frac(p.value), in_pulse: p.in_pulse };
}

function beatMeta(k, beats) {
  const n = beats.length;
  if (n === 0) return [pymod(k, 4) + 1, 4];
  if (k >= 0 && k < n) return [Math.trunc(beats[k].beat_in_bar), Math.trunc(beats[k].beats_in_bar)];
  const ref = k < 0 ? beats[0] : beats[n - 1];
  const kref = k < 0 ? 0 : n - 1;
  const nb = Math.trunc(ref.beats_in_bar);
  return [pymod(Math.trunc(ref.beat_in_bar) - 1 + (k - kref), nb) + 1, nb];
}

/** {value, in_pulse}: ((beat_in_bar - 1) + frac(beat_pos)) / beats_in_bar in [0, 1). */
export function barPhase(t, beats) {
  const p = beatPos(t, beats);
  const k = Math.floor(p.value);
  const [bib, nb] = beatMeta(k, beats);
  return { value: ((bib - 1) + frac(p.value)) / nb, in_pulse: p.in_pulse };
}

/** count(t) -> {eight_id, count, sub, phase, accent, partial, lead_in, in_pulse}. */
export function countAt(t, beats, counts) {
  const p = beatPos(t, beats);
  const pv = p.value;
  const sub = Math.min(3, Math.floor(4 * frac(pv)));
  let hit = null;
  for (const c of counts) {
    const s = +c.start_beat;
    if (s <= pv && pv < s + +c.len && (hit === null || s >= +hit.start_beat)) hit = c;
  }
  if (hit === null) {
    return { eight_id: null, count: null, sub, phase: null, accent: 0, partial: false, lead_in: false, in_pulse: p.in_pulse };
  }
  const k = Math.floor(pv - +hit.start_beat);
  const acc = hit.accents || [];
  return {
    eight_id: hit.id, count: Math.trunc(hit.first_count == null ? 1 : hit.first_count) + k, sub,
    phase: (pv - +hit.start_beat) / +hit.len,
    accent: k < acc.length ? +acc[k] : 0,
    partial: !!hit.partial, lead_in: !!hit.lead_in, in_pulse: p.in_pulse,
  };
}

// ============================================================================================ events
/** events(name).at(t): {item, progress, t_in, t_left} for the latest-starting item with d > 0 containing t, or null. */
export function eventAt(items, t) {
  num(t);
  const { times, maxD } = timesOf(items);
  let best = null;
  const reach = maxD + 1e-9 * (1 + Math.abs(t));   // no item that starts earlier than t - reach can contain t
  for (let i = bisectRight(times, t) - 1; i >= 0 && t - times[i] <= reach; i--) {
    const it = items[i];
    const d = it.d;
    if (d != null && d > 0 && times[i] <= t && t < times[i] + +d) { best = it; break; }
  }
  if (best === null) return null;
  const t0 = +best.t, d = +best.d;
  return { item: best, progress: (t - t0) / d, t_in: t - t0, t_left: t0 + d - t };
}

/** events(name).allAt(t): EVERY item with d > 0 whose [t, t + d) contains t, sorted by t (ties: file order). */
export function eventAllAt(items, t) {
  num(t);
  const { times, maxD } = timesOf(items);
  const reach = maxD + 1e-9 * (1 + Math.abs(t));
  const out = [];
  for (let i = bisectRight(times, t) - 1; i >= 0 && t - times[i] <= reach; i--) {
    const it = items[i];
    const d = it.d;
    if (d != null && d > 0 && times[i] <= t && t < times[i] + +d) out.push(it);
  }
  return out.reverse();
}

function tierOk(it, minTier) {
  return minTier == null || (it.tier != null && Math.trunc(it.tier) <= Math.trunc(minTier));
}

/** First item with item.t > t (strictly after); minTier keeps tiers 1..minTier. */
export function eventNext(items, t, minTier = null) {
  num(t);
  const { times } = timesOf(items);
  for (let i = bisectRight(times, t); i < items.length; i++) if (tierOk(items[i], minTier)) return items[i];
  return null;
}

/** Last item with item.t <= t (at or before). */
export function eventPrev(items, t, minTier = null) {
  num(t);
  const { times } = timesOf(items);
  for (let i = bisectRight(times, t) - 1; i >= 0; i--) if (tierOk(items[i], minTier)) return items[i];
  return null;
}

/** Items with t0 <= item.t < t1. */
export function eventBetween(items, t0, t1, minTier = null) {
  num(t0, 't0'); num(t1, 't1');
  const { times } = timesOf(items);
  const out = [];
  for (let i = bisectLeft(times, t0), e = bisectLeft(times, t1); i < e; i++) if (tierOk(items[i], minTier)) out.push(items[i]);
  return out;
}

/** Items whose t falls in frame n: frameOf(item.t) == n. */
export function eventInFrame(items, n, fr, minTier = null) {
  const r = frameRule(fr);
  const { times } = timesOf(items);
  const out = [];
  for (let i = firstTrue(times.length, (k) => frameOf(times[k], r) >= n); i < times.length; i++) {
    if (frameOf(times[i], r) !== n) break;
    if (tierOk(items[i], minTier)) out.push(items[i]);
  }
  return out;
}

function idNumber(id) {
  const m = /(\d+)$/.exec(id || '');
  return m ? parseInt(m[1], 10) : 1 << 30;
}

function containsT(it, t) {
  const d = it.d;
  return d != null && d > 0 && +it.t <= t && t < +it.t + +d;
}

function singerOrder(a, b) {
  const la = a.lead_backing === 'lead' ? 0 : 1, lb = b.lead_backing === 'lead' ? 0 : 1;
  if (la !== lb) return la - lb;
  const va = a.voice_id ? idNumber(a.voice_id) : 1 << 30, vb = b.voice_id ? idNumber(b.voice_id) : 1 << 30;
  if (va !== vb) return va - vb;
  const xa = a.line_id || '', xb = b.line_id || '';
  return xa < xb ? -1 : xa > xb ? 1 : 0;
}

/** singerAt(t): singing items containing t, lead first, then voice number, then line id; one entry per
 *  (character, voice) (the first in that order; W3C-5). */
export function singerAt(t, singing, mouthOpen) {
  num(t);
  const all = singing.filter((it) => containsT(it, t));
  all.sort(singerOrder);
  const seen = new Set();
  const hits = all.filter((it) => {
    const k = JSON.stringify([it.character_id ?? null, it.voice_id ?? null]);
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
  return hits.map((it) => ({
    character_id: it.character_id ?? null, voice_id: it.voice_id ?? null, lead_backing: it.lead_backing ?? null,
    line_id: it.line_id ?? null, mouth_open: +mouthOpen(it.voice_id ?? null, t),
  }));
}

/** vocalAt(t) -> {voiced, midi, hz, conf, pitch01, phrase_id, note}; never NaN. ch: map of vocal.* arrays. */
export function vocalAt(t, ch, rate = CURVE_RATE_HZ, phrases = [], notes = []) {
  const x = num(t) * rate;
  const empty = [];
  const voiced = holdAt(ch['vocal.voiced'] || empty, x) >= 0.5;
  const midi = nanAwareAt(ch['vocal.midi'] || empty, x);
  const hz = nanAwareAt(ch['vocal.f0_hz'] || empty, x);
  const ph = eventAt(phrases, t);
  const nt = eventAt(notes, t);
  return {
    voiced, midi: Number.isNaN(midi) ? 0 : midi, hz: Number.isNaN(hz) ? 0 : hz,
    conf: lerpAt(ch['vocal.conf'] || empty, x), pitch01: lerpAt(ch['vocal.pitch01'] || empty, x),
    phrase_id: ph ? (ph.item.id ?? null) : null, note: nt ? nt.item : null,
  };
}

// ============================================================================================ textures
/** Wrap layout: channel c occupies rows [row0, row0 + rows), rows = ceil(n / width). */
export function textureLayout(lengths, width = 1024) {
  const out = [];
  let row = 0;
  for (const n of lengths) {
    const rows = Math.max(1, Math.ceil(n / width));
    out.push({ row0: row, rows, n, width });
    row += rows;
  }
  return out;
}

/** Pack channels into a row-major [height x width] Float32Array (padding repeats the last value). */
export function packTexture(channels, width = 1024) {
  const layout = textureLayout(channels.map((v) => v.length), width);
  const height = layout.reduce((s, l) => s + l.rows, 0);
  const data = new Float32Array(height * width);
  channels.forEach((v, c) => {
    const l = layout[c];
    const n = v.length;
    const last = n ? +v[n - 1] : 0;
    for (let k = 0; k < l.rows * width; k++) data[l.row0 * width + k] = k < n ? +v[k] : last;
  });
  return { data, height, layout };
}

/** What mvhCurve (lib/mvh.glsl) computes: manual lerp over the wrapped texels (nearest for hold). */
export function textureSample(data, lay, t, rate = CURVE_RATE_HZ, policy = 'linear') {
  const n = lay.n, w = lay.width, row0 = lay.row0;
  const texel = (i) => +data[(row0 + Math.floor(i / w)) * w + (i % w)];
  let x = num(t) * rate;
  if (policy === 'hold') return texel(nearest(n, x));
  x = x < 0 ? 0 : x > n - 1 ? n - 1 : x;
  const i = Math.floor(x);
  const a = texel(i), b = texel(Math.min(i + 1, n - 1));
  return a + (b - a) * (x - i);
}

// ============================================================================================ pulse / osc
function shapeOf(d, shape) {
  if (d < 0) return 0;
  if (shape === 'exp') return Math.exp(-LN100 * d);
  if (shape === 'linear') return Math.max(0, 1 - d);
  if (shape === 'smooth') return d >= 1 ? 0 : 1 - d * d * (3 - 2 * d);
  throw new RangeError(`mvh: unknown pulse shape '${shape}'`);
}

function weightOf(it) {
  if (it.strength != null) return +it.strength;
  if (it.vel != null) return +it.vel;
  return 1;
}

/** A 0..1 flash per item: w * g(dist / decay) after it, w * g(dist / attack) before it (attack > 0). */
export function pulse(t, items, beats = null, { attack = 0, decay = 0.25, unit = 's', shape = 'exp' } = {}) {
  num(t);
  if (unit !== 's' && unit !== 'beats') throw new RangeError(`mvh: unknown pulse unit '${unit}'`);
  const bs = beats || [];
  const dist = (a, b) => (unit === 's' ? b - a : beatPos(b, bs).value - beatPos(a, bs).value);
  let out = 0;
  const p = eventPrev(items, t);
  if (p !== null && decay > 0) out = Math.max(out, weightOf(p) * shapeOf(dist(+p.t, t) / decay, shape));
  else if (p !== null && +p.t === t) out = Math.max(out, weightOf(p));
  const q = eventNext(items, t);
  if (q !== null && attack > 0) out = Math.max(out, weightOf(q) * shapeOf(dist(t, +q.t) / attack, shape));
  return Math.min(1, Math.max(0, out));
}

/** Beat-locked oscillator in [0, 1], 1 on the beat when phase = 0. */
export function osc(t, beats, { shape = 'sine', periodBeats = 1, phase = 0 } = {}) {
  const x = frac(beatPos(t, beats).value / periodBeats + phase);
  if (shape === 'sine') return 0.5 + 0.5 * Math.cos(2 * Math.PI * x);
  if (shape === 'saw') return 1 - x;
  if (shape === 'square') return x < 0.5 ? 1 : 0;
  if (shape === 'triangle') return 1 - 2 * Math.min(x, 1 - x);
  throw new RangeError(`mvh: unknown osc shape '${shape}'`);
}

/** Row indices of spectrumWindow(t, s): k = round(s * rate) + 1 rows, oldest first; null outside [0, n). */
export function spectrumRows(t, s, nFrames, rate = CURVE_RATE_HZ) {
  const end = Math.floor(num(t) * rate + 0.5 + EPS);
  const k = roundHalfEven(num(s, 's') * rate) + 1;
  const out = [];
  for (let i = end - k + 1; i <= end; i++) out.push(i >= 0 && i < nFrames ? i : null);
  return out;
}

// ============================================================================================ vizState constants
/** Constants copied from viz/js/audio.js (see docs/contract/golden-addendum.md). */
export const VIZ = Object.freeze({
  NUM_BANDS: 128, WAVE_LEN: 512, F_MIN: 32, F_MAX: 16000,
  BEAT_DECAY_S: 0.3,        // beat *= exp(-dt / 0.3)
  PULSE_DECAY_S: 0.11,      // beatPulse / midPulse / highPulse *= exp(-dt / 0.11)
  PEAK_FALL_PER_S: 0.45,    // peaks[k] = max(peaks[k] - dt * 0.45, bands[k])
  BEAT_STRENGTH_MIN: 0.55,  // bass onset strength = clamp(0.55 + ..., 0.55, 1)
  PULSE_STRENGTH_MIN: 0.6,  // mid / high onset pulse = clamp(0.6 + ..., 0.6, 1)
  RECENT_BEATS: 8, RECENT_BEAT_EMPTY: -100,
  HIT_RELEASE: 0.18, HIT_THRESHOLD: 0.35, KICK_GATE_DB: -46, HIT_FLOOR: 0.05, REF_FLOOR: 0.075, REARM_DB: 4,
  RANGE_T: Object.freeze({ bass: Object.freeze([0, 0.25]), mid: Object.freeze([0.25, 0.68]), high: Object.freeze([0.68, 1]) }),
  BEAT_WINDOW_S: 10,        // bass onsets older than this no longer contribute to `beat` (exp(-10/0.3) ~ 3e-15)
  PEAK_WINDOW_S: 2.25,      // spectrum history used for `peaks` (a full-scale peak falls to 0 in 1/0.45 s)
  DEFAULT_FPS: 60,
});

function vizRanges() {
  const ratio = VIZ.F_MAX / VIZ.F_MIN;
  const idx = (f) => clamp(Math.round(Math.log(f / VIZ.F_MIN) / Math.log(ratio) * VIZ.NUM_BANDS), 0, VIZ.NUM_BANDS - 1);
  return {
    bass: [idx(32), idx(150)], kick: [idx(35), idx(100)], mid: [idx(150), idx(2200)], high: [idx(2200), idx(16000)],
    flux: [idx(32), idx(260)], fluxMid: [idx(300), idx(2200)], fluxHigh: [idx(2500), idx(14000)],
  };
}

/** The object vizState() returns: the viz/js/audio.js AudioEngine fields, plus its band accessors. */
export class VizState {
  bandAt(t) { return this.bands[clamp(Math.round(t * (VIZ.NUM_BANDS - 1)), 0, VIZ.NUM_BANDS - 1)]; }
  bandLow(x) { const r = VIZ.RANGE_T.bass; return this.bandAt(r[0] + (r[1] - r[0]) * clamp(x, 0, 1)); }
  bandMid(x) { const r = VIZ.RANGE_T.mid; return this.bandAt(r[0] + (r[1] - r[0]) * clamp(x, 0, 1)); }
  bandHigh(x) { const r = VIZ.RANGE_T.high; return this.bandAt(r[0] + (r[1] - r[0]) * clamp(x, 0, 1)); }
  update() { /* offline: state is computed by song.vizState(t) */ }
  on() { return this; }
}

// ============================================================================================ data sources
const IS_LE = new Uint8Array(new Uint16Array([1]).buffer)[0] === 1;

function nodeModule(name) {
  try {
    if (typeof process !== 'undefined' && process && typeof process.getBuiltinModule === 'function') {
      return process.getBuiltinModule(name);
    }
  } catch (e) { /* not node */ }
  return null;
}

function isUrlLike(base) {
  return base instanceof URL || /^[a-z][a-z0-9+.-]*:\/\//i.test(String(base)) || /^(blob|data):/i.test(String(base));
}

function ownBuffer(u8) {
  // a fresh, 4-byte aligned ArrayBuffer (Node Buffers may be slices of a shared pool)
  const out = new ArrayBuffer(u8.byteLength);
  new Uint8Array(out).set(u8);
  return out;
}

class Source {
  constructor(base, fetchFn) {
    const fs = nodeModule('node:fs');
    const path = nodeModule('node:path');
    const asPath = fs && path && !(isUrlLike(base) && !String(base).startsWith('file:'));
    if (asPath) {
      let p = base;
      if (String(base).startsWith('file:')) {
        const url = nodeModule('node:url');
        p = url.fileURLToPath(String(base));
      }
      this.mode = 'fs';
      this.fs = fs;
      this.root = path.resolve(String(p));
      this.join = (rel) => path.join(this.root, ...rel.split('/'));
      this.label = this.root;
    } else {
      this.mode = 'url';
      let b = String(base);
      if (!b.endsWith('/')) b += '/';
      const loc = typeof globalThis.location !== 'undefined' && globalThis.location ? globalThis.location.href : undefined;
      this.baseUrl = loc ? new URL(b, loc) : new URL(b);
      this.fetch = fetchFn || (typeof globalThis.fetch === 'function' ? globalThis.fetch.bind(globalThis) : null);
      if (!this.fetch) throw new Error('mvh: no fetch() available; pass {fetch} to load()');
      this.label = this.baseUrl.href;
    }
  }

  get canSync() { return this.mode === 'fs'; }

  readSync(rel, kind) {
    if (this.mode !== 'fs') return undefined;
    let buf;
    try { buf = this.fs.readFileSync(this.join(rel)); } catch (e) {
      if (e && (e.code === 'ENOENT' || e.code === 'ENOTDIR')) return null;
      throw e;
    }
    return kind === 'text' ? buf.toString('utf8') : ownBuffer(buf);
  }

  async read(rel, kind) {
    if (this.mode === 'fs') {
      let buf;
      try { buf = await this.fs.promises.readFile(this.join(rel)); } catch (e) {
        if (e && (e.code === 'ENOENT' || e.code === 'ENOTDIR')) return null;
        throw e;
      }
      return kind === 'text' ? buf.toString('utf8') : ownBuffer(buf);
    }
    const url = new URL(rel, this.baseUrl);
    const res = await this.fetch(url.href);
    if (res.status === 404 || res.status === 410) return null;
    if (!res.ok) throw new Error(`mvh: GET ${url.href} failed: HTTP ${res.status}`);
    if (kind === 'text') return await res.text();
    return await res.arrayBuffer();
  }
}

function parseJson(text, rel) {
  try { return JSON.parse(text.charCodeAt(0) === 0xfeff ? text.slice(1) : text); } catch (e) {
    throw new Error(`mvh: ${rel} is not valid JSON: ${e.message}`);
  }
}

function f32View(buf, off, n) {
  if (IS_LE && off % 4 === 0) return new Float32Array(buf, off, n);
  const dv = new DataView(buf, off, 4 * n);
  const out = new Float32Array(n);
  for (let i = 0; i < n; i++) out[i] = dv.getFloat32(4 * i, true);
  return out;
}

function sortedByT(items) {
  for (let i = 1; i < items.length; i++) {
    if (+items[i].t < +items[i - 1].t) {
      return items.map((it, k) => [it, k]).sort((a, b) => (+a[0].t - +b[0].t) || (a[1] - b[1])).map((p) => p[0]);
    }
  }
  return items;
}

/** Which data each helper needs (for song.ensure('helper:<name>')). */
export const HELPER_NEEDS = Object.freeze({
  beatPos: ['events:beats'], beatPhase: ['events:beats'], barPhase: ['events:beats'], osc: ['events:beats'],
  pulse: ['events:beats'], count: ['events:beats', 'events:counts'],
  lyricAt: ['lyrics', 'events:singing'],
  vocalAt: ['curves:vocal', 'events:vocal_phrases', 'events:notes.vocals'],
  singerAt: ['events:singing', 'curves:vocal'],
  meaningAt: ['events:sections', 'meaning'],
  spectrumAt: ['curves:spectrum128'], spectrumWindow: ['curves:spectrum128'],
  vizState: ['curves:core', 'curves:spectrum128', 'events:onsets.bass', 'events:onsets.mid', 'events:onsets.high'],
});
const SNAKE = { beat_pos: 'beatPos', beat_phase: 'beatPhase', bar_phase: 'barPhase', lyric_at: 'lyricAt', vocal_at: 'vocalAt',
  singer_at: 'singerAt', meaning_at: 'meaningAt', spectrum_at: 'spectrumAt', spectrum_window: 'spectrumWindow', viz_state: 'vizState' };

const JSON_FILES = { lyrics: 'lyrics/lyrics.json', meaning: 'meaning/meaning.json' };

// ============================================================================================ Curve / Events
export class Curve {
  constructor(id, values, meta) {
    this.id = id;
    this.values = values;
    this.meta = meta;
    this.rate = meta.rate_hz == null ? CURVE_RATE_HZ : +meta.rate_hz;
    this.policy = meta.resample || 'linear';
    this.nanAware = !!(meta.special && meta.special.nan === 'unvoiced');
  }
  get n() { return this.values.length; }
  at(t) { return curveAt(this.values, t, this.rate, this.policy, this.nanAware); }
  frame(n, fr) { return curveFrame(this.values, n, fr, this.rate, this.policy, this.nanAware); }
}

export class Events {
  constructor(name, env, exists = true) {
    this.name = name;
    this.exists = exists;
    this.kind = env.kind || null;
    this.fields = env.fields || {};
    this.provenance = env.provenance || {};
    this.schema = env.schema || null;
    this.items = sortedByT(Array.isArray(env.items) ? env.items : []);
  }
  get length() { return this.items.length; }
  at(t) { return eventAt(this.items, t); }
  allAt(t) { return eventAllAt(this.items, t); }
  next(t, { minTier = null } = {}) { return eventNext(this.items, t, minTier); }
  prev(t, { minTier = null } = {}) { return eventPrev(this.items, t, minTier); }
  between(t0, t1, { minTier = null } = {}) { return eventBetween(this.items, t0, t1, minTier); }
  inFrame(n, fr, { minTier = null } = {}) { return eventInFrame(this.items, n, fr, minTier); }
  byId(id) { return this.items.find((it) => it.id === id) || null; }
}

const EMPTY_EVENTS = (name) => new Events(name, { items: [] }, false);

// ============================================================================================ Song
export class Song {
  constructor(source, manifest, index) {
    this.source = source;
    this.base = source.label;
    this.manifest = manifest || {};
    this.index = index || { files: {}, channels: [] };
    this.index.files = this.index.files || {};
    this.index.channels = this.index.channels || [];
    this._chan = new Map(this.index.channels.map((c) => [c.id, c]));
    this._raw = new Map();      // key -> loaded raw value (ArrayBuffer / parsed JSON / null when missing)
    this._curves = new Map();
    this._events = new Map();
    this._lyr = undefined;
    this.defaultFr = null;      // set by load(base, {fr}): the frame rule vizState uses when called without one
    const m = this.manifest;
    let dur = m.source && m.source.duration_s != null ? +m.source.duration_s
      : m.summary && m.summary.duration_s != null ? +m.summary.duration_s : null;
    if (dur == null) {
      dur = 0;
      for (const f of Object.values(this.index.files)) if (f.rate_hz > 0) dur = Math.max(dur, f.n_frames / f.rate_hz);
    }
    this.duration = dur;
  }

  // ------------------------------------------------------------------ resources
  /** Events names listed in the manifest. */
  get eventNames() {
    const out = [];
    for (const f of this.manifest.files || []) {
      if (f.kind !== 'events') continue;
      out.push(f.events || f.path.replace(/^.*\//, '').replace(/\.json$/, ''));
    }
    return out;
  }
  /** Curve channel ids in curves/index.json. */
  get channelIds() { return this.index.channels.map((c) => c.id); }
  hasCurve(id) { return this._chan.has(id); }

  _eventsPath(name) {
    for (const f of this.manifest.files || []) {
      if (f.kind === 'events' && (f.events === name || f.path === `events/${name}.json`)) return f.path;
    }
    if (name === 'visemes' || name === 'phonemes') return `lipsync/${name}.json`;
    return `events/${name}.json`;
  }

  _keyInfo(key) {
    if (key.startsWith('curves:')) {
      const fid = key.slice(7);
      const f = this.index.files[fid];
      if (!f) return { rel: null, kind: 'bytes' };
      return { rel: f.path, kind: 'bytes' };
    }
    if (key.startsWith('events:')) return { rel: this._eventsPath(key.slice(7)), kind: 'json' };
    if (key in JSON_FILES) return { rel: JSON_FILES[key], kind: 'json' };
    throw new RangeError(`mvh: unknown resource '${key}'`);
  }

  /** Resolve an ensure() spec into resource keys. */
  resolve(spec) {
    if (Array.isArray(spec)) return [...new Set(spec.flatMap((s) => this.resolve(s)))];
    const s = String(spec);
    if (s === 'all') return [...this.resolve('curves:*'), ...this.resolve('events:*'), 'lyrics', 'meaning'];
    if (s === 'curves:*') return Object.keys(this.index.files).map((f) => `curves:${f}`);
    if (s === 'events:*') return this.eventNames.map((n) => `events:${n}`);
    if (s === 'spectrum') return ['curves:spectrum128'];
    if (s.startsWith('helper:')) {
      const h = SNAKE[s.slice(7)] || s.slice(7);
      const need = HELPER_NEEDS[h];
      if (!need) throw new RangeError(`mvh: unknown helper '${h}'`);
      return need;
    }
    if (s.startsWith('curves:') || s.startsWith('events:') || s in JSON_FILES) return [s];
    if (s in this.index.files) return [`curves:${s}`];
    if (this._chan.has(s)) return [`curves:${this._chan.get(s).file}`];
    return [`events:${s}`];
  }

  _store(key, kind, raw, rel) {
    let v = raw;
    if (raw != null && kind === 'json') v = parseJson(raw, rel);
    this._raw.set(key, v == null ? null : v);
  }

  /** Load resources so the next synchronous calls are safe (Remotion / browsers). */
  async ensure(spec) {
    const keys = this.resolve(spec);
    await Promise.all(keys.map(async (key) => {
      if (this._raw.has(key)) return;
      const { rel, kind } = this._keyInfo(key);
      const raw = rel == null ? null : await this.source.read(rel, kind === 'json' ? 'text' : 'bytes');
      this._store(key, kind, raw, rel);
    }));
  }

  /** Synchronous access to a resource (lazy read in Node; error in browsers when not ensured). */
  _get(key) {
    if (this._raw.has(key)) return this._raw.get(key);
    const { rel, kind } = this._keyInfo(key);
    if (rel == null) { this._raw.set(key, null); return null; }
    if (!this.source.canSync) {
      throw new Error(`mvh: '${key}' is not loaded; call await song.ensure('${key}') first ` +
        `(or load(base, {include: ['${key}']}))`);
    }
    this._store(key, kind, this.source.readSync(rel, kind === 'json' ? 'text' : 'bytes'), rel);
    return this._raw.get(key);
  }

  isLoaded(spec) { return this.resolve(spec).every((k) => this._raw.has(k)); }

  // ------------------------------------------------------------------ curves
  curve(id) {
    let c = this._curves.get(id);
    if (c) return c;
    const meta = this._chan.get(id);
    if (!meta) throw new RangeError(`mvh: unknown curve channel '${id}' (see curves/index.json)`);
    const f = this.index.files[meta.file];
    if (!f || f.dtype !== 'f32le') throw new RangeError(`mvh: '${id}' is not a float curve (use spectrumAt / spectrumWindow)`);
    const buf = this._get(`curves:${meta.file}`);
    if (buf == null) throw new Error(`mvh: curve file ${f.path} is missing`);
    c = new Curve(id, f32View(buf, meta.offset_bytes, meta.n), meta);
    this._curves.set(id, c);
    return c;
  }

  _curveOrNull(id) { return this._chan.has(id) ? this.curve(id) : null; }

  // ------------------------------------------------------------------ events
  events(name) {
    let e = this._events.get(name);
    if (e) return e;
    const env = this._get(`events:${name}`);
    e = env == null ? EMPTY_EVENTS(name) : new Events(name, env, true);
    this._events.set(name, e);
    return e;
  }

  get beats() { return this.events('beats').items; }

  // ------------------------------------------------------------------ frames
  frameCount(fr) { return frameCount(this.duration, fr); }

  // ------------------------------------------------------------------ rhythm
  beatPos(t) { return beatPos(t, this.beats); }
  beatPhase(t) { return beatPhase(t, this.beats); }
  barPhase(t) { return barPhase(t, this.beats); }
  count(t) { return countAt(t, this.beats, this.events('counts').items); }
  pulse(src, t, opts = {}) {
    const items = this.events(src).items;
    return pulse(t, items, opts.unit === 'beats' ? this.beats : null, opts);
  }
  osc(t, opts = {}) { return osc(t, this.beats, opts); }

  // ------------------------------------------------------------------ words / voices / meaning
  _lyrics() {
    if (this._lyr !== undefined) return this._lyr;
    const doc = this._get('lyrics');
    const lines = sortedByT(doc && Array.isArray(doc.lines) ? doc.lines : []);
    const words = new Map();
    for (const w of doc && Array.isArray(doc.words) ? doc.words : []) {
      if (!words.has(w.line_id)) words.set(w.line_id, []);
      words.get(w.line_id).push(w);
    }
    for (const [k, v] of words) words.set(k, sortedByT(v));
    this._lyr = { doc, lines, words };
    return this._lyr;
  }

  /** {line, word, progress, word_progress}; line joined with singer (character ids) and voice_ids. */
  lyricAt(t) {
    const L = this._lyrics();
    const r = eventAt(L.lines, t);
    if (r === null) return { line: null, word: null, progress: null, word_progress: null };
    const sung = this.events('singing').items.filter((s) => s.line_id === r.item.id);
    const order = sung.map((s, k) => [s, k]).sort((a, b) => ((a[0].lead_backing === 'lead' ? 0 : 1) -
      (b[0].lead_backing === 'lead' ? 0 : 1)) || (a[1] - b[1])).map((p) => p[0]);
    const uniq = (xs) => [...new Set(xs.filter((x) => x != null))];
    const line = { ...r.item, singer: uniq(order.map((s) => s.character_id)), voice_ids: uniq(order.map((s) => s.voice_id)) };
    const wr = eventAt(L.words.get(r.item.id) || [], t);
    return { line, word: wr ? wr.item : null, progress: r.progress, word_progress: wr ? wr.progress : null };
  }

  _vocalChannels() {
    const ch = {};
    for (const id of ['vocal.voiced', 'vocal.midi', 'vocal.f0_hz', 'vocal.conf', 'vocal.pitch01']) {
      const c = this._curveOrNull(id);
      if (c) ch[id] = c.values;
    }
    return ch;
  }

  vocalAt(t) {
    const rate = this._chan.has('vocal.midi') ? +(this._chan.get('vocal.midi').rate_hz || CURVE_RATE_HZ) : CURVE_RATE_HZ;
    return vocalAt(t, this._vocalChannels(), rate, this.events('vocal_phrases').items, this.events('notes.vocals').items);
  }

  _mouthOpen(voice, t) {
    const id = voice && this._chan.has(`vocal.mouth_open.${voice}`) ? `vocal.mouth_open.${voice}` : 'vocal.mouth_open';
    const c = this._curveOrNull(id);
    return c ? curveAt(c.values, t, c.rate, 'max') : 0;
  }

  singerAt(t) { return singerAt(t, this.events('singing').items, (v, tt) => this._mouthOpen(v, tt)); }

  meaningAt(t) {
    const sec = eventAt(this.events('sections').items, t);
    const M = this._get('meaning');
    const globalDoNot = M && Array.isArray(M.do_not) ? M.do_not : [];
    const out = {
      section_id: null, meaning: null, feel: null, emotion: null, palette_hint: [], movement_hint: null, camera_hint: null,
      characters_present: [], do_not: [...new Set(globalDoNot)], provenance: null, status: M ? (M.status ?? null) : null,
      field_sources: {},
    };
    if (sec === null) return out;
    out.section_id = sec.item.id ?? null;
    const secs = M && Array.isArray(M.sections) ? M.sections : [];
    const e = secs.find((s) => s.section_id === out.section_id) ||
      secs.find((s) => s.t0 != null && s.t1 != null && +s.t0 <= t && t < +s.t1) || null;
    if (e === null) return out;
    out.meaning = e.meaning ?? null;
    out.feel = e.feel ?? null;
    out.emotion = e.emotion ?? null;
    out.palette_hint = Array.isArray(e.palette_hint) ? [...e.palette_hint] : [];
    out.movement_hint = e.movement_hint ?? null;
    out.camera_hint = e.camera_hint ?? null;
    out.characters_present = Array.isArray(e.characters_present) ? [...e.characters_present] : [];
    out.do_not = [...new Set([...globalDoNot, ...(Array.isArray(e.do_not) ? e.do_not : [])])];
    out.provenance = e.provenance ?? null;
    // D54: which fields of this section are the user's and which a draft's (meaning.json sections[].field_sources)
    out.field_sources = e.field_sources && typeof e.field_sources === 'object' ? { ...e.field_sources } : {};
    return out;
  }

  // ------------------------------------------------------------------ spectrum
  _spectrum() {
    const f = this.index.files.spectrum128;
    if (!f) return null;
    const buf = this._get('curves:spectrum128');
    if (buf == null) return null;
    return { data: new Uint8Array(buf), n: f.n_frames, k: f.n_channels || 128, rate: f.rate_hz || CURVE_RATE_HZ };
  }

  /** Uint8Array(128): the nearest spectrum row (clamped); u8/255 = viz band value. */
  spectrumAt(t) {
    num(t);
    const S = this._spectrum();
    if (!S || S.n === 0) return new Uint8Array(S ? S.k : 128);
    const row = nearest(S.n, t * S.rate);
    return S.data.slice(row * S.k, (row + 1) * S.k);
  }

  /** Uint8Array(k * 128), k = round(100 s) + 1 rows ending at the nearest row of t, oldest first; zero rows outside. */
  spectrumWindow(t, s) {
    const S = this._spectrum();
    const K = S ? S.k : 128;
    const rows = spectrumRows(t, s, S ? S.n : 0, S ? S.rate : CURVE_RATE_HZ);
    const out = new Uint8Array(rows.length * K);
    rows.forEach((r, j) => { if (r !== null) out.set(S.data.subarray(r * K, (r + 1) * K), j * K); });
    return out;
  }

  // ------------------------------------------------------------------ textures
  /** Whole-song curves wrapped into rows of `width` texels (r32f Float32Array or r8 Uint8Array). */
  textureData(ids, { layout = 'wrap', width = 1024, format = 'r32f' } = {}) {
    if (layout !== 'wrap') throw new RangeError(`mvh: unknown texture layout '${layout}'`);
    if (format !== 'r32f' && format !== 'r8') throw new RangeError(`mvh: unknown texture format '${format}'`);
    if (!Number.isInteger(width) || width < 1) throw new RangeError('mvh: width must be a positive integer');
    const list = Array.isArray(ids) ? ids : [ids];
    const chans = list.map((id) => {
      const c = this.curve(id);
      if (!c.nanAware) return c.values;
      const v = new Float32Array(c.values.length);
      for (let i = 0; i < v.length; i++) { const y = nanAwareAt(c.values, i); v[i] = Number.isNaN(y) ? 0 : y; }
      return v;
    });
    const packed = packTexture(chans, width);
    const lay = packed.layout.map((l, k) => {
      const rate = this.curve(list[k]).rate;
      return { id: list[k], row0: l.row0, rows: l.rows, n: l.n, rate, width, info: [rate, l.n, width, l.row0] };
    });
    let data = packed.data;
    if (format === 'r8') {
      const u = new Uint8Array(data.length);
      for (let i = 0; i < data.length; i++) { const y = data[i] * 255; u[i] = Number.isNaN(y) ? 0 : Math.round(clamp(y, 0, 255)); }
      data = u;
    }
    return { data, width, height: packed.height, format, layout: lay };
  }

  // ------------------------------------------------------------------ vizState
  /** The viz/js/audio.js AudioEngine fields at the frame containing t, from offline data. The frame rule is
   *  mandatory (`fr`, or the song-wide `load(base, {fr})`): onsets, the beat pulse and frame-pooled hit values
   *  are computed per video frame, so a 24/30 fps renderer silently given 60 fps frames would lose onsets.
   *  Pass `{fps: 60}` for the viz scenes. */
  vizState(t, fr = null) {
    num(t);
    if (fr == null) fr = this.defaultFr;
    if (fr == null) throw new TypeError("vizState(t, fr) needs a frame rule fr, e.g. {fps: 30} (or pass fr to load()): onsets and pulses are computed per video frame");
    const r = frameRule(fr);
    const n = frameOf(t, r);
    const tc = frameCentre(n, r);
    const fv = (id) => { const c = this._curveOrNull(id); return c ? c.frame(n, r) : 0; };
    const st = new VizState();
    st.t = tc;
    st.frame = n;

    // spectrum: bands / bandsRaw / peaks / bandBytes
    const S = this._spectrum();
    const NB = VIZ.NUM_BANDS;
    const row = this.spectrumAt(tc);
    st.bands = new Float32Array(NB);
    st.peaks = new Float32Array(NB);
    for (let k = 0; k < NB; k++) st.bands[k] = (row[k] || 0) / 255;
    st.bandsRaw = Float32Array.from(st.bands);
    if (S && S.n > 0) {
      const rows = spectrumRows(tc, VIZ.PEAK_WINDOW_S, S.n, S.rate);
      const pk = new Float64Array(NB);
      for (let k = 0; k < NB; k++) pk[k] = st.bands[k];
      for (const j of rows) {
        if (j === null) continue;
        const fall = VIZ.PEAK_FALL_PER_S * Math.max(0, tc - j / S.rate);
        for (let k = 0; k < NB; k++) { const y = S.data[j * S.k + k] / 255 - fall; if (y > pk[k]) pk[k] = y; }
      }
      for (let k = 0; k < NB; k++) st.peaks[k] = clamp(pk[k], 0, 1);
    }
    st.bandBytes = new Uint8Array(NB * 4);
    for (let k = 0; k < NB; k++) {
      const b = row[k] || 0;
      st.bandBytes[4 * k] = b; st.bandBytes[4 * k + 1] = b; st.bandBytes[4 * k + 2] = b; st.bandBytes[4 * k + 3] = 255;
    }
    st.wave = new Float32Array(VIZ.WAVE_LEN);
    st.waveBytes = new Uint8Array(VIZ.WAVE_LEN).fill(128);

    // levels and hit envelopes (frame values under each channel's policy)
    st.bass = fv('bands.bass_viz'); st.mid = fv('bands.mid_viz'); st.high = fv('bands.high_viz'); st.level = fv('bands.level');
    st.kick = clamp(fv('hits.kick'), 0, 1);
    st.kickRaw = clamp(fv('hits.kick_raw'), 0, 1);
    st.midHit = clamp(fv('hits.mid'), 0, 1);
    st.highHit = clamp(fv('hits.high'), 0, 1);
    st.bpm = fv('tempo.bpm');

    // onsets -> beat / pulses (decays as in audio.js; items in the current frame have already fired)
    const fired = (items) => firstTrue(items.length, (i) => frameOf(+items[i].t, r) > n) - 1;
    const str = (it) => clamp(it.strength == null ? 1 : +it.strength, 0, 1);
    const bass = this.events('onsets.bass').items;
    const kb = fired(bass);
    st.beatCount = kb + 1;
    st.onset = kb >= 0 && frameOf(+bass[kb].t, r) === n;
    st.beatPulse = kb >= 0 ? Math.exp(-Math.max(0, tc - +bass[kb].t) / VIZ.PULSE_DECAY_S) : 0;
    let beat = 0;
    for (let i = kb; i >= 0; i--) {
      const age = Math.max(0, tc - +bass[i].t);
      if (age > VIZ.BEAT_WINDOW_S) break;
      const amp = VIZ.BEAT_STRENGTH_MIN + (1 - VIZ.BEAT_STRENGTH_MIN) * str(bass[i]);
      beat = Math.max(beat, amp * Math.exp(-age / VIZ.BEAT_DECAY_S));
    }
    st.beat = beat;
    st.recentBeats = new Float32Array(VIZ.RECENT_BEATS).fill(VIZ.RECENT_BEAT_EMPTY);
    st.recentBeatAmp = new Float32Array(VIZ.RECENT_BEATS);
    const kick = this._curveOrNull('hits.kick'), kickRaw = this._curveOrNull('hits.kick_raw');
    for (let j = 0; j < VIZ.RECENT_BEATS && kb - j >= 0; j++) {
      const it = bass[kb - j];
      const tb = +it.t;
      const amp = VIZ.BEAT_STRENGTH_MIN + (1 - VIZ.BEAT_STRENGTH_MIN) * str(it);
      const a = Math.max(kickRaw ? kickRaw.at(tb) : 0, kick ? kick.at(tb) : 0, amp * 0.6);
      st.recentBeats[VIZ.RECENT_BEATS - 1 - j] = tb;
      st.recentBeatAmp[VIZ.RECENT_BEATS - 1 - j] = clamp(a, 0, 1);
    }
    for (const [band, pulseKey, onsetKey] of [['mid', 'midPulse', 'midOnset'], ['high', 'highPulse', 'highOnset']]) {
      const items = this.events(`onsets.${band}`).items;
      const k = fired(items);
      st[onsetKey] = k >= 0 && frameOf(+items[k].t, r) === n;
      if (k < 0) { st[pulseKey] = 0; continue; }
      const amp = VIZ.PULSE_STRENGTH_MIN + (1 - VIZ.PULSE_STRENGTH_MIN) * str(items[k]);
      st[pulseKey] = amp * Math.exp(-Math.max(0, tc - +items[k].t) / VIZ.PULSE_DECAY_S);
    }

    // engine settings, as audio.js defaults
    st.hitRelease = VIZ.HIT_RELEASE; st.hitThreshold = VIZ.HIT_THRESHOLD; st.kickGateDb = VIZ.KICK_GATE_DB;
    st.hitFloor = VIZ.HIT_FLOOR; st.refFloor = VIZ.REF_FLOOR; st.rearmDb = VIZ.REARM_DB;
    st.gain = 1; st.sensitivity = 1; st.drive = { bass: 1, mid: 1, high: 1 }; st.monitorVolume = 0.6;
    st.silentFor = 0; st.active = true; st.sourceType = 'offline'; st.sourceLabel = 'mv-harness';
    st.ranges = vizRanges();
    return st;
  }
}

// ============================================================================================ entry points
/** Load a song folder: base is a URL (browser) or a folder path (Node). Anything not in `include` loads lazily. */
export async function load(base, { fetch = undefined, include = [], fr = null } = {}) {
  const src = new Source(base, fetch);
  const [mText, iText] = await Promise.all([src.read('manifest.json', 'text'), src.read('curves/index.json', 'text')]);
  const song = new Song(src, mText == null ? null : parseJson(mText, 'manifest.json'),
    iText == null ? null : parseJson(iText, 'curves/index.json'));
  song.defaultFr = fr;
  if (include && (Array.isArray(include) ? include.length : true)) await song.ensure(include);
  return song;
}

/** Node only: open a song folder synchronously (lazy parts are read on first use). */
export function loadSync(path, { fr = null } = {}) {
  const src = new Source(path);
  if (!src.canSync) throw new Error('mvh: loadSync needs Node (fs); use await load(base) in browsers');
  const m = src.readSync('manifest.json', 'text');
  const i = src.readSync('curves/index.json', 'text');
  const song = new Song(src, m == null ? null : parseJson(m, 'manifest.json'), i == null ? null : parseJson(i, 'curves/index.json'));
  song.defaultFr = fr;
  return song;
}

export default { load, loadSync, frameOf, timeOf, frameCount, frameCentre, frameWindow, Song, VIZ };
