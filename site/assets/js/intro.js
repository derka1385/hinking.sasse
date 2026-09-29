// The ascent: fog, a valley, one continuous north face, a climber, then the page.
// Raw WebGL2, no library. One raymarched full-screen pass (terrain, rock, climber, fog,
// clouds) and one instanced pass for snow. Scroll never gets hijacked: the camera follows it, damped.
(() => {

const section = document.getElementById('intro');
const stage = section.querySelector('.intro-stage');
const canvas = section.querySelector('canvas');
const root = document.documentElement;

const params = new URLSearchParams(location.search);
const requestedP = Number(params.get('p'));
const DEBUG_P = params.has('p') && Number.isFinite(requestedP) ? Math.min(1, Math.max(0, requestedP)) : null;   // ?p=0.6 freezes the camera
const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
const coarse = matchMedia('(pointer: coarse)').matches || innerWidth < 760;

// An opening title, not a section: it plays on load (and on every reload), runs once, then it is over.
// Coming back to Home from another page in the same visit goes straight to the title card.
const navType = performance.getEntriesByType('navigation')[0]?.type;
let seen = false;
try { seen = sessionStorage.getItem('hc-intro') === 'seen'; } catch (e) { /* private mode */ }
const play = DEBUG_P != null || params.has('intro') || navType === 'reload' || !seen;
let done = false;
function markDone() {
  section.classList.add('is-done');
  root.classList.add('intro-complete');
  stage.style.setProperty('--p', '1');
  try { sessionStorage.setItem('hc-intro', 'seen'); } catch (e) { /* private mode: replays, harmless */ }
}
if (!play || reduced) { markDone(); return; }   // reduced motion: straight to the title card, no GL
if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
scrollTo({ top: 0, behavior: 'instant' });

// ---------------------------------------------------------------- math
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const smooth = (t) => t * t * (3 - 2 * t);
const V = {
  add: (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]],
  sub: (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]],
  mul: (a, s) => [a[0] * s, a[1] * s, a[2] * s],
  dot: (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2],
  cross: (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]],
  norm: (a) => V.mul(a, 1 / Math.hypot(...a)),
  mix: (a, b, t) => a.map((v, i) => v + (b[i] - v) * t),
};


// ---------------------------------------------------------------- the world (metres, y up)
// The face is a plane through the summit, 66° steep, facing the valley, displaced into ribs and
// ledges. The climber stands on an ice field in it; a glacier and its moraines fill the valley in front.
const NF = V.norm([0, 0.45, 1]);          // face normal
const TX = [1, 0, 0];                     // across the face
const TY = V.cross(NF, TX);               // up the face
const RAISE = 60;                         // a broad crest above the shoulder, not a lone needle
const SUMMIT = V.add([80, 1150, -320], V.mul(TY, RAISE));
const CU = -20, CV = -640 - RAISE;        // climber, in face coordinates: on an ice field in the face
const PEAKS = [
  [[-1530, 960, 520], [[-12, 37], [82, 35], [176, 38], [262, 33]]],
  [[-1810, 1010, 2190], [[8, 39], [111, 35], [184, 34], [279, 37]]],
  [[-1320, 830, 3820], [[-18, 36], [76, 32], [171, 35], [264, 33]]],
  [[1550, 1020, 150], [[171, 39], [84, 36], [7, 34], [275, 38]]],
  [[1900, 1120, 2120], [[195, 38], [105, 35], [13, 37], [289, 34]]],
  [[1470, 850, 3980], [[168, 36], [74, 34], [350, 32], [266, 35]]],
  [[-1870, 1190, -3150], [[64, 38], [151, 35], [249, 36], [343, 37]]],
  [[1950, 1240, -2850], [[108, 36], [18, 39], [207, 35], [299, 36]]],
];
// The massif's base shape, as the shader builds it (pyramids blended by smin, no warp, no rock): used to
// stand the climbers on the actual snow of their couloirs, where the blends bulge the face outward.
const smin = (a, b, k) => { const h = Math.max(k - Math.abs(a - b), 0) / k; return Math.min(a, b) - h * h * k * 0.25; };
const planes = (p, s, ns) => Math.max(...ns.map((n) => V.dot(V.sub(p, s), n)));
const PYR = [
  [SUMMIT, [NF, V.norm([-0.54, 0.70, 0.3]), V.norm([0.78, 0.52, 0.15]), V.norm([0.06, 0.56, -1.0])]],
  [[-520, 1130, -510], [V.norm([0.1, 0.58, 1.0]), V.norm([-0.48, 0.72, 0.2]), V.norm([0.7, 0.69, 0.2]), V.norm([0.0, 0.6, -1.0])]],
  [[680, 995, -820], [V.norm([-0.15, 0.68, 1.0]), V.norm([-0.7, 0.74, 0.1]), V.norm([0.82, 0.7, 0.2]), V.norm([0.0, 0.62, -1.0])]],
];
const PEAKN = PEAKS.map(([s, faces]) => [s, faces.map(([yaw, st]) => {
  const a = (yaw * Math.PI) / 180, b = (st * Math.PI) / 180;
  return [Math.sin(b) * Math.cos(a), Math.cos(b), Math.sin(b) * Math.sin(a)];
})]);
const baseShape = (p) => {
  let pk = 1e5;
  for (const [s, ns] of PEAKN) pk = smin(pk, planes(p, s, ns), 360);
  const [a, b, c] = PYR.map(([s, ns]) => planes(p, s, ns));
  return smin(smin(smin(a, b, 340), c, 390), pk, 360);
};
const LIFT = 4.5;                          // the couloirs sit level with the rock around them (its mean relief)
const onSnow = (v) => {                    // from the face plane, out along its normal to the couloir's surface
  let lo = -40, hi = 160;
  for (let i = 0; i < 40; i++) { const m = (lo + hi) / 2; if (baseShape(V.add(v, V.mul(NF, m))) > LIFT + 0.25) hi = m; else lo = m; }
  return V.add(v, V.mul(NF, (lo + hi) / 2));
};
const CLIMBER = onSnow(V.add(SUMMIT, V.add(V.mul(TX, CU), V.mul(TY, CV))));
// The valley floor is analytic so the camera can skim it (the shader uses the same functions).
const moraine = (x, z) => { const d = (z - 3470 - 60 * Math.sin(x / 260)) / 150; return 36 * Math.exp(-d * d); };   // closes the valley
const rise = (z) => { const t = clamp((2900 - z) / 2600); const s = t * t * (3 - 2 * t); return 150 * s * s; };      // the foreland climbing to the face
const DEEP = 300;                         // the valley is a gorge: its floor sits deep between the peaks
const groundAt = (x, z) => -DEEP - 0.075 * Math.max(z - 250, 0) + 2.5 * Math.sin(x / 37 + 1.3) * Math.sin(z / 53) + 1.8 * Math.sin(z / 91 + x / 140) + moraine(x, z) + rise(z);
const at = (n, x, y, up = 0) => V.add(V.add(V.add(CLIMBER, V.mul(NF, n)), V.add(V.mul(TX, x), V.mul(TY, y))), [0, up, 0]);
const LOOK = V.add(CLIMBER, [0, 1.1, 0]);
// Two rope teams of three climb snow couloirs in the face: ours (the hero leads, two seconds below on
// the rope) and a party higher up, a line of dots from the valley. 14 m of rope between climbers.
const DOWN = V.norm(V.sub([0.12, 0, 0], TY));
const LEAD2 = V.add(SUMMIT, V.add(V.mul(TX, 130), V.mul(TY, -360)));
const TEAM = [CLIMBER, LEAD2].flatMap((l) => [0, 14, 28].map((k) => onSnow(V.add(l, V.mul(DOWN, k)))));
const faceUV = (v) => { const q = V.sub(v, SUMMIT); return [V.dot(q, TX), V.dot(q, TY)]; };

// Camera keys: story time (see story()), position, target, vertical fov (deg).
// Inside the cloud at altitude; as it clears the valley opens below and the peak ahead; a level glide
// up the valley to the wall, then the climber — small, seen from beside the
// face, never closer — and into the cloud.
const KEYS = [
  [0.00, [-90, 700, 4900], [40, 860, 0], 42],
  [0.20, [-70, 670, 4350], [40, 840, 0], 42],
  [0.36, [-50, 640, 3800], [40, 820, 0], 41],
  [0.455, [-35, 620, 3400], [40, 790, 0], 40],        // out of the cloud: the valley below, the peak ahead
  [0.50, [-25, 610, 3050], [40, 760, 0], 38],
  [0.545, [-15, 600, 2700], [45, 720, 0], 37],
  [0.59, [-5, 590, 2300], [45, 660, -60], 35],
  [0.635, [0, 580, 1820], [45, 610, -60], 34],
  [0.68, at(620, -10, -120), LOOK, 30],
  [0.74, at(320, 30, -70), LOOK, 28],
  [0.80, at(150, 45, -30), at(0, 0, 2, 1.2), 26],
  [0.855, at(138, -10, -8), at(0, -8, 4, 1), 26],
  [0.905, at(132, -62, 14), at(0, -16, 12, 1), 27],
  [0.955, at(160, -100, 50), at(40, -140, 220), 31],
  [1.00, at(185, -125, 95), at(60, -170, 330), 33],
];

