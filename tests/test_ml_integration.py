"""
test_ml_integration.py — ML Entegrasyon Testi
══════════════════════════════════════════════
Gerçek pipeline akışını (state_store → ml_predictor → risk_scorer → alert_engine)
sahte sensör verisiyle test eder. Kafka bağlantısı gerekmez.

Çalıştır:
  python3 test_ml_integration.py
"""

import sys, os, time, json
from datetime import datetime, timezone

# ─── proje kökünü path'e ekle ─────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core import state_store       as store
from src.analysis import threshold_checker as thresh
from src.analysis import trend_detector    as trend
from src.analysis import risk_scorer       as scorer
from src.alerts import alert_engine      as alerter

# ─── Test limitleri (HPR001 için limits_config.yaml'dan kopyalandı) ──────────
LIMITS = {
    "HPR001": {
        "oil_tank_temperature":      {"min": 0,    "max": 45.0,  "unit": "°C"},
        "main_pressure":             {"min": 0,    "max": 110.0, "unit": "bar"},
        "horizontal_press_pressure": {"min": 0,    "max": 120.0, "unit": "bar"},
        "lower_ejector_pressure":    {"min": 0,    "max": 110.0, "unit": "bar"},
        "horitzonal_infeed_speed":   {"min": -300, "max": 300.0, "unit": "mm/s"},
        "vertical_infeed_speed":     {"min": -300, "max": 300.0, "unit": "mm/s"},
    }
}

SENSORS = list(LIMITS["HPR001"].keys())
MID     = "HPR001"

# ─── Yardımcılar ─────────────────────────────────────────────────────────────

def feed_state(state: dict, mid: str, sensor_vals: dict, n_steps: int = 50):
    """State Store'u n_steps kez senaryo değerleriyle doldur."""
    for _ in range(n_steps):
        for sensor, val in sensor_vals.items():
            store.update_numeric(state, mid, sensor, val, alpha=0.10)

def run_pipeline(state: dict, mid: str, sensor_vals: dict):
    """Tek geçişte tam pipeline'ı çalıştır ve RiskEvent döndür."""
    t_sigs = []
    r_sigs = []
    for sensor, val in sensor_vals.items():
        sig = thresh.check_threshold(mid, sensor, val, LIMITS)
        if sig:
            t_sigs.append(sig)
        buf  = store.get_buffer(state, mid, sensor)
        tsig = trend.analyze_sensor_trend(
            mid, sensor, buf, LIMITS,
            interval_sec=10, min_samples=10, r2_threshold=0.60,
        )
        if tsig:
            r_sigs.append(tsig)

    confs  = [store.get_confidence(state, mid, s) for s in SENSORS[:4]]
    avg_c  = sum(confs) / len(confs) if confs else 0.1

    event = scorer.calculate_risk(
        mid, t_sigs, r_sigs, avg_c,
        sensor_values={k: f"{v:.2f}" for k, v in sensor_vals.items()},
        state=state.get(mid, {}),
    )
    return event, t_sigs, r_sigs, avg_c

# ═══════════════════════════════════════════════════════════════════════════
# SENARYOLAR
# ═══════════════════════════════════════════════════════════════════════════

def test_normal_operation():
    """NORMAL durum: hiç alert üretilmemeli."""
    print("\n" + "─"*55)
    print("  TEST 1: Normal Operasyon")
    print("─"*55)
    state = {}
    normal_vals = {
        "oil_tank_temperature":      35.0,
        "main_pressure":             80.0,
        "horizontal_press_pressure": 90.0,
        "lower_ejector_pressure":    85.0,
        "horitzonal_infeed_speed":   150.0,
        "vertical_infeed_speed":     100.0,
    }
    feed_state(state, MID, normal_vals, n_steps=60)
    event, t_sigs, r_sigs, conf = run_pipeline(state, MID, normal_vals)

    print(f"  Threshold sinyali : {len(t_sigs)}")
    print(f"  Trend sinyali     : {len(r_sigs)}")
    print(f"  Confidence        : {conf:.2f}")
    print(f"  Risk Event        : {event}")

    if event is None or event.risk_score < 25:
        print("  ✅ GEÇTI — Normal operasyonda alert yok (beklenen)")
        return True
    else:
        print(f"  ❌ BAŞARISIZ — Beklenmedik alert: skor={event.risk_score:.0f}")
        return False


