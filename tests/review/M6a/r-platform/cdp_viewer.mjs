// R-PLATFORM review (M6a): drive viewer.html in a REAL headless browser (Edge/Chrome) over the DevTools protocol.
//   node cdp_viewer.mjs <browser.exe> <profile dir> <url> <scenario>
// Prints one JSON line with what the scenario observed; the pytest wrapper (test_browser_viewer.py) asserts on it.
// No dependencies: node >= 22 has fetch and WebSocket built in.
import { spawn } from 'node:child_process';
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const [, , exe, profile, url, scenario] = process.argv;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function launch() {
  const args = ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--mute-audio',
    '--autoplay-policy=no-user-gesture-required', '--remote-debugging-port=0', `--user-data-dir=${profile}`,
    '--window-size=1600,1000', 'about:blank'];
  const proc = spawn(exe, args, { stdio: 'ignore' });
  const portFile = join(profile, 'DevToolsActivePort');
  for (let i = 0; i < 200 && !existsSync(portFile); i++) await sleep(100);
  await sleep(200);
  const port = readFileSync(portFile, 'utf8').split(/\r?\n/)[0].trim();
  let target = null;
  for (let i = 0; i < 50 && !target; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      target = list.find((t) => t.type === 'page');
    } catch (e) { /* not up yet */ }
    if (!target) await sleep(100);
  }
  return { proc, port, wsUrl: target.webSocketDebuggerUrl };
}

function client(wsUrl) {
  const ws = new WebSocket(wsUrl);
  let id = 0;
  const pending = new Map();
  const events = [];
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); } else if (msg.method) events.push(msg);
  };
  const ready = new Promise((r) => { ws.onopen = r; });
  const send = (method, params) => new Promise((r) => { const k = ++id; pending.set(k, r); ws.send(JSON.stringify({ id: k, method, params: params || {} })); });
  const evaluate = async (expr) => {
    const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
    if (r.result && r.result.exceptionDetails) return { __error: r.result.exceptionDetails.exception ? r.result.exceptionDetails.exception.description : r.result.exceptionDetails.text };
    return r.result && r.result.result ? r.result.result.value : undefined;
  };
  return { ws, ready, send, evaluate, events };
}

const READY = `new Promise((res) => { const t0 = Date.now(); (function w() {
  const f = document.querySelector('#fatal');
  if (document.body && document.body.classList.contains('ready')) return res('ready');
  if (f && !f.hidden) return res('fatal');
  if (Date.now() - t0 > 20000) return res('timeout');
  setTimeout(w, 100); })(); })`;

function consoleErrors(events) {
  const out = [];
  for (const e of events) {
    if (e.method === 'Runtime.consoleAPICalled' && (e.params.type === 'error' || e.params.type === 'assert')) {
      out.push(e.params.args.map((a) => (a.value !== undefined ? String(a.value) : a.description || '')).join(' ').slice(0, 300));
    } else if (e.method === 'Runtime.exceptionThrown') {
      const d = e.params.exceptionDetails;
      out.push(('uncaught: ' + ((d.exception && d.exception.description) || d.text)).slice(0, 300));
    } else if (e.method === 'Log.entryAdded' && e.params.entry.level === 'error') {
      out.push(('log: ' + e.params.entry.text + ' ' + (e.params.entry.url || '')).slice(0, 300));
    }
  }
  return out;
}

