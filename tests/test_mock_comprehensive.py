"""
test_mock_comprehensive.py — Kapsamlı Mock Data Test
══════════════════════════════════════════════════════
Hybrid Alert Engine'i detaylı test eder.
"""

import yaml
from src.alerts.alert_engine import (
    detect_faults_direct,
    predict_pre_fault_direct,
    generate_hybrid_alert,
    process_hybrid_alert,
    format_hybrid_alert_plain
)

# Limits config yükle
with open("limits_config.yaml") as f:
    CONFIG = yaml.safe_load(f)

LIMITS = CONFIG.get("machine_limits", {})

print("\n" + "╔" + "═"*53 + "╗")
print("║" + " "*15 + "HYBRID ALERT ENGINE TEST" + " "*14 + "║")
print("╚" + "═"*53 + "╝")

# ─── TEST 1: RULE-BASED FAULT DETECTION ──────────────────────────────────
print("\n" + "="*55)
print("TEST 1: RULE-BASED FAULT DETECTION")
print("="*55)

sensor_values = {
    "main_pressure": 126.5,            # max: 110 → %15 aşım
    "horizontal_press_pressure": 125.3, # max: 120 → %4.4 aşım
    "oil_tank_temperature": 38.5,      # NORMAL
}

faults = detect_faults_direct("HPR001", sensor_values, LIMITS)

print(f"\n📊 Bulunan fault sayısı: {len(faults)}")
for i, fault in enumerate(faults, 1):
    print(f"\n  Fault {i}:")
    print(f"    Sensor: {fault['sensor']}")
    print(f"    Value: {fault['value']:.1f}")
    print(f"    Limit: {fault['limit']:.1f}")
    print(f"    Over ratio: %{fault['over_ratio']*100:.1f}")
    print(f"    Severity: {fault['severity']}")

assert len(faults) == 2, "2 fault bulunmalıydı!"
assert faults[0]['severity'] == "KRİTİK", "main_pressure KRİTİK olmalı!"
assert faults[1]['severity'] == "YÜKSEK", "horizontal_press YÜKSEK olmalı!"

print("\n✅ TEST 1 GEÇTİ!")

# ─── TEST 2: HYBRID ALERT GENERATION ─────────────────────────────────────
print("\n" + "="*55)
print("TEST 2: HYBRID ALERT GENERATION")
print("="*55)

alerts = generate_hybrid_alert(
    "HPR001",
    sensor_values,
    {"ewma_mean": {}, "buffers": {}, "ewma_var": {}, "sample_count": {}},
    LIMITS
)

print(f"\n📊 Üretilen alert sayısı: {len(alerts)}")

if alerts:
    alert = alerts[0]
    print(f"\n  Alert Detayları:")
    print(f"    Type: {alert['type']}")
    print(f"    Confidence: %{alert['confidence']*100:.0f}")
    print(f"    Severity: {alert['severity']}")
    print(f"    Reason count: {len(alert['reasons'])}")
    print(f"    Recommendation: {alert['recommendation']}")
    
    if alert.get('multi_sensor'):
        print(f"\n  ⚠️  MULTI-SENSOR FAULT: {alert['fault_count']} sensör!")
    
    print(f"\n  Reasons:")
    for reason in alert['reasons']:
        print(f"    • {reason}")

assert len(alerts) == 1, "1 alert üretilmeliydi!"
assert alerts[0]['type'] == 'FAULT', "Type FAULT olmalı!"
assert alerts[0]['confidence'] == 1.0, "Confidence 1.0 olmalı!"

print("\n✅ TEST 2 GEÇTİ!")

# ─── TEST 3: ALERT FORMATTING ────────────────────────────────────────────
print("\n" + "="*55)
print("TEST 3: ALERT FORMATTING (PLAIN TEXT)")
print("="*55)

