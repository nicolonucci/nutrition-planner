// ── DYNAMIC CONFIG ──────────────────────────────────────────────────────────
// Reads github credentials from data/config.json and user profile from data/profilo.json
// Both are loaded once at startup via waitConfig(). All pages call await waitConfig()
// before fetching any data.

let CONFIG = {
  github_user: null,
  github_repo: null,
  branch: 'main',
  get raw_base() {
    return `https://raw.githubusercontent.com/${this.github_user}/${this.github_repo}/${this.branch}`;
  },
  paths: {
    pantry:         'data/pantry.json',
    weeks:          'data/weeks.json',
    menu:           (week) => `data/menus/${week}.json`,
    health_history: 'data/health_history.json',
    profilo:        'data/profilo.json',
  }
};

let PROFILE = {};
let LANG = 'en';

const _configReady = (async () => {
  try {
    const cfg = await fetch('data/config.json').then(r => r.ok ? r.json() : {});
    if (cfg.github_user) CONFIG.github_user = cfg.github_user;
    if (cfg.github_repo) CONFIG.github_repo = cfg.github_repo;
    if (cfg.branch)      CONFIG.branch = cfg.branch;
  } catch (_) {}

  try {
    PROFILE = await fetch('data/profilo.json').then(r => r.ok ? r.json() : {});
    LANG = PROFILE?.meta?.language || 'en';
  } catch (_) {}
})();

/** Await this before calling fetchData(). */
function waitConfig() { return _configReady; }

// ── FETCH ────────────────────────────────────────────────────────────────────
async function fetchData(path) {
  const isGHPages = location.hostname.endsWith('github.io');
  const url = isGHPages
    ? `/${CONFIG.github_repo}/${path}`
    : (CONFIG.github_user && CONFIG.github_repo)
      ? `${CONFIG.raw_base}/${path}`
      : path; // local fallback
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status} — ${path}`);
  return res.json();
}

// ── DATE / WEEK UTILS ────────────────────────────────────────────────────────

/** Current ISO week string e.g. "2026-W26" */
function getCurrentWeek() {
  const now = new Date();
  const jan4 = new Date(now.getFullYear(), 0, 4);
  const sw = new Date(jan4);
  sw.setDate(jan4.getDate() - ((jan4.getDay() + 6) % 7));
  const weekNum = Math.floor((now - sw) / (7 * 86400000)) + 1;
  return `${now.getFullYear()}-W${String(weekNum).padStart(2, '0')}`;
}

/** Monday of the given ISO week */
function weekStart(isoWeek) {
  if (!isoWeek) return null;
  const [year, wPart] = isoWeek.split('-W');
  const week = parseInt(wPart);
  const jan4 = new Date(parseInt(year), 0, 4);
  const sw = new Date(jan4);
  sw.setDate(jan4.getDate() - ((jan4.getDay() + 6) % 7));
  return new Date(sw.getTime() + (week - 1) * 7 * 86400000);
}

/** "12 Jun – 18 Jun 2026" */
function weekLabel(isoWeek) {
  const start = weekStart(isoWeek);
  if (!start) return isoWeek;
  const end = new Date(start.getTime() + 6 * 86400000);
  const locale = LANG === 'en' ? 'en-GB' : LANG + '-' + LANG.toUpperCase();
  const fmt = d => d.toLocaleDateString(locale, { day: 'numeric', month: 'short' });
  return `${fmt(start)} – ${fmt(end)} ${end.getFullYear()}`;
}

/** "12 Jun" */
function shortWeekLabel(isoWeek) {
  const d = weekStart(isoWeek);
  if (!d) return isoWeek;
  const locale = LANG === 'en' ? 'en-GB' : LANG + '-' + LANG.toUpperCase();
  return d.toLocaleDateString(locale, { day: 'numeric', month: 'short' });
}

/** Format a date string "YYYY-MM-DD" as "12 Jun" */
function fmtDate(iso) {
  if (!iso) return '—';
  const locale = LANG === 'en' ? 'en-GB' : LANG + '-' + LANG.toUpperCase();
  return new Date(iso + 'T12:00:00').toLocaleDateString(locale, { day: 'numeric', month: 'short' });
}

/** Format hours as "7h 30m" */
function fmtHours(h) {
  if (h == null) return '—';
  const hrs = Math.floor(h), mins = Math.round((h - hrs) * 60);
  return `${hrs}h${mins > 0 ? ' ' + mins + 'm' : ''}`.trim();
}

/** Format number with locale separators */
function fmtNum(n, decimals = 0) {
  if (n == null) return '—';
  return Number(n).toLocaleString(LANG === 'en' ? 'en-GB' : LANG, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

// ── NAV ──────────────────────────────────────────────────────────────────────
function setActiveNav() {
  const page = location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('nav a').forEach(a => {
    const href = (a.getAttribute('href') || '').split('/').pop().split('?')[0];
    a.classList.toggle('active', href === page);
  });
}
