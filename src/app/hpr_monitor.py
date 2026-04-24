"""
HPR Monitor — Dikey Pres Arıza Tahmin Sistemi
══════════════════════════════════════════════
Sadece HPR (Dikey Pres) makinelerini izler.
Sistem performansını değerlendirmek için tasarlandı.

Çalıştır: PYTHONPATH=. python3 src/app/hpr_monitor.py
"""

import json
import logging
import os
import signal
import sys
import threading
import time
from collections import defaultdict
from datetime import date, datetime, UTC
from typing import Any, Dict, List, Optional, cast

import yaml
from confluent_kafka import Consumer, KafkaError

from scripts.data_tools import context_collector as rich_collector
from scripts.data_tools import window_collector as collector

# ─── Günlük Veri Yöneticisi ───────────────────────────────────────────────────
from scripts.data_tools.daily_data_manager import (
    get_daily_summary,
    save_alert,
    save_context,
    save_raw_message,
    save_violation,
    update_daily_summary,
)
from src.alerts import alert_engine as alerter

from src.analysis.causal_evaluator import CausalEvaluator
from src.analysis import threshold_checker as thresh
from src.analysis import trend_detector as trend
from src.analysis import risk_scorer
from src.core import data_validator as validator
from src.core import state_store as store

# ─── ML Predictor (opsiyonel — model yoksa gracefully degrade) ───────────────
try:
    from pipeline.ml_predictor import predictor as _ml_predictor

    _ML_AVAILABLE = (
        True  # Import başarısı yeterli; is_active çalışma zamanında kontrol edilir
    )
except Exception as _e:
    _ml_predictor: Optional[Any] = None
    _ML_AVAILABLE = False

# ─── AI Usta Başı (opsiyonel — API key yoksa gracefully degrade) ──────────────
try:
    from pipeline import context_builder
    from pipeline.llm_engine import get_usta

    _usta = get_usta()
    _USTA_AVAILABLE = _usta.is_ready
except Exception as _ue:
    _usta: Optional[Any] = None
    _USTA_AVAILABLE = False

# Makine başına son AI analiz metni + üretim zamanı (bayatlama kontrolü için)
# Format: {"text": str, "ts": datetime | None}
_ai_analysis: dict[str, dict] = defaultdict(lambda: {"text": "", "ts": None})

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("hpr")

# ─── Config ──────────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CONFIG_PATH = os.environ.get(
    "CONFIG_PATH", os.path.join(_ROOT, "config", "limits_config.yaml")
)

try:
    with open(_CONFIG_PATH) as f:
        CONFIG = yaml.safe_load(f)
except FileNotFoundError:
    log.error("Hata: Konfig dosyasi bulunamadi -> %s", _CONFIG_PATH)
    log.error("CONFIG_PATH environment variable'i ile yol belirtin.")
    sys.exit(1)

LIMITS = CONFIG.get("machine_limits", {})
BOOL_RULES = CONFIG.get("boolean_rules", {})
EWMA_ALPHA = CONFIG.get("ewma_alpha", {})
PIPELINE = CONFIG.get("pipeline", {})
CAUSAL_RULES_PATH = os.path.join(
    _ROOT, "docs", "causal_rules.json"
)  # v2: 10 altın kural — HPR tipi bazlı filtreleme

causal_evaluator = CausalEvaluator(CAUSAL_RULES_PATH)

KAFKA_CFG = CONFIG["kafka"]
# Env var override — production ortamında YAML'ı değiştirmeye gerek yok
if os.environ.get("KAFKA_BOOTSTRAP_SERVERS"):
    KAFKA_CFG["bootstrap_servers"] = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
if os.environ.get("KAFKA_TOPIC"):
    KAFKA_CFG["topic"] = os.environ["KAFKA_TOPIC"]
if os.environ.get("KAFKA_GROUP_ID"):
    KAFKA_CFG["group_id"] = os.environ["KAFKA_GROUP_ID"]

HPR_MACHINES = [m for m in LIMITS if m.startswith("HPR")]

# İzlenecek sayısal sensörler (öncelik sırası)
KEY_SENSORS = [
    "main_pressure",
    "horizontal_press_pressure",
    "oil_tank_temperature",
]

