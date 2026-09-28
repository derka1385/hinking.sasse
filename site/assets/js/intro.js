// The ascent: a scroll-driven camera through fog, towards one climber on a north face.
// Raw WebGL2, no library. One raymarched full-screen pass (terrain, rock, climber, fog, clouds)
// and one instanced pass for snow. Scroll never gets hijacked: the camera only follows it, damped.
(() => {

const section = document.getElementById('intro');
const stage = section.querySelector('.intro-stage');
const canvas = section.querySelector('canvas');
const root = document.documentElement;

const params = new URLSearchParams(location.search);
const DEBUG_P = params.has('p') ? parseFloat(params.get('p')) : null;   // ?p=0.6 freezes the camera
const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
const coarse = matchMedia('(pointer: coarse)').matches || innerWidth < 760;

// An opening title, not a section: it plays on load (and on every reload), runs once, then it is over.
// Coming back to Home from another page in the same visit goes straight to the title card.
const navType = performance.getEntriesByType('navigation')[0]?.type;
const play = DEBUG_P != null || params.has('intro') || navType === 'reload' || sessionStorage.getItem('hc-intro') !== 'seen';
let done = false;
function markDone() {
  section.classList.add('is-done');
  root.classList.add('intro-complete');
  stage.style.setProperty('--p', '1');
  try { sessionStorage.setItem('hc-intro', 'seen'); } catch (e) { /* private mode: replays, harmless */ }
}
if (!play || reduced) {
  markDone();
  if (!play) return;
}
if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
scrollTo(0, 0);

// ---------------------------------------------------------------- math
const V = {
  add: (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]],
  sub: (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]],
  mul: (a, s) => [a[0] * s, a[1] * s, a[2] * s],
  dot: (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2],
  cross: (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]],
  norm: (a) => V.mul(a, 1 / Math.hypot(...a)),
  mix: (a, b, t) => a.map((v, i) => v + (b[i] - v) * t),
};
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const smooth = (t) => t * t * (3 - 2 * t);

// ---------------------------------------------------------------- the world (metres, y up)
// The face is a plane through the summit, 66° steep, facing the camera; a snow couloir cuts it at
// the 2:1 slope of the club's mark — the cleft — and the climber stands in it.
const SUMMIT = [80, 1150, -320];
const NF = V.norm([0, 0.45, 1]);          // face normal
const TX = [1, 0, 0];                     // across the face
const TY = V.cross(NF, TX);               // up the face
const DEPTH = 8;                          // couloir floor below the face plane
const CU = -20, CV = -640;                // climber, in face coordinates
const CLIMBER = V.add(V.add(SUMMIT, V.add(V.mul(TX, CU), V.mul(TY, CV))), V.mul(NF, -DEPTH));
const at = (n, x, y, up = 0) => V.add(V.add(V.add(CLIMBER, V.mul(NF, n)), V.add(V.mul(TX, x), V.mul(TY, y))), [0, up, 0]);
const LOOK = V.add(CLIMBER, [0, 1.1, 0]);

// Camera keys: progress, position, target, vertical fov (deg).
// The climber is there for scale: we find them, travel along the wall beside them, and never close in.
const KEYS = [
  [0.00, [-150, 430, 5900], [40, 660, 0], 40],
  [0.15, [-120, 440, 4500], [40, 650, 0], 40],
  [0.31, [-70, 455, 3100], [40, 630, 0], 38],
  [0.47, [0, 480, 1800], [45, 610, -60], 36],
  [0.62, at(620, -10, -120), LOOK, 30],
  [0.72, at(300, 30, -70), LOOK, 28],
  [0.79, at(140, 45, -30), at(0, 0, 2, 1.2), 26],
  [0.85, at(128, -10, -8), at(0, -8, 4, 1), 26],
  [0.90, at(122, -62, 14), at(0, -16, 12, 1), 27],
  [0.95, at(150, -100, 50), at(40, -140, 220), 31],
  [1.00, at(175, -125, 95), at(60, -170, 330), 33],
];

