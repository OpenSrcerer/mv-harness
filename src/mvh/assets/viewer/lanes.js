/* Lanes. Each lane: {id, title, h, draw(c, w, h, lane), buildHead?, onDblClick?}; draw pushes pointer hit rectangles to lane.hits. */
const LANES = [];
const FONT = '11px system-ui, "Segoe UI", sans-serif';
const FONT_S = '10px system-ui, "Segoe UI", sans-serif';
const MONO = '10px ui-monospace, Consolas, monospace';
const _maxD = new WeakMap();

function visible(list, t0, t1) {
  // items sorted by t; segments may be long: back up by the longest duration
  let md = _maxD.get(list);
  if (md == null) { md = 0; for (const it of list) if (it.d > md) md = it.d; _maxD.set(list, md); }
  let lo = 0, hi = list.length;
  const key = t0 - md;
  while (lo < hi) { const m = (lo + hi) >> 1; if (list[m].t < key) lo = m + 1; else hi = m; }
  const out = [];
  for (let i = lo; i < list.length; i++) {
    const it = list[i];
    if (it.t > t1) break;
    if (it.t + (it.d || 0) >= t0) out.push(it);
  }
  return out;
}
function fitText(c, text, maxW) {
  text = String(text == null ? '' : text);
  if (maxW <= 6) return '';
  if (c.measureText(text).width <= maxW) return text;
  let lo = 0, hi = text.length;
  while (lo < hi) { const m = (lo + hi + 1) >> 1; if (c.measureText(text.slice(0, m) + '…').width <= maxW) lo = m; else hi = m - 1; }
  return lo > 0 ? text.slice(0, lo) + '…' : '';
}
function wrapText(c, text, maxW, maxLines) {
  const words = String(text || '').split(/\s+/);
  const lines = []; let cur = '';
  for (const wd of words) {
    const t = cur ? cur + ' ' + wd : wd;
    if (c.measureText(t).width <= maxW || !cur) cur = t; else { lines.push(cur); cur = wd; if (lines.length >= maxLines) break; }
  }
  if (cur && lines.length < maxLines) lines.push(cur);
  if (lines.length === maxLines && words.join(' ').length > lines.join(' ').length) lines[maxLines - 1] = fitText(c, lines[maxLines - 1] + ' ……', maxW);
  return lines;
}
function emptyMsg(c, w, hh, msg) {
  laneBg(c, w, hh);
  c.fillStyle = T.faint; c.font = FONT; c.textBaseline = 'middle'; c.textAlign = 'left';
  c.fillText(msg, 12, Math.min(hh / 2, 24));
}
function roundRect(c, x, y, w, hh, r) {
  r = Math.min(r, w / 2, hh / 2);
  c.beginPath(); c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + hh, r); c.arcTo(x + w, y + hh, x, y + hh, r); c.arcTo(x, y + hh, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath();
}
/** draw one curve as a filled line over [y0, y0 + hh] using per-pixel min/max pooling */
function drawCurve(c, cv, y0, hh, lo, hi, colour, opts) {
  if (!cv) return;
  opts = opts || {};
  const p = L.poolCurve(cv.values, cv.rate, VW.t0, VW.t1, VW.w);
  const sc = (v) => y0 + hh - clamp((v - lo) / (hi - lo || 1), 0, 1) * hh;
  if (opts.fill !== false) {
    c.fillStyle = rgba(colour, opts.alpha == null ? 0.28 : opts.alpha);
    c.beginPath(); c.moveTo(0, y0 + hh);
    let last = 0;
    for (let x = 0; x < VW.w; x++) { const v = opts.useMax ? p.max[x] : p.mean[x]; if (v === v) { c.lineTo(x, sc(v)); last = x; } }
    c.lineTo(last, y0 + hh); c.closePath(); c.fill();
  }
  c.strokeStyle = colour; c.lineWidth = opts.lw || 1.2; c.beginPath();
  let started = false;
  for (let x = 0; x < VW.w; x++) {
    const v = opts.useMax ? p.max[x] : p.mean[x];
    if (!(v === v)) { started = false; continue; }
    if (!started) { c.moveTo(x, sc(v)); started = true; } else c.lineTo(x, sc(v));
  }
  c.stroke();
}
/** snap a time to the nearest downbeat when within 8 px (hold Alt to disable) */
function snapBar(t, ev) {
  if (ev && ev.altKey) return t;
  const d = V.model.downbeats || [];
  const i = L.nearestIndex(d, t);
  if (i < 0) return t;
  return Math.abs(t2x(d[i].t) - t2x(t)) <= 8 ? d[i].t : t;
}
function laneTitle(c, text, x, y) { c.font = FONT_S; c.fillStyle = T.faint; c.textAlign = 'left'; c.textBaseline = 'top'; c.fillText(text, x, y); }
const secOf = (t) => sectionAt(t);

// ================================================================================================ overview (whole song)
LANES.push({
  id: 'overview', global: true, h: 86,
  draw(c, w, hh, lane) {
    const dur = Math.max(1, V.model.duration);
    if (!lane.cache || lane.cache.w !== w || lane.cache.h !== hh || lane.cache.v !== (V.model.sections.length + ':' + (V.sectionsVersion || 0))) {
      const off = document.createElement('canvas');
      off.width = Math.round(w * VW.dpr); off.height = Math.round(hh * VW.dpr);
      const o = off.getContext('2d');
      o.setTransform(VW.dpr, 0, 0, VW.dpr, 0, 0);
      drawOverviewStatic(o, w, hh, dur);
      lane.cache = { cv: off, w, h: hh, v: V.model.sections.length + ':' + (V.sectionsVersion || 0) };
    }
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.drawImage(lane.cache.cv, 0, 0);
    c.setTransform(VW.dpr, 0, 0, VW.dpr, 0, 0);
    const xa = VW.t0 / dur * w, xb = VW.t1 / dur * w;
    c.fillStyle = rgba(T.accent, 0.16); c.fillRect(xa, 0, xb - xa, hh);
    c.strokeStyle = T.accent; c.lineWidth = 1.5; c.strokeRect(xa + 0.5, 0.5, Math.max(2, xb - xa - 1), hh - 1);
    const xp = V.t / dur * w;
    c.fillStyle = T.play; c.fillRect(xp - 0.5, 0, 1.5, hh);
    if (A.loop) { c.fillStyle = rgba(T.good, 0.25); c.fillRect(A.loop.a / dur * w, hh - 6, (A.loop.b - A.loop.a) / dur * w, 6); }
  },
});
function drawOverviewStatic(c, w, hh, dur) {
  c.fillStyle = T.lane; c.fillRect(0, 0, w, hh);
  const stripH = 16, wy = (hh - stripH) / 2, amp = (hh - stripH) / 2 - 2;
  const wf = V.bundle.wave;
  const cb = curve('bands.bass'), cm = curve('bands.mid'), ch = curve('bands.high');
  const pb = cb && L.poolCurve(cb.values, cb.rate, 0, dur, w), pm = cm && L.poolCurve(cm.values, cm.rate, 0, dur, w), ph = ch && L.poolCurve(ch.values, ch.rate, 0, dur, w);
  if (wf && wf.n) {
    if (!V._pyr) { V._pyr = L.wavePyramid(new Int8Array(b64bytes(wf.data).buffer)); }
    const binsPerPx = (wf.hz * dur) / w;
    let k = 0; while (k < V._pyr.length - 1 && Math.pow(2, k + 1) <= binsPerPx) k++;
    const lv = V._pyr[k], bpl = Math.pow(2, k);
    for (let x = 0; x < w; x++) {
      const i0 = Math.floor((x * binsPerPx) / bpl), i1 = Math.max(i0, Math.ceil(((x + 1) * binsPerPx) / bpl) - 1);
      let lo = 127, hi = -127;
      for (let i = i0; i <= i1 && i * 2 + 1 < lv.length; i++) { if (lv[i * 2] < lo) lo = lv[i * 2]; if (lv[i * 2 + 1] > hi) hi = lv[i * 2 + 1]; }
      if (lo > hi) continue;
      let col = T.dim;
      if (pb && pm && ph) {
        const a = pb.mean[x] || 0, b = pm.mean[x] || 0, d = ph.mean[x] || 0, s = a + b + d + 1e-6;
        const r = (hexToRgb(T.bass).map((v, j) => v * a / s + hexToRgb(T.mid)[j] * b / s + hexToRgb(T.high)[j] * d / s));
        col = `rgb(${r.map(Math.round).join(',')})`;
      }
      c.fillStyle = col;
      const y1 = wy - (hi / 127) * amp, y2 = wy - (lo / 127) * amp;
      c.fillRect(x, y1, 1, Math.max(1, y2 - y1));
    }
  } else if (cb) {
    c.fillStyle = T.dim; c.font = FONT; c.textBaseline = 'middle'; c.fillText('waveform unavailable: showing band energy', 8, 14);
    for (let x = 0; x < w; x++) { const v = (pb.mean[x] + pm.mean[x] + ph.mean[x]) / 3 || 0; c.fillStyle = T.accent; c.fillRect(x, wy - v * amp, 1, v * amp * 2); }
  }
  c.strokeStyle = T.grid; c.beginPath(); c.moveTo(0, wy + 0.5); c.lineTo(w, wy + 0.5); c.stroke();
  // section strip
  c.font = FONT_S; c.textBaseline = 'middle';
  for (const s of V.model.sections) {
    const x = s.t / dur * w, ww = Math.max(1, s.d / dur * w);
    c.fillStyle = rgba(sectionColour(s.label), 0.85); c.fillRect(x, hh - stripH, ww - 1, stripH);
    c.fillStyle = '#0b0f17'; c.textAlign = 'left';
    const lbl = fitText(c, s.id + ' ' + (s.label || ''), ww - 4);
    if (lbl) c.fillText(lbl, x + 3, hh - stripH / 2 + 0.5);
  }
  // minute marks
  c.fillStyle = T.faint; c.textBaseline = 'top';
  const st = dur > 600 ? 120 : dur > 150 ? 60 : 15;
  for (let t = st; t < dur; t += st) { c.fillRect(t / dur * w, 0, 1, 5); c.fillText(fmtTime(t, 0), t / dur * w + 3, 1); }
}

