// lib/mvh.glsl index math, run as JavaScript: the GLSL functions are transpiled with a few regexes (they are written in
// a small subset: typed declarations, int()/float()/ivec2() casts, clamp/min/floor, texelFetch) and checked against
// curve.at / textureSample.  Run: node --test tests/unit/lib/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import * as mvh from '../../../src/mvh/assets/mvh.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '..', '..', '..');
const SRC = readFileSync(path.join(REPO, 'src', 'mvh', 'assets', 'mvh.glsl'), 'utf8');
const G = JSON.parse(readFileSync(path.join(REPO, 'docs', 'contract', 'golden-vectors.json'), 'utf8'));

function functions(src) {
  const code = src.replace(/\/\/[^\n]*/g, '');
  const out = {};
  const head = /\b(float|int|void)\s+(\w+)\s*\(([^)]*)\)\s*\{/g;
  let m;
  while ((m = head.exec(code))) {
    let depth = 1, i = head.lastIndex;
    while (depth > 0) { if (code[i] === '{') depth++; else if (code[i] === '}') depth--; i++; }
    out[m[2]] = { ret: m[1], params: m[3], body: code.slice(head.lastIndex, i - 1) };
  }
  return out;
}

const TYPES = '(?:float|int|ivec2|vec2|vec3|vec4|bool)';
function transpile(src) {
  const fns = functions(src);
  assert.equal(fns.mvhDivI.body.trim(), 'return a / b;', 'mvhDivI must stay a plain integer division');
  assert.match(fns.mvhDivI.params, /int a,\s*int b/);
  let js = '';
  for (const [name, f] of Object.entries(fns)) {
    if (name === 'mvhDivI') continue;                       // integer division: provided by the shim (truncation)
    const params = f.params.split(',').map((p) => p.trim().split(/\s+/).pop()).join(', ');
    const body = f.body
      .replace(new RegExp(`\\b${TYPES}\\s+(\\w+)\\s*=`, 'g'), 'let $1 =')
      .replace(/\bint\(/g, '_int(').replace(/\bfloat\(/g, '_float(').replace(/\bivec2\(/g, '_ivec2(');
    assert.doesNotMatch(body, new RegExp(`\\b${TYPES}\\b`), `${name}: unsupported GLSL construct left after transpiling`);
    js += `function ${name}(${params}) {${body}}\n`;
  }
  const shim = {
    clamp: (x, a, b) => Math.min(Math.max(x, a), b), min: Math.min, max: Math.max, floor: Math.floor,
    _int: Math.trunc, _float: (x) => x, _ivec2: (x, y) => ({ x, y }), mvhDivI: (a, b) => Math.trunc(a / b),
    texelFetch: (tex, p, lod) => {
      assert.equal(lod, 0);
      assert.ok(Number.isInteger(p.x) && Number.isInteger(p.y), `non-integer texel ${p.x},${p.y}`);
      assert.ok(p.x >= 0 && p.x < tex.width && p.y >= 0 && p.y < tex.height, `texel out of range ${p.x},${p.y}`);
      return { r: tex.norm * tex.data[p.y * tex.width + p.x] };
    },
  };
  const f = new Function(...Object.keys(shim), `${js}\nreturn { mvhTexel, mvhCurve, mvhCurveHold };`);
  return f(...Object.values(shim));
}

const GL = transpile(SRC);
const vec4 = (a) => ({ x: a[0], y: a[1], z: a[2], w: a[3] });
const tex = (td) => ({ data: td.data, width: td.width, height: td.height, norm: td.data instanceof Uint8Array ? 1 / 255 : 1 });

test('mvh.glsl declares the contract signature', () => {
  assert.match(SRC, /float mvhCurve\(sampler2D tex, float t, vec4 info\)/);
  assert.match(SRC, /texelFetch/);
  assert.doesNotMatch(SRC.replace(/\/\/[^\n]*/g, ''), /#version/);
});

test('golden texture cases: mvhCurve equals textureSample and curve.at', () => {
  const T = G.texture;
  const chans = [
    Array.from({ length: T.channels.a.n }, (_, i) => Number((Math.sin(i * 0.013) * 0.5 + 0.5).toFixed(6))),
    Array.from({ length: T.channels.b.n }, (_, i) => Number(((i % 100) / 100).toFixed(6))),
  ];
  const { data, height, layout } = mvh.packTexture(chans, T.width);
  const tx = { data, width: T.width, height, norm: 1 };
  for (const [c, t, ts, ca] of T.sample) {
    const l = layout[c];
    const v = GL.mvhCurve(tx, t, vec4([100, l.n, l.width, l.row0]));
    assert.ok(Math.abs(v - ts) <= 1e-6, `c${c} t${t}: ${v} != ${ts}`);
    assert.ok(Math.abs(v - ca) <= 1e-6, `c${c} t${t}: ${v} != curve.at ${ca}`);
  }
});

function grid(n, rate) {
  const dur = n / rate;
  const ts = [-1, -0.001, 0, dur - 1 / rate, dur, dur + 3];
  for (let k = 0; k <= 997; k++) ts.push(-0.2 + (dur + 0.4) * k / 997);
  return ts;
}

test('wrapped sampling equals curve.at for every width, rate and row wrap (linear and hold)', () => {
  for (const rate of [100, 1]) {
    for (const n of [1, 2, 7, 999, 1024, 1025, 2500]) {
      const v = Float32Array.from({ length: n }, (_, i) => Math.sin(i * 0.37) * 3 + (i % 11) * 0.1);
      const w = Float32Array.from({ length: 3 }, (_, i) => i);   // a second channel, so row0 > 0 for the third
      for (const width of [1, 7, 100, 1024, 4096]) {
        const { data, height, layout } = mvh.packTexture([w, v, v], width);
        const tx = { data, width, height, norm: 1 };
        for (const c of [1, 2]) {
          const l = layout[c];
          const info = vec4([rate, l.n, l.width, l.row0]);
          const ts = grid(n, rate);
          for (let i = 0; i < n; i += Math.max(1, Math.floor(n / 50))) ts.push(i / rate, (i + 0.5) / rate + 1e-7, (i + 0.999) / rate);
          for (let q = l.width; q < n; q += l.width) ts.push((q - 0.5) / rate, (q - 1) / rate, q / rate);   // row wraps
          for (const t of ts) {
            const a = GL.mvhCurve(tx, t, info), e = mvh.curveAt(v, t, rate, 'linear');
            assert.ok(Math.abs(a - e) <= 1e-6 * (1 + Math.abs(e)), `linear n${n} w${width} r${rate} t${t}: ${a} != ${e}`);
            const x = t * rate;
            if (Math.abs(x - Math.floor(x) - 0.5) > 1e-6) {
              const h = GL.mvhCurveHold(tx, t, info), eh = mvh.curveAt(v, t, rate, 'hold');
              assert.equal(h, eh, `hold n${n} w${width} r${rate} t${t}`);
            }
          }
        }
      }
    }
  }
});

test('float32 time input (GPU uniforms) stays within float32 resolution of curve.at', () => {
  const n = 30000;   // a 5-minute song at 100 Hz
  const v = Float32Array.from({ length: n }, (_, i) => 0.5 + 0.5 * Math.sin(i * 0.01));
  const { data, height, layout } = mvh.packTexture([v], 1024);
  const tx = { data, width: 1024, height, norm: 1 };
  const info = vec4([100, n, 1024, layout[0].row0]);
  for (let k = 0; k < 2000; k++) {
    const t = Math.fround(k * 0.15013);
    const a = GL.mvhCurve(tx, t, info), e = mvh.curveAt(v, t, 100);
    assert.ok(Math.abs(a - e) < 1e-6, `t${t}`);
  }
});

test('the transpiled check is not vacuous: an off-by-one row index is caught', () => {
  const bad = transpile(SRC.replace('int row = int(info.w) + q;', 'int row = int(info.w) + q + 1;'));
  const v = Float32Array.from({ length: 50 }, (_, i) => i);
  const { data, height, layout } = mvh.packTexture([v, v], 10);
  const tx = { data, width: 10, height, norm: 1 };
  const info = vec4([100, 50, 10, layout[0].row0]);
  assert.notEqual(bad.mvhCurve(tx, 0.123, info), mvh.curveAt(v, 0.123));
  assert.equal(GL.mvhCurve(tx, 0.123, info), mvh.curveAt(v, 0.123));
});

test('r8 textures: the sampler reads value/255 of the packed bytes', () => {
  const n = 1500;
  const v = Float32Array.from({ length: n }, (_, i) => 0.5 + 0.5 * Math.cos(i * 0.05));
  const { data, height, layout } = mvh.packTexture([v], 512);
  const u = Uint8Array.from(data, (y) => Math.round(Math.min(Math.max(y * 255, 0), 255)));
  const tx = tex({ data: u, width: 512, height });
  const q = Array.from(v, (y) => Math.round(y * 255) / 255);
  const info = vec4([100, n, 512, layout[0].row0]);
  for (let k = 0; k < 600; k++) {
    const t = -0.1 + k * 0.0263;
    assert.ok(Math.abs(GL.mvhCurve(tx, t, info) - mvh.curveAt(q, t)) < 1e-9);
  }
});
