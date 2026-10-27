// Pulls the live intro's world (constants, camera and atmosphere keys, scene shader) out of intro_live.js.
// intro_live.js = `git show hiking/main:site/assets/js/intro.js` (the version on GitHub Pages).
import { readFileSync, writeFileSync } from 'node:fs';
import vm from 'node:vm';
const src = readFileSync(new URL('intro_live.js', import.meta.url), 'utf8');
const a = src.indexOf('// ---------------------------------------------------------------- math');
const b = src.indexOf('// Snow: instanced streaks');
const ctx = { Math, params: new URLSearchParams() };
const out = vm.runInNewContext(src.slice(a, b) + `
({ SUMMIT, NF, TX, TY, DEPTH, CU, CV, CLIMBER, LOOK, KEYS, LOOKS, SCENE_FS, NOISE_FS,
   cam: (p, time) => camera(p, time), look: (p) => look(p) })`, ctx);
const N = +process.argv[2] || 360, FPS = 24;
const frames = [];
for (let f = 0; f <= N; f++) {
  const p = f / N, time = f / FPS;
  const c = out.cam(p, time), L = out.look(p);
  frames.push({ p, pos: c.pos, tgt: c.tgt, fov: c.fov, ...L,
    white: (t => t * t * (3 - 2 * t))(Math.min(1, Math.max(0, (p - 0.975) / 0.02))),
    vig: 1 - (t => t * t * (3 - 2 * t))(Math.min(1, Math.max(0, (p - 0.87) / 0.1))),
    snow: (0.55 + 0.45 * Math.min(1, p / 0.5)) * (1 - (t => t * t * (3 - 2 * t))(Math.min(1, Math.max(0, (p - 0.9) / 0.07)))),
    grain: 0.09 * Math.min(1, Math.max(0, (0.97 - p) * 8)),
    // the site's pixel, in radians, at its starting render scale (0.62 x 982 px): the climber and rope never get thinner
    upix: 2 / ((1 / Math.tan((c.fov * Math.PI) / 360)) * Math.round(982 * 0.62)) });
}
const { SUMMIT, NF, TX, TY, DEPTH, CU, CV, CLIMBER, KEYS, LOOKS } = out;
writeFileSync(new URL('scene_shader.glsl', import.meta.url), out.SCENE_FS);
writeFileSync(new URL('noise_shader.glsl', import.meta.url), out.NOISE_FS);
writeFileSync(new URL('intro_world.json', import.meta.url), JSON.stringify({
  source: 'hiking/main:site/assets/js/intro.js', axes: 'site: x right, y up, z toward the first camera (metres)',
  fps: FPS, SUMMIT, NF, TX, TY, DEPTH, CU, CV, CLIMBER, KEYS, LOOKS, frames }, null, 1));
console.log('frames', frames.length, 'climber', CLIMBER.map(v => v.toFixed(2)).join(','));
