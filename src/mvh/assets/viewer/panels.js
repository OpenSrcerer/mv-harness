/* Side panels (Meaning, Values, Help), the "now" bar, selection */
const SEL = { sectionId: null, lineId: null, wordId: null, boundary: null, pin: null };
const E = { dragB: null, lineDrag: null, wordDrag: null };
const FR = { fps: lsGet('fps', '24'), frame0: lsGet('frame0', 0), early: lsGet('early', false) };

function selectSection(id) { SEL.sectionId = id; requestDraw('sections'); renderMeaning(); if (typeof Edit !== 'undefined') Edit.refreshPanel(); }
function selectLine(id) { SEL.lineId = id; SEL.wordId = null; requestDraw('lyrics'); if (typeof Edit !== 'undefined') Edit.refreshPanel(); }
function openTab(name) {
  $$('#side .tab').forEach((b) => b.classList.toggle('on', b.dataset.tab === name));
  $$('#side .pane').forEach((p) => { p.hidden = p.dataset.pane !== name; });
  $('#side').classList.remove('closed');
  lsSet('tab', name);
  if (name === 'values') updateValues(true);
}
function frameRule() {
  let fps = FR.fps;
  if (typeof fps === 'string' && fps.includes('/')) { const [a, b] = fps.split('/').map(Number); fps = [a, b]; } else fps = Number(fps) || 24;
  return { fps, frame0: Number(FR.frame0) || 0, early: !!FR.early };
}

// ------------------------------------------------------------------------------------------------ now bar
let _nowCache = {};
function setText(id, text) {
  if (_nowCache[id] === text) return;
  _nowCache[id] = text;
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}
function updateNow(t) {
  const M = V.model;
  if (!M) return;
  const fr = frameRule();
  let n = 0;
  try { n = V.mvh.frameOf(t, fr); } catch (e) { /* */ }
  setText('now-time', fmtTime(t, 3));
  setText('now-frame', 'frame ' + n + ' @ ' + (Array.isArray(fr.fps) ? fr.fps.join('/') : fr.fps) + ' fps');
  // rhythm
  let rh = '-';
  try {
    if (M.grid.length) {
      const bp = V.mvh.beatPos(t, M.grid), ph = V.mvh.barPhase(t, M.grid);
      const bi = Math.floor(bp.value);
      const b = M.grid[clamp(bi, 0, M.grid.length - 1)];
      const ct = V.mvh.countAt(t, M.grid, items('counts'));
      rh = `bar ${b.bar}  beat ${b.beat_in_bar}/${b.beats_in_bar}` + (ct.count != null ? `   count ${ct.count}${ct.eight_id ? ' (' + ct.eight_id + ')' : ''}` : '') + (b.in_pulse && bp.in_pulse ? '' : '   off-pulse');
    }
  } catch (e) { rh = 'rhythm n/a'; }
  setText('now-rhythm', rh);
  const s = sectionAt(t);
  setText('now-section', s ? `${s.id} ${s.occurrence_label || s.label}` : '-');
  const ms = s ? M.meaningSections.get(s.id) : null;
  setText('now-feel', ms ? (ms.feel || '') : '');
  // lyric + karaoke
  const ln = lineAt(t);
  const box = $('#now-line');
  const sig = ln ? ln.id + ':' + (L.wordIndexAt(M.wordsByLine.get(ln.id) || [], t)) : '-';
  if (_nowCache.lyric !== sig) {
    _nowCache.lyric = sig;
    box.textContent = '';
    if (ln) {
      const ws = M.wordsByLine.get(ln.id) || [];
      const wi = L.wordIndexAt(ws, t);
      if (ws.length) ws.forEach((w, i) => box.append(h('span', { class: 'w' + (i < wi ? ' done' : i === wi ? ' cur' : '') }, w.text, ' ')));
      else box.append(ln.text);
      const sg = M.singers.get(ln.id);
      const who = sg && sg.length ? sg.map((x) => M.charName(x.character_id) || x.voice_id).join(' + ') : (M.voiceOfLine.get(ln.id) || ln.speaker_hint || '');
      if (who) box.append(h('span', { class: 'who', style: { background: M.keyColour(M.lineKey.get(ln.id)) } }, who));
    } else box.append(h('span', { class: 'dim' }, M.lines.length ? '—' : 'no lyrics'));
  }
  // vocal
  let vt = '-';
  try {
    if (hasCurve('vocal.midi')) {
      const vv = V.song.vocalAt(t);
      vt = vv.voiced ? `${L.midiName(vv.midi)}  ${vv.hz.toFixed(0)} Hz  p01 ${vv.pitch01.toFixed(2)}` : 'unvoiced';
    }
  } catch (e) { vt = '-'; }
  setText('now-vocal', vt);
  const st = curve('loud.short_term_lufs');
  const dy = ev('dynamics').at(t);
  setText('now-loud', (st ? st.at(t).toFixed(1) + ' LUFS' : '-') + (dy ? '  ' + dy.item.level : ''));
  const nx = ev('cues').next(t, { minTier: 2 });
  setText('now-cue', nx ? `next ${nx.kind.replace('_', ' ')} in ${(nx.t - t).toFixed(1)} s` : '');
  const pf = $('#progress-fill');
  if (pf) pf.style.width = (t / Math.max(1, M.duration) * 100).toFixed(2) + '%';
  if (!$('#pane-values').hidden) updateValues(false);
}

