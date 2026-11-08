/* Start-up, header controls, keyboard */
function showFatal(e) {
  console.error(e);
  const box = $('#fatal');
  box.hidden = false;
  box.textContent = '';
  box.append(h('h3', null, 'The viewer could not load this song'), h('pre', null, String(e && e.stack || e)),
    h('p', null, location.protocol === 'file:' ? 'Opened from disk, the viewer needs a browser with DecompressionStream and Blob module imports (any current Chrome, Edge or Firefox).' : 'Check that the song folder is complete (run mvh validate).'));
}

function initUI() {
  const M = V.model;
  document.title = 'mvh viewer - ' + M.title;
  $('#song-title').textContent = M.title;
  $('#song-sub').textContent = [M.artist, fmtTime(M.duration, 1), V.meta.tempo && V.meta.tempo.bpm ? (+V.meta.tempo.bpm).toFixed(1) + ' BPM' : null,
    V.meta.key && V.meta.key.global ? V.meta.key.global.key : null].filter(Boolean).join('  ·  ');
  const badge = $('#mode-badge');
  badge.textContent = V.mode === 'edit' ? 'EDIT MODE' : V.mode === 'served' ? 'read-only' : 'read-only · file';
  badge.className = 'badge ' + (V.mode === 'edit' ? 'edit' : '');
  badge.title = V.mode === 'file' ? 'Opened from the disk: preview data is inlined. Run `mvh view <song>` for edit mode.' : V.mode === 'edit' ? 'Corrections are saved to overrides.json and meaning/intent.md' : '';
  document.body.classList.toggle('edit-mode', V.mode === 'edit');
  document.body.dataset.mode = V.mode;
  V.showSpec = lsGet('spec', false);

  buildLanes();
  for (const lane of VW.lanes) if (lane.rowLabels) for (const r of lane.rowLabels()) lane.head.append(h('div', { class: 'rowlabel', style: { top: r.y + 'px', height: r.h + 'px' } }, h('span', { class: 'swatch', style: { background: r.col } }), r.label));
  const chk = $('#chk-spec'); if (chk) { chk.checked = !!V.showSpec; if (V.showSpec) loadSpectrogram().then(() => requestDraw('bands')); }
  renderSingerChips();
  const dur = M.duration;
  setView(0, dur <= 75 ? dur : 45, true);
  sizeCanvases();
  initAudio();
  buildValuesPane(); buildHelp(); renderMeaning();
  if (V.mode === 'edit') { $('#tab-edit').hidden = false; Edit.refreshPanel(); }
  openTab(V.mode !== 'edit' && lsGet('tab', 'meaning') === 'edit' ? 'meaning' : lsGet('tab', 'meaning'));
  wireControls();
  updateNow(0);
  const info = V.bundle.info || {};
  if (info.lanes_without_data && info.lanes_without_data.length) console.info('mvh viewer: lanes without data:', info.lanes_without_data.join(', '));
  requestDraw('all');
  if (V.mode === 'edit') setInterval(() => { fetch('api/ping', { cache: 'no-store' }).catch(() => {}); }, 15000);
}

function renderSingerChips() {
  const box = $('#singer-chips');
  if (!box) return;
  box.textContent = '';
  const M = V.model;
  for (const k of M.keys) {
    if (k === '-') continue;
    const isChar = M.characters.some((c) => c.id === k);
    box.append(h('span', { class: 'chip on static', style: { '--c': M.keyColour(k) } }, isChar ? `${k} ${M.charName(k)}` : k));
  }
}

