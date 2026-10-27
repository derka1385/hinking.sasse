// The circular pointer belongs to the entrance only. Native links handle navigation.
(() => {
  if (document.documentElement.dataset.entry !== 'choose') return;
  const scene = document.querySelector('.entry-choice');
  const cursor = scene?.querySelector('.entry-cursor');
  const fine = matchMedia('(hover: hover) and (pointer: fine)');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  if (!cursor || !fine.matches || reduced.matches) return;

  let frame = 0, x = 0, y = 0, over = false;
  function hide() {
    if (frame) cancelAnimationFrame(frame);
    frame = 0;
    scene.classList.remove('has-entry-cursor');
    cursor.classList.remove('is-visible', 'is-over', 'is-pressed');
  }
  function paint() {
    frame = 0;
    if (!fine.matches || reduced.matches || document.hidden) { hide(); return; }
    cursor.style.transform = `translate3d(${x}px, ${y}px, 0)`;
    cursor.classList.toggle('is-over', over);
    cursor.classList.add('is-visible');
    // Hide the system pointer only after its replacement has a valid position.
    scene.classList.add('has-entry-cursor');
  }
  scene.addEventListener('pointermove', (event) => {
    if (event.pointerType !== 'mouse' || !fine.matches || reduced.matches) { hide(); return; }
    x = event.clientX; y = event.clientY;
    over = Boolean(event.target.closest?.('a, button'));
    if (!frame) frame = requestAnimationFrame(paint);
  }, { passive: true });
  scene.addEventListener('pointerleave', hide);
  scene.addEventListener('pointercancel', hide);
  scene.addEventListener('pointerdown', (event) => {
    if (event.pointerType === 'mouse') cursor.classList.add('is-pressed');
    else hide();
  }, { passive: true });
  window.addEventListener('pointerup', () => cursor.classList.remove('is-pressed'), { passive: true });
  window.addEventListener('blur', hide);
  window.addEventListener('pagehide', hide);
  document.addEventListener('keydown', hide);
  document.addEventListener('visibilitychange', () => { if (document.hidden) hide(); });
  fine.addEventListener('change', hide);
  reduced.addEventListener('change', hide);
})();
