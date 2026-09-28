// Hiking Club — the motion system every page shares, and the interactions built on it.
// One requestAnimationFrame loop for the whole site, awake only while something moves.
// Scenes ([data-scene]) get their scroll progress as --p; other scripts read it through HC.
(() => {
const root = document.documentElement;
const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
const coarse = matchMedia('(pointer: coarse)').matches;
if (reduced) root.classList.add('reduce');
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));

// ---------------------------------------------------------------- the loop
const cbs = [];
const visibleScenes = new Set();
let running = false, lastY = scrollY, lastT = performance.now(), vel = 0, frameNo = 0;
const pCache = new Map();

function progress(el) {
  if (!el) return 0;
  const hit = pCache.get(el);
  if (hit && hit[0] === frameNo) return hit[1];
  const r = el.getBoundingClientRect(), vh = innerHeight;
  // a pinned scene runs 0 → 1 while it is stuck to the viewport; anything else, while it crosses it
  const p = r.height > vh * 1.05 ? clamp(-r.top / (r.height - vh)) : clamp((vh - r.top) / (vh + r.height));
  pCache.set(el, [frameNo, p]);
  return p;
}

function tick(now) {
  running = false;
  frameNo++;
  const dt = Math.max(0.001, (now - lastT) / 1000); lastT = now;
  const y = scrollY, dy = y - lastY; lastY = y;
  vel += (Math.min(dt, 0.1) ? dy / dt - vel : 0) * 0.25;
  if (Math.abs(vel) < 2) vel = 0;
  for (const s of visibleScenes) s.style.setProperty('--p', progress(s).toFixed(4));
  let busy = parallax() || vel !== 0;
  for (const cb of cbs) busy = cb(now / 1000, y, vel) || busy;
  if (busy) wake();
}
function wake() { if (!running) { running = true; requestAnimationFrame(tick); } }
addEventListener('scroll', wake, { passive: true });
addEventListener('resize', wake);

const tcache = {};
window.HC = {
  onFrame(cb) { cbs.push(cb); wake(); },
  wake,
  progress,
  velocity: () => vel,
  // 16-bit heightmaps (R = high byte, G = low byte), shared by the contours and the relief
  terrain(src) {
    return (tcache[src] ||= new Promise((res, rej) => {
      const im = new Image();
      im.onload = () => {
        const c = document.createElement('canvas'); c.width = im.width; c.height = im.height;
        const x = c.getContext('2d', { willReadFrequently: true }); x.drawImage(im, 0, 0);
        const d = x.getImageData(0, 0, c.width, c.height).data, h = new Float32Array(c.width * c.height);
        for (let i = 0; i < h.length; i++) h[i] = (d[i * 4] * 256 + d[i * 4 + 1]) / 65535;
        res({ w: c.width, h: c.height, data: h });
      };
      im.onerror = rej; im.src = src;
    }));
  },
};

const sceneIO = new IntersectionObserver((es) => {
  for (const e of es) { if (e.isIntersecting) visibleScenes.add(e.target); else visibleScenes.delete(e.target); }
  wake();
}, { rootMargin: '10% 0px' });
document.querySelectorAll('[data-scene]').forEach((s) => sceneIO.observe(s));

// parallax that lags a little behind a fast scroll and settles when it slows: never on text
const para = [...document.querySelectorAll('[data-speed]')].map((el) => ({ el, speed: +el.dataset.speed, cur: 0, on: false }));
const paraIO = new IntersectionObserver((es) => { for (const e of es) { const p = para.find((q) => q.el === e.target); if (p) p.on = e.isIntersecting; } wake(); });
para.forEach((p) => paraIO.observe(p.el));
function parallax() {
  if (reduced) return false;
  let moving = false;
  for (const p of para) {
    if (!p.on) continue;
    const r = p.el.parentElement.getBoundingClientRect();
    const target = (r.top + r.height / 2 - innerHeight / 2) * -p.speed;
    p.cur += (target - p.cur) * 0.14;
    if (Math.abs(target - p.cur) > 0.3) moving = true;
    p.el.style.transform = `translate3d(0, ${p.cur.toFixed(2)}px, 0)`;
  }
  return moving;
}