// Atmosphere keys: progress, fog colour (linear), fog density, cloud bank, sun colour, exposure, sun direction.
// It opens in the club's navy, before dawn. At the end a cloud bank rolls over the wall: contrast goes,
// luminance rises, and the fog itself becomes the paper of the page.
const LOOKS = [
  [0.00, [0.0035, 0.0085, 0.019], 0.00028, 0.12, [0.30, 0.34, 0.46], 1.0, [0.30, 0.12, -1.0]],
  [0.07, [0.0070, 0.0125, 0.024], 0.00050, 1.00, [0.20, 0.21, 0.24], 1.0, [0.34, 0.13, -0.95]],
  [0.13, [0.0180, 0.0250, 0.034], 0.00070, 0.80, [0.35, 0.36, 0.40], 1.0, [0.36, 0.14, -0.92]],
  [0.20, [0.0340, 0.0440, 0.052], 0.00075, 0.38, [0.70, 0.66, 0.62], 1.0, [0.40, 0.16, -0.90]],
  [0.30, [0.0600, 0.0720, 0.080], 0.00070, 0.30, [1.10, 1.00, 0.88], 1.0, [0.46, 0.18, -0.87]],
  [0.40, [0.0950, 0.1080, 0.120], 0.00045, 0.22, [1.50, 1.36, 1.18], 1.0, [0.55, 0.22, -0.80]],
  [0.43, [0.1100, 0.1250, 0.140], 0.00026, 0.16, [1.70, 1.55, 1.35], 1.0, [0.62, 0.26, -0.68]],
  [0.46, [0.0900, 0.1120, 0.140], 0.00014, 0.14, [1.90, 1.78, 1.58], 1.0, [0.68, 0.30, -0.55]],
  [0.56, [0.0800, 0.1040, 0.140], 0.00010, 0.06, [2.20, 2.08, 1.88], 1.0, [0.80, 0.40, -0.10]],
  [0.72, [0.0950, 0.1180, 0.150], 0.00010, 0.10, [2.35, 2.22, 2.00], 1.0, [0.80, 0.42, 0.05]],
  [0.87, [0.2300, 0.2450, 0.262], 0.00026, 0.55, [2.50, 2.35, 2.15], 1.0, [0.80, 0.42, 0.05]],
  [0.91, [0.4000, 0.4150, 0.430], 0.00110, 1.40, [2.60, 2.45, 2.30], 1.0, [0.80, 0.42, 0.05]],
  [0.945, [0.660, 0.668, 0.668], 0.00500, 2.40, [2.80, 2.70, 2.55], 1.04, [0.80, 0.42, 0.05]],
  [0.972, [0.960, 0.950, 0.915], 0.02500, 3.20, [3.00, 2.90, 2.75], 1.08, [0.80, 0.42, 0.05]],
  [1.00, [1.160, 1.135, 1.080], 0.09000, 3.60, [3.00, 2.90, 2.75], 1.10, [0.80, 0.42, 0.05]],
];

function sampleKeys(keys, p) {
  let i = 0;
  while (i < keys.length - 2 && p > keys[i + 1][0]) i++;
  const a = keys[i], b = keys[i + 1];
  return { i, t: clamp((p - a[0]) / (b[0] - a[0])) };
}

function catmull(p0, p1, p2, p3, t) {
  const t2 = t * t, t3 = t2 * t;
  return p1.map((_, k) => 0.5 * (2 * p1[k] + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2 + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3));
}

const DEBUG_CAM = params.get('cam')?.split(',').map(Number);   // ?cam=n,x,y,up, tn,tx,ty,tup, fov (face-relative)
// Scroll to story time (the keys above): a monotone cubic through these knots, so speed never jumps.
const WP = [0, 0.16, 0.26, 0.56, 1], WS = [0, 0.40, 0.50, 0.68, 1];   // fog, the reveal, the valley, the climber
const WD = WP.slice(1).map((x, i) => (WS[i + 1] - WS[i]) / (x - WP[i]));
const WM = WP.map((_, i) => {
  if (i === 0) return WD[0];
  if (i === WP.length - 1) return WD[i - 1];
  const h0 = WP[i] - WP[i - 1], h1 = WP[i + 1] - WP[i], d0 = WD[i - 1], d1 = WD[i];
  return 3 * (h0 + h1) / ((2 * h1 + h0) / d0 + (h1 + 2 * h0) / d1);
});
function story(p) {
  let i = 0;
  while (i < WP.length - 2 && p > WP[i + 1]) i++;
  const h = WP[i + 1] - WP[i], t = clamp((p - WP[i]) / h), t2 = t * t, t3 = t2 * t;
  return (2 * t3 - 3 * t2 + 1) * WS[i] + (t3 - 2 * t2 + t) * h * WM[i] + (-2 * t3 + 3 * t2) * WS[i + 1] + (t3 - t2) * h * WM[i + 1];
}

function camera(p, time) {
  if (DEBUG_CAM) { const c = DEBUG_CAM; return { pos: at(c[0], c[1], c[2], c[3]), tgt: at(c[4], c[5], c[6], c[7]), fov: c[8] }; }
  const { i, t } = sampleKeys(KEYS, p);
  const k = (j) => KEYS[clamp(j, 0, KEYS.length - 1)];
  const pos = catmull(k(i - 1)[1], k(i)[1], k(i + 1)[1], k(i + 2)[1], t);
  const tgt = catmull(k(i - 1)[2], k(i)[2], k(i + 1)[2], k(i + 2)[2], t);
  const fov = k(i)[3] + (k(i + 1)[3] - k(i)[3]) * smooth(t);
  const out = V.dot(V.sub(pos, CLIMBER), NF);
  if (out < 2.5 && p > 0.7) pos.splice(0, 3, ...V.add(pos, V.mul(NF, 2.5 - out)));
  if (p < 0.56) pos[1] = Math.max(pos[1], groundAt(pos[0], pos[2]) + 6.5);   // never below the ground
  // handheld drift, proportional to how far we are from the climber: steady up close
  const dist = Math.hypot(...V.sub(pos, CLIMBER));
  const a = Math.min(dist * 0.004, 6) + 0.02;
  const drift = [Math.sin(time * 0.31) + 0.5 * Math.sin(time * 0.73), Math.sin(time * 0.27 + 1) * 0.6, Math.sin(time * 0.19 + 2) * 0.4];
  return { pos: V.add(pos, V.mul(drift, a)), tgt, fov };
}

function look(p) {
  const { i, t } = sampleKeys(LOOKS, p);
  const a = LOOKS[i], b = LOOKS[i + 1], s = smooth(t);
  // density interpolates in log space: it spans two orders of magnitude
  return {
    fog: V.mix(a[1], b[1], s), den: Math.exp(Math.log(a[2]) + (Math.log(b[2]) - Math.log(a[2])) * s),
    cloud: a[3] + (b[3] - a[3]) * s, sun: V.mix(a[4], b[4], s), exposure: a[5] + (b[5] - a[5]) * s,
    sunDir: V.norm(V.mix(V.norm(a[6]), V.norm(b[6]), s)),
  };
}

// ---------------------------------------------------------------- shaders
const FULLSCREEN_VS = `#version 300 es
void main(){ vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2); gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0); }`;

// Tileable gradient noise baked into a 128³ texture: 16 lattice cells, 8 texels per cell.
const NOISE_FS = `#version 300 es
precision highp float; precision highp int;
uniform float uZ; out vec4 o;
uvec3 pcg3d(uvec3 v){ v = v * 1664525u + 1013904223u; v.x += v.y*v.z; v.y += v.z*v.x; v.z += v.x*v.y;
  v ^= v >> 16u; v.x += v.y*v.z; v.y += v.z*v.x; v.z += v.x*v.y; return v; }
vec3 g(ivec3 c){ uvec3 h = pcg3d(uvec3((c % 16 + 16) % 16)); return normalize(vec3(h & 0xffffu) / 32767.5 - 1.0 + 1e-4); }
void main(){
  vec3 p = vec3(gl_FragCoord.xy, uZ + 0.5) / 8.0;
  ivec3 i = ivec3(floor(p)); vec3 f = fract(p); vec3 u = f*f*f*(f*(f*6.0-15.0)+10.0);
  float n = mix(mix(mix(dot(g(i), f), dot(g(i+ivec3(1,0,0)), f-vec3(1,0,0)), u.x),
                    mix(dot(g(i+ivec3(0,1,0)), f-vec3(0,1,0)), dot(g(i+ivec3(1,1,0)), f-vec3(1,1,0)), u.x), u.y),
                mix(mix(dot(g(i+ivec3(0,0,1)), f-vec3(0,0,1)), dot(g(i+ivec3(1,0,1)), f-vec3(1,0,1)), u.x),
                    mix(dot(g(i+ivec3(0,1,1)), f-vec3(0,1,1)), dot(g(i+ivec3(1,1,1)), f-vec3(1,1,1)), u.x), u.y), u.z);
  o = vec4(clamp(0.5 + 0.8 * n, 0.0, 1.0));
}`;

const f3 = (v) => `vec3(${v.map((x) => x.toFixed(5)).join(',')})`;
// Kebnekaise-inspired ridge groups: unequal shoulders and saddles, not an avenue of identical horns.
// Each mass uses four broad faces; their overlapping crests read as one eroded range.
const peakGLSL = PEAKN.map(([s, ns]) => {
  const q = `(p - ${f3(s)})`, n = ns.map(f3);
  return `  d = smin(d, max(max(dot(${q}, ${n[0]}), dot(${q}, ${n[1]})), max(dot(${q}, ${n[2]}), dot(${q}, ${n[3]}))), 360.0);`;
}).join('\n');

