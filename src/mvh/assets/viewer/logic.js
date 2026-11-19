/* mv-harness viewer: pure logic (no DOM). Unit-tested under node (tests/unit/viewer/logic.test.mjs). */
const MVHLOGIC = (function () {
  'use strict';
  const r3 = (x) => Math.round(x * 1000) / 1000;
  const r6 = (x) => Math.round(x * 1e6) / 1e6;
  const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
  const SEC_TOL = 0.08; // boundary edits closer than this refer to the same boundary

  // ------------------------------------------------------------------ structure.boundaries / labels (anchored by time, D27)
  function cloneList(l) { return (l || []).map((e) => Object.assign({}, e)); }

  /** Move the boundary currently displayed at fromT to toT. */
  function moveBoundary(list, fromT, toT, tol = SEC_TOL) {
    const out = cloneList(list);
    toT = r3(toT);
    let i = out.findIndex((e) => e.action === 'add' && Math.abs(e.t - fromT) < tol);
    if (i >= 0) { out[i].t = toT; return out; }
    i = out.findIndex((e) => e.action === 'move' && Math.abs(e.to_t - fromT) < tol);
    if (i >= 0) {
      if (Math.abs(out[i].t - toT) < 0.002) out.splice(i, 1); else out[i].to_t = toT;
      return out;
    }
    if (Math.abs(fromT - toT) < 0.002) return out;
    out.push({ action: 'move', t: r3(fromT), to_t: toT });
    return out;
  }
  function addBoundary(list, t, tol = SEC_TOL) {
    const out = cloneList(list);
    const i = out.findIndex((e) => e.action === 'remove' && Math.abs(e.t - t) < tol);
    if (i >= 0) { out.splice(i, 1); return out; }
    if (out.some((e) => e.action === 'add' && Math.abs(e.t - t) < tol)) return out;
    out.push({ action: 'add', t: r3(t) });
    return out;
  }
  function removeBoundary(list, t, tol = SEC_TOL) {
    const out = cloneList(list);
    let i = out.findIndex((e) => e.action === 'add' && Math.abs(e.t - t) < tol);
    if (i >= 0) { out.splice(i, 1); return out; }
    i = out.findIndex((e) => e.action === 'move' && Math.abs(e.to_t - t) < tol);
    if (i >= 0) { out[i] = { action: 'remove', t: out[i].t }; return out; }
    if (out.some((e) => e.action === 'remove' && Math.abs(e.t - t) < tol)) return out;
    out.push({ action: 'remove', t: r3(t) });
    return out;
  }
  /** Label of the section [t0, t1): the anchor is the section middle (stable when boundaries move a little). */
  function setSectionLabel(labels, t0, t1, label) {
    const out = cloneList(labels).filter((e) => !(e.t >= t0 - 1e-6 && e.t < t1 - 1e-6));
    if (label) out.push({ t: r3((t0 + t1) / 2), label });
    return out.sort((a, b) => a.t - b.t);
  }
  const LABEL_RE = /^[a-z][a-z-]*$/;
  function cleanLabel(s) {
    const x = String(s || '').trim().toLowerCase().replace(/[\s_]+/g, '-').replace(/[^a-z-]/g, '');
    return LABEL_RE.test(x) ? x : null;
  }

  // ------------------------------------------------------------------ lyrics
  /** New {dt} for a line shown at `shownT` when the analysis already applied `appliedDt`; want it at `wantT`. */
  function lineDt(shownT, appliedDt, wantT) {
    const base = shownT - (appliedDt || 0);
    return r3(wantT - base);
  }
  function setLineNudge(lines, id, shownT, appliedDt, wantT) {
    const out = Object.assign({}, lines || {});
    const dt = lineDt(shownT, appliedDt, wantT);
    if (Math.abs(dt) < 0.0005) delete out[id]; else out[id] = { dt };
    return out;
  }
  // ---- lyric line pins (D82): a fixed start for a line, keyed by its position in the lyric source
  /** the pin of a line in overrides.lyrics, or null */
  function linePin(lyrics, line) {
    if (!line || line.source_index == null) return null;
    return ((lyrics || {}).pins || []).find((p) => p.index === line.source_index) || null;
  }
  /** overrides.lyrics with `line` pinned at t; a pin replaces the line's nudge */
  function setLinePin(lyrics, line, t) {
    const out = Object.assign({}, lyrics || {});
    out.pins = (out.pins || []).filter((p) => p.index !== line.source_index)
      .concat([{ index: line.source_index, t: r3(Math.max(0, t)), key: line.pin_key, line: line.id }])
      .sort((a, b) => a.index - b.index);
    if (out.lines && out.lines[line.id]) { out.lines = Object.assign({}, out.lines); delete out.lines[line.id]; }
    return out;
  }
  function removeLinePin(lyrics, index) {
    const out = Object.assign({}, lyrics || {});
    out.pins = (out.pins || []).filter((p) => p.index !== index);
    if (!out.pins.length) delete out.pins;
    return out;
  }
  // ---------------------------------------------------------------------------------- bars, groups, splits (D83)
  /** the bar a line's words live in: its analysed span joined with where its words show now, [a, b] */
  function barOf(lineT, lineD, words, start, end) {
    // D84: a bar start or end set in the viewer replaces that edge of the line's span; the bar always holds its words
    let a = start != null ? start : lineT, b = end != null ? end : lineT + Math.max(0.05, lineD || 0);
    for (const w of words || []) { a = Math.min(a, w.t); b = Math.max(b, w.t + w.d); }
    return [a, b];
  }
  /** how far a bar's edges can go (D84): its start at most to its first word, its end at least to its last word's end */
  function barEdgeLimits(words) {
    let lo = Infinity, hi = -Infinity;
    for (const w of words || []) { lo = Math.min(lo, w.t); hi = Math.max(hi, w.t + w.d); }
    return { maxStart: lo, minEnd: hi };
  }
  /** the largest move <= |delta| that keeps every word inside its bar: items [{t, d, a, b}] (a, b = the bar) */
  function clampGroupDelta(items, delta) {
    let lo = -Infinity, hi = Infinity;
    for (const x of items) { lo = Math.max(lo, x.a - x.t); hi = Math.min(hi, x.b - (x.t + x.d)); }
    if (lo > hi) return 0;
    return Math.min(Math.max(delta, Math.min(0, lo)), Math.max(0, hi));
  }
  /** the word's place in its source line, from its stable reference r12w4 -> 4 (null without one) */
  function refWord(ref) {
    const m = /^r(\d+)w(\d+)$/.exec(ref || '');
    return m ? { index: +m[1], k: +m[2] } : null;
  }
  /** overrides.lyrics.splits with word positions added to / removed from the split of source line `index` */
  function editSplits(splits, index, key, add, remove) {
    const out = (splits || []).filter((s) => s.index !== index);
    const cur = (splits || []).find((s) => s.index === index);
    const at = new Set((cur && cur.at) || []);
    for (const k of add || []) if (k > 0) at.add(k);
    for (const k of remove || []) at.delete(k);
    if (at.size) out.push(Object.assign({ index, at: [...at].sort((x, y) => x - y) }, key ? { key } : {}));
    return out.sort((x, y) => x.index - y.index);
  }
  /** every override key the lyrics stage applies to a line: its bar reference, the whole source line, its id */
  function lineKeys(line) {
    const ks = [];
    if (line.ref) { ks.push(line.ref); const whole = line.ref.replace(/p\d+$/, ''); if (whole !== line.ref) ks.push(whole); }
    const old = line.legacy_id || line.id;   // an id key means the numbering before any split
    if (!ks.includes(old)) ks.push(old);
    return ks;
  }
  /** D87: the meaning note a line shows: its own (under any of its keys), else the note of the earliest repeat of it
   *  (same repeat_group) that is marked for every repeat; null without one. notes = intent.md's viewer lines
   *  {key: {note, repeats}}; lines in time order. The meaning stage resolves notes the same way. */
  function lineNoteOf(notes, lines, ln) {
    notes = notes || {};
    const k = lineKeys(ln).find((x) => notes[x]);
    if (k) return { note: notes[k].note, repeats: notes[k].repeats !== false, key: k, own: true, from: ln.id };
    if (!ln.repeat_group) return null;
    for (const r of lines || []) {
      if (r.id === ln.id || r.repeat_group !== ln.repeat_group) continue;
      const rk = lineKeys(r).find((x) => notes[x]);
      if (rk && notes[rk].repeats !== false) return { note: notes[rk].note, repeats: true, key: rk, own: false, from: r.id };
    }
    return null;
  }
  /** the id key of a word in the numbering before any split (what an old correction was written against) */
  function legacyWordKey(word, line) {
    const m = /\.(\d+)$/.exec(word.id);
    if (!line || !m) return word.id;
    const k = (line.source_word || 0) + (+m[1]);
    return (line.legacy_id || line.id) + '.' + String(k).padStart(2, '0');
  }
  /** where a word shows in the viewer. An override with an absolute start (t) is the word's final time (the lyrics
   *  stage applies it after the line nudges); otherwise the analysis time, moved with its line's pending shift, plus a
   *  pending relative shift (dt). A length (d) from the override wins. */
  function wordPos(word, ov, pending, lineDlt) {
    if (ov && ov.t != null) return { t: ov.t + (ov.dt || 0), d: ov.d != null ? ov.d : word.d };
    return { t: word.t + (lineDlt || 0) + ((pending && pending.dt) || 0), d: pending && pending.d != null ? pending.d : word.d };
  }
  function setWord(words, id, patch) {
    const out = Object.assign({}, words || {});
    const e = Object.assign({}, out[id] || {}, patch);
    for (const k of Object.keys(e)) e[k] = r3(e[k]);
    if (e.d != null && e.d < 0) e.d = 0;
    out[id] = e;
    return out;
  }

  // ------------------------------------------------------------------ rhythm grid preview (a preview only: the stage recomputes)
  function rebar(beats) {
    // numbering after rotating beat_in_bar: bar +1 at every downbeat; the first downbeat keeps the original bar
    const out = beats.map((b) => Object.assign({}, b));
    let bar = null;
    for (let i = 0; i < out.length; i++) {
      if (out[i].beat_in_bar === 1) bar = bar == null ? (out[i].bar > 0 ? out[i].bar : 1) : bar + 1;
      out[i].bar = bar == null ? 0 : bar;
    }
    return out;
  }
  function previewGrid(beats, o) {
    const dOff = (o.offset || 0) - (o.appliedOffset || 0);
    let out = beats.map((b) => Object.assign({}, b));
    if (Math.abs(dOff) > 1e-9) for (const b of out) b.t = r6(b.t + dOff);
    if (o.bpm && o.baseBpm && Math.abs(o.bpm - o.baseBpm) > 0.01 && out.length) {
      const t0 = out[0].t, dt = 60 / o.bpm, end = Math.max(o.duration || 0, out[out.length - 1].t);
      const bpb = out[0].beats_in_bar || 4;
      const first = out[0].beat_in_bar || 1;
      const g = [];
      for (let i = 0; t0 + i * dt <= end + 1e-6; i++) {
        g.push({ t: r6(t0 + i * dt), beat_index: i, beat_in_bar: ((first - 1 + i) % bpb) + 1, beats_in_bar: bpb,
          bar: 0, in_pulse: true, preview: true });
      }
      out = rebar(g);
    }
    const dPh = (o.phase || 0) - (o.appliedPhase || 0);
    if (dPh) {
      out = out.map((b) => {
        const n = b.beats_in_bar || 4;
        return Object.assign(b, { beat_in_bar: ((((b.beat_in_bar - 1 + dPh) % n) + n) % n) + 1, preview: true });
      });
      out = rebar(out);
    }
    return out;
  }
  function nearestIndex(items, t, key = 't') {
    let lo = 0, hi = items.length - 1;
    if (hi < 0) return -1;
    while (lo < hi) { const m = (lo + hi) >> 1; if (items[m][key] < t) lo = m + 1; else hi = m; }
    if (lo > 0 && Math.abs(items[lo - 1][key] - t) <= Math.abs(items[lo][key] - t)) return lo - 1;
    return lo;
  }
  /** offset change that puts the nearest beat (or downbeat) exactly at t */
  function alignOffset(beats, t, downbeat) {
    const pool = downbeat ? beats.filter((b) => b.beat_in_bar === 1) : beats;
    const i = nearestIndex(pool, t);
    return i < 0 ? 0 : r3(t - pool[i].t);
  }

  // ------------------------------------------------------------------ drawing helpers
  /** min / max / mean of a curve per pixel column over [t0, t1] (samples centred at i / rate). */
  function poolCurve(values, rate, t0, t1, w) {
    const mn = new Float32Array(w).fill(NaN), mx = new Float32Array(w).fill(NaN), mean = new Float32Array(w).fill(NaN);
    const n = values.length;
    if (!n || w <= 0) return { min: mn, max: mx, mean };
    const span = t1 - t0;
    for (let x = 0; x < w; x++) {
      const a = t0 + (x / w) * span, b = t0 + ((x + 1) / w) * span;
      let i0 = Math.ceil(a * rate - 0.5), i1 = Math.ceil(b * rate - 0.5) - 1;
      if (i1 < i0) { // fewer than one sample per pixel: interpolate
        const p = clamp((a + b) / 2 * rate, 0, n - 1);
        const k = Math.floor(p), f = p - k;
        const v = values[k] * (1 - f) + values[Math.min(n - 1, k + 1)] * f;
        mn[x] = mx[x] = mean[x] = v;
        continue;
      }
      i0 = Math.max(0, i0); i1 = Math.min(n - 1, i1);
      if (i1 < i0) continue;
      let lo = Infinity, hi = -Infinity, s = 0, c = 0;
      for (let i = i0; i <= i1; i++) {
        const v = values[i];
        if (!(v === v)) continue;
        if (v < lo) lo = v;
        if (v > hi) hi = v;
        s += v; c++;
      }
      if (c) { mn[x] = lo; mx[x] = hi; mean[x] = s / c; }
    }
    return { min: mn, max: mx, mean };
  }

  /** Build a decimation pyramid from interleaved min/max int8 (level 0 = 1 bin per base step). */
  function wavePyramid(q) {
    const levels = [q];
    let cur = q;
    while (cur.length / 2 > 64) {
      const n = Math.ceil(cur.length / 4);
      const nx = new Int8Array(n * 2);
      for (let i = 0; i < n; i++) {
        const a = i * 4;
        let lo = cur[a], hi = cur[a + 1];
        if (a + 2 < cur.length) { lo = Math.min(lo, cur[a + 2]); hi = Math.max(hi, cur[a + 3]); }
        nx[i * 2] = lo; nx[i * 2 + 1] = hi;
      }
      levels.push(nx);
      cur = nx;
    }
    return levels;
  }

  function niceStep(span, targetTicks) {
    const raw = span / Math.max(1, targetTicks);
    const steps = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600];
    for (const s of steps) if (s >= raw) return s;
    return 600;
  }
  function fmtTime(t, frac) {
    if (!(t === t)) return '--:--';
    const neg = t < 0; t = Math.abs(t);
    const m = Math.floor(t / 60), s = t - m * 60;
    const f = frac == null ? 2 : frac;
    const ss = s.toFixed(f);
    return (neg ? '-' : '') + m + ':' + (s < 10 ? '0' : '') + ss;
  }
  const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
  function midiName(m) {
    const r = Math.round(m);
    return NOTE_NAMES[((r % 12) + 12) % 12] + (Math.floor(r / 12) - 1);
  }
  /** which sections (sorted, with t,d) are affected: index of section containing t, or -1 */
  function sectionIndexAt(secs, t) {
    let r = -1;
    for (let i = 0; i < secs.length; i++) { if (secs[i].t <= t + 1e-9) r = i; else break; }
    if (r >= 0 && secs[r].d != null && t >= secs[r].t + secs[r].d + 1e-9) return -1;
    return r;
  }
  /** karaoke: index of the word being sung at t (or last started, -1 before the first) */
  function wordIndexAt(words, t) {
    let r = -1;
    for (let i = 0; i < words.length; i++) { if (words[i].t <= t) r = i; else break; }
    return r;
  }

  // ---------------------------------------------------------------------------------- meaning forms (D81)
  /** One field of a meaning form: what to show, and where the value comes from.
   *  own: the value saved in the viewer block at this level ('' / null when none)
   *  eff, src, scope: the value of the last analysis (meaning.json), its source (user | draft) and, for a section,
   *  the level the user answered at (all | type | section)
   *  level: the level of this form (song | all | type | section)
   *  -> kind: own (saved from the viewer) | yours (the user's answer at this level, from the template) |
   *     inherited (the user's answer for a wider group; shown as a hint, never saved here) | suggestion (a draft) | empty */
  function meaningField(own, eff, src, scope, level) {
    if (own != null && String(own).trim() !== '') return { value: String(own), kind: 'own' };
    if (Array.isArray(eff)) eff = eff.join(', ');
    if (eff == null || String(eff).trim() === '') return { value: '', kind: 'empty' };
    if (src === 'draft') return { value: String(eff), kind: 'suggestion' };
    if (src !== 'user') return { value: '', kind: 'empty' };
    const at = level === 'section' ? (scope || 'section') : level;
    return at === level ? { value: String(eff), kind: 'yours' } : { value: String(eff), kind: 'inherited', from: at };
  }
  /** Does saving write this field into the viewer block? The viewer's own value always (emptying it clears it), a
   *  value the user changed, and a suggestion only when it was accepted: an unreviewed draft never becomes the user's. */
  function meaningFieldWrite(state, typed, accepted) {
    const t = String(typed == null ? '' : typed).trim();
    if (state.kind === 'own') return true;
    const shown = state.kind === 'inherited' ? '' : String(state.value || '').trim();
    if (t !== shown) return true;
    return state.kind === 'suggestion' && !!accepted && t !== '';
  }

  return { barOf, barEdgeLimits, lineNoteOf, clampGroupDelta, refWord, editSplits, lineKeys, legacyWordKey, wordPos, linePin, setLinePin, removeLinePin, meaningField, meaningFieldWrite, r3, clamp, moveBoundary, addBoundary, removeBoundary, setSectionLabel, cleanLabel, lineDt, setLineNudge, setWord,
    rebar, previewGrid, nearestIndex, alignOffset, poolCurve, wavePyramid, niceStep, fmtTime, midiName, sectionIndexAt,
    wordIndexAt, NOTE_NAMES, SEC_TOL };
})();
if (typeof module !== 'undefined' && module.exports) module.exports = MVHLOGIC;
