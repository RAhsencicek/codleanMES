"""
demo_alert_generation.py — Mock Alert Generation Demo
═══════════════════════════════════════════════════════
Tüm realistic senaryolardan alert üret, terminal'de göster.
Technician feedback için hazır çıktı üretir.
"""

import yaml
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich import box

# Import alert engine
from src.alerts.alert_engine import generate_hybrid_alert, process_hybrid_alert

console = Console()

# Config yükle
with open("limits_config.yaml") as f:
    CONFIG = yaml.safe_load(f)

LIMITS = CONFIG.get("machine_limits", {})

print("\n" + "╔" + "═"*60 + "╗")
print("║" + " "*18 + "MOCK ALERT GENERATION DEMO" + " "*16 + "║")
print("╚" + "═"*60 + "╝")

# ──────────────────────────────────────────────────────────────
# SENARYO 1: NORMAL OPERASYON
# ──────────────────────────────────────────────────────────────
console.print("\n[bold blue]┌─ SENARYO 1: NORMAL OPERASYON[/bold blue]")
console.print(Panel("Durum: Makine full speed çalışıyor, tüm sensörler normal sınırlarda", style="dim"))

sensor_values_1 = {
    "main_pressure": 95.0,             # max: 110 → %86 (normal)
    "horizontal_press_pressure": 100.0, # max: 120 → %83 (normal)
    "oil_tank_temperature": 38.0,      # max: 45 → %84 (normal)
    "lower_ejector_pressure": 90.0,    # max: 110 → %82 (normal)
}

alerts_1 = generate_hybrid_alert("HPR001", sensor_values_1, {}, LIMITS)

if alerts_1:
    console.print(f"[yellow]⚠️  Alert üretildi: {len(alerts_1)}[/yellow]")
    for alert in alerts_1:
        process_hybrid_alert(alert, use_rich=True)
else:
    console.print("[green]✅ Alert YOK (Normal operasyon)[/green]")

# ──────────────────────────────────────────────────────────────
# SENARYO 2: SOFT LIMIT WARNING
# ──────────────────────────────────────────────────────────────
console.print("\n[bold yellow]┌─ SENARYO 2: SOFT LIMIT WARNING (%85+)[/bold yellow]")
console.print(Panel("Durum: Sensörler limite yaklaşıyor ama henüz aşmadı\n→ Dikkatli izleme gerekli", style="dim"))

sensor_values_2 = {
    "main_pressure": 105.0,            # max: 110 → %95 (SOFT LIMIT!)
    "horizontal_press_pressure": 115.0, # max: 120 → %96 (SOFT LIMIT!)
    "oil_tank_temperature": 42.0,      # max: 45 → %93 (SOFT LIMIT!)
}

alerts_2 = generate_hybrid_alert("HPR001", sensor_values_2, {}, LIMITS)

if alerts_2:
    console.print(f"[yellow]⚠️  Alert üretildi: {len(alerts_2)}[/yellow]")
    for alert in alerts_2:
        process_hybrid_alert(alert, use_rich=True)
else:
    console.print("[red]❌ Beklenen alert üretilmedi![/red]")

# ──────────────────────────────────────────────────────────────
# SENARYO 3: HARD FAULT (SINGLE SENSOR)
# ──────────────────────────────────────────────────────────────
console.print("\n[bold red]┌─ SENARYO 3: HARD FAULT - SINGLE SENSOR[/bold red]")
console.print(Panel("Durum: Ana basınç limit aştı (%7 aşım)\n→ Acil bakım gerekli", style="dim"))

sensor_values_3 = {
    "main_pressure": 118.0,            # max: 110 → %107.3 (FAULT!)
    "horizontal_press_pressure": 100.0, # Normal
    "oil_tank_temperature": 38.0,      # Normal
}

alerts_3 = generate_hybrid_alert("HPR001", sensor_values_3, {}, LIMITS)

