"""
test_realistic_scenarios.py — Gerçekçi Üretim Senaryoları
═══════════════════════════════════════════════════════════
Fabrika ortamındaki gerçek durumları simüle eder.
"""

import os
import yaml
import pytest
from src.alerts.alert_engine import generate_hybrid_alert, process_hybrid_alert

# Limits config yükle
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "limits_config.yaml")
with open(CONFIG_PATH) as f:
    CONFIG = yaml.safe_load(f)

LIMITS = CONFIG.get("machine_limits", {})


class MockMLStartup:
    """Startup phase mock ML predictor (düşük confidence)."""
    def __init__(self):
        self.is_active = True

    def predict_risk(self, machine_id, state):
        class Result:
            score = 35.0
            confidence = 0.35  # LOW confidence (startup)
            top_features = ["oil_tank_temperature"]
            explanation = "ML: Startup phase, düşük confidence"
        return Result()


class MockMLDegradation:
    """Gradual degradation mock ML predictor (yüksek confidence)."""
    def __init__(self):
        self.is_active = True

    def predict_risk(self, machine_id, state):
        class Result:
            score = 82.0
            confidence = 0.82  # HIGH confidence
            top_features = ["main_pressure__value_max", "horizontal_press_pressure__over_ratio"]
            explanation = "ML: Kademeli bozulma pattern'i algılandı!"
        return Result()


# ─── SENARYO 1: MAKİNE ISINMA DEVRİ ──────────────────────────────────────
def test_startup_phase():
    """Makine yeni başladı, sensör değerleri stabil değil — low confidence kabul edilebilir."""
    sensor_values_startup = {
        "oil_tank_temperature": 28.0,      # Soğuk (normal: 38-42)
        "main_pressure": 85.0,             # Düşük (normal: 95-105)
        "horizontal_press_pressure": 95.0, # Düşük
        "lower_ejector_pressure": 70.0,    # Düşük
        "horitzonal_infeed_speed": 120.0,  # Normal
        "vertical_infeed_speed": 100.0,    # Normal
    }

    alerts_startup = generate_hybrid_alert(
        "HPR001",
        sensor_values_startup,
        {"ewma_mean": {}, "buffers": {}, "ewma_var": {}, "sample_count": {}},
        LIMITS,
        MockMLStartup()
    )

    # Startup'ta ya alert yoktur ya da düşük confidence'lıdır
    if alerts_startup:
        assert alerts_startup[0]['confidence'] < 0.5, "Startup'ta düşük confidence olmalı!"


# ─── SENARYO 2: PRODUCTION SPEED ─────────────────────────────────────────
def test_full_speed_operation():
    """Makine tam kapasite çalışıyor, basınçlar yüksek — soft limit uyarısı verebilir."""
    sensor_values_full_speed = {
        "oil_tank_temperature": 43.5,      # max: 45'e yakın (%96)
        "main_pressure": 108.0,            # max: 110'a yakın (%98)
        "horizontal_press_pressure": 118.0, # max: 120'e yakın (%98)
        "lower_ejector_pressure": 105.0,   # max: 110'a yakın (%95)
        "horitzonal_infeed_speed": 280.0,  # max: 300'e yakın (%93)
        "vertical_infeed_speed": 270.0,    # max: 300'e yakın (%90)
    }

    alerts_full = generate_hybrid_alert(
        "HPR001",
        sensor_values_full_speed,
        {"ewma_mean": {"oil_tank_temperature": 2.5}, "buffers": {}, "ewma_var": {}, "sample_count": {}},
        LIMITS
    )

    # Full speed'te ya soft limit ya da pre-fault uyarısı olabilir
    if alerts_full:
        assert alerts_full[0]['type'] in ['SOFT_LIMIT_WARNING', 'PRE_FAULT_WARNING', 'FAULT'], \
            "Full speed'te beklenen alert tipi!"


# ─── SENARYO 3: KADEMELİ BOZULMA (Gradual Degradation) ──────────────────
def test_gradual_degradation():
    """Basınç değerleri 3 gündür yavaş yavaş yükseliyor — ML pre-fault yakalamalı."""
    sensor_values_degrading = {
        "oil_tank_temperature": 44.0,      # max: 45 → %97.8
        "main_pressure": 109.5,            # max: 110 → %99.5 (çok yakın!)
        "horizontal_press_pressure": 119.0, # max: 120 → %99.2
        "lower_ejector_pressure": 108.0,   # max: 110 → %98.2
        "horitzonal_infeed_speed": 150.0,  # Normal
        "vertical_infeed_speed": 150.0,    # Normal
    }

    window_features_degrading = {
        "ewma_mean": {
            "main_pressure": 3.5,          # Günlük artış
            "horizontal_press_pressure": 2.8,
            "oil_tank_temperature": 1.2,
        },
        "buffers": {},
        "ewma_var": {},
        "sample_count": {}
    }

    alerts_degrading = generate_hybrid_alert(
        "HPR001",
        sensor_values_degrading,
        window_features_degrading,
        LIMITS,
        MockMLDegradation()
    )

    assert len(alerts_degrading) > 0, "Kademeli bozulmada alert üretilmeli!"
    # ML yüksek confidence verdiği için pre-fault veya fault olabilir
    assert alerts_degrading[0]['confidence'] >= 0.8, "Yüksek confidence olmalı!"


