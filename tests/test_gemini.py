from pipeline.llm_engine import UstaBasi

usta = UstaBasi(model_name="gemini-2.5-flash")
print("Hazır mı:", usta.is_ready)

test_ctx = {
    "machine_id": "HPR001",
    "timestamp": "2026-03-23 14:35:00",
    "risk_score": 75.0,
    "severity": "YÜKSEK",
    "confidence": 85.0,
    "operating_time": "141 saat 36 dakika",
    "operating_minutes": 8496,
    "last_alert_source": "KURAL",
    "alert_count_session": 3,
    "sensor_states": {
        "oil_tank_temperature": {
            "turkish_name": "Yağ Sıcaklığı",
            "value": 44.7, "unit": "°C",
            "limit_max": 45.0, "limit_pct": 99.3,
            "status_label": "🔴 KRİTİK YAKLAŞIM",
            "trend_arrow": "↑", "slope_per_hour": 0.36,
        },
        "main_pressure": {
            "turkish_name": "Ana Basınç",
            "value": 87.3, "unit": "bar",
            "limit_max": 110.0, "limit_pct": 79.4,
            "status_label": "✅ Normal",
            "trend_arrow": "→", "slope_per_hour": 0.02,
        },
    },
    "limit_violations": [],
    "critical_sensors": ["Yağ Sıcaklığı: limitin %99'inde ↑"],
    "eta_predictions": {
        "oil_tank_temperature": {
            "sensor_name": "Yağ Sıcaklığı",
            "eta_minutes": 55,
            "current_value": 44.7,
            "limit": 45.0,
            "unit": "°C",
        }
    },
    "active_physics_rules": [
        "Termal stres: sıcaklık >42°C + basınç >80 bar → hidrolik zorlanma riski"
    ],
    "similar_past_events": [],
    "last_alerts": [],
}

print()
print("=== AI USTA BAŞI ANALİZİ ===")
result = usta.analyze(test_ctx, force=True)
print(result if result else "⚠️ Boş yanıt — API key veya bağlantı sorunu")
