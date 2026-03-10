"""
test_hybrid_with_live_data.py — Mock Live Data Test
═══════════════════════════════════════════════════
Gerçekçi sensör verileriyle hybrid alert engine test eder.
Kafka bağlantısı gerektirmez.
"""

import json
from datetime import datetime, timedelta
from src.alerts.alert_engine import generate_hybrid_alert, process_hybrid_alert
import yaml

# Limits config yükle
with open("limits_config.yaml") as f:
    CONFIG = yaml.safe_load(f)

LIMITS = CONFIG.get("machine_limits", {})

print("\n" + "="*55)
print("HYBRID ALERT ENGINE — MOCK LIVE DATA TEST")
print("="*55)

# ─── SENARYO 1: NORMAL OPERASYON ──────────────────────────────────────────
print("\n┌─ SENARYO 1: NORMAL OPERASYON (Alert beklenmiyor)")
print("─"*55)

sensor_values_normal = {
    "oil_tank_temperature": 38.5,      # max: 45 → NORMAL
    "main_pressure": 95.2,             # max: 110 → NORMAL
    "horizontal_press_pressure": 105.3, # max: 120 → NORMAL
    "lower_ejector_pressure": 88.7,    # max: 110 → NORMAL
    "horitzonal_infeed_speed": 150.0,  # max: 300 → NORMAL
    "vertical_infeed_speed": 120.0,    # max: 300 → NORMAL
}

window_features_normal = {
    "ewma_mean": {},  # Trend yok
    "buffers": {},
    "ewma_var": {},
    "sample_count": {}
}

alerts_1 = generate_hybrid_alert(
    "HPR001",
    sensor_values_normal,
    window_features_normal,
    LIMITS
)

if alerts_1:
    print(f"⚠️  Alert üretildi: {alerts_1[0]['type']}")
    print(f"   Sebep: {alerts_1[0]['reasons'][0]}")
else:
    print("✅ Alert üretilmedi (beklenen)")

# ─── SENARYO 2: RULE-BASED FAULT ─────────────────────────────────────────
print("\n┌─ SENARYO 2: RULE-BASED FAULT (KESİN)")
print("─"*55)

sensor_values_fault = {
    "oil_tank_temperature": 38.5,      # NORMAL
    "main_pressure": 126.5,            # max: 110 → %15 aşım (KRİTİK)
    "horizontal_press_pressure": 125.3, # max: 120 → %4.4 aşım (YÜKSEK)
    "lower_ejector_pressure": 88.7,    # NORMAL
    "horitzonal_infeed_speed": 150.0,  # NORMAL
    "vertical_infeed_speed": 120.0,    # NORMAL
}

alerts_2 = generate_hybrid_alert(
    "HPR001",
    sensor_values_fault,
    window_features_normal,
    LIMITS
)

if alerts_2:
    alert = alerts_2[0]
    print(f"✅ Alert üretildi: {alert['type']}")
    print(f"   Confidence: %{alert['confidence']*100:.0f}")
    print(f"   Severity: {alert['severity']}")
    print(f"   Reason: {alert['reasons'][0]}")
    
    if alert.get('multi_sensor'):
        print(f"   ⚠️  MULTI-SENSOR FAULT: {alert['fault_count']} sensör!")
    
    print(f"\n📢 Terminal Output:")
    process_hybrid_alert(alert, use_rich=False)
else:
    print("❌ Alert üretilmedi (BEKLENMEYEN!)")

# ─── SENARYO 3: PRE-FAULT WARNING ────────────────────────────────────────
print("\n┌─ SENARYO 3: ML PRE-FAULT WARNING (OLASI)")
print("─"*55)

sensor_values_pre_fault = {
    "oil_tank_temperature": 42.0,      # max: 45 → Yakın
    "main_pressure": 105.0,            # max: 110 → Yakın
    "horizontal_press_pressure": 115.0, # max: 120 → Yakın
    "lower_ejector_pressure": 88.7,    # NORMAL
    "horitzonal_infeed_speed": 150.0,  # NORMAL
    "vertical_infeed_speed": 120.0,    # NORMAL
}

# Mock ML Predictor
class MockMLPredictor:
    def __init__(self):
        self.is_active = True
    
    def predict_risk(self, machine_id, state):
        class Result:
            score = 65.0
            confidence = 0.65  # MEDIUM
            top_features = ["main_pressure__value_max", "oil_tank_temperature"]
            explanation = "ML Modeli %65 ihtimalle yakın arıza öngörüyor"
        return Result()

window_features_trend = {
    "ewma_mean": {
        "main_pressure": 8.5,  # Yükseliş trendi
        "oil_tank_temperature": 3.2
    },
    "buffers": {},
    "ewma_var": {},
    "sample_count": {}
}