const SCENE_FS = `#version 300 es
precision highp float; precision highp sampler3D;
uniform sampler3D uNoise;
uniform sampler2D uRock;
uniform vec2 uRes; uniform float uTime, uFocal, uPix;
uniform vec3 uCam, uCamR, uCamU, uCamF;
uniform vec3 uSunDir, uSunCol, uFogCol;
uniform float uFogDen, uCloud, uWhite, uTMax, uExposure, uVig, uLayer;
uniform vec3 uPaper;
uniform int uSteps, uCloudSteps, uQuality;
out vec4 outColor;

const vec3 S1 = ${f3(SUMMIT)};
const vec3 NF = ${f3(NF)};
const vec3 TY = ${f3(TY)};
const vec3 CLIMB = ${f3(CLIMBER)};
const vec2 CUV = vec2(${CU.toFixed(1)}, ${CV.toFixed(1)});
const vec3 DOWN = ${f3(DOWN)};
const vec3 CLS[6] = vec3[6](${TEAM.map(f3).join(', ')});
const vec2 CLF[6] = vec2[6](${TEAM.map((v) => `vec2(${faceUV(v).map((x) => x.toFixed(2)).join(',')})`).join(', ')});
const vec2 TSEG = vec2(${faceUV(V.add(SUMMIT, V.mul(DOWN, 30))).map((x) => x.toFixed(2)).join(',')});
const mat3 ROT = mat3(0.00, 0.80, 0.60, -0.80, 0.36, -0.48, -0.60, -0.48, 0.64);

float n3(vec3 p){ return textureLod(uNoise, p * 0.0625, 0.0).r; }
// analytic value noise, quintic: C2 everywhere, so large rock octaves shade without texel facets
float hash13(vec3 p){ p = fract(p * 0.1031); p += dot(p, p.zyx + 31.32); return fract((p.x + p.y) * p.z); }
float vn3(vec3 x){
  vec3 i = floor(x), f = fract(x), u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);
  return mix(mix(mix(hash13(i), hash13(i + vec3(1, 0, 0)), u.x), mix(hash13(i + vec3(0, 1, 0)), hash13(i + vec3(1, 1, 0)), u.x), u.y),
             mix(mix(hash13(i + vec3(0, 0, 1)), hash13(i + vec3(1, 0, 1)), u.x), mix(hash13(i + vec3(0, 1, 1)), hash13(i + vec3(1, 1, 1)), u.x), u.y), u.z);
}
float hash12(vec2 p){ vec3 p3 = fract(vec3(p.xyx) * 0.1031); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.x + p3.y) * p3.z); }
float smin(float a, float b, float k){ float h = max(k - abs(a - b), 0.0) / k; return min(a, b) - h*h*k*0.25; }

// ---- the face, in its own coordinates: u across, v up the face, w out of it (metres)
vec3 faceUVW(vec3 p){ vec3 q = p - S1; return vec3(q.x, dot(q, TY), dot(q, NF)); }
float segDist(vec2 u, vec2 a, vec2 d){ return length(u - a - d * clamp(dot(u - a, d) / dot(d, d), 0.0, 1.0)); }
// how far from the two rope teams' couloirs (face coordinates, metres)
float teamLane(vec2 u){ return min(segDist(u, CLF[0], TSEG), segDist(u, CLF[3], TSEG)); }

// ---- rock: restrained relief stretched along the natural fall line.
float rock(vec3 p, float lod, float nearGully){
  vec3 q = p + (vec3(n3(p / 330.0), n3(p / 330.0 + 5.2), n3(p / 330.0 + 9.1)) - 0.5) * 60.0;
  float h = 0.0;
  float oct = clamp(log2(130.0 / (4.0 * max(lod, 1.0) * uPix)), 1.0, 9.0);
  vec3 r = vec3(q.x, q.y * 0.45, q.z) / 175.0;
  float amp = 7.5, wgt = 1.0, sum = 0.0;
  for (int i = 0; i < 9; i++){
    float fw = clamp(oct - float(i), 0.0, 1.0);
    if (fw <= 0.0) break;
    float n = 1.0 - abs(2.0 * (i < 3 ? vn3(r * 1.7) : n3(r)) - 1.0);
    n = n * n * wgt;
    wgt = clamp(n * 1.6, 0.0, 1.0);
    sum += amp * n * fw;
    amp *= 0.5;
    r = vec3(r.x * 0.8 - r.z * 0.6, r.y, r.x * 0.6 + r.z * 0.8) * 2.03 + vec3(1.7, 3.1, 0.4);
  }
  h += sum;
  return h * nearGully;
}

float pyramid(vec3 p, vec3 s, vec3 nf, vec3 nl, vec3 nr, vec3 nb){
  vec3 q = p - s; return max(max(dot(q, nf), dot(q, nl)), max(dot(q, nr), dot(q, nb)));
}

float peaks(vec3 p){
  float d = 1e5;
${peakGLSL}
  return d;
}

bool gAO = false;        // ambient occlusion wants true distances, not the march's safe bounds
float massif(vec3 p, float lod){
  // The main summit is a long asymmetric ridge with lower connected shoulders.
  float d0 = smin(smin(pyramid(p, S1, NF, normalize(vec3(-0.54, 0.70, 0.3)), normalize(vec3(0.78, 0.52, 0.15)), normalize(vec3(0.06, 0.56, -1.0))),
                       pyramid(p, vec3(-520.0, 1130.0, -510.0), normalize(vec3(0.1, 0.58, 1.0)), normalize(vec3(-0.48, 0.72, 0.2)), normalize(vec3(0.7, 0.69, 0.2)), normalize(vec3(0.0, 0.6, -1.0))), 340.0),
                  pyramid(p, vec3(680.0, 995.0, -820.0), normalize(vec3(-0.15, 0.68, 1.0)), normalize(vec3(-0.7, 0.74, 0.1)), normalize(vec3(0.82, 0.7, 0.2)), normalize(vec3(0.0, 0.62, -1.0))), 390.0);
  float pk = peaks(p);                                   // the valley's peaks take no warp: their rock does the work
  d0 = min(d0, pk);
  if (d0 > 260.0) return (d0 - 190.0) * 0.8;
  vec3 f = faceUVW(p);
  // the teams' couloirs are smooth snow (the warp and the rock fade out over 45 m), levelled under each climber
  float calm = smoothstep(10.0, 110.0, teamLane(f.xy) + 35.0 * (n3(p / 90.0) - 0.5));   // a ragged edge, no oval
  float core = 1.0 - calm, feet = 1.0;
  if (core > 0.0) for (int k = 0; k < 6; k++) feet = min(feet, smoothstep(1.5, 5.0, length(f.xy - CLF[k])));
  float runnel = core * (1.0 - smoothstep(180.0, 450.0, lod))
               * feet * 0.7 * (2.0 * pow(1.0 - abs(2.0 * n3(vec3(f.x / 7.0, f.y / 60.0, 3.3)) - 1.0), 2.0) + 0.45 * n3(p / 3.0) - 0.95);   // zero-mean, so no pit   // flutes along the face's own fall line
  // Broad west shoulder and lower east ridge remain connected to the climber's face.
  vec3 w1 = (vec3(n3(p / 900.0 + 2.0), 0.0, n3(p / 900.0 + 6.0)) - 0.5) * 88.0;
  vec3 w2 = (vec3(n3(p / 420.0 + 4.0), 0.0, n3(p / 420.0 + 8.0)) - 0.5) * 13.0;
  vec3 w = w1 + w2;
  vec3 wp = p + (w - NF * dot(w, NF)) * calm;            // slides along the face (never moves its plane), and fades at the teams: the JS stands them on this shape
  float a = pyramid(wp, S1, NF, normalize(vec3(-0.54, 0.70, 0.3)), normalize(vec3(0.78, 0.52, 0.15)), normalize(vec3(0.06, 0.56, -1.0)));
  float b = pyramid(wp, vec3(-520.0, 1130.0, -510.0), normalize(vec3(0.1, 0.58, 1.0)), normalize(vec3(-0.48, 0.72, 0.2)), normalize(vec3(0.7, 0.69, 0.2)), normalize(vec3(0.0, 0.6, -1.0)));
  float c = pyramid(wp, vec3(680.0, 995.0, -820.0), normalize(vec3(-0.15, 0.68, 1.0)), normalize(vec3(-0.7, 0.74, 0.1)), normalize(vec3(0.82, 0.7, 0.2)), normalize(vec3(0.0, 0.62, -1.0)));
  float d = smin(smin(smin(a, b, 340.0), c, 390.0), pk, 360.0);
  if (d > 100.0 && !gAO) return (d - 85.0) * 0.8;                                // near rock but not at it: cheap bound (too pessimistic for AO)
  float fine = 1.0 - smoothstep(60.0, 260.0, lod);
  float snow = (1.0 - calm) * (0.18 * n3(p / 4.0) + 0.3 * n3(p / 23.0) + fine * 0.06 * n3(p / 0.5));
  return (d - rock(p, lod, calm) - snow - runnel - ${LIFT.toFixed(1)} * core) * 0.8;   // the couloir's 100 m transition is gentle: no step correction (it read as occlusion)
}

float moraine(vec2 xz){ float d = (xz.y - 3470.0 - 60.0 * sin(xz.x / 260.0)) / 150.0; return 36.0 * exp(-d * d); }
float rise(float z){ float s = smoothstep(2900.0, 300.0, z); return 150.0 * s * s; }
float groundA(vec2 xz){ return -${DEEP.toFixed(1)} - 0.075 * max(xz.y - 250.0, 0.0) + 2.5 * sin(xz.x / 37.0 + 1.3) * sin(xz.y / 53.0) + 1.8 * sin(xz.y / 91.0 + xz.x / 140.0) + moraine(xz) + rise(xz.y); }
// the glacier: a tongue from the foot of the face, widening into its basin, snout above the moraine
float glacier(vec2 xz){
  float u = (xz.x - 40.0 - 90.0 * sin(xz.y / 700.0)) / mix(520.0, 260.0, smoothstep(400.0, 2200.0, xz.y));
  return smoothstep(0.0, 0.5, 1.0 - u * u) * smoothstep(2350.0, 2050.0, xz.y);
}
float glacierU(vec2 xz){ return (xz.x - 40.0 - 90.0 * sin(xz.y / 700.0)) / mix(520.0, 260.0, smoothstep(400.0, 2200.0, xz.y)); }
// hummocks; where the camera skims the valley floor they are measured from its line (x = 0), so the
// camera never flies into one
float lumps(vec2 xz, float lod){ return 24.0 * vn3(vec3(xz.x, 3.0, xz.y) / 230.0) + (lod < 1200.0 ? 6.0 * vn3(vec3(xz.x, 5.0, xz.y) / 41.0) * (1.0 - smoothstep(600.0, 1200.0, lod)) : 0.0); }   // analytic: 8-bit texels terrace at this height
// talus and avalanche cones fanning out from the foot of the face, clear of the climber's fall line
float cone(vec2 xz, vec2 c, float h, float r){ float d = length((xz - c) / vec2(1.0, 1.3)) / r; float s = smoothstep(1.0, 0.0, d); return h * s * s; }   // rounded top, soft toe
float cones(vec2 xz){
  if (xz.y > 780.0) return 0.0;
  return cone(xz, vec2(-330.0, 40.0), 190.0, 460.0) + cone(xz, vec2(-140.0, 60.0), 120.0, 340.0)
       + cone(xz, vec2(250.0, 50.0), 160.0, 400.0) + cone(xz, vec2(440.0, 20.0), 200.0, 480.0);
}
float relief(vec2 xz, float lod){
  float w = smoothstep(3300.0, 3650.0, xz.y);
  float l = lumps(xz, lod) - (w > 0.0 ? w * lumps(vec2(0.0, xz.y), lod) : 0.0);
  return l * (1.0 + 0.9 * smoothstep(3300.0, 900.0, xz.y));
}

float ground(vec2 xz, float lod){
  float h = groundA(xz);
  // a valley between mountains: its walls close in toward the face, and the face has a foot, buttresses
  // and spurs climbing to it on either side of the glacier, so the wall never stands on a plain
  float side = max(abs(xz.x - 60.0) - mix(380.0, 750.0, smoothstep(600.0, 4500.0, xz.y)), 0.0);
  float far = 1.0 - smoothstep(-2000.0, -600.0, xz.y);
  vec3 q = vec3(xz.x, 11.0, xz.y) / 1700.0; q += (vec3(n3(q * 0.7), 0.0, n3(q * 0.7 + 4.0)) - 0.5) * 0.8;
  if (side > 0.0 || far > 0.0){
    float rg = 0.0, a = 1.0;
    for (int i = 0; i < 5; i++){ float n = 1.0 - abs(2.0 * n3(q) - 1.0); rg += a * n; a *= 0.48; q = ROT * q * 2.03; }
    rg /= 1.9;
    h += smoothstep(0.0, 1200.0, side) * (60.0 + 200.0 * rg * rg) + far * (300.0 + ${DEEP.toFixed(1)} + 900.0 * rg * rg) ;
  }
  if (xz.y < 3300.0){
    // above the moraine: the glacier and its lateral moraines, hills rising to the valley walls, an apron at the face
    float g = glacier(xz), u = abs(glacierU(xz)), along = smoothstep(2450.0, 2150.0, xz.y) * smoothstep(250.0, 900.0, xz.y);
    float hills = 80.0 * vn3(vec3(xz.x, 1.0, xz.y) / 650.0) * smoothstep(3300.0, 2900.0, xz.y) * (0.7 + 0.3 * smoothstep(150.0, 600.0, abs(xz.x - 60.0)));
    float lat = (u - 1.15) / 0.22;
    float apron = smoothstep(800.0, 100.0, xz.y);
    float med = 1.0 - abs(2.0 * fract((xz.x - 90.0 * sin(xz.y / 700.0)) / 160.0 + 0.3 * vn3(vec3(xz.x, 2.0, xz.y) / 400.0)) - 1.0);
    h += 50.0 * g + 42.0 * exp(-lat * lat) * along + hills * (1.0 - g) + 60.0 * apron * apron
       + g * (14.0 * med * med + 9.0 * vn3(vec3(xz.x, 4.0, xz.y) / 60.0));   // medial moraines and debris hummocks
    h += relief(xz, lod) * (1.0 - 0.9 * g);
  } else h += relief(xz, lod);
  return h;
}

// ---- the climber, in local coordinates: x across, y up, z into the wall. Metres.
float sdCap(vec3 p, vec3 a, vec3 b, float r){ vec3 pa = p - a, ba = b - a; float h = clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0); return length(pa - ba*h) - r; }
float sdBox(vec3 p, vec3 b, float r){ vec3 q = abs(p) - b; return length(max(q, 0.0)) + min(max(q.x, max(q.y, q.z)), 0.0) - r; }

vec2 climber(vec3 q, float t){
  vec3 b = vec3(q.x, q.y, -q.z);
  float swing = fract(t / 7.0); swing = swing > 0.78 ? sin(3.14159 * (swing - 0.78) / 0.22) : 0.0;
  float kick = fract(t / 7.0 + 0.45); kick = kick > 0.8 ? sin(3.14159 * (kick - 0.8) / 0.2) : 0.0;
  float breath = 0.006 * sin(t * 1.4);
  vec3 eR = vec3(0.31, 1.62, 0.25) + vec3(0.0, 0.05, -0.1) * swing;
  vec3 hR = vec3(0.24, 1.92, 0.55) + vec3(0.0, 0.10, -0.24) * swing;
  vec3 tR = hR + mix(vec3(0.0, 0.42, 0.26), vec3(0.0, 0.32, -0.06), swing);
  vec3 hL = vec3(-0.27, 1.60, 0.47), tL = hL + vec3(0.0, 0.40, 0.25);
  vec3 sR = vec3(0.18, 1.44 + breath, 0.06), sL = vec3(-0.18, 1.44 + breath, 0.06);
  vec3 kL = vec3(-0.16, 0.72, -0.03) + vec3(0.0, 0.04, -0.08) * kick, fL = vec3(-0.14, 0.40, 0.12) + vec3(0.0, 0.05, -0.12) * kick;
  // jacket: torso, hood, arms; a few millimetres of flutter
  float flutter = 0.005 * sin(38.0 * b.y + 9.0 * t) * sin(27.0 * b.x + 7.0 * t);
  float jk = sdCap(b, vec3(0.0, 1.0, -0.03), vec3(0.0, 1.37 + breath, 0.05), 0.16) + flutter;
  jk = smin(jk, sdCap(b, sR, eR, 0.058), 0.04);
  jk = min(jk, sdCap(b, eR, hR, 0.05));
  jk = smin(jk, sdCap(b, sL, vec3(-0.33, 1.35, 0.23), 0.058), 0.04);
  jk = min(jk, sdCap(b, vec3(-0.33, 1.35, 0.23), hL, 0.05));
  jk = smin(jk, sdCap(b, vec3(0.0, 1.48, 0.05), vec3(0.0, 1.56, 0.09), 0.085), 0.05);
  // dark: trousers, boots, a slim pack, harness, gloves
  float dk = sdBox(b - vec3(0.0, 1.25, -0.18), vec3(0.085, 0.14, 0.035), 0.05);
  dk = min(dk, sdCap(b, vec3(0.09, 0.96, -0.07), vec3(0.14, 0.52, -0.07), 0.075));
  dk = min(dk, sdCap(b, vec3(0.14, 0.52, -0.07), vec3(0.13, 0.13, -0.01), 0.062));
  dk = min(dk, sdCap(b, vec3(-0.09, 0.96, -0.07), kL, 0.075));
  dk = min(dk, sdCap(b, kL, fL, 0.062));
  dk = min(dk, sdBox(b - vec3(0.13, 0.07, 0.03), vec3(0.042, 0.045, 0.1), 0.02));
  dk = min(dk, sdBox(b - fL - vec3(0.0, -0.05, 0.05), vec3(0.042, 0.045, 0.1), 0.02));
  dk = min(dk, sdCap(b, vec3(-0.15, 0.93, -0.02), vec3(0.15, 0.93, -0.02), 0.035));
  dk = min(dk, length(b - hR) - 0.048); dk = min(dk, length(b - hL) - 0.048);
  float hd = length(b - vec3(0.0, 1.66 + breath, 0.11)) - 0.112;             // helmet
  float tl = min(sdCap(b, hR, tR, 0.013), sdCap(b, tR, tR + vec3(0.0, -0.05, 0.25), 0.009));
  tl = min(tl, min(sdCap(b, hL, tL, 0.013), sdCap(b, tL, tL + vec3(0.0, -0.05, 0.25), 0.009)));
  vec2 r = vec2(jk, 1.0);
  if (dk < r.x) r = vec2(dk, 2.0);
  if (hd < r.x) r = vec2(hd, 3.0);
  if (tl < r.x) r = vec2(tl, 5.0);
  return r;
}

// a team's rope: leader's harness, slack lying on the snow, each second's harness, a tail to the anchor
float rope(vec3 p, float lod, vec3 L){
  vec3 hk = vec3(0.0, 0.95, 0.16);
  vec3 h0 = L + hk, a = L + DOWN * 1.1 + NF * 0.42, m1 = L + DOWN * 7.0 + NF * 0.08, h1 = L + DOWN * 14.0 + hk;
  vec3 m2 = L + DOWN * 21.0 + NF * 0.08, h2 = L + DOWN * 28.0 + hk, e = L + DOWN * 40.0 + NF * 0.07;
  float r = max(0.011, 0.6 * uPix * lod);
  float d = min(min(sdCap(p, h0, a, r), sdCap(p, a, m1, r)), sdCap(p, m1, h1, r));
  return min(min(d, sdCap(p, h1, m2, r)), min(sdCap(p, m2, h2, r), sdCap(p, h2, e, r)));
}

vec2 map(vec3 p, float lod){
  vec2 r = vec2(min(massif(p, lod), (p.y - ground(p.xz, lod)) * 0.55), 0.0);   // no smin: the massif's distance is a scaled bound, a blend with it floats off the snow
  float inflate = 0.75 * uPix * lod;                    // never thinner than a pixel: from the valley, a line of dots
  for (int j = 0; j < 2; j++){
    vec3 L = CLS[j * 3];
    if (length(p - (L + DOWN * 14.0)) - 22.0 > r.x + inflate) continue;   // the whole team is far
    for (int k = 0; k < 3; k++){
      vec3 q = p - CLS[j * 3 + k];
      if (length(q - vec3(0.0, 1.0, 0.0)) - 1.6 < r.x + inflate){
        vec2 c = climber(q, uTime + float(j * 3 + k) * 2.37); c.x -= inflate; if (c.x < r.x) r = c;
      }
    }
    float rp = rope(p, lod, L); if (rp < r.x) r = vec2(rp, 4.0);
  }
  return r;
}

vec3 normal(vec3 p, float t){
  float e = max(0.0012 * t, 0.004); const vec2 k = vec2(1.0, -1.0);
  return normalize(k.xyy * map(p + k.xyy*e, t).x + k.yyx * map(p + k.yyx*e, t).x + k.yxy * map(p + k.yxy*e, t).x + k.xxx * map(p + k.xxx*e, t).x);
}

float shadow(vec3 ro, vec3 rd, float lod){
  float res = 1.0, t = (0.05 + lod * 0.002) * (1.0 + fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715)))));   // jittered start: grain, not bands
  for (int i = 0; i < 22; i++){
    float h = map(ro + rd*t, lod * 4.0 + t * 3.0).x;
    res = min(res, 8.0 * h / t);
    t += clamp(h, 0.03 + t * 0.03, 120.0);
    if (res < 0.01 || t > 500.0) break;
  }
  return clamp(res, 0.0, 1.0);
}

float ao(vec3 p, vec3 n, float t){
  float s = clamp(t * 0.012, 0.08, 14.0), o = 0.0, w = 1.0;
  int cnt = uQuality > 0 ? 4 : 2;
  gAO = true;
  for (int i = 1; i <= 4; i++){ if (i > cnt) break; float h = s * float(i); o += w * (h - map(p + n*h, t).x); w *= 0.62; }
  gAO = false;
  return clamp(1.0 - o / (s * 2.2), 0.0, 1.0);
}

vec3 fogColor(vec3 rd){
  float s = max(dot(rd, uSunDir), 0.0);
  return uFogCol * (1.0 + 0.25 * rd.y) + uSunCol * (0.05 * pow(s, 5.0) + 0.06 * pow(s, 40.0));
}

// fog: uniform haze + an exponential layer that thins with altitude
float fogAmount(vec3 ro, vec3 rd, float t){
  float b = 1.0 / 420.0, base = 380.0;
  float k = abs(rd.y) < 1e-4 ? t : (1.0 - exp(-t * rd.y * b)) / (rd.y * b);
  return 1.0 - exp(-uFogDen * (0.55 * t + uLayer * exp(-(ro.y - base) * b) * k));
}

// Close rock comes from a photographed Nordic gneiss surface. Mirrored tiling and
// triplanar projection hide the source edges; beyond the wall, geology reads at landform scale.
vec3 rockTri(vec3 p, vec3 w, float tile){
  return texture(uRock, p.yz / tile).rgb * w.x
       + texture(uRock, p.xz / tile).rgb * w.y
       + texture(uRock, p.xy / tile).rgb * w.z;
}
vec3 rockAlbedo(vec3 p, vec3 n, float t){
  float weather = vn3(p / 240.0);
  float grain = vn3(vec3(p.x / 33.0, p.y / 18.0, p.z / 35.0));
  vec3 stone = mix(vec3(0.092, 0.089, 0.083), vec3(0.205, 0.186, 0.162), weather);
  stone *= 0.86 + 0.25 * grain;
  if (t < 1400.0){
    vec3 w = pow(abs(n), vec3(4.0)); w /= max(w.x + w.y + w.z, 0.001);
    vec3 tex = t < 180.0 ? rockTri(p, w, 28.0) : rockTri(p, w, 118.0);
    if (t >= 180.0 && t < 420.0)
      tex = mix(rockTri(p, w, 28.0), tex, smoothstep(180.0, 420.0, t));
    tex = pow(tex, vec3(2.2));
    stone = mix(stone, tex * (0.75 + 0.35 * weather), 0.62 * (1.0 - smoothstep(1000.0, 1400.0, t)));
  }
  return stone;
}

vec3 shade(vec3 p, vec3 rd, float t, float mat){
  vec3 n = normal(p, t);
  vec3 alb; float spec = 0.0, snowAmt = 0.0;
  if (mat < 0.5){
    vec3 stone = rockAlbedo(p, n, t);
    float gy = p.y - ground(p.xz, t);
    float basin = vn3(vec3(p.x / 150.0, 2.2, p.z / 150.0)) * 0.65
                + vn3(vec3(p.x / 42.0, 5.3, p.z / 42.0)) * 0.35;
    // Snow as on Ama Dablam: plastered above a ragged snowline (faces hold it to ~60 degrees, fluted by
    // spindrift), on ledges and in couloirs below; rock shows on the steepest steps. It is judged on a
    // blurred normal, so it settles on the form rather than on every facet.
    vec3 nb = t < 3000.0 ? normal(p, t * 5.0) : n;
    float sl = smoothstep(220.0, 650.0, p.y + 160.0 * (basin - 0.5));
    float hold = mix(0.8, 0.30, sl);
    float snow = smoothstep(hold, hold + 0.16, nb.y + 0.16 * (basin - 0.5));
    float flute = n3(vec3(p.x / 6.0, p.y / 80.0, p.z / 6.0)) * 0.6 + n3(vec3(p.x / 19.0, p.y / 260.0, p.z / 19.0)) * 0.4;
    float steep = 1.0 - smoothstep(0.42, 0.72, nb.y);
    snow *= 1.0 - 0.5 * steep * smoothstep(0.56, 0.3, flute);
    snow = max(snow, 1.0 - smoothstep(20.0, 90.0, teamLane(faceUVW(p).xy) + 35.0 * (n3(p / 90.0) - 0.5)));   // the teams' couloirs
    float onGround = 1.0 - smoothstep(0.0, 4.0, gy);
    if (onGround > 0.0){
      float g = glacier(p.xz);
      vec3 scree = mix(vec3(0.16, 0.145, 0.126), vec3(0.225, 0.207, 0.178), basin);
      stone = mix(stone, scree, onGround * (0.25 + 0.50 * (1.0 - g)));
      snow = max(snow, onGround * g * 0.30 * (0.7 + 0.3 * basin));
    }
    vec3 snowCol = mix(vec3(0.86, 0.88, 0.92), vec3(0.64, 0.72, 0.83), steep * 0.55) * (0.94 + 0.08 * basin);   // steep snow is ice, bluer
    alb = mix(stone, snowCol, snow);
    spec = snow * 0.03; snowAmt = snow;
  } else if (mat < 1.5) alb = vec3(0.52, 0.2, 0.04);       // jacket, the club's rope colour
  else if (mat < 2.5) alb = vec3(0.035, 0.04, 0.05);
  else if (mat < 3.5) alb = vec3(0.62, 0.62, 0.60);
  else if (mat < 4.5){                                    // rope: fade to snow when sub-pixel
    float cover = 0.011 / max(0.011, 0.6 * uPix * t);
    alb = mix(vec3(0.8, 0.84, 0.9), vec3(0.60, 0.28, 0.06), cover);
  } else { alb = vec3(0.3, 0.31, 0.33); spec = 0.5; }
  if (snowAmt > 0.05 && t < 160.0){                      // crust and spindrift, below the SDF's resolution
    vec3 q = p * vec3(1.0 / 0.3, 1.0 / 1.4, 1.0 / 0.3); const vec2 e = vec2(0.35, 0.0);
    vec3 g = vec3(n3(q + e.xyy) - n3(q - e.xyy), n3(q + e.yxy) - n3(q - e.yxy), n3(q + e.yyx) - n3(q - e.yyx));
    n = normalize(n + g * 0.22 * snowAmt * (1.0 - t / 160.0));
  }
  float dif = max(dot(n, uSunDir), 0.0);
  float occ = t < 3500.0 ? ao(p, n, t) : 1.0;
  float sh = dif > 0.001 ? (uQuality > 1 && t < 1800.0 ? shadow(p + n * max(0.02, t * 0.002), uSunDir, t) : occ) : 0.0;
  vec3 sky = uFogCol * 2.2 + vec3(0.02, 0.03, 0.05);
  vec3 lin = uSunCol * dif * sh
           + sky * (0.55 + 0.45 * n.y) * occ
           + uFogCol * 1.4 * (0.5 - 0.5 * n.y) * occ;           // bounce from the snow below
  vec3 col = alb * lin;
  col += spec * uSunCol * pow(max(dot(reflect(rd, n), uSunDir), 0.0), 8.0) * sh;
  if (mat > 0.5) col += alb * uSunCol * 0.35 * pow(clamp(1.0 + dot(rd, n), 0.0, 1.0), 3.0) * max(dot(rd, uSunDir) * 0.5 + 0.5, 0.0);  // rim
  return col;
}

// drifting cloud, sampled across the first few hundred metres in front of the camera
vec4 clouds(vec3 ro, vec3 rd, float tHit, vec2 fc){
  if (uCloud < 0.01) return vec4(0.0, 0.0, 0.0, 1.0);
  float range = min(tHit, 420.0), dt = range / float(uCloudSteps);
  float t = dt * hash12(fc + fract(uTime * 7.31) * 97.0), T = 1.0; vec3 L = vec3(0.0);   // white noise: reads as grain, never as a pattern
  vec3 wind = vec3(uTime * 3.0, 0.0, uTime * 1.2);
  vec3 lit = fogColor(rd) * 1.25 + uSunCol * 0.05;
  for (int i = 0; i < 16; i++){
    if (i >= uCloudSteps) break;
    vec3 p = ro + rd * t - wind;
    float d = n3(p / 110.0) * 0.55 + n3(p / 36.0) * 0.3 + n3(p / 11.0) * 0.15;
    d = (smoothstep(0.46, 0.72, d) + 0.16 * max(uCloud - 1.0, 0.0)) * uCloud;   // thickens, keeps its wisps
    float a = 1.0 - exp(-d * dt * 0.035);
    L += T * a * lit; T *= 1.0 - a;
    t += dt;
  }
  return vec4(L, T);
}

// how clear the air is: the sky, the cumulus and the cloud sea only exist between the fogs
float clearAir(){ return (1.0 - smoothstep(0.00018, 0.0005, uFogDen)) * (1.0 - smoothstep(0.3, 1.0, uCloud)); }

// a blue sky, and a field of cumulus above the summits (sunlit tops, grey bellies)
vec3 sky(vec3 ro, vec3 rd){
  vec3 c = fogColor(rd);
  float clear = clearAir();
  if (clear < 0.01) return c;
  c = mix(c, vec3(0.028, 0.07, 0.19) * uSunCol.g * 0.9, clear * smoothstep(0.0, 0.45, rd.y));
  if (rd.y > 0.004){
    float tc = (2600.0 - ro.y) / rd.y;
    vec2 q = (ro.xz + rd.xz * tc) / 1300.0 + vec2(uTime * 0.003, uTime * 0.001);
    float d = vn3(vec3(q, 1.0)) * 0.55 + n3(vec3(q * 2.7, 2.0)) * 0.3 + n3(vec3(q * 7.3, 3.0)) * 0.15;
    float ds = vn3(vec3(q + uSunDir.xz * 0.05, 1.0)) * 0.55 + n3(vec3((q + uSunDir.xz * 0.05) * 2.7, 2.0)) * 0.3 + n3(vec3(q * 7.3, 3.0)) * 0.15;
    float a = smoothstep(0.48, 0.7, d) * clear * smoothstep(0.004, 0.06, rd.y) * (1.0 - smoothstep(12000.0, 40000.0, tc));
    float lit = 0.55 + 0.45 * smoothstep(-0.08, 0.12, d - ds);
    c = mix(c, mix(uFogCol * 2.6 + vec3(0.03, 0.04, 0.06), uSunCol * 0.62, lit), a);
  }
  return c;
}

// the cloud sea: a layer lying in the valleys below the camera, wrapping the feet of the peaks
vec4 cloudSea(vec3 ro, vec3 rd, float tHit, vec2 fc){
  float clear = clearAir();
  if (clear < 0.01 || abs(rd.y) < 1e-4) return vec4(0.0, 0.0, 0.0, 1.0);
  const float Y0 = 170.0, Y1 = 520.0;
  float ta = (Y0 - ro.y) / rd.y, tb = (Y1 - ro.y) / rd.y;
  if (ta > tb){ float s = ta; ta = tb; tb = s; }
  ta = max(ta, 0.0); tb = min(tb, min(tHit, 4500.0));
  if (tb <= ta) return vec4(0.0, 0.0, 0.0, 1.0);
  float dt = (tb - ta) / 14.0, t = ta + dt * hash12(fc + fract(uTime * 3.7) * 61.0), T = 1.0;
  vec3 L = vec3(0.0), wind = vec3(uTime * 2.2, 0.0, uTime * 0.8);
  for (int i = 0; i < 14; i++){
    vec3 p = ro + rd * t;
    float pr = smoothstep(Y0, Y0 + 90.0, p.y) * (1.0 - smoothstep(Y1 - 150.0, Y1, p.y));
    vec3 w = (p - wind) / 330.0;
    float d = n3(w) * 0.6 + n3(w * 3.1) * 0.28 + n3(w * 9.3) * 0.12;
    float dens = smoothstep(0.46, 0.8, d) * pr * clear;
    if (dens > 0.001){
      vec3 ws = w + uSunDir * 0.22;
      float light = exp(-2.4 * smoothstep(0.5, 0.74, n3(ws) * 0.6 + n3(ws * 3.1) * 0.28 + 0.06));
      vec3 cc = mix(uFogCol * 2.4 + vec3(0.02, 0.03, 0.05), uSunCol * 0.6, light);
      cc = mix(cc, fogColor(rd), fogAmount(ro, rd, t));
      float a = 1.0 - exp(-dens * dt * 0.012);
      L += T * a * cc; T *= 1.0 - a;
    }
    t += dt;
  }
  return vec4(L, T);
}

vec3 aces(vec3 x){ return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0); }

void main(){
  vec2 fc = gl_FragCoord.xy;
  vec2 uv = (2.0 * fc - uRes) / uRes.y;
  vec3 rd = normalize(uCamF * uFocal + uCamR * uv.x + uCamU * uv.y);
  vec3 ro = uCam;
  float t = 1.0, tPrev = 1.0, mat = -1.0;
  vec2 h;
  float bestR = 1e9, bestT = 1.0, bestM = 0.0;             // the ray's closest pass to a surface
  for (int i = 0; i < 220; i++){
    if (i >= uSteps) break;
    vec3 p = ro + rd * t;
    if (p.y > 2300.0 && rd.y > 0.0) { t = uTMax + 1.0; break; }
    h = map(p, t);
    if (h.x < bestR * t){ bestR = h.x / t; bestT = t; bestM = h.y; }
    if (h.x < 0.0006 * t){
      mat = h.y;
      if (h.x < 0.0){                                     // overshot a thin crest: bisect back to it
        float a = tPrev, b = t;
        for (int k = 0; k < 5; k++){ float m = 0.5 * (a + b); vec2 hm = map(ro + rd * m, m); if (hm.x < 0.0) { b = m; mat = hm.y; } else a = m; }
        t = b;
      }
      break;
    }
    tPrev = t;
    t += h.x * 0.72;
    if (t > uTMax) break;
  }
  if (mat < -0.5 && t < uTMax && bestR < 0.03 && bestM < 0.5){ t = bestT; mat = bestM; }   // out of steps creeping over far terrain: that terrain, not a grey hole (not the climber)
  vec3 col;
  if (t < uTMax && mat > -0.5) col = shade(ro + rd * t, rd, t, mat);
  else { t = uTMax; col = sky(ro, rd); }
  if (mat > -0.5 || t < uTMax) col = mix(col, fogColor(rd), fogAmount(ro, rd, t));
  vec4 sea = cloudSea(ro, rd, t, fc);
  col = col * sea.a + sea.rgb;
  vec4 cl = clouds(ro, rd, t, fc);
  col = col * cl.a + cl.rgb;
  col = aces(col * uExposure * 1.6);
  col = pow(col, vec3(1.0 / 2.2));
  col = mix(col, col * vec3(0.95, 0.985, 1.04), 1.0 - col.g);           // cold shadows
  vec2 q = fc / uRes - 0.5;
  col *= 1.0 - 0.32 * uVig * dot(q, q) * 1.6;
  col = mix(col, uPaper, uWhite);
  col += (hash12(fc + uTime * 13.0) - 0.5) / 255.0;                     // dither the fog gradients
  outColor = vec4(col, 1.0);
}`;

