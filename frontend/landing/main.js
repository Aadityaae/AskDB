const reduce = matchMedia('(prefers-reduced-motion: reduce)');
const burger = document.querySelector('.burger');
const menu = document.querySelector('.mobile-menu');
const overlay = document.querySelector('.menu-overlay');
const dialog = document.querySelector('#details');
const video = document.querySelector('.bg-video');
const toggle = document.querySelector('#video-toggle');
let menuOpen = false, userPaused = reduce.matches || Boolean(globalThis.navigator?.connection?.saveData);
function setMenu(open, restoreFocus = false) {
  menuOpen = open;
  menu.hidden = overlay.hidden = !open;
  document.body.classList.toggle('menu-open', open);
  burger.setAttribute('aria-expanded', String(open));
  burger.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
  if (open) menu.querySelector('a').focus();
  else if (restoreFocus) burger.focus();
}
burger.addEventListener('click', () => setMenu(!menuOpen));
overlay.addEventListener('click', () => setMenu(false, true));
menu.addEventListener('click', e => { if (e.target.closest('a,button')) setMenu(false); });
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && menuOpen) setMenu(false, true);
  if (e.key === 'Tab' && menuOpen) {
    const items = [burger, ...menu.querySelectorAll('a,button')];
    const i = items.indexOf(document.activeElement);
    if (e.shiftKey && i <= 0) { e.preventDefault(); items.at(-1).focus(); }
    else if (!e.shiftKey && i === items.length - 1) { e.preventDefault(); burger.focus(); }
  }
});
window.addEventListener('resize', () => { if (innerWidth > 720 && menuOpen) setMenu(false, true); });
const content = {
  product: ['A question becomes a discovery.', 'AskDB connects natural-language questions to real, read-only SQL. Inspect the query, explore the records, and turn results into charts.', ['Upload a private CSV or SQLite database, or explore the demo.', 'Type a question, or use local voice transcription.', 'Review the answer, SQL, validation checks and supporting data.']],
  how: ['From file to first answer.', 'Your files become private snapshots in your account. You choose the active database; AskDB uses its tables and columns for every question.', ['Create an account and open Your databases.', 'Upload a CSV or a standalone SQLite .db file (up to 50 MB).', 'Select your database and ask your first question.']],
  about: ['Built for the “what if?” people.', 'AskDB is a workspace for exploring data without starting with SQL. Your archive keeps previous questions and their database context, so each discovery has a trail.', ['Cloud SQL generation, with local database execution.', 'Read-only guardrails and visible confidence checks.', 'Review AI answers against the SQL and supporting records.']]
};
document.querySelectorAll('[data-panel]').forEach(button => button.addEventListener('click', () => {
  const [title, copy, steps] = content[button.dataset.panel];
  document.querySelector('#detail-title').textContent = title;
  document.querySelector('#detail-copy').textContent = copy;
  document.querySelector('#detail-steps').replaceChildren(...steps.map(text => { const li = document.createElement('li'); li.textContent = text; return li; }));
  dialog.showModal();
}));
document.querySelector('.close-dialog').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', e => { const box = dialog.getBoundingClientRect(); if (e.clientX < box.left || e.clientX > box.right || e.clientY < box.top || e.clientY > box.bottom) dialog.close(); });
// The API selects the local workspace URL; production routes this same path.
if (location.protocol !== 'file:') document.querySelectorAll('[data-workspace]').forEach(link => {
  const url = new URL('/workspace', location.href); url.search = '?entry=' + link.dataset.workspace; link.href = url.href;
});
function syncVideo() {
  const paused = userPaused || document.hidden;
  if (paused) video.pause(); else video.play().catch(() => { toggle.textContent = 'Background unavailable'; toggle.disabled = true; });
  toggle.setAttribute('aria-pressed', String(userPaused));
  toggle.textContent = userPaused ? 'Play background ▷' : 'Pause background Ⅱ';
}
toggle.addEventListener('click', () => { userPaused = !userPaused; syncVideo(); });
video.addEventListener('error', () => { toggle.hidden = true; });
document.addEventListener('visibilitychange', syncVideo);
reduce.addEventListener('change', () => { userPaused = reduce.matches || Boolean(globalThis.navigator?.connection?.saveData); syncVideo(); });
syncVideo();
const counters = [...document.querySelectorAll('[data-target]')];
const frames = new Map();
function finishCounters() { for (const node of counters) { cancelAnimationFrame(frames.get(node)); node.textContent = Number(node.dataset.target).toFixed(Number(node.dataset.decimals)) + node.dataset.suffix; } }
if (!reduce.matches && 'IntersectionObserver' in window) {
  const observer = new IntersectionObserver(entries => entries.forEach(entry => {
    if (!entry.isIntersecting) return;
    const node = entry.target, i = counters.indexOf(node), duration = 1500 + i * 80;
    const start = performance.now() + 480 + i * 90;
    function tick(time) {
      if (reduce.matches || document.hidden) { finishCounters(); return; }
      const progress = Math.max(0, Math.min(1, (time - start) / duration));
      node.textContent = (Number(node.dataset.target) * (1 - Math.pow(1 - progress, 3))).toFixed(Number(node.dataset.decimals)) + node.dataset.suffix;
      if (progress < 1) frames.set(node, requestAnimationFrame(tick));
    }
    frames.set(node, requestAnimationFrame(tick)); observer.unobserve(node);
  }), {threshold: .25});
  counters.forEach(node => observer.observe(node));
  reduce.addEventListener('change', () => { if (reduce.matches) { finishCounters(); observer.disconnect(); } });
}