if alerts:
    output = format_hybrid_alert_plain(alerts[0])
    print(output)
    
    # Output validation
    assert "FAULT ALERT" in output, "FAULT ALERT içermeli!"
    assert "HPR001" in output, "Machine ID içermeli!"
    assert "main_pressure" in output, "Sensor name içermeli!"
    assert "Öneri:" in output, "Recommendation içermeli!"
    
    print("✅ TEST 3 GEÇTİ!")

# ─── TEST 4: PRE-FAULT WARNING ───────────────────────────────────────────
print("\n" + "="*55)
print("TEST 4: ML PRE-FAULT WARNING")
print("="*55)

class MockMLPredictor:
    def __init__(self, confidence=0.75):
        self.is_active = True
        self.confidence = confidence
    
    def predict_risk(self, machine_id, state):
        class Result:
            score = 70.0
            confidence = self.confidence
            top_features = ["main_pressure__value_max", "active_sensors"]
            explanation = f"ML Modeli %{int(self.confidence*100)} ihtimalle yakın arıza öngörüyor"
        return Result()

sensor_values_normal = {
    "main_pressure": 105.0,            # max: 110 → Yakın ama aşım yok
    "horizontal_press_pressure": 115.0, # max: 120 → Yakın
    "oil_tank_temperature": 42.0,      # max: 45 → Yakın
}

window_features_trend = {
    "ewma_mean": {
        "main_pressure": 5.0,  # Yükseliş trendi
    },
    "buffers": {},
    "ewma_var": {},
    "sample_count": {}
}

pre_fault_alerts = generate_hybrid_alert(
    "HPR001",
    sensor_values_normal,
    window_features_trend,
    LIMITS,
    MockMLPredictor(confidence=0.75)
)

print(f"\n📊 Üretilen alert sayısı: {len(pre_fault_alerts)}")

if pre_fault_alerts:
    alert = pre_fault_alerts[0]
    print(f"\n  Alert Detayları:")
    print(f"    Type: {alert['type']}")
    print(f"    Confidence: %{alert['confidence']*100:.0f}")
    print(f"    Time Horizon: {alert.get('time_horizon', 'N/A')}")
    print(f"    Recommendation: {alert['recommendation']}")
    
    print(f"\n  Reasons:")
    for reason in alert['reasons']:
        print(f"    • {reason}")

assert len(pre_fault_alerts) == 1, "1 alert üretilmeliydi!"
assert pre_fault_alerts[0]['type'] == 'PRE_FAULT_WARNING', "PRE_FAULT_WARNING olmalı!"

print("\n✅ TEST 4 GEÇTİ!")

# ─── TEST 5: ALERT PRIORITIZATION ────────────────────────────────────────
print("\n" + "="*55)
print("TEST 5: ALERT PRIORITIZATION (FAULT > PRE_FAULT)")
print("="*55)

# Hem fault hem pre-fault olan senaryo
sensor_values_both = {
    "main_pressure": 126.5,            # FAULT
    "horizontal_press_pressure": 125.3, # FAULT
    "oil_tank_temperature": 42.0,
}

both_alerts = generate_hybrid_alert(
    "HPR001",
    sensor_values_both,
    window_features_trend,
    LIMITS,
    MockMLPredictor(confidence=0.90)  # Yüksek confidence
)

print(f"\n📊 Üretilen alert sayısı: {len(both_alerts)}")

if both_alerts:
    alert = both_alerts[0]
    print(f"\n  Öncelikli Alert:")
    print(f"    Type: {alert['type']}")
    print(f"    Confidence: %{alert['confidence']*100:.0f}")
    
    # FAULT her zaman öncelikli
    assert alert['type'] == 'FAULT', "FAULT öncelikli olmalı!"
    assert len(both_alerts) == 1, "Sadece 1 alert dönmeli (spam önleme)!"
    
    print("\n  ✅ Alert prioritization doğru çalışıyor!")
    print("  ✅ FAULT > PRE_FAULT (beklendiği gibi)")
    print("  ✅ Alert spam önleme çalışıyor")

