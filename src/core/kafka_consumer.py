"""
Ana Pipeline — Kafka Consumer + Canlı Terminal Dashboard
══════════════════════════════════════════════════════════
Çalıştır:  python3 kafka_consumer.py
Dur:       Ctrl+C
"""

import json, time, signal, sys, yaml, logging, threading
from datetime import datetime
from collections import defaultdict
from confluent_kafka import Consumer, KafkaError

from src.core import data_validator   as validator
from src.core import state_store      as store
from src.analysis import threshold_checker as thresh
from src.analysis import trend_detector   as trend
from src.analysis import risk_scorer      as scorer
from src.alerts import alert_engine     as alerter

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")

# ─── Config yükle ────────────────────────────────────────────────────────────
with open("limits_config.yaml") as f:
    CONFIG = yaml.safe_load(f)

KAFKA_CONF = CONFIG["kafka"]
PIPELINE   = CONFIG["pipeline"]
LIMITS     = CONFIG.get("machine_limits", {})
BOOL_RULES = CONFIG.get("boolean_rules", {})
EWMA_ALPHA = CONFIG.get("ewma_alpha", {})


def get_alpha(machine_type: str, sensor: str) -> float:
    return (
        EWMA_ALPHA.get(machine_type, {}).get(sensor)
        or EWMA_ALPHA.get("default", 0.10)
    )


# ─── Global state ────────────────────────────────────────────────────────────
state          = store.load_state()
startup_state  = {}          # {machine_id: {last_execution, startup_ts}}
stats          = {           # Dashboard için istatistik
    "total_messages": 0,
    "machines": defaultdict(lambda: {
        "last_seen": None,
        "execution": "—",
        "risk_score": 0.0,
        "severity": "",
        "alert_count": 0,
        "sensors": {},       # {sensor: last_value}
    })
}
running = True


# ─── Checkpoint thread ───────────────────────────────────────────────────────
def checkpoint_loop():
    interval = PIPELINE.get("checkpoint_interval_seconds", 300)
    while running:
        time.sleep(interval)
        store.save_state(state)
        log.info("Checkpoint kaydedildi")


# ─── Terminal dashboard ───────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.table import Table
    from rich.live import Live
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.text import Text
    from rich import box
    RICH = True
    console = Console()
except ImportError:
    RICH = False
    console = None

_log_lines = []  # Son 10 log satırı

def add_log(msg: str):
    _log_lines.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    if len(_log_lines) > 12:
        _log_lines.pop(0)


def build_table() -> "Table":
    table = Table(
        title=f"🏭 Codlean MES — Arıza Tahmin  "
              f"[{datetime.now().strftime('%H:%M:%S')}]  "
              f"Mesaj: {stats['total_messages']}",
        box=box.ROUNDED, show_lines=True,
        title_style="bold cyan",
    )
    table.add_column("Makine",   style="cyan",  width=10)
    table.add_column("Durum",    style="white", width=12)
    table.add_column("Risk",     style="white", width=22)
    table.add_column("Güven",    style="white", width=7)
    table.add_column("Sensors",  style="dim",   width=40)

    severity_color = {"KRİTİK": "bold red", "YÜKSEK": "red",
                      "ORTA": "yellow", "DÜŞÜK": "blue", "": "white"}

    for mid in sorted(stats["machines"]):
        m = stats["machines"][mid]
        score   = m["risk_score"]
        sev     = m["severity"]
        color   = severity_color.get(sev, "white")
        filled  = int(score / 100 * 15)
        bar     = "█" * filled + "░" * (15 - filled)
        conf    = store.get_confidence(state, mid, next(iter(m["sensors"]), "")) if m["sensors"] else 0

        # Risk bar rengi
        bar_text = Text()
        bar_text.append(bar, style=color)
        bar_text.append(f" {score:.0f}", style=color)

        # Sensörler (ilk 3)
        sensor_str = "  ".join(
            f"{k}={v:.1f}" if isinstance(v, float) else f"{k}={v}"
            for k, v in list(m["sensors"].items())[:3]
        )

        exec_text = Text(m["execution"])
        if m["execution"] == "RUNNING":
            exec_text.stylize("green")
        elif m["execution"] in ("IDLE", "STOPPED"):
            exec_text.stylize("yellow")

        table.add_row(
            mid,
            exec_text,
            bar_text,
            f"%{conf*100:.0f}",
            sensor_str,
        )
    return table


def build_log_panel() -> "Panel":
    from rich.text import Text
    t = Text()
    for line in _log_lines:
        if "🚨" in line or "KRİTİK" in line:
            t.append(line + "\n", style="bold red")
        elif "⚠️" in line or "ORTA" in line or "YÜKSEK" in line:
            t.append(line + "\n", style="yellow")
        else:
            t.append(line + "\n", style="dim white")
    return Panel(t, title="Canlı Log", border_style="dim", box=box.SIMPLE)


# ─── Mesaj işleme ────────────────────────────────────────────────────────────

def _get_ewma_for_validator(machine_id: str, sensor: str) -> dict:
    return store.get_ewma_stats(state, machine_id, sensor)


