// The editorial site after the ascent: reveals, navigation theme, disciplines, join form.
(() => {
const root = document.documentElement;
const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
if (reduced) root.classList.add('reduce');

// lines: each <br>-separated run of a heading rises out of its own mask
for (const el of document.querySelectorAll('[data-lines]')) {
  const parts = el.innerHTML.split(/<br\s*\/?>/i);
  el.innerHTML = parts.map((h, i) => `<span class="line"><span style="--i:${i}">${h.trim()}</span></span>`).join('');
}

// reveal once, staggering siblings that enter together
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

// the intro normally says when it is over; this covers a failed or skipped intro script
new IntersectionObserver(([e]) => { if (e.boundingClientRect.top < innerHeight) root.classList.add('intro-done'); })
  .observe(document.getElementById('manifesto'));

// navigation: takes the theme of the section under it, marks the current section
const nav = document.querySelector('[data-nav]');
const links = [...nav.querySelectorAll('.nav-links a')];
const themeIO = new IntersectionObserver((entries) => {
  for (const e of entries) if (e.isIntersecting) nav.dataset.theme = e.target.dataset.theme;
}, { rootMargin: '-32px 0px -94% 0px' });
document.querySelectorAll('main [data-theme], footer[data-theme]').forEach((s) => themeIO.observe(s));

const current = new IntersectionObserver((entries) => {
  for (const e of entries) {
    if (!e.isIntersecting) continue;
    links.forEach((a) => a.setAttribute('aria-current', String(a.hash === '#' + e.target.id)));
  }
}, { rootMargin: '-45% 0px -50% 0px' });
links.forEach((a) => { const s = document.querySelector(a.hash); if (s) current.observe(s); });

const toggle = nav.querySelector('.nav-toggle');
const setMenu = (open) => {
  nav.classList.toggle('is-open', open);
  toggle.setAttribute('aria-expanded', String(open));
  toggle.firstElementChild.textContent = open ? 'Close' : 'Menu';
};
toggle.addEventListener('click', () => setMenu(!nav.classList.contains('is-open')));
links.forEach((a) => a.addEventListener('click', () => setMenu(false)));
addEventListener('keydown', (e) => { if (e.key === 'Escape') setMenu(false); });

// disciplines: the item crossing the middle of the viewport owns the picture
const discImgs = [...document.querySelectorAll('[data-disc]')];
const discItems = [...document.querySelectorAll('[data-disc-item]')];
const discNo = document.querySelector('[data-disc-no]');
let active = -1;
const setDisc = (i) => {
  if (i === active) return;
  discImgs.forEach((img, k) => { img.classList.toggle('was-active', k === active); img.classList.toggle('is-active', k === i); });
  discItems.forEach((li, k) => li.classList.toggle('is-active', k === i));
  if (discNo) discNo.textContent = String(i + 1).padStart(2, '0');
  active = i;
};
const discIO = new IntersectionObserver((entries) => {
  for (const e of entries) if (e.isIntersecting) setDisc(+e.target.dataset.discItem);
}, { rootMargin: '-48% 0px -48% 0px' });
discItems.forEach((li) => discIO.observe(li));
setDisc(0);
// the stage images are lazy; start fetching them once the section is near
new IntersectionObserver(([e], io) => {
  if (e.isIntersecting) { discImgs.forEach((img) => (img.loading = 'eager')); io.disconnect(); }
}, { rootMargin: '100% 0px' }).observe(document.getElementById('disciplines'));

// "Register for 004" carries the intention down to the form
document.querySelectorAll('[data-register]').forEach((a) => a.addEventListener('click', () => {
  const box = document.querySelector('.join-form [name="trip"]');
  if (box) box.checked = true;
}));

// join: no backend yet, so the form composes an email to the club
const form = document.querySelector('.join-form');
form?.addEventListener('submit', (e) => {
  e.preventDefault();
  const d = new FormData(form);
  const to = form.dataset.mailto;
  const body = [
    `Name: ${d.get('name')}`, `Email: ${d.get('email')}`, `Programme: ${d.get('programme')}`,
    `Experience: ${d.get('experience')}`, d.get('trip') ? `Register me for: ${d.get('trip')}` : '',
  ].filter(Boolean).join('\n');
  location.href = `mailto:${to}?subject=${encodeURIComponent('Membership — ' + d.get('name'))}&body=${encodeURIComponent(body)}`;
  form.querySelector('.join-status').textContent = `Your mail app should open with everything filled in. If it does not, write to ${to}.`;
});
})();
