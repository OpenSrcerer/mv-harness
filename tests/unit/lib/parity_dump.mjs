// Dump every lib/mvh.js helper on a song folder for the JS vs Python parity test (tests/unit/lib/test_lib_parity.py).
//   node tests/unit/lib/parity_dump.mjs <song_dir> <spec.json> <out.json>
// The Python side (dump() in test_lib_parity.py) produces the same structure with lib/mvh_load.py.
import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import * as mvh from '../../../src/mvh/assets/mvh.js';

export function plain(x) {
  if (x === null || x === undefined) return null;
  if (ArrayBuffer.isView(x)) return Array.from(x);
  if (Array.isArray(x)) return x.map(plain);
  if (typeof x === 'object') {
    const o = {};
    for (const k of Object.keys(x)) o[k] = plain(x[k]);
    return o;
  }
  if (typeof x === 'number' && !Number.isFinite(x)) return `NON-FINITE:${x}`;
  return x;
}

const ref = (it) => (it === null || it === undefined ? null : [it.t, it.id ?? null]);
const atOut = (r) => (r === null ? null : { item: ref(r.item), progress: r.progress, t_in: r.t_in, t_left: r.t_left });

/** Frames frame0-1 .. frame0+cnt; long songs: the first spanS seconds and the last quarter-span (frame_list in Python). */
function frameList(r, cnt, spanS) {
  const k = Math.ceil(spanS * r.num / r.den);
  const out = [];
  if (cnt + 2 <= k) { for (let n = r.frame0 - 1; n < r.frame0 + cnt + 1; n++) out.push(n); return out; }
  for (let n = r.frame0 - 1; n < r.frame0 + k; n++) out.push(n);
  for (let n = r.frame0 + cnt - Math.floor(k / 4); n < r.frame0 + cnt + 1; n++) out.push(n);
  return out;
}

export function dump(song, spec) {
  const T = spec.times;
  const out = { meta: { duration: song.duration, event_names: [...song.eventNames].sort(), channel_ids: [...song.channelIds].sort(),
    kick_source: song.kickSource, kicks: song.kicks().items.map((k) => [k.t, k.vel, k.conf, k.source]) } };
  out.frame_count = spec.frame_rules.map((fr) => song.frameCount(fr));
  out.curve_at = Object.fromEntries(spec.curve_ids.map((id) => [id, T.map((t) => song.curve(id).at(t))]));
  out.curve_frame = [];
  for (const fr of spec.frame_rules) {
    const r = mvh.frameRule(fr);
    for (const id of spec.frame_curve_ids) {
      const c = song.curve(id);
      const cnt = mvh.frameCount(c.n / c.rate, r);
      out.curve_frame.push(frameList(r, cnt, spec.frame_span_s).map((n) => c.frame(n, r)));
    }
  }
  out.events = {};
  for (const name of spec.event_names) {
    const e = song.events(name);
    out.events[name] = {
      exists: e.exists, n: e.items.length,
      at: T.map((t) => atOut(e.at(t))),
      next: spec.tiers.map((mt) => T.map((t) => ref(e.next(t, { minTier: mt })))),
      prev: spec.tiers.map((mt) => T.map((t) => ref(e.prev(t, { minTier: mt })))),
      between: T.map((t) => e.between(t, t + 0.37).map((it) => it.t)),
    };
  }
  out.in_frame = [];
  for (const fr of spec.frame_rules) {
    const r = mvh.frameRule(fr);
    for (const name of spec.in_frame_events) {
      const e = song.events(name);
      const cnt = song.frameCount(r);
      const rows = [];
      for (const n of frameList(r, cnt, spec.frame_span_s)) {
        const a = e.inFrame(n, r).map((it) => it.t);
        const b = name === 'cues' ? e.inFrame(n, r, { minTier: 2 }).map((it) => it.t) : [];
        rows.push([a, b]);
      }
      out.in_frame.push(rows);
    }
  }
  out.rhythm = {
    beat_pos: T.map((t) => song.beatPos(t)), beat_phase: T.map((t) => song.beatPhase(t)), bar_phase: T.map((t) => song.barPhase(t)),
    count: T.map((t) => song.count(t)),
    pulse: spec.pulse.map(([src, kw]) => T.map((t) => song.pulse(src, t, kw))),
    osc: spec.osc.map((kw) => T.map((t) => song.osc(t, { shape: kw.shape, periodBeats: kw.period_beats, phase: kw.phase }))),
  };
  out.lyric_at = T.map((t) => song.lyricAt(t));
  out.vocal_at = T.map((t) => song.vocalAt(t));
  out.singer_at = T.map((t) => song.singerAt(t));
  out.meaning_at = T.map((t) => song.meaningAt(t));
  out.spectrum_at = T.map((t) => song.spectrumAt(t));
  out.spectrum_window = spec.window_s.map((s) => T.map((t) => song.spectrumWindow(t, s)));
  out.texture = spec.texture.map((x) => song.textureData(x.ids, { width: x.width, format: x.format }));
  out.viz = [];
  for (const fr of spec.viz_rules) {
    const r = mvh.frameRule(fr);
    const cnt = song.frameCount(r);
    const rows = [];
    const step = Math.max(spec.viz_step, Math.floor(cnt / spec.viz_max));
    for (let n = r.frame0; n < r.frame0 + cnt; n += step) rows.push(song.vizState(mvh.frameCentre(n, r), fr));
    rows.push(song.vizState(spec.times[3], fr));
    out.viz.push(rows);
  }
  out.viz_default = T.filter((_, k) => k % 7 === 0).map((t) => song.vizState(t, { fps: 60 }));
  return plain(out);
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  const [songDir, specPath, outPath] = process.argv.slice(2);
  const spec = JSON.parse(readFileSync(specPath, 'utf8'));
  const song = mvh.loadSync(songDir);
  writeFileSync(outPath, JSON.stringify(dump(song, spec)), 'utf8');
}