// ================================================================================================ sections
LANES.push({
  id: 'sections', title: 'Sections', sub: 'structure, EDM roles, phrases', h: 58,
  draw(c, w, hh, lane) {
    laneBg(c, w, hh);
    const secs = V.model.sections;
    if (!secs.length) return emptyMsg(c, w, hh, 'No sections (structure stage has no output).');
    c.font = FONT; c.textBaseline = 'middle';
    const bh = 34;
    for (const s of secs) {
      let t0 = s.t, t1 = s.t + s.d;
      const x0 = t2x(t0), x1 = t2x(t1);
      if (x1 < -2 || x0 > w + 2) continue;
      const col = sectionColour(s.label);
      c.fillStyle = rgba(col, 0.5); c.fillRect(x0, 2, Math.max(1, x1 - x0 - 1), bh);
      c.fillStyle = col; c.fillRect(x0, 2, Math.max(1, x1 - x0 - 1), 3);
      if (SEL.sectionId === s.id) { c.strokeStyle = T.text; c.lineWidth = 1.5; c.strokeRect(x0 + 0.5, 2.5, Math.max(1, x1 - x0 - 2), bh - 1); }
      c.fillStyle = T.text; c.textAlign = 'left';
      const txt = fitText(c, `${s.id}  ${s.occurrence_label || s.label}`, x1 - x0 - 8);
      if (txt) c.fillText(txt, Math.max(x0, 0) + 5, 17);
      c.fillStyle = T.dim; c.font = FONT_S;
      const sub = fitText(c, `bars ${s.start_bar != null ? s.start_bar : '-'}+${s.n_bars != null ? s.n_bars : '-'}  ${fmtTime(s.t, 1)}-${fmtTime(s.t + s.d, 1)}${s.conf != null ? '  conf ' + s.conf.toFixed(2) : ''}`, x1 - x0 - 8);
      if (sub) c.fillText(sub, Math.max(x0, 0) + 5, 30);
      c.font = FONT;
      lane.hits.push({ x: x0, y: 2, w: x1 - x0, h: bh, tip: () => `${s.id} ${s.occurrence_label || s.label} (group ${s.repeat_group || '-'})\n${fmtTime(s.t, 2)} - ${fmtTime(s.t + s.d, 2)}  (${s.d.toFixed(2)} s)\nbars ${s.start_bar}..${s.start_bar != null ? s.start_bar + (s.n_bars || 0) - 1 : ''}  boundary conf ${s.boundary_conf != null ? s.boundary_conf : '-'}\nlabel: ${Object.entries(s.label_probs || {}).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([k, v]) => k + ' ' + v.toFixed(2)).join(', ')}`,
        onClick: () => { selectSection(s.id); seek(s.t); } });
    }
    // boundary handles
    for (const s of secs) {
      let bt = s.t;
      if (E.dragB && Math.abs(E.dragB.from - s.t) < 1e-6) bt = E.dragB.to;
      const x = t2x(bt);
      if (x < -6 || x > w + 6) continue;
      c.fillStyle = E.dragB && Math.abs(E.dragB.from - s.t) < 1e-6 ? T.edit : (V.mode === 'edit' ? T.text : T.dim);
      c.fillRect(Math.round(x) - 1, 0, 2, bh + 4);
      if (V.mode === 'edit') {
        lane.hits.push({ x: x - 4, y: 0, w: 8, h: bh + 4, cursor: 'ew-resize', drag: true, tip: 'Drag to move boundary (double-click empty space to add; Delete to remove)',
          onDragStart: () => { E.dragB = { from: s.t, to: s.t }; SEL.boundary = s.t; }, onDrag: (t, ev) => { E.dragB.to = clamp(snapBar(t, ev), 0, V.model.duration); requestDraw('sections'); },
          onDragEnd: (t, moved) => { const d = E.dragB; E.dragB = null; if (moved) Edit.moveBoundary(d.from, d.to); else { SEL.boundary = s.t; requestDraw('sections'); } } });
      }
    }
    // EDM roles + phrases strip
    const y2 = bh + 6, rh = hh - y2 - 2;
    c.font = FONT_S;
    for (const r of visible(items('edm_roles'), VW.t0, VW.t1)) {
      const x0 = t2x(r.t), x1 = t2x(r.t + r.d);
      c.fillStyle = rgba(sectionColour(r.role), 0.7); c.fillRect(x0, y2, Math.max(1, x1 - x0 - 1), rh);
      c.fillStyle = '#0b0f17'; c.textAlign = 'left'; c.textBaseline = 'middle';
      const t = fitText(c, `${r.id} ${r.role}`, x1 - x0 - 6); if (t) c.fillText(t, x0 + 3, y2 + rh / 2 + 0.5);
      lane.hits.push({ x: x0, y: y2, w: x1 - x0, h: rh, tip: `${r.id} ${r.role} (${r.n_bars} bars), conf ${r.conf != null ? r.conf : '-'}${r.evidence ? '\n' + r.evidence.join(', ') : ''}` });
    }
    c.strokeStyle = T.faint; c.lineWidth = 1;
    for (const p of visible(items('phrases'), VW.t0, VW.t1)) {
      const x = Math.round(t2x(p.t)) + 0.5;
      c.beginPath(); c.moveTo(x, y2 + rh - 3); c.lineTo(x, y2 + rh); c.stroke();
    }
    drawPendingLabels(c, lane);
    for (const b of Edit.pendingBoundaries()) {
      const tt = b.action === 'move' ? b.to_t : b.t, x = t2x(tt);
      if (x < -4 || x > w + 4) continue;
      c.strokeStyle = b.action === 'remove' ? T.bad : T.edit; c.lineWidth = 2; c.setLineDash(b.action === 'remove' ? [2, 2] : []);
      c.beginPath(); c.moveTo(x, 0); c.lineTo(x, bh + 4); c.stroke(); c.setLineDash([]); c.lineWidth = 1;
      c.fillStyle = b.action === 'remove' ? T.bad : T.edit; c.font = 'bold 9px system-ui'; c.textAlign = 'left'; c.textBaseline = 'top'; c.fillText(b.action === 'remove' ? 'removed' : b.action === 'add' ? 'new' : 'moved', x + 3, bh - 6);
    }
  },
  onDblClick(t, hit) { if (V.mode === 'edit' && !(hit && hit.drag)) Edit.addBoundary(t); },
});
function drawPendingLabels(c, lane) {
  const labs = ((V.ovr || {}).structure || {}).labels || [];
  if (!labs.length) return;
  c.font = FONT_S; c.fillStyle = T.edit; c.textAlign = 'left';
  for (const l of labs) { const x = t2x(l.t); if (x > 0 && x < VW.w) { c.fillText('● ' + l.label, x + 3, 48); } }
}

