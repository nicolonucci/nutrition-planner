// ═══════════════════════════════════════════════════════════
// APP CORE — logica pura (parser ingredienti, matching dispensa,
// scalaggio fresco→congelato, lista spesa, settimane)
// Usata da app.html; testabile in Node.
// ═══════════════════════════════════════════════════════════

// ── Normalizzazione nomi ──
const STOPWORDS = new Set(['gf','glutine','senza','fresco','fresca','freschi','fresche',
  'surgelato','surgelata','surgelati','surgelate','integrale','integrali','bio','circa',
  'peso','crudo','cruda','cotto','cotta','intere','intero','intera','interi','maturo','matura',
  'affumicato','affumicata','secchi','secche','secco','sgusciate','sgusciati','naturale',
  'sgocciolato','sgocciolata','sode','sodo','strapazzate','strapazzato','lessate','lesso',
  'grattugiato','grattugiata','vapore','forno','qb','extra','vergine','tot','misto','mista',
  'grande','piccolo','piccola','della','del','di','con','per','al','alla']);

function normText(s) {
  return String(s).toLowerCase()
    .normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[0-9]+([.,][0-9]+)?\s*%/g, ' ')
    .replace(/[^a-z\s]/g, ' ')
    .replace(/\s+/g, ' ').trim();
}

// radice grezza: tronca a 4 caratteri per assorbire singolare/plurale (pollo/polli, uovo/uova→uov)
function stem(w) {
  if (w.length <= 3) return w;
  if (w.length > 4 && /[aeio]$/.test(w)) w = w.slice(0, -1);
  return w.slice(0, 5);
}

function tokensOf(s) {
  return normText(s).split(' ')
    .filter(w => w.length >= 3 && !STOPWORDS.has(w))
    .map(stem);
}

// ── Parser riga ingrediente ──
// Esempi reali: "3 uova intere (150 g)" · "90 g riso basmati (peso crudo)" ·
// "1 banana (~120 g)" · "½ avocado maturo (~80 g)" · "15 ml tamari GF" ·
// "sale, pepe q.b." · "succo ½ limone" · "150 g yogurt greco 0%"
const FRAZ = { '½': 0.5, '¼': 0.25, '¾': 0.75, '⅓': 0.33, '⅔': 0.67 };

function parseNum(s) {
  s = s.trim();
  if (FRAZ[s] != null) return FRAZ[s];
  let m = s.match(/^(\d+)\s*([½¼¾⅓⅔])$/);
  if (m) return parseInt(m[1]) + FRAZ[m[2]];
  m = s.match(/^(\d+)\s*\/\s*(\d+)$/);           // "1/2"
  if (m) return parseInt(m[1]) / parseInt(m[2]);
  return parseFloat(s.replace(',', '.'));
}
const NUMPAT = '[\\d]+\\s*\\/\\s*[\\d]+|[\\d.,]+\\s*[½¼¾]?|[½¼¾⅓⅔]';

function normUnit(u, qty) {
  if (!u) return { unit: 'pz', qty };
  u = u.toLowerCase();
  if (u === 'kg') return { unit: 'g', qty: qty * 1000 };
  if (u === 'l' || u === 'lt') return { unit: 'ml', qty: qty * 1000 };
  if (u === 'g' || u === 'gr') return { unit: 'g', qty };
  if (u === 'ml') return { unit: 'ml', qty };
  return { unit: 'pz', qty }; // fette, vasetti, pezzi…
}

