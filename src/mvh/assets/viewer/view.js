/* Time axis, lane framework, pointer interaction, render loop */
const VW = {
  t0: 0, t1: 30, w: 800, gw: 172, dpr: window.devicePixelRatio || 1, follow: lsGet('follow', 'page'),
  hoverT: null, drag: null, sel: null, lanes: [], flags: new Set(), raf: 0, lastNow: 0, lastStem: 0,
};
const MIN_SPAN = 0.4;
const t2x = (t) => ((t - VW.t0) / (VW.t1 - VW.t0)) * VW.w;
const x2t = (x) => VW.t0 + (x / VW.w) * (VW.t1 - VW.t0);

function setView(t0, t1, quiet) {
  const dur = Math.max(1, V.model.duration);
  let span = clamp(t1 - t0, MIN_SPAN, dur);
  t0 = clamp(t0, 0, Math.max(0, dur - span));
  VW.t0 = t0; VW.t1 = t0 + span;
  if (!quiet) requestDraw('all');
}
function zoomAt(factor, t) {
  const span = VW.t1 - VW.t0;
  const f = clamp((t - VW.t0) / span, 0, 1);
  const ns = clamp(span * factor, MIN_SPAN, Math.max(1, V.model.duration));
  setView(t - f * ns, t - f * ns + ns);
}
function panBy(dt) { setView(VW.t0 + dt, VW.t1 + dt); }
function fitAll() { setView(0, V.model.duration); }
function ensureVisible(t, margin) {
  const span = VW.t1 - VW.t0;
  if (t < VW.t0 || t > VW.t1) setView(t - span * (margin == null ? 0.1 : margin), t - span * (margin == null ? 0.1 : margin) + span);
}

function requestDraw(what) {
  if (what === 'all') VW.flags.add('all'); else VW.flags.add(what || 'all');
  if (!VW.raf) VW.raf = requestAnimationFrame(frame);
}

// ---------------------------------------------------------------------------------------- layout
function buildLanes() {
  const host = $('#lanes');
  host.textContent = '';
  const saved = lsGet('collapsed', {});
  VW.lanes = LANES.filter((l) => !l.global).map((def) => {
    const lane = Object.assign({ hits: [], collapsed: !!saved[def.id] }, def);
    const head = h('div', { class: 'lane-head' });
    const title = h('button', { class: 'lane-title', title: 'Collapse / expand', onclick: () => toggleLane(lane) }, h('span', { class: 'chev' }, '▾'), h('span', { class: 'ltxt' }, def.title));
    head.append(title);
    if (def.sub && !def.rowLabels && def.id !== 'instruments') head.append(h('div', { class: 'lane-sub', text: def.sub }));
    else if (def.sub) title.title = def.sub;
    const cv = h('div', { class: 'lane-cv' });
    const canvas = h('canvas');
    cv.append(canvas);
    const row = h('div', { class: 'lane', 'data-lane': def.id }, head, cv);
    lane.row = row; lane.head = head; lane.canvas = canvas; lane.cv = cv;
    if (def.buildHead) def.buildHead(head, lane);
    host.append(row);
    attachPointer(lane, canvas);
    applyLaneHeight(lane);
    return lane;
  });
  const ov = LANES.find((l) => l.global);
  VW.overview = Object.assign({ hits: [] }, ov);
  VW.overview.canvas = $('#cv-overview');
  attachPointer(VW.overview, VW.overview.canvas);
  VW.ruler = { canvas: $('#cv-ruler'), id: 'ruler', hits: [] };
  attachPointer(VW.ruler, VW.ruler.canvas);
}
function laneHeight(l) { return l.collapsed ? 24 : (typeof l.h === 'function' ? l.h() : l.h); }
function applyLaneHeight(l) {
  l.row.style.height = laneHeight(l) + 'px';
  l.row.classList.toggle('collapsed', l.collapsed);
  const chev = $('.chev', l.row);
  if (chev) chev.textContent = l.collapsed ? '▸' : '▾';
}
function toggleLane(l) {
  l.collapsed = !l.collapsed;
  const saved = lsGet('collapsed', {});
  saved[l.id] = l.collapsed; lsSet('collapsed', saved);
  applyLaneHeight(l);
  sizeCanvases();
  requestDraw(l.id);
}
function sizeCanvases() {
  const wrap = $('#lanes-wrap');
  const lanesEl = $('#lanes');
  VW.gw = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--gw'), 10) || 172;
  const gw = VW.gw;
  const sbw = lanesEl.offsetWidth - lanesEl.clientWidth;
  $$('.head-row').forEach((r) => { r.style.paddingRight = sbw + 'px'; });
  VW.w = Math.max(200, Math.floor(lanesEl.clientWidth - gw));
  VW.dpr = window.devicePixelRatio || 1;
  const all = [...VW.lanes, VW.overview, VW.ruler];
  for (const l of all) {
    const cv = l.canvas;
    const hpx = l === VW.overview ? l.h : l === VW.ruler ? 26 : laneHeight(l);
    cv.style.width = VW.w + 'px';
    cv.style.height = hpx + 'px';
    cv.width = Math.round(VW.w * VW.dpr);
    cv.height = Math.round(hpx * VW.dpr);
    l.pxH = hpx;
    l.cache = null;
  }
  requestDraw('all');
}