// ================================================================================================ meaning
LANES.push({
  id: 'meaning', title: 'Meaning', sub: 'per-section feel and intent', h: 84,
  draw(c, w, hh, lane) {
    laneBg(c, w, hh);
    const M = V.model;
    if (!M.meaning) { emptyMsg(c, w, hh, 'Meaning is pending: write meaning/intent.md (or add notes in edit mode) and run mvh meaning.'); return; }
    drawSectionGrid(c, hh);
    c.textBaseline = 'top';
    for (const s of M.sections) {
      const ms = M.meaningSections.get(s.id);
      const x0 = t2x(s.t), x1 = t2x(s.t + s.d);
      if (x1 < 0 || x0 > w) continue;
      const ww = x1 - x0 - 2;
      const pal = ms && ms.palette_hint && ms.palette_hint.length ? ms.palette_hint : [sectionColour(s.label)];
      c.fillStyle = rgba(pal[0], 0.2); c.fillRect(x0 + 1, 2, ww, hh - 4);
      pal.slice(0, 5).forEach((col, i) => { c.fillStyle = col; c.fillRect(x0 + 1 + i * Math.max(3, Math.min(14, ww / 8)), 2, Math.max(3, Math.min(14, ww / 8)) - 1, 4); });
      if (!ms) { c.fillStyle = T.faint; c.font = FONT_S; c.fillText(fitText(c, 'no meaning entry', ww - 6), x0 + 5, 12); }
      else if (ww > 40) {
        c.font = 'bold 11px system-ui, sans-serif'; c.fillStyle = T.text;
        c.fillText(fitText(c, ms.feel || ms.occurrence_label || '', ww - 8), x0 + 5, 10);
        c.font = FONT_S; c.fillStyle = T.dim;
        wrapText(c, ms.meaning || '', ww - 10, 3).forEach((ln, i) => c.fillText(ln, x0 + 5, 25 + i * 12));
        let bx = x0 + 5; const by = hh - 14;
        for (const cid of ms.characters_present || []) {
          c.fillStyle = M.keyColour(cid); c.beginPath(); c.arc(bx + 4, by + 5, 4, 0, 7); c.fill();
          c.fillStyle = T.dim; c.fillText(cid, bx + 10, by); bx += 10 + c.measureText(cid).width + 6;
        }
        if ((ms.do_not || []).length) { c.fillStyle = T.bad; c.fillText('⛔ ' + ms.do_not.length, Math.max(bx, x1 - 30), by); }
        if (ms.emotion && ms.emotion.agree === false) { c.fillStyle = T.warn; c.fillText('lyric ≠ audio', Math.max(bx, x1 - 80), by - 12); }
      }
      lane.hits.push({ x: x0, y: 0, w: x1 - x0, h: hh, onClick: () => { selectSection(s.id); seek(s.t); openTab('meaning'); },
        tip: ms ? `${s.id} ${ms.occurrence_label || ''}\nfeel: ${ms.feel || '-'}\nmeaning: ${ms.meaning || '-'}\nmovement: ${ms.movement_hint || '-'}\ncamera: ${ms.camera_hint || '-'}\nsource: ${(ms.provenance || {}).source || '-'} / ${(ms.provenance || {}).status || '-'}` : `${s.id}: no meaning entry` });
    }
  },
});

// ================================================================================================ lyrics & singers
const LROW = 34;
LANES.push({
  id: 'lyrics', title: 'Lyrics & singers', sub: 'line blocks by singer; word ticks', h: () => 26 + V.model.nRows * LROW,
  buildHead(head, lane) {
    const chips = h('div', { class: 'chips', id: 'singer-chips' });
    head.append(chips);
  },
  draw(c, w, hh, lane) {
    laneBg(c, w, hh);
    const M = V.model;
    if (!M.lines.length) { emptyMsg(c, w, hh, M.lyrics && M.lyrics.instrumental ? 'Instrumental: no lyrics.' : 'No lyrics for this song (lyrics stage has no output).'); return; }
    drawSectionGrid(c, hh);
    const pxs = w / (VW.t1 - VW.t0);
    c.textBaseline = 'middle';
    const top = 4;
    for (const ln of visible(M.lines, VW.t0, VW.t1)) {
      let lt = ln.t + Edit.lineShift(ln.id), ld = Math.max(0.05, ln.d || 0.3);
      const ed = E.lineDrag && E.lineDrag.id === ln.id ? E.lineDrag : null;
      if (ed) lt = ed.t;
      const pend = Edit.pendingLine(ln.id);
      const x0 = t2x(lt), x1 = t2x(lt + ld), ww = Math.max(2, x1 - x0 - 1);
      const row = M.rowOfLine(ln), y = top + row * LROW, bh = LROW - 6;
      const key = M.lineKey.get(ln.id), col = M.keyColour(key);
      const conf = ln.conf == null ? 1 : ln.conf;
      c.fillStyle = rgba(col, 0.22 + 0.5 * clamp(conf, 0, 1));
      roundRect(c, x0, y, ww, bh, 4); c.fill();
      if (conf < 0.5) { c.save(); roundRect(c, x0, y, ww, bh, 4); c.clip(); c.strokeStyle = rgba(T.bad, 0.55); c.lineWidth = 1; for (let k = -bh; k < ww; k += 6) { c.beginPath(); c.moveTo(x0 + k, y + bh); c.lineTo(x0 + k + bh, y); c.stroke(); } c.restore(); }
      const selected = SEL.lineId === ln.id;
      if (selected || pend || ed) { c.strokeStyle = ed || pend ? T.edit : T.text; c.lineWidth = 1.5; roundRect(c, x0 + 0.5, y + 0.5, ww - 1, bh - 1, 4); c.stroke(); }
      c.fillStyle = T.text; c.font = FONT; c.textAlign = 'left';
      const hasWords = pxs > 38 && (M.wordsByLine.get(ln.id) || []).length;
      const label = fitText(c, ln.text, ww - 6);
      if (label) c.fillText(label, Math.max(x0, 0) + 4, y + (hasWords ? 9 : bh / 2));
      // words
      if (hasWords) {
        const dlt = lt - ln.t;
        c.font = FONT_S;
        for (const wd of M.wordsByLine.get(ln.id)) {
          const wp = Edit.pendingWord(wd.id);
          const wt = (wp && wp.t != null ? wp.t : wd.t) + dlt, wdd = wp && wp.d != null ? wp.d : wd.d;
          const wx0 = t2x(wt), wx1 = t2x(wt + (wdd || 0.1));
          if (wx1 < 0 || wx0 > w) continue;
          const wc = wd.conf == null ? 1 : wd.conf;
          c.fillStyle = rgba(wp ? T.edit : '#ffffff', 0.18 + 0.4 * wc);
          c.fillRect(wx0, y + 17, Math.max(1.5, wx1 - wx0 - 1), 3);
          if (wx1 - wx0 > 14) { c.fillStyle = T.dim; const t = fitText(c, wd.text, wx1 - wx0 - 2); if (t) c.fillText(t, wx0 + 1, y + 27); }
          if (V.mode === 'edit' && pxs > 80) lane.hits.push({ x: wx0 - 1, y: y + 14, w: Math.max(4, wx1 - wx0), h: bh - 12, drag: true, cursor: 'ew-resize', pad: 1,
            tip: () => `${wd.id} "${wd.text}"  ${fmtTime(wt, 3)}  d=${(wdd || 0).toFixed(3)} conf ${wc.toFixed(2)}\nDrag to retime the word`,
            onDragStart: () => { SEL.wordId = wd.id; SEL.lineId = ln.id; E.wordDrag = { id: wd.id, t: wd.t, t0: wd.t, anchor: null }; },
            onDrag: (t) => { const d = E.wordDrag; if (d.anchor == null) d.anchor = t - d.t0; d.t = t - d.anchor; requestDraw('lyrics'); },
            onDragEnd: (t, moved) => { const d = E.wordDrag; E.wordDrag = null; if (moved) Edit.setWordTime(wd.id, d.t); requestDraw('lyrics'); } });
        }
      }
      const hit = { x: x0, y, w: ww, h: bh, tip: () => lineTip(ln), onClick: () => { selectLine(ln.id); seek(ln.t); } };
      if (V.mode === 'edit') Object.assign(hit, { drag: true, cursor: 'grab',
        onDragStart: () => { selectLine(ln.id); E.lineDrag = { id: ln.id, t: ln.t, t0: ln.t, anchor: null }; },
        onDrag: (t) => { const d = E.lineDrag; if (d.anchor == null) d.anchor = t - d.t0; d.t = Math.max(0, t - d.anchor); requestDraw('lyrics'); },
        onDragEnd: (t, moved) => { const d = E.lineDrag; E.lineDrag = null; if (moved) Edit.setLineTime(ln.id, d.t); else { seek(ln.t); } requestDraw('lyrics'); } });
      lane.hits.unshift(hit);
    }
    // voice row labels
    if (M.voices.length > 1) {
      c.font = FONT_S; c.textAlign = 'left'; c.textBaseline = 'top';
      M.voices.forEach((v, i) => { c.fillStyle = T.faint; c.fillText(v.id + (M.charOfVoice.get(v.id) ? ' ' + M.charName(M.charOfVoice.get(v.id)) : ''), 4, top + i * LROW + 0); });
    }
  },
});
function lineTip(ln) {
  const M = V.model, sg = M.singers.get(ln.id) || [];
  const who = sg.map((s) => `${s.character_id || '?'}/${s.voice_id}${s.lead_backing === 'backing' ? ' (backing)' : ''}`).join(', ') || (M.voiceOfLine.get(ln.id) || ln.speaker_hint || 'singer unknown');
  return `${ln.id}  ${fmtTime(ln.t, 2)} - ${fmtTime(ln.t + ln.d, 2)}\n${ln.text}\nsinger: ${who}   conf ${ln.conf != null ? ln.conf.toFixed(2) : '-'}  grade ${ln.grade || '-'}  timing ${ln.timing_source || '-'}`;
}

