#!/usr/bin/env python3
"""
extract_workout_details.py — Aggiornamento incrementale di workout_details.json

Uso:
  python3 extract_workout_details.py <xml_path> <output_path> [--height-m 1.70] [--max-hr 195]

Logica incrementale:
  - Se output_path esiste, trova l'ultimo workout già salvato
  - Processa solo workout successivi a quella data
  - Appende i nuovi workout al file esistente
"""

import sys, argparse, xml.etree.ElementTree as ET, json, bisect
from datetime import datetime, timedelta
from collections import defaultdict

ap = argparse.ArgumentParser()
ap.add_argument('xml_path')
ap.add_argument('output_path')
ap.add_argument('--height-m', type=float, default=1.70)
ap.add_argument('--max-hr',   type=int,   default=195)
args = ap.parse_args()

XML_PATH    = args.xml_path
OUTPUT_PATH = args.output_path
HEIGHT_M    = args.height_m
MAX_HR      = args.max_hr

def parse_dt(s):
    try: return datetime.fromisoformat(s[:19])
    except: return None

def iso_week(dt):
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"

TIPO_MAP = {
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
    'HKWorkoutActivityTypeOther': None,
}
DIST_MAP = {
    'HKQuantityTypeIdentifierDistanceCycling':           'cycling',
    'HKQuantityTypeIdentifierDistanceWalkingRunning':    'run',
    'HKQuantityTypeIdentifierDistanceSwimming':          'swim',
    'HKQuantityTypeIdentifierDistanceDownhillSnowSports':'snow',
}
TIPO_DIST = {
    'Nuoto':'swim','Ciclismo':'cycling','Corsa':'run',
    'Camminata':'run','Hiking':'run','Snowboarding':'snow','WaterSports':'swim',
}

# ── Carica esistente (incrementale) ───────────────────────────────────────
existing_workouts = []
cutoff_dt = None

try:
    with open(OUTPUT_PATH) as f:
        existing_data = json.load(f)
    existing_workouts = existing_data.get('workouts', [])
    MAX_HR    = existing_data.get('max_hr_ref', MAX_HR)
    HEIGHT_M  = existing_data.get('height_m', HEIGHT_M)
    if existing_workouts:
        # L'ultimo workout nel file (sono in ordine desc)
        latest_id = existing_workouts[0]['id']  # più recente
        cutoff_dt = datetime.fromisoformat(latest_id) - timedelta(days=1)
        # già processati: escludi l'ultimo (potrebbe essere parziale → lo ri-elaboriamo)
        existing_workouts = [w for w in existing_workouts if w['id'] < latest_id]
        print(f"Incrementale: {len(existing_workouts)+1} workout già presenti, riprocesso da {cutoff_dt.date()}", flush=True)
except (FileNotFoundError, json.JSONDecodeError):
    print("Nessun dato esistente — parsing completo", flush=True)

cutoff_str = cutoff_dt.date().isoformat() if cutoff_dt else None

# ── Parsing XML ────────────────────────────────────────────────────────────
print("Parsing XML...", flush=True)
context = ET.iterparse(XML_PATH, events=('end',))

workouts_raw = []
hr_pairs     = []   # (datetime, bpm)
dist_data    = defaultdict(list)   # cat -> [(dt, km)]
kcal_data    = []   # (dt, kcal)

skipped = 0
for event, elem in context:
    if elem.tag == 'Record':
        t   = elem.get('type', '')
        val = elem.get('value', '')
        sd  = elem.get('startDate', '')

        if cutoff_str and sd and sd[:10] < cutoff_str:
            skipped += 1; elem.clear(); continue

        if t == 'HKQuantityTypeIdentifierHeartRate' and val and sd:
            dt = parse_dt(sd)
            if dt:
                try: hr_pairs.append((dt, float(val)))
                except: pass

        elif t in DIST_MAP and val and sd:
            dt = parse_dt(sd)
            if dt:
                try:
                    unit = elem.get('unit','')
                    km = float(val)
                    if unit in ('m','meters'): km /= 1000
                    dist_data[DIST_MAP[t]].append((dt, km))
                except: pass

        elif t == 'HKQuantityTypeIdentifierActiveEnergyBurned' and val and sd:
            dt = parse_dt(sd)
            if dt:
                try: kcal_data.append((dt, float(val)))
                except: pass

        elem.clear()

    elif elem.tag == 'Workout':
        wtype  = elem.get('workoutActivityType', '')
        sd_str = elem.get('startDate', '')
        ed_str = elem.get('endDate', '')
        tipo   = TIPO_MAP.get(wtype, wtype.replace('HKWorkoutActivityType',''))
        if tipo is None: elem.clear(); continue
        if cutoff_str and sd_str and sd_str[:10] < cutoff_str:
            elem.clear(); continue
        s_dt, e_dt = parse_dt(sd_str), parse_dt(ed_str)
        if s_dt and e_dt:
            dur = int((e_dt - s_dt).total_seconds() / 60)
            if dur > 5 and not (tipo == 'Camminata' and dur < 20):
                workouts_raw.append({'tipo':tipo,'start':s_dt,'end':e_dt,'dur':dur})
        elem.clear()

if cutoff_str:
    print(f"  Skippati {skipped:,} record precedenti al {cutoff_str}", flush=True)
print(f"  {len(hr_pairs)} HR · {len(workouts_raw)} workout nuovi", flush=True)