// ------------------------------------------------------------------------------------------------ meaning pane
function chip(text, cls) { return h('span', { class: 'pill ' + (cls || '') }, text); }
function field(label, value) { return value == null || value === '' ? document.createDocumentFragment() : h('div', { class: 'kv' }, h('span', { class: 'k' }, label), h('span', { class: 'v' }, value)); }
function renderMeaning() {
  const host = $('#pane-meaning');
  if (!host || !V.model) return;
  const M = V.model, m = M.meaning;
  host.textContent = '';
  if (!m) {
    host.append(h('h3', null, 'Meaning is pending'),
      h('p', { class: 'dim' }, 'The meaning stage has no output for this song yet. The harness asks the questions in meaning/interview.md; answer them in meaning/intent.md (free text) and run mvh meaning. The user is the authority on what a song means; any draft is labelled as such.'),
      V.mode === 'edit' ? h('p', null, 'In edit mode you can write per-section meaning and map voices to characters on the ', h('a', { href: '#', onclick: (e) => { e.preventDefault(); openTab('edit'); } }, 'Edit tab'), '.') : h('p', { class: 'dim' }, 'Open this song with mvh view to write meaning notes here.'));
    return;
  }
  const status = m.status || 'pending';
  host.append(h('div', { class: 'row-between' }, h('h3', null, 'What the song means'), chip(status, status === 'user' ? 'good' : status === 'draft' ? 'warn' : '')));
  if (status === 'draft') host.append(h('p', { class: 'note warn' }, 'This is a DRAFT filled in by an agent or LLM. It has not been confirmed by the user.'));
  if (m.logline) host.append(h('p', { class: 'logline' }, m.logline));
  if (m.summary) host.append(h('p', null, m.summary));
  host.append(field('tone', m.tone), field('setting', m.setting));
  if (m.perspective && (m.perspective.narrator || m.perspective.addressee)) host.append(field('perspective', `narrator ${m.perspective.narrator ? M.charName(m.perspective.narrator) : '-'} → addressee ${m.perspective.addressee ? M.charName(m.perspective.addressee) : '-'}`));
  if ((m.themes || []).length) host.append(h('h4', null, 'Themes'), h('ul', null, m.themes.map((t) => h('li', null, t.text, ' ', chip(t.source || t.status || '', '')))));
  if ((m.palette || []).length) host.append(h('h4', null, 'Palette'), h('div', { class: 'swatches' }, m.palette.map((c) => h('span', { class: 'sw', style: { background: c }, title: c }))));
  if (M.characters.length) {
    host.append(h('h4', null, 'Characters'));
    for (const c of M.characters) {
      host.append(h('div', { class: 'card', style: { borderLeftColor: M.keyColour(c.id) } },
        h('div', { class: 'row-between' }, h('b', null, `${c.id} ${c.name}`), h('span', { class: 'dim' }, `${(c.voice_ids || []).join(', ') || 'no voice'} · ${c.lead_backing || ''}`)),
        c.description ? h('div', { class: 'dim' }, c.description) : null,
        h('div', { class: 'dim small' }, `${(c.line_ids || []).length} lines · sections ${(c.section_ids || []).join(' ')}`)));
    }
  }
  if ((m.motifs || []).length) host.append(h('h4', null, 'Motifs'), h('ul', null, m.motifs.map((x) => h('li', null, h('b', null, x.id + ' ' + x.name), ` · ${(x.occurrences || []).length} occurrences`))));
  if ((m.symbolism || []).length) host.append(h('h4', null, 'Symbolism'), h('ul', null, m.symbolism.map((x) => h('li', null, x.text))));
  if ((m.do_not || []).length) host.append(h('h4', null, 'Never show'), h('ul', { class: 'donot' }, m.do_not.map((x) => h('li', null, x))));
  if ((m.open_questions || []).length) host.append(h('h4', null, 'Open questions'), h('ul', null, m.open_questions.map((x) => h('li', null, typeof x === 'string' ? x : (x.question || x.text || JSON.stringify(x))))));
  host.append(h('h4', null, 'Sections'));
  for (const s of M.sections) {
    const ms = M.meaningSections.get(s.id);
    const card = h('div', { class: 'card sec' + (SEL.sectionId === s.id ? ' sel' : ''), id: 'msec-' + s.id, style: { borderLeftColor: sectionColour(s.label) }, onclick: () => { selectSection(s.id); seek(s.t); ensureVisible(s.t, 0.05); } },
      h('div', { class: 'row-between' }, h('b', null, `${s.id} ${s.occurrence_label || s.label}`), h('span', { class: 'dim small' }, `${fmtTime(s.t, 1)} - ${fmtTime(s.t + s.d, 1)}`)));
    if (ms) {
      card.append(field('feel', ms.feel), field('meaning', ms.meaning), field('movement', ms.movement_hint), field('camera', ms.camera_hint));
      if (ms.emotion) card.append(field('emotion', `lyric ${ms.emotion.lyric || '-'} / audio ${ms.emotion.audio || '-'} ${ms.emotion.agree === false ? '(disagree)' : ''}`));
      if ((ms.palette_hint || []).length) card.append(h('div', { class: 'swatches' }, ms.palette_hint.map((c) => h('span', { class: 'sw', style: { background: c }, title: c }))));
      if ((ms.characters_present || []).length) card.append(field('characters', ms.characters_present.map((c) => M.charName(c)).join(', ')));
      if ((ms.do_not || []).length) card.append(field('do not', ms.do_not.join('; ')));
      if (ms.provenance) card.append(h('div', { class: 'dim small' }, `source ${ms.provenance.source || '-'} · ${ms.provenance.status || '-'}`));
    } else card.append(h('div', { class: 'dim' }, 'no meaning entry for this section'));
    host.append(card);
  }
  if (SEL.sectionId) { const el = $('#msec-' + SEL.sectionId); if (el) el.scrollIntoView({ block: 'nearest' }); }
}

