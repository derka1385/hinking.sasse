// Contour layers: marching squares over a real heightmap, redrawn as the page scrolls.
// Scrolling moves the contour interval through the terrain, so the lines migrate as if the
// water table were rising; near the pointer they part by a few pixels. Canvas 2D, no library.
(() => {
const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
const root = document.body.dataset.root || '';
const LEVELS = 30;

class Layer {
  constructor(canvas) {
    this.c = canvas;
    this.ctx = canvas.getContext('2d');
    this.alpha = parseFloat(canvas.dataset.alpha || '0.12');
    this.flow = canvas.dataset.flow || 'scroll';
    this.offset = Math.random();
    this.mouse = { x: -1e4, y: -1e4, tx: -1e4, ty: -1e4 };
    this.visible = false;
    this.dirty = true;
    HC.terrain(`${root}site/assets/terrain/${canvas.dataset.contours}.png`).then((t) => { this.t = t; this.resize(); });
    new IntersectionObserver(([e]) => { this.visible = e.isIntersecting; if (this.visible) HC.wake(); }).observe(canvas);
    new ResizeObserver(() => this.t && this.resize()).observe(canvas);
    canvas.parentElement.addEventListener('pointermove', (e) => {
      const r = canvas.getBoundingClientRect();
      this.mouse.tx = e.clientX - r.left; this.mouse.ty = e.clientY - r.top; this.dirty = true; HC.wake();
    }, { passive: true });
    canvas.parentElement.addEventListener('pointerleave', () => { this.mouse.tx = -1e4; this.mouse.ty = -1e4; this.dirty = true; });
  }

  resize() {
    const r = this.c.getBoundingClientRect();
    if (!r.width || !r.height) return;
    const dpr = Math.min(devicePixelRatio || 1, 2);
    this.c.width = Math.round(r.width * dpr); this.c.height = Math.round(r.height * dpr);
    this.w = r.width; this.h = r.height; this.dpr = dpr;
    // a grid of about one cell every 7 px, sampled from the terrain with 'cover' framing
    const cols = this.cols = Math.min(240, Math.round(r.width / 7)), rows = this.rows = Math.min(200, Math.round(r.height / 7));
    const { w: tw, h: th, data } = this.t;
    const s = Math.max(cols / tw, rows / th);
    const ox = (tw - cols / s) / 2, oy = (th - rows / s) / 2;
    const G = this.g = new Float32Array((cols + 1) * (rows + 1));
    for (let j = 0; j <= rows; j++) for (let i = 0; i <= cols; i++) {
      const x = Math.min(tw - 1.001, ox + i / s), y = Math.min(th - 1.001, oy + j / s);
      const x0 = x | 0, y0 = y | 0, fx = x - x0, fy = y - y0, k = y0 * tw + x0;
      G[j * (cols + 1) + i] = (data[k] * (1 - fx) + data[k + 1] * fx) * (1 - fy) + (data[k + tw] * (1 - fx) + data[k + tw + 1] * fx) * fy;
    }
    const col = getComputedStyle(this.c).color.match(/[\d.]+/g) || [29, 29, 27];
    this.rgb = col.slice(0, 3).join(',');
    this.dirty = true;
    HC.wake();
  }

  frame(time, scrollP, vel) {
    if (!this.visible || !this.g) return false;
    const m = this.mouse;
    m.x += (m.tx - m.x) * 0.12; m.y += (m.ty - m.y) * 0.12;
    const moving = Math.abs(m.tx - m.x) > 0.5 || Math.abs(m.ty - m.y) > 0.5;
    const flow = this.flow === 'scroll' ? scrollP * 0.5 : 0;
    const drift = reduced ? 0 : time * 0.0035;
    const off = (this.offset + flow + drift) % 1;
    const stretch = 1 + Math.min(Math.abs(vel) * 0.00004, 0.04);        // a fast scroll stretches the lines a hair
    if (!this.dirty && !moving && Math.abs(off - (this.lastOff ?? -1)) < 0.00025 && stretch === this.lastStretch) return false;
    this.lastOff = off; this.lastStretch = stretch; this.dirty = false;
    this.draw(off, stretch);
    return true;
  }

  draw(off, stretch) {
    const { ctx, cols, rows, g, dpr, w, h, mouse } = this;
    const cw = w / cols, ch = h / rows * stretch, step = 1 / LEVELS;
    const R = 120, R2 = R * R;
    ctx.setTransform(dpr, 0, 0, dpr, 0, -(h * (stretch - 1) / 2) * dpr);
    ctx.clearRect(0, h * (stretch - 1) / 2 - 1, w, h * stretch + 2);
    const minor = new Path2D(), major = new Path2D();
    const px = (x, y, path, move) => {
      const dx = x - mouse.x, dy = y - mouse.y, d2 = dx * dx + dy * dy;
      if (d2 < R2) { const f = (1 - d2 / R2) ** 2 * 7 / (Math.sqrt(d2) + 1); x += dx * f; y += dy * f; }
      move ? path.moveTo(x, y) : path.lineTo(x, y);
    };
    const W1 = cols + 1;
    for (let j = 0; j < rows; j++) {
      for (let i = 0; i < cols; i++) {
        const a = g[j * W1 + i], b = g[j * W1 + i + 1], c = g[(j + 1) * W1 + i + 1], d = g[(j + 1) * W1 + i];
        const lo = Math.min(a, b, c, d), hi = Math.max(a, b, c, d);
        for (let k = Math.ceil((lo - off) / step); k <= Math.floor((hi - off) / step); k++) {
          const L = k * step + off;
          const idx = (a > L ? 8 : 0) | (b > L ? 4 : 0) | (c > L ? 2 : 0) | (d > L ? 1 : 0);
          if (idx === 0 || idx === 15) continue;
          const x = i * cw, y = j * ch;
          const top = [x + cw * (L - a) / (b - a), y], right = [x + cw, y + ch * (L - b) / (c - b)];
          const bot = [x + cw * (L - d) / (c - d), y + ch], left = [x, y + ch * (L - a) / (d - a)];
          const path = ((k % 5) + 5) % 5 === 0 ? major : minor;
          const seg = (p, q) => { px(p[0], p[1], path, true); px(q[0], q[1], path, false); };
          switch (idx) {
            case 1: case 14: seg(left, bot); break;
            case 2: case 13: seg(bot, right); break;
            case 3: case 12: seg(left, right); break;
            case 4: case 11: seg(top, right); break;
            case 5: seg(left, top); seg(bot, right); break;
            case 6: case 9: seg(top, bot); break;
            case 7: case 8: seg(left, top); break;
            case 10: seg(left, bot); seg(top, right); break;
          }
        }
      }
    }
    ctx.lineWidth = 0.6; ctx.strokeStyle = `rgba(${this.rgb},${this.alpha})`; ctx.stroke(minor);
    ctx.lineWidth = 0.9; ctx.strokeStyle = `rgba(${this.rgb},${Math.min(1, this.alpha * 2.2)})`; ctx.stroke(major);
  }
}

const layers = [...document.querySelectorAll('canvas[data-contours]')].map((c) => new Layer(c));
HC.onFrame((time, _, vel) => {
  let busy = false;
  for (const l of layers) {
    const host = l.c.closest('[data-scene], section, header, nav') || document.body;
    busy = l.frame(time, HC.progress(host), vel) || busy;
  }
  return busy || (!reduced && layers.some((l) => l.visible));
});
})();