// Snow: instanced soft flakes living in a box that travels with the camera.
const SNOW_VS = `#version 300 es
layout(location=0) in vec4 aSeed;
uniform mat4 uVP; uniform vec3 uCam, uVel; uniform float uTime, uScale, uFocalPx, uDen;
uniform vec2 uRes;
out vec2 vQ; out float vA;
const vec3 BOX = vec3(70.0, 44.0, 70.0);
void main(){
  vec2 corner = vec2(gl_VertexID & 1, gl_VertexID >> 1) * 2.0 - 1.0;
  vec3 wind = vec3(4.5, -1.6, 1.2) * (0.6 + 0.8 * aSeed.w);
  vec3 sway = vec3(sin(uTime * 1.3 + aSeed.x * 40.0), 0.0, cos(uTime * 1.1 + aSeed.z * 40.0)) * 0.6;
  vec3 rel = mod(aSeed.xyz * BOX + wind * uTime + sway - uCam, BOX) - BOX * 0.5;
  vec3 wp = uCam + rel;
  vec4 c0 = uVP * vec4(wp, 1.0);
  vec4 c1 = uVP * vec4(wp - (wind - uVel) * 0.03, 1.0);   // where it was a frame ago, relative to us
  if (c0.w < 0.3 || c1.w < 0.3) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }
  vec2 s0 = c0.xy / c0.w * uRes * 0.5, s1 = c1.xy / c1.w * uRes * 0.5;
  float size = max((0.006 + 0.01 * aSeed.w) * uFocalPx / c0.w, 0.9 * uScale);
  float blur = 1.0 - smoothstep(0.6, 4.0, c0.w);                         // close flakes defocus
  size *= 1.0 + blur * 3.0;
  float len = 0.0;                                   // round flakes: no motion blur on the 3D
  vec2 s = s0 + corner * size;
  gl_Position = vec4(s / (uRes * 0.5) * c0.w, 0.0, c0.w);
  vQ = corner;
  vA = (0.5 + 0.5 * aSeed.w) * (1.0 - blur * 0.75) * exp(-c0.w * uDen * 18.0) * smoothstep(0.3, 1.2, c0.w) / (1.0 + len / (size * 2.0) * 0.5);
}`;