def process(raw_data: dict):
    packets = validator.process_message(raw_data, state, startup_state)

    for pkt in packets:
        mid   = pkt["machine_id"]
        mtype = pkt["machine_type"]
        mstat = stats["machines"][mid]

        # Dashboard güncelle
        mstat["last_seen"] = pkt["timestamp"]
        if "execution" in pkt["text"]:
            mstat["execution"] = pkt["text"]["execution"]

        # ─── Sayısal sensörler ────────────────────────────────────────────
        t_signals: list = []
        r_signals: list = []

        for sensor, value in pkt["numeric"].items():
            alpha = get_alpha(mtype, sensor)
            store.update_numeric(
                state, mid, sensor, value, alpha=alpha,
                window=PIPELINE.get("state_window_size", 720),
            )
            mstat["sensors"][sensor] = value

            confidence = store.get_confidence(state, mid, sensor)

            if confidence < PIPELINE.get("min_confidence_for_alert", 0.10):
                continue

            # Threshold kontrol
            sig = thresh.check_threshold(mid, sensor, value, LIMITS,
                                          soft_ratio=PIPELINE.get("soft_limit_ratio", 0.85))
            if sig:
                t_signals.append(sig)

            # Trend kontrol (stale ve startup maskeli)
            if not pkt["is_stale"] and not pkt["is_startup"]:
                buf = store.get_buffer(state, mid, sensor)
                tsig = trend.analyze_sensor_trend(
                    mid, sensor, buf, LIMITS,
                    interval_sec=10,
                    min_samples=PIPELINE.get("min_samples_for_trend", 30),
                    r2_threshold=PIPELINE.get("trend_r2_threshold", 0.70),
                    eta_min_minutes=PIPELINE.get("trend_eta_min_minutes", 5),
                    eta_max_minutes=PIPELINE.get("trend_eta_max_minutes", 480),
                )
                if tsig:
                    r_signals.append(tsig)

        # ─── Boolean sensörler ────────────────────────────────────────────
        for sensor, value in pkt["boolean"].items():
            # success_key bul
            rule = BOOL_RULES.get(sensor)
            sk   = rule.get("success_key", True) if rule else True
            bad_minutes = store.update_boolean(state, mid, sensor, value, success_key=sk)
            bsig = thresh.check_boolean(mid, sensor, bad_minutes, BOOL_RULES)
            if bsig:
                t_signals.append(bsig)

        # ─── Risk hesapla ─────────────────────────────────────────────────
        if t_signals or r_signals:
            # Ortalama confidence al
            confs = [
                store.get_confidence(state, mid, s)
                for s in list(pkt["numeric"].keys())[:5]
            ]
            avg_conf = sum(confs) / len(confs) if confs else 0.1

            event = scorer.calculate_risk(
                mid, t_signals, r_signals, avg_conf,
                sensor_values={k: f"{v:.2f}" for k, v in pkt["numeric"].items()},
            )

            if event:
                mstat["risk_score"] = event.risk_score
                mstat["severity"]   = event.severity

                if alerter.process_alert(event, min_score=PIPELINE.get("min_confidence_for_alert", 0.10) * 100):
                    mstat["alert_count"] += 1
                    icon = "🚨" if event.severity == "KRİTİK" else "⚠️ "
                    add_log(f"{icon} {mid} {event.severity} | skor={event.risk_score:.0f} | {event.reasons[0][:60]}")
        else:
            # Risk geçti, skoru sıfırla
            mstat["risk_score"] = max(mstat["risk_score"] - 2, 0.0)
            if mstat["risk_score"] == 0:
                mstat["severity"] = ""


# ─── Ana döngü ───────────────────────────────────────────────────────────────

def main():
    global running

    kafka_cfg = {
        "bootstrap.servers": KAFKA_CONF["bootstrap_servers"],
        "group.id":          KAFKA_CONF.get("group_id", "ariza-pipeline"),
        "auto.offset.reset": "latest",
        "enable.auto.commit": False,
        "session.timeout.ms": KAFKA_CONF.get("session_timeout_ms", 10000),
        "fetch.wait.max.ms":  KAFKA_CONF.get("fetch_wait_max_ms", 500),
    }

    consumer = Consumer(kafka_cfg)
    consumer.subscribe([KAFKA_CONF["topic"]])

    # Checkpoint thread başlat
    cp_thread = threading.Thread(target=checkpoint_loop, daemon=True)
    cp_thread.start()

    def shutdown(sig, frame):
        global running
        running = False
        add_log("⛔ Sistem durduruluyor...")

    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"\n🏭 Codlean MES Arıza Tahmin Pipeline başlatıldı")
    print(f"   Broker: {KAFKA_CONF['bootstrap_servers']}")
    print(f"   Topic:  {KAFKA_CONF['topic']}")
    print(f"   Config: {sum(len(v) for v in LIMITS.values())} sensör limiti yüklendi\n")

    if RICH:
        with Live(build_table(), refresh_per_second=1, screen=False) as live:
            while running:
                msg = consumer.poll(timeout=1.0)
                if msg is None:
                    live.update(build_table())
                    continue
                if msg.error():
                    if msg.error().code() != KafkaError._PARTITION_EOF:
                        log.error("Kafka hatası: %s", msg.error())
                    continue
                try:
                    data = json.loads(msg.value())
                    stats["total_messages"] += 1
                    process(data)
                    if stats["total_messages"] % 10 == 0:
                        live.update(build_table())
                except Exception as e:
                    log.warning("Mesaj işleme hatası: %s", e)
    else:
        # rich yoksa basit çıktı
        last_print = 0
        while running:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                continue
            try:
                data = json.loads(msg.value())
                stats["total_messages"] += 1
                process(data)
                now = time.time()
                if now - last_print > 5:
                    last_print = now
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                          f"{stats['total_messages']} mesaj | "
                          f"{len(stats['machines'])} makine")
                    for mid, m in sorted(stats["machines"].items()):
                        if m["risk_score"] > 0:
                            print(f"  {mid}: {m['execution']:12s} risk={m['risk_score']:.0f} {m['severity']}")
            except Exception as e:
                log.warning("Mesaj işleme hatası: %s", e)

    store.save_state(state)
    consumer.close()
    print("\n✅ Pipeline durduruldu. State kaydedildi.")


if __name__ == "__main__":
    main()
