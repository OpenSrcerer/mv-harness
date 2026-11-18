/* Edit mode (only when served by `mvh view`): corrections -> overrides.json / meaning/intent.md */
const SECTION_LABELS = ['intro', 'verse', 'pre-chorus', 'chorus', 'bridge', 'build', 'drop', 'breakdown', 'solo', 'interlude', 'instrumental', 'outro'];
const Edit = (() => {
  const st = { affected: [], saving: false, last: '', history: [], rerun: null, error: '', group: 'all' };
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
  // Saves run one at a time: each one sends the etag of the previous save, so two in flight (a held key, quick
  // drags) would make the server reject the second one as a conflict. A commit waits for the one before it and
  // then applies its change to the latest state.
  let queue = Promise.resolve();
  function commit(label, mutate, opts) {
    const run = async () => {
      const before = J(clean(ovr()));
      const next = JSON.parse(before);
      mutate(next);
      const doc = clean(next);
      if (J(doc) === before) return;
      st.history.push(before);
      if (st.history.length > 60) st.history.shift();
      await save(doc, label);
    };
    queue = queue.then(run, run);
    return queue;
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
  function undo() {
    // queued like every save, so it never goes out with a stale etag
    const run = async () => {
      const prev = st.history.pop();
      if (prev == null) { toast('Nothing to undo'); return; }
      await save(JSON.parse(prev), 'undo', prev);
      renderBar();
    };
    queue = queue.then(run, run);
    return queue;
  }
  async function saveIntent(patch, label, onOk) {
    st.saving = true; renderBar();
    const r = await api('api/intent', patch);
    st.saving = false;
    if (r.ok) {
      if (onOk) onOk();
      V.intent = r.j.intent; st.affected = r.j.affected || []; st.last = label;
      toast(`Saved to meaning/intent.md: ${label}. Will re-run: ${st.affected.map((a) => a.stage).join(', ') || 'nothing'}`, 'good', 5000);
    } else { st.error = (r.j.errors || [r.j.error]).join('; '); toast('Not saved: ' + st.error, 'bad', 7000); }
    renderBar(); refreshPanel();
  }

  // ------------------------------------------------------------------ pending state helpers
  const appliedLines = () => (V.model.applied || {}) && (appliedOverrides('lyrics')['lyrics.lines'] || {});
  const appliedWords = () => appliedOverrides('lyrics')['lyrics.words'] || {};
  // ---- lyric line pins (D82)
  const appliedPins = () => appliedOverrides('lyrics')['lyrics.pins'] || [];
  const linePinOf = (ln) => L.linePin(ovr().lyrics, ln);
  /** the line's pin when the last run has not applied it yet */
  function pendingPin(ln) {
    const p = linePinOf(ln);
    if (!p) return null;
    const a = appliedPins().find((x) => x.index === p.index);
    return a && Math.abs(a.t - p.t) < 0.0005 ? null : p;
  }
  function pinLine(id, t) {
    const ln = V.model.lines.find((l) => l.id === id);
    if (!ln) return;
    if (ln.source_index === undefined) { toast('Re-run the analysis once to pin lines (this folder was made by an older version)', 'bad', 6000); return; }
    if (ln.source_index === null) { toast('This line was added by the harness (a repeat it heard), so it cannot be pinned', 'bad', 6000); return; }
    return commit(`pin ${id} at ${fmtTime(t, 2)}`, (o) => { o.lyrics = L.setLinePin(o.lyrics, ln, t); });
  }
  function unpinLine(index, label) {
    return commit(`unpin ${label}`, (o) => { o.lyrics = L.removeLinePin(o.lyrics, index); });
  }
  function lineShift(id) {
    const ln = V.model.lines.find((l) => l.id === id);
    const pp = ln ? pendingPin(ln) : null;
    if (pp) return pp.t - ln.t;   // a pending pin shows the line where it will start
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
  // ---- single words
  const wordById = (id) => (V.song._get('lyrics').words || []).find((x) => x.id === id);
  /** where a word shows now (see logic.wordPos): {t, d, pending} */
  function wordShown(w, dlt) {
    const ov = ((ovr().lyrics || {}).words || {})[w.id];
    const p = pendingWord(w.id);
    return Object.assign(L.wordPos(w, ov, p, dlt == null ? lineShift(w.line_id) : dlt), { pending: !!p });
  }
  function setWordTime(id, t) {
    // an absolute start replaces any relative shift of the word
    return commit(`retime word ${id} to ${fmtTime(t, 3)}`, (o) => {
      const ws = L.setWord((o.lyrics = o.lyrics || {}).words, id, { t: Math.max(0, t) });
      delete ws[id].dt;
      o.lyrics.words = ws;
    });
  }
  function setWordDur(id, d) {
    const w = wordById(id);
    if (!w) return;
    const t = wordShown(w).t;
    return commit(`word ${id} length ${Math.round(d * 1000)} ms`, (o) => {
      const ws = L.setWord((o.lyrics = o.lyrics || {}).words, id, { t, d: Math.max(0.02, d) });
      delete ws[id].dt;
      o.lyrics.words = ws;
    });
  }
  function nudgeWord(id, ms) {
    const w = wordById(id);
    if (!w) return;
    // relative to where the word is when this save runs (queued saves before it may have moved it)
    return commit(`move word ${id} ${ms > 0 ? '+' : ''}${ms} ms`, (o) => {
      const ws = L.setWord((o.lyrics = o.lyrics || {}).words, id, { t: Math.max(0, wordShown(w).t + ms / 1000) });
      delete ws[id].dt;
      o.lyrics.words = ws;
    });
  }
  function resetWord(id) {
    return commit(`reset word ${id}`, (o) => { const ws = Object.assign({}, (o.lyrics || {}).words || {}); delete ws[id]; (o.lyrics = o.lyrics || {}).words = ws; });
  }
  function selectWord(id, lineId) {
    SEL.lineId = lineId; SEL.wordId = id;
    requestDraw('lyrics'); refreshPanel();
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

  // ------------------------------------------------------------------ meaning forms (D81)
  // The page shows the last analysis; a suggestion dismissed since then is hidden with this set until the re-run.
  const dismissed = new Set();
  const dkey = (it) => [it.scope, it.id || it.key || '', it.field, it.value == null ? '' : it.value].join('|');
  // Text typed (and suggestions accepted) but not saved yet, by 'form|field'. The panel is redrawn whenever a section
  // is selected or something is saved, and unsaved words must survive that. A form's entries go when it is saved.
  const typed = new Map(), accepted = new Set();
  const forget = (form) => { for (const k of [...typed.keys(), ...accepted]) if (k.startsWith(form + '|')) { typed.delete(k); accepted.delete(k); } };
  /** a textarea whose unsaved text survives a redraw of the panel */
  function keptArea(id, initial, attrs) {
    const ta = h('textarea', attrs);
    ta.value = typed.has(id) ? typed.get(id) : initial;
    ta.addEventListener('input', () => typed.set(id, ta.value));
    return ta;
  }
  async function dismiss(items, label) {
    st.saving = true; renderBar();
    const r = await api('api/draft', { dismiss: items });
    st.saving = false;
    if (r.ok) {
      items.forEach((it) => dismissed.add(dkey(it)));
      if ((r.j.affected || []).length) st.affected = r.j.affected;
      st.last = 'dismissed ' + label;
      toast(`Dismissed the suggestion for ${label}: it is removed from the draft (meaning/authored.json).`, 'good', 5000);
    } else { st.error = (r.j.errors || [r.j.error]).join('; '); toast('Not dismissed: ' + st.error, 'bad', 7000); }
    renderBar(); refreshPanel();
  }
  /** id: the form ('song', 'group:drop', 'sec:S04'); fields: [{key, label, rows, st (L.meaningField), placeholder, dis (the
   *  dismiss item)}] -> {rows, collect(acceptAll), nSugg} */
  function meaningForm(id, fields) {
    const inputs = {};
    const rows = fields.map((f) => {
      const fid = id + '|' + f.key;
      const sugg = f.st.kind === 'suggestion';
      const shown = f.st.kind === 'inherited' ? '' : f.st.value;
      const ta = keptArea(fid, shown, { rows: f.rows || 1, class: 'txt', placeholder: f.placeholder || '' });
      inputs[f.key] = ta;
      const tools = [];
      if (sugg) {
        const pill = h('span', { title: 'From a draft, not from you. It stays a draft until you accept or change it.' });
        const show = () => {
          const edited = ta.value.trim() !== shown.trim(), acc = accepted.has(fid);
          ta.classList.toggle('sugg', !edited && !acc);
          pill.className = 'pill ' + (edited || acc ? 'good' : 'warn');
          pill.textContent = edited ? 'edited: yours when saved' : acc ? 'accepted: yours when saved' : 'suggestion';
        };
        ta.addEventListener('input', show);
        show();
        tools.push(pill, btn('accept', () => { accepted.add(fid); show(); }, 'keep this suggestion as your own answer'));
        if (f.dis) tools.push(btn('dismiss', () => { typed.delete(fid); accepted.delete(fid); dismiss([f.dis], f.label); }, 'remove this suggestion from the draft'));
      } else if (f.st.kind === 'own') tools.push(h('span', { class: 'pill good' }, 'yours'));
      else if (f.st.kind === 'yours') tools.push(h('span', { class: 'pill good', title: 'From the template in meaning/intent.md. A change saved here wins over it.' }, 'yours (template)'));
      return h('div', { class: 'blk' }, h('div', { class: 'lbl' }, f.label, ' ', tools), ta);
    });
    const collect = (acceptAll) => {
      const rec = {};
      for (const f of fields) {
        const v = inputs[f.key].value.trim();
        if (L.meaningFieldWrite(f.st, v, acceptAll || accepted.has(id + '|' + f.key))) rec[f.key] = v;
      }
      return rec;
    };
    return { id, rows, collect, nSugg: fields.filter((f) => f.st.kind === 'suggestion').length };
  }
  const SEC_FIELDS = [['feel', 'feel', 'how it feels', 1], ['meaning', 'meaning', 'what it means', 2], ['movement', 'movement_hint', 'movement', 2],
    ['camera', 'camera_hint', 'camera', 2], ['palette', 'palette_hint', 'palette (hex, comma separated)', 1]];
  function meaningPanel(host, M) {
    const m = M.meaning || {}, defs = m.section_defaults || [];
    const I = V.intent || {};
    // a draft value is hidden once it was dismissed here
    const live = (item, eff, src) => (src === 'draft' && dismissed.has(dkey(item)) ? ['', undefined] : [eff, src]);
    const saveRow = (form, label, patchOf, clearPatch) => h('div', { class: 'btnrow' },
      btn('save ' + label, () => saveIntent(patchOf(form.collect(false)), label, () => forget(form.id))),
      form.nSugg ? btn(`accept all ${form.nSugg} suggestion${form.nSugg > 1 ? 's' : ''} and save`, () => saveIntent(patchOf(form.collect(true)), label + ' (suggestions accepted)', () => forget(form.id))) : null,
      btn('clear', () => saveIntent(clearPatch, 'cleared ' + label, () => forget(form.id)), 'remove what the viewer saved here; the template and the draft are not touched'));

    // ---- the whole song
    host.append(h('h3', { id: 'edit-meaning' }, 'Meaning of the whole song'),
      h('div', { class: 'dim small' }, 'Written to meaning/intent.md (the same fields as the template that mvh meaning --edit opens). What you save here wins over the template. Re-runs: meaning, brief.'));
    const fs = m.field_sources || {}, own = I.song || {};
    const songField = (key, label, rows, eff, src) => {
      const dis = { scope: 'song', field: key };
      const [e, sc] = live(dis, eff, src);
      return { key, label, rows, dis, st: L.meaningField(Array.isArray(own[key]) ? own[key].join('\n') : own[key], e, sc, 'song', 'song') };
    };
    const song = meaningForm('song', [
      songField('logline', 'logline: the song in one line', 2, m.logline, fs.logline),
      songField('summary', 'story: what happens, start to end', 4, m.summary, fs.summary),
      songField('setting', 'setting: the world it happens in', 2, m.setting, fs.setting),
      songField('tone', 'tone', 1, m.tone, fs.tone),
      songField('themes', 'themes (one per line)', 2, (m.themes || []).map((t) => t.text).join('\n'), fs.themes),
      songField('palette', 'palette (hex or colour words, comma separated)', 1, (m.palette || []).join(', '), fs.palette),
    ]);
    const ownRules = own.do_not || [];
    const rules = keptArea('song|do_not', ownRules.join('\n'), { rows: 3, class: 'txt', placeholder: 'one rule per line, in your own words' });
    const tmplRules = (m.do_not || []).filter((r) => !ownRules.includes(r));
    const sugRules = (m.suggested_do_not || []).filter((r) => !ownRules.includes(r) && !dismissed.has(dkey({ scope: 'song', field: 'do_not', value: r })));
    host.append(...song.rows,
      h('div', { class: 'blk' }, h('div', { class: 'lbl' }, 'never show: the only hard rules, copied word for word to every agent'), rules,
        tmplRules.length ? h('div', { class: 'dim small' }, 'Also in the template of intent.md (edit them there): ' + tmplRules.join(' · ')) : null,
        sugRules.map((r) => h('div', { class: 'pendrow' }, h('span', { class: 'pill warn' }, 'suggested rule'), ' ', r, ' ',
          btn('add', () => { rules.value = (rules.value.trim() ? rules.value.trim() + '\n' : '') + r; typed.set('song|do_not', rules.value); toast('Added to the box: save to keep it'); }, 'put this rule in the box above'),
          btn('dismiss', () => dismiss([{ scope: 'song', field: 'do_not', value: r }], 'a rule'), 'remove this suggestion from the draft')))),
      saveRow(song, 'whole-song meaning', (rec) => ({ song: Object.assign(rec, { do_not: rules.value }) }), { song: null }));

    // ---- a group of sections: every section, every <label>
    host.append(h('h3', null, 'Meaning by group of sections'),
      h('div', { class: 'dim small' }, 'Answer once for many sections. A single section overrides its group, and a group overrides "every section".'));
    const gOwn = I.groups || {};
    const groups = defs.filter((g) => g.key === 'all' || (g.section_ids || []).length > 1 || Object.keys(g.field_sources || {}).length || gOwn[g.key]);
    const allDef = defs.find((g) => g.key === 'all') || {};
    // an answer one level up, as a hint: what the viewer saved since the last run first, then the last run's
    const upAll = (key, mf) => (gOwn.all || {})[key] || ((allDef.field_sources || {})[mf] === 'user' ? [].concat(allDef[mf] || []).join(', ') : '');
    if (!groups.length) host.append(h('div', { class: 'dim' }, 'Re-run the analysis once to edit by group (this folder was made by an older version).'));
    else {
      if (!groups.some((g) => g.key === st.group)) st.group = 'all';
      const g = groups.find((x) => x.key === st.group);
      const level = g.key === 'all' ? 'all' : 'type';
      const form = meaningForm('group:' + g.key, SEC_FIELDS.map(([key, mf, label, rows]) => {
        const dis = { scope: 'group', key: g.key, field: key };
        const [e, sc] = live(dis, g[mf], (g.field_sources || {})[mf]);
        const stt = L.meaningField((gOwn[g.key] || {})[key], e, sc, level, level);
        const up = level === 'type' && stt.kind === 'empty' ? upAll(key, mf) : '';
        return { key, label, rows, dis, st: stt, placeholder: up ? 'from every section: ' + up : '' };
      }));
      const name = g.key === 'all' ? 'every section' : 'every ' + g.key;
      host.append(h('div', { class: 'form-row' }, h('span', { class: 'lbl' }, 'group'),
        h('select', { onchange: (e) => { st.group = e.target.value; refreshPanel(); } }, groups.map((x) => h('option', { value: x.key, selected: x.key === g.key },
          x.key === 'all' ? `every section (${(x.section_ids || []).length})` : `every ${x.key} (${(x.section_ids || []).length}: ${(x.section_ids || []).join(' ')})`)))),
      ...form.rows, saveRow(form, 'meaning of ' + name, (rec) => ({ groups: { [g.key]: rec } }), { groups: { [g.key]: null } }));
    }

    // ---- one section
    host.append(h('h3', null, 'Meaning of a section'), h('div', { class: 'dim small' }, 'Only what differs from its group. Anchored by section time. Select a section (click it in the Sections or Meaning lane).'));
    const msec = SEL.sectionId ? M.sections.find((x) => x.id === SEL.sectionId) : null;
    if (!msec) { host.append(h('div', { class: 'dim' }, 'No section selected.')); return; }
    const ex = (I.sections || {})[msec.id] || {};
    const base = M.meaningSections.get(msec.id) || {};
    const grp = defs.find((x) => x.key !== 'all' && (x.section_ids || []).includes(msec.id));
    const form = meaningForm('sec:' + msec.id, SEC_FIELDS.map(([key, mf, label, rows]) => {
      const dis = { scope: 'section', id: msec.id, field: key };
      const [e, sc] = live(dis, base[mf], (base.field_sources || {})[mf]);
      let stt = L.meaningField(ex[key], e, sc, (base.field_scope || {})[mf], 'section');
      // an answer for the group saved in the viewer since the last run beats a draft: show it as inherited
      const viaGroup = grp ? (gOwn[grp.key] || {})[key] : '';
      const viaAll = (gOwn.all || {})[key];
      if (stt.kind === 'suggestion' && (viaGroup || viaAll)) stt = { value: '', kind: 'empty' };
      let ph = '';
      if (stt.kind === 'inherited') ph = `from every ${stt.from === 'all' ? 'section' : (grp ? grp.key : 'section of this type')}: ${stt.value}`;
      else if (stt.kind === 'empty') ph = viaGroup ? `from every ${grp.key}: ${viaGroup}` : (upAll(key, mf) ? 'from every section: ' + upAll(key, mf) : '');
      return { key, label, rows, dis, st: stt, placeholder: ph };
    }));
    const dn = keptArea('sec:' + msec.id + '|do_not', (ex.do_not || []).join('\n'), { rows: 2, class: 'txt', placeholder: 'rules for this section only, one per line' });
    const heard = (base.emotion || {}).audio;
    host.append(h('div', { class: 'card' }, h('b', null, `${msec.id} ${msec.occurrence_label || msec.label}`), ' ', h('span', { class: 'dim' }, `${fmtTime(msec.t, 1)}-${fmtTime(msec.t + msec.d, 1)}`),
        heard ? h('div', { class: 'dim small' }, `Heard in the audio: ${heard}. Measured by the mood model: intensity is more reliable than happy or sad.`) : null),
      ...form.rows, h('div', { class: 'blk' }, h('div', { class: 'lbl' }, 'never show in this section (one per line)'), dn),
      saveRow(form, 'meaning of ' + msec.id, (rec) => ({ sections: { [msec.id]: Object.assign({ t0: msec.t, t1: msec.t + msec.d, label: msec.occurrence_label || msec.label }, rec, { do_not: dn.value }) } }),
        { sections: { [msec.id]: null } }));
  }

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
      // pins: a fixed start; the re-run places the lines up to the next pin again and snaps their words
      const pin = linePinOf(ln);
      // the section start nearest to the playhead, looked up when the button is pressed (the playhead moves)
      const nearStart = () => M.sections.reduce((b, s) => (Math.abs(s.t - V.t) < Math.abs(b.t - V.t) ? s : b)).t;
      host.append(h('div', { class: 'btnrow' },
        btn(pin ? 'move pin to playhead' : 'pin start at playhead', () => pinLine(ln.id, V.t), 'fix where this line starts'),
        M.sections.length ? btn('pin at nearest section start', () => pinLine(ln.id, nearStart()), 'the section boundary closest to the playhead') : null,
        pin ? btn('remove pin', () => unpinLine(pin.index, ln.id)) : null),
        h('div', { class: 'dim small' }, pin ? `Pinned at ${fmtTime(pin.t, 2)}${pendingPin(ln) ? ': applies on the next re-run.' : '.'}`
          : 'When a part is out of place, pin the first line of each pass where it really starts, then re-run: the lines up to the next pin are placed again and their words snap to the singing.'));
      const vopts = M.voices.map((v) => v.id);
      const curV = (((ovr().voices || {}).lines || {})[ln.id]) || M.voiceOfLine.get(ln.id) || '';
      host.append(h('div', { class: 'form-row' }, h('span', { class: 'lbl' }, 'sung by'), h('select', { onchange: (e) => setLineVoice(ln.id, e.target.value) }, h('option', { value: '' }, '(automatic)'),
        vopts.map((v) => h('option', { value: v, selected: v === curV }, v + (M.charOfVoice.get(v) ? ' — ' + M.charName(M.charOfVoice.get(v)) : ''))))));
      const w = SEL.wordId ? wordById(SEL.wordId) : null;
      if (w && w.line_id === ln.id) {
        const pos = wordShown(w);
        const ov = ((ovr().lyrics || {}).words || {})[w.id];
        host.append(h('div', { class: 'card' }, h('b', null, w.id), ' ', w.text, ' ',
          h('span', { class: 'dim small' }, `${fmtTime(pos.t, 3)} · ${Math.round(pos.d * 1000)} ms${pos.pending ? ' · not re-run yet' : ''}`)),
        h('div', { class: 'btnrow' }, [-50, -10, 10, 50].map((d) => btn((d > 0 ? '+' : '') + d + ' ms', () => nudgeWord(w.id, d))),
          btn('start at playhead', () => setWordTime(w.id, V.t), 'the word starts where the playhead is'),
          btn('end at playhead', () => { if (V.t - pos.t >= 0.02) setWordDur(w.id, V.t - pos.t); else toast('The playhead is before the word: nothing changed', 'bad'); }, 'the word ends where the playhead is'),
          ov ? btn('reset', () => resetWord(w.id), 'back to the analysed timing') : null),
        numRow('word start', Math.round(pos.t * 1000), 'ms', (v) => setWordTime(w.id, v / 1000), { step: 5 }),
        numRow('word length', Math.round(pos.d * 1000), 'ms', (v) => setWordDur(w.id, v / 1000), { step: 5, min: 20 }),
        h('div', { class: 'dim small' }, 'In the Lyrics lane: drag a word to move it, drag its right edge to change its length, click it to select it. Keys < and > move the selected word by 10 ms.'));
      } else {
        host.append(h('div', { class: 'dim small' }, 'Single words: zoom in on the Lyrics lane until the words show under the line, then drag one or click it to select it.'));
      }
    }
    const allPins = (ovr().lyrics || {}).pins || [];
    if (allPins.length) {
      host.append(h('div', { class: 'dim small' }, 'pinned lines:'), ...allPins.map((p) => {
        const l = M.lines.find((x) => x.source_index === p.index);
        const name = l ? l.id : 'line ' + (p.index + 1);
        return h('div', { class: 'pendrow', onclick: () => { if (l) selectLine(l.id); seek(p.t); } }, `${name} at ${fmtTime(p.t, 2)}`, ' ',
          btn('×', (e) => { e.stopPropagation(); unpinLine(p.index, name); }, 'remove this pin'));
      }));
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
    // ---- meaning: the whole song, a group of sections, one section (D81)
    meaningPanel(host, M);
    // ---- pins
    host.append(h('h3', null, 'Pinned moments'), h('div', { class: 'dim small' }, 'Pins become tier-1 cues. Double-click the Cues lane or add one at the playhead. Re-runs: cues.'));
    const pins = ((ovr().cues || {}).pinned) || [];
    const note = h('input', { type: 'text', class: 'txt', placeholder: 'note (e.g. camera cut)' });
    host.append(h('div', { class: 'form-row' }, note, btn('pin at playhead', () => addPin(V.t, note.value))));
    pins.forEach((p, i) => host.append(h('div', { class: 'pendrow' + (SEL.pin === i ? ' sel' : ''), onclick: () => { SEL.pin = i; seek(p.t); } }, `${fmtTime(p.t, 2)}  ${p.note || ''}`, ' ', btn('×', (e) => { e.stopPropagation(); removePin(i); }, 'remove pin'))));
    renderBar();
    host.scrollTop = keep;
  }

  return { wordShown, nudgeWord, selectWord, resetWord, linePinOf, pinLine, unpinLine, moveBoundary, addBoundary, removeBoundary, setLabel, setLineTime, nudgeLine, setLineVoice, setRhythm, saveIntent, setWordTime, setWordDur, addPin, removePin, undo, pendingLine, pendingWord, pendingBoundaries, lineShift,
    refreshPanel, renderBar, save, commit, state: st };
})();
