"""
test_mock_comprehensive.py — Kapsamlı Mock Data Test
══════════════════════════════════════════════════════
Hybrid Alert Engine'i detaylı test eder.
"""

import os
import yaml
import pytest
from src.alerts.alert_engine import (
    detect_faults_direct,
    predict_pre_fault_direct,
    generate_hybrid_alert,
    process_hybrid_alert,
    format_hybrid_alert_plain
)

# Limits config yükle
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "limits_config.yaml")
with open(CONFIG_PATH) as f:
    CONFIG = yaml.safe_load(f)

LIMITS = CONFIG.get("machine_limits", {})


class MockMLPredictor:
    """Test için mock ML predictor."""
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


# ─── TEST 1: RULE-BASED FAULT DETECTION ──────────────────────────────────
def test_rule_based_fault_detection():
    """Kural tabanlı fault detection doğru çalışmalı."""
    sensor_values = {
        "main_pressure": 126.5,            # max: 110 → %15 aşım (KRİTİK)
        "horizontal_press_pressure": 125.3, # max: 120 → %4.4 aşım (YÜKSEK)
        "oil_tank_temperature": 35.0,      # max: 45 → %77 (normal, soft limit değil)
    }

    faults = detect_faults_direct("HPR001", sensor_values, LIMITS)

    assert len(faults) == 2, "2 fault bulunmalıydı!"
    assert faults[0]['severity'] == "KRİTİK", "main_pressure KRİTİK olmalı!"
    assert faults[1]['severity'] == "YÜKSEK", "horizontal_press YÜKSEK olmalı!"


# ─── TEST 2: HYBRID ALERT GENERATION ─────────────────────────────────────
def test_hybrid_alert_generation():
    """Hybrid alert generation fault için doğru alert üretmeli."""
    sensor_values = {
        "main_pressure": 126.5,            # max: 110 → %15 aşım (KRİTİK)
        "horizontal_press_pressure": 125.3, # max: 120 → %4.4 aşım (YÜKSEK)
        "oil_tank_temperature": 35.0,      # normal
    }

    alerts = generate_hybrid_alert(
        "HPR001",
        sensor_values,
        {"ewma_mean": {}, "buffers": {}, "ewma_var": {}, "sample_count": {}},
        LIMITS
    )

    assert len(alerts) == 1, "1 alert üretilmeliydi!"
    assert alerts[0]['type'] == 'FAULT', "Type FAULT olmalı!"
    assert alerts[0]['confidence'] == 1.0, "Confidence 1.0 olmalı!"


# ─── TEST 3: ALERT FORMATTING ────────────────────────────────────────────
def test_alert_formatting_plain_text():
    """Alert plain text formatı doğru içerikleri barındırmalı."""
    sensor_values = {
        "main_pressure": 126.5,
        "horizontal_press_pressure": 125.3,
        "oil_tank_temperature": 35.0,
    }

    alerts = generate_hybrid_alert(
        "HPR001",
        sensor_values,
        {"ewma_mean": {}, "buffers": {}, "ewma_var": {}, "sample_count": {}},
        LIMITS
    )

    assert len(alerts) > 0, "Alert üretilmeli!"
    output = format_hybrid_alert_plain(alerts[0])
    assert "FAULT ALERT" in output, "FAULT ALERT içermeli!"
    assert "HPR001" in output, "Machine ID içermeli!"
    assert "main_pressure" in output, "Sensor name içermeli!"
    assert "Öneri:" in output, "Recommendation içermeli!"


# ─── TEST 4: PRE-FAULT WARNING ───────────────────────────────────────────
def test_pre_fault_warning():
    """ML pre-fault warning doğru çalışmalı."""
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

    assert len(pre_fault_alerts) == 1, "1 alert üretilmeliydi!"
    assert pre_fault_alerts[0]['type'] == 'PRE_FAULT_WARNING', "PRE_FAULT_WARNING olmalı!"


# ─── TEST 5: ALERT PRIORITIZATION ────────────────────────────────────────
def test_alert_prioritization_fault_over_pre_fault():
    """FAULT her zaman PRE_FAULT'tan öncelikli olmalı."""
    # Hem fault hem pre-fault olan senaryo
    sensor_values_both = {
        "main_pressure": 126.5,            # FAULT
        "horizontal_press_pressure": 125.3, # FAULT
        "oil_tank_temperature": 42.0,
    }

    window_features_trend = {
        "ewma_mean": {
            "main_pressure": 5.0,
        },
        "buffers": {},
        "ewma_var": {},
        "sample_count": {}
    }

    both_alerts = generate_hybrid_alert(
        "HPR001",
        sensor_values_both,
        window_features_trend,
        LIMITS,
        MockMLPredictor(confidence=0.90)  # Yüksek confidence
    )

    assert len(both_alerts) == 1, "Sadece 1 alert dönmeli (spam önleme)!"
    assert both_alerts[0]['type'] == 'FAULT', "FAULT öncelikli olmalı!"


# ─── TEST 6: CRITICAL FAULT ──────────────────────────────────────────────
def test_critical_fault():
    """%10+ aşım kritik fault olarak işaretlenmeli."""
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

    assert len(critical_alerts) > 0, "Kritik fault alert üretilmeli!"
    alert = critical_alerts[0]
    assert alert['severity'] == "KRİTİK", "KRİTİK severity olmalı!"
    assert "ACİL" in alert['recommendation'], "Acil recommendation olmalı!"


# ─── TEST 7: ALT LİMİT AŞIMI ─────────────────────────────────────────────
def test_low_limit_violation():
    """Alt limit aşımı fault olarak algılanmalı."""
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

    assert len(low_alerts) > 0, "Alt limit aşımı alert üretilmeli!"
    alert = low_alerts[0]
    assert alert['type'] == 'FAULT', "FAULT olmalı!"
    assert "min" in alert['reasons'][0].lower() or "alt limit" in alert['reasons'][0].lower(), "Alt limit belirtilmeli!"


# ─── TEST 8: NORMAL OPERASYON ────────────────────────────────────────────
def test_normal_operation_no_alert():
    """Normal operasyonda alert üretilmemeli."""
    sensor_values_all_normal = {
        "main_pressure": 80.0,              # max: 110 → %72 (normal)
        "horizontal_press_pressure": 90.0,  # max: 120 → %75 (normal)
        "oil_tank_temperature": 35.0,       # max: 45 → %77 (normal)
        "lower_ejector_pressure": 80.0,     # max: 110 → %72 (normal)
        "horitzonal_infeed_speed": 120.0,   # max: 300 → %40 (normal)
        "vertical_infeed_speed": 100.0,     # max: 250 → %40 (normal)
    }

    normal_alerts = generate_hybrid_alert(
        "HPR001",
        sensor_values_all_normal,
        {},
        LIMITS
    )

    assert len(normal_alerts) == 0, "Normal operasyonda alert olmamalı!"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
