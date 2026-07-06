# Briefing: andamento.html — stato attuale e problemi aperti

## Repo GitHub
- **URL**: https://github.com/nicolonucci/nutrition-planner
- **GitHub Pages**: https://nicolonucci.github.io/nutrition-planner/andamento.html
- **Commit corrente**: a1d4eb5
- **Path locale**: `/Users/nicolo/Documents/Claude/Projects/Nutrition and Training/`

---

## Cosa fa andamento.html

Pagina singola con **4 tab** che visualizza i dati di salute e allenamento estratti da Apple Health.

### Tab 1 — Riepilogo
- Hero card: peso attuale, variazione, BMI con gauge colorata
- Record personali: peso min/max, passi record, calorie max, BMI min
- Lista allenamenti dell'ultima settimana

### Tab 2 — Trend
- 6 grafici Chart.js (peso+BMI, passi, calorie attive, sonno, FC riposo, mix allenamenti)
- Selector range: 8 / 16 / 26 / 52 settimane / tutto
- Grafici inizializzati lazy (solo quando si apre la tab Trend per la prima volta)

### Tab 3 — Settimane
- Tabella ordinabile per settimana/peso/BMI/passi/calorie/sonno/FC
- Righe espandibili: click → mostra allenamenti della settimana
- Bottone "Mostra tutte" se >20 settimane

### Tab 4 — Allenamenti
- Card riepilogo per tipo di attività (totale sessioni, minuti, HR media)
- Chip filtro per tipo: Tutti / Ciclismo / Nuoto / Corsa / ...
- Lista workout cliccabili: click → espande dettaglio inline
- Dettaglio workout: stats (durata, calorie, distanza, velocità/passo, HR avg/max), barre zone HR (Z1–Z5), grafico HR nel tempo (Chart.js line chart con sfondo zone colorato)

---

## Struttura file rilevanti

```
nutrition-planner/
├── andamento.html          ← pagina principale (664 righe)
├── js/
│   └── config.js           ← CONFIG, fetchData, fetchCached
├── data/
│   ├── health_history.json ← 193 settimane (42KB)
│   └── workout_details.json ← 112 workout con hr_timeline (97KB)
└── scripts/
    ├── extract_health_history.py   ← aggiornamento incrementale settimanale
    └── extract_workout_details.py  ← aggiornamento incrementale workout
```

---

## Struttura dati

### health_history.json
```json
{
  "settimane": [
    {
      "settimana": "2026-W26",
      "data_analisi": "2026-06-27",
      "peso": { "ultimo_kg": 73.8, "data_rilevamento": "2026-06-21", "variazione_kg": -0.4 },
      "passi": { "totale": 82389, "media_giorno": 13732 },
      "calorie_attive": { "totale": 6032, "media_giorno": 862 },
      "calorie_totali_media": 2330,
      "allenamenti": [
        { "tipo": "Ciclismo", "data": "2026-06-23", "durata_min": 161 }
      ],
      "sonno": { "media_ore": 6.68, "min_ore": 5.35, "max_ore": 8.07 },
      "fc_riposo_media": 61
    }
  ]
}
```

