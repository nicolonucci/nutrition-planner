#!/usr/bin/env python3
"""
extract_health_history.py — Aggiornamento incrementale di health_history.json

Uso:
  python3 extract_health_history.py <xml_path> <output_path>

Logica incrementale:
  - Se output_path esiste già, legge le settimane presenti
  - Processa solo le ultime 2 settimane già presenti (per aggiornare dati parziali)
    + tutte le settimane nuove
  - Salta il parsing dei record più vecchi della data di cutoff → molto più veloce
"""

import sys
import xml.etree.ElementTree as ET
import json
from collections import defaultdict
from datetime import datetime, timedelta

if len(sys.argv) < 3:
    print("Uso: python3 extract_health_history.py <xml_path> <output_path>", file=sys.stderr)
    sys.exit(1)

XML_PATH    = sys.argv[1]
OUTPUT_PATH = sys.argv[2]

def iso_week(date_str):
    d = datetime.fromisoformat(date_str[:10])
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"

def week_start_date(wk):
    """Restituisce la data di inizio settimana ISO come stringa YYYY-MM-DD."""
    year, w = wk.split('-W')
    jan4 = datetime(int(year), 1, 4)
    start_w1 = jan4 - timedelta(days=(jan4.weekday()))
    start = start_w1 + timedelta(weeks=int(w) - 1)
    return start.date().isoformat()

# ── Carica dati esistenti (modalità incrementale) ──────────────────────────
existing_weeks = {}   # wk -> entry
cutoff_date   = None  # stringa YYYY-MM-DD: ignora record prima di questa data

try:
    with open(OUTPUT_PATH) as f:
        existing = json.load(f)
    all_wks = sorted(s['settimana'] for s in existing.get('settimane', []))
    if all_wks:
        # Mantieni tutto tranne le ultime 2 settimane (le ri-processiamo per dati parziali)
        keep_until   = all_wks[-3] if len(all_wks) >= 3 else ''
        reprocess_from = all_wks[-2] if len(all_wks) >= 2 else all_wks[0]
        existing_weeks = {
            s['settimana']: s
            for s in existing['settimane']
            if s['settimana'] <= keep_until
        }
        cutoff_date = week_start_date(reprocess_from)
        print(f"Modalità incrementale: {len(existing_weeks)} settimane già presenti, riprocesso da {cutoff_date}", flush=True)
    else:
        print("Nessun dato esistente — parsing completo", flush=True)
except (FileNotFoundError, json.JSONDecodeError):
    print("Nessun dato esistente — parsing completo", flush=True)

# ── Parsing XML ────────────────────────────────────────────────────────────
print("Parsing XML...", flush=True)
context = ET.iterparse(XML_PATH, events=('end',))

peso_by_date        = {}
passi_by_week       = defaultdict(float)
passi_days          = defaultdict(set)
kcal_attive_by_week = defaultdict(float)
kcal_bmr_by_week    = defaultdict(float)
sleep_intervals_by_week = defaultdict(list)
fc_by_week          = defaultdict(list)
workouts            = []

SLEEP_ASLEEP = {
    'HKCategoryValueSleepAnalysisAsleepCore',
    'HKCategoryValueSleepAnalysisAsleepDeep',
    'HKCategoryValueSleepAnalysisAsleepREM',
    'HKCategoryValueSleepAnalysisAsleepUnspecified',
    'HKCategoryValueSleepAnalysisAsleep',
}

