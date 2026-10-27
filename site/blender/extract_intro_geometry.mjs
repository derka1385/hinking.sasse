// Pull the current intro's world coordinates into an editable Blender source.
// Run from anywhere: node site/blender/extract_intro_geometry.mjs
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const here = new URL('.', import.meta.url);
const introURL = new URL('../assets/js/intro.js', here);
const source = readFileSync(introURL, 'utf8');
const start = source.indexOf('const clamp =');
const end = source.indexOf('const SCENE_FS =');
if (start < 0 || end <= start) throw new Error('Intro geometry block was not found');

const context = { Math, URLSearchParams, params: new URLSearchParams() };
const fields = '({ PYR, PEAKN, SUMMIT, CLIMBER, TEAM, NF, TY, DEEP, KEYS, RAISE, cameras: Array.from({length: 101}, (_, i) => camera(story(i / 100), 0)) })';
const geometry = vm.runInNewContext(source.slice(start, end) + '\n' + fields, context, { timeout: 2000 });
const data = {
  source: 'site/assets/js/intro.js',
  sourceSha256: createHash('sha256').update(source).digest('hex'),
  units: 'metres; site axes x-right, y-up, z-toward-camera',
  main: geometry.PYR.map(([apex, normals], i) => ({ name: ['Main summit', 'West shoulder', 'East shoulder'][i], apex, normals })),
  peaks: geometry.PEAKN.map(([apex, normals], i) => ({ name: `Side ridge ${String(i + 1).padStart(2, '0')}`, apex, normals })),
  summit: geometry.SUMMIT,
  climber: geometry.CLIMBER,
  team: geometry.TEAM,
  northFace: geometry.NF,
  faceUp: geometry.TY,
  valleyDepth: geometry.DEEP,
  cameraKeys: geometry.KEYS,
  cameraSamples: geometry.cameras,
  raise: geometry.RAISE,
};
const output = new URL('intro_mountain_source.json', here);
writeFileSync(output, JSON.stringify(data, null, 2) + '\n');
console.log(`Wrote ${fileURLToPath(output)} from ${data.sourceSha256.slice(0, 12)}`);