function parseIngrediente(riga) {
  let s = String(riga).trim();
  if (!s || /q\.?\s?b\.?/i.test(s)) return null;           // sale, spezie q.b. → non scalare
  if (/^(acqua|sale|pepe|spezie|erbe)\b/i.test(normText(s))) return null;
  s = s.replace(/^(succo|scorza|spremuta)\s+(di\s+)?/i, ''); // "succo ½ limone" → "½ limone"

  let qty = null, unit = null;

  const noPar = s.replace(/\([^)]*\)/g, ' ').replace(/\s+/g, ' ').trim();
  const UNITS = 'g|gr|kg|ml|l|lt|pz|fett[ae]|vasett[oi]|scatolett[ae]|cucchia\\w+|spicchi?o?';

  // 1) quantità in testa: "90 g riso" · "3 uova" · "½ avocado" · "2 fette pane"
  const lead = noPar.match(new RegExp(`^~?\\s*(${NUMPAT})\\s*(${UNITS})?\\s+(.+)$`, 'i'));
  if (lead) { qty = parseNum(lead[1]); unit = lead[2] || null; }

  // 2) quantità tra parentesi in g/ml: "(~150 g)" "(80 g)" — usata se in testa
  //    non c'è un'unità di peso/volume E il nome non è "contabile" (uova, banana…)
  const par = s.match(new RegExp(`\\(\\s*~?\\s*(${NUMPAT})\\s*(g|gr|ml|kg|l)\\b[^)]*\\)`, 'i'));
  // "contabili": in dispensa stanno a pezzi → preferisci il conteggio ai grammi
  const contabile = /\buov|banana|arancia|mela\b|mele\b|limone|limoni|kiwi|pera\b|pere\b|pesca\b|pesche\b/i.test(noPar);
  const leadPeso = lead && lead[2] && /^(g|gr|kg|ml|l|lt)$/i.test(lead[2]); // unità di misura vera in testa
  if (par && !leadPeso && !(lead && contabile)) { qty = parseNum(par[1]); unit = par[2]; }

  // 3) quantità in coda: "uova 12 pz" · "latte 500 ml"
  if (qty == null) {
    const tail = noPar.match(new RegExp(`^(.+?)\\s+~?(${NUMPAT})\\s*(g|gr|kg|ml|l|pz)?\\s*$`, 'i'));
    if (tail) { qty = parseNum(tail[2]); unit = tail[3] || null; }
  }

  // nome: togli parentesi, numeri e unità
  let nome = noPar
    .replace(new RegExp(`^~?\\s*(${NUMPAT})\\s*(?:(${UNITS})(?=\\s|$))?\\s*`, 'i'), '')
    .replace(new RegExp(`\\s*~?(${NUMPAT})\\s*(g|gr|kg|ml|l|pz)?\\s*$`, 'i'), '')
    .replace(/\bsucco\b/ig, ' ').replace(/\s+/g, ' ').trim();
  if (!nome) nome = noPar;

  if (qty == null) { qty = 1; unit = 'pz'; }
  const nu = normUnit(unit, qty);
  return { raw: riga, nome, qty: Math.round(nu.qty * 100) / 100, unit: nu.unit, tokens: tokensOf(nome) };
}

// ── Monoporzione: prodotti con nota "NxMg" (es. "6x25g") ──
// La grammatura (M) è il dato stabile; N viene ricalcolato da quantita.
const NXG_RE = /(\d+(?:[.,]\d+)?)\s*[xX×]\s*(\d+(?:[.,]\d+)?)\s*(g|gr|kg|ml|l)\b/;

function portionInfo(a) {
  const m = String(a.note || '').match(NXG_RE);
  if (!m) return null;
  let gramm = parseFloat(m[2].replace(',', '.'));
  const u = (m[3] || 'g').toLowerCase();
  if (u === 'kg') gramm *= 1000; else if (u === 'l') gramm *= 1000;
  if (!gramm || normDispUnit(a.unita) === 'pz') return null;
  return { gramm, pezzi: Math.round((Number(a.quantita) / gramm) * 10) / 10 };
}

function noteLabelPorzioni(qta, gramm) {
  const n = Math.round((Number(qta) / gramm) * 10) / 10;
  return `${String(n % 1 ? n.toFixed(1) : n).replace('.', ',')}x${String(gramm).replace('.', ',')}g`;
}

// riscrive la parte NxMg della nota in base alla quantità attuale
function syncNotePorzioni(a) {
  const pi = portionInfo(a);
  if (!pi) return;
  a.note = String(a.note).replace(NXG_RE, noteLabelPorzioni(a.quantita, pi.gramm));
}

// parse riga "philadelphia 6x25g" / "pollo 5x200g" → {nome, n, gramm, qty, unit}
function parseNxG(riga) {
  const m = String(riga).match(NXG_RE);
  if (!m) return null;
  const n = parseFloat(m[1].replace(',', '.'));
  let gramm = parseFloat(m[2].replace(',', '.'));
  let unit = m[3].toLowerCase();
  if (unit === 'kg') { gramm *= 1000; unit = 'g'; }
  else if (unit === 'l') { gramm *= 1000; unit = 'ml'; }
  else if (unit === 'gr') unit = 'g';
  const nome = String(riga).replace(m[0], ' ').replace(/\([^)]*\)/g, ' ').replace(/\s+/g, ' ').trim();
  if (!nome || !n || !gramm) return null;
  return { nome, n, gramm, qty: Math.round(n * gramm * 100) / 100, unit };
}