// ---------------------------------------------------------------- reveals
for (const el of document.querySelectorAll('[data-lines]')) {
  const parts = el.innerHTML.split(/<br\s*\/?>/i);
  el.innerHTML = parts.map((h, i) => `<span class="line"><span style="--i:${i}">${h.trim()}</span></span>`).join('');
}
const seen = new IntersectionObserver((entries) => {
  let n = 0;
  for (const e of entries) {
    if (!e.isIntersecting) continue;
    e.target.style.setProperty('--i', n++);
    e.target.classList.add('is-in');
    seen.unobserve(e.target);
  }
}, { rootMargin: '0px 0px -8% 0px', threshold: 0.12 });
document.querySelectorAll('[data-reveal], [data-lines]').forEach((el) => seen.observe(el));

// ---------------------------------------------------------------- navigation
const nav = document.querySelector('[data-nav]');
const themeIO = new IntersectionObserver((entries) => {
  for (const e of entries) if (e.isIntersecting) nav.dataset.theme = e.target.dataset.theme || 'paper';
}, { rootMargin: '-32px 0px -94% 0px' });
document.querySelectorAll('main [data-theme], footer[data-theme], .intro').forEach((s) => themeIO.observe(s));
const toggle = nav.querySelector('.nav-toggle');
const setMenu = (open) => {
  nav.classList.toggle('is-open', open);
  root.classList.toggle('menu-open', open);
  toggle.setAttribute('aria-expanded', String(open));
  toggle.firstElementChild.textContent = open ? 'Close' : 'Menu';
  if (open) HC.wake();
};
toggle.addEventListener('click', () => setMenu(!nav.classList.contains('is-open')));
nav.querySelectorAll('.nav-links a').forEach((a) => a.addEventListener('click', () => setMenu(false)));
addEventListener('keydown', (e) => { if (e.key === 'Escape') setMenu(false); });
const onScrollNav = () => nav.classList.toggle('is-scrolled', scrollY > 8);
addEventListener('scroll', onScrollNav, { passive: true }); onScrollNav();

// ---------------------------------------------------------------- 1,002 km north (home)
const north = document.querySelector('[data-north]');
if (north) {
  const path = north.querySelector('.scandi-route.is-focus');
  const len = path.getTotalLength();
  const svg = north.querySelector('.scandi-overlay');
  const head = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  head.setAttribute('class', 'scandi-head'); head.innerHTML = '<circle r="11"/><circle r="3.5"/>';
  svg.append(head);
  const kmEl = document.querySelector('[data-north-km]'), latEl = document.querySelector('[data-north-lat]');
  const KM = +north.dataset.km, L0 = +north.dataset.lat0, L1 = +north.dataset.lat1;
  const scene = north.closest('[data-scene]');
  let last = -1;
  HC.onFrame(() => {
    if (!visibleScenes.has(scene)) return false;
    const d = reduced ? 1 : clamp((progress(scene) - 0.12) / 0.7);
    if (Math.abs(d - last) < 0.0005) return false;
    last = d;
    path.style.strokeDashoffset = (1 - d).toFixed(4);
    const pt = path.getPointAtLength(d * len);
    head.setAttribute('transform', `translate(${pt.x.toFixed(1)} ${pt.y.toFixed(1)})`);
    kmEl.textContent = Math.round(d * KM).toLocaleString('en-US');
    latEl.textContent = `${(L0 + (L1 - L0) * d).toFixed(2)}° N`;
    north.classList.toggle('is-arrived', d > 0.995);
    return false;
  });
}

