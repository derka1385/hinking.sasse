// Integration contracts for the approved relief, the archived intro and Git atmosphere.
// Run from any directory: node site/tools/check_khumbu_integration.mjs.
// These checks validate asset identity and math; real shader compilation needs WebGL2.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url));
const archive = path.join(root, 'archive/intro-before-khumbu-2026-10-02');
const read = name => fs.readFileSync(path.join(root, name), 'utf8');
const archived = name => fs.readFileSync(path.join(archive, name), 'utf8');
const sha256 = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const source = read('site/assets/js/intro.js');
const previous = archived('site/assets/js/intro.js');
const published = archived('published-intro-reference.js');
const helper = read('site/assets/js/intro-khumbu.js');
const reports = [];

// Delimiter matching skips strings and comments, so comments cannot truncate a body.
function endOfBlock(text, start, open = '{', close = '}') {
  assert.equal(text[start], open);
  let depth = 1;
  for (let i = start + 1; i < text.length; i++) {
    const c = text[i], next = text[i + 1];
    if (c === '/' && next === '/') { i = text.indexOf('\n', i); if (i < 0) break; continue; }
    if (c === '/' && next === '*') { i = text.indexOf('*/', i + 2); assert(i >= 0); i++; continue; }
    if (c === "'" || c === '"' || c === '`') {
      const quote = c;
      while (++i < text.length) { if (text[i] === '\\') i++; else if (text[i] === quote) break; }
      continue;
    }
    if (c === open) depth++;
    if (c === close && --depth === 0) return i + 1;
    // Closing characters of other kinds must not affect this depth.
    if (c !== close) depth += 0;
  }
  throw new Error('Unclosed block at ' + start);
}

function constant(text, name) {
  const re = new RegExp('\\bconst\\s+' + name + '\\s*=\\s*', 'g');
  const match = re.exec(text);
  assert(match, 'Missing constant ' + name);
  const start = match.index, valueStart = re.lastIndex, c = text[valueStart];
  if (c === '`') {
    let i = valueStart + 1;
    for (; i < text.length; i++) { if (text[i] === '\\') i++; else if (text[i] === '`') break; }
    assert.equal(text[i + 1], ';');
    return text.slice(start, i + 2);
  }
  assert(c === '[' || c === '{', name + ' requires an array or object literal');
  const end = endOfBlock(text, valueStart, c, c === '[' ? ']' : '}');
  assert.equal(text[end], ';');
  return text.slice(start, end + 1);
}

function fn(text, name, glsl = false) {
  const match = new RegExp(glsl ? '\\b(?:vec[234]|float)\\s+' + name + '\\s*\\(' : '\\bfunction\\s+' + name + '\\s*\\(').exec(text);
  assert(match, 'Missing function ' + name);
  const start = text.indexOf('{', match.index);
  return text.slice(match.index, endOfBlock(text, start));
}

function storyBlock(text) {
  const start = text.indexOf('const WP =');
  assert(start >= 0, 'Scroll knots missing');
  const story = fn(text, 'story');
  return text.slice(start, text.indexOf(story) + story.length);
}

const manifest = JSON.parse(archived('manifest.json'));
assert(Object.keys(manifest).length > 50, 'Archive omitted packaged assets');
for (const [name, expected] of Object.entries(manifest)) {
  assert.match(expected, /^[0-9a-f]{64}$/);
  assert.equal(sha256(fs.readFileSync(path.join(archive, name))), expected, 'Archived file changed: ' + name);
}
reports.push(Object.keys(manifest).length + ' archived files verified byte for byte');

for (const name of ['khumbu.bin', 'khumbu.json']) {
  const relative = 'site/assets/mountain/' + name;
  assert.equal(sha256(fs.readFileSync(path.join(root, relative))), manifest[relative], 'Approved relief asset changed: ' + name);
}
assert.equal(read('site/assets/js/mountain-lab.js'), archived('site/assets/js/mountain-lab.js'), 'Approved lab viewer changed');
const meta = JSON.parse(read('site/assets/mountain/khumbu.json'));
const binary = fs.readFileSync(path.join(root, 'site/assets/mountain/khumbu.bin'));
assert.equal(meta.encoding, 'height7-normalxz-concavity-i16');
assert.equal(binary.length, meta.rows * meta.columns * 8, 'Relief record count mismatch');
for (const [axis, count] of [[meta.x, meta.columns], [meta.z, meta.rows]]) {
  assert.equal(axis.length, count);
  for (let i = 0; i < count; i++) { assert(Number.isFinite(axis[i])); if (i) assert(axis[i] > axis[i - 1]); }
}
reports.push('approved Ama Dablam mesh binary and metadata preserved');