function wireControls() {
  $('#btn-play').addEventListener('click', togglePlay);
  $('#src-sel').value = A.source === 'mix' ? 'mix' : 'preview';
  $('#src-sel').addEventListener('change', (e) => setSource(e.target.value));
  $('#rate-sel').addEventListener('change', (e) => setRate(Number(e.target.value)));
  $('#vol').addEventListener('input', (e) => { A.volume = Number(e.target.value); applyMixer(); });
  const m = (id, fn) => $(id).addEventListener('change', fn);
  m('#chk-metro', (e) => { setMetro({ on: e.target.checked }); lsSet('metro', e.target.checked); });
  m('#chk-beats', (e) => setMetro({ beats: e.target.checked }));
  m('#chk-down', (e) => setMetro({ downbeats: e.target.checked }));
  m('#chk-hits', (e) => setMetro({ hits: e.target.checked }));
  m('#chk-clicks', (e) => setMetro({ clicksOnly: e.target.checked }));
  $('#metro-vol').addEventListener('input', (e) => { A.metro.vol = Number(e.target.value); });
  $('#metro-off').addEventListener('input', (e) => { A.metro.offsetMs = Number(e.target.value); $('#metro-off-v').textContent = e.target.value + ' ms'; });
  $('#z-in').addEventListener('click', () => zoomAt(0.6, V.t));
  $('#z-out').addEventListener('click', () => zoomAt(1 / 0.6, V.t));
  $('#z-fit').addEventListener('click', fitAll);
  const fs = $('#follow-sel');
  fs.value = VW.follow;
  fs.addEventListener('change', (e) => { VW.follow = e.target.value; lsSet('follow', VW.follow); });
  $('#btn-loop').addEventListener('click', toggleLoop);
  $('#btn-panel').addEventListener('click', () => $('#side').classList.toggle('closed'));
  $$('#side .tab').forEach((b) => b.addEventListener('click', () => openTab(b.dataset.tab)));
  $('#progress').addEventListener('click', (e) => { const r = e.currentTarget.getBoundingClientRect(); seek((e.clientX - r.left) / r.width * V.model.duration); centreOn(V.t, true); });
  const ro = new ResizeObserver(() => { clearTimeout(wireControls._t); wireControls._t = setTimeout(sizeCanvases, 60); });
  ro.observe($('#lanes-wrap'));
  window.addEventListener('keydown', onKey);
}
function toggleLoop() {
  const b = $('#btn-loop');
  if (A.loop) { A.loop = null; b.classList.remove('on'); requestDraw('overview'); return; }
  const s = sectionAt(V.t);
  if (!s) { toast('Put the playhead inside a section to loop it'); return; }
  A.loop = { a: s.t, b: s.t + s.d };
  b.classList.add('on');
  toast(`Looping ${s.id}`);
  requestDraw('overview');
}
function stepBeat(dir) {
  const g = V.model.grid;
  if (!g.length) return;
  const i = L.nearestIndex(g, V.t);
  let j = i;
  if (dir > 0) { while (j < g.length - 1 && g[j].t <= V.t + 1e-3) j++; } else { while (j > 0 && g[j].t >= V.t - 1e-3) j--; }
  seek(g[j].t); ensureVisible(g[j].t, 0.2);
}
function stepSection(dir) {
  const ss = V.model.sections;
  if (!ss.length) return;
  let target = null;
  if (dir > 0) target = ss.find((s) => s.t > V.t + 0.05);
  else { const cur = ss.filter((s) => s.t < V.t - 0.5); target = cur[cur.length - 1] || ss[0]; }
  if (target) { selectSection(target.id); seek(target.t); ensureVisible(target.t, 0.1); }
}
function onKey(e) {
  const tag = (e.target.tagName || '').toLowerCase();
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
  const k = e.key;
  const step = e.shiftKey ? 5 : e.altKey ? 0.1 : 1;
  if (k === ' ') { e.preventDefault(); togglePlay(); }
  else if (k === 'ArrowLeft') { e.preventDefault(); seek(V.t - step); ensureVisible(V.t); }
  else if (k === 'ArrowRight') { e.preventDefault(); seek(V.t + step); ensureVisible(V.t); }
  else if (k === '[') stepSection(-1);
  else if (k === ']') stepSection(1);
  else if (k === ',') stepBeat(-1);
  else if (k === '.') stepBeat(1);
  else if (k === '+' || k === '=') zoomAt(0.7, V.t);
  else if (k === '-' || k === '_') zoomAt(1 / 0.7, V.t);
  else if (k === '0') fitAll();
  else if (k === 'f' || k === 'F') { const o = ['page', 'centre', 'off']; VW.follow = o[(o.indexOf(VW.follow) + 1) % 3]; $('#follow-sel').value = VW.follow; lsSet('follow', VW.follow); toast('Follow: ' + VW.follow); }
  else if (k === 'm' || k === 'M') { const c = $('#chk-metro'); c.checked = !c.checked; c.dispatchEvent(new Event('change')); }
  else if (k === 'l' || k === 'L') toggleLoop();
  else if ((k === 'e' || k === 'E') && V.mode === 'edit') openTab('edit');
  else if ((k === 'z' || k === 'Z') && (e.ctrlKey || e.metaKey) && V.mode === 'edit') { e.preventDefault(); Edit.undo(); }
  else if ((k === 'Delete' || k === 'Backspace') && V.mode === 'edit') {
    if (SEL.boundary != null) { Edit.removeBoundary(SEL.boundary); SEL.boundary = null; }
    else if (SEL.pin != null) Edit.removePin(SEL.pin);
  }
}

window.addEventListener('DOMContentLoaded', async () => {
  readTheme();
  try { matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => { setTimeout(() => { readTheme(); if (V.model) { for (const l of [VW.overview]) l.cache = null; requestDraw('all'); } }, 30); }); } catch (e) { /* old browser */ }
  try {
    await boot();
    initUI();
    document.body.classList.add('ready');
    if (V.ovrError) toast(V.ovrError, 'bad', 12000);
  } catch (e) { showFatal(e); }
});