// ---------------------------------------------------------------- expedition route (dossier)
const route = document.querySelector('[data-route-svg]');
if (route) {
  const line = route.querySelector('.route-line'), len = line.getTotalLength();
  const head = route.querySelector('.route-head');
  const scene = route.closest('[data-scene]');
  const stages = [...document.querySelectorAll('.stage')];
  const prof = document.querySelector('.profile'), cover = prof?.querySelector('.profile-cover');
  const read = prof?.querySelector('[data-route-read]');
  const P = JSON.parse(prof?.dataset.profile || '[]'), KM = +(prof?.dataset.km || 0);
  const seg = line.cloneNode(); seg.setAttribute('class', 'route-seg'); route.insertBefore(seg, head);
  let last = -1, hover = -1;
  const show = (k) => {
    hover = k;
    stages.forEach((s, i) => s.classList.toggle('is-hover', i === k));
    route.querySelectorAll('.rt-stop').forEach((s) => s.classList.toggle('is-on', k >= 0 && (+s.dataset.stop === k || +s.dataset.stop === k + 1)));
    if (k < 0) { seg.style.opacity = 0; return; }
    const a = +stages[k].dataset.a, b = +stages[k].dataset.b;
    seg.style.strokeDasharray = `${(b - a).toFixed(4)} 2`; seg.style.strokeDashoffset = (-a).toFixed(4); seg.style.opacity = 1;
  };
  stages.forEach((s, k) => {
    s.tabIndex = 0;
    s.addEventListener('pointerenter', () => show(k)); s.addEventListener('pointerleave', () => show(-1));
    s.addEventListener('focus', () => show(k)); s.addEventListener('blur', () => show(-1));
  });
  HC.onFrame(() => {
    if (!visibleScenes.has(scene)) return false;
    const d = reduced ? 1 : clamp((progress(scene) - 0.05) / 0.85);
    if (Math.abs(d - last) < 0.0005) return false;
    last = d;
    line.style.strokeDashoffset = (1 - d).toFixed(4);
    const pt = line.getPointAtLength(d * len);
    head.setAttribute('transform', `translate(${pt.x.toFixed(1)} ${pt.y.toFixed(1)})`);
    if (cover) { cover.setAttribute('x', (d * 1000).toFixed(1)); cover.setAttribute('width', ((1 - d) * 1000).toFixed(1)); }
    if (read && P.length) read.textContent = `${(d * KM).toFixed(1)} km · +${P[Math.round(d * (P.length - 1))].toLocaleString('en-US')} m`;
    stages.forEach((s) => s.classList.toggle('is-on', d >= +s.dataset.a - 0.001 && d <= +s.dataset.b + 0.001));
    return false;
  });
}

// ---------------------------------------------------------------- archive: list / map, photographs out of coordinates
const aroot = document.querySelector('[data-view-root]');
if (aroot) {
  document.querySelectorAll('[data-view]').forEach((b) => b.addEventListener('click', () => {
    const go = () => {
      aroot.dataset.viewRoot = b.dataset.view;
      document.querySelectorAll('[data-view]').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    };
    document.startViewTransition && !reduced ? document.startViewTransition(go) : go();
  }));
  const amap = aroot.querySelector('.amap');
  const cards = Object.fromEntries([...aroot.querySelectorAll('[data-card]')].map((c) => [c.dataset.card, c]));
  const open = (no, pt) => {
    for (const [k, c] of Object.entries(cards)) c.classList.toggle('is-on', k === no);
    aroot.querySelectorAll('.scandi-pt').forEach((g) => g.classList.toggle('is-on', g.dataset.no === no));
    aroot.querySelectorAll('[data-hover]').forEach((a) => a.classList.toggle('is-on', a.dataset.hover === no));
    if (!no || !pt) return;
    const m = amap.getBoundingClientRect(), r = pt.getBoundingClientRect(), c = cards[no];
    const x = r.left + r.width / 2 - m.left, y = r.top + r.height / 2 - m.top;
    c.style.setProperty('--x', `${x}px`); c.style.setProperty('--y', `${y}px`);
    c.classList.toggle('is-left', x > m.width * 0.55);
  };
  aroot.querySelectorAll('.scandi-pt').forEach((g) => {
    const no = g.dataset.no;
    g.addEventListener('pointerenter', () => open(no, g.querySelector('circle')));
    g.addEventListener('click', () => { location.href = cards[no].href; });
    g.style.cursor = 'pointer';
  });
  amap.addEventListener('pointerleave', () => open(null));
  aroot.querySelectorAll('[data-hover]').forEach((a) => {
    const g = aroot.querySelector(`.scandi-pt[data-no="${a.dataset.hover}"]`);
    const on = () => open(a.dataset.hover, g.querySelector('circle'));
    a.addEventListener('pointerenter', on); a.addEventListener('focus', on);
    a.addEventListener('pointerleave', () => open(null)); a.addEventListener('blur', () => open(null));
  });
}