// ------------------------------------------------------------------------------------------------ values pane
const VAL_CHANNELS = ['bands.bass', 'bands.mid', 'bands.high', 'bands.kick', 'hits.kick', 'loud.short_term', 'loud.short_term_lufs', 'dyn.intensity', 'vocal.pitch01', 'vocal.mouth_open',
  'choreo.movement', 'choreo.accent', 'rhythm.in_pulse', 'tempo.bpm'];
let _valT = 0;
function buildValuesPane() {
  const host = $('#pane-values');
  host.textContent = '';
  const sel = h('select', { id: 'fr-fps', onchange: (e) => { FR.fps = e.target.value; lsSet('fps', FR.fps); updateValues(true); updateNow(V.t); } },
    ['24', '24000/1001', '25', '30', '30000/1001', '48', '50', '60'].map((v) => h('option', { value: v, selected: v === String(FR.fps) }, v.includes('/') ? v.replace('24000/1001', '23.976 (24000/1001)').replace('30000/1001', '29.97 (30000/1001)') : v + ' fps')));
  host.append(h('h3', null, 'Values at this frame'),
    h('p', { class: 'dim small' }, 'The same frame rule and helpers a video agent would use (lib/mvh.js): numbers are what curve.frame(n, fr) and the event helpers return.'),
    h('div', { class: 'form-row' }, h('label', null, 'fps ', sel),
      h('label', null, 'frame0 ', h('input', { type: 'number', min: 0, max: 1, step: 1, value: FR.frame0, style: { width: '3.2em' }, onchange: (e) => { FR.frame0 = Number(e.target.value) || 0; lsSet('frame0', FR.frame0); updateValues(true); } })),
      h('label', null, h('input', { type: 'checkbox', checked: FR.early, onchange: (e) => { FR.early = e.target.checked; lsSet('early', FR.early); updateValues(true); } }), ' early')),
    h('div', { id: 'val-table' }));
}
function updateValues(force) {
  const nowMs = performance.now();
  if (!force && nowMs - _valT < 100) return;
  _valT = nowMs;
  const box = $('#val-table');
  if (!box || !V.model) return;
  const fr = frameRule(), t = V.t, mv = V.mvh;
  const n = mv.frameOf(t, fr);
  const rows = [['frame n', n], ['time_of(n)', mv.timeOf(n, fr).toFixed(4) + ' s'], ['t', t.toFixed(4) + ' s']];
  for (const id of VAL_CHANNELS) { const c = curve(id); if (c) rows.push([id, c.frame(n, fr).toFixed(3)]); }
  try { const ct = mv.countAt(t, V.model.grid, items('counts')); rows.push(['count', ct.count == null ? '-' : `${ct.count} sub ${ct.sub} accent ${ct.accent.toFixed(2)} ${ct.eight_id || ''}${ct.partial ? ' partial' : ''}`]); } catch (e) { /* */ }
  try { const bp = mv.beatPos(t, V.model.grid); rows.push(['beatPos', bp.value.toFixed(3) + (bp.in_pulse ? '' : ' (off-pulse)')]); } catch (e) { /* */ }
  try { const sg = V.song.singerAt(t); rows.push(['singerAt', sg.length ? sg.map((x) => `${x.character_id || '?'}/${x.voice_id} mouth ${x.mouth_open.toFixed(2)}`).join(', ') : 'none']); } catch (e) { /* */ }
  const pulseKick = (() => { try { return V.song.pulse('hits.kick', t, { decay: 0.12 }).toFixed(3); } catch (e) { return null; } })();
  if (pulseKick != null) rows.push(['pulse(kick, 0.12 s)', pulseKick]);
  const tbl = h('table', { class: 'vals' }, rows.map(([k, v]) => h('tr', null, h('td', { class: 'k' }, k), h('td', { class: 'v' }, String(v)))));
  box.textContent = '';
  box.append(tbl);
}

