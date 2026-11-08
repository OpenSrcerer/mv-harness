// Runs the REAL viz/js/audio.js AudioEngine under Node with a stub analyser and prints JSON for the Python parity test.
// usage: node viz_parity.cjs <audio.js> <input.json>
//   input: {sr, frames: [[dB per bin (N/2)], ...], e: [hit envelope inputs], dt}
//   output: {bLo, bHi, bC, tilt, ranges, kickBins, frames: [{bandsRaw, eKick}], hit: {raw, env}, flux: [...]}
'use strict';
const fs = require('fs');
const vm = require('vm');
const [, , audioJs, inputJson] = process.argv;
const input = JSON.parse(fs.readFileSync(inputJson, 'utf8'));
const sandbox = { window: {}, Math, Float32Array, Uint8Array, Object, Array, console };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(audioJs, 'utf8'), sandbox);
const AE = sandbox.window.VIZ.AudioEngine;

const out = {};
// ---------------------------------------------------------------- band map
const eng = new AE();
eng.ctx = { sampleRate: input.sr };
eng._computeBandMap();
out.bLo = Array.from(eng._bLo); out.bHi = Array.from(eng._bHi); out.bC = Array.from(eng._bC); out.tilt = Array.from(eng._tilt);
out.ranges = eng._ranges; out.kickBins = eng._kickBins;

// ---------------------------------------------------------------- per-frame raw bands + eKick through update()
out.frames = [];
for (const fr of input.frames) {
  const e2 = new AE();
  e2.ctx = { sampleRate: input.sr };
  e2._computeBandMap();
  e2.active = true;
  e2.analyser = {
    getFloatFrequencyData: (a) => { for (let i = 0; i < a.length; i++) a[i] = fr[i]; },
    getFloatTimeDomainData: (a) => { a.fill(0); },
  };
  e2._fft = new Float32Array(fr.length);
  e2._time = new Float32Array(2048);
  e2.update(0.01, 1.0);
  out.frames.push({ bandsRaw: Array.from(e2.bandsRaw), eKick: e2._hit.bass.fast });
}

// ---------------------------------------------------------------- _hitEnvelope on a series (causal viz reference)
const e3 = new AE();
const st = { fast: undefined, slow: undefined, ref: 0.2, cur: 0, raw: 0 };
let prev = 0;
const raw = []; const env = [];
for (const v of input.e) {
  prev = e3._hitEnvelope(st, v, prev, input.dt, input.gateDb === null ? undefined : input.gateDb);
  raw.push(st.raw); env.push(prev);
}
out.hit = { raw, env };

// ---------------------------------------------------------------- _flux on consecutive normalised band frames
out.flux = [];
const rng = eng._ranges.flux;
for (let i = 1; i < input.norm.length; i++) out.flux.push(e3._flux(input.norm[i], input.norm[i - 1], rng));
process.stdout.write(JSON.stringify(out));
