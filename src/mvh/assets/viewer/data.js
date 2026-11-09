/* Data access: lib/mvh.js loader (inline bundle through a fetch shim on file://, real fetch when served) + the derived model */
const V = {
  mode: 'file',          // 'file' (inline, read-only) | 'served' (fetch, read-only) | 'edit' (served by mvh view)
  mvh: null, song: null, bundle: null, edit: null, model: null, readJSON: null, fetchFn: null,
  hasSpectrogram: false, dirty: new Set(), t: 0,
};
const EVENT_NAMES = ['sections', 'phrases', 'beats', 'bars', 'counts', 'pulse_regions', 'tempo_segments', 'grooves', 'drum_hits', 'hit_points', 'holds',
  'onsets.bass', 'onsets.mid', 'onsets.high', 'hits.kick', 'hits.mid', 'hits.high', 'dynamics', 'impacts', 'stops', 'silences', 'decay_tails',
  'instruments', 'stem_activity', 'notes.bass', 'notes.piano', 'notes.guitar', 'notes.other', 'notes.vocals', 'chords', 'key', 'vocal_phrases',
  'vocal_style', 'voice_activity', 'voice_spans', 'singing', 'visemes', 'cues', 'moments', 'edm_roles', 'mood'];

function b64bytes(s) {
  const bin = atob(s), u = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
  return u;
}
async function inflate(u8) {
  const ds = new DecompressionStream('deflate');
  const w = ds.writable.getWriter();
  w.write(u8); w.close();
  return await new Response(ds.readable).arrayBuffer();
}
const SHIM_BASE = 'https://mvh-inline.invalid/';
function makeShim(files) {
  const cache = new Map();
  return async function shimFetch(url) {
    const u = new URL(url, SHIM_BASE);
    const rel = decodeURIComponent(u.pathname.replace(/^\//, ''));
    const ent = files[rel];
    if (!ent) return { status: 404, ok: false, text: async () => '', arrayBuffer: async () => new ArrayBuffer(0) };
    if (!cache.has(rel)) cache.set(rel, inflate(b64bytes(ent[2])));
    const buf = await cache.get(rel);
    return {
      status: 200, ok: true,
      text: async () => new TextDecoder('utf-8').decode(buf),
      arrayBuffer: async () => buf.slice(0),
    };
  };
}

async function importMvh() {
  const src = $('#mvh-src').textContent;
  const blob = new Blob([src], { type: 'text/javascript' });
  if (location.protocol.startsWith('http')) {
    try { return await import(new URL('lib/mvh.js', location.href).href); } catch (e) { /* no lib/ in this folder: use the inline copy */ }
  }
  const url = URL.createObjectURL(blob);
  try { return await import(url); } finally { setTimeout(() => URL.revokeObjectURL(url), 5000); }
}

async function boot() {
  const raw = $('#mvh-data').textContent;
  V.bundle = JSON.parse(raw);
  // ?inline=1 forces the file:// code path (inline bundle + fetch shim) when served, for testing
  const served = location.protocol.startsWith('http') && !/[?&]inline=1/.test(location.search);
  V.edit = served ? (window.MVH_EDIT || null) : null;
  V.mode = V.edit && served ? 'edit' : served ? 'served' : 'file';
  V.mvh = await importMvh();
  let base, fetchFn;
  if (V.mode === 'file') {
    fetchFn = makeShim(V.bundle.files);
    base = SHIM_BASE;
  } else {
    fetchFn = (u, o) => fetch(u, Object.assign({ cache: 'no-store' }, o || {}));
    base = new URL('./', location.href).href;
  }
  V.fetchFn = fetchFn;
  V.base = base;
  V.readJSON = async (rel) => {
    try {
      const r = await fetchFn(new URL(rel, base).href);
      if (!r.ok) return null;
      return JSON.parse(await r.text());
    } catch (e) { return null; }
  };
  const song = await V.mvh.load(base, { fetch: fetchFn });
  V.song = song;
  const idxFiles = Object.keys(song.index.files);
  // a real manifest lists what exists: only ask for that (no 404 noise); fixtures without one are probed
  const listed = new Set((song.manifest.files || []).map((f) => f.path));
  const has = (rel) => !listed.size || listed.has(rel);
  const names = song.eventNames.length ? song.eventNames : EVENT_NAMES;
  await Promise.all([
    song.ensure(names.map((n) => 'events:' + n)),
    song.ensure(['lyrics', 'meaning'].filter((k) => has(k === 'lyrics' ? 'lyrics/lyrics.json' : 'meaning/meaning.json'))),
    song.ensure(idxFiles.filter((f) => f !== 'spectrum128').map((f) => 'curves:' + f)),
  ]);
  // optional / degraded runs: an events file that does not exist reads as an empty list (never throws)
  for (const n of new Set([...EVENT_NAMES, ...names])) markAbsent('events:' + n);
  V.hasSpectrogram = idxFiles.includes('spectrum128');
  const meta = {};
  await Promise.all(['source', 'identity', 'tempo', 'loudness', 'vocal_range', 'voices', 'key', 'structure', 'instruments', 'stems', 'mood', 'separation', 'grooves']
    .map(async (k) => { meta[k] = has('meta/' + k + '.json') ? await V.readJSON('meta/' + k + '.json') : null; }));
  V.meta = meta;
  if (V.edit) {
    const o = await (await fetch('api/overrides', { cache: 'no-store' })).json();
    V.ovr = o.overrides || {}; V.ovrEtag = o.etag;
    V.ovrError = o.error || '';
    V.intent = await (await fetch('api/intent', { cache: 'no-store' })).json();
  }
  buildModel();
}

// ------------------------------------------------------------------------------------------------ model
function markAbsent(key) {
  // the viewer only ever asks for files it ensured; one that was not listed / not found counts as an empty file
  try { if (!V.song.isLoaded(key)) V.song._raw.set(key, null); } catch (e) { /* unknown key */ }
}
const ev = (name) => { markAbsent('events:' + name); return V.song.events(name); };
const items = (name) => ev(name).items;
const hasCurve = (id) => V.song.hasCurve(id);
const curve = (id) => (V.song.hasCurve(id) ? V.song.curve(id) : null);

function appliedOverrides(evName) {
  // the override values a stage reports having applied (provenance.overrides_applied)
  const out = {};
  const prov = (evName === 'lyrics' ? (rawGet('lyrics') || {}).provenance : ev(evName).provenance) || {};
  // a key may repeat (one entry per edit, e.g. structure.boundaries before structure 1.2.0): repeated keys collect
  // their values into one list, plain-object maps (lyrics.lines) merge (F-R5-APPLIED-BOUNDARY)
  const plain = (x) => x != null && typeof x === 'object' && !Array.isArray(x);
  const listy = { 'structure.boundaries': 1, 'structure.labels': 1 };
  for (const o of prov.overrides_applied || []) {
    const k = o.key, v = o.value;
    if (!(k in out)) out[k] = listy[k] ? [].concat(v == null ? [] : v) : v;
    else if (listy[k] || Array.isArray(out[k])) out[k] = [].concat(out[k], v == null ? [] : v);
    else if (plain(out[k]) && plain(v)) out[k] = Object.assign({}, out[k], v);
    else out[k] = v;
  }
  return out;
}

function buildModel() {
  const S = V.song, M = {};
  V.model = M;
  M.duration = S.duration || V.bundle.duration || 0;
  const src = V.meta.source || {}, idn = V.meta.identity || {};
  M.title = idn.title || (src.tags || {}).title || V.bundle.title || V.bundle.slug;
  M.artist = idn.artist || (src.tags || {}).artist || '';
  M.sections = items('sections').slice().sort((a, b) => a.t - b.t);
  const lyr = rawGet('lyrics') || {};
  M.lyrics = lyr;
  M.lines = (lyr.lines || []).slice().sort((a, b) => a.t - b.t);
  M.wordsByLine = new Map();
  for (const w of lyr.words || []) {
    if (!M.wordsByLine.has(w.line_id)) M.wordsByLine.set(w.line_id, []);
    M.wordsByLine.get(w.line_id).push(w);
  }
  for (const a of M.wordsByLine.values()) a.sort((x, y) => x.t - y.t);
  M.meaning = rawGet('meaning') || null;
  M.meaningSections = new Map(((M.meaning || {}).sections || []).map((s) => [s.section_id, s]));
  M.characters = (M.meaning || {}).characters || [];
  const vm = V.meta.voices || {};
  M.voices = (vm.voices || []).slice();
  // singers per line: singing.json, else voice_spans
  M.singers = new Map();
  for (const s of items('singing')) {
    if (!M.singers.has(s.line_id)) M.singers.set(s.line_id, []);
    M.singers.get(s.line_id).push(s);
  }
  M.voiceOfLine = new Map();
  for (const s of items('voice_spans')) M.voiceOfLine.set(s.line_id, s.voice_id);
  for (const [lid, arr] of M.singers) if (!M.voiceOfLine.has(lid) && arr[0]) M.voiceOfLine.set(lid, arr[0].voice_id);
  const charOfVoice = new Map();
  for (const c of M.characters) for (const v of c.voice_ids || []) if (!charOfVoice.has(v)) charOfVoice.set(v, c.id);
  for (const v of M.voices) if (v.proposed_character_id && !charOfVoice.has(v.id)) charOfVoice.set(v.id, v.proposed_character_id);
  M.charOfVoice = charOfVoice;
  M.charName = (id) => { const c = M.characters.find((x) => x.id === id); return c ? c.name : id; };
  // colour key per line: character > voice > speaker hint
  const keys = [];
  const keyOf = (ln) => {
    const sg = M.singers.get(ln.id);
    if (sg && sg.length) return sg[0].character_id || sg[0].voice_id;
    const v = M.voiceOfLine.get(ln.id);
    if (v) return charOfVoice.get(v) || v;
    return ln.speaker_hint || '-';
  };
  M.lineKey = new Map();
  for (const ln of M.lines) { const k = keyOf(ln); M.lineKey.set(ln.id, k); if (!keys.includes(k)) keys.push(k); }
  for (const c of M.characters) if (!keys.includes(c.id)) keys.push(c.id);
  for (const v of M.voices) if (!keys.includes(v.id) && !charOfVoice.has(v.id)) keys.push(v.id);
  M.keys = keys;
  M.keyColour = (k) => (k === '-' ? '#7a8499' : CAT[Math.max(0, keys.indexOf(k)) % CAT.length]);
  M.rowOfLine = (ln) => {
    const v = M.voiceOfLine.get(ln.id);
    const vs = M.voices.map((x) => x.id);
    if (vs.length > 1 && v) return Math.max(0, vs.indexOf(v));
    return 0;
  };
  M.nRows = Math.max(1, M.voices.length > 1 ? M.voices.length : 1);
  rebuildGrid();
  M.tempo = V.meta.tempo || {};
  M.cues = items('cues');
}

/** the (possibly preview-edited) beat grid; pending rhythm edits are shown before the stages re-run */
function rebuildGrid() {
  const M = V.model, base = items('beats');
  const applied = appliedOverrides('beats');
  const o = (V.ovr || {}).rhythm || {};
  const baseBpm = (V.meta.tempo || {}).bpm;
  M.gridPending = false;
  const q = {
    offset: o.beat_offset_s != null ? o.beat_offset_s : (applied['rhythm.beat_offset_s'] || 0), appliedOffset: applied['rhythm.beat_offset_s'] || 0,
    bpm: o.bpm != null ? o.bpm : null, baseBpm: applied['rhythm.bpm'] != null ? applied['rhythm.bpm'] : baseBpm,
    phase: o.downbeat_phase != null ? o.downbeat_phase : (applied['rhythm.downbeat_phase'] || 0), appliedPhase: applied['rhythm.downbeat_phase'] || 0,
    duration: M.duration,
  };
  if (q.bpm != null && applied['rhythm.bpm'] != null && Math.abs(q.bpm - applied['rhythm.bpm']) < 0.01) q.bpm = null;
  if (q.bpm != null && applied['rhythm.bpm'] == null && Math.abs(q.bpm - (baseBpm || 0)) < 0.01) q.bpm = null;
  M.gridOpts = q;
  M.applied = applied;
  if (Math.abs(q.offset - q.appliedOffset) > 1e-6 || q.bpm != null || q.phase !== q.appliedPhase) {
    M.grid = L.previewGrid(base, q);
    M.gridPending = true;
  } else M.grid = base;
  M.downbeats = M.grid.filter((b) => b.beat_in_bar === 1);
}

function sectionAt(t) { const i = L.sectionIndexAt(V.model.sections, t); return i < 0 ? null : V.model.sections[i]; }
function lineAt(t) {
  const ls = V.model.lines;
  let r = null;
  for (const l of ls) { if (l.t <= t && t < l.t + (l.d || 0.01)) r = l; else if (l.t > t) break; }
  return r;
}
function stemsAvailable() { return V.bundle.stems || []; }
/** lyrics / meaning when the folder has them (null when the file is not listed and was never requested) */
function rawGet(key) { try { return V.song._get(key); } catch (e) { return null; } }