# ─── State ───────────────────────────────────────────────────────────────────
state: Dict[str, Any] = store.load_state()
startup_state: Dict[str, Any] = {}
running = True

machine_data: Dict[str, Dict[str, Any]] = defaultdict(
    lambda: {
        "execution": "—",
        "sensors": {},
        "booleans": {},
        "risk_score": 0.0,
        "severity": "",
        "confidence": 0.0,
        "alert_count": 0,
        "last_alerts": cast(List[Any], []),  # Son 3 alert
        "trend_info": {},  # {sensor: slope_per_hour}
        "last_signal_ts": None,  # Zamana dayalı decay için
        "last_alert_source": "",  # "KURAL" | "ML"
        "diagnosis": "",          # "Aktif Arıza Teşhisi" (Kısa İsim)
        "diagnosis_desc": "",     # Teşhis açıklaması
    }
)

# Tüm HPR makinelerini başlat
for mid in HPR_MACHINES:
    _ = machine_data[mid]  # defaultdict otomatik başlatır

stats: Dict[str, Any] = {"total": 0, "hpr_msgs": 0, "alerts": 0, "start": datetime.now()}


# ─── Makine verilerini state'den yenile ──────────────────────────────────────
def refresh_machine_data():
    """
    Tüm HPR makinelerinin verilerini state store'dan okuyarak
    machine_data dictionary'sini günceller.
    """
    all_hpr = sorted(HPR_MACHINES)

    for mid in all_hpr:
        ms = state.get(mid, {})
        md = machine_data[mid]

        # State'den EWMA ortalama değerlerini oku
        if ms.get("ewma_mean"):
            for sensor, ewma_val in ms.get("ewma_mean", {}).items():
                md["sensors"][sensor] = round(ewma_val, 1)

            # Boolean sensörler - Kaç dakikadır aktif? (ISO string çözümlemesi)
            for sensor, bad_str in ms.get("bool_active_since", {}).items():
                if not bad_str:
                    continue
                try:
                    from datetime import datetime, timezone
                    dt = datetime.fromisoformat(bad_str.replace("Z", "+00:00"))
                    if dt.tzinfo is not None:
                        bad_min = (datetime.now(timezone.utc) - dt).total_seconds() / 60
                    else:
                        bad_min = (datetime.now(UTC) - dt).total_seconds() / 60
                    if bad_min > 0:
                        md["booleans"][sensor] = round(bad_min, 1)
                except Exception:
                    pass

            # Execution status
            if ms.get("last_execution"):
                md["execution"] = ms["last_execution"]

        # Operating minutes güncelle
        md["operating_minutes"] = store.get_operating_minutes(state, mid)

        # CAUSAL RULES DEĞERLENDİRME
        diag_name, diag_desc = causal_evaluator.evaluate(md)
        md["diagnosis"] = diag_name
        md["diagnosis_desc"] = diag_desc

        if mid not in state:
            state[mid] = {}
        state[mid]["diagnosis"] = diag_name
        state[mid]["diagnosis_desc"] = diag_desc