// ── Matching con dispensa ──
function matchScore(tokA, tokB) {
  if (!tokA.length || !tokB.length) return 0;
  let hit = 0;
  for (const a of tokA) if (tokB.includes(a)) hit++;
  return hit / Math.min(tokA.length, tokB.length);
}

function normDispUnit(u) {
  u = String(u || '').toLowerCase();
  if (u === 'kg') return 'g';
  if (u === 'g' || u === 'gr') return 'g';
  if (u === 'l' || u === 'lt' || u === 'ml') return 'ml';
  return 'pz';
}

// ritorna indici delle voci dispensa che corrispondono all'ingrediente
// (stessa unità: mai scalare grammi da voci a pezzi o viceversa)
function matchDispensa(ing, alimenti) {
  const out = [];
  alimenti.forEach((al, i) => {
    if (ing.unit && normDispUnit(al.unita) !== ing.unit) return;
    const score = matchScore(ing.tokens, tokensOf(al.nome));
    if (score >= 0.5) out.push({ i, score, al });
  });
  out.sort((a, b) => b.score - a.score);
  const best = out.length ? out[0].score : 0;
  return out.filter(o => o.score >= best - 0.01); // tutte le voci con lo stesso nome
}

// ── Scalaggio: fresco prima, poi congelato in ordine di lista ──
// Ritorna [{index, prelievo}] senza modificare la dispensa.
function pianoScalaggio(qtyNeeded, matches) {
  const ordered = [...matches].sort((a, b) => (a.al.congelato === b.al.congelato) ? a.i - b.i : (a.al.congelato ? 1 : -1));
  let rest = qtyNeeded;
  const plan = [];
  for (const m of ordered) {
    if (rest <= 0) break;
    const disp = Number(m.al.quantita) || 0;
    if (disp <= 0) continue;
    const take = Math.min(disp, rest);
    plan.push({ index: m.i, prelievo: Math.round(take * 100) / 100, congelato: !!m.al.congelato, nome: m.al.nome, unita: m.al.unita });
    rest -= take;
  }
  return { plan, mancante: Math.round(Math.max(0, rest) * 100) / 100 };
}

// ── Aggregazione ingredienti di una settimana (per lista spesa) ──
function ingredientiSettimana(menu, giorniFiltro) {
  const agg = new Map(); // key = tokens.join(' ')
  for (const g of (menu.giorni || [])) {
    if (giorniFiltro && !giorniFiltro.includes(g.giorno)) continue;
    for (const [slot, pasto] of Object.entries(g.pasti || {})) {
      const righe = pasto && pasto.ricetta && pasto.ricetta.ingredienti;
      if (!righe) continue;
      for (const r of righe) {
        const ing = parseIngrediente(r);
        if (!ing || !ing.tokens.length) continue;
        const key = [...ing.tokens].sort().join(' ');
        if (!agg.has(key)) agg.set(key, { nome: ing.nome, unit: ing.unit, qty: 0, giorni: [], tokens: ing.tokens });
        const e = agg.get(key);
        if (e.unit === ing.unit) e.qty += ing.qty;
        else if (e.unit === 'pz' && ing.unit !== 'pz') { e.unit = ing.unit; e.qty = e.qty /*pz persi*/ + ing.qty; }
        else e.qty += ing.qty; // unità miste: somma grezza, l'utente corregge
        if (!e.giorni.includes(g.giorno)) e.giorni.push(g.giorno);
      }
    }
  }
  return [...agg.values()].map(e => ({ ...e, qty: Math.round(e.qty) }));
}

