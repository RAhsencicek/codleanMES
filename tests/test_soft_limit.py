"""
test_soft_limit.py — Soft Limit Warning Test
══════════════════════════════════════════════
%85 threshold soft limit warning test eder.
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


# ─── TEST 1: SOFT LIMIT (%85-100) ────────────────────────────────────────
def test_soft_limit_warning():
    """main_pressure %95'te (max: 110 → 104.5 bar) soft limit uyarısı vermeli."""
    sensor_values_soft = {
        "main_pressure": 104.5,            # max: 110 → %95.5 (SOFT LIMIT!)
        "horizontal_press_pressure": 105.0, # max: 120 → %87.5 (SOFT LIMIT!)
        "oil_tank_temperature": 38.0,      # Normal
    }

    alerts_soft = generate_hybrid_alert(
        "HPR001",
        sensor_values_soft,
        {},
        LIMITS
    )

    assert len(alerts_soft) > 0, "Soft limit durumunda alert üretilmeli!"
    alert = alerts_soft[0]
    assert alert['type'] == 'SOFT_LIMIT_WARNING', "SOFT_LIMIT_WARNING olmalı!"
    assert alert['severity'] == 'DÜŞÜK', "Severity DÜŞÜK olmalı!"
    assert alert['confidence'] == 0.8, "Confidence 0.8 olmalı!"


# ─── TEST 2: HARD_FAULT VARSA SOFT_LIMIT GÖSTERİLMEZ ─────────────────────
def test_hard_fault_priority_over_soft_limit():
    """Hard fault varsa soft limit bastırılmalı (alert spam önleme)."""
    sensor_values_mixed = {
        "main_pressure": 118.0,            # max: 110 → %107.3 (HARD FAULT!)
        "horizontal_press_pressure": 115.0, # max: 120 → %95.8 (SOFT LIMIT)
        "oil_tank_temperature": 38.0,      # Normal
    }

    alerts_mixed = generate_hybrid_alert(
        "HPR001",
        sensor_values_mixed,
        {},
        LIMITS
    )

    assert len(alerts_mixed) > 0, "Alert üretilmedi (BEKLENMEYEN!)"
    alert = alerts_mixed[0]
    # Hard fault öncelikli olmalı
    assert alert['type'] == 'FAULT', "FAULT olmalı (soft limit değil)!"
    assert alert['severity'] in ['YÜKSEK', 'KRİTİK'], "Severity YÜKSEK/KRİTİK olmalı!"


# ─── TEST 3: MULTI-SENSOR SOFT LIMIT ─────────────────────────────────────
def test_multi_sensor_soft_limit():
    """3 sensör birden %85+ threshold'ta multi-sensor soft limit detection."""
    sensor_values_multi_soft = {
        "main_pressure": 105.0,            # max: 110 → %95.5
        "horizontal_press_pressure": 116.0, # max: 120 → %96.7
        "lower_ejector_pressure": 106.0,   # max: 110 → %96.4
        "oil_tank_temperature": 43.0,      # max: 45 → %95.6
    }

    alerts_multi_soft = generate_hybrid_alert(
        "HPR001",
        sensor_values_multi_soft,
        {},
        LIMITS
    )

    assert len(alerts_multi_soft) > 0, "Alert üretilmedi (BEKLENMEYEN!)"
    alert = alerts_multi_soft[0]
    assert alert.get('soft_fault_count', 0) >= 2, "En az 2 soft fault olmalı!"


# ─── TEST 4: NORMAL OPERASYON (ALERT YOK) ────────────────────────────────
def test_normal_operation_no_alert():
    """Tüm sensörler %85'in altında — alert üretilmemeli."""
    sensor_values_all_normal = {
        "main_pressure": 90.0,             # max: 110 → %81.8 (< %85)
        "horizontal_press_pressure": 100.0, # max: 120 → %83.3 (< %85)
        "oil_tank_temperature": 38.0,      # Normal
    }

    alerts_normal = generate_hybrid_alert(
        "HPR001",
        sensor_values_all_normal,
        {},
        LIMITS
    )

    assert len(alerts_normal) == 0, "Normal operasyonda alert olmamalı!"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
