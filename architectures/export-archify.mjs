#!/usr/bin/env node
// Drive archify HTML viewer exports via CDP: PNG (rasterized SVG) + SVG (dual-theme).
// Usage: node export-archify.mjs <file://url> <outPrefix>
import { execFile } from 'node:child_process';
import { mkdtempSync, readdirSync, statSync, renameSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import wsPkg from '/Users/shenqing/.dsh/profiles/web/node_modules/ws/index.js';
const { WebSocket } = wsPkg;

const [, , htmlPath, outPrefix] = process.argv;
if (!htmlPath || !outPrefix) { console.error('usage: export-archify.mjs <html> <outPrefix>'); process.exit(2); }

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PORT = 9338;
const prof = mkdtempSync(join(tmpdir(), 'archify-chrome-'));
const outDir = mkdtempSync(join(tmpdir(), 'archify-dl-'));

const chrome = execFile(CHROME, [
  '--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${prof}`,
  '--no-first-run', '--no-sandbox', '--disable-gpu', 'about:blank',
], () => {});
process.on('exit', () => { try { chrome.kill(); } catch {} });

const wait = (ms) => new Promise(r => setTimeout(r, ms));
async function cdpInfo() {
  for (let i = 0; i < 40; i++) {
    try { const r = await fetch(`http://127.0.0.1:${PORT}/json/version`); return await r.json(); } catch { await wait(250); }
  }
  throw new Error('chrome debug port never came up');
}

const info = await cdpInfo();
const browserWs = info.webSocketDebuggerUrl;

const ws = new WebSocket(browserWs);
await new Promise((res, rej) => {
  const t = setTimeout(() => rej(new Error('ws open timeout')), 10000);
  ws.once('open', () => { clearTimeout(t); res(); });
  ws.once('error', () => { clearTimeout(t); rej(new Error('ws open failed')); });
});

let msgId = 0;
const pending = new Map();
ws.on('message', (data) => {
  const m = JSON.parse(data.toString());
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
});
const send = (method, params = {}, sessionId) => new Promise((res, rej) => {
  const id = ++msgId;
  pending.set(id, res);
  ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
  setTimeout(() => { if (pending.has(id)) { pending.delete(id); rej(new Error('cdp timeout: ' + method)); } }, 20000);
});

const ver = await send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: outDir, eventsEnabled: true });
if (ver.error) throw new Error('setDownloadBehavior failed: ' + JSON.stringify(ver.error));

const created = await send('Target.createTarget', { url: 'about:blank' });
if (created.error) throw new Error('createTarget failed: ' + JSON.stringify(created.error));
const targetId = created.result.targetId;
const attached = await send('Target.attachToTarget', { targetId, flatten: true });
if (attached.error) throw new Error('attachToTarget failed: ' + JSON.stringify(attached.error));
const sessionId = attached.result.sessionId;
await send('Page.enable', {}, sessionId);
await send('Page.navigate', { url: 'file://' + htmlPath }, sessionId);
await wait(4000); // let runtime init

async function evaluate(expr) {
  const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }, sessionId);
  if (r.result?.exceptionDetails) throw new Error('evaluate failed: ' + JSON.stringify(r.result.exceptionDetails.exception?.description || r.result.exceptionDetails));
  return r.result?.result?.value;
}

const ok = await evaluate("typeof Archify !== 'undefined' && !!(Archify.exportMenu && Archify.exportMenu.run)");
if (!ok) throw new Error('Archify.exportMenu not available on page');

async function exportOne(format) {
  const before = new Set(readdirSync(outDir));
  await evaluate(`Archify.exportMenu.run(${JSON.stringify(format)})`);
  for (let i = 0; i < 60; i++) {
    await wait(500);
    const now = readdirSync(outDir);
    const fresh = now.filter(f => !before.has(f) && !f.endsWith('.crdownload'));
    if (fresh.length) return join(outDir, fresh[0]);
    const err = await evaluate("document.documentElement.getAttribute('data-last-export-error')");
    if (err) throw new Error('export error (' + format + '): ' + err);
  }
  throw new Error('no download appeared for ' + format);
}

for (const fmt of ['png', 'svg']) {
  const f = await exportOne(fmt);
  const dest = outPrefix + '.' + fmt;
  renameSync(f, dest);
  const kb = Math.round(statSync(dest).size / 1024);
  console.log(`${fmt}: ${dest} (${kb} KB)`);
}
ws.close();
try { chrome.kill(); } catch {}
console.log('DONE');
