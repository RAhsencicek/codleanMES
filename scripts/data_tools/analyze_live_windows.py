"""
analyze_live_windows.py — Live Windows Veri Analizi
═══════════════════════════════════════════════════
live_windows.json'u analiz eder, violation_log ile compare eder.
"""

import json
import pandas as pd
from datetime import datetime

print("\n" + "╔" + "═"*53 + "╗")
print("║" + " "*15 + "LIVE WINDOWS VERİ ANALİZİ" + " "*15 + "║")
print("╚" + "═"*53 + "╝")

# ─── YÜKLEME ──────────────────────────────────────────────────────────────
print("\n📂 live_windows.json yükleniyor...\n")

with open("live_windows.json") as f:
    live_data = json.load(f)

meta = live_data.get("meta", {})
normal_windows = live_data.get("normal_windows", [])
fault_windows = live_data.get("fault_windows", [])

print(f"✅ Yüklendi!")
print(f"\n📊 META BİLGİLER:")
print(f"   Toplam window: {meta.get('total_windows', 'N/A')}")
print(f"   Normal window: {len(normal_windows):,}")
print(f"   Fault window:  {len(fault_windows):,}")

if len(normal_windows) + len(fault_windows) > 0:
    fault_rate = len(fault_windows) / (len(normal_windows) + len(fault_windows)) * 100
    print(f"   Fault rate:    %{fault_rate:.2f}")

# ─── TARİH ARALIĞI ────────────────────────────────────────────────────────
print("\n📅 TARİH ARALIĞI ANALİZİ\n")

all_windows = normal_windows + fault_windows

if all_windows:
    # Timestamp'leri topla
    timestamps = []
    for w in all_windows[:100]:  # İlk 100 örnek
        ts = w.get("timestamp") or w.get("window_start")
        if ts:
            timestamps.append(ts)
    
    if timestamps:
        print(f"   İlk timestamp: {timestamps[0]}")
        print(f"   Son timestamp: {timestamps[-1]}")
        print(f"   Örneklem:      İlk 100 window")

# ─── MAKİNE DAĞILIMI ──────────────────────────────────────────────────────
print("\n🏭 MAKİNE BAZLI DAĞILIM\n")

machine_counts = {}
for w in all_windows[:500]:  # İlk 500 örnek
    machine_id = w.get("machine_id", "N/A")
    machine_counts[machine_id] = machine_counts.get(machine_id, 0) + 1

print("   Makine dağılımı (ilk 500 window):")
for machine, count in sorted(machine_counts.items(), key=lambda x: -x[1])[:10]:
    pct = count / 500 * 100
    print(f"      {machine}: {count} window (%{pct:.1f})")

# ─── FAULT TİPLERİ ────────────────────────────────────────────────────────
print("\n⚠️  FAULT TİPLERİ ANALİZİ\n")

if fault_windows:
    fault_sensors = {}
    for w in fault_windows[:100]:  # İlk 100 fault
        violations = w.get("violations", [])
        for v in violations:
            sensor = v.get("sensor_name", v.get("sensor", "N/A"))
            fault_sensors[sensor] = fault_sensors.get(sensor, 0) + 1
    
    print("   En sık görülen fault'lar (ilk 100 fault):")
    for sensor, count in sorted(fault_sensors.items(), key=lambda x: -x[1])[:10]:
        print(f"      {sensor}: {count} kez")
else:
    print("   ⚠️  Fault window yok!")

# ─── SENSÖR DEĞERLERİ İSTATİSTİKLERİ ─────────────────────────────────────
print("\n📊 SENSÖR DEĞERLERİ İSTATİSTİKLERİ\n")

# Sensör değerlerini topla
sensor_values = {}
for w in all_windows[:200]:  # İlk 200 window
    items = w.get("items", []) or w.get("sensor_values", [])
    for item in items:
        sensor = item.get("name", item.get("sensor", "N/A"))
        value = item.get("value")
        
        if value is not None and isinstance(value, (int, float)):
            if sensor not in sensor_values:
                sensor_values[sensor] = []
            sensor_values[sensor].append(value)

# İstatistikleri hesapla
print("   Sensör istatistikleri (ilk 200 window):\n")
for sensor in ["main_pressure", "horizontal_press_pressure", "oil_tank_temperature"][:3]:
    if sensor in sensor_values:
        values = sensor_values[sensor]
        if values:
            import numpy as np
            mean_val = np.mean(values)
            std_val = np.std(values)
            min_val = np.min(values)
            max_val = np.max(values)
            
            print(f"   {sensor}:")
            print(f"      Mean: {mean_val:.2f}")
            print(f"      Std:  {std_val:.2f}")
            print(f"      Min:  {min_val:.2f}")
            print(f"      Max:  {max_val:.2f}")
            print()

