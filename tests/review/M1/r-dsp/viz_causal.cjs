// r-dsp-m1 review helper: drive the REAL viz/js/audio.js AudioEngine.update() causally, frame by frame, from
// precomputed AnalyserNode data (per-bin dB + time-domain block), exactly as a browser at `fps` would.
// usage: node viz_causal.cjs <audio.js> <frames.bin> <out.json>
// frames.bin: int32 header [sr, nFrames, nBins, nTime, fpsNum, fpsDen], then per frame nBins float32 dB, nTime float32 samples.
'use strict';
const fs = require('fs');
const vm = require('vm');
const [, , audioJs, framesBin, outJson] = process.argv;
const sandbox = { window: {}, Math, Float32Array, Uint8Array, Object, Array, console };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(audioJs, 'utf8'), sandbox);
const AE = sandbox.window.VIZ.AudioEngine;
const buf = fs.readFileSync(framesBin);
const ab = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
const hdr = new Int32Array(ab, 0, 6);
const [sr, nFrames, nBins, nTime, fpsNum, fpsDen] = Array.from(hdr);
const dt = fpsDen / fpsNum;
const eng = new AE();
eng.ctx = { sampleRate: sr };
eng._computeBandMap();
eng.active = true;
eng._fft = new Float32Array(nBins);
eng._time = new Float32Array(nTime || 2048);  // nTime 0: no time-domain data (level reads 0)
let off = 24;
let curF = null, curT = null;
eng.analyser = {
  getFloatFrequencyData: (a) => a.set(curF),
  getFloatTimeDomainData: (a) => a.set(curT),
};
const out = { t: [], kick: [], kickRaw: [], midHit: [], highHit: [], bass: [], mid: [], high: [], level: [], gain: [],
  onset: [], midOnset: [], highOnset: [], kickHit: [], midHitEv: [], highHitEv: [] };
for (let k = 0; k < nFrames; k++) {
  curF = new Float32Array(ab, off, nBins); off += 4 * nBins;
  curT = nTime ? new Float32Array(ab, off, nTime) : new Float32Array(2048); off += 4 * nTime;
  const now = (k + 1) * dt;
  eng.update(dt, now);
  out.t.push(now);
  for (const key of ['kick', 'kickRaw', 'midHit', 'highHit', 'bass', 'mid', 'high', 'level', 'gain']) out[key].push(eng[key]);
  out.onset.push(eng.onset ? 1 : 0); out.midOnset.push(eng.midOnset ? 1 : 0); out.highOnset.push(eng.highOnset ? 1 : 0);
  // a viz "hit" is registered when _hitEnvelope disarms (sinceHit reset to 0 in this frame)
  out.kickHit.push(eng._hit.bass.sinceHit === 0 ? 1 : 0);
  out.midHitEv.push(eng._hit.mid.sinceHit === 0 ? 1 : 0);
  out.highHitEv.push(eng._hit.high.sinceHit === 0 ? 1 : 0);
}
fs.writeFileSync(outJson, JSON.stringify(out));