# ─── İşleme ──────────────────────────────────────────────────────────────────
def process(raw: dict):
    packets = validator.process_message(raw, state, startup_state)

    for pkt in packets:
        mid = pkt["machine_id"]

        # ── Günlük veri saklama ─────────────────────────────────────────────
        if "timestamp" in pkt:
            try:
                msg_time = datetime.fromisoformat(
                    pkt["timestamp"].replace("Z", "+00:00")
                )
                save_raw_message(
                    {
                        "machine_id": mid,
                        "timestamp": pkt["timestamp"],
                        "numeric": pkt.get("numeric", {}),
                        "boolean": pkt.get("boolean", {}),
                        "is_stale": pkt.get("is_stale", False),
                        "is_startup": pkt.get("is_startup", False),
                    },
                    date_str=msg_time.strftime("%Y-%m-%d"),
                )
            except Exception as e:
                log.debug("Günlük kayıt hatası: %s", e)
        # ────────────────────────────────────────────────────────────────────

        # Sadece HPR
        if not mid.startswith("HPR"):
            continue

        stats["hpr_msgs"] = cast(int, stats["hpr_msgs"]) + 1
        md = machine_data[mid]

        if "execution" in pkt["text"]:
            md["execution"] = pkt["text"]["execution"]

        t_signals = []
        r_signals = []

        for sensor, value in pkt["numeric"].items():
            alpha = EWMA_ALPHA.get("HPR", {}).get(
                sensor, EWMA_ALPHA.get("default", 0.10)
            )
            store.update_numeric(state, mid, sensor, value, alpha=alpha)
            md["sensors"][sensor] = value

            conf = store.get_confidence(state, mid, sensor)

            sig = thresh.check_threshold(mid, sensor, value, LIMITS)
            if sig:
                t_signals.append(sig)

            if not pkt["is_stale"] and not pkt["is_startup"]:
                buf = store.get_buffer(state, mid, sensor)
                tsig = trend.analyze_sensor_trend(
                    mid,
                    sensor,
                    buf,
                    LIMITS,
                    interval_sec=10,
                    min_samples=PIPELINE.get("min_samples_for_trend", 30),
                    r2_threshold=PIPELINE.get("trend_r2_threshold", 0.70),
                )
                if tsig:
                    r_signals.append(tsig)
                    md["trend_info"][sensor] = tsig.slope_per_hour

        for sensor, value in pkt["boolean"].items():
            rule = BOOL_RULES.get(sensor)
            sk = rule.get("success_key", True) if rule else True
            bad_min = store.update_boolean(state, mid, sensor, value, success_key=sk)
            if bad_min is not None:
                md["booleans"][sensor] = bad_min
                bsig = thresh.check_boolean(mid, sensor, bad_min, BOOL_RULES)
                if bsig:
                    t_signals.append(bsig)
            else:
                md["booleans"].pop(sensor, None)

        if t_signals or r_signals:
            # ── KURAL TABANLI YOL: Threshold + Trend + Physics + ML Ensemble ──
            confs = [
                store.get_confidence(state, mid, s) for s in list(pkt["numeric"])[:5]
            ]
            avg_c = sum(confs) / len(confs) if confs else 0.1
            event = risk_scorer.calculate_risk(
                mid,
                t_signals,
                r_signals,
                avg_c,
                sensor_values={k: f"{v:.2f}" for k, v in pkt["numeric"].items()},
                state=state.get(mid, {}),
                machine_limits=LIMITS.get(mid, {}),
            )
            if event:
                md["risk_score"] = event.risk_score
                md["severity"] = event.severity
                md["confidence"] = event.confidence
                md["last_signal_ts"] = datetime.now()
                md["last_alert_source"] = "KURAL"

                if alerter.process_alert(event, min_score=20):
                    stats["alerts"] = cast(int, stats["alerts"]) + 1
                    md["alert_count"] = cast(int, md["alert_count"]) + 1
                    log.info(
                        "[KURAL] %s | %s | skor=%.0f | %s",
                        mid,
                        event.severity,
                        event.risk_score,
                        event.reasons[0][:50],
                    )
                    # ── AI Usta Başı: alert sonrası arka planda analiz ──────
                    if _USTA_AVAILABLE:
                        ctx = context_builder.build(mid, md, LIMITS, CAUSAL_RULES_PATH)

                        def _cb(machine_id: str, text: str) -> None:
                            _ai_analysis[machine_id] = {
                                "text": text,
                                "ts": datetime.now(),
                            }
                            log.info("[AI] %s analizi hazir", machine_id)

                        _usta.analyze_async(ctx, _cb, force=True)
        else:
            # ── Zamana dayalı decay ──────────────────────────────────────────
            if md["risk_score"] > 0:
                last_decay = md.get("last_decay_ts", md.get("last_signal_ts") or datetime.now())
                elapsed_sec = (datetime.now() - last_decay).total_seconds()
                decay = (elapsed_sec / 60.0) * 5.0

                if decay > 0.5:
                    md["risk_score"] = max(md["risk_score"] - decay, 0.0)
                    if md["risk_score"] == 0:
                        md["last_signal_ts"] = None
                        md["last_alert_source"] = ""
                        md["severity"] = ""
                    md["last_decay_ts"] = datetime.now()

            # ── ML PRE-FAULT YOLU: Kural sinyali yokken ML erken uyarı ──────
            if (
                _ML_AVAILABLE
                and _ml_predictor.is_active
                and not pkt["is_stale"]
                and not pkt["is_startup"]
            ):
                hybrid_alerts = alerter.generate_hybrid_alert(
                    mid,
                    sensor_values=pkt["numeric"],
                    window_features=state.get(mid, {}),
                    limits_config=LIMITS,
                    ml_predictor=_ml_predictor,
                )
                for ha in hybrid_alerts:
                    if ha["type"] != "PRE_FAULT_WARNING":
                        continue
                    if alerter.process_hybrid_alert(ha, use_rich=False):
                        stats["alerts"] += 1
                        md["alert_count"] += 1
                        md["risk_score"] = min(ha.get("ml_score", 50.0), 100.0)
                        md["severity"] = ha.get("severity", "ORTA")
                        md["confidence"] = ha.get("confidence", 0.0)
                        md["last_signal_ts"] = datetime.now()
                        md["last_alert_source"] = "ML"
                        log.info(
                            "[ML] %s | %s | guven=%.0f%% | %s",
                            mid,
                            ha["severity"],
                            ha["confidence"] * 100,
                            ha["reasons"][0][:50],
                        )

        # ── Window Collectors ─────────────────────────────────────────
        if pkt["numeric"]:
            collector.record(mid, pkt["numeric"])

            startup_ts = None
            if mid in state and "startup_ts" in state[mid]:
                startup_ts = state[mid]["startup_ts"]
            rich_collector.record(mid, pkt["numeric"], startup_ts)