// ================================================================================================ beats and counts
LANES.push({
  id: 'beats', title: 'Beats & counts', sub: 'beats, bars, eight-counts, tempo', h: 118,
  draw(c, w, hh, lane) {
    laneBg(c, w, hh);
    const M = V.model, grid = M.grid;
    if (!grid.length) return emptyMsg(c, w, hh, 'No beats (rhythm stage has no output).');
    drawSectionGrid(c, hh);
    const span = VW.t1 - VW.t0, pxBeat = (60 / ((M.tempo && M.tempo.bpm) || 120)) / span * w;
    // out-of-pulse regions
    for (const r of visible(items('pulse_regions'), VW.t0, VW.t1)) {
      if (r.in_pulse) continue;
      c.fillStyle = rgba(T.bad, 0.1); c.fillRect(t2x(r.t), 0, t2x(r.t + r.d) - t2x(r.t), hh);
    }
    // counts strip (top)
    const cy = 3, chh = 22;
    c.font = FONT_S; c.textBaseline = 'middle';
    const counts = items('counts');
    for (const ct of visible(counts, VW.t0, VW.t1)) {
      const x0 = t2x(ct.t), x1 = t2x(ct.t + ct.d);
      c.strokeStyle = ct.lead_in ? T.warn : T.accent; c.lineWidth = 1;
      if (ct.partial) c.setLineDash([3, 2]);
      c.strokeRect(x0 + 0.5, cy + 0.5, Math.max(1, x1 - x0 - 1), chh - 1);
      c.setLineDash([]);
      c.fillStyle = ct.lead_in ? T.warn : T.dim; c.textAlign = 'left';
      const lab = fitText(c, ct.id + (ct.partial ? ' partial' : '') + (ct.in_pulse === false ? ' off-pulse' : ''), x1 - x0 - 4);
      if (lab) c.fillText(lab, x0 + 3, cy + 6);
      lane.hits.push({ x: x0, y: cy, w: x1 - x0, h: chh, tip: `${ct.id}  ${ct.lead_in ? 'lead-in (5-6-7-8)' : ''}\nlen ${ct.len}${ct.partial ? ' (partial)' : ''}  first count ${ct.first_count}\n${ct.phrase_id || ''} ${ct.section_id || ''}\naccents ${(ct.accents || []).map((a) => a.toFixed(2)).join(' ')}` });
    }
    // beats
    const by0 = 30, by1 = hh - 34;
    let lastBar = -1;
    for (const b of grid) {
      if (b.t < VW.t0 - 0.5) continue;
      if (b.t > VW.t1 + 0.5) break;
      const x = Math.round(t2x(b.t)) + 0.5;
      const down = b.beat_in_bar === 1;
      c.strokeStyle = b.preview ? T.edit : b.in_pulse ? (down ? T.text : T.dim) : T.faint;
      c.lineWidth = down ? 1.8 : 1;
      if (!b.in_pulse) c.setLineDash([2, 3]);
      c.beginPath(); c.moveTo(x, down ? by0 : by0 + 12); c.lineTo(x, by1); c.stroke();
      c.setLineDash([]);
      c.fillStyle = down ? T.text : T.dim; c.font = down ? 'bold 10px system-ui' : FONT_S; c.textAlign = 'left'; c.textBaseline = 'top';
      if (down && b.bar !== lastBar && (pxBeat * (b.beats_in_bar || 4) > 18)) { c.fillText(String(b.bar), x + 3, by0 - 1); lastBar = b.bar; }
      if (pxBeat > 22) c.fillText(String(b.beat_in_bar), x + 3, by0 + 11);
      // count numbers within the count strip
    }
    // count digits under the strip
    if (pxBeat > 16) {
      c.font = FONT_S; c.textAlign = 'center'; c.textBaseline = 'middle';
      for (const ct of visible(counts, VW.t0, VW.t1)) {
        for (let k = 0; k < ct.len; k++) {
          const bi = ct.start_beat + k;
          const bt = beatTime(bi);
          if (bt == null) continue;
          const x = t2x(bt);
          if (x < -10 || x > w + 10) continue;
          const acc = (ct.accents || [])[k] || 0;
          c.fillStyle = rgba(ct.lead_in ? T.warn : T.accent, 0.45 + 0.55 * acc);
          c.font = (acc > 0.6 ? 'bold ' : '') + '11px system-ui';
          c.fillText(String(((ct.first_count - 1 + k) % 8) + 1), x, cy + 12);
        }
      }
    }
    // meter changes
    const mc = ((M.tempo || {}).meter || {}).changes || [];
    c.textAlign = 'left'; c.textBaseline = 'top'; c.font = 'bold 10px system-ui';
    for (const m of mc) { const x = t2x(m.t); if (x < 0 || x > w) continue; c.fillStyle = T.warn; c.fillRect(Math.round(x) - 1, by0, 2, by1 - by0); c.fillText(m.beats_per_bar + '/4', x + 3, by1 - 12); }
    // tempo curve
    const tc = curve('tempo.bpm');
    if (tc) {
      const ty = hh - 30, th = 26;
      c.fillStyle = T.faint; c.font = FONT_S; c.textAlign = 'left'; c.textBaseline = 'top';
      const p = L.poolCurve(tc.values, tc.rate, VW.t0, VW.t1, w);
      let lo = Infinity, hi = -Infinity;
      for (let x = 0; x < w; x++) { if (p.mean[x] < lo) lo = p.mean[x]; if (p.mean[x] > hi) hi = p.mean[x]; }
      if (!isFinite(lo)) { lo = 100; hi = 140; }
      const mid = (lo + hi) / 2, rng = Math.max(6, hi - lo);
      drawCurve(c, tc, ty, th, mid - rng * 0.6, mid + rng * 0.6, T.good, { fill: false, lw: 1.4 });
      c.fillStyle = T.good; c.fillText(`${(M.gridOpts && M.gridOpts.bpm) ? 'preview ' + M.gridOpts.bpm.toFixed(1) : (hi - lo < 0.5 ? mid.toFixed(1) : lo.toFixed(0) + '-' + hi.toFixed(0))} BPM`, 4, ty - 1);
    }
    if (M.gridPending) { c.fillStyle = T.edit; c.font = 'bold 10px system-ui'; c.textAlign = 'right'; c.textBaseline = 'top'; c.fillText('PREVIEW: pending rhythm edit (stages re-run)', w - 6, hh - 14); }
    // beat hit-rects (tooltip) only when zoomed in
    if (pxBeat > 10) for (const b of grid) {
      if (b.t < VW.t0 - 0.2 || b.t > VW.t1 + 0.2) continue;
      lane.hits.push({ x: t2x(b.t) - 4, y: by0, w: 8, h: by1 - by0, tip: `beat ${b.beat_index}  bar ${b.bar} beat ${b.beat_in_bar}/${b.beats_in_bar}\n${fmtTime(b.t, 3)}  ${b.in_pulse ? 'in pulse' : 'off-pulse (virtual)'}${b.strength != null ? '  strength ' + b.strength : ''}` });
    }
  },
});
function beatTime(i) {
  const g = V.model.grid;
  if (i >= 0 && i < g.length) return g[i].t;
  if (g.length < 2) return null;
  if (i < 0) return g[0].t + i * (g[1].t - g[0].t);
  return g[g.length - 1].t + (i - g.length + 1) * (g[g.length - 1].t - g[g.length - 2].t);
}

