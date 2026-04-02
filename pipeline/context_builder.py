"""
context_builder.py — AI Usta Başı için Bağlam Paketi Derleyici
═══════════════════════════════════════════════════════════════
Her makine için mevcut sensör durumu, trend, fizik kuralları ve
ETA tahminlerini tek bir yapılandırılmış pakette birleştirir.
Bu paket llm_engine.py'ye gönderilir.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

# HPR tip grupları — Yatay presler oil_tank_temperature sensörü içermiyor
_YATAY_PRESLER = {"HPR002", "HPR004", "HPR006"}
_DIKEY_PRESLER = {"HPR001", "HPR003", "HPR005"}

# Sensör Türkçe isimleri ve birimleri
SENSOR_META = {
    "oil_tank_temperature": {"name": "Yağ Sıcaklığı", "unit": "°C"},
    "main_pressure": {"name": "Ana Basınç", "unit": "bar"},
    "horizontal_press_pressure": {"name": "Yatay Basınç", "unit": "bar"},
    "lower_ejector_pressure": {"name": "Alt Ejektör Basıncı", "unit": "bar"},
    "horitzonal_infeed_speed": {"name": "Yatay Besleme Hızı", "unit": "mm/s"},
    "vertical_infeed_speed": {"name": "Dikey Besleme Hızı", "unit": "mm/s"},
}


# Limitlerin yüzdesi → durum etiketi
def _pct_label(pct: float) -> str:
    if pct >= 100:
        return "⛔ LİMİT AŞILDI"
    if pct >= 90:
        return "🔴 KRİTİK YAKLAŞIM"
    if pct >= 75:
        return "🟡 DİKKAT"
    return "✅ Normal"


def _trend_arrow(slope: float | None) -> str:
    if slope is None:
        return "→"
    if slope > 0.05:
        return "↑"
    if slope < -0.05:
        return "↓"
    return "→"


def build(
    machine_id: str,
    machine_data: dict,
    limits: dict,
    causal_rules_path: str = None,
) -> dict:
    """
    Tek bir makine için bağlam paketi oluşturur.

    Args:
        machine_id:        "HPR001" vb.
        machine_data:      hpr_monitor.py içindeki machine_data[mid] sözlüğü
        limits:            limits_config.yaml'dan yüklenen makine limitleri
        causal_rules_path: causal_rules.json dosya yolu (opsiyonel)

    Returns:
        LLM'e gönderilecek yapılandırılmış dict
    """
    md = machine_data
    sensors = md.get("sensors", {})
    trends = md.get("trend_info", {})
    mac_lims = limits.get(machine_id, {})

    # ── 0. Türetilmiş sensör değerleri (kural değerlendirmesi için) ─────────
    # causal_rules.json'daki bazı kurallar doğrudan ölçülen değer değil,
    # hesaplanmış oran (ratio) veya ayrı kaynaktan gelen değerler kullanıyor.
    # Bunları bir "zenginleştirilmiş" dict'e ekleyip kurallara veriyoruz.
    # Orijinal sensors dict'i değiştirilmiyor — sadece kural kontrolünde kullanılıyor.
    enriched_sensors = dict(sensors)

    # main_pressure_ratio: Ana basıncın limit maksimumuna oranı (0.0 - 1.0+)
    _p_val = sensors.get("main_pressure")
    _p_lim = mac_lims.get("main_pressure", {}).get("max")
    if _p_val is not None and _p_lim and _p_lim > 0:
        enriched_sensors["main_pressure_ratio"] = round(_p_val / _p_lim, 3)

    # horitzonal_infeed_speed_ratio: Yatay hızın mutlak değerinin limit oranı
    _hs_val = sensors.get("horitzonal_infeed_speed")
    _hs_lim = mac_lims.get("horitzonal_infeed_speed", {}).get("max")
    if _hs_val is not None and _hs_lim and abs(_hs_lim) > 0:
        enriched_sensors["horitzonal_infeed_speed_ratio"] = round(
            abs(_hs_val) / abs(_hs_lim), 3
        )

    # vertical_infeed_speed_ratio: Dikey hızın mutlak değerinin limit oranı
    _vs_val = sensors.get("vertical_infeed_speed")
    _vs_lim = mac_lims.get("vertical_infeed_speed", {}).get("max")
    if _vs_val is not None and _vs_lim and abs(_vs_lim) > 0:
        enriched_sensors["vertical_infeed_speed_ratio"] = round(
            abs(_vs_val) / abs(_vs_lim), 3
        )

    # operating_minutes: machine_data'dan al — cold_startup_mask kuralı için
    enriched_sensors["operating_minutes"] = md.get("operating_minutes", 0)

    # ── KATMAN 2: Yeni Zengin Metrikler ──────────────────────────────────

    # filter_dirty_minutes: bool_active_since'den filtre kirliliği süresi
    # boolean sensörler için machine_data["booleans"] aktärılır (kac dakika kotu durumda)
    _bool_actives = md.get("booleans", {})
    _filter_bad_minutes = 0.0
    for _bkey in ("pressure_line_filter_1_dirty", "pressure_line_filter_2_dirty",
                  "pressure_line_filter_3_dirty", "pressure_line_filter_4_dirty"):
        _bad_min = _bool_actives.get(_bkey)
        if _bad_min and isinstance(_bad_min, (int, float)) and _bad_min > 0:
            _filter_bad_minutes = max(_filter_bad_minutes, _bad_min)
    enriched_sensors["pressure_line_filter_dirty_minutes"] = _filter_bad_minutes

    # trend_direction: Ana basınç trendini okunabilir etiketle ver
    _press_slope = trends.get("main_pressure")
    if _press_slope is None:
        enriched_sensors["trend_direction"] = "STABIL"
    elif _press_slope > 0.5:
        enriched_sensors["trend_direction"] = "ARTIYOR"
    elif _press_slope < -0.5:
        enriched_sensors["trend_direction"] = "AZALIYOR"
    else:
        enriched_sensors["trend_direction"] = "STABIL"

    # horizontal_press_pressure_ratio: Yatay presler için
    _hp_val = sensors.get("horizontal_press_pressure")
    _hp_lim = mac_lims.get("horizontal_press_pressure", {}).get("max")
    if _hp_val is not None and _hp_lim and _hp_lim > 0:
        enriched_sensors["horizontal_press_pressure_ratio"] = round(_hp_val / _hp_lim, 3)

    # ── 1. Sensör durumları ─────────────────────────────────────────────────
    sensor_states = {}
    limit_violations = []
    critical_sensors = []

    for key, meta in SENSOR_META.items():
        val = sensors.get(key)
        if val is None:
            continue

        lim = mac_lims.get(key, {})
        max_lim = lim.get("max")
        min_lim = lim.get("min", 0)

        if max_lim and max_lim > 0:
            pct = abs(val) / max_lim * 100
        else:
            pct = 0.0

        slope = trends.get(key)
        direction = _trend_arrow(slope)
        label = _pct_label(pct)

        sensor_states[key] = {
            "turkish_name": meta["name"],
            "value": round(val, 2),
            "unit": meta["unit"],
            "limit_max": max_lim,
            "limit_pct": round(pct, 1),
            "status_label": label,
            "trend_arrow": direction,
            "slope_per_hour": round(slope, 3) if slope else None,
        }

        if pct >= 100:
            limit_violations.append(
                f"{meta['name']}: {val}{meta['unit']} (limit: {max_lim})"
            )
        elif pct >= 85:
            critical_sensors.append(
                f"{meta['name']}: limitin %{pct:.0f}'inde {direction}"
            )

    # ── 2. ETA tahminleri (trend_info'dan) ──────────────────────────────────
    eta_predictions = {}
    for key, slope in trends.items():
        meta = SENSOR_META.get(key, {})
        lim = mac_lims.get(key, {})
        max_l = lim.get("max")
        val = sensors.get(key)
        if not (slope and max_l and val is not None and slope > 0):
            continue
        remaining = max_l - val
        if remaining <= 0:
            continue
        eta_min = (remaining / slope) * 60  # slope saat başına
        if 1 < eta_min < 480:  # 1dk - 8 saat arası mantıklı
            eta_predictions[key] = {
                "sensor_name": meta.get("name", key),
                "eta_minutes": round(eta_min),
                "current_value": round(val, 2),
                "limit": max_l,
                "unit": meta.get("unit", ""),
            }

    # ── 3. Aktif fizik / nedensellik kuralları ──────────────────────────────
    # causal_rules.json formatı:
    # {
    #   "rules": {
    #     "thermal_stress": {
    #       "condition": {"oil_tank_temperature": "> 40", "main_pressure": "> 100"},
    #       "explanation_tr": "...",
    #       "action_tr": "..."
    #     }, ...
    #   }
    # }
    active_rules = []
    if causal_rules_path and os.path.exists(causal_rules_path):
        try:
            data = json.load(open(causal_rules_path, encoding="utf-8"))
            rules_dict = data.get("rules", {})

            # HPR tipi filtresi — yanat presler için sıcaklık kuralı atlat
            _is_yatay = machine_id in _YATAY_PRESLER

            for rule_name, rule_data in rules_dict.items():
                if not isinstance(rule_data, dict):
                    continue

                # HPR tipi filtreleme
                hpr_types = rule_data.get("hpr_types")
                if hpr_types:
                    if _is_yatay and "yatay_pres" not in hpr_types:
                        continue  # Yatay pres bu kuralı atlatsın
                    if not _is_yatay and "dikey_pres" not in hpr_types:
                        continue  # Dikey pres bu kuralı atlatsın

                condition = rule_data.get("condition", {})
                matched = True

                for sensor_key, expr in condition.items():
                    # enriched_sensors önce kontrol et (ratio ve türetilmiş değerler),
                    # yoksa orijinal sensors'a bak
                    val = enriched_sensors.get(sensor_key)
                    if val is None:
                        matched = False
                        break

                    # expr formatı: "> 40" veya "< 0.2"
                    try:
                        parts = str(expr).strip().split(" ", 1)
                        if len(parts) != 2:
                            matched = False
                            break
                        op, threshold_str = parts
                        threshold = float(threshold_str)

                        if op == ">" and not (val > threshold):
                            matched = False
                            break
                        if op == ">=" and not (val >= threshold):
                            matched = False
                            break
                        if op == "<" and not (val < threshold):
                            matched = False
                            break
                        if op == "<=" and not (val <= threshold):
                            matched = False
                            break
                    except (ValueError, AttributeError):
                        matched = False
                        break

                if matched:
                    explanation = rule_data.get("explanation_tr", rule_name)
                    action = rule_data.get("action_tr", "")
                    active_rules.append(explanation)
                    if action:
                        active_rules.append(f"→ Öneri: {action}")

        except Exception as e:
            import logging as _log

            _log.getLogger("context_builder").warning(
                "causal_rules.json okunamadı (%s): %s", causal_rules_path, e
            )

    # ── 4. Makine genel durumu ───────────────────────────────────────────────
    risk_score = md.get("risk_score", 0.0)
    severity = md.get("severity", "NORMAL")
    operating_min = md.get("operating_minutes", 0)
    last_src = md.get("last_alert_source", "")
    alert_count = md.get("alert_count", 0)
    confidence = md.get("confidence", 0.0)

    operating_h = operating_min // 60
    operating_m = operating_min % 60

    # ── 5. Geçmiş benzer olaylar (SimilarityEngine v1 - Faz A) ────────────────
    similar_past_events = []
    try:
        from src.analysis.similarity_engine import SimilarityEngine
        import os
        v_path = os.path.join(os.path.dirname(__file__), "..", "data", "ml_training_data_v2.csv")
        sim_engine = SimilarityEngine(v_path)
        
        live_features = md.get("last_ml_features", {})
        if live_features:
            summary = sim_engine.find_similar_events(
                live_features=live_features,
                current_machine_id=machine_id,
                top_k=3
            )
            if summary and summary != "Geçmiş olay hafızası veritabanı aktif değil.":
                similar_past_events.append(summary)
                
    except Exception as _sim_err:
        import logging as _log2
        _log2.getLogger("context_builder").debug("SimilarityEngine hatası: %s", _sim_err)

    # ── 6. Son uyarı özeti ───────────────────────────────────────────────────
    last_alerts = md.get("last_alerts", [])

    return {
        "machine_id": machine_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "risk_score": round(risk_score, 1),
        "severity": severity,
        "confidence": round(confidence * 100, 0),
        "operating_time": f"{operating_h} saat {operating_m} dakika",
        "operating_minutes": operating_min,
        "last_alert_source": last_src,
        "alert_count_session": alert_count,
        "sensor_states": sensor_states,
        "limit_violations": limit_violations,
        "critical_sensors": critical_sensors,
        "eta_predictions": eta_predictions,
        "active_physics_rules": active_rules,
        "last_alerts": last_alerts[-3:] if last_alerts else [],
        "similar_past_events": similar_past_events,
    }


def build_all(machine_data: dict, limits: dict, causal_rules_path: str = None) -> dict:
    """Tüm HPR makineleri için bağlam paketleri oluşturur."""
    return {
        mid: build(mid, md, limits, causal_rules_path)
        for mid, md in machine_data.items()
        if mid.startswith("HPR")
    }