// ---------------------------------------------------------------- snow for the Winter scene
const snowC = document.querySelector('canvas[data-snow]');
if (snowC && !reduced) {
  const x = snowC.getContext('2d');
  const flakes = Array.from({ length: coarse ? 70 : 160 }, () => ({ x: Math.random(), y: Math.random(), z: Math.random() }));
  let on = false;
  new IntersectionObserver(([e]) => { on = e.isIntersecting; if (on) wake(); }).observe(snowC);
  HC.onFrame((t) => {
    if (!on) return false;
    const w = snowC.clientWidth, h = snowC.clientHeight, dpr = Math.min(devicePixelRatio, 2);
    if (snowC.width !== Math.round(w * dpr)) { snowC.width = Math.round(w * dpr); snowC.height = Math.round(h * dpr); }
    x.setTransform(dpr, 0, 0, dpr, 0, 0); x.clearRect(0, 0, w, h);
    const cold = progress(snowC.closest('[data-scene]'));
    x.fillStyle = 'rgba(255,255,255,0.9)';
    for (const f of flakes) {
      f.y += 0.0006 + f.z * 0.0014 + vel * 0.0000015 * f.z; f.x += Math.sin(t * 0.6 + f.z * 20) * 0.00035 + 0.0002;
      if (f.y > 1) { f.y = 0; f.x = Math.random(); } if (f.x > 1) f.x = 0;
      x.globalAlpha = (0.25 + f.z * 0.6) * Math.min(1, cold * 3);
      x.beginPath(); x.arc(f.x * w, f.y * h, 0.6 + f.z * 1.8, 0, 6.283); x.fill();
    }
    return true;
  });
}

// ---------------------------------------------------------------- the rope (the club's three rules)
const ropeSvg = document.querySelector('svg[data-rope]');
if (ropeSvg) {
  const path = ropeSvg.querySelector('path'), host = ropeSvg.parentElement;
  const N = 36;
  let pts = [], on = false, w = 0, h = 0, seg = 0;
  const anchorX = () => w * (coarse ? 0.08 : 0.28);
  const layout = () => {
    w = host.clientWidth; h = host.clientHeight; seg = h / (N - 1);
    ropeSvg.setAttribute('viewBox', `0 0 ${w} ${h}`);
    pts = Array.from({ length: N }, (_, i) => ({ x: anchorX(), y: i * seg, px: anchorX(), py: i * seg }));
    wake();
  };
  new ResizeObserver(layout).observe(host);
  new IntersectionObserver(([e]) => { on = e.isIntersecting; if (on) wake(); }).observe(host);
  HC.onFrame(() => {
    if (!on || !pts.length) return false;
    // verlet: tied off at the top; a scroll pushes it sideways, it swings back and settles
    const push = reduced ? 0 : clamp(vel * 0.00035, -0.9, 0.9);   // a nudge, not a gust
    let energy = 0;
    for (let i = 1; i < N; i++) {
      const p = pts[i], vx = (p.x - p.px) * 0.9, vy = (p.y - p.py) * 0.9;
      p.px = p.x; p.py = p.y;
      p.x += vx + push * Math.sin((i / N) * Math.PI) * 0.6; p.y += vy + 0.35;
      energy += Math.abs(vx) + Math.abs(vy);
    }
    for (let k = 0; k < 6; k++) {
      pts[0].x = pts[0].px = anchorX(); pts[0].y = pts[0].py = 0;
      for (let i = 0; i < N - 1; i++) {
        const a = pts[i], b = pts[i + 1], dx = b.x - a.x, dy = b.y - a.y, dl = Math.hypot(dx, dy) || 1, f = (dl - seg) / dl / 2;
        if (i) { a.x += dx * f; a.y += dy * f; } b.x -= dx * f; b.y -= dy * f;
      }
    }
    let d = `M${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)}`;
    for (let i = 1; i < N - 1; i++) { const mx = (pts[i].x + pts[i + 1].x) / 2, my = (pts[i].y + pts[i + 1].y) / 2; d += ` Q${pts[i].x.toFixed(1)} ${pts[i].y.toFixed(1)} ${mx.toFixed(1)} ${my.toFixed(1)}`; }
    path.setAttribute('d', d);
    return energy > 0.05 || vel !== 0;
  });
}

// ---------------------------------------------------------------- join
const form = document.querySelector('.join-form');
if (form) {
  const trip = new URLSearchParams(location.search).get('trip');
  const box = form.querySelector('[name="trip"]');
  if (trip && box && box.value.includes(trip)) box.checked = true;
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const d = new FormData(form);
    const to = form.dataset.mailto;
    const body = [`Name: ${d.get('name')}`, `Email: ${d.get('email')}`, `Programme: ${d.get('programme')}`,
      `Experience: ${d.get('experience')}`, d.get('trip') ? `Register me for: ${d.get('trip')}` : ''].filter(Boolean).join('\n');
    location.href = `mailto:${to}?subject=${encodeURIComponent('Membership — ' + d.get('name'))}&body=${encodeURIComponent(body)}`;
    form.querySelector('.join-status').textContent = `Your mail app should open with everything filled in. If it does not, write to ${to}.`;
  });
}
wake();
})();
