export default function({data}) {
  const host = document.querySelector('[data-testid="stApp"]');
  if (!host) return;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const layer = document.createElement('div');
  layer.className = 'auth-video-backdrop' + (data?.light ? ' is-light' : '');
  const video = document.createElement('video');
  video.src = 'https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260419_065931_e3ca7b53-d32e-4ad5-81de-dc9d6fcfda6d.mp4';
  video.muted = true; video.loop = true; video.playsInline = true;
  video.preload = 'metadata'; video.setAttribute('aria-hidden', 'true');
  const scrim = document.createElement('div'); scrim.className = 'auth-video-scrim';
  let paused = reduced.matches || Boolean(globalThis.navigator?.connection?.saveData);
  function sync() {
    if (paused || document.hidden) video.pause();
    else video.play().catch(() => { paused = true; });
  }
  function preference() { paused = reduced.matches || Boolean(globalThis.navigator?.connection?.saveData); sync(); }
  layer.append(video, scrim); host.prepend(layer);
  let frame = 0;
  function fit() {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      const card = document.querySelector('.st-key-auth_form_wrap');
      if (!card) return;
      if (matchMedia('(max-width: 600px), (max-height: 600px)').matches) {
        card.style.removeProperty('--auth-fit');
        card.style.removeProperty('top');
        return;
      }
      const view = window.visualViewport;
      const height = view?.height || innerHeight;
      card.style.setProperty('--auth-fit', String(Math.min(1, (height - 24) / Math.max(1, card.offsetHeight))));
      card.style.top = `${(view?.offsetTop || 0) + height / 2}px`;
    });
  }
  const size = new ResizeObserver(fit);
  const changes = new MutationObserver(() => {
    const card = document.querySelector('.st-key-auth_form_wrap');
    if (card) size.observe(card);
    fit();
  });
  changes.observe(host, {childList:true,subtree:true});
  const initialCard = document.querySelector('.st-key-auth_form_wrap');
  if (initialCard) size.observe(initialCard);
  window.addEventListener('resize', fit);
  window.visualViewport?.addEventListener('resize', fit);
  window.visualViewport?.addEventListener('scroll', fit);
  document.addEventListener('visibilitychange', sync);
  reduced.addEventListener('change', preference);
  sync();
  fit();
  return () => {
    video.pause(); video.removeAttribute('src'); video.load();
    cancelAnimationFrame(frame); size.disconnect(); changes.disconnect();
    window.removeEventListener('resize', fit);
    window.visualViewport?.removeEventListener('resize', fit);
    window.visualViewport?.removeEventListener('scroll', fit);
    document.removeEventListener('visibilitychange', sync);
    reduced.removeEventListener('change', preference);
    layer.remove();
  };
}
