#!/usr/bin/env python3
"""
Faz E - ML Eğitim Seti Oluşturucu (build_dataset.py)
══════════════════════════════════════════════════════════
Tüm "data/daily" geçmişini tarar (15.2M+ satır).
Veriyi 10 dakikalık pencerelere (windows) böler.
Her pencere için:
 - Sensör mean, max, min, std
 - Slope (Eğim) ve Volatility
 - Boolean flagler (filter_dirty_minutes)
hesaplar. "total_faults_window" gibi leaky feature'ları BARINDIRMAZ!

Çıktı: data/ml_training_data_v2.csv
"""

import sys
import json
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from scipy import stats
import yaml

TARGET_CSV = "data/ml_training_data_v2.csv"
WINDOW_MINS = 10

HPR_SENSORS = [
    "oil_tank_temperature",
    "main_pressure",
    "horizontal_press_pressure",
    "lower_ejector_pressure",
    "horitzonal_infeed_speed",
    "vertical_infeed_speed",
]

def parse_iso(ts_str):
    try:
        ts_str = ts_str.replace('Z', '+00:00')
        if '.' in ts_str and '+' in ts_str:
            main_p, tz_p = ts_str.rsplit('+', 1)
            if len(main_p.split('.')[1]) > 6:
                main_p = main_p.split('.')[0] + '.' + main_p.split('.')[1][:6]
                ts_str = f"{main_p}+{tz_p}"
        return datetime.fromisoformat(ts_str)
    except:
        return None

def main():
    print("=" * 60)
    print("🚀 FAZ E - ML TRAINING DATASET BUILDER")
    print("=" * 60)
    
    # Load limits to determine if a FAULT occurred
    try:
        with open("config/limits_config.yaml") as f:
            config = yaml.safe_load(f)
            limits = config.get("machine_limits", {})
            hpr001_limits = limits.get("HPR001", {})
    except:
        print("❌ config/limits_config.yaml bulunamadı!")
        return

    base_dir = Path("data/daily")
    if not base_dir.exists():
        print("❌ data/daily bulunamadı.")
        return

    folders = sorted([d for d in base_dir.iterdir() if d.is_dir() and len(d.name) == 10])
    
    # Her makine, her 10 dk'lık interval için liste tutacağız
    # window_data[machine_id][interval_start] = { 'numeric': {sensor: []}, 'boolean': ... }
    window_data = defaultdict(lambda: defaultdict(lambda: {'numeric': defaultdict(list), 'faults': 0}))
    
    total_read = 0
    t0 = time.time()
    
    print(f"📂 Okunacak gün sayısı: {len(folders)}")
    
    for folder in folders:
        file_path = folder / "raw_messages.jsonl"
        if not file_path.exists(): continue
        
        print(f"⏳ Taranıyor: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                total_read += 1
                try:
                    data = json.loads(line)
                    mid = data.get("machine_id")
                    if not mid or not mid.startswith("HPR"): continue
                    
                    ts = parse_iso(data.get("timestamp"))
                    if not ts: continue
                    
                    # Yuvarlama: 10 dakikalık gruba oturt
                    # dakikayı 10'un katlarına yuvarla
                    minute = (ts.minute // WINDOW_MINS) * WINDOW_MINS
                    interval_start = ts.replace(minute=minute, second=0, microsecond=0)
                    
                    num = data.get("numeric", {})
                    
                    w_ref = window_data[mid][interval_start]
                    
                    # FAULT KONTROLÜ
                    is_fault = False
                    for s_name, val in num.items():
                        w_ref['numeric'][s_name].append(val)
                        # Threshold kontrolü (warn_level veya max üzerinden)
                        lims = limits.get(mid, hpr001_limits).get(s_name)
                        if lims and val is not None:
                            max_val = lims.get("max")
                            warn_val = lims.get("warn_level", abs(max_val) * 0.85 if max_val else None)
                            if warn_val and abs(val) >= warn_val:
                                is_fault = True
                                
                    if is_fault:
                        w_ref['faults'] += 1
                        
                except Exception as e:
                    pass
                    
                if total_read % 1000000 == 0:
                    print(f"  ... {total_read/1000000:.1f} Milyon satır okundu.")

    print(f"\n✅ Okuma tamamlandı! Toplam {total_read} mesaj. (Süre: {time.time()-t0:.1f}s)")
    print("🧠 Feature Engineering (Slope, Volatility vb.) Hesaplanıyor...")
    
    t1 = time.time()
    rows = []
    
    for mid, intervals in window_data.items():
        sorted_intervals = sorted(intervals.keys())
        
        for i, dt in enumerate(sorted_intervals):
            w = intervals[dt]
            
            # Etiket belirleme
            # Eğer bu pencerede fault varsa -> FAULT (1)
            # Eğer BİR SONRAKİ pencerede fault varsa -> PRE-FAULT (1)
            # Diğerleri -> NORMAL (0)
            is_fault_now = (w['faults'] > 0)
            
            is_fault_next = False
            if i + 1 < len(sorted_intervals):
                next_dt = sorted_intervals[i+1]
                # Sadece ardışık pencerelerse
                if next_dt == dt + timedelta(minutes=WINDOW_MINS):
                    if intervals[next_dt]['faults'] > 0:
                        is_fault_next = True
            
            label = "NORMAL"
            binary_label = 0
            if is_fault_now:
                label = "FAULT"
                binary_label = 1
            elif is_fault_next:
                label = "PRE-FAULT"
                binary_label = 1
                
            row = {
                "machine_id": mid,
                "timestamp": dt.isoformat(),
                "hour_of_day": dt.hour,
                "month_of_year": dt.month,
                "label": label,
                "binary_label": binary_label
            }
            
            for s in HPR_SENSORS:
                vals = w['numeric'].get(s, [])
                if not vals or len(vals) < 3:
                    row[f"{s}_mean"] = 0.0
                    row[f"{s}_max"] = 0.0
                    row[f"{s}_std"] = 0.0
                    row[f"{s}_slope"] = 0.0
                    row[f"{s}_volatility"] = 0.0
                else:
                    mean_v = float(np.mean(vals))
                    std_v = float(np.std(vals))
                    x = np.arange(len(vals))
                    slope, _, _, _, _ = stats.linregress(x, vals)
                    
                    row[f"{s}_mean"] = round(mean_v, 2)
                    row[f"{s}_max"] = round(float(np.max(vals)), 2)
                    row[f"{s}_std"] = round(std_v, 2)
                    row[f"{s}_slope"] = round(float(slope * 6), 4) # 1 dakikaya normalize et (1 dakkada ~6 mesaj vs. önemsiz oransal olarak)
                    row[f"{s}_volatility"] = round(float(std_v / mean_v if mean_v != 0 else 0), 4)
                    
            rows.append(row)

    df = pd.DataFrame(rows)
    print(f"✅ Özellik çıkarımı tamamlandı! Şekil: {df.shape} (Süre: {time.time()-t1:.1f}s)")
    
    print("\n📊 Etiket Dağılımı:")
    print(df['label'].value_counts())
    
    df.to_csv(TARGET_CSV, index=False)
    print(f"\n💾 Veri seti başarıyla {TARGET_CSV} konumuna kaydedildi!")

if __name__ == '__main__':
    main()
