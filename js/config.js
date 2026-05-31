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
  const url = `${CONFIG.raw_base}/${path}?_=${Date.now()}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status} — ${path}`);
  return res.json();
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