# ─── VIOLATION_LOG İLE KARŞILAŞTIRMA ─────────────────────────────────────
print("\n📋 VIOLATION_LOG İLE KARŞILAŞTIRMA\n")

try:
    with open("violation_log.json") as f:
        violation_data = json.load(f)
    
    violation_meta = violation_data.get("scan_stats", {})
    
    print("   LIVE WINDOWS vs VIOLATION LOG:\n")
    print(f"   {'Metric':<25} | {'Live':<15} | {'Violation':<15}")
    print(f"   {'─'*25}─┼{'─'*15}─┼{'─'*15}")
    
    # Total windows
    live_total = len(all_windows)
    violation_total = violation_meta.get("total_windows", violation_meta.get("total", "N/A"))
    print(f"   {'Total Windows':<25} | {str(live_total):<15} | {str(violation_total):<15}")
    
    # Fault windows
    live_faults = len(fault_windows)
    violation_faults = violation_meta.get("fault_windows", violation_meta.get("faults", "N/A"))
    print(f"   {'Fault Windows':<25} | {str(live_faults):<15} | {str(violation_faults):<15}")
    
    # Fault rate
    live_rate = (live_faults / live_total * 100) if live_total > 0 else 0
    violation_rate = violation_meta.get("fault_rate", "N/A")
    if isinstance(violation_rate, (int, float)):
        violation_rate = f"%{violation_rate:.2f}"
    print(f"   {'Fault Rate':<25} | %{live_rate:.2f}{'':<10} | {str(violation_rate):<15}")
    
    print("\n   ✅ İki dosya karşılaştırıldı!")
    
except FileNotFoundError:
    print("   ⚠️  violation_log.json bulunamadı!")
except Exception as e:
    print(f"   ⚠️  Karşılaştırma hatası: {e}")

# ─── VALIDATION SET OLARAK KULLANILABİLİRLİK ─────────────────────────────
print("\n🎯 VALIDATION SET OLARAK KULLANILABİLİRLİK\n")

# Kriterler
criteria = {
    "Yeterli büyüklük": len(all_windows) >= 100,
    "Fault/various samples": len(fault_windows) >= 10,
    "Timestamp mevcut": bool(timestamps),
    "Sensor values mevcut": bool(sensor_values),
    "Format tutarlı": "items" in str(all_windows[:1]) or "sensor_values" in str(all_windows[:1]),
}

print("   Validation set kriterleri:\n")
for criterion, passed in criteria.items():
    status = "✅" if passed else "❌"
    print(f"      {status} {criterion}")

# Genel değerlendirme
passed_count = sum(criteria.values())
total_count = len(criteria)

print(f"\n   📊 Skor: {passed_count}/{total_count} kriter geçti")

if passed_count == total_count:
    print("   ✅ MÜKEMMEL! Validation set olarak kullanıma hazır!")
elif passed_count >= total_count - 1:
    print("   ✅ İYİ! Küçük eksiklikler var ama kullanılabilir.")
else:
    print("   ⚠️  DİKKAT! Bazı kriterler geçmedi, dikkatli kullanın.")

# ─── SONUÇ VE ÖNERİLER ───────────────────────────────────────────────────
print("\n" + "="*55)
print("SONUÇ VE ÖNERİLER")
print("="*55)

print("\n💡 BULGULAR:")
print(f"   • Toplam {len(all_windows)} window bulundu")
print(f"   • {len(fault_windows)} fault eventi var")
print(f"   • {len(sensor_values)} farklı sensör verisi var")

print("\n🎯 ÖNERİLER:")

if len(fault_windows) >= 10:
    print("   ✅ Model testi için yeterli fault var")
    print("   → live_windows.json üzerinde inference yapabiliriz")
    print("   → Gerçek performance metrikleri hesaplayabiliriz")
else:
    print("   ⚠️  Fault sayısı az (<10)")
    print("   → Sadece normal operasyon testi için kullanılır")
    print("   → Model validation için yeterli değil")

if timestamps:
    print("   ✅ Timestamp analizi yapılabilir")
    print("   → Temporal pattern detection mümkün")

print("\n📋 SONRAKİ ADIMLAR:")
print("   1. ✅ live_windows.json validation set olarak kullan")
print("   2. ✅ Model'i bu veriyle test et")
print("   3. ✅ Gerçek performance metrikleri hesapla")
print("   4. ✅ violation_log.json sonuçları ile compare et")

print("\n" + "="*55)
print("ANALİZ TAMAMLANDI")
print("="*55 + "\n")