for (const name of ['LOOKS', 'NOISE_FS', 'SNOW_FS']) {
  assert.equal(constant(source, name), constant(published, name), name + ' differs from published Git atmosphere');
}
assert.equal(fn(source, 'look'), fn(published, 'look'), 'Atmosphere interpolation changed');
for (const name of ['fogColor', 'fogAmount', 'clouds', 'aces']) {
  assert.equal(fn(source, name, true), fn(published, name, true), name + ' differs from published Git atmosphere');
}
const snowfallWithoutGust=constant(source,'SNOW_VS').replace('uniform vec2 uRes; uniform float uGust;','uniform vec2 uRes;').replace('vec3 wind = vec3(4.5 + uGust*22.0, -1.6-uGust*.8, 1.2+uGust*3.)','vec3 wind = vec3(4.5, -1.6, 1.2)');
assert.equal(snowfallWithoutGust,constant(published,'SNOW_VS'),'Only storm wind speed may change the snowfall shader');
reports.push('published fog, light keys, moving clouds and grain retained; snowfall gains controlled storm gust');

assert.notEqual(constant(source, 'KEYS'), constant(previous, 'KEYS'), 'Summit arrival needs its new camera path');
assert.equal(storyBlock(source), storyBlock(previous), 'Scroll timing changed');
for (const name of ['sampleKeys', 'catmull']) assert.equal(fn(source, name), fn(previous, name), 'Camera interpolation changed');
const withoutGroundSafety = body => body.replace(/^\s*if \(p <[^\n]*groundAt\([^\n]*\n/gm, '');

// Evaluate both camera functions with the same abstract face. This intentionally separates
// the authored animation from the new geometry's climber projection and ground clearance.
const mathStart = previous.indexOf('const clamp ='), mathEnd = previous.indexOf('// ---------------------------------------------------------------- the world');
const commonMath = previous.slice(mathStart, mathEnd);
function cameraModel(text) {
  const context = { Math };
  const declarations = `
    ${commonMath}
    const CLIMBER = [60, 563, -20], NF = V.norm([0,.45,1]), TX = [1,0,0], TY = V.cross(NF,TX);
    const at = (n,x,y,up=0) => V.add(V.add(V.add(CLIMBER,V.mul(NF,n)),V.add(V.mul(TX,x),V.mul(TY,y))),[0,up,0]);
    const LOOK = V.add(CLIMBER,[0,1.1,0]), SUMMIT=CLIMBER, DEBUG_CAM = null;
    const groundAt = () => -1e9;
    ${constant(text, 'KEYS')}
    ${fn(text, 'sampleKeys')}
    ${fn(text, 'catmull')}
    ${storyBlock(text)}
    ${fn(text, 'camera')}
    this.animation = { camera, story };
  `;
  vm.runInNewContext(declarations, context);
  return context.animation;
}
const a = cameraModel(previous), b = cameraModel(source);
let priorStory = -Infinity;
for (let i = 0; i <= 2000; i++) {
  const p = i / 2000;
  assert.equal(a.story(p), b.story(p));
  assert(b.story(p) >= priorStory, 'Scroll reverses near ' + p);
  priorStory = b.story(p);
  for (const time of [0, 17, 63]) {
    const next = b.camera(p, time);
    assert(next.fov >= 25 && next.fov <= 43, 'Invalid summit framing');
    assert(next.pos.every(Number.isFinite) && next.tgt.every(Number.isFinite) && Number.isFinite(next.fov));
  }
}
reports.push('same scroll timing; valid distant camera and idle drift at 6,003 samples');

const html = read('index.html');
assert(html.indexOf('site/assets/js/intro-khumbu.js') >= 0, 'Main site does not load the relief helper');
assert(html.indexOf('site/assets/js/intro-khumbu.js') < html.indexOf('site/assets/js/intro.js'), 'Relief helper must load before intro');
assert(source.includes('HCKhumbu.load('), 'Intro does not load the approved relief');
assert(source.includes('.register(SUMMIT'), 'Relief must register to the existing camera world');
assert(source.includes('.heightAt('), 'Camera/climber lack mesh clearance');
assert(source.includes('.upload('), 'Approved mesh is not uploaded');
assert(helper.includes('window.HCKhumbu'), 'Helper public API missing');
reports.push('main site is wired to the approved terrain helper');

function loadedModel(bytes = binary, ok = true) {
  const requests = [];
  const context = {
    window: {}, Float32Array, Uint32Array, DataView, Math,
    fetch: async url => {
      requests.push(url);
      return {
        ok,
        json: async () => structuredClone(meta),
        arrayBuffer: async () => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength),
      };
    },
  };
  vm.runInNewContext(helper, context);
  return { promise: context.window.HCKhumbu.load(), requests };
}
const loaded = loadedModel(), terrain = await loaded.promise;
assert.deepEqual(loaded.requests.sort(), ['site/assets/mountain/khumbu.bin', 'site/assets/mountain/khumbu.json']);
assert(terrain.data instanceof Float32Array);
assert.equal(terrain.data.length, meta.rows * meta.columns * 7);
// Every decoded vertex comes from the approved record. No new cone or cap may be appended.
for (let row = 0; row < meta.rows; row++) for (let col = 0; col < meta.columns; col++) {
  const k = row * meta.columns + col, o = k * 7, packed = k * 8;
  const expected = [meta.x[col], (binary.readUInt16LE(packed) / 7 - meta.datumMetres) / 1000, meta.z[row]];
  for (let j = 0; j < 3; j++) assert.equal(terrain.data[o + j], Math.fround(expected[j]), 'Decoded terrain position changed at ' + k);
  assert.equal(terrain.data[o + 3], Math.fround(binary.readInt16LE(packed + 2) / 32767));
  assert.equal(terrain.data[o + 5], Math.fround(binary.readInt16LE(packed + 4) / 32767));
  assert.equal(terrain.data[o + 6], Math.fround(binary.readInt16LE(packed + 6) / 32767));
  const normalLength = Math.hypot(...terrain.data.subarray(o + 3, o + 6));
  assert(Math.abs(normalLength - 1) < .00005, 'Invalid normal at ' + k);
}
await assert.rejects(loadedModel(binary.subarray(0, binary.length - 8)).promise, /Invalid mountain data/, 'Truncated relief should fail before upload');
await assert.rejects(loadedModel(binary, false).promise, /unavailable/, 'Missing relief should fail before upload');

const summit = [80, 1204.715290310, -344.621880639];
terrain.register(summit);
const transform = (m, p) => [0, 1, 2].map(row => m[row] * p[0] + m[4 + row] * p[1] + m[8 + row] * p[2] + m[12 + row]);
const registeredPeak = transform(terrain.transform, terrain.peak);
assert(Math.hypot(...registeredPeak.map((v, i) => v - summit[i])) < .001, 'The summit does not register to the existing animation');
let largestHeightError = 0;
// Use varied interior and edge vertices on the nonuniform grid. CPU collision queries
// must return the same world height as the model matrix sent to the terrain shader.
for (let i = 0; i < 512; i++) {
  const row = (i * 173) % meta.rows, col = (i * 269) % meta.columns, o = (row * meta.columns + col) * 7;
  const world = transform(terrain.transform, terrain.data.subarray(o, o + 3));
  const height = terrain.heightAt(world[0], world[2]);
  assert(Number.isFinite(height));
  largestHeightError = Math.max(largestHeightError, Math.abs(height - world[1]));
}
assert(largestHeightError < .15, 'Summit snow relief exceeds its bounded displacement: ' + largestHeightError);
const detailed = terrain.summitMesh(false);
assert(detailed.refinedCells > 0 && detailed.refinedCells < 1000);
for(let i=terrain.data.length/7;i<detailed.vertices.length/7;i+=173){
  const o=i*7,world=transform(terrain.transform,detailed.vertices.subarray(o,o+3));
  assert(Math.abs(terrain.heightAt(world[0],world[2])-world[1])<.001,'Detailed mesh/collision disagree');
  assert(Math.abs(Math.hypot(...detailed.vertices.subarray(o+3,o+6))-1)<.00001);
}
assert(detailed.indices.length/3 < 1250000,'Summit refinement exceeded desktop triangle budget');
reports.push(terrain.data.length / 7 + ' original vertices decoded; summit refined locally with matching collision heights');

function fakeGL() {
  const constants = new Map(), buffers = [], uniforms = [], draws = [], shaderPairs = [];
  let nextObject = 0;
  const gl = new Proxy({
    bufferData: (...args) => buffers.push(args),
    uniformMatrix4fv: (...args) => uniforms.push(['mat4', ...args]),
    uniformMatrix3fv: (...args) => uniforms.push(['mat3', ...args]),
    uniform3fv: (...args) => uniforms.push(['vec3', ...args]),
    drawElements: (...args) => draws.push(args),
    checkFramebufferStatus: () => gl.FRAMEBUFFER_COMPLETE,
  }, { get(obj, key) {
    if (key in obj) return obj[key];
    if (/^[A-Z_0-9]+$/.test(key)) { if (!constants.has(key)) constants.set(key, 2 ** constants.size); return constants.get(key); }
    if (String(key).startsWith('create')) return () => ({ id: ++nextObject });
    return () => {};
  } });
  const program = (vs, fs) => {
    shaderPairs.push([vs, fs]);
    return { p: {}, u: new Proxy({}, { get: (_, name) => String(name) }) };
  };
  return { gl, buffers, uniforms, draws, shaderPairs, program };
}
for (const coarse of [false, true]) {
  const state = fakeGL(), renderer = terrain.upload(state.gl, state.program, coarse, {});
  const vertexBuffer = state.buffers.find(args => args[0] === state.gl.ARRAY_BUFFER);
  assert.deepEqual(vertexBuffer[1].subarray(0,terrain.data.length),terrain.data,'Approved source vertices must remain intact');
  const indices = state.buffers.find(args => args[0] === state.gl.ELEMENT_ARRAY_BUFFER)[1];
  assert(indices instanceof Uint32Array);
  const expectedTriangles = Math.ceil((meta.rows - 1) / (coarse ? 2 : 1)) * Math.ceil((meta.columns - 1) / (coarse ? 2 : 1)) * 2;
  assert.equal(renderer.count, expectedTriangles+renderer.refinedCells*2*((coarse?8:12)**2-1));
  assert.equal(indices.length, renderer.count * 3);
  for (const index of indices) assert(index < vertexBuffer[1].length/7);
  assert(renderer.colorTex && renderer.distanceTex);
  const vp = new Float32Array([1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]);
  const lighting = { sunDir: [.8,.42,.05], sun: [2.4,2.25,2.05], fog: [.15,.165,.185] };
  renderer.render(vp, [40,640,3800], lighting, 640,360);
  assert.equal(state.draws.length, 2, 'First frame needs shadow and terrain draws');
  renderer.render(vp, [40,640,3800], lighting, 640,360);
  assert.equal(state.draws.length, 3, 'Unchanged sunlight should reuse the shadow map');
  const matrices = state.uniforms.filter(([kind, name]) => kind === 'mat4' && name === 'model');
  assert(matrices.length >= 3);
  for (const entry of matrices) assert.equal(entry[3], terrain.transform, 'Shadow/terrain transforms diverged');
  for (const [name, values] of [['sun',lighting.sunDir], ['sunCol',lighting.sun], ['fogCol',lighting.fog]]) {
    assert(state.uniforms.some(([kind, uniform, input]) => kind === 'vec3' && uniform === name && input === values), 'Published lighting input missing: ' + name);
  }
}
reports.push('desktop/mobile mesh indices, world transforms, atmosphere uniforms and shadow reuse verified');

// The offscreen target needs its own multisampling: canvas antialiasing does
// not cover MRT textures. Resolve both color and encoded distance on each frame.
for (const coarse of [false, true]) {
  const state = fakeGL(), resolves = [];
  state.gl.getParameter = key => key === state.gl.MAX_SAMPLES ? 4 : 0;
  state.gl.blitFramebuffer = (...args) => resolves.push(args);
  const renderer = terrain.upload(state.gl, state.program, coarse, {});
  assert.equal(renderer.samples, coarse ? 2 : 4);
  const vp = new Float32Array([1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]);
  const light = {sunDir:[.8,.42,.05],sun:[2.4,2.25,2.05],fog:[.15,.165,.185]};
  renderer.render(vp,[40,640,3800],light,640,360);
  assert.equal(resolves.length,2,'Both terrain outputs need an MSAA resolve');
  renderer.render(vp,[40,640,3800],light,640,360);
  assert.equal(state.draws.length,3,'Idle camera must reuse the fixed light shadow');
  const changed = {...light,sunDir:[.8005,.42,.05]};
  renderer.render(vp,[40,640,3800],changed,640,360);
  assert.equal(state.draws.length,5,'Small light movement must update shadows without the old visible jump');
  assert.equal(resolves.length,6);
  renderer.render(vp,[40,640,3800],changed,800,450);
  assert.equal(resolves.length,8,'Resized targets must still resolve both outputs');
}
reports.push('2x/4x offscreen MSAA, both resolved outputs and continuous small sunlight changes verified');

// A 5 m separation at 10 km was less than one depth-buffer level with the old
// 10 cm near plane. Keep distant rock surfaces distinguishable without moving the camera.
function depthLevels(near, distance) {
  const far=20000;
  return (far/(far-near)-far*near/((far-near)*distance))*((1<<24)-1);
}
const oldSeparation=depthLevels(.1,10005)-depthLevels(.1,10000);
const newSeparation=depthLevels(3,10005)-depthLevels(3,10000);
assert(oldSeparation<1 && newSeparation>1);
assert(newSeparation/oldSeparation>29);
reports.push('distant terrain depth precision improved by 30x; original near-camera snow projection kept');


const actualContext = { model: terrain, params: new URLSearchParams(''), Math };
const actualMath = source.slice(source.indexOf('const clamp ='), source.indexOf('// ---------------------------------------------------------------- shaders'));
vm.runInNewContext(actualMath + '\nthis.actual = { camera, story, KEYS, TEAM, V, CLIMBER, NF, SUMMIT };', actualContext);
const actual = actualContext.actual;
assert(actual.TEAM.every(p => p === actual.CLIMBER), 'Only one summit actor may be positioned');
assert(!html.includes('intro-summit-flag') && !html.includes('intro-logo-flight'),'This variant must show only the mountain and storm');
assert(html.includes('intro-end-lockup'),'Final brand card missing');
const climberClearances = actual.TEAM.map((p, i) => {
  assert(p.every(Number.isFinite), 'Climber position is invalid: ' + i);
  return p[1] - terrain.heightAt(p[0], p[2]);
});
const cameraDiagnostics = { closest: { clearance: Infinity }, nearestSummitDistance: Infinity, maxCrossTrack: 0, maxHeightDeviation: 0, maxHeadingStep: { degrees: 0 }, maxBoundaryJump: { metres: 0 } };
for (const time of [0, 17, 63]) for (let i = 0; i <= 1880; i++) {
  const p = i / 2000, pose = actual.camera(p, time);
  assert(pose.pos.every(Number.isFinite) && pose.tgt.every(Number.isFinite) && Number.isFinite(pose.fov));
  cameraDiagnostics.nearestSummitDistance = Math.min(cameraDiagnostics.nearestSummitDistance, Math.hypot(...actual.V.sub(pose.pos, actual.SUMMIT)));
  cameraDiagnostics.maxCrossTrack = Math.max(cameraDiagnostics.maxCrossTrack, Math.abs(pose.pos[0]-40));
  cameraDiagnostics.maxHeightDeviation = Math.max(cameraDiagnostics.maxHeightDeviation, Math.abs(pose.pos[1]-740));
  assert.equal(pose.fov,42,'The approach must not add an optical zoom');
  const clearance = pose.pos[1] - terrain.heightAt(pose.pos[0], pose.pos[2]);
  if (clearance < cameraDiagnostics.closest.clearance) cameraDiagnostics.closest = { clearance, p, time, position: [...pose.pos] };
  const next = actual.camera(Math.min(.94, p + .0005), time);
  assert(next.pos[2] <= pose.pos[2]+.00001,'Camera reverses along the approach');
  const d0 = actual.V.norm(actual.V.sub(pose.tgt, pose.pos)), d1 = actual.V.norm(actual.V.sub(next.tgt, next.pos));
  const degrees = Math.acos(Math.min(1, Math.max(-1, actual.V.dot(d0, d1)))) * 180 / Math.PI;
  if (degrees > cameraDiagnostics.maxHeadingStep.degrees) cameraDiagnostics.maxHeadingStep = { degrees, p, time };
}
for (const boundary of [...actual.KEYS.map(k => k[0]), .7, .73]) {
  if (boundary <= 0 || boundary >= .94) continue;
  for (const time of [0, 17, 63]) {
    const before = actual.camera(boundary - .0000001, time), after = actual.camera(boundary + .0000001, time);
    const metres = Math.hypot(...actual.V.sub(after.pos, before.pos));
    if (metres > cameraDiagnostics.maxBoundaryJump.metres) cameraDiagnostics.maxBoundaryJump = { metres, p: boundary, time };
  }
}
console.log('Geometry diagnostics: ' + JSON.stringify({ climberClearances, camera: cameraDiagnostics }));
for (let i = 0; i < climberClearances.length; i++) {
  assert(Math.abs(climberClearances[i] - .04) < .001, 'Climber ' + i + ' does not touch the approved terrain: ' + climberClearances[i] + ' m');
}
assert(cameraDiagnostics.closest.clearance > 0, 'Camera enters terrain: ' + JSON.stringify(cameraDiagnostics.closest));
assert(cameraDiagnostics.nearestSummitDistance > 2000,'Whiteout must occur well away from the summit');
assert(cameraDiagnostics.maxCrossTrack < 2,'Camera strays sideways from the straight route');
assert(cameraDiagnostics.maxHeightDeviation < 1,'Camera climbs instead of approaching level');
assert(cameraDiagnostics.maxBoundaryJump.metres < .05, 'Camera jumps at a safety boundary: ' + JSON.stringify(cameraDiagnostics.maxBoundaryJump));
assert(cameraDiagnostics.maxHeadingStep.degrees < 2, 'Camera heading jumps: ' + JSON.stringify(cameraDiagnostics.maxHeadingStep));
const held=actual.camera(.90,0);
for(const p of [.92,.95,.98,1]) for(const time of [0,17,63]) assert.deepEqual(actual.camera(p,time),held,'Final movement must be removed');
assert(source.includes('stage.dataset.whiteout = storm(p).bank.toFixed(4)'),'Whiteout transition missing');
const stormContext={Math};vm.runInNewContext(commonMath+'\n'+fn(source,'storm')+'\nthis.storm=storm;',stormContext);
let lastBank=-1,lastPaper=-1;
for(let i=0;i<=1000;i++){const w=stormContext.storm(i/1000);for(const v of Object.values(w))assert(v>=0&&v<=1);assert(w.bank>=lastBank&&w.paper>=lastPaper);lastBank=w.bank;lastPaper=w.paper;}
assert.equal(stormContext.storm(.64).bank,0);assert.equal(stormContext.storm(.856).bank,1);assert.equal(stormContext.storm(.98).gust,0);assert.equal(stormContext.storm(.98).paper,1);
assert(stormContext.storm(.84).gust>.99,'Storm peak should precede the title reveal');
const flagArchive=path.join(root,'archive/intro-summit-flag-morph-2026-10-02');
const flagManifest=JSON.parse(fs.readFileSync(path.join(flagArchive,'manifest.json'),'utf8'));
for(const [name,hash] of Object.entries(flagManifest))assert.equal(sha256(fs.readFileSync(path.join(flagArchive,name))),hash,'Saved flag version changed: '+name);
assert(fs.readFileSync(path.join(flagArchive,'index.html'),'utf8').includes('intro-summit-flag'));
reports.push(Object.keys(flagManifest).length+' files of the previous flag/morph version retained byte for byte');
reports.push('camera stays clear and settles during the storm; whiteout grows monotonically and wind ends before the logo');

console.log('PASS: Khumbu integration contracts');
for (const report of reports) console.log('  ' + report);
