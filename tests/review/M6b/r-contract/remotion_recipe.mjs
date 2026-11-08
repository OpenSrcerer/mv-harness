// r-contract-m6b: execute the RECIPES.md Remotion recipe the way Remotion runs it (browser: URL base + fetch, no fs).
// argv: <RECIPES.md> <song folder> <mvh.js>. Prints one JSON line {include, errors[]}; exit 1 when a helper the recipe uses throws.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const [recipes, folder, lib] = process.argv.slice(2);
const md = readFileSync(recipes, 'utf8');
const block = md.split('## Remotion')[1].split('\n## ')[0];
const m = block.match(/include:\s*\[([^\]]*)\]/s);
if (!m) { console.log(JSON.stringify({ error: 'no include list in the Remotion recipe' })); process.exit(2); }
const include = [...m[1].matchAll(/'([^']+)'/g)].map((x) => x[1]);
const { load } = await import(pathToFileURL(lib).href);
// a browser-like fetch over the song folder (Remotion serves public/song/ over http)
const fetchShim = async (url) => {
  const rel = decodeURIComponent(new URL(url).pathname.replace(/^\/song\//, ''));
  try {
    const buf = readFileSync(join(folder, ...rel.split('/')));
    return { ok: true, status: 200, text: async () => buf.toString('utf8'),
             arrayBuffer: async () => buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) };
  } catch { return { ok: false, status: 404 }; }
};
const song = await load('http://localhost:3000/song/', { fetch: fetchShim, include, fr: { fps: 30 } });
const errors = [];
const frame = 30 * 20;              // 20 s: inside the first chorus of the synthetic song
const t = frame / 30;               // the recipe's clock
// the recipe's render body says: "...use song.count(t), song.singerAt(t)..."
for (const [name, f] of [['count', () => song.count(t)], ['singerAt', () => song.singerAt(t)]]) {
  try { f(); } catch (e) { errors.push(`${name}: ${String(e.message).slice(0, 160)}`); }
}
console.log(JSON.stringify({ include, errors }));
process.exit(errors.length ? 1 : 0);
