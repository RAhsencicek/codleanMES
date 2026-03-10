"""
test_hybrid_alerts.py — Hybrid Alert Engine Testi
═══════════════════════════════════════════════════
Sahte sensör verisiyle hybrid alert system'i test eder.
"""

import sys
from datetime import datetime

# Limits config (örnek)
LIMITS_CONFIG = {
    "HPR001": {
        "main_pressure": {"min": 0, "max": 120, "unit": "bar"},
        "horizontal_press_pressure": {"min": 0, "max": 120, "unit": "bar"},
        "oil_tank_temperature": {"min": 0, "max": 45, "unit": "°C"},
    },
    "HPR002": {
        "main_pressure": {"min": 0, "max": 110, "unit": "bar"},
        "horizontal_press_pressure": {"min": 0, "max": 110, "unit": "bar"},
        "oil_tank_temperature": {"min": 0, "max": 45, "unit": "°C"},
    }
}


# Mock ML Predictor
class MockMLPredictor:
    def __init__(self, is_active=True):
        self.is_active = is_active
    
    def predict_risk(self, machine_id, state):
        class Result:
            score = 75.0
            confidence = 0.75
            top_features = ["main_pressure__value_max", "active_sensors"]
            explanation = "ML Modeli %75 ihtimalle yakın arıza öngörüyor"
        return Result()


def test_rule_based_fault():
    """TEST 1: Rule-based fault detection"""
    print("\n" + "="*55)
    print("TEST 1: Rule-Based Fault Detection (KESİN)")
    print("="*55)
    
    from alert_engine import detect_faults_direct
    
    # Senaryo: HPR001, main_pressure limit aşımı
    sensor_values = {
        "main_pressure": 126.5,  # max: 120 → %5.4 aşım
        "horizontal_press_pressure": 125.3,  # max: 120 → %4.4 aşım
        "oil_tank_temperature": 42.0,  # normal
    }
    
    faults = detect_faults_direct("HPR001", sensor_values, LIMITS_CONFIG)
    
    print(f"\nBulunan fault sayısı: {len(faults)}")
    for fault in faults:
        print(f"  • {fault['message']}")
        print(f"    Severity: {fault['severity']}")
    
    if len(faults) >= 2:
        print(f"\n⚠️  MULTI-SENSOR FAULT: {len(faults)} sensör!")
    
    return len(faults) > 0


def test_ml_pre_fault():
    """TEST 2: ML pre-fault prediction"""
    print("\n" + "="*55)
    print("TEST 2: ML Pre-Fault Prediction (OLASI)")
    print("="*55)
    
    from alert_engine import predict_pre_fault_direct
    
    # Senaryo: HPR002, normal değerler ama ML anormallik algılıyor
    sensor_values = {
        "main_pressure": 95.0,  # normal
        "horizontal_press_pressure": 100.0,  # normal
        "oil_tank_temperature": 40.0,  # normal
    }
    
    window_features = {
        "ewma_mean": {
            "main_pressure": 5.0,  # yükseliş trendi
        },
        "buffers": {},
        "ewma_var": {},
        "sample_count": {}
    }
    
    mock_ml = MockMLPredictor(is_active=True)
    
    pre_fault = predict_pre_fault_direct("HPR002", window_features, mock_ml)
    
    if pre_fault:
        print(f"\nPre-fault detected!")
        print(f"  Probability: %{pre_fault['probability']*100:.0f}")
        print(f"  Confidence: {pre_fault['confidence']}")
        print(f"  Trends: {pre_fault['trends']}")
        print(f"  Top Features: {pre_fault['top_features']}")
        print(f"  Explanation: {pre_fault['explanation']}")
    else:
        print("\nNo pre-fault detected (normal operation)")
    
    return pre_fault is not None


