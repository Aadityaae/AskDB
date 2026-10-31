export default function({data}) {
  const host = document.querySelector('[data-testid="stApp"]');
  if (!host) return;
  const media = matchMedia('(prefers-reduced-motion: reduce)');
  const layer = document.createElement('div');
  layer.className = 'dashboard-backdrop' + (data?.light ? ' is-light' : '');
  const video = document.createElement('video');
  video.src = 'https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260826_124724_bc041163-d651-425f-aea3-2acc1efc2c96.mp4';
  video.muted = true; video.loop = true; video.playsInline = true;
  video.preload = 'metadata'; video.setAttribute('aria-hidden', 'true');
  const overlay = document.createElement('div'); overlay.className = 'dashboard-scrim';
  layer.append(video, overlay); host.prepend(layer);
  function sync() {
    if (!data?.motion || media.matches || document.hidden) video.pause();
    else video.play().catch(() => {});
  }
  media.addEventListener('change', sync);
  document.addEventListener('visibilitychange', sync); sync();
  return () => {
    video.pause(); video.removeAttribute('src'); video.load(); layer.remove();
    media.removeEventListener('change', sync);
    document.removeEventListener('visibilitychange', sync);
  };
}
