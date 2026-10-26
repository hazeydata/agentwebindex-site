// Local test server for browser_check: serves dist/ and runs the real /api/subscribe handler (signup/core.js) on mocks
// (in-memory D1/KV, mocked Beehiiv 201). No network. Prints "port <n>" on stdout. GET /__rows returns stored rows (test only).
import http from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { join, extname, resolve } from 'node:path';
import { handleSubscribe } from '../../signup/core.js';
import { env, mockFetch } from './helpers.mjs';

const DIST = resolve(new URL('../../dist', import.meta.url).pathname);
const E = env();
const beehiiv = mockFetch();
let n = 0;
const TYPES = { '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.json': 'application/json' };

const srv = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  try {
    if (url.pathname === '/api/subscribe') {
      const chunks = []; for await (const c of req) chunks.push(c);
      const headers = new Headers(); for (const [k, v] of Object.entries(req.headers)) headers.set(k, String(v));
      headers.set('CF-Connecting-IP', `203.0.113.${(n++ % 250) + 1}`);   // distinct per request so browser flows never hit the per-IP limit
      const r = await handleSubscribe(new Request(url, { method: req.method, headers, body: req.method === 'POST' ? Buffer.concat(chunks) : undefined }), E,
        { fetch: beehiiv, now: Date.now() });
      res.writeHead(r.status, Object.fromEntries(r.headers)); res.end(Buffer.from(await r.arrayBuffer())); return;
    }
    if (url.pathname === '/__rows') { res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ rows: E.SIGNUPS.rows, beehiiv: beehiiv.calls.length })); return; }
    let f = join(DIST, decodeURIComponent(url.pathname));
    if (!f.startsWith(DIST)) throw new Error('path');
    if ((await stat(f).catch(() => null))?.isDirectory()) f = join(f, 'index.html');
    const body = await readFile(f);
    res.writeHead(200, { 'Content-Type': TYPES[extname(f)] || 'application/octet-stream' }); res.end(body);
  } catch { res.writeHead(404); res.end('not found'); }
});
srv.listen(0, '127.0.0.1', () => console.log(`port ${srv.address().port}`));
process.on('SIGTERM', () => srv.close(() => process.exit(0)));
