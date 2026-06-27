// CONFIGURAZIONE — aggiorna con il tuo username e nome repo dopo la creazione su GitHub
const CONFIG = {
  github_user: 'nicolonucci',       // <-- aggiorna con username esatto
  github_repo: 'nutrition-planner',   // <-- nome repo che creerai
  branch: 'main',

  // URL base per leggere i file raw da GitHub
  get raw_base() {
    return `https://raw.githubusercontent.com/${this.github_user}/${this.github_repo}/${this.branch}`;
  },

  // Percorsi dati
  paths: {
    dispensa:       'data/dispensa.json',
    settimane:      'data/settimane.json',
    menu:           (settimana) => `data/menus/${settimana}.json`,
    health_history: 'data/health_history.json',
  }
};

// Utility: fetcha un JSON dal repo
async function fetchData(path) {
  const isGHPages = location.hostname.endsWith('github.io');
  const url = isGHPages
    ? `/${CONFIG.github_repo}/${path}`
    : `${CONFIG.raw_base}/${path}`;
  const res = await fetch(url, { cache: 'no-cache' });
  if (!res.ok) throw new Error(`HTTP ${res.status} — ${path}`);
  return res.json();
}

// Utility: fetch con cache localStorage (ritorna dati subito, aggiorna in background)
// TTL in secondi (default 30 min). Passa ttl=0 per forzare refresh.
async function fetchCached(path, ttl = 1800) {
  const key = `_nh_${path}`;
  let cached = null;
  try {
    const raw = localStorage.getItem(key);
    if (raw) {
      const { ts, data } = JSON.parse(raw);
      if (ttl > 0 && Date.now() - ts < ttl * 1000) cached = data;
    }
  } catch (_) {}

  // Fetch rete in background — aggiorna localStorage
  const netPromise = fetchData(path).then(data => {
    try { localStorage.setItem(key, JSON.stringify({ ts: Date.now(), data })); } catch (_) {}
    return data;
  });

  // Se abbiamo dati cached validi, mostrali subito (la rete aggiorna in silenzio)
  if (cached !== null) {
    netPromise.catch(() => {});  // ignora errori background
    return cached;
  }

  // Prima visita o cache scaduta: aspetta la rete
  return netPromise;
}

// Utility: calcola settimana ISO corrente (YYYY-WNN)
function getCurrentWeek() {
  const now = new Date();
  const jan4 = new Date(now.getFullYear(), 0, 4);
  const startOfWeek1 = new Date(jan4);
  startOfWeek1.setDate(jan4.getDate() - ((jan4.getDay() + 6) % 7));
  const diff = now - startOfWeek1;
  const weekNum = Math.floor(diff / (7 * 86400000)) + 1;
  return `${now.getFullYear()}-W${String(weekNum).padStart(2, '0')}`;
}

// Utility: da "YYYY-WNN" a stringa leggibile "25 mag – 31 mag 2026"
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

// Utility: nav link attivo
function setActiveNav() {
  const page = location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('nav a').forEach(a => {
    const href = a.getAttribute('href').split('/').pop();
    if (href === page) a.classList.add('active');
  });
}
