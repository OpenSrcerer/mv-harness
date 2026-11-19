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
  // ---- line and word keys (D83): overrides are written under stable references (r12, r12p1, r12w4) when the line
  // has one, so they stay with the right line when lines are moved, split or renumbered; old id keys still count
  const lineById = (id) => V.model.lines.find((l) => l.id === id);
  const sumDt = (map, ks) => ks.reduce((s, k) => s + (((map || {})[k] || {}).dt || 0), 0);
  function lineShift(id) {
    const ln = lineById(id);
    if (!ln) return 0;
    const pp = pendingPin(ln);
    if (pp) return pp.t - ln.t;   // a pending pin shows the line where it will start
    const ks = L.lineKeys(ln);
    return sumDt((ovr().lyrics || {}).lines, ks) - sumDt(appliedLines(), ks);
  }
  function pendingLine(id) { return Math.abs(lineShift(id)) > 0.0004; }
  const oldWordKey = (w) => L.legacyWordKey(w, lineById(w.line_id));
  const wordKey = (w) => w.ref || oldWordKey(w);
  const wordEntry = (w, map) => (map ? (w.ref && map[w.ref]) || map[oldWordKey(w)] || null : null);
  function pendingWord(id) {
    const w = wordById(id);
    if (!w) return null;
    const o = wordEntry(w, (ovr().lyrics || {}).words);
    if (!o) return null;
    return J(o) === J(wordEntry(w, appliedWords())) ? null : o;
  }
  /** set fields of a word's override (under its stable key; an old id key is folded in) */
  function putWord(o, w, patch) {
    const ws = Object.assign({}, (o.lyrics = o.lyrics || {}).words || {});
    const k = wordKey(w), old = oldWordKey(w);
    const e = Object.assign({}, ws[old] || {}, ws[k] || {}, patch);
    if (k !== old) delete ws[old];
    for (const f of Object.keys(e)) { if (e[f] == null) delete e[f]; else e[f] = L.r3(e[f]); }
    delete e.dt;   // an absolute start replaces a relative shift
    ws[k] = e;
    o.lyrics.words = ws;
  }
  /** where a line and its words show now: {lt, a, b, words: [{w, t, d, pending}]}; `lt` moves it (a line drag) */
  function lineView(ln, lt) {
    const sh = lineShift(ln.id);
    const extra = lt != null ? lt - (ln.t + sh) : 0;
    const words = (V.model.wordsByLine.get(ln.id) || []).map((w) => {
      const p = wordShown(w, sh);
      return { w, t: p.t + extra, d: p.d, pending: p.pending };
    });
    const e = barEdges(ln);
    const [a, b] = L.barOf(ln.t + sh + extra, ln.d, words, e.start != null ? e.start + extra : null, e.end != null ? e.end + extra : null);
    return { lt: ln.t + sh + extra, a, b, words };
  }
  /** the bar's own start and end as saved (D84; absolute times, null = the line's span). A key naming every bar of a
   *  split line gives the start of its first bar and the end of its last one, as in the stage. */
  function barEdges(ln) {
    const ls = (ovr().lyrics || {}).lines || {};
    const ks = L.lineKeys(ln), own = ls[ks[0]] || {};
    const parts = ln.source_part == null ? [] : V.model.lines.filter((l) => l.ref && l.source_index === ln.source_index);
    const first = !parts.some((l) => (l.source_part || 0) < ln.source_part), last = !parts.some((l) => (l.source_part || 0) > ln.source_part);
    const from = (f, ok) => (own[f] != null ? own[f] : ok ? (ks.slice(1).map((k) => (ls[k] || {})[f]).find((x) => x != null) ?? null) : null);
    return { start: from('start', first), end: from('end', last) };
  }
  function setLineTime(id, newT) {
    const ln = lineById(id);
    if (!ln) return;
    const ks = L.lineKeys(ln), k = ks[0];
    const delta = newT - (ln.t + lineShift(id));
    return commit(`move ${id} to ${fmtTime(newT, 2)}`, (o) => {
      const ls = Object.assign({}, (o.lyrics = o.lyrics || {}).lines || {});
      const want = sumDt(appliedLines(), ks) + (newT - ln.t);   // what the stage should add to this line in total
      const old = ks[ks.length - 1];
      if (k !== old && ls[old] && !ln.source_part) { ls[k] = Object.assign({}, ls[old], ls[k] || {}, { dt: ((ls[k] || {}).dt || 0) + (ls[old].dt || 0) }); delete ls[old]; }
      const dt = L.r3(want - sumDt(ls, ks.filter((x) => x !== k)));
      const e = Object.assign({}, ls[k] || {}, { dt });
      if (Math.abs(dt) < 0.0005) delete e.dt;
      // the bar's own edges are absolute times: they move with the line (D84)
      for (const x of ks) {
        const src = x === k ? e : ls[x];
        if (!src || (src.start == null && src.end == null)) continue;
        const moved = Object.assign({}, src);
        if (moved.start != null) moved.start = L.r3(Math.max(0, moved.start + delta));
        if (moved.end != null) moved.end = L.r3(moved.end + delta);
        if (x === k) Object.assign(e, moved); else ls[x] = moved;
      }
      if (Object.keys(e).length) ls[k] = e; else delete ls[k];
      o.lyrics.lines = ls;
      // words placed by hand have an absolute time: they move with their line
      for (const w of V.model.wordsByLine.get(id) || []) {
        const e = wordEntry(w, o.lyrics.words);
        if (e && e.t != null) putWord(o, w, { t: Math.max(0, e.t + delta) });
      }
    });
  }
  function nudgeLine(id, dtMs) {
    const ln = lineById(id);
    if (!ln) return;
    return setLineTime(id, ln.t + lineShift(id) + dtMs / 1000);
  }
  // ---- single words and groups of words (D83: a word stays inside its bar)
  let wordIndex = null;
  const wordById = (id) => {
    const ws = V.song._get('lyrics').words || [];
    if (!wordIndex || wordIndex.src !== ws) wordIndex = { src: ws, map: new Map(ws.map((w) => [w.id, w])) };
    return wordIndex.map.get(id);
  };
  /** where a word shows now (see logic.wordPos): {t, d, pending} */
  function wordShown(w, dlt) {
    const ov = wordEntry(w, (ovr().lyrics || {}).words);
    const p = pendingWord(w.id);
    return Object.assign(L.wordPos(w, ov, p, dlt == null ? lineShift(w.line_id) : dlt), { pending: !!p });
  }
  /** [{w, t, d, a, b}] for word ids: where each shows and the bar it must stay in */
  function wordsInBars(ids) {
    const out = [];
    const views = new Map();
    for (const id of ids) {
      const w = wordById(id);
      if (!w) continue;
      if (!views.has(w.line_id)) { const ln = lineById(w.line_id); if (ln) views.set(w.line_id, lineView(ln)); }
      const v = views.get(w.line_id);
      const p = v ? v.words.find((x) => x.w.id === id) : null;
      if (p) out.push({ w, t: p.t, d: p.d, a: v.a, b: v.b });
    }
    return out;
  }
  /** move words by `delta` seconds, together; the move is cut so that none leaves its bar */
  function moveWords(ids, delta, label) {
    if (!ids.length) return;
    return commit(label || `move ${ids.length > 1 ? ids.length + ' words' : 'word ' + ids[0]}`, (o) => {
      const items = wordsInBars(ids);   // evaluated when this save runs: saves queued before it may have moved them
      const d = L.clampGroupDelta(items, delta);
      if (Math.abs(d) < 0.0005) { if (Math.abs(delta) >= 0.0005) toast('The words are at the edge of their bar: drag the bar\'s edge to make room'); return; }
      for (const x of items) putWord(o, x.w, { t: x.t + d });
    });
  }
  function setWordTime(id, t) {
    const x = wordsInBars([id])[0];
    if (x) return moveWords([id], t - x.t, `move word ${id} to ${fmtTime(t, 3)}`);
  }
  function setWordDur(id, d) {
    const x = wordsInBars([id])[0];
    if (!x) return;
    const nd = Math.max(0.02, Math.min(d, x.b - x.t));
    if (nd < d - 0.0005) toast('The word would end after its bar: it ends at the bar\'s end');
    return commit(`word ${id} length ${Math.round(nd * 1000)} ms`, (o) => putWord(o, x.w, { t: x.t, d: nd }));
  }
  function nudgeWord(id, ms) { return moveWords(selectedWords(id), ms / 1000, `move ${selectedWords(id).length > 1 ? selectedWords(id).length + ' words' : 'word ' + id} ${ms > 0 ? '+' : ''}${ms} ms`); }
  function resetWord(id) {
    const ids = selectedWords(id);
    return commit(`reset ${ids.length > 1 ? ids.length + ' words' : 'word ' + id}`, (o) => {
      const ws = Object.assign({}, (o.lyrics || {}).words || {});
      for (const i of ids) { const w = wordById(i); if (w) { delete ws[oldWordKey(w)]; if (w.ref) delete ws[w.ref]; } }
      (o.lyrics = o.lyrics || {}).words = ws;
    });
  }
  /** a line's bar resized to [a2, b2] (D84): only the bar changes, no word moves; an edge stops at the first word's
   *  start or the last word's end, so every word stays inside */
  function resizeBar(id, a2, b2) {
    const ln = lineById(id);
    if (!ln) return;
    const v = lineView(ln), lim = L.barEdgeLimits(v.words);
    const a = L.r3(Math.max(0, Math.min(a2, lim.maxStart))), b = L.r3(Math.max(b2, lim.minEnd, a + 0.05));
    const k = L.lineKeys(ln)[0];
    return commit(`bar ${id} ${fmtTime(a, 2)}-${fmtTime(b, 2)}`, (o) => {
      const ls = Object.assign({}, (o.lyrics = o.lyrics || {}).lines || {});
      const e = Object.assign({}, ls[k] || {});
      if (Math.abs(a - v.a) > 0.0005) e.start = a;
      if (Math.abs(b - v.b) > 0.0005) e.end = b;
      ls[k] = e;
      o.lyrics.lines = ls;
    });
  }
  /** the words an action applies to: the selection when `id` is in it, else just `id` */
  function selectedWords(id) { return SEL.words.has(id) ? [...SEL.words] : [id]; }
  /** mode: 'only' (a click), 'toggle' (Ctrl/Cmd+click), 'range' (Shift+click: every word between the last one and this) */
  function selectWord(id, lineId, mode) {
    if (mode === 'toggle') { if (SEL.words.has(id)) SEL.words.delete(id); else SEL.words.add(id); }
    else if (mode === 'range' && SEL.wordId) {
      const all = V.song._get('lyrics').words || [];
      const i = all.findIndex((w) => w.id === SEL.wordId), j = all.findIndex((w) => w.id === id);
      if (i >= 0 && j >= 0) for (let k = Math.min(i, j); k <= Math.max(i, j); k++) SEL.words.add(all[k].id);
    } else if (mode !== 'keep' || !SEL.words.has(id)) { SEL.words.clear(); SEL.words.add(id); }
    if (!SEL.words.size) { SEL.wordId = null; } else { SEL.wordId = SEL.words.has(id) ? id : [...SEL.words][0]; SEL.lineId = wordById(SEL.wordId).line_id; }
    requestDraw('lyrics'); refreshPanel();
  }
  function clearWords() { SEL.words.clear(); SEL.wordId = null; requestDraw('lyrics'); refreshPanel(); }
  // ---- splits: a source line cut into bars at word positions (D83)
  function splitAt(ln, ks, joinKs) {
    if (ln.source_index == null) { toast(ln.source_index === undefined ? 'Re-run the analysis once to split lines (this folder was made by an older version)' : 'This line was added by the harness, so it cannot be split', 'bad', 6000); return; }
    return commit(`${ks.length ? 'split' : 'join'} ${ln.id}`, (o) => {
      (o.lyrics = o.lyrics || {}).splits = L.editSplits(o.lyrics.splits, ln.source_index, ln.pin_key, ks, joinKs);
      if (!o.lyrics.splits.length) delete o.lyrics.splits;
    });
  }
  /** the word positions (in the source line) that cut the selection into its own bar */
  function splitSelection(ids) {
    const ws = ids.map(wordById).filter(Boolean);
    const ln = ws.length ? lineById(ws[0].line_id) : null;
    if (!ln || ws.some((w) => w.line_id !== ln.id)) { toast('Select words of one bar to split it', 'bad'); return; }
    const all = V.model.wordsByLine.get(ln.id) || [];
    const idx = ws.map((w) => all.indexOf(w)).sort((x, y) => x - y);
    if (idx[idx.length - 1] - idx[0] + 1 !== idx.length) { toast('Select words that follow each other', 'bad'); return; }
    const first = L.refWord(all[idx[0]].ref), lastNext = idx[idx.length - 1] + 1 < all.length ? L.refWord(all[idx[idx.length - 1] + 1].ref) : null;
    if (!first) { toast('Re-run the analysis once to split lines (this folder was made by an older version)', 'bad', 6000); return; }
    const ks = [];
    if (idx[0] > 0) ks.push(first.k);
    if (lastNext) ks.push(lastNext.k);
    if (!ks.length) { toast('These are all the words of the bar: nothing to split', 'warn'); return; }
    return splitAt(ln, ks, []);
  }
  /** the split positions waiting for a re-run, as word ids (drawn as a mark in their bar) */
  function pendingSplitWords() {
    const out = new Set();
    const applied = appliedOverrides('lyrics')['lyrics.splits'] || [];
    for (const s of ((ovr().lyrics || {}).splits || [])) {
      const a = applied.find((x) => x.index === s.index);
      for (const k of s.at) {
        if (a && a.at.includes(k)) continue;
        const w = (V.song._get('lyrics').words || []).find((x) => x.ref === `r${s.index}w${k}`);
        if (w) out.add(w.id);
      }
    }
    return out;
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
  function setLineVoice(id, voice) {
    const ln = lineById(id);
    const ks = ln ? L.lineKeys(ln) : [id], k = ks[0];
    return commit(`${id} sung by ${voice || '(auto)'}`, (o) => {
      const v = (o.voices = o.voices || {});
      v.lines = Object.assign({}, v.lines || {});
      if (!ln || !ln.source_part) for (const x of ks.slice(1)) delete v.lines[x];   // an older key of the same line
      if (voice) v.lines[k] = voice; else delete v.lines[k];
    });
  }
  /** remove a voice: its lines go to `target` on the next re-run (null keeps the voice) */
  function mergeVoice(vid, target) {
    return commit(target ? `merge ${vid} into ${target}` : `keep ${vid}`, (o) => {
      const v = (o.voices = o.voices || {});
      v.merge = Object.assign({}, v.merge || {});
      if (target) v.merge[vid] = target; else delete v.merge[vid];
      if (!Object.keys(v.merge).length) delete v.merge;
    });
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
  function meaningPanel(host, M) {
    const m = M.meaning || {};
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

    // ---- single lyric lines (D87): optional notes. Sections are the music's parts: they get no meaning box here
    const notes = I.lines || {};
    const withNote = M.lines.map((l) => [l, L.lineNoteOf(notes, M.lines, l)]).filter((x) => x[1]);
    host.append(h('h3', null, 'Meaning of single lines (optional)'),
      h('div', { class: 'dim small' }, 'Extra information where a line needs it. Select a line in the Lyrics lane and write it under "Lyrics & singers". A line that repeats shares its meaning with every repeat unless you untick that.'),
      withNote.length ? withNote.map(([l, n]) => h('div', { class: 'pendrow' }, btn(l.id, () => { selectLine(l.id); seek(l.t); }, 'select this line'), ' ',
        n.note.length > 90 ? n.note.slice(0, 90) + '…' : n.note, n.own ? null : h('span', { class: 'dim small' }, ` (from ${n.from})`)))
        : h('div', { class: 'dim' }, 'No line has a note.'));
    // answers by section or group saved before this change stay in intent.md, and agents still get them
    const oldSec = Object.keys(I.sections || {}), oldGrp = Object.keys(I.groups || {});
    if (oldSec.length || oldGrp.length) {
      const clear = { sections: Object.fromEntries(oldSec.map((x) => [x, null])), groups: Object.fromEntries(oldGrp.map((x) => [x, null])) };
      host.append(h('div', { class: 'dim small' }, `meaning/intent.md still holds ${oldSec.length + oldGrp.length} answer(s) by section or group from an earlier version of the viewer (${[...oldGrp.map((x) => 'every ' + (x === 'all' ? 'section' : x)), ...oldSec].join(', ')}). Agents still get them.`),
        h('div', { class: 'btnrow' }, btn('remove them', () => saveIntent(clear, 'removed the section answers'), 'only the viewer block of intent.md; the template is not touched')));
    }
  }

  /** D87: what one lyric line means (optional extra information, the user's words). A line that repeats shares one
   *  note with every repeat by default; unticking gives this line its own. */
  function lineNoteBox(host, ln) {
    const M = V.model, notes = (V.intent || {}).lines || {};
    const cur = L.lineNoteOf(notes, M.lines, ln);
    const reps = ln.repeat_group ? M.lines.filter((l) => l.repeat_group === ln.repeat_group && l.id !== ln.id) : [];
    const ks = L.lineKeys(ln), k = ks[0], fid = 'line|' + ln.id;
    const ta = keptArea(fid, cur ? cur.note : '', { rows: 2, class: 'txt', placeholder: 'optional: what this line means, who it is aimed at, a reference ...' });
    const chk = reps.length ? h('input', { type: 'checkbox', checked: cur ? cur.repeats : true }) : null;
    if (chk) chk.addEventListener('change', () => {   // unticked on a line that shows a repeat's note: start its own
      if (!chk.checked && cur && !cur.own && ta.value === cur.note) { ta.value = ''; typed.set(fid, ''); }
    });
    const save = () => {
      const note = ta.value.trim(), repeats = chk ? chk.checked : true;
      // a shared note edited from another repeat is the same note: it stays under the line that holds it
      const target = repeats && cur && !cur.own ? cur.key : k;
      const patch = { lines: {} };
      for (const x of ks) if (x !== target && notes[x]) patch.lines[x] = null;   // an older key of this line
      patch.lines[target] = note ? { note, repeats } : null;
      saveIntent(patch, `meaning of ${ln.id}`, () => typed.delete(fid));
    };
    const clear = () => saveIntent({ lines: Object.fromEntries(ks.filter((x) => notes[x]).map((x) => [x, null])) }, `cleared the meaning of ${ln.id}`, () => typed.delete(fid));
    host.append(h('div', { class: 'blk' },
      h('div', { class: 'lbl' }, 'what this line means (optional) ', cur ? h('span', { class: 'pill good' }, cur.own ? 'yours' : 'yours, from ' + cur.from) : null),
      ta,
      chk ? h('label', { class: 'small' }, chk, ` same for every repeat of this line (${reps.length + 1} in all)`) : null,
      h('div', { class: 'btnrow' }, btn('save line meaning', save), cur && cur.own ? btn('clear', clear, 'remove this line\'s own note') : null),
      h('div', { class: 'dim small' }, reps.length
        ? 'Written to meaning/intent.md for the video agents. Ticked: one meaning for every repeat. Untick to give this repeat a meaning of its own. Re-runs: meaning, brief.'
        : 'Written to meaning/intent.md for the video agents. Re-runs: meaning, brief.')));
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
      const vmap = (ovr().voices || {}).lines || {};
      const curV = L.lineKeys(ln).map((k) => vmap[k]).find(Boolean) || M.voiceOfLine.get(ln.id) || '';
      const added = [...new Set(Object.values(vmap))].filter((v) => !vopts.includes(v));   // voices added since the last run
      const nextV = 'V' + (Math.max(0, ...[...vopts, ...added].map((v) => +v.slice(1))) + 1);
      host.append(h('div', { class: 'form-row' }, h('span', { class: 'lbl' }, 'sung by'), h('select', { onchange: (e) => setLineVoice(ln.id, e.target.value) }, h('option', { value: '' }, '(automatic)'),
        [...vopts, ...added].map((v) => h('option', { value: v, selected: v === curV }, v + (M.charOfVoice.get(v) ? ' — ' + M.charName(M.charOfVoice.get(v)) : added.includes(v) ? ' (new, after re-run)' : ''))),
        h('option', { value: nextV }, `+ new voice (${nextV})`))));
      if (ln.source_part != null && ln.source_part > 0) {
        host.append(h('div', { class: 'btnrow' }, btn('join with the bar before', () => splitAt(ln, [], [ln.source_word]), 'undo the split that started this bar')));
      }
      lineNoteBox(host, ln);
      const sel = [...SEL.words].map(wordById).filter(Boolean);
      const w = SEL.wordId ? wordById(SEL.wordId) : null;
      if (w && sel.length) {
        const many = sel.length > 1;
        const pos = wordShown(w);
        const anyOv = sel.some((x) => wordEntry(x, (ovr().lyrics || {}).words));
        const oneBar = sel.every((x) => x.line_id === w.line_id);
        const first = wordsInBars(sel.map((x) => x.id)).reduce((m, x) => (m == null || x.t < m ? x.t : m), null);
        const wIdx = (V.model.wordsByLine.get(w.line_id) || []).indexOf(w);
        host.append(h('div', { class: 'card' },
          many ? h('b', null, `${sel.length} words selected`) : [h('b', null, w.id), ' ', w.text, ' ',
            h('span', { class: 'dim small' }, `${fmtTime(pos.t, 3)} · ${Math.round(pos.d * 1000)} ms${pos.pending ? ' · not re-run yet' : ''}`)],
          many ? h('div', { class: 'dim small' }, sel.map((x) => x.text).join(' ')) : null),
        h('div', { class: 'btnrow' }, [-50, -10, 10, 50].map((d) => btn((d > 0 ? '+' : '') + d + ' ms', () => nudgeWord(w.id, d))),
          btn('start at playhead', () => moveWords(sel.map((x) => x.id), V.t - first, many ? 'selection to the playhead' : `word ${w.id} to the playhead`), many ? 'the first selected word starts where the playhead is' : 'the word starts where the playhead is'),
          many ? null : btn('end at playhead', () => { if (V.t - pos.t >= 0.02) setWordDur(w.id, V.t - pos.t); else toast('The playhead is before the word: nothing changed', 'bad'); }, 'the word ends where the playhead is'),
          anyOv ? btn('reset', () => resetWord(w.id), 'back to the analysed timing') : null,
          btn('clear selection', clearWords)),
        many ? null : numRow('word start', Math.round(pos.t * 1000), 'ms', (v) => setWordTime(w.id, v / 1000), { step: 5 }),
        many ? null : numRow('word length', Math.round(pos.d * 1000), 'ms', (v) => setWordDur(w.id, v / 1000), { step: 5, min: 20 }),
        oneBar ? h('div', { class: 'btnrow' },
          !many && wIdx > 0 ? btn('split the bar before this word', () => { const r = L.refWord(w.ref); if (r) splitAt(lineById(w.line_id), [r.k], []); else toast('Re-run the analysis once to split lines (this folder was made by an older version)', 'bad', 6000); }, 'this word and the ones after it become a new bar') : null,
          btn(many ? 'move these words to a new bar' : 'move this word to its own bar', () => splitSelection(sel.map((x) => x.id)), 'cut the bar around the selection; give the new bar its own voice under "sung by"')) : null,
        h('div', { class: 'dim small' }, 'Click a word to select it, Ctrl+click to add or remove one, Shift+click for a range; drag a selected word to move them all, drag a word\'s right edge to change its length. Words stay inside their bar: drag the bar\'s left or right edge to make it longer or shorter (no word moves; an edge stops at the first or last word). Keys < and > move the selection by 10 ms, Esc clears it.'));
      } else {
        host.append(h('div', { class: 'dim small' }, 'Single words: zoom in on the Lyrics lane until the words show under the line, then click or drag one. A bar\'s left and right edges make it longer or shorter; its words stay where they are.'));
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
    host.append(h('h3', null, 'Voices → characters'), h('div', { class: 'dim small' }, 'Characters are written to meaning/intent.md (managed block). To add a voice, choose "+ new voice" under a line\'s "sung by"; to remove one, merge it into another. Re-runs: voices, meaning.'));
    const merges = (ovr().voices || {}).merge || {};
    const chars = M.characters.length ? M.characters : [];
    for (const v of M.voices) {
      const mapped = (V.intent.voices || {})[v.id] || {};
      const curC = mapped.character_id || M.charOfVoice.get(v.id) || '';
      const nameInp = h('input', { type: 'text', class: 'txt', value: mapped.name || (curC ? M.charName(curC) : ''), placeholder: 'character name' });
      const csel = h('select', null, h('option', { value: '' }, '(none)'),
        chars.map((c) => h('option', { value: c.id, selected: c.id === curC }, `${c.id} ${c.name}`)),
        h('option', { value: '__new' }, '+ new character'));
      csel.addEventListener('change', () => { if (csel.value && csel.value !== '__new') { const c = chars.find((x) => x.id === csel.value); nameInp.value = c ? c.name : nameInp.value; } });
      const into = merges[v.id];
      const mergeSel = h('select', { onchange: (e) => mergeVoice(v.id, e.target.value || null), title: 'remove this voice: its lines go to the voice you choose' },
        h('option', { value: '' }, into ? `(keep ${v.id})` : '(keep)'), M.voices.filter((x) => x.id !== v.id).map((x) => h('option', { value: x.id, selected: x.id === into }, `merge into ${x.id}`)));
      host.append(h('div', { class: 'card' + (into ? ' dim' : '') }, h('div', { class: 'row-between' }, h('b', null, v.id + (into ? ` → ${into} on the next re-run` : '')), h('span', { class: 'dim small' }, `${Math.round(v.seconds || 0)} s · ${v.n_lines || 0} lines`)),
        h('div', { class: 'form-row' }, h('span', { class: 'lbl' }, 'remove voice'), mergeSel),
        h('div', { class: 'form-row' }, csel, nameInp, btn('save', () => {
          let cid = csel.value;
          if (cid === '__new' || (!cid && nameInp.value)) { const used = new Set([...chars.map((c) => c.id), ...Object.values(V.intent.voices || {}).map((x) => x.character_id)]); let n = 1; while (used.has('C' + n)) n++; cid = 'C' + n; }
          saveIntent({ voices: { [v.id]: cid ? { character_id: cid, name: nameInp.value.trim() || cid } : null } }, `${v.id} → ${cid || 'none'}`);
        }))));
    }
    if (!M.voices.length) host.append(h('div', { class: 'dim' }, 'No voices detected.'));
    // ---- meaning: the whole song (D81), single lines (D87)
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

  return { lineView, barEdges, wordsInBars, moveWords, resizeBar, clearWords, pendingSplitWords, splitSelection, mergeVoice, wordShown, nudgeWord, selectWord, resetWord, linePinOf, pinLine, unpinLine, moveBoundary, addBoundary, removeBoundary, setLabel, setLineTime, nudgeLine, setLineVoice, setRhythm, saveIntent, setWordTime, setWordDur, addPin, removePin, undo, pendingLine, pendingWord, pendingBoundaries, lineShift,
    refreshPanel, renderBar, save, commit, state: st };
})();