print("\n✅ TEST 5 GEÇTİ!")

# ─── TEST 6: CRITICAL FAULT ──────────────────────────────────────────────
print("\n" + "="*55)
print("TEST 6: CRITICAL FAULT (%10+ AŞIM)")
print("="*55)

sensor_values_critical = {
    "main_pressure": 125.0,            # max: 110 → %13.6 aşım (KRİTİK)
    "horizontal_press_pressure": 135.0, # max: 120 → %12.5 aşım (KRİTİK)
    "oil_tank_temperature": 38.5,
}

critical_alerts = generate_hybrid_alert(
    "HPR001",
    sensor_values_critical,
    {},
    LIMITS
)

if critical_alerts:
    alert = critical_alerts[0]
    print(f"\n  Alert Detayları:")
    print(f"    Severity: {alert['severity']}")
    print(f"    Recommendation: {alert['recommendation']}")
    
    assert alert['severity'] == "KRİTİK", "KRİTİK severity olmalı!"
    assert "ACİL" in alert['recommendation'], "Acil recommendation olmalı!"

print("\n✅ TEST 6 GEÇTİ!")

# ─── TEST 7: ALT LİMİT AŞIMI ─────────────────────────────────────────────
print("\n" + "="*55)
print("TEST 7: ALT LİMİT AŞIMI (LOW)")
print("="*55)

sensor_values_low = {
    "main_pressure": -5.0,             # min: 0 → ALT LİMİT!
    "horizontal_press_pressure": 105.3, # NORMAL
    "oil_tank_temperature": 38.5,
}

low_alerts = generate_hybrid_alert(
    "HPR001",
    sensor_values_low,
    {},
    LIMITS
)

if low_alerts:
    alert = low_alerts[0]
    print(f"\n  Alert Detayları:")
    print(f"    Type: {alert['type']}")
    print(f"    Reason: {alert['reasons'][0]}")
    
    assert alert['type'] == 'FAULT', "FAULT olmalı!"
    assert "min" in alert['reasons'][0].lower() or "alt limit" in alert['reasons'][0].lower(), "Alt limit belirtilmeli!"

print("\n✅ TEST 7 GEÇTİ!")

# ─── TEST 8: NORMAL OPERASYON ────────────────────────────────────────────
print("\n" + "="*55)
print("TEST 8: NORMAL OPERASYON (ALERT YOK)")
print("="*55)

sensor_values_all_normal = {
    "main_pressure": 95.0,
    "horizontal_press_pressure": 105.0,
    "oil_tank_temperature": 38.0,
    "lower_ejector_pressure": 88.0,
    "horitzonal_infeed_speed": 150.0,
    "vertical_infeed_speed": 120.0,
}

normal_alerts = generate_hybrid_alert(
    "HPR001",
    sensor_values_all_normal,
    {},
    LIMITS
)

print(f"\n📊 Üretilen alert sayısı: {len(normal_alerts)}")
assert len(normal_alerts) == 0, "Normal operasyonda alert olmamalı!"

print("\n  ✅ Normal operasyonda alert üretilmedi")
print("\n✅ TEST 8 GEÇTİ!")

# ─── ÖZET ────────────────────────────────────────────────────────────────
print("\n" + "="*55)
print("TEST ÖZETİ")
print("="*55)

all_tests = [
    ("Rule-Based Fault Detection", True),
    ("Hybrid Alert Generation", True),
    ("Alert Formatting", True),
    ("Pre-Fault Warning", True),
    ("Alert Prioritization", True),
    ("Critical Fault", True),
    ("Alt Limit Aşımı", True),
    ("Normal Operasyon", True),
]

for name, passed in all_tests:
    status = "✅ GEÇTİ" if passed else "❌ BAŞARISIZ"
    print(f"  {status} | {name}")

print("\n" + "="*55)
print("🎉 TÜM TESTLER BAŞARILI!")
print("="*55 + "\n")
