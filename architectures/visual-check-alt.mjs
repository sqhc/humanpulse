#!/usr/bin/env node
// Containment check + screenshots at archify review viewports (equivalent of visual-check).
// Usage: node visual-check-alt.mjs <file://url> <shotPrefix>
import { execFile } from 'node:child_process';
import { mkdtempSync, readdirSync, statSync, renameSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import wsPkg from '/Users/shenqing/.dsh/profiles/web/node_modules/ws/index.js';
const { WebSocket } = wsPkg;

const [, , htmlPath, shotPrefix] = process.argv;
if (!htmlPath || !shotPrefix) { console.error('usage: visual-check-alt.mjs <html> <shotPrefix>'); process.exit(2); }

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PORT = 9341;
const prof = mkdtempSync(join(tmpdir(), 'archify-vc-'));
const shotDir = join(tmpdir(), 'archify-shots-' + Date.now());
mkdirSync(shotDir, { recursive: true });

const chrome = execFile(CHROME, [
  '--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${prof}`,
  '--no-first-run', '--no-sandbox', '--disable-gpu', '--hide-scrollbars', 'about:blank',
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
const ws = new WebSocket(info.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.once('open', res); ws.once('error', () => rej(new Error('ws failed'))); });
let msgId = 0; const pending = new Map();
ws.on('message', (data) => { const m = JSON.parse(data.toString()); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } });
const send = (method, params = {}, sessionId) => new Promise((res, rej) => {
  const id = ++msgId; pending.set(id, res);
  ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
  setTimeout(() => { if (pending.has(id)) { pending.delete(id); rej(new Error('cdp timeout: ' + method)); } }, 25000);
});

const created = await send('Target.createTarget', { url: 'about:blank' });
const { sessionId } = (await send('Target.attachToTarget', { targetId: created.result.targetId, flatten: true })).result;
await send('Page.enable', {}, sessionId);

const VIEWPORTS = [[1440, 900], [1600, 1000], [1920, 1080], [2048, 1320]];
let allOk = true;
for (const [w, h] of VIEWPORTS) {
  await send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 1, mobile: false }, sessionId);
  await send('Page.navigate', { url: 'file://' + htmlPath }, sessionId);
  await wait(3000);
  const m = await send('Runtime.evaluate', {
    expression: `JSON.stringify({sw: document.documentElement.scrollWidth, sh: document.documentElement.scrollHeight, iw: window.innerWidth, ih: window.innerHeight})`,
    returnByValue: true,
  }, sessionId);
  const { sw, sh } = JSON.parse(m.result.result.value);
  const ok = sw <= w && sh <= h;
  if (!ok) allOk = false;
  console.log(`${w}x${h}: scroll ${sw}x${sh} ${ok ? 'OK' : 'OVERFLOW'}`);
  if (w === 1440 || w === 2048) {
    const shot = await send('Page.captureScreenshot', { format: 'png' }, sessionId);
    const f = join(shotDir, `shot-${w}.png`);
    const { writeFileSync } = await import('node:fs');
    writeFileSync(f, Buffer.from(shot.result.data, 'base64'));
    renameSync(f, `${shotPrefix}-${w}.png`);
    console.log(`  shot: ${shotPrefix}-${w}.png (${Math.round(statSync(`${shotPrefix}-${w}.png`).size / 1024)} KB)`);
  }
}
ws.close(); try { chrome.kill(); } catch {}
console.log(allOk ? 'CONTAINMENT PASS' : 'CONTAINMENT FAIL');
