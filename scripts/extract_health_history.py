import xml.etree.ElementTree as ET
import json
from collections import defaultdict
from datetime import datetime, timedelta

XML_PATH = "/tmp/ah_extract/apple_health_export/dati esportati.xml"

def iso_week(date_str):
    d = datetime.fromisoformat(date_str[:10])
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"

print("Parsing XML...", flush=True)
context = ET.iterparse(XML_PATH, events=('end',))

peso_by_date = {}
passi_by_week = defaultdict(float)
passi_days = defaultdict(set)
kcal_attive_by_week = defaultdict(float)
kcal_bmr_by_week = defaultdict(float)
# Sleep: list of (start_dt, end_dt) per week — only "real sleep" stages
sleep_intervals_by_week = defaultdict(list)
fc_by_week = defaultdict(list)
workouts = []

SLEEP_ASLEEP = {
    'HKCategoryValueSleepAnalysisAsleepCore',
    'HKCategoryValueSleepAnalysisAsleepDeep',
    'HKCategoryValueSleepAnalysisAsleepREM',
    'HKCategoryValueSleepAnalysisAsleepUnspecified',
    'HKCategoryValueSleepAnalysisAsleep',
}

for event, elem in context:
    if elem.tag == 'Record':
        t = elem.get('type','')
        val = elem.get('value','')
        sd = elem.get('startDate','')
        ed = elem.get('endDate','')

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
                if mins > 10:  # ignora micro-segmenti
                    # Notte = usare la data di fine mattina (ore 0-14)
                    night_date = e_dt.date() if e_dt.hour < 14 else (e_dt.date() + timedelta(days=1))
                    wk = iso_week(night_date.isoformat())
                    sleep_intervals_by_week[wk].append((s_dt, e_dt, night_date.isoformat()))
            except: pass

        elem.clear()

    elif elem.tag == 'Workout':
        wtype = elem.get('workoutActivityType','')
        sd = elem.get('startDate','')
        ed_full = elem.get('endDate','')
        kcal = float(elem.get('totalEnergyBurned') or 0)
        try:
            dur = int((datetime.fromisoformat(ed_full[:19]) - datetime.fromisoformat(sd[:19])).seconds / 60)
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
            'HKWorkoutActivityTypeOther': 'Other',
        }
        tipo = tipo_map.get(wtype, wtype.replace('HKWorkoutActivityType',''))
        if sd[:10]:
            workouts.append({'tipo': tipo, 'data': sd[:10], 'durata_min': dur, 'kcal': round(kcal), 'week': iso_week(sd[:10])})
        elem.clear()

print("Elaborazione sonno...", flush=True)

# Calcola ore di sonno per notte usando merge di intervalli sovrapposti
def merge_intervals(intervals):
    """Unisce intervalli (start, end) sovrapposti, restituisce minuti totali per notte."""
    nights = defaultdict(list)
    for s, e, night in intervals:
        nights[night].append((s, e))
    result = {}
    for night, ivs in nights.items():
        ivs.sort()
        merged = [ivs[0]]
        for s, e in ivs[1:]:
            if s < merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))
            else:
                merged.append((s, e))
        mins = sum((e-s).total_seconds()/60 for s, e in merged)
        result[night] = mins
    return result

sleep_by_week = {}
for wk, intervals in sleep_intervals_by_week.items():
    nights = merge_intervals(intervals)
    valid = [m for m in nights.values() if m > 120]  # almeno 2h
    if valid:
        sleep_by_week[wk] = valid

# Workouts: rimuovi "Other" se c'è già un tipo specifico stesso giorno e durata simile
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
            # Salta se c'è un tipo specifico stesso giorno con durata simile (±5 min)
            skip = any(d == w['data'] and abs(dur - w['durata_min']) <= 5
                      for t, d, dur in specific)
            if skip:
                continue
        # Salta camminata < 20 min
        if w['tipo'] == 'Camminata' and w['durata_min'] < 20:
            continue
        out.append(w)
    return out

workouts_by_week = defaultdict(list)
for w in workouts:
    workouts_by_week[w['week']].append(w)

# Costruisci settimane
all_weeks = sorted(set(
    list(passi_by_week) + list(kcal_attive_by_week) +
    list(workouts_by_week) + list(sleep_by_week)
))

peso_by_week = {}
for d, kg in sorted(peso_by_date.items()):
    peso_by_week[iso_week(d)] = {'kg': kg, 'data': d}

settimane = []
prev_peso = None

for wk in all_weeks:
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
        media = round(sum(nights) / len(nights) / 60, 2)
        entry['sonno'] = {
            'media_ore': media,
            'min_ore': round(min(nights) / 60, 2),
            'max_ore': round(max(nights) / 60, 2)
        }

    if wk in fc_by_week:
        resting = [v for v in fc_by_week[wk] if v < 80]
        if resting:
            entry['fc_riposo_media'] = round(sum(resting) / len(resting))

    if len(entry) > 2:
        settimane.append(entry)

print(f"Settimane: {len(settimane)}  ({settimane[0]['settimana']} → {settimane[-1]['settimana']})")

# Verifica ultime settimane
for s in settimane[-2:]:
    print(f"\n{s['settimana']}:")
    if 'sonno' in s: print(f"  Sonno: {s['sonno']}")
    if 'allenamenti' in s: print(f"  Allenamenti: {[a['tipo'] for a in s['allenamenti']]}")

with open("/tmp/health_history_new.json", "w") as f:
    json.dump({"settimane": settimane}, f, ensure_ascii=False, indent=2)
print("\nSalvato!")