# ─── Ana döngü ───────────────────────────────────────────────────────────────
def main():
    global running

    consumer = Consumer(
        {
            "bootstrap.servers": KAFKA_CFG["bootstrap_servers"],
            "group.id": KAFKA_CFG.get("group_id", "hpr-monitor-prod"),
            "auto.offset.reset": "latest",
            "enable.auto.commit": True,
            "auto.commit.interval.ms": 5000,
            "session.timeout.ms": 10000,
            "fetch.wait.max.ms": 500,
        }
    )
    consumer.subscribe([KAFKA_CFG["topic"]])

    def stop(sig, frame):
        global running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    log.info("Pipeline baslatildi — HPR makineleri izleniyor")
    log.info(
        "%s makine konfigurasyonu yuklendi: %s",
        len(HPR_MACHINES),
        ", ".join(HPR_MACHINES),
    )

    last_state_save = time.time()
    last_status_log = time.time()

    while running:
        msg = consumer.poll(timeout=0.5)

        if msg is None:
            now_time = time.time()
            if now_time - last_status_log >= 60.0:
                active_alerts = sum(
                    1 for m in machine_data.values()
                    if m.get("severity") not in ("", "DÜŞÜK", None)
                )
                log.info(
                    "DURUM | makineler=%s | mesajlar=%s | hpr_mesajlar=%s | alertler=%s | aktif_uyarilar=%s",
                    len(HPR_MACHINES),
                    stats["total"],
                    stats["hpr_msgs"],
                    stats["alerts"],
                    active_alerts,
                )
                last_status_log = now_time
            continue

        if msg.error():
            if msg.error().code() != KafkaError._PARTITION_EOF:
                log.error("Kafka hata: %s", msg.error())
            continue

        try:
            data = json.loads(msg.value())
            stats["total"] = cast(int, stats["total"]) + 1
            process(data)

            refresh_machine_data()

            now_time = time.time()
            if now_time - last_state_save >= 30.0:
                store.save_state(state)
                last_state_save = now_time

                active_alerts = sum(
                    1 for m in machine_data.values()
                    if m.get("severity") not in ("", "DÜŞÜK", None)
                )
                log.info(
                    "DURUM | makineler=%s | mesajlar=%s | hpr_mesajlar=%s | alertler=%s | aktif_uyarilar=%s",
                    len(HPR_MACHINES),
                    stats["total"],
                    stats["hpr_msgs"],
                    stats["alerts"],
                    active_alerts,
                )
                last_status_log = now_time

        except Exception as e:
            log.debug("İşleme hatası: %s", e)

    store.save_state(state)
    collector.force_save()
    rich_collector.force_save()
    consumer.close()
    log.info("Sistem durduruldu. State + Windows kaydedildi.")
    log.info("%s", collector.summary())
    log.info("%s", rich_collector.summary())


if __name__ == "__main__":
    main()