# ─── SENARYO 4: ANİ ŞOK (Sudden Shock) ───────────────────────────────────
def test_sudden_shock():
    """Makine bir şeye çarptı, ani basınç sıçraması — kritik fault algılanmalı."""
    sensor_values_shock = {
        "oil_tank_temperature": 38.0,      # Normal
        "main_pressure": 145.0,            # max: 110 → %31.8 aşım (ÇOK KRİTİK!)
        "horizontal_press_pressure": 155.0, # max: 120 → %29.2 aşım
        "lower_ejector_pressure": 125.0,   # max: 110 → %13.6 aşım
        "horitzonal_infeed_speed": 150.0,  # Normal
        "vertical_infeed_speed": 150.0,    # Normal
    }

    alerts_shock = generate_hybrid_alert(
        "HPR001",
        sensor_values_shock,
        {},
        LIMITS
    )

    assert len(alerts_shock) > 0, "Ani şok durumunda alert üretilmeli!"
    alert = alerts_shock[0]
    assert alert['severity'] == 'KRİTİK', "Ani şok KRİTİK olmalı!"
    assert alert.get('multi_sensor', False) is True, "Multi-sensor fault olmalı!"


# ─── SENARYO 5: TEK SENSÖR FAULT vs MULTI-SENSORS ───────────────────────
def test_single_sensor_fault():
    """Tek sensör fault — multi_sensor flag False olmalı."""
    sensor_values_single = {
        "oil_tank_temperature": 48.0,      # max: 45 → %6.7 aşım
        "main_pressure": 95.0,             # Normal
        "horizontal_press_pressure": 105.0, # Normal
        "lower_ejector_pressure": 88.0,    # Normal
        "horitzonal_infeed_speed": 150.0,  # Normal
        "vertical_infeed_speed": 150.0,    # Normal
    }

    alerts_single = generate_hybrid_alert("HPR001", sensor_values_single, {}, LIMITS)

    assert len(alerts_single) > 0, "Tek sensör fault alert üretilmeli!"
    assert alerts_single[0].get('multi_sensor', False) is False, "Tek sensörde multi_sensor False olmalı!"


def test_multi_sensor_fault():
    """Multi-sensor fault — multi_sensor flag True ve daha acil olmalı."""
    sensor_values_multi = {
        "oil_tank_temperature": 48.0,      # max: 45 → %6.7 aşım
        "main_pressure": 118.0,            # max: 110 → %7.3 aşım
        "horizontal_press_pressure": 128.0, # max: 120 → %6.7 aşım
        "lower_ejector_pressure": 88.0,    # Normal
        "horitzonal_infeed_speed": 150.0,  # Normal
        "vertical_infeed_speed": 150.0,    # Normal
    }

    alerts_multi = generate_hybrid_alert("HPR001", sensor_values_multi, {}, LIMITS)

    assert len(alerts_multi) > 0, "Multi-sensor fault alert üretilmeli!"
    alert = alerts_multi[0]
    assert alert.get('multi_sensor', False) is True, "Multi-sensorde multi_sensor True olmalı!"
    assert alert.get('fault_count', 0) >= 2, "En az 2 fault olmalı!"


# ─── SENARYO 6: GECE VARDİYASI (DÜŞÜK LOAD) ─────────────────────────────
def test_night_shift_low_load():
    """Gece üretimi az, makineler düşük yükte — alert olmamalı."""
    sensor_values_night = {
        "oil_tank_temperature": 35.0,      # Düşük (normal: 38-42)
        "main_pressure": 75.0,             # Düşük (normal: 95-105)
        "horizontal_press_pressure": 85.0, # Düşük
        "lower_ejector_pressure": 65.0,    # Düşük
        "horitzonal_infeed_speed": 80.0,   # Düşük
        "vertical_infeed_speed": 70.0,     # Düşük
    }

    alerts_night = generate_hybrid_alert(
        "HPR001",
        sensor_values_night,
        {},
        LIMITS
    )

    assert len(alerts_night) == 0, "Düşük load gece vardiyasında alert olmamalı!"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