// ---------------------------------------------------------------------------------------- frame loop
function frame() {
  VW.raf = 0;
  const t = now();
  V.t = t;
  if (A.playing) {
    loopTick();
    followPlayhead(t);
    if (performance.now() - VW.lastStem > 250) { VW.lastStem = performance.now(); syncStems(); }
  }
  updatePlayhead(t);
  const all = VW.flags.has('all');
  const tickNow = performance.now();
  if (tickNow - VW.lastNow > 33 || !A.playing) { VW.lastNow = tickNow; updateNow(t); }
  if (all || VW.flags.size > (VW.flags.has('playhead') ? 1 : 0)) {
    for (const l of VW.lanes) {
      if (!(all || VW.flags.has(l.id))) continue;
      drawLane(l);
    }
    if (all || VW.flags.has('ruler')) drawRuler();
  }
  if (all || VW.flags.has('overview') || A.playing || VW.flags.has('playhead')) drawLane(VW.overview);
  VW.flags.clear();
  if (A.playing) VW.raf = requestAnimationFrame(frame);
}
function followPlayhead(t) {
  const span = VW.t1 - VW.t0;
  if (VW.follow === 'off' || VW.drag) return;
  if (VW.follow === 'centre') { setView(t - span * 0.4, t + span * 0.6, true); VW.flags.add('all'); return; }
  if (t > VW.t0 + span * 0.92 || t < VW.t0 - 0.001) { setView(t - span * 0.06, t + span * 0.94, true); VW.flags.add('all'); }
}
function updatePlayhead(t) {
  const ph = $('#playhead');
  const x = VW.gw + t2x(t);
  const vis = t >= VW.t0 - 0.01 && t <= VW.t1 + 0.01;
  ph.style.transform = `translateX(${x.toFixed(1)}px)`;
  ph.style.display = vis ? 'block' : 'none';
}
function drawLane(l) {
  const cv = l.canvas;
  if (!cv.width) return;
  const c = cv.getContext('2d');
  c.setTransform(VW.dpr, 0, 0, VW.dpr, 0, 0);
  l.hits = [];
  const hpx = l.pxH;
  if (!l.global && l.collapsed) { c.clearRect(0, 0, VW.w, hpx); c.fillStyle = T.lane; c.fillRect(0, 0, VW.w, hpx); return; }
  try { l.draw(c, VW.w, hpx, l); } catch (e) {
    c.fillStyle = T.lane; c.fillRect(0, 0, VW.w, hpx);
    c.fillStyle = T.bad; c.font = '12px system-ui'; c.fillText('lane error: ' + (e && e.message), 8, 18);
    console.error('lane', l.id, e);
    (V.laneErrors = V.laneErrors || []).push(l.id + ': ' + (e && e.message));
  }
}
function laneBg(c, w, hh, alt) { c.fillStyle = alt ? T.laneAlt : T.lane; c.fillRect(0, 0, w, hh); }
/** vertical lines at section boundaries (all zoomed lanes) */
function drawSectionGrid(c, hh) {
  c.save();
  c.strokeStyle = T.gridStrong; c.lineWidth = 1; c.setLineDash([3, 3]);
  for (const s of V.model.sections) {
    const x = Math.round(t2x(s.t)) + 0.5;
    if (x < 0 || x > VW.w) continue;
    c.beginPath(); c.moveTo(x, 0); c.lineTo(x, hh); c.stroke();
  }
  c.restore();
}
function drawRuler() {
  const l = VW.ruler, cv = l.canvas, c = cv.getContext('2d');
  c.setTransform(VW.dpr, 0, 0, VW.dpr, 0, 0);
  const w = VW.w, hh = l.pxH;
  c.fillStyle = T.panel; c.fillRect(0, 0, w, hh);
  const span = VW.t1 - VW.t0;
  const step = L.niceStep(span, w / 90);
  c.font = '11px ui-monospace, Consolas, monospace';
  c.textBaseline = 'middle';
  c.strokeStyle = T.gridStrong; c.fillStyle = T.dim;
  const first = Math.ceil(VW.t0 / step) * step;
  for (let t = first; t <= VW.t1 + 1e-9; t += step) {
    const x = Math.round(t2x(t)) + 0.5;
    c.beginPath(); c.moveTo(x, hh - 8); c.lineTo(x, hh); c.stroke();
    c.fillText(fmtTime(t, step < 1 ? (step < 0.1 ? 2 : 1) : 0), x + 3, hh / 2 - 2);
  }
  // bar numbers when there is room
  const downs = V.model.downbeats || [];
  if (downs.length > 1) {
    const barPx = (downs.length > 1 ? (downs[1].t - downs[0].t) : 2) / span * w;
    if (barPx > 28) {
      c.fillStyle = T.accent; c.font = '10px ui-monospace, Consolas, monospace';
      for (const b of downs) {
        if (b.t < VW.t0 - 1 || b.t > VW.t1) continue;
        c.fillText(b.bar, t2x(b.t) + 2, hh - 4);
      }
    }
  }
  if (VW.hoverT != null) {
    const x = t2x(VW.hoverT);
    c.fillStyle = T.text; c.font = '10px ui-monospace, Consolas, monospace';
    const lbl = fmtTime(VW.hoverT, 2);
    c.fillStyle = T.accent; c.fillRect(x - 0.5, 0, 1, hh);
    c.fillStyle = T.panel; c.fillRect(x + 2, 1, 46, 12);
    c.fillStyle = T.text; c.fillText(lbl, x + 4, 7);
  }
}