// ================================================================================================ hits
const HIT_ROWS = ['kick', 'snare', 'hat', 'tom', 'cymbal', 'perc'];
const ONSET_ROWS = [['onsets.bass', 'bass onsets', 'bass'], ['onsets.mid', 'mid onsets', 'mid'], ['onsets.high', 'high onsets', 'high']];
LANES.push({
  id: 'hits', title: 'Hits', sub: 'drums by velocity, onsets, hit points, holds', h: 26 + HIT_ROWS.length * 15 + ONSET_ROWS.length * 11 + 36,
  rowLabels: () => [...HIT_ROWS.map((r, i) => ({ y: 26 + i * 15, h: 14, label: r, col: DRUM_COL[r] })), ...ONSET_ROWS.map((r, i) => ({ y: 26 + HIT_ROWS.length * 15 + 2 + i * 11, h: 11, label: r[1], col: T[r[2]] })), { y: 26 + HIT_ROWS.length * 15 + ONSET_ROWS.length * 11 + 5, h: 28, label: 'hit points / holds', col: T.warn }],
  draw(c, w, hh, lane) {
    laneBg(c, w, hh);
    const dh = items('drum_hits');
    const hp = items('hit_points');
    if (!dh.length && !hp.length && !items('onsets.bass').length && !items('hits.kick').length) return emptyMsg(c, w, hh, 'No drum hits (drums stage has no output).');
    drawSectionGrid(c, hh);
    let y = 26;
    const rowsDef = [];
    const useFallback = !dh.length;
    HIT_ROWS.forEach((r, i) => { rowsDef.push({ y: y + i * 15, h: 14, r }); });
    rowsDef.forEach((rd, i) => { if (i % 2) { c.fillStyle = rgba('#ffffff', 0.025); c.fillRect(0, rd.y - 0.5, w, 15); } });
    c.lineCap = 'butt';
    if (!useFallback) {
      for (const it of visible(dh, VW.t0, VW.t1)) {
        const rd = rowsDef[Math.max(0, HIT_ROWS.indexOf(it.drum))] || rowsDef[0];
        const x = t2x(it.t), v = clamp(it.vel == null ? 0.7 : it.vel, 0, 1);
        const bh = 3 + v * 11;
        c.fillStyle = rgba(DRUM_COL[it.drum] || '#999', 0.4 + 0.6 * v);
        c.fillRect(Math.round(x) - 1, rd.y + 14 - bh, 2, bh);
        lane.hits.push({ x: x - 3, y: rd.y, w: 6, h: 14, tip: `${it.drum} @ ${fmtTime(it.t, 3)}  vel ${v.toFixed(2)}${it.level_db != null ? '  ' + it.level_db + ' dB' : ''}${it.source ? '\n' + it.source : ''}` });
      }
    } else {
      for (const [name, rowIdx] of [['hits.kick', 0], ['hits.mid', 1], ['hits.high', 2]]) {
        for (const it of visible(items(name), VW.t0, VW.t1)) {
          const rd = rowsDef[rowIdx], x = t2x(it.t), v = clamp(it.strength == null ? 0.6 : it.strength, 0, 1);
          c.fillStyle = rgba(DRUM_COL[HIT_ROWS[rowIdx]], 0.4 + 0.6 * v); c.fillRect(Math.round(x) - 1, rd.y + 14 - (3 + v * 11), 2, 3 + v * 11);
        }
      }
      c.fillStyle = T.faint; c.font = FONT_S; c.textAlign = 'right'; c.fillText('viz hit envelopes (no drum classifier output)', w - 6, 10);
    }
    y += HIT_ROWS.length * 15 + 2;
    ONSET_ROWS.forEach(([name, _l, tk], i) => {
      c.fillStyle = rgba(T[tk], 0.8);
      for (const it of visible(items(name), VW.t0, VW.t1)) {
        const x = t2x(it.t), v = clamp(it.strength == null ? 0.5 : it.strength, 0, 1);
        c.globalAlpha = 0.35 + 0.65 * v; c.fillRect(Math.round(x), y + i * 11 + 9 - (2 + 7 * v), 1.5, 2 + 7 * v);
      }
      c.globalAlpha = 1;
    });
    y += ONSET_ROWS.length * 11 + 3;
    // holds then hit points
    for (const o of visible(items('holds'), VW.t0, VW.t1)) {
      const x0 = t2x(o.t), x1 = t2x(o.t + o.d);
      c.fillStyle = rgba(T.good, 0.5); c.fillRect(x0, y + 12, Math.max(2, x1 - x0), 8);
      c.fillStyle = T.text; c.font = FONT_S; c.textAlign = 'left'; c.textBaseline = 'middle'; const t = fitText(c, o.id + ' ' + (o.kind || ''), x1 - x0 - 3); if (t) c.fillText(t, x0 + 2, y + 16.5);
      lane.hits.push({ x: x0, y: y + 12, w: x1 - x0, h: 8, tip: `${o.id} hold (${o.kind})  ${fmtTime(o.t, 2)} d ${o.d.toFixed(2)}  strength ${o.strength}` });
    }
    for (const p of visible(hp, VW.t0, VW.t1)) {
      const x = t2x(p.t), s = 4 + 5 * clamp(p.strength == null ? 0.5 : p.strength, 0, 1);
      c.fillStyle = T.warn; c.beginPath(); c.moveTo(x, y + 6 - s); c.lineTo(x + s, y + 6); c.lineTo(x, y + 6 + s); c.lineTo(x - s, y + 6); c.closePath(); c.fill();
      lane.hits.push({ x: x - s, y: y + 6 - s, w: 2 * s, h: 2 * s, onClick: () => seek(p.t), tip: `${p.id} hit point (rank ${p.rank})  strength ${p.strength}\n${(p.kinds || []).join(' + ')}  @ ${fmtTime(p.t, 3)}` });
    }
  },
  buildHead: null,
});

// ================================================================================================ bands
LANES.push({
  id: 'bands', title: 'Bands', sub: 'bass / mid / high + kick envelope', h: 130,
  buildHead(head) {
    head.append(h('label', { class: 'mini' }, h('input', { type: 'checkbox', id: 'chk-spec', onchange: (e) => { V.showSpec = e.target.checked; lsSet('spec', V.showSpec); loadSpectrogram().then(() => requestDraw('bands')); } }), ' spectrogram'));
    const k = h('div', { class: 'legend' }, h('span', { style: { color: 'var(--bass)' } }, '■ bass '), h('span', { style: { color: 'var(--mid)' } }, '■ mid '), h('span', { style: { color: 'var(--high)' } }, '■ high '), h('span', { style: { color: '#ff5d5d' } }, '■ kick'));
    head.append(k);
  },
  draw(c, w, hh, lane) {
    laneBg(c, w, hh);
    if (!curve('bands.bass')) return emptyMsg(c, w, hh, 'No band curves (spectral stage has no output).');
    if (V.showSpec && V.hasSpectrogram && V.specLoaded) drawSpectrogram(c, w, hh);
    else if (V.showSpec && V.hasSpectrogram) { c.fillStyle = T.faint; c.font = FONT; c.fillText('loading spectrogram...', 10, hh - 10); }
    else if (V.showSpec) { c.fillStyle = T.faint; c.font = FONT; c.fillText('No spectrogram in this folder/bundle (it was over the inline size cap): use mvh view.', 10, hh - 10); }
    drawSectionGrid(c, hh);
    const ab = V.showSpec && V.specLoaded ? 0.0 : 0.22;
    drawCurve(c, curve('bands.high'), 4, hh - 8, 0, 1, T.high, { alpha: ab });
    drawCurve(c, curve('bands.mid'), 4, hh - 8, 0, 1, T.mid, { alpha: ab });
    drawCurve(c, curve('bands.bass'), 4, hh - 8, 0, 1, T.bass, { alpha: ab });
    const hk = curve('hits.kick') || curve('bands.kick');
    if (hk) drawCurve(c, hk, 4, hh - 8, 0, 1.2, '#ff5d5d', { fill: false, useMax: true, lw: 1 });
  },
});
async function loadSpectrogram() {
  if (!V.hasSpectrogram || V.specLoaded || V.specLoading) return;
  V.specLoading = true;
  try { await V.song.ensure('curves:spectrum128'); V.specLoaded = true; } catch (e) { V.hasSpectrogram = false; }
  V.specLoading = false;
}
function drawSpectrogram(c, w, hh) {
  const key = [VW.t0.toFixed(3), VW.t1.toFixed(3), w, hh].join('|');
  if (!V._specImg || V._specImg.key !== key) {
    const iw = w, ih = hh;
    const img = new ImageData(iw, 128);
    const span = VW.t1 - VW.t0, dur = V.model.duration;
    for (let x = 0; x < iw; x++) {
      const ta = VW.t0 + (x / iw) * span, tb = VW.t0 + ((x + 1) / iw) * span;
      const row = V.song.spectrumAt(clamp((ta + tb) / 2, 0, dur));
      const rowB = tb - ta > 0.02 ? V.song.spectrumAt(clamp(ta + (tb - ta) * 0.2, 0, dur)) : row;
      const rowC = tb - ta > 0.02 ? V.song.spectrumAt(clamp(ta + (tb - ta) * 0.8, 0, dur)) : row;
      for (let b = 0; b < 128; b++) {
        const v = Math.max(row[b], rowB[b], rowC[b]);
        const o = ((127 - b) * iw + x) * 4;
        img.data[o] = LUT[v * 3]; img.data[o + 1] = LUT[v * 3 + 1]; img.data[o + 2] = LUT[v * 3 + 2]; img.data[o + 3] = 255;
      }
    }
    const off = document.createElement('canvas'); off.width = iw; off.height = 128;
    off.getContext('2d').putImageData(img, 0, 0);
    V._specImg = { key, cv: off };
  }
  c.imageSmoothingEnabled = true;
  c.drawImage(V._specImg.cv, 0, 0, w, hh);
}