// ── Lista spesa: fabbisogno − dispensa (fresco prima, poi congelato ±25g) ──
function calcolaSpesa(menu, alimenti, giorniFiltro) {
  const need = ingredientiSettimana(menu, giorniFiltro);
  const out = [];
  for (const ing of need) {
    const matches = matchDispensa(ing, alimenti);
    let rest = ing.qty;
    let daFresco = 0, daCong = 0;
    for (const m of matches.filter(m => !m.al.congelato)) {
      const take = Math.min(Number(m.al.quantita) || 0, rest);
      daFresco += take; rest -= take;
      if (rest <= 0) break;
    }
    if (rest > 0) {
      // congelato: somma greedy di tutte le voci disponibili
      for (const m of matches.filter(m => m.al.congelato)) {
        const q = Number(m.al.quantita) || 0;
        if (q <= 0) continue;
        const take = Math.min(q, rest);
        daCong += take; rest -= take;
        if (rest <= 0) break;
      }
    }
    if (rest > 25 || (rest > 0 && ing.unit === 'pz')) {
      out.push({ nome: ing.nome, qty: Math.ceil(rest), unit: ing.unit, giorni: ing.giorni,
                 inDispensa: Math.round(daFresco + daCong), categoria: guessCategoria(ing.nome) });
    }
  }
  out.sort((a, b) => a.categoria.localeCompare(b.categoria) || a.nome.localeCompare(b.nome));
  return out;
}

// ── Categoria indovinata dal nome ──
const CAT_KW = [
  ['Proteine', ['pollo','manzo','tacchino','merluzzo','salmone','tonno','pesce','uov','gamber','bresaola','prosciutt','legum','ceci','lentic','fagiol','tofu','vitell','orata','branzino','sgombro','polpo','carne','fesa','macinat']],
  ['Latticini', ['yogurt','latte','parmigian','grana','mozzarell','ricotta','feta','formagg','burro','kefir','skyr']],
  ['Cereali & Carboidrati', ['pasta','riso','pane','avena','farina','patat','quinoa','gnocchi','couscous','mais','gallett','cracker','fiocchi','muesli','tortill']],
  ['Verdure & Frutta', ['zucchin','carot','brocc','spinac','insalat','pomodor','peperon','melanzan','cipoll','aglio','banana','mela','arancia','limone','frutt','verdur','rucola','lattuga','cetriol','avocado','pisell','asparag','funghi','cavol','finocchi','sedano','zucca','kiwi','pera','pesca','anguria','melone','ananas','mirtill','fragol','albicoc']],
  ['Condimenti & Spezie', ['olio','aceto','tamari','soia','miele','curcuma','zenzero','pesto','passata','sugo','senape','maionese','sciroppo','cacao','cioccolat','vanig']],
  ['Snack & Altro', ['mandorl','noci','nocciol','anacard','pistacc','datter','uvetta','barrett','proteic','frullat','burro di']],
];
function guessCategoria(nome) {
  const n = normText(nome);
  for (const [cat, kws] of CAT_KW) for (const kw of kws) if (n.includes(kw)) return cat;
  return 'Snack & Altro';
}

// ── Settimane ISO ──
function isoWeekOf(date) {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const day = (d.getUTCDay() + 6) % 7;
  d.setUTCDate(d.getUTCDate() - day + 3);
  const jan4 = new Date(Date.UTC(d.getUTCFullYear(), 0, 4));
  const week = 1 + Math.round(((d - jan4) / 86400000 - 3 + ((jan4.getUTCDay() + 6) % 7)) / 7);
  return `${d.getUTCFullYear()}-W${String(week).padStart(2, '0')}`;
}
function prossimaSettimana(today) {
  const t = today || new Date();
  const dow = (t.getDay() + 6) % 7; // 0 = lunedì
  const nextMon = new Date(t); nextMon.setDate(t.getDate() + (7 - dow));
  const dal = nextMon;
  const al = new Date(nextMon); al.setDate(nextMon.getDate() + 6);
  const fmt = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  return { id: isoWeekOf(nextMon), dal: fmt(dal), al: fmt(al), date: [...Array(7)].map((_, i) => { const x = new Date(nextMon); x.setDate(nextMon.getDate() + i); return fmt(x); }) };
}

const GIORNI_IT = ['Lunedì','Martedì','Mercoledì','Giovedì','Venerdì','Sabato','Domenica'];

if (typeof module !== 'undefined') module.exports = {
  normText, tokensOf, parseIngrediente, matchDispensa, pianoScalaggio,
  ingredientiSettimana, calcolaSpesa, guessCategoria, isoWeekOf, prossimaSettimana, GIORNI_IT,
  portionInfo, syncNotePorzioni, noteLabelPorzioni, parseNxG
};
