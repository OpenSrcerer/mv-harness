/* Edit mode (only when served by `mvh view`): corrections -> overrides.json / meaning/intent.md */
const SECTION_LABELS = ['intro', 'verse', 'pre-chorus', 'chorus', 'bridge', 'build', 'drop', 'breakdown', 'solo', 'interlude', 'instrumental', 'outro'];
const Edit = (() => {
  const st = { affected: [], saving: false, last: '', history: [], rerun: null, error: '' };
  const J = (o) => JSON.stringify(o);
  const ovr = () => V.ovr || (V.ovr = {});
  const clean = (o) => {
    const out = JSON.parse(J(o || {}));
    for (const k of Object.keys(out)) {
      if (k === 'schema' || k === 'schema_version') continue;
      const sec = out[k];
      if (sec && typeof sec === 'object' && !Array.isArray(sec)) {
        for (const f of Object.keys(sec)) {
          const v = sec[f];
          if (v == null || (Array.isArray(v) && !v.length) || (v && typeof v === 'object' && !Array.isArray(v) && !Object.keys(v).length)) delete sec[f];
        }
        if (!Object.keys(sec).length) delete out[k];
      }
    }
    delete out.schema; delete out.schema_version;
    if (!Object.keys(out).length) return out;
    return Object.assign({ schema: 'mvh/overrides', schema_version: (V.bundle.info || {}).contract || '1.0.0-rc.3' }, out);
  };
  async function api(path, body, method) {
    let r;
    try {
      r = await fetch(path, { method: method || 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json', 'X-MVH-Token': V.edit.token }, body: body == null ? undefined : J(body) });
    } catch (e) {
      // network failure: the server was stopped, timed out or dropped the connection; nothing was saved
      return { status: 0, ok: false, j: { error: 'server unreachable: nothing was saved (is mvh view still running?)' } };
    }
    let j = {};
    try { j = await r.json(); } catch (e) { /* */ }
    return { status: r.status, ok: r.ok, j };
  }
  async function commit(label, mutate, opts) {
    const before = J(clean(ovr()));
    const next = JSON.parse(before);
    mutate(next);
    const doc = clean(next);
    if (J(doc) === before) return;
    st.history.push(before);
    if (st.history.length > 60) st.history.shift();
    await save(doc, label);
  }
  async function save(doc, label, popped) {
    const prev = V.ovr;
    V.ovr = doc;
    rebuildGrid();
    st.saving = true; st.error = ''; renderBar();
    requestDraw('all');
    const r = await api('api/overrides', { overrides: doc, etag: V.ovrEtag || null });
    st.saving = false;
    if (r.ok) {
      V.ovrEtag = r.j.etag;
      st.affected = r.j.affected || [];
      st.last = label;
      toast(`Saved: ${label}. ` + (st.affected.length ? 'Will re-run: ' + st.affected.map((a) => a.stage).join(', ') : 'No stage is affected.'), 'good', 5000);
    } else {
      V.ovr = prev; rebuildGrid(); requestDraw('all');
      if (popped != null) st.history.push(popped); else st.history.pop();
      st.error = (r.j && (r.j.errors || [r.j.error]).join('; ')) || ('HTTP ' + r.status);
      toast('Not saved: ' + st.error, 'bad', 7000);
      if (r.status === 409) {
        try { const o = await (await fetch('api/overrides', { cache: 'no-store' })).json(); V.ovr = o.overrides || {}; V.ovrEtag = o.etag; rebuildGrid(); } catch (e) { /* server gone */ }
      }
    }
    renderBar(); refreshPanel(); requestDraw('all');
  }
  async function undo() {
    if (st.saving) return; // a second Undo must not go out with a stale etag
    const prev = st.history.pop();
    if (prev == null) { toast('Nothing to undo'); return; }
    await save(JSON.parse(prev), 'undo', prev);
    renderBar();
  }
  async function saveIntent(patch, label) {
    st.saving = true; renderBar();
    const r = await api('api/intent', patch);
    st.saving = false;
    if (r.ok) {
      V.intent = r.j.intent; st.affected = r.j.affected || []; st.last = label;
      toast(`Saved to meaning/intent.md: ${label}. Will re-run: ${st.affected.map((a) => a.stage).join(', ') || 'nothing'}`, 'good', 5000);
    } else { st.error = (r.j.errors || [r.j.error]).join('; '); toast('Not saved: ' + st.error, 'bad', 7000); }
    renderBar(); refreshPanel();
  }

  // ------------------------------------------------------------------ pending state helpers
  const appliedLines = () => (V.model.applied || {}) && (appliedOverrides('lyrics')['lyrics.lines'] || {});
  const appliedWords = () => appliedOverrides('lyrics')['lyrics.words'] || {};
  function lineShift(id) {
    const o = ((ovr().lyrics || {}).lines || {})[id];
    const a = (appliedLines()[id] || {}).dt || 0;
    return (o ? o.dt : 0) - a;
  }
  function pendingLine(id) { return Math.abs(lineShift(id)) > 0.0004; }
  function pendingWord(id) {
    const o = ((ovr().lyrics || {}).words || {})[id];
    if (!o) return null;
    const a = appliedWords()[id];
    return J(o) === J(a) ? null : o;
  }
  function pendingBoundaries() {
    const a = [].concat(appliedOverrides('sections')['structure.boundaries'] || []).map(J);
    return (((ovr().structure || {}).boundaries) || []).filter((b) => !a.includes(J(b)));
  }

  // ------------------------------------------------------------------ edits
  const dur = () => V.model.duration;
  function moveBoundary(from, to) {
    to = clamp(to, 0.2, dur() - 0.2);
    if (Math.abs(to - from) < 0.005) return;
    return commit(`move boundary ${fmtTime(from, 2)} → ${fmtTime(to, 2)}`, (o) => { (o.structure = o.structure || {}).boundaries = L.moveBoundary((o.structure || {}).boundaries, from, to); });
  }
  function addBoundary(t) {
    return commit(`add boundary at ${fmtTime(t, 2)}`, (o) => { (o.structure = o.structure || {}).boundaries = L.addBoundary((o.structure || {}).boundaries, L.r3(t)); });
  }
  function removeBoundary(t) {
    return commit(`remove boundary at ${fmtTime(t, 2)}`, (o) => { (o.structure = o.structure || {}).boundaries = L.removeBoundary((o.structure || {}).boundaries, t); });
  }
  function revertBoundary(b) {
    return commit('revert boundary edit', (o) => { o.structure.boundaries = (o.structure.boundaries || []).filter((x) => J(x) !== J(b)); });
  }
  function setLabel(sec, label) {
    const lab = L.cleanLabel(label);
    if (label && !lab) { toast('Label: lower-case letters and dashes only', 'warn'); return; }
    return commit(`label ${sec.id} = ${lab || '(auto)'}`, (o) => { (o.structure = o.structure || {}).labels = L.setSectionLabel((o.structure || {}).labels, sec.t, sec.t + sec.d, lab); });
  }
  function setLineTime(id, newT) {
    const ln = V.model.lines.find((l) => l.id === id);
    const a = (appliedLines()[id] || {}).dt || 0;
    const shown = ln.t;
    return commit(`nudge ${id} to ${fmtTime(newT, 2)}`, (o) => { (o.lyrics = o.lyrics || {}).lines = L.setLineNudge((o.lyrics || {}).lines, id, shown, a, newT); });
  }
  function nudgeLine(id, dtMs) {
    const ln = V.model.lines.find((l) => l.id === id);
    if (!ln) return;
    return setLineTime(id, ln.t + lineShift(id) + dtMs / 1000);
  }
  function setWordTime(id, t) {
    return commit(`retime word ${id}`, (o) => { (o.lyrics = o.lyrics || {}).words = L.setWord((o.lyrics || {}).words, id, { t }); });
  }
  function setWordDur(id, d) {
    const w = (V.song._get('lyrics').words || []).find((x) => x.id === id);
    return commit(`word ${id} duration`, (o) => { (o.lyrics = o.lyrics || {}).words = L.setWord((o.lyrics || {}).words, id, { t: (((o.lyrics || {}).words || {})[id] || {}).t != null ? o.lyrics.words[id].t : w.t, d }); });
  }
  function setLineVoice(id, voice) {
    return commit(`${id} sung by ${voice || '(auto)'}`, (o) => { const v = (o.voices = o.voices || {}); v.lines = Object.assign({}, v.lines || {}); if (voice) v.lines[id] = voice; else delete v.lines[id]; });
  }
  function setRhythm(patch, label) {
    return commit(label, (o) => { o.rhythm = Object.assign({}, o.rhythm || {}, patch); for (const k of Object.keys(o.rhythm)) if (o.rhythm[k] == null) delete o.rhythm[k]; });
  }
  function addPin(t, note) {
    return commit(`pin at ${fmtTime(t, 2)}`, (o) => { const c = (o.cues = o.cues || {}); c.pinned = (c.pinned || []).concat([{ t: L.r3(t), note: note || '' }]).sort((a, b) => a.t - b.t); });
  }
  function removePin(i) {
    return commit('remove pin', (o) => { o.cues.pinned = o.cues.pinned.filter((_, k) => k !== i); SEL.pin = null; });
  }

  // ------------------------------------------------------------------ panel
  function renderBar() {
    const b = $('#edit-bar');
    if (!b) return;
    b.textContent = '';
    b.append(h('div', { class: 'row-between' },
      h('span', { class: 'pill ' + (st.error ? 'bad' : st.saving ? 'warn' : 'good') }, st.error ? 'not saved' : st.saving ? 'saving…' : st.last ? 'saved' : 'no edits'),
      h('span', null, h('button', { class: 'btn sm', onclick: undo, disabled: !st.history.length }, 'Undo'), ' ', h('button', { class: 'btn sm', onclick: () => checkStatus() }, 'Check stages'))));
    if (st.error) b.append(h('div', { class: 'note bad' }, st.error));
    if (st.last) b.append(h('div', { class: 'dim small' }, 'last: ' + st.last));
    if (st.affected.length) {
      b.append(h('div', { class: 'note' }, h('b', null, 'These stages will re-run: '), st.affected.map((a) => h('span', { class: 'pill', title: a.reason }, a.stage))),
        h('div', { class: 'dim small' }, 'Run mvh analyze ', V.edit.folder, ' or press Re-run. Only these stages and their dependants run; cached results are reused.'));
    }
    if (V.edit.rerun) {
      b.append(h('div', { class: 'row-between' }, h('button', { class: 'btn', id: 'btn-rerun', onclick: rerun, disabled: !!(st.rerun && st.rerun.running) }, st.rerun && st.rerun.running ? 'Re-running…' : 'Re-run affected stages'),
        st.rerun && !st.rerun.running && st.rerun.code != null ? h('span', { class: 'pill ' + (st.rerun.code === 0 ? 'good' : 'bad') }, 'exit ' + st.rerun.code + (st.rerun.code === 0 ? ' — reload to see it' : '')) : null));
      if (st.rerun && st.rerun.tail) b.append(h('pre', { class: 'log' }, st.rerun.tail.join('\n')));
      if (st.rerun && !st.rerun.running && st.rerun.code === 0) b.append(h('button', { class: 'btn', onclick: () => location.reload() }, 'Reload viewer'));
    }
  }
  async function checkStatus() {
    const r = await fetch('api/status', { cache: 'no-store' });
    const j = await r.json();
    st.affected = (j.stale || []).map((s) => ({ stage: s.stage, reason: s.reason }));
    toast(st.affected.length ? 'Stale stages: ' + st.affected.map((a) => a.stage).join(', ') : 'Everything is up to date', st.affected.length ? 'warn' : 'good');
    renderBar();
  }
  async function rerun() {
    const r = await api('api/rerun', {});
    if (!r.ok) { toast('Could not start: ' + (r.j.error || r.status), 'bad'); return; }
    st.rerun = { running: true, tail: [], code: null };
    renderBar();
    const poll = async () => {
      const s = await (await fetch('api/rerun', { cache: 'no-store' })).json();
      st.rerun = s; renderBar();
      if (s.running) setTimeout(poll, 1200); else if (s.code === 0) { toast('Re-run finished: reload to see the new analysis', 'good', 6000); st.affected = []; renderBar(); }
    };
    setTimeout(poll, 800);
  }

  function numRow(label, value, unit, onSet, attrs) {
    const inp = h('input', Object.assign({ type: 'number', value, step: 'any', class: 'num' }, attrs || {}));
    inp.addEventListener('change', () => onSet(inp.value === '' ? null : Number(inp.value)));
    return h('label', { class: 'form-row' }, h('span', { class: 'lbl' }, label), inp, h('span', { class: 'dim small' }, unit || ''));
  }
  function btn(text, fn, title) { return h('button', { class: 'btn sm', onclick: fn, title }, text); }

  function refreshPanel() {
    const host = $('#pane-edit');
    if (!host || V.mode !== 'edit' || !V.model) return;
    const keep = host.scrollTop;
    host.textContent = '';
    const M = V.model;
    host.append(h('div', { id: 'edit-bar', class: 'edit-bar' }));
    // ---- rhythm
    const o = ovr().rhythm || {};
    const ap = M.applied || {};
    const off = o.beat_offset_s != null ? o.beat_offset_s : (ap['rhythm.beat_offset_s'] || 0);
    const baseBpm = (V.meta.tempo || {}).bpm;
    const cands = ((V.meta.tempo || {}).candidates || []).slice(0, 5);
    host.append(h('h3', null, 'Rhythm'),
      h('div', { class: 'dim small' }, 'Re-runs: rhythm, choreo, cues and their dependants. The grid in the lanes shows a preview of the pending change.'),
      numRow('beat offset', Math.round(off * 1000), 'ms', (v) => setRhythm({ beat_offset_s: v == null ? null : v / 1000 }, `beat offset ${v} ms`), { step: 1 }),
      h('div', { class: 'btnrow' }, [-50, -10, -1, 1, 10, 50].map((d) => btn((d > 0 ? '+' : '') + d, () => setRhythm({ beat_offset_s: L.r3(off + d / 1000) }, `beat offset ${Math.round((off + d / 1000) * 1000)} ms`))),
        btn('reset', () => setRhythm({ beat_offset_s: null }, 'beat offset reset'))),
      h('div', { class: 'btnrow' }, btn('nearest downbeat → playhead', () => setRhythm({ beat_offset_s: L.r3(off + L.alignOffset(M.grid, V.t, true)) }, 'align downbeat to playhead'), 'shifts the whole grid so the downbeat nearest the playhead lands on it'),
        btn('nearest beat → playhead', () => setRhythm({ beat_offset_s: L.r3(off + L.alignOffset(M.grid, V.t, false)) }, 'align beat to playhead'))),
      numRow('BPM override', o.bpm != null ? o.bpm : '', baseBpm != null ? 'detected ' + (+baseBpm).toFixed(2) : '', (v) => setRhythm({ bpm: v }, v == null ? 'BPM override cleared' : `BPM ${v}`), { step: 0.01, min: 1 }),
      h('div', { class: 'btnrow' }, cands.map((c) => btn(`${(+c.bpm).toFixed(1)} ${c.relation || ''}`, () => setRhythm({ bpm: L.r3(c.bpm) }, `BPM ${c.bpm}`))), btn('clear', () => setRhythm({ bpm: null }, 'BPM override cleared'))),
      h('div', { class: 'form-row' }, h('span', { class: 'lbl' }, 'downbeat phase'), btn('− beat', () => setRhythm({ downbeat_phase: (o.downbeat_phase != null ? o.downbeat_phase : (ap['rhythm.downbeat_phase'] || 0)) - 1 }, 'downbeat phase -1')),
        h('b', null, String(o.downbeat_phase != null ? o.downbeat_phase : (ap['rhythm.downbeat_phase'] || 0))), btn('+ beat', () => setRhythm({ downbeat_phase: (o.downbeat_phase != null ? o.downbeat_phase : (ap['rhythm.downbeat_phase'] || 0)) + 1 }, 'downbeat phase +1')),
        btn('reset', () => setRhythm({ downbeat_phase: null }, 'downbeat phase reset'))));
    // ---- structure
    const sec = SEL.sectionId ? M.sections.find((s) => s.id === SEL.sectionId) : sectionAt(V.t);
    host.append(h('h3', null, 'Sections'), h('div', { class: 'dim small' }, 'Drag a boundary in the Sections lane, double-click it to add one, select it and press Delete to remove. Edits are anchored by time. Re-runs: structure and its dependants.'));
    const pend = pendingBoundaries();
    host.append(h('div', { class: 'btnrow' }, btn('add boundary at playhead', () => addBoundary(V.t)), SEL.boundary != null ? btn('remove selected boundary (' + fmtTime(SEL.boundary, 2) + ')', () => { removeBoundary(SEL.boundary); SEL.boundary = null; }) : null));
    if (sec) {
      const sel = h('select', { onchange: (e) => setLabel(sec, e.target.value) }, h('option', { value: '' }, '(auto)'),
        SECTION_LABELS.map((l) => h('option', { value: l, selected: l === sec.label }, l)));
      const cust = h('input', { type: 'text', placeholder: 'custom label', class: 'txt', onchange: (e) => { if (e.target.value) setLabel(sec, e.target.value); } });
      host.append(h('div', { class: 'form-row' }, h('span', { class: 'lbl' }, `label of ${sec.id}`), sel), h('div', { class: 'form-row' }, h('span', { class: 'lbl' }, ''), cust));
    }
    if (pend.length) host.append(h('div', { class: 'dim small' }, 'pending boundary edits:'), ...pend.map((b) => h('div', { class: 'pendrow' }, `${b.action} ${fmtTime(b.t, 2)}${b.to_t != null ? ' → ' + fmtTime(b.to_t, 2) : ''}`, ' ', btn('×', () => revertBoundary(b), 'revert this edit'))));
    // ---- lyrics
    const ln = SEL.lineId ? M.lines.find((l) => l.id === SEL.lineId) : null;
    host.append(h('h3', null, 'Lyrics & singers'));
    if (!M.lines.length) host.append(h('div', { class: 'dim' }, 'This song has no lyrics.'));
    else if (!ln) host.append(h('div', { class: 'dim' }, 'Click a line in the Lyrics lane to select it, then drag it (or its word ticks, when zoomed in) or nudge it here.'));
    else {
      const a = (appliedLines()[ln.id] || {}).dt || 0, cur = (((ovr().lyrics || {}).lines || {})[ln.id] || {}).dt;
      host.append(h('div', { class: 'card' }, h('b', null, ln.id + '  '), h('span', { class: 'dim' }, fmtTime(ln.t, 2)), h('div', null, ln.text)),
        h('div', { class: 'btnrow' }, [-100, -20, -10, 10, 20, 100].map((d) => btn((d > 0 ? '+' : '') + d + ' ms', () => nudgeLine(ln.id, d))), btn('start at playhead', () => setLineTime(ln.id, V.t))),
        h('div', { class: 'dim small' }, `nudge now ${cur != null ? Math.round(cur * 1000) : 0} ms (applied by the last run ${Math.round(a * 1000)} ms)`));
      const vopts = M.voices.map((v) => v.id);
      const curV = (((ovr().voices || {}).lines || {})[ln.id]) || M.voiceOfLine.get(ln.id) || '';
      host.append(h('div', { class: 'form-row' }, h('span', { class: 'lbl' }, 'sung by'), h('select', { onchange: (e) => setLineVoice(ln.id, e.target.value) }, h('option', { value: '' }, '(automatic)'),
        vopts.map((v) => h('option', { value: v, selected: v === curV }, v + (M.charOfVoice.get(v) ? ' — ' + M.charName(M.charOfVoice.get(v)) : ''))))));
      if (SEL.wordId) {
        const w = (V.song._get('lyrics').words || []).find((x) => x.id === SEL.wordId);
        if (w) {
          const wp = (((ovr().lyrics || {}).words || {})[w.id]) || {};
          host.append(h('div', { class: 'card' }, h('b', null, w.id), ' ', w.text),
            numRow('word start', Math.round((wp.t != null ? wp.t : w.t) * 1000), 'ms', (v) => setWordTime(w.id, v / 1000), { step: 5 }),
            numRow('word length', Math.round((wp.d != null ? wp.d : w.d) * 1000), 'ms', (v) => setWordDur(w.id, v / 1000), { step: 5, min: 0 }));
        }
      }
    }
    // ---- voices -> characters (intent.md)
    host.append(h('h3', null, 'Voices → characters'), h('div', { class: 'dim small' }, 'Written to meaning/intent.md (managed block). Re-runs: voices, meaning.'));
    const chars = M.characters.length ? M.characters : [];
    for (const v of M.voices) {
      const mapped = (V.intent.voices || {})[v.id] || {};
      const curC = mapped.character_id || M.charOfVoice.get(v.id) || '';
      const nameInp = h('input', { type: 'text', class: 'txt', value: mapped.name || (curC ? M.charName(curC) : ''), placeholder: 'character name' });
      const csel = h('select', null, h('option', { value: '' }, '(none)'),
        chars.map((c) => h('option', { value: c.id, selected: c.id === curC }, `${c.id} ${c.name}`)),
        h('option', { value: '__new' }, '+ new character'));
      csel.addEventListener('change', () => { if (csel.value && csel.value !== '__new') { const c = chars.find((x) => x.id === csel.value); nameInp.value = c ? c.name : nameInp.value; } });
      host.append(h('div', { class: 'card' }, h('div', { class: 'row-between' }, h('b', null, v.id), h('span', { class: 'dim small' }, `${Math.round(v.seconds || 0)} s · ${v.n_lines || 0} lines`)),
        h('div', { class: 'form-row' }, csel, nameInp, btn('save', () => {
          let cid = csel.value;
          if (cid === '__new' || (!cid && nameInp.value)) { const used = new Set([...chars.map((c) => c.id), ...Object.values(V.intent.voices || {}).map((x) => x.character_id)]); let n = 1; while (used.has('C' + n)) n++; cid = 'C' + n; }
          saveIntent({ voices: { [v.id]: cid ? { character_id: cid, name: nameInp.value.trim() || cid } : null } }, `${v.id} → ${cid || 'none'}`);
        }))));
    }
    if (!M.voices.length) host.append(h('div', { class: 'dim' }, 'No voices detected.'));
    // ---- section meaning
    host.append(h('h3', null, 'Meaning of a section'), h('div', { class: 'dim small' }, 'Written to meaning/intent.md; anchored by section time. Select a section (click it in the Sections or Meaning lane).'));
    const msec = SEL.sectionId ? M.sections.find((s) => s.id === SEL.sectionId) : null;
    if (!msec) host.append(h('div', { class: 'dim' }, 'No section selected.'));
    else {
      const ex = (V.intent.sections || {})[msec.id] || {};
      const base = M.meaningSections.get(msec.id) || {};
      const f = {};
      const mk = (key, label, init, rows) => { f[key] = h('textarea', { rows: rows || 2, class: 'txt' }); f[key].value = init || ''; return h('label', { class: 'blk' }, h('span', { class: 'lbl' }, label), f[key]); };
      host.append(h('div', { class: 'card' }, h('b', null, `${msec.id} ${msec.occurrence_label || msec.label}`), ' ', h('span', { class: 'dim' }, `${fmtTime(msec.t, 1)}-${fmtTime(msec.t + msec.d, 1)}`)),
        mk('feel', 'how it feels', ex.feel != null ? ex.feel : base.feel, 1), mk('meaning', 'what it means', ex.meaning != null ? ex.meaning : base.meaning, 3),
        mk('movement', 'movement', ex.movement != null ? ex.movement : base.movement_hint, 2), mk('camera', 'camera', ex.camera != null ? ex.camera : base.camera_hint, 2),
        mk('palette', 'palette (hex, comma separated)', ex.palette != null ? ex.palette : (base.palette_hint || []).join(', '), 1), mk('do_not', 'never show (one per line)', ex.do_not != null ? ex.do_not : (base.do_not || []).join('\n'), 2),
        h('div', { class: 'btnrow' }, btn('save section meaning', () => {
          const rec = { t0: msec.t, t1: msec.t + msec.d, label: msec.occurrence_label || msec.label };
          for (const k of Object.keys(f)) rec[k] = f[k].value.trim();
          saveIntent({ sections: { [msec.id]: rec } }, `meaning of ${msec.id}`);
        }), btn('clear', () => saveIntent({ sections: { [msec.id]: null } }, `cleared ${msec.id}`))));
    }
    // ---- pins
    host.append(h('h3', null, 'Pinned moments'), h('div', { class: 'dim small' }, 'Pins become tier-1 cues. Double-click the Cues lane or add one at the playhead. Re-runs: cues.'));
    const pins = ((ovr().cues || {}).pinned) || [];
    const note = h('input', { type: 'text', class: 'txt', placeholder: 'note (e.g. camera cut)' });
    host.append(h('div', { class: 'form-row' }, note, btn('pin at playhead', () => addPin(V.t, note.value))));
    pins.forEach((p, i) => host.append(h('div', { class: 'pendrow' + (SEL.pin === i ? ' sel' : ''), onclick: () => { SEL.pin = i; seek(p.t); } }, `${fmtTime(p.t, 2)}  ${p.note || ''}`, ' ', btn('×', (e) => { e.stopPropagation(); removePin(i); }, 'remove pin'))));
    renderBar();
    host.scrollTop = keep;
  }

  return { moveBoundary, addBoundary, removeBoundary, setLabel, setLineTime, nudgeLine, setLineVoice, setRhythm, saveIntent, setWordTime, setWordDur, addPin, removePin, undo, pendingLine, pendingWord, pendingBoundaries, lineShift,
    refreshPanel, renderBar, save, commit, state: st };
})();
