// Async intro lifecycle regressions. Asset/geometry contracts are checked separately
// by check_khumbu_integration.mjs; real shader compilation still needs WebGL2.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const source = fs.readFileSync(new URL('../assets/js/intro.js', import.meta.url), 'utf8');
const classes = () => ({ values: new Set(), add(...xs) { xs.forEach(x => this.values.add(x)); }, toggle(x, on) { if (on) this.values.add(x); else this.values.delete(x); } });

async function run({ reduced = false, seen = false, blocked = false, webgl = true, query = '', nav = 'navigate', deferred = false, loadFails = false, entry = 'mountaineering' } = {}) {
  const events = new Map(), rafs = new Map(), images = [], errors = [];
  let id = 0, tick = 0, allocations = 0, releases = 0, removals = 0, draws = 0, loads = 0;
  let completeLoad;
  const modelStub = { heightAt: () => -1e9, register() {}, upload: () => ({ render() {}, colorTex: {}, distanceTex: {}, count: 941064 }) };
  const pendingLoad = new Promise(resolve => { completeLoad = () => resolve(modelStub); });
  const node = () => ({ dataset: {}, classList: classes(), style: { setProperty() {} }, textContent: '', appendChild() {}, getBoundingClientRect() { return {left:0,top:0,width:210,height:154}; }, querySelector() { return node(); }, focus() {} });
  const section = node(), stage = node(), canvas = node(), root = node(), skip = node(), sound = node();
  root.dataset.entry = entry;
  stage.offsetHeight = stage.clientHeight = 900; stage.clientWidth = 1440;
  canvas.width = canvas.height = 1;
  canvas.remove = () => { removals++; };
  const constants = new Map();
  const gl = new Proxy({
    getShaderParameter: () => true,
    getProgramParameter: (_, key) => key === constants.get('LINK_STATUS'),
    getExtension: () => ({ loseContext: () => { releases++; } }),
    drawArrays: () => { draws++; },
    drawArraysInstanced: () => { draws++; },
  }, { get(obj, key) {
    if (key in obj) return obj[key];
    if (/^[A-Z_0-9]+$/.test(key)) { if (!constants.has(key)) constants.set(key, constants.size + 1); return constants.get(key); }
    return () => ({});
  } });
  canvas.getContext = () => { allocations++; return webgl ? gl : null; };
  skip.addEventListener = (name, fn) => events.set('skip:' + name, fn);
  skip.removeEventListener = (name, fn) => { if (events.get('skip:' + name) === fn) events.delete('skip:' + name); };
  sound.addEventListener = (name, fn) => events.set('sound:' + name, fn);
  sound.getAttribute = () => 'false';
  const nodes = { '.intro-stage': stage, canvas, '.intro-skip': skip, '.intro-end h2, .intro-end': node(), '.intro-sound': sound };
  section.querySelector = selector => nodes[selector] ?? node();
  section.querySelectorAll = () => [0, .18, .49, .73, .93].map(p => ({ ...node(), dataset: { chapter: String(p) } }));
  Object.defineProperty(section, 'offsetHeight', { get: () => section.classList.values.has('is-done') ? 900 : 5400 });
  const context = {
    Image: class { set src(path) { images.push(path); } }, console: { ...console, error: (...args) => errors.push(args) }, URLSearchParams,
    location: { search: query },
    document: { createElement: () => node(), documentElement: root, hidden: false, getElementById: () => section, addEventListener: (name, fn) => events.set(name, fn) },
    history: { scrollRestoration: 'auto' },
    innerWidth: 1440, innerHeight: 900, devicePixelRatio: 1, scrollY: 0,
    performance: { now: () => 0, getEntriesByType: () => [{ type: nav }] },
    matchMedia: name => ({ matches: name.includes('reduced-motion') ? reduced : false }),
    sessionStorage: {
      getItem() { if (blocked) throw Error('blocked'); return seen ? 'seen' : null; },
      setItem() { if (blocked) throw Error('blocked'); },
    },
    scrollTo: (a, b) => { context.scrollY = typeof a === 'object' ? a.top : b; },
    requestAnimationFrame: fn => { const key = ++id; rafs.set(key, fn); return key; },
    cancelAnimationFrame: key => rafs.delete(key),
    IntersectionObserver: class { observe() {} },
    setTimeout: fn => fn(), window: { HCKhumbu: { load(base) {
      assert.equal(base, 'site/assets/mountain/');
      loads++;
      return loadFails ? Promise.reject(new Error('Asset unavailable')) : deferred ? pendingLoad : Promise.resolve(modelStub);
    } } },
  };
  section.getBoundingClientRect = () => ({ top: -context.scrollY });
  const ready = vm.runInNewContext(source, context);
  if (!deferred) await ready;
  return {
    context, section, root, events, rafs, images, errors, ready, completeLoad,
    counts: () => ({ allocations, releases, removals, draws, loads }),
    advance(n) { for (let i = 0; i < n; i++) { const next = [...rafs.values()]; rafs.clear(); next.forEach(fn => fn(++tick * 1000 / 60)); } },
  };
}