def test_hybrid_alert_generation():
    """TEST 3: Hybrid alert generation (FULL PIPELINE)"""
    print("\n" + "="*55)
    print("TEST 3: Hybrid Alert Generation (FULL PIPELINE)")
    print("="*55)
    
    from alert_engine import generate_hybrid_alert
    
    # Senaryo A: FAULT var (rule-based öncelikli)
    print("\n┌─ SENARYO A: FAULT + PRE-FAULT (hangisi öncelikli?)")
    sensor_values_fault = {
        "main_pressure": 126.5,  # FAULT
        "horizontal_press_pressure": 125.3,  # FAULT
        "oil_tank_temperature": 42.0,
    }
    
    mock_ml = MockMLPredictor(is_active=True)
    
    alerts_a = generate_hybrid_alert(
        "HPR001",
        sensor_values_fault,
        {"ewma_mean": {}, "buffers": {}, "ewma_var": {}, "sample_count": {}},
        LIMITS_CONFIG,
        mock_ml
    )
    
    print(f"\nÜretilen alert sayısı: {len(alerts_a)}")
    if alerts_a:
        alert = alerts_a[0]
        print(f"  Type: {alert['type']}")
        print(f"  Confidence: %{alert['confidence']*100:.0f}")
        print(f"  Reasons: {len(alert['reasons'])}")
        print(f"  Recommendation: {alert['recommendation']}")
    
    # Senaryo B: Sadece PRE-FAULT (fault yok)
    print("\n┌─ SENARYO B: Sadece PRE-FAULT (fault yok)")
    sensor_values_normal = {
        "main_pressure": 95.0,
        "horizontal_press_pressure": 100.0,
        "oil_tank_temperature": 40.0,
    }
    
    alerts_b = generate_hybrid_alert(
        "HPR002",
        sensor_values_normal,
        {"ewma_mean": {"main_pressure": 5.0}, "buffers": {}, "ewma_var": {}, "sample_count": {}},
        LIMITS_CONFIG,
        mock_ml
    )
    
    print(f"\nÜretilen alert sayısı: {len(alerts_b)}")
    if alerts_b:
        alert = alerts_b[0]
        print(f"  Type: {alert['type']}")
        print(f"  Confidence: %{alert['confidence']*100:.0f}")
        print(f"  Time Horizon: {alert.get('time_horizon', 'N/A')}")
        print(f"  Recommendation: {alert['recommendation']}")
    
    return len(alerts_a) > 0 and len(alerts_b) > 0


def test_terminal_output():
    """TEST 4: Terminal output formatting"""
    print("\n" + "="*55)
    print("TEST 4: Terminal Output Formatting")
    print("="*55)
    
    from alert_engine import generate_hybrid_alert, process_hybrid_alert
    
    # Senaryo: Multi-sensor fault
    sensor_values = {
        "main_pressure": 135.0,  # KRİTİK: %12.5 aşım
        "horizontal_press_pressure": 128.0,  # YÜKSEK: %6.7 aşım
        "oil_tank_temperature": 42.0,
    }
    
    mock_ml = MockMLPredictor(is_active=True)
    
    alerts = generate_hybrid_alert(
        "HPR001",
        sensor_values,
        {"ewma_mean": {}, "buffers": {}, "ewma_var": {}, "sample_count": {}},
        LIMITS_CONFIG,
        mock_ml
    )
    
    if alerts:
        print("\n📢 ALERT OUTPUT (Plain text format):")
        process_hybrid_alert(alerts[0], use_rich=False)
        # Rich format için use_rich=True yapabilirsin
    
    return len(alerts) > 0


if __name__ == "__main__":
    print("\n" + "╔" + "═"*53 + "╗")
    print("║" + " "*10 + "HYBRID ALERT ENGINE TESTİ" + " "*16 + "║")
    print("╚" + "═"*53 + "╝")
    
    results = []
    
    # Test 1
    results.append(("Rule-Based Fault", test_rule_based_fault()))
    
    # Test 2
    results.append(("ML Pre-Fault", test_ml_pre_fault()))
    
    # Test 3
    results.append(("Hybrid Alert Gen", test_hybrid_alert_generation()))
    
    # Test 4
    results.append(("Terminal Output", test_terminal_output()))
    
    # Özet
    print("\n" + "="*55)
    print("TEST ÖZETİ")
    print("="*55)
    for name, passed in results:
        status = "✅ GEÇTİ" if passed else "❌ BAŞARISIZ"
        print(f"  {status} | {name}")
    
    all_passed = all(result[1] for result in results)
    
    print("\n" + "="*55)
    if all_passed:
        print("🎉 TÜM TESTLER BAŞARILI!")
    else:
        print("⚠️  BAZI TESTLER BAŞARISIZ")
    print("="*55 + "\n")