const SNOW_FS = `#version 300 es
precision mediump float;
in vec2 vQ; in float vA; uniform vec3 uColor; out vec4 o;
void main(){ float d = dot(vQ, vQ); if (d > 1.0) discard; float a = vA * (1.0 - d) * (1.0 - d); o = vec4(uColor * a, a); }`;

// ---------------------------------------------------------------- setup
function fail() { root.classList.add('no-webgl'); return null; }

const gl = canvas.getContext('webgl2', { antialias: false, alpha: false, depth: false, powerPreference: 'high-performance' });

function program(vs, fs) {
  const p = gl.createProgram();
  for (const [type, src] of [[gl.VERTEX_SHADER, vs], [gl.FRAGMENT_SHADER, fs]]) {
    const s = gl.createShader(type);
    gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) { console.error(gl.getShaderInfoLog(s)); return null; }
    gl.attachShader(p, s);
  }
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) { console.error(gl.getProgramInfoLog(p)); return null; }
  const u = {};
  for (let i = 0, n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS); i < n; i++) {
    const name = gl.getActiveUniform(p, i).name; u[name] = gl.getUniformLocation(p, name);
  }
  return { p, u };
}

function init() {
  if (!gl) return fail();
  const noiseProg = program(FULLSCREEN_VS, NOISE_FS);
  const scene = program(FULLSCREEN_VS, SCENE_FS);
  const snow = program(SNOW_VS, SNOW_FS);
  if (!noiseProg || !scene || !snow) return fail();

  // bake the noise volume, one slice per draw
  const N = 128, tex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_3D, tex);
  gl.texImage3D(gl.TEXTURE_3D, 0, gl.R8, N, N, N, 0, gl.RED, gl.UNSIGNED_BYTE, null);
  for (const k of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER]) gl.texParameteri(gl.TEXTURE_3D, k, gl.LINEAR);
  for (const k of [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T, gl.TEXTURE_WRAP_R]) gl.texParameteri(gl.TEXTURE_3D, k, gl.REPEAT);
  const fb = gl.createFramebuffer();
  gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
  gl.viewport(0, 0, N, N);
  gl.useProgram(noiseProg.p);
  for (let z = 0; z < N; z++) {
    gl.framebufferTextureLayer(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, tex, 0, z);
    gl.uniform1f(noiseProg.u.uZ, z);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  gl.deleteFramebuffer(fb);

  const rockTex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, rockTex);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB8, 1, 1, 0, gl.RGB, gl.UNSIGNED_BYTE, new Uint8Array([105, 99, 91]));
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.MIRRORED_REPEAT);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.MIRRORED_REPEAT);
  const rockImage = new Image();
  rockImage.onload = () => {
    if (done) return;
    gl.bindTexture(gl.TEXTURE_2D, rockTex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB8, gl.RGB, gl.UNSIGNED_BYTE, rockImage);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
    gl.generateMipmap(gl.TEXTURE_2D);
  };
  rockImage.src = 'site/assets/img/intro-kebnekaise-rock.webp';

  // snow seeds
  const COUNT = coarse ? 900 : 2600;
  const seeds = new Float32Array(COUNT * 4);
  for (let i = 0; i < seeds.length; i++) seeds[i] = Math.random();
  const vao = gl.createVertexArray();
  gl.bindVertexArray(vao);
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, seeds, gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0);
  gl.vertexAttribPointer(0, 4, gl.FLOAT, false, 0, 0);
  gl.vertexAttribDivisor(0, 1);
  gl.bindVertexArray(null);

  return { scene, snow, tex, rockTex, vao, COUNT };
}