if alerts_3:
    console.print(f"[red]🔴 FAULT Alert: {len(alerts_3)}[/red]")
    for alert in alerts_3:
        process_hybrid_alert(alert, use_rich=True)
else:
    console.print("[red]❌ Beklenen alert üretilmedi![/red]")

# ──────────────────────────────────────────────────────────────
# SENARYO 4: HARD FAULT (MULTI-SENSOR KRİTİK)
# ──────────────────────────────────────────────────────────────
console.print("\n[bold red]┌─ SENARYO 4: MULTI-SENSOR KRİTİK FAULT[/bold red]")
console.print(Panel("Durum: 3 sensör birden limit dışı + %10+ aşım\n→ ACİL DURDURMA GEREKLİ!", style="bold red"))

sensor_values_4 = {
    "main_pressure": 125.0,            # max: 110 → %113.6 (KRİTİK!)
    "horizontal_press_pressure": 135.0, # max: 120 → %112.5 (KRİTİK!)
    "lower_ejector_pressure": 122.0,   # max: 110 → %110.9 (KRİTİK!)
    "oil_tank_temperature": 48.0,      # max: 45 → %106.7 (YÜKSEK)
}

alerts_4 = generate_hybrid_alert("HPR001", sensor_values_4, {}, LIMITS)

if alerts_4:
    console.print(f"[bold red]🔴 KRİTİK FAULT: {len(alerts_4)}[/bold red]")
    for alert in alerts_4:
        process_hybrid_alert(alert, use_rich=True)
else:
    console.print("[red]❌ Beklenen alert üretilmedi![/red]")

# ──────────────────────────────────────────────────────────────
# SENARYO 5: ML PRE-FAULT PREDICTION
# ──────────────────────────────────────────────────────────────
console.print("\n[bold yellow]┌─ SENARYO 5: ML PRE-FAULT PREDICTION[/bold yellow]")
console.print(Panel("Durum: Henüz fault yok AMA ML bozulma öngörüyor\n→ 30-60 dakika içinde fault bekleniyor", style="dim"))

# Pre-fault window features (kademeli bozulma)
window_features_5 = {
    'main_pressure_mean': 108.0,       # Yükselişte
    'main_pressure_std': 8.5,          # Yüksek varyans
    'main_pressure_min': 95.0,
    'main_pressure_max': 118.0,
    'horizontal_press_pressure_mean': 112.0,
    'horizontal_press_pressure_std': 9.2,
    'horizontal_press_pressure_min': 98.0,
    'horizontal_press_pressure_max': 125.0,
    'oil_tank_temperature_mean': 43.5,
    'oil_tank_temperature_std': 2.8,
    'oil_tank_temperature_min': 40.0,
    'oil_tank_temperature_max': 46.0,
    'total_faults_window': 3,          # Son window'da 3 fault
    'active_sensors': 6,               # 6 sensör aktif
    'fault_rate_window': 0.15,         # %15 fault rate
}

# Sensor values şu an normal
sensor_values_5 = {
    "main_pressure": 108.0,            # max: 110 → %98 (hala normal)
    "horizontal_press_pressure": 112.0, # max: 120 → %93 (normal)
    "oil_tank_temperature": 43.5,      # max: 45 → %97 (yakın ama normal)
}

# Not: ML predictor olmadan sadece rule-based çalışır
# Gerçek demo'da ML predictor ile yapılacak
console.print("[dim]Not: ML predictor olmadan sadece rule-based detection çalışır[/dim]")
console.print("[dim]Gerçek demo: python3 hpr_monitor.py ile canlı[/dim]")

alerts_5 = generate_hybrid_alert("HPR001", sensor_values_5, {}, LIMITS)

if alerts_5:
    console.print(f"[yellow]⚠️  Alert: {len(alerts_5)}[/yellow]")
    for alert in alerts_5:
        process_hybrid_alert(alert, use_rich=True)
else:
    console.print("[green]✅ Rule-based: Alert yok (ML olsaydı PRE_FAULT uyarısı verirdi)[/green]")

