// Runs sampler.html in headless Chrome (Metal) and executes the jobs listed in a JSON file.
// node gpu.mjs <jobs.json> <data dir>
// Job: { kind: 'grid', name, O, A, B, C, nx, ny, nz, u, mode } | { kind: 'points', name, n, u }
//    | { kind: 'blocks', name, n, c, u } | { kind: 'climber', name, O, A, B, C, nx, ny, nz }
import http from 'node:http';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { join, extname } from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire('/tmp/hc/');
const puppeteer = require('puppeteer-core');

const here = new URL('.', import.meta.url).pathname;
const [jobsFile, dataDir] = process.argv.slice(2);
mkdirSync(dataDir, { recursive: true });
const jobs = JSON.parse(readFileSync(jobsFile, 'utf8'));
const world = JSON.parse(readFileSync(join(here, 'intro_world.json'), 'utf8'));

// camera frames as the site builds them: forward, right, up, tan(fov/2)
const V = { sub: (a, b) => a.map((v, i) => v - b[i]), cross: (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]], norm: (a) => { const l = Math.hypot(...a); return a.map((v) => v / l); } };
const fr = [];
for (const f of world.frames) {
  const fw = V.norm(V.sub(f.tgt, f.pos)), r = V.norm(V.cross(fw, [0, 1, 0])), u = V.cross(r, fw);
  fr.push(...f.pos, Math.tan((f.fov * Math.PI) / 360), ...fw, 0, ...r, 0, ...u, 0);
}

const server = http.createServer((req, res) => {
  if (req.method === 'POST' && req.url.startsWith('/out/')) {
    const chunks = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', () => { writeFileSync(join(dataDir, req.url.slice(5)), Buffer.concat(chunks)); res.end('ok'); });
    return;
  }
  const file = req.url.startsWith('/in/') ? join(dataDir, req.url.slice(4)) : join(here, req.url.split('?')[0]);
  let body;
  try { body = readFileSync(file); } catch { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { 'content-type': extname(file) === '.html' ? 'text/html' : 'application/octet-stream' }); res.end(body);
}).listen(0);
await new Promise((r) => server.once('listening', r));
const port = server.address().port;

const browser = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: 'new', protocolTimeout: 0,
  args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist', '--disable-gpu-watchdog', '--disable-features=GpuWatchdog'] });
const page = await browser.newPage();
page.on('console', (m) => console.log('page:', m.text()));
page.on('pageerror', (e) => { console.error('page error:', e.message); process.exit(1); });
page.on('error', (e) => { console.error('page crashed:', e.message); process.exit(1); });
await page.goto(`http://localhost:${port}/sampler.html`);
await page.waitForFunction('window.ready === true', { timeout: 120000 });
await page.evaluate((a, n) => window.setFrames(a, n, 1512 / 982), fr, world.frames.length);
for (const job of jobs) {
  const t = Date.now();
  await page.evaluate((j) => window[{ grid: 'grid', points: 'points', blocks: 'blocks', climber: 'climber', noise: 'noiseVolume', couloir: 'couloir' }[j.kind]](j), job);
  console.log(job.kind, job.name, ((Date.now() - t) / 1000).toFixed(1) + ' s');
}
await browser.close();
server.close();