// ---------------------------------------------------------------------------------------- pointer
function laneHit(l, x, y) {
  const hs = l.hits || [];
  for (let i = hs.length - 1; i >= 0; i--) {
    const r = hs[i];
    const pad = r.pad || 0;
    if (x >= r.x - pad && x <= r.x + r.w + pad && y >= r.y - pad && y <= r.y + r.h + pad) return r;
  }
  return null;
}
function attachPointer(lane, canvas) {
  const rectOf = () => canvas.getBoundingClientRect();
  canvas.addEventListener('mousemove', (e) => {
    const r = rectOf(), x = e.clientX - r.left, y = e.clientY - r.top;
    if (VW.drag) return;
    const t = lane.global ? (x / VW.w) * V.model.duration : x2t(x);
    if (!lane.global) { VW.hoverT = t; requestDraw('ruler'); moveCursor(x); }
    const hit = laneHit(lane, x, y);
    canvas.style.cursor = hit && hit.cursor ? hit.cursor : (hit && hit.onClick ? 'pointer' : lane.global ? 'pointer' : 'crosshair');
    showTip(hit, e, lane, t);
  });
  canvas.addEventListener('mouseleave', () => { VW.hoverT = null; hideTip(); moveCursor(null); requestDraw('ruler'); });
  canvas.addEventListener('mousedown', (e) => {
    if (e.button !== 0) return;
    const r = rectOf(), x = e.clientX - r.left, y = e.clientY - r.top;
    const hit = laneHit(lane, x, y);
    VW.drag = { lane, x0: x, y0: y, cx: e.clientX, t0: VW.t0, t1: VW.t1, moved: false, hit, edit: !!(hit && hit.drag && V.mode === 'edit') };
    if (VW.drag.edit && hit.onDragStart) hit.onDragStart(x2t(x));
    e.preventDefault();
  });
  canvas.addEventListener('wheel', (e) => {
    const r = rectOf(), x = e.clientX - r.left;
    if (lane.global) { e.preventDefault(); const t = (x / VW.w) * V.model.duration; zoomAt(e.deltaY > 0 ? 1.25 : 0.8, t); return; }
    if (e.ctrlKey || e.metaKey) { e.preventDefault(); zoomAt(Math.exp(e.deltaY * 0.0022), x2t(x)); }
    else if (e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) { e.preventDefault(); panBy(((e.deltaX || e.deltaY) / VW.w) * (VW.t1 - VW.t0)); }
  }, { passive: false });
  canvas.addEventListener('dblclick', (e) => {
    const r = rectOf(), x = e.clientX - r.left, y = e.clientY - r.top;
    const hit = laneHit(lane, x, y);
    if (lane.onDblClick) lane.onDblClick(lane.global ? (x / VW.w) * V.model.duration : x2t(x), hit, e);
  });
  canvas.addEventListener('contextmenu', (e) => {
    if (V.mode !== 'edit' || !lane.onContext) return;
    const r = rectOf(), x = e.clientX - r.left, y = e.clientY - r.top;
    e.preventDefault();
    lane.onContext(x2t(x), laneHit(lane, x, y), e);
  });
}
window.addEventListener('mousemove', (e) => {
  const d = VW.drag;
  if (!d) return;
  const dx = e.clientX - d.cx;
  if (!d.moved && Math.abs(dx) < 4 && Math.abs(e.clientY - (d.y0 + d.lane.canvas.getBoundingClientRect().top)) < 4) return;
  d.moved = true;
  const r = d.lane.canvas.getBoundingClientRect();
  const x = e.clientX - r.left;
  if (d.edit) { if (d.hit.onDrag) d.hit.onDrag(x2t(x), e); return; }
  if (d.lane.global) { seek((x / VW.w) * V.model.duration); centreOn((x / VW.w) * V.model.duration); return; }
  if (d.lane === VW.ruler) { seek(x2t(x)); return; }
  const span = d.t1 - d.t0;
  setView(d.t0 - (dx / VW.w) * span, d.t0 - (dx / VW.w) * span + span);
});
window.addEventListener('mouseup', (e) => {
  const d = VW.drag;
  if (!d) return;
  VW.drag = null;
  const r = d.lane.canvas.getBoundingClientRect();
  const x = e.clientX - r.left, y = e.clientY - r.top;
  if (d.edit) { if (d.hit.onDragEnd) d.hit.onDragEnd(x2t(x), d.moved, e); return; }
  if (d.moved) return;
  if (d.hit && d.hit.onClick) { d.hit.onClick(e, d.lane.global ? (x / VW.w) * V.model.duration : x2t(x)); return; }
  if (d.lane.global) { const t = (x / VW.w) * V.model.duration; seek(t); centreOn(t, true); return; }
  seek(x2t(x));
});
function centreOn(t, onlyIfOut) {
  const span = VW.t1 - VW.t0;
  if (onlyIfOut && t >= VW.t0 && t <= VW.t1) return;
  setView(t - span / 2, t + span / 2);
}
function moveCursor(x) {
  const c = $('#cursor');
  if (x == null) { c.style.display = 'none'; return; }
  c.style.display = 'block';
  c.style.transform = `translateX(${(VW.gw + x).toFixed(1)}px)`;
}

// ---------------------------------------------------------------------------------------- tooltip
function showTip(hit, e, lane, t) {
  const tip = $('#tip');
  if (!hit || !hit.tip) { tip.style.display = 'none'; return; }
  const txt = typeof hit.tip === 'function' ? hit.tip() : hit.tip;
  tip.textContent = txt;
  tip.style.display = 'block';
  const pad = 14, w = tip.offsetWidth, hh = tip.offsetHeight;
  let x = e.clientX + pad, y = e.clientY + pad;
  if (x + w > window.innerWidth - 8) x = e.clientX - w - pad;
  if (y + hh > window.innerHeight - 8) y = e.clientY - hh - pad;
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
}
function hideTip() { $('#tip').style.display = 'none'; }
