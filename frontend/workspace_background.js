export default function({data}) {
  const host = document.querySelector('[data-testid="stApp"]');
  if (!host) return;
  const layer = document.createElement('div');
  layer.className = 'workspace-ambient';
  layer.setAttribute('aria-hidden', 'true');
  for (const name of ['ambient-grid', 'ambient-teal', 'ambient-warm']) {
    const item = document.createElement('div');
    item.className = name;
    layer.appendChild(item);
  }
  host.appendChild(layer);
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  function sync() {
    layer.dataset.paused = String(!data?.motion || document.hidden || reduced.matches);
  }
  sync();
  document.addEventListener('visibilitychange', sync);
  reduced.addEventListener('change', sync);
  return () => {
    document.removeEventListener('visibilitychange', sync);
    reduced.removeEventListener('change', sync);
    layer.remove();
  };
}