const chooser = await run({ entry: 'choose', query: '?intro' });
assert.equal(chooser.counts().loads, 0, 'The entrance must not fetch the mountain');
assert.equal(chooser.counts().allocations, 0, 'The entrance must not allocate WebGL');
assert.equal(chooser.rafs.size, 0, 'The mountain animation must wait for the blue choice');
assert(!chooser.root.classList.values.has('intro-complete'), 'The entrance must not finish the intro');

for (const options of [{ reduced: true }, { seen: true }]) {
  const r = await run(options);
  assert.equal(r.counts().allocations, 0);
  assert.equal(r.counts().loads, 0, 'Completed or reduced-motion intro must not fetch terrain');
  assert.equal(r.rafs.size, 0);
  assert(r.section.classList.values.has('is-done'));
  assert(r.root.classList.values.has('intro-complete'));
}
// Skip must work during a slow asset load and prevent late WebGL allocation.
let r = await run({ deferred: true });
assert.equal(r.counts().loads, 1);
assert.equal(r.counts().allocations, 0);
assert(r.events.has('skip:click'), 'Skip was unavailable while relief loaded');
r.events.get('skip:click')({ preventDefault() {} });
assert(r.section.classList.values.has('is-done'));
assert(r.root.classList.values.has('intro-complete'));
r.completeLoad();
await r.ready;
assert.equal(r.counts().allocations, 0, 'A skipped intro allocated a late WebGL renderer');
assert.equal(r.rafs.size, 0);

// An unavailable model leaves the usable title card and allocates no graphics.
r = await run({ loadFails: true });
assert.equal(r.counts().loads, 1);
assert.equal(r.counts().allocations, 0);
assert.equal(r.rafs.size, 0);
assert(r.section.classList.values.has('is-done'));
assert(r.errors.some(args => args[0] === 'Mountain intro unavailable'));

r = await run({ webgl: false });
assert.equal(r.counts().allocations, 1);
assert.equal(r.rafs.size, 0);
assert(r.section.classList.values.has('is-done'));
assert(r.root.classList.values.has('no-webgl'));

// Blocked storage cannot stop playback; skip releases the renderer exactly once.
r = await run({ blocked: true });
assert.equal(r.counts().allocations, 1);
r.events.get('skip:click')({ preventDefault() {} });
assert(r.section.classList.values.has('is-done'));
assert.equal(r.context.scrollY, 0);
assert.equal(r.counts().releases, 1);
assert.equal(r.counts().removals, 1);
assert.equal(r.rafs.size, 0);
r.events.get('skip:click')({ preventDefault() {} });
assert.equal(r.counts().releases, 1);

// A completed scroll cannot restart the old WebGL canvas when the page scrolls back.
r = await run();
r.context.scrollY = 4320;
r.advance(180);
assert(r.section.classList.values.has('is-done'));
assert.equal(r.counts().releases, 1);
const stoppedAt = r.counts().draws;
r.context.scrollY = 0;
r.advance(10);
assert.equal(r.counts().draws, stoppedAt);
assert.equal(r.rafs.size, 0);

for (const options of [{ seen: true, nav: 'reload' }, { seen: true, query: '?intro' }]) {
  r = await run(options);
  assert.equal(r.counts().allocations, 1);
  assert(r.rafs.size > 0);
}
for (const query of ['?p=invalid', '?p=Infinity', '?p=NaN']) {
  r = await run({ query });
  r.advance(2);
  assert(Number.isFinite(r.context.window.__intro.p), query + ' produced non-finite progress');
  r.events.get('skip:click')({ preventDefault() {} });
  assert(r.section.classList.values.has('is-done'), query + ' blocked completion');
}
for (const [query, expected] of [['?p=-3', 0], ['?p=3', 1]]) {
  r = await run({ query });
  r.advance(2);
  assert.equal(r.context.window.__intro.p, expected);
}

// The material's runtime URL must point to a packaged WebP.
r = await run({ query: '?p=0.5' });
const rockSrc = r.images.find(src => src.endsWith('/intro-kebnekaise-rock.webp'));
assert(rockSrc, 'rock albedo was not requested');
const rock = fs.readFileSync(new URL('../../' + rockSrc, import.meta.url));
assert(rock.length > 100_000);
assert.equal(rock.toString('ascii', 0, 4), 'RIFF');
assert.equal(rock.toString('ascii', 8, 12), 'WEBP');

r.advance(2);
const canvas = r.context.document.getElementById('intro').querySelector('canvas');
assert.equal(canvas.dataset.model, 'khumbu-approved');
assert.equal(canvas.dataset.atmosphere, '595da573f2d1ac9b3bc489cc05bb9d5cb142c063');
assert.equal(canvas.dataset.triangles, 941064);
console.log('PASS: entrance waits without mountain fetch/WebGL, async loading/skip, load failure, reduced/seen zero-fetch fallback, no-WebGL fallback, teardown, one-shot completion, replay, debug values and packaged rock.');
