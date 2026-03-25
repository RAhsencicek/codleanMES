"""
batch_alert_analysis.py — Violation Log Batch Processing
══════════════════════════════════════════════════════════
violation_log.json'dan 1000+ window oku, alert üret, analiz et.
"""

import json
import yaml
from datetime import datetime
from collections import Counter
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from src.alerts.alert_engine import generate_hybrid_alert

console = Console()

print("\n" + "╔" + "═"*60 + "╗")
print("║" + " "*15 + "VIOLATION LOG BATCH ANALYSIS" + " "*15 + "║")
print("╚" + "═"*60 + "╝")

# ──────────────────────────────────────────────────────────────
# VERİ YÜKLEME
# ──────────────────────────────────────────────────────────────
print("\n📂 violation_log.json yükleniyor...\n")

with open("data/violation_log.json") as f:
    violation_data = json.load(f)

# Windows'ları çıkar
fault_windows = violation_data.get("fault_windows", [])
normal_windows = violation_data.get("normal_windows", [])

print(f"✅ Yüklendi!")
print(f"   Fault windows:  {len(fault_windows):,}")
print(f"   Normal windows: {len(normal_windows):,}")
print(f"   Toplam:         {(len(fault_windows) + len(normal_windows)):,}")

# Config yükle
with open("limits_config.yaml") as f:
    CONFIG = yaml.safe_load(f)

LIMITS = CONFIG.get("machine_limits", {})

# ──────────────────────────────────────────────────────────────
# ÖRNEKLEM ALMA (İlk 1000 window)
# ──────────────────────────────────────────────────────────────
print("\n⏳ İlk 1000 window işleniyor...\n")

# Stratified sampling yap (hem fault hem normal olsun)
sample_size = min(1000, len(fault_windows) + len(normal_windows))

# %20 fault, %80 normal (gerçek dağılıma yakın)
fault_sample_size = int(sample_size * 0.20)
normal_sample_size = sample_size - fault_sample_size

fault_sample = fault_windows[:fault_sample_size]
normal_sample = normal_windows[:normal_sample_size]

all_samples = fault_sample + normal_sample

print(f"   Fault samples:  {len(fault_sample)}")
print(f"   Normal samples: {len(normal_sample)}")
print(f"   Toplam:         {len(all_samples)}\n")

# ──────────────────────────────────────────────────────────────
# ALERT ÜRETİMİ
# ──────────────────────────────────────────────────────────────
alert_counts = Counter()
severity_counts = Counter()
alert_types = []

for i, window in enumerate(all_samples):
    # Window data
    machine_id = window.get("machine_id", "HPR001")
    sensor_values = {}
    
    # Sensor values'ı çıkar (format'a göre)
    items = window.get("items", []) or window.get("sensor_values", [])
    for item in items:
        name = item.get("name", item.get("sensor"))
        value = item.get("value")
        if name and value is not None:
            sensor_values[name] = value
    
    # Alert üret
    alerts = generate_hybrid_alert(machine_id, sensor_values, {}, LIMITS)
    
    # Alert sayılarını topla
    if alerts:
        for alert in alerts:
            alert_type = alert['type']
            severity = alert.get('severity', 'N/A')
            
            alert_counts[alert_type] += 1
            severity_counts[severity] += 1
            
            if alert_type == 'FAULT':
                alert_types.append(('🔴 FAULT', severity))
            elif alert_type == 'SOFT_LIMIT_WARNING':
                alert_types.append(('⚠️  SOFT', 'DÜŞÜK'))
            elif alert_type == 'PRE_FAULT_WARNING':
                alert_types.append(('🟡 PRE-FAULT', 'ORTA'))
    else:
        alert_types.append(('✅ NORMAL', '-'))
    
    # Progress
    if (i + 1) % 100 == 0:
        print(f"   İşlendi: {i+1}/{len(all_samples)} ({(i+1)/len(all_samples)*100:.0f}%)")

print(f"   İşlendi: {len(all_samples)}/{len(all_samples)} (100%)\n")

# ──────────────────────────────────────────────────────────────
# ANALİZ SONUÇLARI
# ──────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("ANALİZ SONUÇLARI")
print("="*60)

# Alert distribution table
table = Table(title="Alert Distribution", box=box.ROUNDED)
table.add_column("Alert Type", style="bold")
table.add_column("Count", justify="right")
table.add_column("Percentage", justify="right")
table.add_column("Visual")

total_alerts = sum(alert_counts.values())
total_windows = len(all_samples)

for alert_type, count in sorted(alert_counts.items(), key=lambda x: -x[1]):
    percentage = count / total_windows * 100
    bar_length = int(percentage / 2)
    bar = "█" * bar_length
    
    table.add_row(
        alert_type,
        f"{count:,}",
        f"%{percentage:.1f}",
        bar
    )

# No alert
no_alert_count = total_windows - total_alerts
no_alert_pct = no_alert_count / total_windows * 100
bar_length = int(no_alert_pct / 2)
bar = "░" * bar_length

table.add_row(
    "✅ NORMAL (No Alert)",
    f"{no_alert_count:,}",
    f"%{no_alert_pct:.1f}",
    bar
)

