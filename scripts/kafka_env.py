"""
kafka_env.py — Ortak Kafka Ortam Değişkeni Yardımcısı
═══════════════════════════════════════════════════════
Tüm utility scriptler bu modülden Kafka bağlantı bilgilerini alır.
Böylece IP değişikliği tek yerden yapılır, tüm scriptler otomatik alır.

Öncelik sırası:
  1. Ortam değişkeni (KAFKA_BOOTSTRAP_SERVERS vb.)
  2. .env dosyası (proje kökünde varsa)
  3. Varsayılan değer (fabrika LAN adresi)

Kullanım:
    from scripts.kafka_env import BOOTSTRAP, TOPIC, make_config

    consumer = Consumer(make_config("benim-group-id"))
"""

from __future__ import annotations

import os
import sys


# ─── .env dosyasını yükle (varsa) ────────────────────────────────────────────
# python-dotenv kurulu değilse sessizce atla — env var'lar yeterli.
def _load_dotenv() -> None:
    """Proje kökündeki .env dosyasını ortam değişkenlerine yükler."""
    try:
        from dotenv import load_dotenv

        # Bu modül scripts/ altında, proje kökü bir üst dizin
        _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _env_path = os.path.join(_root, ".env")
        if os.path.exists(_env_path):
            load_dotenv(_env_path, override=False)  # Mevcut env var'ları ezmez
    except ImportError:
        pass  # python-dotenv kurulu değil — sadece env var'lara bak


_load_dotenv()

# ─── Değerleri oku ───────────────────────────────────────────────────────────
# Varsayılanlar: Fabrikadaki gerçek adresler (env var yoksa kullanılır)
BOOTSTRAP: str = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "10.71.120.10:7001")
TOPIC: str = os.environ.get("KAFKA_TOPIC", "mqtt-topic-v2")
GROUP_ID: str = os.environ.get("KAFKA_GROUP_ID", "ariza-tahmin-pipeline")


# ─── Config üretici ──────────────────────────────────────────────────────────


def make_config(
    group_id: str | None = None,
    *,
    auto_offset_reset: str = "latest",
    enable_auto_commit: bool = False,
    session_timeout_ms: int = 10_000,
    fetch_wait_max_ms: int = 500,
    **extra,
) -> dict:
    """
    confluent-kafka Consumer için hazır config dict döner.

    Parametreler:
        group_id           : Consumer group ID. None ise KAFKA_GROUP_ID env var kullanılır.
        auto_offset_reset  : "latest" (canlı) veya "earliest" (geçmiş veri çekme)
        enable_auto_commit : Offset otomatik commit edilsin mi?
        session_timeout_ms : Broker'a bağlantı zaman aşımı (ms)
        fetch_wait_max_ms  : Mesaj beklemede maksimum bekleme (ms)
        **extra            : confluent-kafka'nın desteklediği ek parametreler

    Kullanım:
        # Canlı izleme (latest, auto commit kapalı)
        cfg = make_config("hpr-monitor-prod")

        # Geçmiş veri çekme (earliest)
        cfg = make_config("gecmis-cek", auto_offset_reset="earliest",
                          fetch_min_bytes=1_000_000)
    """
    cfg = {
        "bootstrap.servers": BOOTSTRAP,
        "group.id": group_id or GROUP_ID,
        "auto.offset.reset": auto_offset_reset,
        "enable.auto.commit": enable_auto_commit,
        "session.timeout.ms": session_timeout_ms,
        "fetch.wait.max.ms": fetch_wait_max_ms,
    }
    cfg.update(extra)
    return cfg


def print_connection_info() -> None:
    """Script başında bağlantı bilgisini terminale basar."""
    source = "env var" if os.environ.get("KAFKA_BOOTSTRAP_SERVERS") else "varsayılan"
    print(f"  Kafka Broker : {BOOTSTRAP}  [{source}]")
    print(f"  Topic        : {TOPIC}")
    print()