// ================================================================================================ loud and quiet
const LEVELS = ['silence', 'quiet', 'soft', 'medium', 'loud', 'peak'];
LANES.push({
  id: 'loud', title: 'Loud & quiet', sub: 'LUFS, dynamics segments, impacts, stops', h: 132,
  buildHead(head) {
    head.append(h('div', { class: 'legend wrap' }, LEVELS.map((l) => h('span', { style: { color: LEVEL_COL[l] } }, '■ ' + l + ' '))));
  },
  draw(c, w, hh, lane) {
    laneBg(c, w, hh);
    const st = curve('loud.short_term_lufs'), mo = curve('loud.momentary_lufs');
    const dyn = items('dynamics');
    if (!st && !dyn.length) return emptyMsg(c, w, hh, 'No loudness data (loudness/dynamics stages have no output).');
    const top = 14, bot = hh - 6, ph = bot - top;
    for (const d of visible(dyn, VW.t0, VW.t1)) {
      const x0 = t2x(d.t), x1 = t2x(d.t + d.d);
      c.fillStyle = rgba(LEVEL_COL[d.level] || '#444', 0.38); c.fillRect(x0, 0, Math.max(1, x1 - x0), hh);
      c.fillStyle = LEVEL_COL[d.level] || '#444'; c.fillRect(x0, 0, Math.max(1, x1 - x0), 3);
      lane.hits.push({ x: x0, y: 0, w: x1 - x0, h: hh, tip: `${d.level}  ${fmtTime(d.t, 1)} - ${fmtTime(d.t + d.d, 1)}\nmean ${d.mean_lufs} LUFS (${d.rel_lu > 0 ? '+' : ''}${d.rel_lu} LU rel.)  conf ${d.conf}` });
    }
    const lo = -48, hi = -4;
    c.font = FONT_S; c.textAlign = 'left'; c.textBaseline = 'middle'; c.strokeStyle = T.grid;
    for (const g of [-40, -30, -23, -14, -8]) { const y = top + (1 - (g - lo) / (hi - lo)) * ph; c.beginPath(); c.moveTo(0, y + 0.5); c.lineTo(w, y + 0.5); c.stroke(); c.fillStyle = T.faint; c.fillText(g + ' LUFS', 3, y - 5); }
    if (mo) drawCurve(c, mo, top, ph, lo, hi, T.dim, { fill: false, lw: 0.8 });
    if (st) drawCurve(c, st, top, ph, lo, hi, T.accent, { alpha: 0.18, lw: 1.8 });
    const li = V.meta.loudness;
    if (li && li.integrated_lufs != null) {
      const y = top + (1 - (li.integrated_lufs - lo) / (hi - lo)) * ph;
      c.setLineDash([5, 4]); c.strokeStyle = T.good; c.beginPath(); c.moveTo(0, y); c.lineTo(w, y); c.stroke(); c.setLineDash([]);
      c.fillStyle = T.good; c.textAlign = 'right'; c.fillText(`integrated ${li.integrated_lufs.toFixed(1)} LUFS  LRA ${li.lra_lu != null ? li.lra_lu.toFixed(1) : '-'}  TP ${li.true_peak_dbtp != null ? li.true_peak_dbtp.toFixed(1) : '-'}`, w - 6, y - 6);
    }
    for (const z of visible(items('silences'), VW.t0, VW.t1)) {
      const x0 = t2x(z.t), x1 = t2x(z.t + z.d);
      c.fillStyle = rgba('#000000', 0.5); c.fillRect(x0, 0, x1 - x0, hh);
      c.fillStyle = T.text; c.textAlign = 'left'; c.fillText(z.id + ' silence', x0 + 3, hh - 10);
      lane.hits.push({ x: x0, y: 0, w: x1 - x0, h: hh, tip: `${z.id} silence ${fmtTime(z.t, 2)}  ${z.d.toFixed(2)} s  depth ${z.depth_db} dB` });
    }
    for (const i of visible(items('impacts'), VW.t0, VW.t1)) {
      const x = t2x(i.t); c.fillStyle = T.warn; c.beginPath(); c.moveTo(x, 16); c.lineTo(x - 5, 5); c.lineTo(x + 5, 5); c.closePath(); c.fill();
      lane.hits.push({ x: x - 6, y: 3, w: 12, h: 14, onClick: () => seek(i.t), tip: `${i.id} impact @ ${fmtTime(i.t, 2)}  strength ${i.strength}  +${i.delta_lu} LU  bass +${i.delta_bass_db} dB` });
    }
    for (const s of visible(items('stops'), VW.t0, VW.t1)) {
      const x = t2x(s.t); c.strokeStyle = T.bad; c.lineWidth = 2; c.beginPath(); c.moveTo(x - 4, 5); c.lineTo(x + 4, 15); c.moveTo(x + 4, 5); c.lineTo(x - 4, 15); c.stroke(); c.lineWidth = 1;
      lane.hits.push({ x: x - 6, y: 3, w: 12, h: 14, onClick: () => seek(s.t), tip: `${s.id} stop @ ${fmtTime(s.t, 2)}  gap ${s.gap_s} s` });
    }
    drawSectionGrid(c, hh);
  },
});

// ================================================================================================ instruments & stems
const ST_ROW = 20;
function stemRows() { return MIXER_STEMS.filter((s) => curve('stem.' + s + '.level') || stemsAvailable().includes(s)); }
function instrumentRows() {
  const cov = new Map();
  for (const it of items('instruments')) cov.set(it.instrument, (cov.get(it.instrument) || 0) + (it.d || 0));
  return Array.from(cov.entries()).sort((a, b) => b[1] - a[1]).slice(0, 12).map((x) => x[0]);
}
LANES.push({
  id: 'instruments', title: 'Instruments & stems', sub: 'stem levels (S solo / M mute), tagged instruments', h: () => 26 + (stemRows().length + instrumentRows().length) * ST_ROW + 6,
  buildHead(head, lane) {
    const box = h('div', { class: 'stem-ctl' });
    stemRows().forEach((s, i) => {
      const playable = stemsAvailable().includes(s);
      box.append(h('div', { class: 'stem-row', style: { top: (26 + i * ST_ROW) + 'px', height: ST_ROW + 'px' } },
        h('span', { class: 'swatch', style: { background: STEM_COL[s] } }), h('span', { class: 'stem-name', text: s.replace('_', ' ') }),
        playable ? h('button', { class: 'stembtn', 'data-stem': s, 'data-act': 'solo', title: 'Solo (listen to this stem only)', onclick: () => toggleStem(s, 'solo') }, 'S') : null,
        playable ? h('button', { class: 'stembtn', 'data-stem': s, 'data-act': 'mute', title: 'Mute this stem', onclick: () => toggleStem(s, 'mute') }, 'M') : null));
    });
    const ir = instrumentRows();
    const off = 26 + stemRows().length * ST_ROW;
    ir.forEach((n, i) => box.append(h('div', { class: 'stem-row', style: { top: (off + i * ST_ROW) + 'px', height: ST_ROW + 'px' } }, h('span', { class: 'stem-name inst', text: n.replace(/_/g, ' ') }))));
    box.append(h('button', { id: 'btn-clear-stems', class: 'stembtn wide', hidden: true, style: { top: '3px', right: '4px' }, onclick: clearStems }, 'clear S/M'));
    head.append(box);
  },
  draw(c, w, hh, lane) {
    laneBg(c, w, hh);
    const sr = stemRows(), ir = instrumentRows();
    if (!sr.length && !ir.length) return emptyMsg(c, w, hh, 'No stem or instrument data.');
    drawSectionGrid(c, hh);
    const mixNote = A.mixer ? 'stem mixer active: the mix is replaced by the unmuted stems' : (stemsAvailable().length ? 'S / M toggle the stem mixer' : 'no stem audio in this folder');
    c.font = FONT_S; c.fillStyle = A.mixer ? T.edit : T.faint; c.textAlign = 'left'; c.textBaseline = 'top'; c.fillText(mixNote, 6, 6);
    const acts = new Map();
    for (const it of items('stem_activity')) { if (!acts.has(it.stem)) acts.set(it.stem, []); acts.get(it.stem).push(it); }
    sr.forEach((s, i) => {
      const y = 26 + i * ST_ROW;
      if (i % 2) { c.fillStyle = rgba('#ffffff', 0.025); c.fillRect(0, y, w, ST_ROW); }
      const lv = curve('stem.' + s + '.level');
      const col = STEM_COL[s] || '#999';
      if (lv) drawCurve(c, lv, y + 1, ST_ROW - 5, 0, 1, col, { alpha: 0.35, lw: 1 });
      c.fillStyle = col;
      for (const a of visible(acts.get(s) || [], VW.t0, VW.t1)) { c.globalAlpha = 0.9; c.fillRect(t2x(a.t), y + ST_ROW - 3, Math.max(1, t2x(a.t + a.d) - t2x(a.t)), 2); }
      c.globalAlpha = 1;
      const st = A.stemState[s];
      if (st && (st.mute || st.solo)) { c.fillStyle = rgba(st.solo ? T.good : T.bad, 0.12); c.fillRect(0, y, w, ST_ROW); }
    });
    const off = 26 + sr.length * ST_ROW;
    ir.forEach((name, i) => {
      const y = off + i * ST_ROW;
      if (i % 2) { c.fillStyle = rgba('#ffffff', 0.025); c.fillRect(0, y, w, ST_ROW); }
      for (const a of visible(items('instruments').filter((x) => x.instrument === name), VW.t0, VW.t1)) {
        const x0 = t2x(a.t), x1 = t2x(a.t + a.d);
        c.fillStyle = rgba(CAT[(i + 2) % CAT.length], 0.25 + 0.6 * clamp(a.conf == null ? 0.6 : a.conf, 0, 1));
        c.fillRect(x0, y + 3, Math.max(1, x1 - x0 - 1), ST_ROW - 7);
        lane.hits.push({ x: x0, y: y + 3, w: x1 - x0, h: ST_ROW - 7, tip: `${name}  ${fmtTime(a.t, 1)} - ${fmtTime(a.t + a.d, 1)}\nconf ${a.conf}  evidence ${a.evidence || '-'}${a.stem ? '  stem ' + a.stem : ''}` });
      }
    });
  },
});