# Sort
hr_pairs.sort(key=lambda x: x[0])
hr_dts  = [x[0] for x in hr_pairs]
hr_bpm  = [x[1] for x in hr_pairs]
for cat in dist_data:
    dist_data[cat].sort(key=lambda x: x[0])
kcal_data.sort(key=lambda x: x[0])
kcal_dts  = [x[0] for x in kcal_data]
kcal_vals = [x[1] for x in kcal_data]

def window(dts, s, e):
    return bisect.bisect_left(dts, s), bisect.bisect_right(dts, e)

def hr_zone(bpm, mhr):
    p = bpm / mhr
    if p < .50: return 1
    if p < .60: return 2
    if p < .70: return 3
    if p < .80: return 4
    return 5

# ── Elabora nuovi workout ─────────────────────────────────────────────────
print("Elaborazione workout...", flush=True)
new_workouts = []

for w in workouts_raw:
    s, e = w['start'], w['end']

    i, j = window(hr_dts, s, e)
    w_hr_dts = hr_dts[i:j]; w_hr_bpm = hr_bpm[i:j]
    hr_avg = round(sum(w_hr_bpm)/len(w_hr_bpm)) if w_hr_bpm else None
    hr_max = round(max(w_hr_bpm)) if w_hr_bpm else None

    zones = defaultdict(float)
    if len(w_hr_dts) > 1:
        for k in range(len(w_hr_dts)-1):
            gap = (w_hr_dts[k+1]-w_hr_dts[k]).total_seconds()/60
            if 0 < gap < 5:
                zones[hr_zone(w_hr_bpm[k], MAX_HR)] += gap

    # Timeline HR (1 pt/minuto)
    timeline = []
    if w_hr_dts:
        by_min = defaultdict(list)
        for dt, bpm in zip(w_hr_dts, w_hr_bpm):
            by_min[int((dt-s).total_seconds()/60)].append(bpm)
        for m in sorted(by_min):
            timeline.append({'t':m,'bpm':round(sum(by_min[m])/len(by_min[m]))})
        if len(timeline) > 150:
            step = max(1,len(timeline)//120)
            timeline = timeline[::step]

    cat = TIPO_DIST.get(w['tipo'])
    dist_km = None
    if cat and cat in dist_data:
        dts2 = [x[0] for x in dist_data[cat]]
        di, dj = window(dts2, s, e)
        total = sum(x[1] for x in dist_data[cat][di:dj])
        if total > 0: dist_km = round(total, 2)

    ki, kj = window(kcal_dts, s, e)
    kcal = round(sum(kcal_vals[ki:kj])) or None

    speed_kmh = pace_minkm = None
    if dist_km and dist_km > 0 and w['dur'] > 0:
        speed_kmh = round(dist_km / (w['dur']/60), 1)
        if w['tipo'] in ('Corsa','Camminata','Hiking'):
            pace_minkm = round(w['dur']/dist_km, 2)

    entry = {
        'id': s.isoformat(), 'tipo': w['tipo'],
        'data': s.date().isoformat(), 'settimana': iso_week(s),
        'ora_inizio': s.strftime('%H:%M'), 'durata_min': w['dur'],
    }
    if kcal:       entry['calorie']      = kcal
    if dist_km:    entry['distanza_km']  = dist_km
    if speed_kmh:  entry['velocita_kmh'] = speed_kmh
    if pace_minkm: entry['passo_minkm']  = pace_minkm
    if hr_avg:     entry['hr_avg']       = hr_avg
    if hr_max:     entry['hr_max']       = hr_max
    if zones:      entry['hr_zones']     = {f'z{k}':round(v,1) for k,v in sorted(zones.items())}
    if timeline:   entry['_hr_timeline'] = timeline  # tenuto separato dal salvataggio
    new_workouts.append(entry)

# ── Merge e salva ─────────────────────────────────────────────────────────
all_workouts = existing_workouts + new_workouts
all_workouts.sort(key=lambda x: x['id'], reverse=True)

# Carica timelines esistenti e unisci le nuove
import os as _os
timelines_path = _os.path.join(_os.path.dirname(OUTPUT_PATH), 'workout_timelines.json')
try:
    with open(timelines_path) as f:
        all_timelines = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    all_timelines = {}

for w in all_workouts:
    tl = w.pop('_hr_timeline', None)
    if tl:
        all_timelines[w['id']] = tl

# workout_details.json — leggero, senza timeline
result = {'max_hr_ref': MAX_HR, 'height_m': HEIGHT_M, 'workouts': all_workouts}
with open(OUTPUT_PATH, 'w') as f:
    json.dump(result, f, ensure_ascii=False, separators=(',',':'))

# workout_timelines.json — caricato lazy dal browser solo al click
with open(timelines_path, 'w') as f:
    json.dump(all_timelines, f, ensure_ascii=False, separators=(',',':'))

print(f"\n✅ {len(all_workouts)} workout totali ({len(new_workouts)} nuovi)")
print(f"   workout_details.json:   {_os.path.getsize(OUTPUT_PATH)//1024} KB")
print(f"   workout_timelines.json: {_os.path.getsize(timelines_path)//1024} KB")
for w in new_workouts[:4]:
    print(f"  {w['tipo']:15s} {w['data']} {w['durata_min']}min hr={w.get('hr_avg','—')}/{w.get('hr_max','—')} dist={w.get('distanza_km','—')}km")