// ------------------------------------------------------------------------------------------------ help
function buildHelp() {
  const keys = [['Space', 'play / pause'], ['← →', 'seek 1 s (Shift 5 s, Alt 0.1 s)'], ['[ ]', 'previous / next section'], [', .', 'previous / next beat'], ['+ -', 'zoom in / out around the playhead'],
    ['0', 'fit the whole song'], ['F', 'cycle follow: page / centre / off'], ['M', 'metronome on / off'], ['L', 'loop the current section'], ['Ctrl+wheel', 'zoom at the pointer'], ['Shift+wheel / drag', 'pan the time axis'],
    ['click', 'seek to the clicked time'], ['E', 'edit panel (edit mode only)'], ['Ctrl+Z', 'undo the last correction (edit mode)'], ['Delete', 'remove the selected boundary or pin (edit mode)']];
  $('#pane-help').append(h('h3', null, 'Keys'), h('table', { class: 'vals' }, keys.map(([k, v]) => h('tr', null, h('td', { class: 'k' }, k), h('td', { class: 'v' }, v)))),
    h('h3', null, 'Modes'),
    h('p', { class: 'dim' }, V.mode === 'edit' ? 'EDIT MODE: served by mvh view on 127.0.0.1. Corrections are saved to overrides.json (and meaning/intent.md); the Edit tab lists the stages that will re-run.' : V.mode === 'served' ? 'Served read-only (no edit server).' : 'Opened from the disk: read-only. Preview data is inlined. Run mvh view <song> to correct beats, sections, lyrics, singers and meaning.'),
    h('p', { class: 'dim small' }, 'Playback uses audio/mix.flac (or audio/preview.opus) next to this file. Stem solo/mute plays the stem files together with the mix muted; drift is corrected every 250 ms, so use it for listening checks, not sample-exact work. The click track is generated in the browser from the beat grid; the offset slider compensates output latency.'));
}