skipped = 0
for event, elem in context:
    if elem.tag == 'Record':
        t   = elem.get('type', '')
        val = elem.get('value', '')
        sd  = elem.get('startDate', '')
        ed  = elem.get('endDate', '')

        # Skip veloce se il record è più vecchio del cutoff
        if cutoff_date and sd and sd[:10] < cutoff_date:
            skipped += 1
            elem.clear()
            continue

        if t == 'HKQuantityTypeIdentifierBodyMass' and val and sd:
            try: peso_by_date[sd[:10]] = float(val)
            except: pass

        elif t == 'HKQuantityTypeIdentifierStepCount' and val and sd:
            try:
                passi_by_week[iso_week(sd[:10])] += float(val)
                passi_days[iso_week(sd[:10])].add(sd[:10])
            except: pass

        elif t == 'HKQuantityTypeIdentifierActiveEnergyBurned' and val and sd:
            try: kcal_attive_by_week[iso_week(sd[:10])] += float(val)
            except: pass

        elif t == 'HKQuantityTypeIdentifierBasalEnergyBurned' and val and sd:
            try: kcal_bmr_by_week[iso_week(sd[:10])] += float(val)
            except: pass

        elif t == 'HKQuantityTypeIdentifierHeartRate' and val and sd:
            try: fc_by_week[iso_week(sd[:10])].append(float(val))
            except: pass

        elif t == 'HKCategoryTypeIdentifierSleepAnalysis' and val in SLEEP_ASLEEP:
            try:
                s_dt = datetime.fromisoformat(sd[:19])
                e_dt = datetime.fromisoformat(ed[:19])
                mins = (e_dt - s_dt).total_seconds() / 60
                if mins > 10:
                    night_date = e_dt.date() if e_dt.hour < 14 else (e_dt.date() + timedelta(days=1))
                    wk = iso_week(night_date.isoformat())
                    sleep_intervals_by_week[wk].append((s_dt, e_dt, night_date.isoformat()))
            except: pass

        elem.clear()

    elif elem.tag == 'Workout':
        sd_full = elem.get('startDate', '')
        if cutoff_date and sd_full and sd_full[:10] < cutoff_date:
            elem.clear()
            continue

        wtype = elem.get('workoutActivityType', '')
        ed_full = elem.get('endDate', '')
        kcal = float(elem.get('totalEnergyBurned') or 0)
        try:
            dur = int((datetime.fromisoformat(ed_full[:19]) - datetime.fromisoformat(sd_full[:19])).seconds / 60)
        except:
            dur = 0
        tipo_map = {
            'HKWorkoutActivityTypeSwimming': 'Nuoto',
            'HKWorkoutActivityTypeRunning': 'Corsa',
            'HKWorkoutActivityTypeWalking': 'Camminata',
            'HKWorkoutActivityTypeCycling': 'Ciclismo',
            'HKWorkoutActivityTypeTraditionalStrengthTraining': 'Pesi',
            'HKWorkoutActivityTypeFunctionalStrengthTraining': 'Functional',
            'HKWorkoutActivityTypeTennis': 'Tennis',
            'HKWorkoutActivityTypeYoga': 'Yoga',
            'HKWorkoutActivityTypeHighIntensityIntervalTraining': 'HIIT',
            'HKWorkoutActivityTypeSurfingSports': 'Surf/Wingfoil',
            'HKWorkoutActivityTypeCoreTraining': 'CoreTraining',
            'HKWorkoutActivityTypeHiking': 'Hiking',
            'HKWorkoutActivityTypeSnowboarding': 'Snowboarding',
            'HKWorkoutActivityTypeWaterSports': 'WaterSports',
            'HKWorkoutActivityTypeOther': 'Other',
        }
        tipo = tipo_map.get(wtype, wtype.replace('HKWorkoutActivityType', ''))
        if sd_full[:10]:
            workouts.append({'tipo': tipo, 'data': sd_full[:10], 'durata_min': dur, 'kcal': round(kcal), 'week': iso_week(sd_full[:10])})
        elem.clear()

if cutoff_date:
    print(f"  Skippati {skipped:,} record precedenti al {cutoff_date}", flush=True)

# ── Elaborazione sonno ────────────────────────────────────────────────────
print("Elaborazione sonno...", flush=True)

def merge_intervals(intervals):
    nights = defaultdict(list)
    for s, e, night in intervals:
        nights[night].append((s, e))
    result = {}
    for night, ivs in nights.items():
        ivs.sort()
        merged = [list(ivs[0])]
        for s, e in ivs[1:]:
            if s < merged[-1][1]:
                merged[-1] = [merged[-1][0], max(merged[-1][1], e)]
            else:
                merged.append([s, e])
        mins = sum((e - s).total_seconds() / 60 for s, e in merged)
        result[night] = mins
    return result

sleep_by_week = {}
for wk, intervals in sleep_intervals_by_week.items():
    nights = merge_intervals(intervals)
    valid = [m for m in nights.values() if m > 120]
    if valid:
        sleep_by_week[wk] = valid

