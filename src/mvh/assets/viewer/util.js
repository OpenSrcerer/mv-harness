/* DOM and colour helpers */
const L = MVHLOGIC;
const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === 'class') e.className = v;
      else if (k === 'style' && typeof v === 'object') Object.assign(e.style, v);
      else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
      else if (k === 'text') e.textContent = v;
      else if (v === true) e.setAttribute(k, '');
      else e.setAttribute(k, v);
    }
  }
  for (const k of kids.flat()) {
    if (k == null || k === false) continue;
    e.append(k.nodeType ? k : document.createTextNode(String(k)));
  }
  return e;
}
const clamp = L.clamp;
const fmtTime = L.fmtTime;
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function hexToRgb(hex) {
  let s = String(hex || '#888').replace('#', '');
  if (s.length === 3) s = s.split('').map((c) => c + c).join('');
  const n = parseInt(s, 16);
  return isNaN(n) ? [136, 136, 136] : [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function rgba(hex, a) { const c = hexToRgb(hex); return `rgba(${c[0]},${c[1]},${c[2]},${a})`; }
function mixHex(a, b, f) {
  const x = hexToRgb(a), y = hexToRgb(b);
  return '#' + [0, 1, 2].map((i) => Math.round(x[i] + (y[i] - x[i]) * f).toString(16).padStart(2, '0')).join('');
}

// ---- theme: read from CSS variables so canvases follow the light / dark scheme
const T = {};
function readTheme() {
  const cs = getComputedStyle(document.documentElement);
  const g = (n) => cs.getPropertyValue(n).trim();
  Object.assign(T, {
    bg: g('--bg'), panel: g('--panel'), lane: g('--lane'), laneAlt: g('--lane-alt'), grid: g('--grid'), gridStrong: g('--grid-strong'),
    text: g('--text'), dim: g('--dim'), faint: g('--faint'), accent: g('--accent'), warn: g('--warn'), bad: g('--bad'),
    good: g('--good'), play: g('--play'), edit: g('--edit'),
    bass: g('--bass'), mid: g('--mid'), high: g('--high'), light: g('--scheme') === 'light',
  });
}
// categorical colours for singers / characters / stems (distinct in both schemes)
const CAT = ['#4cc9f0', '#f72585', '#ffd166', '#80ed99', '#b79cff', '#ff9f1c', '#2ec4b6', '#ef476f', '#9bc53d', '#e29578'];
const STEM_COL = { lead_vocals: '#f72585', backing_vocals: '#c77dff', vocals: '#f72585', drums: '#ffd166', bass: '#4cc9f0', guitar: '#ff9f1c',
  piano: '#80ed99', other: '#b79cff', instrumental: '#8d99ae' };
const DRUM_COL = { kick: '#ff5d5d', snare: '#ffd166', hat: '#80ed99', tom: '#ff9f1c', cymbal: '#4cc9f0', perc: '#b79cff' };
const NOTE_COL = { bass: '#4cc9f0', piano: '#80ed99', guitar: '#ff9f1c', other: '#b79cff', vocals: '#f72585' };
const LEVEL_COL = { silence: '#222a38', quiet: '#2b4a6b', soft: '#356f91', medium: '#3f9b8f', loud: '#e0a43a', peak: '#e5533d' };
const VISEME_COL = { X: '#3a4256', A: '#ff6b6b', B: '#ffa94d', C: '#ffd43b', D: '#69db7c', E: '#38d9a9', F: '#4dabf7', G: '#9775fa', H: '#f06595' };
const SECTION_COL = { intro: '#5c7cfa', verse: '#22b8cf', 'pre-chorus': '#51cf66', chorus: '#fcc419', bridge: '#ff922b', outro: '#9775fa',
  drop: '#ff6b6b', build: '#f783ac', breakdown: '#74c0fc', instrumental: '#63e6be', solo: '#ffa94d', interlude: '#a9e34b' };
function sectionColour(label) {
  const k = String(label || '').toLowerCase();
  if (SECTION_COL[k]) return SECTION_COL[k];
  let hsh = 0; for (const ch of k) hsh = (hsh * 31 + ch.charCodeAt(0)) >>> 0;
  return CAT[hsh % CAT.length];
}
// perceptual-ish LUT for the spectrogram
const LUT = (() => {
  const stops = [[0, 6, 8, 20], [0.2, 38, 30, 110], [0.45, 130, 40, 140], [0.7, 226, 100, 60], [0.9, 250, 200, 80], [1, 255, 250, 220]];
  const out = new Uint8ClampedArray(256 * 3);
  for (let i = 0; i < 256; i++) {
    const v = i / 255;
    let k = 0; while (k < stops.length - 2 && v > stops[k + 1][0]) k++;
    const a = stops[k], b = stops[k + 1], f = clamp((v - a[0]) / (b[0] - a[0]), 0, 1);
    for (let c = 0; c < 3; c++) out[i * 3 + c] = a[c + 1] + (b[c + 1] - a[c + 1]) * f;
  }
  return out;
})();

function toast(msg, kind, ms) {
  const box = $('#toasts');
  if (!box) return;
  const t = h('div', { class: 'toast ' + (kind || '') }, msg);
  box.append(t);
  setTimeout(() => t.classList.add('out'), ms || 4200);
  setTimeout(() => t.remove(), (ms || 4200) + 400);
}
function lsGet(k, d) { try { const v = localStorage.getItem('mvh.viewer.' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } }
function lsSet(k, v) { try { localStorage.setItem('mvh.viewer.' + k, JSON.stringify(v)); } catch (e) { /* private window */ } }