alerts_3 = generate_hybrid_alert(
    "HPR001",
    sensor_values_pre_fault,
    window_features_trend,
    LIMITS,
    MockMLPredictor()
)

if alerts_3:
    alert = alerts_3[0]
    print(f"✅ Alert üretildi: {alert['type']}")
    print(f"   Confidence: %{alert['confidence']*100:.0f}")
    print(f"   Time Horizon: {alert.get('time_horizon', 'N/A')}")
    print(f"   Recommendation: {alert['recommendation']}")
    print(f"\n📢 Terminal Output:")
    process_hybrid_alert(alert, use_rich=False)
else:
    print("❌ Alert üretilmedi (BEKLENMEYEN!)")

# ─── SENARYO 4: KRİTİK FAULT ─────────────────────────────────────────────
print("\n┌─ SENARYO 4: KRİTİK FAULT (ACİL DURUM)")
print("─"*55)

sensor_values_critical = {
    "oil_tank_temperature": 48.5,      # max: 45 → %7.8 aşım
    "main_pressure": 125.0,            # max: 110 → %13.6 aşım (KRİTİK)
    "horizontal_press_pressure": 135.0, # max: 120 → %12.5 aşım (KRİTİK)
    "lower_ejector_pressure": 88.7,    # NORMAL
    "horitzonal_infeed_speed": 150.0,  # NORMAL
    "vertical_infeed_speed": 120.0,    # NORMAL
}

alerts_4 = generate_hybrid_alert(
    "HPR001",
    sensor_values_critical,
    window_features_normal,
    LIMITS
)

if alerts_4:
    alert = alerts_4[0]
    print(f"✅ Alert üretildi: {alert['type']}")
    print(f"   Confidence: %{alert['confidence']*100:.0f}")
    print(f"   Severity: {alert['severity']}")
    print(f"   Recommendation: {alert['recommendation']}")
    
    if alert.get('multi_sensor'):
        print(f"   ⚠️  MULTI-SENSOR FAULT: {alert['fault_count']} sensör!")
    
    print(f"\n📢 Terminal Output:")
    process_hybrid_alert(alert, use_rich=False)
else:
    print("❌ Alert üretilmedi (BEKLENMEYEN!)")

# ─── SENARYO 5: ALT LİMİT AŞIMI ──────────────────────────────────────────
print("\n┌─ SENARYO 5: ALT LİMİT AŞIMI (LOW)")
print("─"*55)

sensor_values_low = {
    "oil_tank_temperature": 38.5,      # NORMAL
    "main_pressure": -5.0,             # min: 0 → ALT LİMİT!
    "horizontal_press_pressure": 105.3, # NORMAL
    "lower_ejector_pressure": 88.7,    # NORMAL
    "horitzonal_infeed_speed": 150.0,  # NORMAL
    "vertical_infeed_speed": 120.0,    # NORMAL
}

alerts_5 = generate_hybrid_alert(
    "HPR001",
    sensor_values_low,
    window_features_normal,
    LIMITS
)

if alerts_5:
    alert = alerts_5[0]
    print(f"✅ Alert üretildi: {alert['type']}")
    print(f"   Confidence: %{alert['confidence']*100:.0f}")
    print(f"   Severity: {alert['severity']}")
    print(f"   Reason: {alert['reasons'][0]}")
    print(f"\n📢 Terminal Output:")
    process_hybrid_alert(alert, use_rich=False)
else:
    print("❌ Alert üretilmedi (BEKLENMEYEN!)")

# ─── ÖZET ────────────────────────────────────────────────────────────────
print("\n" + "="*55)
print("TEST ÖZETİ")
print("="*55)

tests = [
    ("Normal Operation", len(alerts_1) == 0),
    ("Rule-Based Fault", len(alerts_2) > 0 and alerts_2[0]['type'] == 'FAULT'),
    ("Pre-Fault Warning", len(alerts_3) > 0 and alerts_3[0]['type'] == 'PRE_FAULT_WARNING'),
    ("Critical Fault", len(alerts_4) > 0 and alerts_4[0]['severity'] == 'KRİTİK'),
    ("Low Limit Alert", len(alerts_5) > 0),
]

for name, passed in tests:
    status = "✅ GEÇTİ" if passed else "❌ BAŞARISIZ"
    print(f"  {status} | {name}")

all_passed = all(test[1] for test in tests)

print("\n" + "="*55)
if all_passed:
    print("🎉 TÜM TESTLER BAŞARILI!")
else:
    print("⚠️  BAZI TESTLER BAŞARISIZ")
print("="*55 + "\n")
