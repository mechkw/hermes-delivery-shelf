// usage: node render.mjs stills <t1,t2,...> <outdir>
import path from 'node:path';
//        node render.mjs segment <startFrame> <endFrame> <out.mp4>
import { createRequire } from 'node:module';
const { chromium } = createRequire(process.env.NODE_PATH ? path.join(process.env.NODE_PATH.split(':')[0], 'x') : import.meta.url)('playwright');
import { spawn } from 'node:child_process';
import fs from 'node:fs';

import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const audio = JSON.parse(fs.readFileSync(path.join(here, 'audio.json'), 'utf8'));
const [mode, a, b, out] = process.argv.slice(2);

const browser = await chromium.launch({ args: ['--allow-file-access-from-files', '--disable-web-security'] });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
page.on('console', m => { if (m.type() === 'error') console.error('[page]', m.text()); });
page.on('pageerror', e => console.error('[pageerror]', e.message));
await page.addInitScript(d => { window.AUDIO = d; }, { rms: audio.rms, low: audio.low, high: audio.high });
await page.goto('file://' + path.join(here, 'index.html'));
await page.waitForFunction(() => window.READY || window.ERR, null, { timeout: 60000 });
const err = await page.evaluate(() => window.ERR);
if (err) { console.error(err); process.exit(1); }

if (mode === 'stills') {
  const ts = a.split(',').map(Number); const dir = b; fs.mkdirSync(dir, { recursive: true });
  for (const t of ts) {
    const f = Math.round(t * 30);
    const durl = await page.evaluate(f => window.frameJPEG(f, 0.9), f);
    fs.writeFileSync(path.join(dir, `t${t.toFixed(2).padStart(6, '0')}.jpg`), Buffer.from(durl.split(',')[1], 'base64'));
  }
} else if (mode === 'segment') {
  const s = +a, e = +b;
  const ff = spawn('ffmpeg', ['-v', 'error', '-y', '-f', 'image2pipe', '-framerate', '30', '-c:v', 'mjpeg', '-i', '-',
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '17', '-pix_fmt', 'yuv420p', '-g', '60', '-bf', '2', '-r', '30', out], { stdio: ['pipe', 'inherit', 'inherit'] });
  const t0 = Date.now();
  for (let f = s; f < e; f++) {
    const durl = await page.evaluate(f => window.frameJPEG(f, 0.95), f);
    const buf = Buffer.from(durl.split(',')[1], 'base64');
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if ((f - s) % 150 === 0) console.log(`[${s}-${e}] frame ${f} ${((Date.now() - t0) / (f - s + 1)).toFixed(0)}ms/f`);
  }
  ff.stdin.end();
  await new Promise(r => ff.on('close', r));
}
await browser.close();
