// JS twin of mvh_sample.py (zero deps; Node or browser). Same frame rules, used to check parity.
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

export function loadSync(dir) {
  const man = JSON.parse(readFileSync(join(dir, "manifest.json"), "utf8"));
  const curves = {};
  for (const c of man.curves) {
    const buf = readFileSync(join(dir, c.path));
    const all = new Float32Array(buf.buffer, buf.byteOffset, buf.byteLength / 4);
    const [rows, cols] = c.shape;
    c.channels.forEach((ch, j) => {
      const v = new Float32Array(rows);
      for (let i = 0; i < rows; i++) v[i] = all[i * cols + j];
      curves[ch.name] = { v, rate: c.rate_hz, t0: c.t0_s, mode: ch.resample || "linear" };
    });
  }
  return { man, curves };
}
const lin = (c, t) => {
  const x = (t - c.t0) * c.rate, n = c.v.length;
  if (x <= 0) return c.v[0];
  if (x >= n - 1) return c.v[n - 1];
  const i = Math.floor(x), f = x - i;
  return c.v[i] * (1 - f) + c.v[i + 1] * f;
};
export function frameValue(c, n, fps) {
  const a = n / fps, b = (n + 1) / fps;
  if (c.mode === "linear") return lin(c, a);
  const i0 = Math.max(0, Math.ceil((a - c.t0) * c.rate - 1e-9)), i1 = Math.min(c.v.length, Math.ceil((b - c.t0) * c.rate - 1e-9));
  if (c.mode === "mean") {
    if (i1 <= i0) return lin(c, (a + b) / 2);
    let s = 0; for (let i = i0; i < i1; i++) s += c.v[i]; return s / (i1 - i0);
  }
  if (c.mode === "max") {
    let m = lin(c, a); for (let i = i0; i < i1; i++) m = Math.max(m, c.v[i]); return m;
  }
  throw new Error(c.mode);
}
if (process.argv[2]) {
  const [dir, fpsS] = process.argv.slice(2), fps = Number(fpsS);
  const { man, curves } = loadSync(dir);
  const nframes = Math.ceil(man.source.duration_s * fps);
  const py = JSON.parse(readFileSync(join(dir, `py_${Math.trunc(fps)}.json`), "utf8"));
  let worst = 0;
  for (const name of Object.keys(py)) for (let n = 0; n < nframes; n++) worst = Math.max(worst, Math.abs(frameValue(curves[name], n, fps) - py[name][n]));
  console.log(`frames ${nframes}, max |js - py| = ${worst.toExponential(2)}`);
}