async function main() {
  const { proc, wsUrl } = await launch();
  const c = client(wsUrl);
  await c.ready;
  const result = { scenario };
  try {
    await c.send('Runtime.enable');
    await c.send('Log.enable');
    await c.send('Page.enable');
    await c.send('Page.navigate', { url });
    await sleep(300);
    result.state = await c.evaluate(READY);
    result.fatal = await c.evaluate(`(document.querySelector('#fatal') && !document.querySelector('#fatal').hidden) ? document.querySelector('#fatal').innerText.slice(0, 300) : null`);
    if (result.state === 'ready') {
      await sleep(800); // first draws
      if (scenario === 'playhead') {
        // press Play exactly as a user does (the header button); the pointer stays off the lanes
        await c.evaluate(`document.querySelector('#btn-play').click(); true`);
        await sleep(2500);
        result.play = await c.evaluate(`({ playing: A.playing, paused: A.el.paused, currentTime: A.el.currentTime, viewT: V.t,
          clock: document.querySelector('#now-time').textContent, playheadX: document.querySelector('#playhead').style.transform })`);
      } else if (scenario === 'undo') {
        // Round 2: three +10 ms beat-offset edits (each save finished), then two clicks on Undo (each finished),
        // reading overrides.json from the server after every step
        await c.evaluate(`document.querySelector('[data-tab=edit]').click(); true`);
        await sleep(300);
        const disk = `(async () => { const o = await (await fetch('api/overrides', { cache: 'no-store' })).json(); return ((o.overrides || {}).rhythm || {}).beat_offset_s ?? null; })()`;
        const click = (label) => c.evaluate(`(() => { const b = [...document.querySelectorAll('#pane-edit button, #edit-bar button')].find((x) => x.textContent.trim() === ${JSON.stringify(label)}); if (!b || b.disabled) return false; b.click(); return true; })()`);
        result.steps = [];
        for (const label of ['+10', '+10', '+10', 'Undo', 'Undo']) {
          const ok = await click(label);
          await sleep(700);
          result.steps.push({ label, clicked: ok, disk: await c.evaluate(disk) });
        }
      } else if (scenario === 'undo-fail') {
        // Round 3: three +10 ms edits, then ONE Undo whose POST is answered exactly as the server answers when
        // overrides.json cannot be replaced (read-only / locked on Windows: 503), then two more Undos that succeed.
        await c.evaluate(`document.querySelector('[data-tab=edit]').click(); true`);
        await sleep(300);
        const disk = `(async () => { const o = await (await fetch('api/overrides', { cache: 'no-store' })).json(); return ((o.overrides || {}).rhythm || {}).beat_offset_s ?? null; })()`;
        const click = (label) => c.evaluate(`(() => { const b = [...document.querySelectorAll('#pane-edit button, #edit-bar button')].find((x) => x.textContent.trim() === ${JSON.stringify(label)}); if (!b || b.disabled) return false; b.click(); return true; })()`);
        const shown = `(((V.ovr || {}).rhythm || {}).beat_offset_s ?? null)`;
        result.steps = [];
        for (const label of ['+10', '+10', '+10']) {
          const ok = await click(label);
          await sleep(700);
          result.steps.push({ label, clicked: ok, disk: await c.evaluate(disk), shown: await c.evaluate(shown) });
        }
        await c.send('Fetch.enable', { patterns: [{ urlPattern: '*api/overrides*', requestStage: 'Request' }] });
        const ok = await click('Undo');
        let failed = 0;
        for (let i = 0; i < 60; i++) {
          const ev = c.events.find((e) => e.method === 'Fetch.requestPaused' && !e.__done);
          if (ev) {
            ev.__done = true;
            if (ev.params.request.method === 'POST' && !failed) {
              failed++;
              const body = Buffer.from(JSON.stringify({ error: 'could not write overrides.json (PermissionError); is it open in another program?' })).toString('base64');
              await c.send('Fetch.fulfillRequest', { requestId: ev.params.requestId, responseCode: 503, responseHeaders: [{ name: 'Content-Type', value: 'application/json; charset=utf-8' }], body });
            } else {
              await c.send('Fetch.continueRequest', { requestId: ev.params.requestId });
            }
          }
          await sleep(25);
        }
        await c.send('Fetch.disable');
        await sleep(300);
        result.steps.push({ label: 'Undo (503)', clicked: ok, failedPosts: failed, disk: await c.evaluate(disk), shown: await c.evaluate(shown) });
        for (const label of ['Undo', 'Undo']) {
          const ok2 = await click(label);
          await sleep(700);
          result.steps.push({ label, clicked: ok2, disk: await c.evaluate(disk), shown: await c.evaluate(shown) });
        }
      } else if (scenario === 'save-offline') {
        // the server is unreachable (stopped, idle timeout, Windows file lock): press a real edit button
        await c.evaluate(`document.querySelector('[data-tab=edit]').click(); true`);
        await sleep(300);
        await c.send('Network.enable');
        await c.send('Fetch.enable', { patterns: [{ urlPattern: '*api/overrides*', requestStage: 'Request' }] });
        const btn = await c.evaluate(`(() => { const b = [...document.querySelectorAll('#pane-edit button')].find((x) => x.textContent.trim() === '+10'); if (!b) return false; b.click(); return true; })()`);
        result.clicked = btn;
        // fail every POST to api/overrides at the network level
        for (let i = 0; i < 40; i++) {
          const ev = c.events.find((e) => e.method === 'Fetch.requestPaused' && !e.__done);
          if (ev) { ev.__done = true; await c.send('Fetch.failRequest', { requestId: ev.params.requestId, errorReason: 'ConnectionRefused' }); }
          await sleep(50);
        }
        await sleep(800);
        result.after = await c.evaluate(`({ ovr: V.ovr, gridPending: V.model.gridPending,
          bar: (document.querySelector('#pane-edit') || {}).innerText.slice(0, 40),
          toasts: [...document.querySelectorAll('#toasts .toast')].map((t) => t.className + ': ' + t.textContent.slice(0, 120)) })`);
      }
      await sleep(scenario === 'errors' ? 1500 : 200);
      result.laneErrors = await c.evaluate(`V.laneErrors || []`);
    }
    result.consoleErrors = consoleErrors(c.events);
  } catch (e) {
    result.harnessError = String(e && e.stack || e);
  } finally {
    try { await c.send('Browser.close'); } catch (e) { /* gone */ }
    try { c.ws.close(); } catch (e) { /* */ }
    await sleep(300);
    try { proc.kill(); } catch (e) { /* */ }
  }
  process.stdout.write(JSON.stringify(result) + '\n');
  process.exit(0);
}
main();
