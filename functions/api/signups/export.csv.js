// GET /api/signups/export.csv (AC 10, R1 OQ-3): rows not yet in Beehiiv as email,source,created_at.
// Gated by the X-Export-Token header (Pages secret EXPORT_TOKEN); missing or wrong -> 401. Exporting deletes nothing (R2).
import { Q, log } from '../../../signup/core.js';

async function digest(s) { return new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s))); }
export async function tokenMatches(given, secret) {
  if (!secret || typeof given !== 'string' || given === '') return false;
  const [a, b] = await Promise.all([digest(given), digest(secret)]);
  let d = 0; for (let i = 0; i < a.length; i++) d |= a[i] ^ b[i];
  return d === 0;
}
export function csvCell(v) {
  let s = v == null ? '' : String(v);
  if (/^[=+\-@\t\r]/.test(s)) s = `'${s}`;          // spreadsheet formula guard
  if (/[",\r\n]/.test(s)) s = `"${s.replace(/"/g, '""')}"`;
  return s;
}
export const CSV_COLUMNS = ['email', 'source', 'created_at'];
export function toCsv(rows) {
  return [CSV_COLUMNS.join(','), ...rows.map((r) => CSV_COLUMNS.map((c) => csvCell(r[c])).join(','))].join('\r\n') + '\r\n';
}
const deny = () => new Response('Unauthorized', { status: 401, headers: { 'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex' } });

export async function handleExport(request, env) {
  if (request.method !== 'GET') return deny();
  if (!(await tokenMatches(request.headers.get('X-Export-Token'), env.EXPORT_TOKEN))) { log('export', 'denied'); return deny(); }
  let rows;
  try { rows = (await env.SIGNUPS.prepare(Q.exportRows).all()).results || []; } catch { log('export', 'error'); return new Response('Export failed', { status: 500 }); }
  log('export', 'ok');
  return new Response(toCsv(rows), { status: 200, headers: {
    'Content-Type': 'text/csv; charset=utf-8', 'Content-Disposition': 'attachment; filename="awi-signups-unsent.csv"',
    'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex' } });
}
export const onRequest = (context) => handleExport(context.request, context.env);