console.print("\n")
console.print(table)

# Severity distribution
print("\n" + "-"*60)
print("SEVERITY DAĞILIMI")
print("-"*60)

severity_table = Table(title="Severity Distribution", box=box.ROUNDED)
severity_table.add_column("Severity", style="bold")
severity_table.add_column("Count", justify="right")
severity_table.add_column("Percentage", justify="right")

total_severity = sum(severity_counts.values())

for severity, count in sorted(severity_counts.items(), key=lambda x: -x[1]):
    percentage = count / total_severity * 100 if total_severity > 0 else 0
    
    severity_table.add_row(
        severity,
        f"{count:,}",
        f"%{percentage:.1f}"
    )

console.print("\n")
console.print(severity_table)

# ──────────────────────────────────────────────────────────────
# FAULT TİPLERİ ANALİZİ
# ──────────────────────────────────────────────────────────────
print("\n" + "-"*60)
print("FAULT TİPLERİ ANALİZİ (Fault Windows)")
print("-"*60)

fault_sensor_counts = Counter()
for window in fault_sample:
    violations = window.get("violations", [])
    for v in violations:
        sensor = v.get("sensor_name", v.get("sensor"))
        if sensor:
            fault_sensor_counts[sensor] += 1

print("\nEn sık görülen fault sensörleri:\n")
for sensor, count in sorted(fault_sensor_counts.items(), key=lambda x: -x[1])[:10]:
    pct = count / len(fault_sample) * 100 if fault_sample else 0
    bar_len = int(pct / 3)
    bar = "▓" * bar_len
    print(f"  {sensor:<35} {count:>4} (%{pct:>5.1f}) {bar}")

# ──────────────────────────────────────────────────────────────
# ÖRNEK ALERT ÇIKTILARI
# ──────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("ÖRNEK ALERT ÇIKTILARI")
print("="*60)

# İlk 3 fault alert'i göster
fault_alerts_shown = 0
for i, window in enumerate(fault_sample[:5]):
    if fault_alerts_shown >= 3:
        break
        
    machine_id = window.get("machine_id", "HPR001")
    sensor_values = {}
    
    items = window.get("items", [])
    for item in items:
        name = item.get("name")
        value = item.get("value")
        if name and value is not None:
            sensor_values[name] = value
    
    alerts = generate_hybrid_alert(machine_id, sensor_values, {}, LIMITS)
    
    if alerts and alerts[0]['type'] == 'FAULT':
        fault_alerts_shown += 1
        console.print(f"\n[bold red]┌─ Örnek Alert #{fault_alerts_shown}[/bold red]")
        
        alert = alerts[0]
        console.print(Panel(
            f"[bold]Makine:[/bold] {machine_id}\n"
            f"[bold]Tip:[/bold] {alert['type']}\n"
            f"[bold]Severity:[/bold] {alert['severity']}\n"
            f"[bold]Confidence:[/bold] %{alert['confidence']*100:.0f}\n"
            f"[bold]Sebep:[/bold] {alert['reasons'][0]}\n"
            f"[bold]Öneri:[/bold] {alert['recommendation']}",
            title=f"FAULT Alert Example",
            border_style="red"
        ))

# ──────────────────────────────────────────────────────────────
# ÖZET VE ÖNERİLER
# ──────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("ÖZET VE ÖNERİLER")
print("="*60)

print(f"\n📊 İSTATİSTİKLER:")
print(f"   Toplam window: {len(all_samples):,}")
print(f"   Alert üretilen: {total_alerts:,} (%{total_alerts/len(all_samples)*100:.1f})")
print(f"   Alert olmayan: {no_alert_count:,} (%{no_alert_pct:.1f})")

print(f"\n🎯 BULGULAR:")

if alert_counts['FAULT'] > 0:
    print(f"   ✅ FAULT alert'leri: {alert_counts['FAULT']} ({alert_counts['FAULT']/len(all_samples)*100:.1f}%)")
    print(f"      → Gerçek arızaları yakalıyor")
else:
    print(f"   ⚠️  FAULT alert bulunamadı")

if alert_counts['SOFT_LIMIT_WARNING'] > 0:
    print(f"   ✅ SOFT_LIMIT_WARNING: {alert_counts['SOFT_LIMIT_WARNING']}")
    print(f"      → Erken uyarı sistemi çalışıyor")

if no_alert_pct > 70:
    print(f"   ✅ Normal operasyon yüksek (%{no_alert_pct:.1f})")
    print(f"      → False positive düşük (iyi!)")
else:
    print(f"   ⚠️  Alert rate yüksek (%{100-no_alert_pct:.1f})")
    print(f"      → Alert fatigue riski var")

print(f"\n💡 TECHNICIAN FEEDBACK İÇİN:")
print(f"   • {alert_counts['FAULT']} fault alert inceleyin")
print(f"   • Bunlardan kaçı gerçek arıza?")
print(f"   • False positive var mı?")
print(f"   • Threshold 0.50 uygun mu? (Precision-focused)")
print(f"   • Soft limit warning faydalı mı?")

print("\n" + "="*60)
print("✅ BATCH ANALYSIS TAMAMLANDI!")
print("="*60 + "\n")