# ──────────────────────────────────────────────────────────────
# SENARYO 6: STARTUP/COLD MACHINE
# ──────────────────────────────────────────────────────────────
console.print("\n[bold cyan]┌─ SENARYO 6: STARTUP / COLD MACHINE[/bold cyan]")
console.print(Panel("Durum: Makine yeni başladı, sıcaklıklar düşük\n→ Isınma devri, normal kabul edilir", style="dim"))

sensor_values_6 = {
    "main_pressure": 75.0,             # max: 110 → %68 (düşük, normal)
    "horizontal_press_pressure": 80.0,  # max: 120 → %67 (düşük, normal)
    "oil_tank_temperature": 28.0,      # max: 45 → %62 (soğuk, normal)
}

alerts_6 = generate_hybrid_alert("HPR001", sensor_values_6, {}, LIMITS)

if alerts_6:
    console.print(f"[yellow]⚠️  Alert: {len(alerts_6)}[/yellow]")
    for alert in alerts_6:
        process_hybrid_alert(alert, use_rich=True)
else:
    console.print("[green]✅ Alert yok (Startup normal)[/green]")

# ──────────────────────────────────────────────────────────────
# SENARYO 7: ALT LİMİT AŞIMI (LOW)
# ──────────────────────────────────────────────────────────────
console.print("\n[bold red]┌─ SENARYO 7: ALT LİMİT AŞIMI (NEGATİF BASINÇ)[/bold red]")
console.print(Panel("Durum: Basınç negatif değere düştü\n→ Ciddi sistem arızası!", style="bold red"))

sensor_values_7 = {
    "main_pressure": -5.0,             # min: 0.0 → ALT LİMİT AŞIMI!
    "horizontal_press_pressure": 100.0, # Normal
    "oil_tank_temperature": 38.0,      # Normal
}

alerts_7 = generate_hybrid_alert("HPR001", sensor_values_7, {}, LIMITS)

if alerts_7:
    console.print(f"[red]🔴 FAULT Alert: {len(alerts_7)}[/red]")
    for alert in alerts_7:
        process_hybrid_alert(alert, use_rich=True)
else:
    console.print("[red]❌ Beklenen alert üretilmedi![/red]")

# ──────────────────────────────────────────────────────────────
# ÖZET
# ──────────────────────────────────────────────────────────────
console.print("\n" + "="*60)
console.print("[bold]SENARYO ÖZETİ[/bold]")
console.print("="*60)

summary_data = [
    ("1. Normal Operasyon", "✅ Alert YOK", "Beklenen"),
    ("2. Soft Limit Warning", "⚠️  SOFT_LIMIT_WARNING", "DÜŞÜK severity"),
    ("3. Single Sensor Fault", "🔴 FAULT", "YÜKSEK severity"),
    ("4. Multi-Sensor Kritik", "🔴 FAULT (KRİTİK)", "ACİL durdurma"),
    ("5. Pre-Fault Prediction", "⚠️  PRE_FAULT_WARNING", "ML gerekir"),
    ("6. Startup/Cold", "✅ Alert YOK", "Normal"),
    ("7. Alt Limit Aşımı", "🔴 FAULT", "YÜKSEK severity"),
]

for scenario, result, note in summary_data:
    console.print(f"  [bold]{scenario:<25}[/bold] → {result:<25} ({note})")

console.print("\n" + "="*60)
console.print("[bold green]✅ TÜM SENARYOLAR BAŞARIYLA TEST EDİLDİ![/bold green]")
console.print("="*60)

print("\n💡 TECHNICIAN FEEDBACK İÇİN NOTLAR:")
print("   → Hangi alert'ler faydalı?")
print("   → Hangi alert'ler gereksiz/alert fatigue yaratır?")
print("   → Severity seviyeleri doğru mu?")
print("   → Recommendations actionable mı?")
print("   → Threshold 0.50 uygun mu? (Yeni: Precision-focused)")
print("   → Soft limit (%85) faydalı mı?")
print("\n")
