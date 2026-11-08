/* Playback: mix (or preview.opus) through <audio>, optional per-stem mixer, click-track metronome (WebAudio) */
const MIXER_STEMS = ['lead_vocals', 'backing_vocals', 'drums', 'bass', 'guitar', 'piano', 'other'];
const A = {
  el: null, stemEls: {}, stemState: {},   // stemState[name] = {mute, solo}
  source: 'mix', playing: false, rate: 1, volume: 0.9, musicOn: true,
  ctx: null, master: null, lastCT: 0, lastPerf: 0, loop: null,
  metro: { on: false, beats: true, downbeats: true, hits: false, vol: 0.6, offsetMs: 0, nextIdx: 0, timer: null, lastT: -1 },
  mixer: false, failed: false,
};

function audioUrl(rel) { return new URL(rel, V.mode === 'file' ? location.href : V.base).href; }

function initAudio() {
  const el = new Audio();
  el.preload = 'auto';
  A.el = el;
  el.addEventListener('error', onAudioError);
  el.addEventListener('ended', () => { setPlaying(false); });
  el.addEventListener('timeupdate', () => { A.lastCT = el.currentTime; A.lastPerf = performance.now(); });
  el.addEventListener('seeked', () => { A.lastCT = el.currentTime; A.lastPerf = performance.now(); requestDraw('playhead'); });
  setSource(lsGet('source', 'mix'), true);
}

function onAudioError() {
  // chain: mix.flac -> preview.opus (relative file) -> inline preview blob -> give up
  const el = A.el;
  const cur = el.dataset.src || '';
  const t = el.currentTime || 0;
  if (cur === 'mix') return loadSrc('preview', t);
  if (cur === 'preview' && V.bundle.audio_preview && !el.dataset.inline) return loadSrc('inline', t);
  A.failed = true;
  toast('Audio could not be loaded. The viewer still shows every lane; put the audio/ folder next to viewer.html to listen.', 'warn', 7000);
  setPlaying(false);
}
function loadSrc(kind, t) {
  const el = A.el;
  const was = A.playing;
  el.dataset.src = kind === 'inline' ? 'preview' : kind;
  if (kind === 'inline') {
    el.dataset.inline = '1';
    el.src = URL.createObjectURL(new Blob([b64bytes(V.bundle.audio_preview)], { type: 'audio/ogg' }));
  } else {
    delete el.dataset.inline;
    el.src = audioUrl(kind === 'mix' ? 'audio/mix.flac' : 'audio/preview.opus');
  }
  el.playbackRate = A.rate;
  el.currentTime = t || 0;
  A.failed = false;
  if (was) el.play().catch(() => {});
  const sel = $('#src-sel');
  if (sel) sel.value = kind === 'mix' ? 'mix' : 'preview';
}
function setSource(kind, silent) {
  A.source = kind;
  lsSet('source', kind);
  loadSrc(kind, silent ? 0 : A.el.currentTime);
}

function setPlaying(p) {
  if (p && A.failed) { toast('No audio loaded', 'warn'); p = false; }
  A.playing = p;
  const el = A.el;
  if (p) {
    ensureCtx();
    if (A.ctx && A.ctx.state === 'suspended') A.ctx.resume();
    el.play().catch((e) => { A.playing = false; updatePlayButton(); toast('Playback blocked: ' + (e && e.name), 'warn'); });
    for (const n of activeStemNames()) { const s = A.stemEls[n]; if (s) { s.currentTime = el.currentTime; s.play().catch(() => {}); } }
    resetMetro();
  } else {
    el.pause();
    for (const s of Object.values(A.stemEls)) s.pause();
  }
  updatePlayButton();
  if (p) { A.lastCT = el.currentTime; A.lastPerf = performance.now(); requestDraw('playhead'); }
}
function togglePlay() { setPlaying(!A.playing); }