const ctx = init();

// ---------------------------------------------------------------- overlay
const chapters = [...section.querySelectorAll('[data-chapter]')];
const fig = section.querySelector('.intro-fig');
const readAlt = section.querySelector('[data-read="alt"]');
const readTemp = section.querySelector('[data-read="temp"]');
const readWind = section.querySelector('[data-read="wind"]');
const altMark = section.querySelector('.intro-alt i');
let lastChapter = -1, lastRead = '';

function overlay(p, cam, vp, w, h) {
  stage.style.setProperty('--p', p.toFixed(4));
  let ch = 0;
  chapters.forEach((el, i) => { if (p >= parseFloat(el.dataset.chapter)) ch = i; });
  if (ch !== lastChapter) {
    chapters.forEach((el, i) => el.classList.toggle('is-on', i === ch));
    lastChapter = ch;
  }
  const alt = Math.round(1320 + cam.pos[1]);
  const temp = Math.round(-7 - (alt - 1700) / 70);
  const wind = Math.round(p > 0.93 ? 18 * (1 - smooth(clamp((p - 0.93) / 0.05))) : 11 + 13 * smooth(clamp(p / 0.8)));
  const txt = alt + '|' + temp + '|' + wind;
  if (txt !== lastRead && readAlt) {
    readAlt.textContent = alt.toLocaleString('en-US') + ' m';
    readTemp.textContent = (temp < 0 ? '−' : '+') + Math.abs(temp) + ' °C';
    readWind.textContent = 'NW ' + wind + ' km/h';
    if (altMark) altMark.style.transform = `translateY(${(-(alt - 1700) / 700) * 100}%)`;
    lastRead = txt;
  }
  // FIG. 01 — pinned to the climber while they are still a speck
  if (fig) {
    const on = p > 0.665 && p < 0.79;
    fig.classList.toggle('is-on', on);
    if (on && vp) {
      const c = project(vp, V.add(CLIMBER, [0, 1.0, 0]));
      if (c) fig.style.transform = `translate3d(${(c[0] * 0.5 + 0.5) * w}px, ${(0.5 - c[1] * 0.5) * h}px, 0)`;
    }
  }
}