// ================================================================================================ notes (piano roll)
V.noteSrc = V.noteSrc || lsGet('noteSrc', { bass: true, piano: true, guitar: true, other: true, vocals: true });
let _noteRange = null;
function noteRange() {
  if (_noteRange) return _noteRange;
  let lo = 200, hi = -1;
  const all = [];
  for (const s of Object.keys(NOTE_COL)) for (const n of items('notes.' + s)) all.push(n.midi);
  if (!all.length) return (_noteRange = [36, 84]);
  all.sort((a, b) => a - b);
  lo = all[Math.floor(all.length * 0.01)]; hi = all[Math.min(all.length - 1, Math.ceil(all.length * 0.99))];
  lo = Math.floor(lo / 12) * 12; hi = Math.ceil((hi + 1) / 12) * 12;
  return (_noteRange = [Math.max(0, lo - 1), Math.min(127, hi)]);
}
LANES.push({
  id: 'notes', title: 'Notes', sub: 'piano roll per source, key and chords', h: 210,
  buildHead(head) {
    const chips = h('div', { class: 'chips' });
    for (const s of Object.keys(NOTE_COL)) {
      const n = items('notes.' + s).length;
      chips.append(h('button', { class: 'chip' + (V.noteSrc[s] ? ' on' : ''), style: { '--c': NOTE_COL[s] }, onclick: (e) => { V.noteSrc[s] = !V.noteSrc[s]; lsSet('noteSrc', V.noteSrc); e.currentTarget.classList.toggle('on', V.noteSrc[s]); requestDraw('notes'); } }, `${s} ${n}`));
    }
    head.append(chips);
  },
  draw(c, w, hh, lane) {
    laneBg(c, w, hh);
    const total = Object.keys(NOTE_COL).reduce((a, s) => a + items('notes.' + s).length, 0);
    if (!total) return emptyMsg(c, w, hh, 'No notes (notes/vocals stages have no output).');
    const [lo, hi] = noteRange();
    const top = 18, ph = hh - top - 4, rows = hi - lo + 1, rh = ph / rows;
    const yOf = (m) => top + (hi - m) * rh;
    for (let m = lo; m <= hi; m++) {
      const pc = ((m % 12) + 12) % 12, black = [1, 3, 6, 8, 10].includes(pc);
      c.fillStyle = black ? rgba('#000000', 0.22) : rgba('#ffffff', 0.025);
      c.fillRect(0, yOf(m), w, rh);
      if (pc === 0) { c.strokeStyle = T.gridStrong; c.beginPath(); c.moveTo(0, yOf(m) + rh + 0.5); c.lineTo(w, yOf(m) + rh + 0.5); c.stroke(); c.fillStyle = T.faint; c.font = FONT_S; c.textAlign = 'left'; c.textBaseline = 'bottom'; c.fillText(L.midiName(m), 3, yOf(m) + rh); }
    }
    drawSectionGrid(c, hh);
    // key + chords strip
    c.font = FONT_S; c.textBaseline = 'middle';
    const key = items('key')[0] || (V.meta.key && V.meta.key.global);
    if (key) { c.fillStyle = T.accent; c.textAlign = 'left'; c.fillText('key: ' + key.key + (key.conf != null ? ' (' + (+key.conf).toFixed(2) + ')' : ''), 4, 8); }
    for (const ch of visible(items('chords'), VW.t0, VW.t1)) {
      if (ch.label === 'N') continue;
      const x0 = t2x(ch.t), x1 = t2x(ch.t + ch.d);
      c.fillStyle = rgba(T.accent, 0.12); c.fillRect(x0, 1, Math.max(1, x1 - x0 - 1), 15);
      c.fillStyle = T.text; c.textAlign = 'left';
      const t = fitText(c, ch.label, x1 - x0 - 3); if (t && x0 > 110) c.fillText(t, x0 + 2, 8.5);
      else if (t && x0 <= 110 && x1 > 120) c.fillText(t, Math.max(x0, 110) + 2, 8.5);
    }
    for (const s of Object.keys(NOTE_COL)) {
      if (!V.noteSrc[s]) continue;
      const col = NOTE_COL[s];
      for (const n of visible(items('notes.' + s), VW.t0, VW.t1)) {
        const x0 = t2x(n.t), x1 = t2x(n.t + n.d), y = yOf(n.midi);
        c.fillStyle = rgba(col, 0.35 + 0.6 * clamp(n.vel == null ? 0.6 : n.vel, 0, 1));
        c.fillRect(x0, y + 0.5, Math.max(1.5, x1 - x0 - 0.5), Math.max(2, rh - 1));
        lane.hits.push({ x: x0, y, w: Math.max(3, x1 - x0), h: Math.max(3, rh), onClick: () => seek(n.t), tip: `${s}  ${n.name || L.midiName(n.midi)} (midi ${n.midi})  ${fmtTime(n.t, 2)}  d ${n.d.toFixed(2)}  vel ${n.vel != null ? (+n.vel).toFixed(2) : '-'}  conf ${n.conf != null ? (+n.conf).toFixed(2) : '-'}` });
      }
    }
  },
});