/** current media time, interpolated between the (coarse) currentTime updates */
function now() {
  const el = A.el;
  if (!el) return V.t;
  if (!A.playing) return el.currentTime;
  const dt = (performance.now() - A.lastPerf) / 1000 * A.rate;
  const ct = el.currentTime;
  if (ct !== A.lastCT) { A.lastCT = ct; A.lastPerf = performance.now(); return ct; }
  return A.lastCT + Math.min(dt, 0.25);
}
function seek(t, keepPlaying) {
  t = clamp(t, 0, Math.max(0, V.model.duration - 0.001));
  A.el.currentTime = t;
  A.lastCT = t; A.lastPerf = performance.now();
  for (const s of Object.values(A.stemEls)) s.currentTime = t;
  V.t = t;
  resetMetro();
  requestDraw('playhead');
}
function setRate(r) {
  A.rate = r;
  A.el.playbackRate = r;
  for (const s of Object.values(A.stemEls)) s.playbackRate = r;
  resetMetro();
}

// ---------------------------------------------------------------------------------------- stems
function stemUrl(n) { return audioUrl('stems/' + n + '.flac'); }
function ensureStems() {
  for (const n of MIXER_STEMS) {
    if (A.stemEls[n] || !stemsAvailable().includes(n)) continue;
    const s = new Audio();
    s.preload = 'auto';
    s.src = stemUrl(n);
    s.playbackRate = A.rate;
    s.addEventListener('error', () => { s.dataset.bad = '1'; });
    A.stemEls[n] = s;
    A.stemState[n] = A.stemState[n] || { mute: false, solo: false };
  }
}
function activeStemNames() {
  if (!A.mixer) return [];
  const st = A.stemState;
  const anySolo = Object.values(st).some((s) => s.solo);
  return Object.keys(A.stemEls).filter((n) => (anySolo ? st[n].solo : !st[n].mute));
}
function mixerEngaged() {
  const st = Object.values(A.stemState);
  return st.some((s) => s.solo || s.mute);
}
function applyMixer() {
  const engaged = mixerEngaged();
  if (engaged && !A.mixer) { ensureStems(); A.mixer = true; for (const s of Object.values(A.stemEls)) s.currentTime = A.el.currentTime; }
  if (!engaged) A.mixer = false;
  const act = new Set(activeStemNames());
  A.el.muted = A.mixer || !A.musicOn;
  for (const [n, s] of Object.entries(A.stemEls)) {
    s.volume = A.volume;
    s.muted = !(A.mixer && A.musicOn && act.has(n));
    if (A.playing && A.mixer && act.has(n) && s.paused) { s.currentTime = A.el.currentTime; s.play().catch(() => {}); }
    if (!A.mixer && !s.paused) s.pause();
  }
  A.el.volume = A.volume;
  updateStemButtons();
}
function toggleStem(n, what) {
  ensureStems();
  const s = A.stemState[n] || (A.stemState[n] = { mute: false, solo: false });
  s[what] = !s[what];
  if (what === 'solo' && s.solo) s.mute = false;
  applyMixer();
}
function clearStems() { for (const s of Object.values(A.stemState)) { s.mute = false; s.solo = false; } applyMixer(); }
function syncStems() {
  if (!A.mixer || !A.playing) return;
  const t = A.el.currentTime;
  for (const [n, s] of Object.entries(A.stemEls)) {
    if (s.paused || s.dataset.bad) continue;
    const d = s.currentTime - t;
    if (Math.abs(d) > 0.045) s.currentTime = t + 0.02 * A.rate;
  }
}