def test_oil_temp_fault():
    """YAĞ SICAKLIĞI AŞIMI: limit 45°C, değer 48°C → YÜKSEK alert beklenir."""
    print("\n" + "─"*55)
    print("  TEST 2: Yağ Sıcaklığı Limit Aşımı (48°C > 45°C)")
    print("─"*55)
    state = {}
    # Önce normal geçmiş yükle
    feed_state(state, MID, {
        "oil_tank_temperature":      38.0,
        "main_pressure":             80.0,
        "horizontal_press_pressure": 90.0,
        "lower_ejector_pressure":    85.0,
        "horitzonal_infeed_speed":   150.0,
        "vertical_infeed_speed":     100.0,
    }, n_steps=60)
    # Sonra aşım değeri
    fault_vals = dict(oil_tank_temperature=48.0, main_pressure=80.0,
                      horizontal_press_pressure=90.0, lower_ejector_pressure=85.0,
                      horitzonal_infeed_speed=150.0, vertical_infeed_speed=100.0)
    event, t_sigs, r_sigs, conf = run_pipeline(state, MID, fault_vals)

    print(f"  Threshold sinyali : {len(t_sigs)} → {[s.severity for s in t_sigs]}")
    print(f"  Confidence        : {conf:.2f}")
    if event:
        print(f"  Risk Skoru        : {event.risk_score:.1f}")
        print(f"  Severity          : {event.severity}")
        ml_s = getattr(event, "ml_score", 0)
        ml_c = getattr(event, "ml_confidence", 0)
        print(f"  ML Skoru          : {ml_s:.1f}  (anomali %{ml_c*100:.0f})")
        print(f"  ML Açıklama       : {getattr(event, 'ml_explanation', '—')}")

    if event and event.risk_score >= 25:
        print("  ✅ GEÇTI — Limit aşımı tespit edildi")
        return True
    else:
        print("  ❌ BAŞARISIZ — Limit aşımı tespit edilemedi")
        return False


def test_multi_sensor_fault():
    """ÇOKLU SENSÖR AŞIMI: ML modeli active_sensors=2+ için daha yüksek skor vermeli."""
    print("\n" + "─"*55)
    print("  TEST 3: Çoklu Sensör Aşımı (oil_temp + main_pressure)")
    print("─"*55)
    state = {}
    feed_state(state, MID, {
        "oil_tank_temperature":      38.0,
        "main_pressure":             80.0,
        "horizontal_press_pressure": 90.0,
        "lower_ejector_pressure":    85.0,
        "horitzonal_infeed_speed":   150.0,
        "vertical_infeed_speed":     100.0,
    }, n_steps=60)

    multi_fault = dict(
        oil_tank_temperature=49.0,       # limit 45 → aşım
        main_pressure=120.0,             # limit 110 → aşım
        horizontal_press_pressure=90.0,
        lower_ejector_pressure=85.0,
        horitzonal_infeed_speed=150.0,
        vertical_infeed_speed=100.0,
    )
    event, t_sigs, r_sigs, conf = run_pipeline(state, MID, multi_fault)

    print(f"  Threshold sinyali : {len(t_sigs)} → {[s.sensor for s in t_sigs]}")
    if event:
        print(f"  Risk Skoru        : {event.risk_score:.1f}")
        print(f"  Severity          : {event.severity}")
        ml_s = getattr(event, "ml_score", 0)
        ml_c = getattr(event, "ml_confidence", 0)
        print(f"  ML Skoru          : {ml_s:.1f}  (anomali %{ml_c*100:.0f})")
        print(f"  ML Açıklama       : {getattr(event, 'ml_explanation', '—')}")

    if event and event.risk_score >= 40:
        print("  ✅ GEÇTI — Çoklu sensör aşımı yüksek risk skoru verdi")
        return True
    else:
        print("  ❌ BAŞARISIZ — Çoklu sensör skoru beklenenin altında")
        return False


