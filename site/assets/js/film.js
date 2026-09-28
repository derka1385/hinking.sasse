// The film (home, last section). A silent loop plays while the frame is on screen, as the poster;
// the button hands the frame to the film, with sound and its own controls. Nothing loads before
// the section is near, nothing plays off screen, and nothing moves for reduced motion or Save-Data.
(() => {
const stage = document.querySelector('[data-film]');
if (!stage) return;
const loop = stage.querySelector('.film-loop');
const full = stage.querySelector('.film-full');
const btn = stage.querySelector('.film-play');
const label = btn.querySelector('.film-play-t');
const still = matchMedia('(prefers-reduced-motion: reduce)').matches || navigator.connection?.saveData;
stage.dataset.state = 'loop';

let onScreen = false;
const playLoop = () => {
  if (still || !onScreen || stage.dataset.state !== 'loop') return;
  loop.play().catch(() => { /* autoplay refused: the poster stays, which is fine */ });
};

new IntersectionObserver(([e]) => {
  onScreen = e.isIntersecting;
  if (onScreen) playLoop();
  else { loop.pause(); if (!full.paused) full.pause(); }
}, { threshold: 0.2 }).observe(stage);

btn.addEventListener('click', () => {
  stage.dataset.state = 'film';
  loop.pause();
  if (full.ended) full.currentTime = 0;
  full.play().catch(() => { /* the native controls are there if the browser wants a second tap */ });
  full.focus({ preventScroll: true });
});

full.addEventListener('ended', () => {
  stage.dataset.state = 'loop';
  label.textContent = 'Play again';
  btn.focus({ preventScroll: true });
  playLoop();
});
})();
