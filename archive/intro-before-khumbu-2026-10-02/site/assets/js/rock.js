// A fragment of granite for the Climbing scene: a raymarched block, fractured by a few planes,
// weathered by the same ridged noise as the intro's north face. It turns with the scroll.
(() => {
const canvas = document.querySelector('canvas[data-rock]');
if (!canvas) return;
const gl = canvas.getContext('webgl2', { alpha: true, premultipliedAlpha: true, antialias: false });
if (!gl) return;
const coarse = matchMedia('(pointer: coarse)').matches;

const FS = `#version 300 es
precision highp float;
uniform vec2 uRes; uniform mat3 uRot; out vec4 o;
float h13(vec3 p){ p = fract(p * 0.1031); p += dot(p, p.zyx + 31.32); return fract((p.x + p.y) * p.z); }
float vn(vec3 x){ vec3 i = floor(x), f = fract(x), u = f*f*f*(f*(f*6.0-15.0)+10.0);
  return mix(mix(mix(h13(i), h13(i+vec3(1,0,0)), u.x), mix(h13(i+vec3(0,1,0)), h13(i+vec3(1,1,0)), u.x), u.y),
             mix(mix(h13(i+vec3(0,0,1)), h13(i+vec3(1,0,1)), u.x), mix(h13(i+vec3(0,1,1)), h13(i+vec3(1,1,1)), u.x), u.y), u.z); }
const mat3 R = mat3(0.00, 0.80, 0.60, -0.80, 0.36, -0.48, -0.60, -0.48, 0.64);
float fbm(vec3 p){ float s = 0.0, a = 0.5; for (int i = 0; i < 5; i++){ s += a * (1.0 - abs(2.0 * vn(p) - 1.0)); p = R * p * 2.07; a *= 0.5; } return s; }
float map(vec3 p){
  p = uRot * p;
  float d = length(p * vec3(1.0, 1.25, 0.9)) - 0.9;                        // a rounded block
  d = max(d, dot(p, normalize(vec3(0.3, 1.0, 0.2))) - 0.52);                 // fracture planes
  d = max(d, dot(p, normalize(vec3(-0.9, -0.3, 0.4))) - 0.66);
  d = max(d, dot(p, normalize(vec3(0.5, -0.8, -0.6))) - 0.6);
  d = max(d, dot(p, normalize(vec3(0.1, 0.2, -1.0))) - 0.62);
  return d - 0.07 * fbm(p * 2.6) - 0.012 * vn(p * 30.0);
}
vec3 nrm(vec3 p){ const vec2 e = vec2(0.0015, 0.0); return normalize(vec3(map(p+e.xyy)-map(p-e.xyy), map(p+e.yxy)-map(p-e.yxy), map(p+e.yyx)-map(p-e.yyx))); }
void main(){
  vec2 uv = (2.0 * gl_FragCoord.xy - uRes) / uRes.y;
  vec3 ro = vec3(0.0, 0.0, 3.2), rd = normalize(vec3(uv, -2.1));
  float t = 1.8; bool hit = false;
  for (int i = 0; i < 90; i++){ float h = map(ro + rd * t); if (h < 0.0008) { hit = true; break; } t += h * 0.8; if (t > 4.8) break; }
  if (!hit){ o = vec4(0.0); return; }
  vec3 p = ro + rd * t, n = nrm(p), q = uRot * p;
  vec3 L = normalize(vec3(-0.5, 0.7, 0.5));
  float dif = max(dot(n, L), 0.0), occ = 0.0;
  for (int i = 1; i <= 4; i++){ float s = 0.03 * float(i); occ += (s - map(p + n * s)) / s; }
  occ = clamp(1.0 - occ * 0.25, 0.0, 1.0);
  float grain = vn(q * 42.0), fel = smoothstep(0.72, 0.9, vn(q * 17.0 + 3.0));
  vec3 alb = mix(vec3(0.34, 0.33, 0.32), vec3(0.52, 0.49, 0.46), grain);   // granite, with a little feldspar
  alb = mix(alb, vec3(0.62, 0.52, 0.46), fel * 0.5) * (0.8 + 0.3 * vn(q * 5.0));
  alb *= 1.0 - 0.6 * smoothstep(0.55, 0.8, vn(q * 3.0 + 9.0)) * smoothstep(0.2, 0.8, n.y);   // weathering on the upper faces
  vec3 col = alb * (dif * 1.25 + 0.28 * (0.6 + 0.4 * n.y)) * occ;
  col += 0.05 * pow(clamp(1.0 + dot(rd, n), 0.0, 1.0), 3.0);
  o = vec4(pow(col, vec3(1.0 / 2.2)), 1.0);
}`;
const VS = '#version 300 es\nvoid main(){ vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2); gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0); }';
const prog = gl.createProgram();
for (const [type, src] of [[gl.VERTEX_SHADER, VS], [gl.FRAGMENT_SHADER, FS]]) {
  const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) { console.error(gl.getShaderInfoLog(s)); return; }
  gl.attachShader(prog, s);
}
gl.linkProgram(prog);
const uRes = gl.getUniformLocation(prog, 'uRes'), uRot = gl.getUniformLocation(prog, 'uRot');
let visible = false, last = '', ptr = [0, 0], pt = [0, 0];
new IntersectionObserver(([e]) => { visible = e.isIntersecting; if (visible) HC.wake(); }).observe(canvas);
if (!coarse) addEventListener('pointermove', (e) => { if (visible) { pt = [e.clientX / innerWidth - 0.5, e.clientY / innerHeight - 0.5]; HC.wake(); } }, { passive: true });

HC.onFrame((time) => {
  if (!visible) return false;
  const p = HC.progress(canvas.closest('[data-scene]'));
  ptr[0] += (pt[0] - ptr[0]) * 0.05; ptr[1] += (pt[1] - ptr[1]) * 0.05;
  const a = p * 2.2 + ptr[0] * 0.5 + 0.6, b = 0.35 + p * 0.5 + ptr[1] * 0.3;
  const key = `${a.toFixed(4)}|${b.toFixed(4)}|${canvas.clientWidth}`;
  if (key === last) return false;
  last = key;
  const dpr = Math.min(devicePixelRatio || 1, coarse ? 1 : 1.5) * 0.8;
  const w = Math.round(canvas.clientWidth * dpr), h = Math.round(canvas.clientHeight * dpr);
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  const ca = Math.cos(a), sa = Math.sin(a), cb = Math.cos(b), sb = Math.sin(b);
  // yaw then pitch
  const M = [ca, sa * sb, -sa * cb, 0, cb, sb, sa, -ca * sb, ca * cb];
  gl.viewport(0, 0, w, h); gl.useProgram(prog);
  gl.uniform2f(uRes, w, h); gl.uniformMatrix3fv(uRot, false, M);
  gl.drawArrays(gl.TRIANGLES, 0, 3);
  return Math.abs(pt[0] - ptr[0]) > 0.001 || Math.abs(pt[1] - ptr[1]) > 0.001;
});
})();