def test_pre_fault_trend():
    """PRE-FAULT TREND: Yağ sıcaklığı 40→44°C trendinde yükseliyor, ETA hesaplanmalı."""
    print("\n" + "─"*55)
    print("  TEST 4: Artan Trend (oil_temp 40→44°C, limit 45)")
    print("─"*55)
    state = {}
    # Artımlı değerlerle state doldur
    for i in range(80):
        temp = 40.0 + i * 0.05   # 40 → 44°C
        store.update_numeric(state, MID, "oil_tank_temperature", temp, alpha=0.10)
        for sensor in ["main_pressure", "horizontal_press_pressure",
                       "lower_ejector_pressure", "horitzonal_infeed_speed",
                       "vertical_infeed_speed"]:
            store.update_numeric(state, MID, sensor, 80.0, alpha=0.10)

    current_vals = dict(
        oil_tank_temperature=44.0,
        main_pressure=80.0,
        horizontal_press_pressure=90.0,
        lower_ejector_pressure=85.0,
        horitzonal_infeed_speed=150.0,
        vertical_infeed_speed=100.0,
    )
    event, t_sigs, r_sigs, conf = run_pipeline(state, MID, current_vals)

    print(f"  Threshold sinyali : {len(t_sigs)}")
    print(f"  Trend sinyali     : {len(r_sigs)}")
    if event:
        print(f"  Risk Skoru        : {event.risk_score:.1f}")
        print(f"  Severity          : {event.severity}")
        if event.eta_minutes:
            h, m = divmod(int(event.eta_minutes), 60)
            print(f"  ETA               : {h}sa {m}dk")
        ml_s = getattr(event, "ml_score", 0)
        ml_c = getattr(event, "ml_confidence", 0)
        print(f"  ML Skoru          : {ml_s:.1f}  (anomali %{ml_c*100:.0f})")

    # Trend veya Threshold sinyali yakalandıysa başarı
    if r_sigs or (event and event.risk_score >= 10):
        print("  ✅ GEÇTI — Artış trendi tespit edildi")
        return True
    else:
        print("  ❌ BAŞARISIZ — Trend tespit edilemedi")
        return False


def test_alert_throttle():
    """THROTTLE: Aynı makineden 30 dk içinde ikinci alert üretilmemeli."""
    print("\n" + "─"*55)
    print("  TEST 5: Alert Throttle (30 dk)") 
    print("─"*55)
    from src.analysis.risk_scorer import RiskEvent
    from datetime import datetime as dt

    alerter._last_alert.clear()

    fake_event = RiskEvent(
        machine_id="HPR001", risk_score=70.0, severity="YÜKSEK",
        confidence=0.85, reasons=["Test: oil_tank_temperature aşımı"],
    )
    r1 = alerter.process_alert(fake_event, min_score=20)
    r2 = alerter.process_alert(fake_event, min_score=20)   # throttle devrede

    print(f"  1. alert üretildi : {r1}")
    print(f"  2. alert (throttle): {r2}")

    if r1 and not r2:
        print("  ✅ GEÇTI — Throttle doğru çalışıyor")
        return True
    else:
        print("  ❌ BAŞARISIZ — Throttle sorunu")
        return False

# ═══════════════════════════════════════════════════════════════════════════
# ANA ÇALIŞTIRICI
# ═══════════════════════════════════════════════════════════════════════════

def main():
    from pipeline.ml_predictor import predictor
    t0 = time.time()
    print(f"\n{'═'*55}")
    print(f"  ML Entegrasyon Testleri")
    print(f"  ML Predictor aktif: {predictor.is_active}")
    print(f"  {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"{'═'*55}")

    tests = [
        test_normal_operation,
        test_oil_temp_fault,
        test_multi_sensor_fault,
        test_pre_fault_trend,
        test_alert_throttle,
    ]

    results = []
    for t in tests:
        try:
            results.append(t())
        except Exception as e:
            print(f"  💥 Test hata verdi: {e}")
            import traceback; traceback.print_exc()
            results.append(False)

    passed = sum(results)
    total  = len(results)
    elapsed = time.time() - t0

    print(f"\n{'═'*55}")
    print(f"  SONUÇ: {passed}/{total} test geçti  ({elapsed:.1f}sn)")
    if passed == total:
        print("  ✅ Tüm testler başarılı!")
    else:
        failed = [i+1 for i, r in enumerate(results) if not r]
        print(f"  ❌ Başarısız testler: {failed}")
    print(f"{'═'*55}\n")
    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(main())