// ================================================================================================ vocal range
LANES.push({
  id: 'vocal', title: 'Vocal range', sub: 'lead f0 on a note axis, tessitura, mouth, visemes', h: 190,
  draw(c, w, hh, lane) {
    laneBg(c, w, hh);
    const mid = curve('vocal.midi'), vr = V.meta.vocal_range;
    if (!mid) return emptyMsg(c, w, hh, 'No vocal pitch data (vocals stage has no output).');
    if (vr && vr.present === false) return emptyMsg(c, w, hh, 'No lead vocal found (instrumental).');
    const topS = 16, mouthH = 22, visH = 12, gap = 6;
    const bot = hh - mouthH - visH - gap * 2, top = topS;
    const lo = (vr && vr.p2 != null ? vr.p2 : 48) - 4, hi = (vr && vr.p98 != null ? vr.p98 : 72) + 4;
    const yOf = (m) => top + (1 - (m - lo) / (hi - lo)) * (bot - top);
    c.font = FONT_S; c.textAlign = 'left'; c.textBaseline = 'middle';
    for (let m = Math.ceil(lo); m <= hi; m++) {
      const pc = ((m % 12) + 12) % 12;
      c.strokeStyle = pc === 0 ? T.gridStrong : T.grid;
      if ([0, 2, 4, 5, 7, 9, 11].includes(pc)) { c.beginPath(); c.moveTo(0, yOf(m) + 0.5); c.lineTo(w, yOf(m) + 0.5); c.stroke(); }
      if (pc === 0 || pc === 7 || pc === 4) { c.fillStyle = T.faint; c.fillText(L.midiName(m), 3, yOf(m) - 6); }
    }
    if (vr && vr.p10 != null) {
      c.fillStyle = rgba(T.good, 0.12); c.fillRect(0, yOf(vr.p90), w, yOf(vr.p10) - yOf(vr.p90));
      c.strokeStyle = rgba(T.good, 0.6); c.setLineDash([2, 3]);
      for (const m of [vr.p2, vr.p98]) { c.beginPath(); c.moveTo(0, yOf(m) + 0.5); c.lineTo(w, yOf(m) + 0.5); c.stroke(); }
      c.setLineDash([]);
      c.fillStyle = T.good; c.textAlign = 'right'; c.fillText(`tessitura ${L.midiName(vr.p10)}-${L.midiName(vr.p90)}   range ${L.midiName(vr.p2)}-${L.midiName(vr.p98)}   ${vr.register || ''}`, w - 6, bot - 8);
    }
    drawSectionGrid(c, hh);
    // phrases / style strip
    for (const p of visible(items('vocal_style'), VW.t0, VW.t1)) {
      const x0 = t2x(p.t), x1 = t2x(p.t + p.d);
      c.fillStyle = rgba({ singing: '#f72585', speech: '#4cc9f0', rap: '#ffd166' }[p.style] || '#999', 0.5); c.fillRect(x0, 1, Math.max(1, x1 - x0 - 1), 12);
      c.fillStyle = T.text; c.textAlign = 'left'; c.textBaseline = 'middle'; const t = fitText(c, p.style, x1 - x0 - 4); if (t) c.fillText(t, x0 + 3, 7.5);
    }
    // notes as bars
    for (const n of visible(items('notes.vocals'), VW.t0, VW.t1)) {
      const x0 = t2x(n.t), x1 = t2x(n.t + n.d), y = yOf(n.midi);
      c.fillStyle = rgba('#f72585', 0.25); c.fillRect(x0, y - 3, Math.max(1.5, x1 - x0), 6);
      lane.hits.push({ x: x0, y: y - 4, w: Math.max(3, x1 - x0), h: 8, tip: `vocal note ${n.name} (${n.midi})  ${fmtTime(n.t, 2)}  d ${n.d.toFixed(2)}` });
    }
    // f0
    const p = L.poolCurve(mid.values, mid.rate, VW.t0, VW.t1, w);
    c.strokeStyle = '#f72585'; c.lineWidth = 1.6; c.beginPath();
    let on = false;
    for (let x = 0; x < w; x++) {
      const lo2 = p.min[x], hi2 = p.max[x];
      if (!(lo2 === lo2)) { on = false; continue; }
      const y1 = yOf(hi2), y2 = yOf(lo2);
      if (!on) { c.moveTo(x, y1); on = true; } else c.lineTo(x, y1);
      if (y2 - y1 > 1) { c.lineTo(x, y2); }
    }
    c.stroke(); c.lineWidth = 1;
    // lowest / highest markers
    for (const [k, col] of [['lowest', T.bass], ['highest', T.warn]]) {
      const m = vr && vr[k];
      if (!m) continue;
      const x = t2x(m.t), y = yOf(m.midi);
      c.fillStyle = col; c.beginPath(); c.arc(x, y, 4, 0, 7); c.fill();
      if (x > 0 && x < w) { c.font = 'bold 10px system-ui'; c.textAlign = 'left'; c.fillText(`${k} ${m.name}`, x + 6, y + (k === 'lowest' ? 10 : -8)); }
      lane.hits.push({ x: x - 7, y: y - 7, w: 14, h: 14, pad: 3, onClick: () => { seek(m.t); ensureVisible(m.t, 0.3); }, tip: `${k} sustained note ${m.name} (${m.hz.toFixed(1)} Hz) @ ${fmtTime(m.t, 2)}\nclick to jump` });
    }
    // mouth open + visemes
    const my = bot + gap;
    c.fillStyle = rgba('#ffffff', 0.03); c.fillRect(0, my, w, mouthH);
    const mo = curve('vocal.mouth_open');
    const voices = V.model.voices;
    if (voices.length > 1) voices.forEach((v, i) => { const mc = curve('vocal.mouth_open.' + v.id); if (mc) drawCurve(c, mc, my, mouthH, 0, 1, CAT[i % CAT.length], { alpha: 0.2, useMax: true, lw: 1 }); });
    else if (mo) drawCurve(c, mo, my, mouthH, 0, 1, '#ffd166', { alpha: 0.25, useMax: true, lw: 1 });
    c.fillStyle = T.faint; c.textAlign = 'left'; c.textBaseline = 'top'; c.fillText('mouth_open', 3, my + 1);
    const vy = my + mouthH + gap - 2;
    for (const vs of visible(items('visemes'), VW.t0, VW.t1)) {
      if (vs.viseme === 'X') continue;
      const x0 = t2x(vs.t), x1 = t2x(vs.t + vs.d);
      c.fillStyle = VISEME_COL[vs.viseme] || '#888'; c.fillRect(x0, vy, Math.max(1, x1 - x0 - 0.5), visH);
      if (x1 - x0 > 9) { c.fillStyle = '#0b0f17'; c.textAlign = 'left'; c.textBaseline = 'middle'; c.fillText(vs.viseme, x0 + 2, vy + visH / 2 + 0.5); }
    }
  },
});

// ================================================================================================ cues
LANES.push({
  id: 'cues', title: 'Cues', sub: 'tiered cue list with lead-in; pinned moments', h: 100,
  draw(c, w, hh, lane) {
    laneBg(c, w, hh);
    const cues = items('cues');
    const pins = (((V.ovr || {}).cues || {}).pinned) || [];
    if (!cues.length && !pins.length) return emptyMsg(c, w, hh, 'No cues (cues stage has no output).');
    drawSectionGrid(c, hh);
    const rowH = 19, KIND_COL = { drop: '#ff6b6b', build_start: '#f783ac', breakdown: '#74c0fc', section: '#fcc419', stop: '#ff4d4d', silence: '#868e96', impact: '#ffa94d', phrase: '#69db7c', hit_point: '#ffd43b', downbeat: '#74c0fc', beat: '#868e96', pinned: '#f59f00' };
    c.font = FONT_S; c.textBaseline = 'middle';
    for (let tier = 1; tier <= 3; tier++) {
      const y = 4 + (tier - 1) * rowH;
      c.fillStyle = tier % 2 ? rgba('#ffffff', 0.02) : 'transparent'; c.fillRect(0, y - 2, w, rowH);
      c.fillStyle = T.faint; c.textAlign = 'left'; c.fillText('tier ' + tier, 3, y + rowH / 2 - 2);
      for (const q of visible(cues, VW.t0 - 5, VW.t1 + 1)) {
        if (q.tier !== tier) continue;
        const x = t2x(q.t), col = KIND_COL[q.kind] || '#aaa';
        if (q.lead_in_s) { c.fillStyle = rgba(col, 0.18); c.fillRect(t2x(q.t - q.lead_in_s), y, x - t2x(q.t - q.lead_in_s), rowH - 4); }
        if (x < -80 || x > w + 5) continue;
        c.fillStyle = col; c.fillRect(Math.round(x) - 1, y, 2, rowH - 4);
        c.beginPath(); c.moveTo(x, y); c.lineTo(x + 8, y + 4); c.lineTo(x, y + 8); c.closePath(); c.fill();
        c.fillStyle = T.text; c.textAlign = 'left';
        if (x >= 0) c.fillText(fitText(c, q.kind.replace('_', ' ') + (q.kinds && q.kinds.length > 1 ? ' +' + (q.kinds.length - 1) : ''), 90), x + 10, y + 6);
        lane.hits.push({ x: x - 3, y, w: 12, h: rowH - 3, onClick: () => seek(q.t), tip: `${q.id}  ${q.kind}  tier ${q.tier}  @ ${fmtTime(q.t, 3)}\nstrength ${q.strength == null ? '-' : q.strength}  lead-in ${q.lead_in_s == null ? '-' : q.lead_in_s + ' s'}\nkinds: ${(q.kinds || [q.kind]).join(', ')}\nsource: ${q.source ? q.source.id : '-'}` });
      }
    }
    // pinned moments (overrides.json cues.pinned)
    const py = 4 + 3 * rowH;
    c.fillStyle = T.faint; c.textAlign = 'left'; c.fillText('pins', 3, py + 8);
    pins.forEach((p, i) => {
      const x = t2x(p.t);
      if (x < -50 || x > w + 5) return;
      if (p.d) { c.fillStyle = rgba(T.edit, 0.25); c.fillRect(x, py + 2, t2x(p.t + p.d) - x, 12); }
      c.fillStyle = T.edit; c.beginPath(); c.moveTo(x, py); c.lineTo(x + 6, py + 7); c.lineTo(x, py + 14); c.lineTo(x - 6, py + 7); c.closePath(); c.fill();
      c.fillStyle = T.text; c.fillText(fitText(c, p.note || 'pin', 120), x + 9, py + 7);
      lane.hits.push({ x: x - 7, y: py, w: 14, h: 14, pad: 2, onClick: () => { SEL.pin = i; seek(p.t); openTab('edit'); requestDraw('cues'); }, tip: `pin ${fmtTime(p.t, 2)}${p.d ? ' d ' + p.d : ''}\n${p.note || ''}${V.mode === 'edit' ? '\n(select, then Delete to remove)' : ''}` });
    });
  },
  onDblClick(t) { if (V.mode === 'edit') Edit.addPin(t); },
});
