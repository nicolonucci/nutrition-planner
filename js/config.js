// CONFIGURAZIONE
const CONFIG = {
  github_user: 'nicolonucci',
  github_repo: 'nutrition-planner',
  branch: 'main',

  get raw_base() {
    return `https://raw.githubusercontent.com/${this.github_user}/${this.github_repo}/${this.branch}`;
  },

  paths: {
    dispensaLoc:    (loc) => `data/dispensa_${loc}.json`,
    settimane:      'data/settimane.json',
    menu:           (settimana) => `data/menus/${settimana}.json`,
    health_history: 'data/health_history.json',
  }
};

// Fetch base: usa path relativo su GitHub Pages (CDN veloce), raw.githubusercontent come fallback
// Cache-buster (_=timestamp) + cache:'no-store' per evitare che il browser o la CDN
// servano una copia cachata dei dati dopo un aggiornamento appena pushato.
async function fetchData(path) {
  const isGHPages = location.hostname.endsWith('github.io');
  const base = isGHPages
    ? `/${CONFIG.github_repo}/${path}`
    : `${CONFIG.raw_base}/${path}`;
  const sep = base.includes('?') ? '&' : '?';
  const url = `${base}${sep}_=${Date.now()}`;
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) throw new Error(`HTTP ${res.status} — ${path}`);
  return res.json();
}

// Fetch con cache localStorage: ritorna dati subito alla seconda visita.
// TTL predefinito: 30 minuti. La rete aggiorna silenziosamente in background.
async function fetchCached(path, ttl = 1800) {
  const key = `_nh_${path}`;
  let cached = null;
  try {
    const raw = localStorage.getItem(key);
    if (raw) {
      const { ts, data } = JSON.parse(raw);
      if (Date.now() - ts < ttl * 1000) cached = data;
    }
  } catch (_) {}

  const netPromise = fetchData(path).then(data => {
    try { localStorage.setItem(key, JSON.stringify({ ts: Date.now(), data })); } catch (_) {}
    return data;
  });

  if (cached !== null) {
    netPromise.catch(() => {});
    return cached;
  }
  return netPromise;
}

// Calcola settimana ISO corrente (YYYY-WNN)
function getCurrentWeek() {
  const now = new Date();
  const jan4 = new Date(now.getFullYear(), 0, 4);
  const startOfWeek1 = new Date(jan4);
  startOfWeek1.setDate(jan4.getDate() - ((jan4.getDay() + 6) % 7));
  const diff = now - startOfWeek1;
  const weekNum = Math.floor(diff / (7 * 86400000)) + 1;
  return `${now.getFullYear()}-W${String(weekNum).padStart(2, '0')}`;
}

// Da "YYYY-WNN" a stringa leggibile "25 mag – 31 mag 2026"
function weekLabel(isoWeek) {
  const [year, wPart] = isoWeek.split('-W');
  const week = parseInt(wPart);
  const jan4 = new Date(parseInt(year), 0, 4);
  const startOfWeek1 = new Date(jan4);
  startOfWeek1.setDate(jan4.getDate() - ((jan4.getDay() + 6) % 7));
  const start = new Date(startOfWeek1.getTime() + (week - 1) * 7 * 86400000);
  const end = new Date(start.getTime() + 6 * 86400000);
  const fmt = (d) => d.toLocaleDateString('it-IT', { day: 'numeric', month: 'short' });
  return `${fmt(start)} – ${fmt(end)} ${end.getFullYear()}`;
}

// Nav link attivo
function setActiveNav() {
  const page = location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('nav a').forEach(a => {
    const href = a.getAttribute('href').split('/').pop();
    if (href === page) a.classList.add('active');
  });
}