### workout_details.json
```json
{
  "max_hr_ref": 175,
  "height_m": 1.70,
  "workouts": [
    {
      "id": "2026-06-26T15:24:41",
      "tipo": "Surf/Wingfoil",
      "data": "2026-06-26",
      "settimana": "2026-W26",
      "ora_inizio": "15:24",
      "durata_min": 47,
      "calorie": 417,
      "distanza_km": null,
      "hr_avg": 134,
      "hr_max": 162,
      "hr_zones": { "z3": 7.3, "z4": 23.7, "z5": 15.9 },
      "hr_timeline": [{ "t": 0, "bpm": 120 }, { "t": 1, "bpm": 125 }, ...]
    }
  ]
}
```
- `hr_zones`: minuti per zona (z1–z5). Non tutti i workout ce l'hanno.
- `hr_timeline`: punti {t: minuto dall'inizio, bpm}. Non tutti i workout ce l'hanno.
- Zone calcolate su `max_hr_ref=175`: z1<50%, z2<60%, z3<70%, z4<80%, z5≥80%

---

## Logica fetch (js/config.js + inline in andamento.html)

```javascript
// config.js
async function fetchData(path) {
  const isGHPages = location.hostname.endsWith('github.io');
  const url = isGHPages
    ? `/${CONFIG.github_repo}/${path}`          // su GitHub Pages
    : `https://raw.githubusercontent.com/.../${path}`;  // in locale
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function fetchCached(path, ttl=1800) {
  // localStorage con TTL 30min — seconda visita istantanea
  // se cache presente: ritorna subito, aggiorna in background
  // se no cache: aspetta la rete
}
```

**Attenzione**: `andamento.html` definisce anche un fallback inline di `fetchCached`
subito dopo il `<script src="js/config.js">`, per gestire il caso in cui il browser
abbia in cache una versione vecchia di config.js priva di `fetchCached`.

### init() in andamento.html
```javascript
async function init() {
  const [healthData, workoutData] = await Promise.all([
    fetchCached(CONFIG.paths.health_history),       // data/health_history.json
    fetchCached('data/workout_details.json'),
  ]);
  gSettimane = healthData.settimane.sort(...);
  gWorkouts  = workoutData.workouts;
  gMaxHR     = workoutData.max_hr_ref || 175;
  gHeight    = workoutData.height_m   || 1.70;
  // render tutte le tab...
}
```

---

## Stato globale in andamento.html

```javascript
let gSettimane=[], gWorkouts=[], gMaxHR=175, gHeight=1.70;
let chartInstances={}, chartsReady=false;
let currentRange=26;        // settimane visibili nei grafici Trend
let filterTipo='tutti';     // filtro tab Allenamenti
let openWorkoutId=null;     // workout espanso inline
let workoutChartInst=null;  // istanza Chart.js HR del workout aperto
let expandedWeekRow=null;   // riga espansa in tab Settimane
let tableSortCol='settimana', tableSortDir=-1, tableShowAll=false;
```

---

## Problema aperto: il caricamento non funziona

La pagina su GitHub Pages **non carica i dati di salute** (`health_history.json`).

### Sintomi
- La pagina rimane in stato di loading o mostra "Nessun dato disponibile"
- Il problema persiste anche dopo hard refresh (Cmd+Shift+R)

### Cause probabili da investigare
1. **URL costruito male**: su GitHub Pages `location.hostname` = `nicolonucci.github.io`,
   quindi `endsWith('github.io')` = true, URL = `/nutrition-planner/data/health_history.json`.
   Verificare con DevTools → Network che questa URL risponda 200.

2. **localStorage corrotto**: se una sessione precedente ha salvato JSON malformato,
   `fetchCached` torna dati invalidi. Fix rapido: `localStorage.clear()` in console.

3. **GitHub Pages CDN lento**: dopo un push, i file possono impiegare 2–5 minuti
   ad aggiornare. La pagina potrebbe caricare una versione vecchia del JS.

### Come diagnosticare
Aprire DevTools → Console e cercare errori. Aprire DevTools → Network e verificare:
- `health_history.json`: status, URL usato, dimensione risposta
- `workout_details.json`: stesso
- `config.js`: che sia la versione corrente (controlla `fetchCached` nel sorgente)

### Cosa fare per risolvere definitivamente
Riscrivere il fetch in modo più semplice e robusto, senza localStorage come dipendenza
critica per il primo caricamento. Proposta:

```javascript
// In init(): prova localStorage, se fallisce usa rete diretta
async function safeLoad(path) {
  try {
    return await fetchCached(path);
  } catch(e) {
    console.warn('fetchCached fallito, retry diretto:', e);
    return await fetchData(path);
  }
}
```

---

## Funzionalità da aggiungere / migliorare (backlog)

1. **Peso nella tab Riepilogo**: mostrare grafico peso ultime 4 settimane
2. **Confronto settimane**: evidenziare settimane sopra/sotto media
3. **Export PNG grafici**: bottone screenshot del trend
4. **Filtrare per anno**: nella tab Settimane, aggiungere filtro anno
5. **Notifiche push**: avvisare quando aggiornamento dati disponibile

---

## Come aggiornare i dati (skill Apple Health)

La skill `/apple-health` esegue automaticamente:
1. Estrae XML dallo zip caricato
2. Mostra riepilogo ultima settimana
3. Aggiorna `data/health_history.json` (incrementale, salta record già elaborati)
4. Aggiorna `data/workout_details.json` (incrementale)
5. Fa `git push origin main`

Script Python in `scripts/extract_health_history.py` e `scripts/extract_workout_details.py`.
Entrambi accettano `<xml_path> <output_path>` come argomenti CLI.