function project(m, p) {
  const x = m[0] * p[0] + m[4] * p[1] + m[8] * p[2] + m[12];
  const y = m[1] * p[0] + m[5] * p[1] + m[9] * p[2] + m[13];
  const w = m[3] * p[0] + m[7] * p[1] + m[11] * p[2] + m[15];
  return w > 0 ? [x / w, y / w] : null;
}

function viewProj(pos, r, u, f, fov, aspect) {
  const n = 0.1, fa = 20000, t = 1 / Math.tan(fov / 2);
  const P = [t / aspect, 0, 0, 0, 0, t, 0, 0, 0, 0, (fa + n) / (n - fa), -1, 0, 0, (2 * fa * n) / (n - fa), 0];
  const Vw = [r[0], u[0], -f[0], 0, r[1], u[1], -f[1], 0, r[2], u[2], -f[2], 0, -V.dot(r, pos), -V.dot(u, pos), V.dot(f, pos), 1];
  const out = new Float32Array(16);
  for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) {
    let s = 0; for (let k = 0; k < 4; k++) s += P[k * 4 + j] * Vw[i * 4 + k]; out[i * 4 + j] = s;
  }
  return out;
}

// ---------------------------------------------------------------- sound: wind, then silence
const soundBtn = section.querySelector('.intro-sound');
let audio = null;
function startAudio() {
  const ac = new (window.AudioContext || window.webkitAudioContext)();
  const len = ac.sampleRate * 4, buf = ac.createBuffer(2, len, ac.sampleRate);
  for (let c = 0; c < 2; c++) {                 // brown noise, one per channel for width
    const d = buf.getChannelData(c); let last = 0;
    for (let i = 0; i < len; i++) { last = (last + 0.02 * (Math.random() * 2 - 1)) / 1.02; d[i] = last * 3.2; }
  }
  const src = ac.createBufferSource(); src.buffer = buf; src.loop = true;
  const low = ac.createBiquadFilter(); low.type = 'lowpass'; low.frequency.value = 420; low.Q.value = 0.6;
  const band = ac.createBiquadFilter(); band.type = 'bandpass'; band.frequency.value = 900; band.Q.value = 3.5;
  const bandGain = ac.createGain(); bandGain.gain.value = 0.0;
  const master = ac.createGain(); master.gain.value = 0;
  src.connect(low).connect(master); src.connect(band).connect(bandGain).connect(master);
  master.connect(ac.destination); src.start();
  audio = { ac, low, band, bandGain, master };
}
function updateAudio(p, time) {
  if (!audio) return;
  const gust = 0.5 + 0.5 * Math.sin(time * 0.37) * Math.sin(time * 0.13 + 1);
  const toWall = smooth(clamp(p / 0.85));
  const silence = 1 - smooth(clamp((p - 0.9) / 0.08));
  const now = audio.ac.currentTime;
  const on = soundBtn.getAttribute('aria-pressed') === 'true' && p < 1.2;
  audio.master.gain.setTargetAtTime(on ? (0.25 + 0.55 * toWall) * silence * (0.7 + 0.3 * gust) : 0, now, 0.25);
  audio.low.frequency.setTargetAtTime(260 + 520 * gust * (0.4 + toWall), now, 0.3);
  audio.band.frequency.setTargetAtTime(700 + 900 * gust, now, 0.4);
  audio.bandGain.gain.setTargetAtTime(0.18 * toWall * gust, now, 0.4);
}
soundBtn?.addEventListener('click', () => {
  const on = soundBtn.getAttribute('aria-pressed') !== 'true';
  soundBtn.setAttribute('aria-pressed', String(on));
  soundBtn.querySelector('span').textContent = on ? 'On' : 'Off';
  if (on && !audio) startAudio();
  audio?.ac.resume();
});