def dedup_workouts(ws):
    specific = [(w['tipo'], w['data'], w['durata_min']) for w in ws if w['tipo'] != 'Other']
    out = []
    seen = set()
    for w in ws:
        key = (w['tipo'], w['data'], w['durata_min'])
        if key in seen:
            continue
        seen.add(key)
        if w['tipo'] == 'Other':
            skip = any(d == w['data'] and abs(dur - w['durata_min']) <= 5
                       for t, d, dur in specific)
            if skip:
                continue
        if w['tipo'] == 'Camminata' and w['durata_min'] < 20:
            continue
        out.append(w)
    return out

workouts_by_week = defaultdict(list)
for w in workouts:
    workouts_by_week[w['week']].append(w)

# ── Costruisci settimane nuove ─────────────────────────────────────────────
all_weeks_new = sorted(set(
    list(passi_by_week) + list(kcal_attive_by_week) +
    list(workouts_by_week) + list(sleep_by_week)
))

# Peso storico (serve anche da vecchi dati)
peso_by_week = {}
for d, kg in sorted(peso_by_date.items()):
    peso_by_week[iso_week(d)] = {'kg': kg, 'data': d}

# Calcola il prev_peso dal confine tra dati vecchi e nuovi
all_existing_sorted = sorted(existing_weeks.values(), key=lambda s: s['settimana'])
prev_peso = None
if all_existing_sorted:
    for s in reversed(all_existing_sorted):
        if s.get('peso', {}).get('ultimo_kg') is not None:
            prev_peso = s['peso']['ultimo_kg']
            break

new_settimane = []
for wk in all_weeks_new:
    entry = {'settimana': wk, 'data_analisi': datetime.today().date().isoformat()}

    if wk in peso_by_week:
        p = peso_by_week[wk]
        delta = round(p['kg'] - prev_peso, 1) if prev_peso is not None else None
        entry['peso'] = {'ultimo_kg': p['kg'], 'data_rilevamento': p['data']}
        if delta is not None:
            entry['peso']['variazione_kg'] = delta
        prev_peso = p['kg']

    if wk in passi_by_week:
        tot = round(passi_by_week[wk])
        giorni = len(passi_days[wk])
        entry['passi'] = {'totale': tot, 'media_giorno': round(tot / max(giorni, 1))}

    if wk in kcal_attive_by_week:
        tot = round(kcal_attive_by_week[wk])
        entry['calorie_attive'] = {'totale': tot, 'media_giorno': round(tot / 7)}

    if wk in kcal_bmr_by_week and wk in kcal_attive_by_week:
        entry['calorie_totali_media'] = round((kcal_bmr_by_week[wk] + kcal_attive_by_week[wk]) / 7)

    if wk in workouts_by_week:
        ws = dedup_workouts(workouts_by_week[wk])
        if ws:
            entry['allenamenti'] = [
                {'tipo': w['tipo'], 'data': w['data'], 'durata_min': w['durata_min']}
                | ({'kcal': w['kcal']} if w['kcal'] > 0 else {})
                for w in ws
            ]

    if wk in sleep_by_week:
        nights = sleep_by_week[wk]
        entry['sonno'] = {
            'media_ore': round(sum(nights) / len(nights) / 60, 2),
            'min_ore': round(min(nights) / 60, 2),
            'max_ore': round(max(nights) / 60, 2)
        }

    if wk in fc_by_week:
        resting = [v for v in fc_by_week[wk] if v < 80]
        if resting:
            entry['fc_riposo_media'] = round(sum(resting) / len(resting))

    if len(entry) > 2:
        new_settimane.append(entry)

# ── Merge: esistenti (stabili) + nuove ────────────────────────────────────
merged = list(existing_weeks.values()) + new_settimane
merged.sort(key=lambda s: s['settimana'])

print(f"Settimane totali: {len(merged)}  ({merged[0]['settimana']} → {merged[-1]['settimana']})")
print(f"  Già presenti (stabili): {len(existing_weeks)}")
print(f"  Elaborate ora:          {len(new_settimane)}")

for s in merged[-2:]:
    print(f"\n{s['settimana']}:")
    if 'sonno' in s:      print(f"  Sonno: {s['sonno']}")
    if 'allenamenti' in s: print(f"  Allenamenti: {[a['tipo'] for a in s['allenamenti']]}")

with open(OUTPUT_PATH, 'w') as f:
    json.dump({"settimane": merged}, f, ensure_ascii=False, separators=(',', ':'))
print(f"\n✅ Salvato: {OUTPUT_PATH}")
