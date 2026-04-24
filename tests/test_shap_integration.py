"""
test_shap_integration.py — SHAP Integration Test
═════════════════════════════════════════════════
ML predictor SHAP explanation test eder.
"""

import pytest
from pipeline.ml_predictor import predictor


def test_shap_integration_predict_risk():
    """ML predictor risk prediction ve explanation üretmeli."""
    machine_id = "HPR001"

    state = {
        "buffers": {
            "main_pressure": [150.0] * 30,
            "horizontal_press_pressure": [120.0] * 30,
            "oil_tank_temperature": [65.0] * 30
        },
        "ewma_mean": {
            "main_pressure": 150.0,
            "horizontal_press_pressure": 120.0,
            "oil_tank_temperature": 65.0
        },
        "ewma_var": {
            "main_pressure": 0.0,
            "horizontal_press_pressure": 0.0,
            "oil_tank_temperature": 0.0
        },
        "sample_count": {
            "main_pressure": 30,
            "horizontal_press_pressure": 30,
            "oil_tank_temperature": 30
        }
    }

    result = predictor.predict_risk(machine_id, state)

    assert result.score >= 0.0, "Score 0'dan büyük/eşit olmalı!"
    assert result.confidence >= 0.0, "Confidence 0'dan büyük/eşit olmalı!"
    assert isinstance(result.top_features, list), "Top features liste olmalı!"
    assert len(result.top_features) > 0, "En az bir top feature olmalı!"
    assert isinstance(result.explanation, str), "Explanation string olmalı!"
    assert len(result.explanation) > 0, "Explanation boş olmamalı!"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