// ---------------------------------------------------------------- loop
let scale = coarse ? 0.75 : 0.62;            // render resolution, in CSS pixels, adapted live
const MAX_SCALE = Math.min(devicePixelRatio || 1, coarse ? 1.25 : 1.5);
const MIN_SCALE = 0.3;
let quality = coarse ? 1 : 2, cooldown = 60;
let pShown = DEBUG_P ?? 0, target = 0, running = false, visible = true, raf = 0;
let t0 = performance.now(), last = t0, frames = 0, acc = 0, prevCam = null;

function scrollProgress() {
  const span = (section.offsetHeight - innerHeight) * 0.96;     // complete while the stage is still pinned
  return span > 0 ? clamp(-section.getBoundingClientRect().top / span) : 0;
}

function resize() {
  const w = Math.max(1, Math.round(stage.clientWidth * scale));
  const h = Math.max(1, Math.round(stage.clientHeight * scale));
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
}

// The end: the stage stays exactly where it is on screen and becomes the first screen of the page,
// the scroll length it used is removed, and the GPU is released. Scrolling up later is just the page.
function finish(toTop) {
  if (done || DEBUG_P != null) return;
  done = true;
  const extra = section.offsetHeight - stage.offsetHeight;
  const y = toTop ? 0 : Math.max(0, scrollY - extra);
  markDone();
  scrollTo({ top: y, behavior: 'instant' });   // html scrolls smoothly: an animated jump here flies down the page and back
  cancelAnimationFrame(raf);
  if (audio) { audio.master.gain.setTargetAtTime(0, audio.ac.currentTime, 0.2); setTimeout(() => audio.ac.close(), 1500); }
  gl?.getExtension('WEBGL_lose_context')?.loseContext();
  canvas.remove();
}

function frame(now) {
  running = false;
  if (!visible || !ctx || done) return;
  const dt = Math.min((now - last) / 1000, 0.1); last = now;
  const time = (now - t0) / 1000;
  target = DEBUG_P ?? (reduced ? 0.4 : scrollProgress());
  pShown = reduced || DEBUG_P != null ? target : pShown + (target - pShown) * (1 - Math.exp(-dt * 2.6));
  if (target >= 1 && pShown > 0.994 && !reduced && DEBUG_P == null) { finish(false); return; }
  const p = story(pShown);

  resize();
  const W = canvas.width, H = canvas.height;
  const cam = camera(p, reduced ? 0 : time);
  const f = V.norm(V.sub(cam.tgt, cam.pos));
  const r = V.norm(V.cross(f, [0, 1, 0]));
  const u = V.cross(r, f);
  const fov = (cam.fov * (W < H ? 1.3 : 1) * Math.PI) / 180;   // portrait: open up so the peak is not cropped
  const focal = 1 / Math.tan(fov / 2);
  const L = look(p);
  const layer = 1.6 - 1.35 * smooth(clamp((p - 0.37) / 0.08)) + 1.1 * smooth(clamp((p - 0.56) / 0.1));
  const tmax = Math.min(9000, 6.5 / (L.den * (0.55 + layer * Math.exp(-(cam.pos[1] - 380) / 420)) + 1e-6));   // where the mist is total, stop
  const vel = prevCam && dt > 0 ? V.mul(V.sub(cam.pos, prevCam), 1 / dt) : [0, 0, 0];
  prevCam = cam.pos;
  const white = smooth(clamp((p - 0.975) / 0.02));   // the fog is already white by then: this only settles the last bit

  const { scene, snow } = ctx;
  gl.viewport(0, 0, W, H);
  gl.useProgram(scene.p);
  const U = scene.u;
  gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_3D, ctx.tex); gl.uniform1i(U.uNoise, 0);
  gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, ctx.rockTex); gl.uniform1i(U.uRock, 1);
  gl.uniform2f(U.uRes, W, H);
  gl.uniform1f(U.uTime, reduced ? 0 : time);
  gl.uniform1f(U.uFocal, focal);
  gl.uniform1f(U.uPix, 2 / (focal * H));
  gl.uniform3fv(U.uCam, cam.pos); gl.uniform3fv(U.uCamR, r); gl.uniform3fv(U.uCamU, u); gl.uniform3fv(U.uCamF, f);
  gl.uniform3fv(U.uSunDir, L.sunDir);
  gl.uniform3fv(U.uSunCol, L.sun); gl.uniform3fv(U.uFogCol, L.fog);
  gl.uniform1f(U.uFogDen, L.den); gl.uniform1f(U.uCloud, L.cloud); gl.uniform1f(U.uWhite, white);
  gl.uniform1f(U.uTMax, tmax); gl.uniform1f(U.uExposure, L.exposure);
  gl.uniform1f(U.uVig, 1 - smooth(clamp((p - 0.87) / 0.1)));
  gl.uniform1f(U.uLayer, layer);
  gl.uniform3f(U.uPaper, 0.957, 0.949, 0.933);
  gl.uniform1i(U.uSteps, coarse ? 110 : 180);
  gl.uniform1i(U.uCloudSteps, coarse ? 7 : 12);
  gl.uniform1i(U.uQuality, quality);
  gl.disable(gl.BLEND);
  gl.drawArrays(gl.TRIANGLES, 0, 3);

  const vp = viewProj(cam.pos, r, u, f, fov, W / H);
  if (white < 0.999) {
    gl.useProgram(snow.p);
    const S = snow.u;
    gl.uniformMatrix4fv(S.uVP, false, vp);
    gl.uniform3fv(S.uCam, cam.pos); gl.uniform3fv(S.uVel, vel);
    gl.uniform1f(S.uTime, reduced ? 0 : time);
    gl.uniform1f(S.uScale, scale);
    gl.uniform1f(S.uFocalPx, focal * H * 0.5);
    gl.uniform1f(S.uDen, L.den);
    gl.uniform2f(S.uRes, W, H);
    const bright = (0.55 + 0.45 * clamp(p / 0.5)) * (1 - smooth(clamp((p - 0.9) / 0.07)));   // flakes vanish into the cloud
    gl.uniform3f(S.uColor, 0.8 * bright, 0.84 * bright, 0.9 * bright);
    gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.bindVertexArray(ctx.vao);
    gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, ctx.COUNT);
    gl.bindVertexArray(null);
  }

  overlay(reduced ? 0 : p, cam, vp, stage.clientWidth, stage.clientHeight);
  stage.classList.toggle('is-light', p > 0.88 && !reduced);
  updateAudio(p, time);

  // adaptive resolution. Under vsync a fast frame and a barely-fast one look the same, so the
  // only signal is dropped frames: back off quickly, and probe upwards again after a quiet spell.
  frames++; acc += dt; cooldown = Math.max(0, cooldown - 1);
  if (frames >= 30 && DEBUG_P == null) {
    const ms = (acc / frames) * 1000;
    if (ms > 19.5) {
      if (scale > MIN_SCALE) scale = Math.max(MIN_SCALE, scale * 0.88);
      else if (quality > 0 && ms > 24) quality--;
      cooldown = 150;
    } else if (ms < 17.6 && !cooldown && scale < MAX_SCALE) { scale = Math.min(MAX_SCALE, scale * 1.05); cooldown = 45; }
    frames = 0; acc = 0;
  }
  window.__intro = { p, scale, quality, W, H, ms: dt * 1000 };
  if (!reduced || DEBUG_P != null) request();
}

function request() { if (!running && !done) { running = true; raf = requestAnimationFrame(frame); } }

if (ctx) {
  root.classList.add('has-webgl');
  // scrolled away before the camera caught up (a fast flick, a #hash): the intro is over all the same
  new IntersectionObserver(([e]) => {
    visible = e.isIntersecting;
    if (visible) request(); else if (target >= 1 || scrollProgress() >= 1) finish(false);
  }).observe(section);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) { last = performance.now(); request(); } });
  section.querySelector('.intro-skip')?.addEventListener('click', (e) => { e.preventDefault(); finish(true); section.querySelector('.intro-end h2, .intro-end')?.focus?.(); });
  request();
} else markDone();
})();