// ---------------------------------------------------------------------------------------- metronome
function ensureCtx() {
  if (A.ctx) return;
  try {
    const AC = window.AudioContext || window.webkitAudioContext;
    A.ctx = new AC({ latencyHint: 'interactive' });
    A.master = A.ctx.createGain();
    A.master.gain.value = 1;
    A.master.connect(A.ctx.destination);
  } catch (e) { A.ctx = null; }
}
function resetMetro() {
  A.metro.lastT = now() - 0.001;
}
function click(when, kind, vel) {
  const c = A.ctx;
  if (!c) return;
  const g = c.createGain();
  const o = c.createOscillator();
  const spec = {
    down: [1760, 0.06, 1.0, 'square'], beat: [1180, 0.04, 0.7, 'square'],
    kick: [90, 0.12, 1.0, 'sine'], snare: [240, 0.09, 0.8, 'triangle'], hat: [7000, 0.03, 0.35, 'square'],
    tom: [140, 0.1, 0.8, 'sine'], cymbal: [5200, 0.14, 0.3, 'square'], perc: [900, 0.04, 0.5, 'triangle'],
  }[kind] || [1000, 0.04, 0.6, 'square'];
  o.type = spec[3];
  o.frequency.setValueAtTime(spec[0], when);
  if (kind === 'kick') o.frequency.exponentialRampToValueAtTime(45, when + spec[1]);
  const peak = A.metro.vol * spec[2] * (vel == null ? 1 : 0.35 + 0.65 * vel) * 0.5;
  g.gain.setValueAtTime(0.0001, when);
  g.gain.exponentialRampToValueAtTime(Math.max(0.0002, peak), when + 0.002);
  g.gain.exponentialRampToValueAtTime(0.0001, when + spec[1]);
  o.connect(g); g.connect(A.master);
  o.start(when); o.stop(when + spec[1] + 0.02);
}
/** the scheduler: every 25 ms it schedules the clicks that fall into the next 150 ms of music time */
function metroTick() {
  const m = A.metro;
  if (!A.playing || !m.on || !A.ctx || A.ctx.state !== 'running') return;
  const tNow = now();
  const ahead = 0.15 * A.rate;
  let t0 = m.lastT;
  if (t0 < tNow - 0.3 || t0 > tNow + 1) t0 = tNow - 0.01;
  const t1 = tNow + ahead;
  const ts = A.ctx.getOutputTimestamp ? A.ctx.getOutputTimestamp() : null;
  const ctxNow = A.ctx.currentTime;
  const toCtx = (mt) => ctxNow + (mt - tNow) / A.rate + m.offsetMs / 1000;
  const emit = (arr, fn) => {
    let i = L.nearestIndex(arr, t0);
    if (i < 0) return;
    while (i > 0 && arr[i - 1].t > t0) i--;
    for (; i < arr.length && arr[i].t < t1; i++) if (arr[i].t > t0) fn(arr[i]);
  };
  if (m.beats || m.downbeats) {
    emit(V.model.grid, (b) => {
      if (!b.in_pulse && V.model.grid === V.model.grid) { /* virtual beats still click, quieter */ }
      const down = b.beat_in_bar === 1;
      if (down && m.downbeats) click(toCtx(b.t), 'down', b.in_pulse ? 1 : 0.5);
      else if (m.beats) click(toCtx(b.t), 'beat', b.in_pulse ? 1 : 0.4);
    });
  }
  if (m.hits) emit(items('drum_hits'), (h2) => click(toCtx(h2.t), h2.drum, h2.vel));
  m.lastT = t1;
}
function setMetro(patch) {
  Object.assign(A.metro, patch);
  if (A.metro.on) ensureCtx();
  if (A.metro.timer == null) A.metro.timer = setInterval(metroTick, 25);
  resetMetro();
  const musicWanted = !(A.metro.on && A.metro.clicksOnly);
  A.musicOn = musicWanted;
  applyMixer();
}
function updatePlayButton() {
  const b = $('#btn-play');
  if (b) { b.textContent = A.playing ? 'Pause' : 'Play'; b.classList.toggle('on', A.playing); }
}
function updateStemButtons() {
  for (const n of MIXER_STEMS) {
    const st = A.stemState[n] || {};
    $$(`[data-stem="${n}"][data-act="solo"]`).forEach((b) => b.classList.toggle('on', !!st.solo));
    $$(`[data-stem="${n}"][data-act="mute"]`).forEach((b) => b.classList.toggle('on', !!st.mute));
  }
  const clr = $('#btn-clear-stems');
  if (clr) clr.hidden = !mixerEngaged();
}
function loopTick() {
  const lp = A.loop;
  if (!lp || !A.playing) return;
  if (V.t >= lp.b - 0.005 || V.t < lp.a - 0.5) seek(lp.a);
}