// Atmosphere keys: progress, fog colour (linear), fog density, cloud bank, sun colour, exposure, sun direction.
// It opens in the club's navy, before dawn. At the end a cloud bank rolls over the wall: contrast goes,
// luminance rises, and the fog itself becomes the paper of the page.
const LOOKS = [
  [0.00, [0.0035, 0.0085, 0.019], 0.00028, 0.12, [0.30, 0.34, 0.46], 1.0, [0.30, 0.12, -1.0]],
  [0.10, [0.0080, 0.0140, 0.026], 0.00060, 1.00, [0.20, 0.21, 0.24], 1.0, [0.40, 0.16, -0.9]],
  [0.22, [0.030, 0.040, 0.055], 0.00050, 0.90, [0.45, 0.43, 0.42], 1.0, [0.60, 0.22, -0.7]],
  [0.34, [0.070, 0.082, 0.100], 0.00024, 0.25, [1.20, 1.10, 1.00], 1.0, [0.78, 0.30, -0.45]],
  [0.50, [0.110, 0.125, 0.145], 0.00013, 0.06, [2.20, 2.05, 1.85], 1.0, [0.82, 0.40, -0.05]],
  [0.70, [0.150, 0.165, 0.185], 0.00012, 0.10, [2.40, 2.25, 2.05], 1.0, [0.80, 0.42, 0.05]],
  [0.87, [0.230, 0.245, 0.262], 0.00026, 0.55, [2.50, 2.35, 2.15], 1.0, [0.80, 0.42, 0.05]],
  [0.905, [0.400, 0.415, 0.430], 0.00110, 1.40, [2.60, 2.45, 2.30], 1.0, [0.80, 0.42, 0.05]],
  [0.94, [0.660, 0.668, 0.668], 0.00500, 2.40, [2.80, 2.70, 2.55], 1.04, [0.80, 0.42, 0.05]],
  [0.97, [0.960, 0.950, 0.915], 0.02500, 3.20, [3.00, 2.90, 2.75], 1.08, [0.80, 0.42, 0.05]],
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
function camera(p, time) {
  if (DEBUG_CAM) { const c = DEBUG_CAM; return { pos: at(c[0], c[1], c[2], c[3]), tgt: at(c[4], c[5], c[6], c[7]), fov: c[8] }; }
  const { i, t } = sampleKeys(KEYS, p);
  const k = (j) => KEYS[clamp(j, 0, KEYS.length - 1)];
  const pos = catmull(k(i - 1)[1], k(i)[1], k(i + 1)[1], k(i + 2)[1], t);
  const tgt = catmull(k(i - 1)[2], k(i)[2], k(i + 1)[2], k(i + 2)[2], t);
  const fov = k(i)[3] + (k(i + 1)[3] - k(i)[3]) * smooth(t);
  const out = V.dot(V.sub(pos, CLIMBER), NF);
  if (out < 2.5 && p > 0.7) pos.splice(0, 3, ...V.add(pos, V.mul(NF, 2.5 - out)));
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

const SCENE_FS = `#version 300 es
precision highp float; precision highp sampler3D;
uniform sampler3D uNoise;
uniform vec2 uRes; uniform float uTime, uFocal, uPix;
uniform vec3 uCam, uCamR, uCamU, uCamF;
uniform vec3 uSunDir, uSunCol, uFogCol;
uniform float uFogDen, uCloud, uWhite, uTMax, uExposure, uVig;
uniform vec3 uPaper;
uniform int uSteps, uCloudSteps, uQuality;
out vec4 outColor;

const vec3 S1 = ${f3(SUMMIT)};
const vec3 NF = ${f3(NF)};
const vec3 TY = ${f3(TY)};
const vec3 CLIMB = ${f3(CLIMBER)};
const vec2 CUV = vec2(${CU.toFixed(1)}, ${CV.toFixed(1)});
const vec2 CDIR = vec2(-0.4472136, 0.8944272);   // up the couloir: 2:1, the slope of the mark
const float DEPTH = ${DEPTH.toFixed(1)};
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

// the couloir: signed distance across it, rough walls, a meandering line at the 2:1 slope
float couloirAcross(vec3 p, vec3 f, out float along){
  vec2 uv = f.xy - CUV;
  along = dot(uv, CDIR);
  float across = uv.x * CDIR.y - uv.y * CDIR.x;
  across += 16.0 * (n3(vec3(along / 150.0, 1.7, 0.3)) - 0.5) * smoothstep(40.0, 140.0, abs(along));  // meander, straight near the climber
  float ends = smoothstep(-340.0, -250.0, along) * (1.0 - smoothstep(420.0, 540.0, along));
  float w = mix(-30.0, 15.0 + 11.0 * n3(vec3(along / 70.0, 4.1, 2.2)) * smoothstep(30.0, 120.0, abs(along)), ends);
  return abs(across) - w;
}

// ---- rock: ridged multifractal stretched along the fall line (flutings, ribs, gullies),
// each octave weighted by the one above it so crests stay sharp and hollows stay smooth
float rock(vec3 p, float lod, float nearGully, out float gully){
  vec3 q = p + (vec3(n3(p / 330.0), n3(p / 330.0 + 5.2), n3(p / 330.0 + 9.1)) - 0.5) * 60.0;
  float big = n3(q * vec3(1.0 / 420.0, 1.0 / 1000.0, 1.0 / 420.0) + 1.3);
  float h = 85.0 * smoothstep(0.3, 0.85, big);
  float oct = clamp(log2(150.0 / (4.0 * max(lod, 1.0) * uPix)), 1.0, 9.0);
  vec3 r = vec3(q.x, q.y * 0.4, q.z) / 150.0;                   // features 2.5x taller than wide
  float amp = 46.0, wgt = 1.0, sum = 0.0;
  gully = 0.0;
  for (int i = 0; i < 9; i++){
    float fw = clamp(oct - float(i), 0.0, 1.0);
    if (fw <= 0.0) break;
    float n = 1.0 - abs(2.0 * (i < 3 ? vn3(r * 1.7) : n3(r)) - 1.0);
    n = n * n * wgt;
    wgt = clamp(n * 1.6, 0.0, 1.0);
    sum += amp * n * fw;
    if (i == 1) gully = 1.0 - clamp(sum / 40.0, 0.0, 1.0);
    amp *= 0.5;
    r = (i < 2 ? vec3(r.x * 0.8 - r.z * 0.6, r.y, r.x * 0.6 + r.z * 0.8) : ROT * r) * 2.03 + vec3(1.7, 3.1, 0.4);
  }
  h += sum;
  return h * nearGully;
}

float pyramid(vec3 p, vec3 s, vec3 nf, vec3 nl, vec3 nr, vec3 nb){
  vec3 q = p - s; return max(max(dot(q, nf), dot(q, nl)), max(dot(q, nr), dot(q, nb)));
}

float gullyOut; // set by massif(), read by shade()
float massif(vec3 p, float lod){
  vec3 f = faceUVW(p);
  float along, cw = couloirAcross(p, f, along);
  float calm = smoothstep(15.0, 260.0, cw);                                         // the gully sits in a quiet hollow
  vec3 wp = p + (vec3(n3(p / 700.0 + 2.0), 0.0, n3(p / 700.0 + 6.0)) - 0.5) * 110.0 * mix(0.15, 1.0, calm);  // no straight edges
  float a = pyramid(wp, S1, NF, normalize(vec3(-0.72, 0.58, 0.3)), normalize(vec3(0.96, 0.3, 0.2)), normalize(vec3(0.05, 0.5, -1.0)));
  float b = pyramid(wp, vec3(-860.0, 720.0, -380.0), normalize(vec3(0.12, 0.85, 1.0)), normalize(vec3(-0.6, 0.95, 0.15)), normalize(vec3(0.75, 0.7, 0.25)), normalize(vec3(0.0, 0.7, -1.0)));
  float c = pyramid(wp, vec3(960.0, 640.0, -820.0), normalize(vec3(-0.15, 0.75, 1.0)), normalize(vec3(-0.8, 0.8, 0.1)), normalize(vec3(0.9, 0.75, 0.2)), normalize(vec3(0.0, 0.6, -1.0)));
  float d = smin(smin(a, b, 140.0), c, 160.0);
  if (d > 200.0) return (d - 185.0) * 0.8;                                        // far from rock: cheap bound
  float near = mix(0.15, 1.0, calm);
  // from far away the gully is a snow-filled hollow in the rock; it is only carved once we are close
  float carveAmt = 1.0 - smoothstep(900.0, 1400.0, lod);
  if (carveAmt <= 0.0) return (d - rock(p, lod, near, gullyOut)) * 0.8;
  // rough gully walls, band-limited: noise finer than a pixel only makes rays stop in mid-air
  float wall = cw < 12.0 ? cw - 3.5 * n3(p / 7.0) * (1.0 - smoothstep(1200.0, 2600.0, lod)) - 1.6 * n3(p / 2.6) * (1.0 - smoothstep(300.0, 800.0, lod)) : cw - 5.1;
  float floorD = f.z + DEPTH;
  float carve = -max(wall, -floorD);
  // exact: rock() >= 0, so when d < carve the carve wins whatever the rock does
  bool buried = wall < -1.0 && d < carve && carveAmt >= 1.0;
  float raw = buried ? carve : d - rock(p, lod, near, gullyOut);
  float rk = buried ? carve : max(raw, carve);
  float snow = wall - 1.0;
  if (wall < 2.0){
    float fine = 1.0 - smoothstep(60.0, 260.0, lod);                  // sub-pixel beyond that: it would only sparkle
    float ripples = fine * (0.12 * n3(p * vec3(1.0 / 0.6, 1.0 / 5.0, 1.0 / 0.6)) + 0.06 * n3(p / 0.45)) + 0.12 * n3(p / 4.0) + 0.35 * n3(p / 23.0);
    snow = max(max(floorD - ripples, snow), d + 4.0);
  }
  float res = min(rk, snow);
  return (carveAmt < 1.0 ? mix(raw, res, carveAmt) : res) * 0.8;
}

float ground(vec2 xz, float lod){
  float h = -0.075 * max(xz.y - 250.0, 0.0);
  float side = max(abs(xz.x - 60.0) - 1000.0, 0.0);
  float far = 1.0 - smoothstep(-2000.0, -600.0, xz.y);
  vec3 q = vec3(xz.x, 11.0, xz.y) / 1700.0; q += (vec3(n3(q * 0.7), 0.0, n3(q * 0.7 + 4.0)) - 0.5) * 0.8;
  if (side > 0.0 || far > 0.0){
    float rg = 0.0, a = 1.0;
    for (int i = 0; i < 5; i++){ float n = 1.0 - abs(2.0 * n3(q) - 1.0); rg += a * n; a *= 0.48; q = ROT * q * 2.03; }
    rg /= 1.9;
    h += smoothstep(0.0, 1600.0, side) * (380.0 + 820.0 * rg * rg) + far * (300.0 + 900.0 * rg * rg);
  }
  h += 24.0 * n3(vec3(xz.x, 3.0, xz.y) / 230.0) + 6.0 * n3(vec3(xz.x, 5.0, xz.y) / 41.0);
  return h;
}

// ---- the climber, in local coordinates: x across, y up, z into the wall. Metres.
float sdCap(vec3 p, vec3 a, vec3 b, float r){ vec3 pa = p - a, ba = b - a; float h = clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0); return length(pa - ba*h) - r; }
float sdBox(vec3 p, vec3 b, float r){ vec3 q = abs(p) - b; return length(max(q, 0.0)) + min(max(q.x, max(q.y, q.z)), 0.0) - r; }

vec2 climber(vec3 q){
  vec3 b = vec3(q.x, q.y, -q.z);
  float t = uTime;
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

// the rope, from the harness down the couloir to an anchor out of sight
const vec3 DOWN = normalize(vec3(0.4472136, 0.0, 0.0) - 0.8944272 * TY);
float rope(vec3 p, float lod){
  vec3 h = CLIMB + vec3(0.0, 0.95, 0.16);
  vec3 a = CLIMB + DOWN * 1.1 + NF * 0.42, b = CLIMB + DOWN * 5.0 + NF * 0.07, c = CLIMB + DOWN * 48.0 + NF * 0.07;
  float r = max(0.011, 0.6 * uPix * lod);
  return min(min(sdCap(p, h, a, r), sdCap(p, a, b, r)), sdCap(p, b, c, r));
}

vec2 map(vec3 p, float lod){
  vec2 r = vec2(smin(massif(p, lod), (p.y - ground(p.xz, lod)) * 0.55, 45.0), 0.0);
  vec3 q = p - CLIMB;
  float inflate = 0.75 * uPix * lod;                    // never thinner than a pixel: no shimmering speck
  float bound = length(q - vec3(0.0, 1.0, 0.0)) - 1.6;
  if (bound < r.x + inflate){ vec2 c = climber(q); c.x -= inflate; if (c.x < r.x) r = c; }
  if (dot(q, q) < 3000.0){ float rp = rope(p, lod); if (rp < r.x) r = vec2(rp, 4.0); }
  return r;
}

vec3 normal(vec3 p, float t){
  float e = max(0.0012 * t, 0.004); const vec2 k = vec2(1.0, -1.0);
  return normalize(k.xyy * map(p + k.xyy*e, t).x + k.yyx * map(p + k.yyx*e, t).x + k.yxy * map(p + k.yxy*e, t).x + k.xxx * map(p + k.xxx*e, t).x);
}

float shadow(vec3 ro, vec3 rd, float lod){
  float res = 1.0, t = 0.05 + lod * 0.002;
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
  for (int i = 1; i <= 4; i++){ if (i > cnt) break; float h = s * float(i); o += w * (h - map(p + n*h, t).x); w *= 0.62; }
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
  return 1.0 - exp(-uFogDen * (0.55 * t + 1.6 * exp(-(ro.y - base) * b) * k));
}

vec3 shade(vec3 p, vec3 rd, float t, float mat){
  vec3 n = normal(p, t);
  vec3 alb; float spec = 0.0, snowAmt = 0.0;
  if (mat < 0.5){
    vec3 f = faceUVW(p);
    float along, cw = couloirAcross(p, f, along);
    float gully; rock(p, t, 1.0, gully);
    float v = n3(p / 23.0), w = n3(p / 5.0), fine = n3(p / 1.3);
    vec3 rk = vec3(0.050, 0.052, 0.057) * (0.6 + 0.8 * v) * mix(vec3(1.0), vec3(1.1, 1.0, 0.9), n3(p / 170.0));
    rk = mix(rk, vec3(0.5, 0.53, 0.58), 0.35 * smoothstep(0.35, 0.65, n.y + 0.4 * (fine - 0.5)));   // dusting
    float snow = smoothstep(0.56, 0.72, n.y + 0.28 * (w - 0.5) + 0.1 * (v - 0.5));                 // ledges
    snow = max(snow, smoothstep(0.62, 0.86, gully + 0.25 * (w - 0.5)) * smoothstep(0.18, 0.4, n.y)); // gullies
    float onFloor = max(1.0 - smoothstep(-DEPTH + 0.8, -DEPTH + 3.5, f.z), smoothstep(900.0, 1400.0, t));
    snow = max(snow, (1.0 - smoothstep(0.0, 1.8, cw - 2.5 * w)) * onFloor);  // the couloir
    snow = max(snow, (1.0 - smoothstep(0.0, 60.0, p.y - ground(p.xz, t))) * smoothstep(0.2, 0.5, n.y) * (1.0 - smoothstep(120.0, 260.0, p.y)));
    alb = mix(rk, vec3(0.76, 0.80, 0.87) * (0.88 + 0.16 * w), snow);
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
  float sh = dif > 0.001 ? (uQuality > 1 && t < 2600.0 ? shadow(p + n * max(0.02, t * 0.002), uSunDir, t) : occ) : 0.0;
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

vec3 aces(vec3 x){ return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0); }

void main(){
  vec2 fc = gl_FragCoord.xy;
  vec2 uv = (2.0 * fc - uRes) / uRes.y;
  vec3 rd = normalize(uCamF * uFocal + uCamR * uv.x + uCamU * uv.y);
  vec3 ro = uCam;
  float t = 1.0, tPrev = 1.0, mat = -1.0;
  for (int i = 0; i < 220; i++){
    if (i >= uSteps) break;
    vec3 p = ro + rd * t;
    if (p.y > 2300.0 && rd.y > 0.0) { t = uTMax + 1.0; break; }
    vec2 h = map(p, t);
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
  vec3 col;
  if (t < uTMax && mat > -0.5) col = shade(ro + rd * t, rd, t, mat);
  else { t = uTMax; col = fogColor(rd); }
  col = mix(col, fogColor(rd), fogAmount(ro, rd, t));
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

// Snow: instanced streaks living in a box that travels with the camera.
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
  vec2 v = s0 - s1; float len = length(v); vec2 dir = len > 1e-3 ? v / len : vec2(0.0, 1.0);
  vec2 perp = vec2(-dir.y, dir.x);
  vec2 off = dir * corner.y * (size + len * 0.5) + perp * corner.x * size;
  vec2 s = (s0 + s1) * 0.5 + off;
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

  return { scene, snow, tex, vao, COUNT };
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
    readTemp.textContent = '−' + Math.abs(temp) + ' °C';
    readWind.textContent = 'NW ' + wind + ' km/h';
    if (altMark) altMark.style.transform = `translateY(${(-(alt - 1700) / 700) * 100}%)`;
    lastRead = txt;
  }
  // FIG. 01 — pinned to the climber while they are still a speck
  if (fig) {
    const on = p > 0.60 && p < 0.75;
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
  scrollTo(0, y);
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
  if (target >= 1 && pShown > 0.994 && !reduced) { finish(false); return; }
  const p = pShown;

  resize();
  const W = canvas.width, H = canvas.height;
  const cam = camera(p, reduced ? 0 : time);
  const f = V.norm(V.sub(cam.tgt, cam.pos));
  const r = V.norm(V.cross(f, [0, 1, 0]));
  const u = V.cross(r, f);
  const fov = (cam.fov * (W < H ? 1.3 : 1) * Math.PI) / 180;   // portrait: open up so the peak is not cropped
  const focal = 1 / Math.tan(fov / 2);
  const L = look(p);
  const tmax = Math.min(9000, 7.0 / (L.den * 0.55 + 1e-6));
  const vel = prevCam && dt > 0 ? V.mul(V.sub(cam.pos, prevCam), 1 / dt) : [0, 0, 0];
  prevCam = cam.pos;
  const white = smooth(clamp((p - 0.975) / 0.02));   // the fog is already white by then: this only settles the last bit

  const { scene, snow } = ctx;
  gl.viewport(0, 0, W, H);
  gl.useProgram(scene.p);
  const U = scene.u;
  gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_3D, ctx.tex); gl.uniform1i(U.uNoise, 0);
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
  if (reduced) addEventListener('resize', () => requestAnimationFrame(frame));
  section.querySelector('.intro-skip')?.addEventListener('click', (e) => { e.preventDefault(); finish(true); section.querySelector('.intro-end h2, .intro-end')?.focus?.(); });
  request();
} else markDone();
})();
