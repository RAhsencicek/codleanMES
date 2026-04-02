"""
Katman 0 — Veri Doğrulama Modülü
══════════════════════════════════
Her Kafka mesajını filtreler. Temiz, tip-güvenli veri paketi üretir.

Kontroller:
  1. Schema doğrulama  — zorunlu alanlar var mı?
  2. Sensör çekimi     — hem samples hem events taranır
  3. safe_numeric()    — virgül→nokta, UNAVAILABLE→None, float dönüşüm
  4. Stale kontrolü    — mesaj 5 dakikadan eski mi?
  5. Spike filtresi    — 5σ aşımı → geçici olarak atla
  6. Startup mask      — IDLE/STOPPED→RUNNING geçişinde 60 dk maskele
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

log = logging.getLogger("validator")

# ─── Sabitler ────────────────────────────────────────────────────────────────
STALE_SECONDS = 300  # 5 dakika
STARTUP_MINUTES = 60
SPIKE_SIGMA = 5.0
MIN_SAMPLES_FOR_SPIKE = 15

# ─── Yardımcı: Güvenli float dönüşümü ───────────────────────────────────────


# Makinelerden gelen bilinen metin/durum değerleri — float parse hatası değil, beklenen metin
_KNOWN_TEXT_VALUES = frozenset(
    {
        # Çalışma durumu
        "RUNNING",
        "STOPPED",
        "IDLE",
        "PAUSED",
        "INTERRUPTED",
        "READY",
        "HOLD",
        "RESET",
        "START",
        "STOP",
        "ACTIVE",
        "INACTIVE",
        # Mod
        "AUTO",
        "MANUAL",
        "MANUEL",
        "SEMIAUTO",
        "MAINTENANCE",
        "SPINDLE",
        "AUTOMATIC",
        # Boolean string
        "TRUE",
        "FALSE",
        # Sistem
        "AVAILABLE",
        "UNAVAILABLE",
        "NORMAL",
        "FAULT",
        "WARNING",
        # Boş / null
        "",
    }
)


def _looks_numeric(s: str) -> bool:
    """
    Değer sayısal olmaya 'çalışıyor' ama parse edilemedi mi?
    Örnek: "37.5 bar", "120bar", "-5.2°C" → True (gerçek uyarı)
    Örnek: "RUNNING", "G01 X149.648", "O7004(...)" → False (beklenen metin)
    """
    # En az bir rakam içerip içermediğine bak
    return any(c.isdigit() for c in s)


def safe_numeric(value) -> float | None:
    """
    String result alanını güvenle float'a çevirir.
    - UNAVAILABLE / boş string / None → None
    - Türkçe locale virgül → nokta  ("37,022568" → 37.022568)

    Log seviyeleri:
    - WARNING: Değer rakam içeriyor ama float'a çevrilemiyor
                → Muhtemelen bir sensör format değiştirdi ("37.5 bar" gibi)
    - DEBUG  : Bilinen metin durumu veya G-kodu gibi açıkça metin alan
                → Beklenen davranış, gürültü yaratmayalım
    """
    if value is None:
        return None
    s = str(value).strip()
    if s.upper() in ("UNAVAILABLE", ""):
        return None
    try:
        return float(s.replace(",", "."))
    except (ValueError, TypeError):
        # Bilinen metin değerleri → sessiz DEBUG
        if s.upper() in _KNOWN_TEXT_VALUES:
            log.debug("METIN_ALAN | '%s' → metin olarak işlenecek", s)
            return None
        # Rakam içeriyorsa → gerçek bir parse anomalisi olabilir, WARNING
        if _looks_numeric(s):
            log.warning(
                "PARSE_ERROR | Ham değer: '%s' | Rakam içeriyor ama float'a çevrilemiyor "
                "→ Sensör formatı değişmiş olabilir",
                s,
            )
        else:
            # G-kodu, parça adı, program adı gibi açıkça metin → DEBUG
            log.debug("METIN_ALAN | '%s' → metin olarak işlenecek", s)
        return None


def safe_bool(value) -> bool | None:
    """Boolean string değerini Python bool'a çevirir."""
    if value is None:
        return None
    s = str(value).strip().upper()
    if s == "TRUE":
        return True
    if s in ("FALSE", "0"):
        return False
    if s in ("UNAVAILABLE", ""):
        return None
    # Bazı makinelerde "0"/"1" olarak geliyor
    try:
        return bool(int(s))
    except (ValueError, TypeError):
        return None


# ─── Pydantic Schema doğrulama ───────────────────────────────────────────────
from pydantic import BaseModel, Field, ValidationError
from typing import Optional, List, Dict, Any

class KafkaHeader(BaseModel):
    sender: str
    creationTime: str
    uuid: Optional[str] = None

class KafkaMessage(BaseModel):
    header: KafkaHeader
    streams: List[Dict[str, Any]] = Field(min_length=1)

def validate_schema(data: dict) -> bool:
    """Pydantic kullanarak Kafka mesajının donanımsal zırh kontrolünü yapar."""
    try:
        KafkaMessage(**data)
        return True
    except ValidationError as e:
        log.warning("SCHEMA_ERROR: Pydantic validasyonu reddetti: %s", str(e).replace('\n', ' '))
        return False


# ─── Stale veri kontrolü ─────────────────────────────────────────────────────


def is_stale(creation_time_str: str, machine_id: str) -> bool:
    """Mesaj 5 dakikadan eskiyse True döner."""
    try:
        event_time = datetime.fromisoformat(creation_time_str.replace("Z", "+00:00"))
        lag = (datetime.now(timezone.utc) - event_time).total_seconds()
        if lag > STALE_SECONDS:
            log.warning("STALE_DATA | %s | lag=%.0fs", machine_id, lag)
            return True
        return False
    except Exception:
        log.warning("TIMESTAMP_PARSE_ERROR | %s | '%s'", machine_id, creation_time_str)
        return False


# ─── Spike filtresi ──────────────────────────────────────────────────────────


def is_spike(value: float, sensor_stats: dict) -> bool:
    """
    Değer EWMA ortalamasından 5σ uzaktaysa spike sayar.
    İlk MIN_SAMPLES_FOR_SPIKE ölçümde kontrolü atlar.
    """
    count = sensor_stats.get("count", 0)
    if count < MIN_SAMPLES_FOR_SPIKE:
        return False
    mean = sensor_stats.get("ewma_mean")
    std = sensor_stats.get("ewma_std")
    if mean is None or std is None or std < 0.001:
        return False
    z = abs(value - mean) / std
    if z > SPIKE_SIGMA:
        log.warning(
            "SPIKE | z=%.1f | value=%.3f mean=%.3f std=%.3f", z, value, mean, std
        )
        return True
    return False


# ─── Sensör çekimi (samples + events birlikte) ───────────────────────────────


def extract_sensors(comp: dict) -> dict[str, str]:
    """
    componentStream içindeki samples ve events'i tek dict'te birleştirir.
    Alarm alanları ve asset alanları atlanır.
    Dönen: {dataItemId: result_string}
    """
    sensors: dict[str, str] = {}
    skip_keywords = ("alarm", "_assetchanged", "_assetcount", "_assetremoved")

    for entry in comp.get("samples", []) + comp.get("events", []):
        did = entry.get("dataItemId", "")
        if not did:
            continue
        # Alarm ve asset alanlarını atla
        did_lower = did.lower()
        if any(kw in did_lower for kw in skip_keywords):
            continue
        sensors[did] = entry.get("result", "")

    return sensors


# ─── Startup mask ────────────────────────────────────────────────────────────


def check_startup(machine_id: str, execution: str | None, startup_state: dict) -> bool:
    """
    IDLE/STOPPED → RUNNING geçişinde startup_ts kaydeder.
    Son 60 dakika içindeyse startup_phase=True döner (trend hesabı maskelenir).
    """
    if execution is None:
        return False

    prev = startup_state.get(machine_id, {}).get("last_execution", "")
    curr = execution.upper()

    if curr == "RUNNING" and prev.upper() in ("IDLE", "STOPPED", "INTERRUPTED", ""):
        startup_state.setdefault(machine_id, {})["startup_ts"] = (
            datetime.utcnow().isoformat()
        )
        log.info("STARTUP_DETECTED | %s", machine_id)

    startup_state.setdefault(machine_id, {})["last_execution"] = curr

    ts_str = startup_state.get(machine_id, {}).get("startup_ts")
    if ts_str:
        try:
            since = (
                datetime.utcnow() - datetime.fromisoformat(ts_str)
            ).total_seconds() / 60
            if since < STARTUP_MINUTES:
                return True  # Hâlâ ısınma döneminde
        except Exception:
            pass
    return False


# ─── Ana işlev: Mesajı işle ──────────────────────────────────────────────────


def process_message(
    raw_data: dict,
    ewma_state: dict,  # state_store formatı: {machine_id: {ewma_mean: {sensor: float}, ewma_var: {sensor: float}, sample_count: {sensor: int}}}
    startup_state: dict,  # {machine_id: {last_execution, startup_ts}}
) -> list[dict]:
    """
    Ham Kafka mesajını işler. Her makine için temiz veri paketi döner.

    Dönüş: [
        {
            "machine_id": "HPR001",
            "machine_type": "HPR",
            "timestamp": "2026-03-05T...",
            "is_stale": False,
            "is_startup": False,
            "numeric": {"oil_tank_temperature": 38.4, ...},
            "boolean": {"pressure_line_filter_1_dirty": False, ...},
            "text":    {"execution": "RUNNING", "mode": "AUTO", ...},
        },
        ...
    ]
    """
    if not validate_schema(raw_data):
        return []

    header = raw_data["header"]
    timestamp = header.get("creationTime", "")
    results = []

    for stream in raw_data.get("streams", []):
        stream_name = stream.get("name", "")

        # Makine tipini belirle
        machine_type = "UNK"
        for prefix in ("HPR", "IND", "TST", "RBT", "CNC"):
            if prefix in stream_name.upper():
                machine_type = prefix
                break

        for comp in stream.get("componentStream", []):
            machine_id = comp.get("componentId", "")
            if not machine_id:
                continue

            sensors_raw = extract_sensors(comp)
            if not sensors_raw:
                continue

            stale = is_stale(timestamp, machine_id)
            execution = sensors_raw.get("execution")
            startup = check_startup(machine_id, execution, startup_state)

            # Sensörleri tipine göre ayır
            numeric: dict[str, float] = {}
            boolean: dict[str, bool] = {}
            text: dict[str, str] = {}

            for did, raw_val in sensors_raw.items():
                # Önce sayısal dene
                num = safe_numeric(raw_val)
                if num is not None:
                    # Spike kontrolü — state_store yapısından doğru eriş:
                    # ewma_state[machine_id]["ewma_mean"][sensor] ve ewma_var/sample_count
                    ms = ewma_state.get(machine_id, {})
                    count = ms.get("sample_count", {}).get(did, 0)
                    mean  = ms.get("ewma_mean",   {}).get(did)
                    var   = ms.get("ewma_var",    {}).get(did, 0.0)
                    spike_stats = {
                        "count":     count,
                        "ewma_mean": mean,
                        "ewma_std":  var ** 0.5 if var and var > 0 else 0.0,
                    }
                    if is_spike(num, spike_stats):
                        log.warning("SPIKE_SKIP | %s.%s = %.3f", machine_id, did, num)
                        continue
                    numeric[did] = num
                    continue

                # Boolean dene
                bval = safe_bool(raw_val)
                if bval is not None:
                    boolean[did] = bval
                    continue

                # Metin
                s = str(raw_val).strip()
                if s and s.upper() not in ("UNAVAILABLE", ""):
                    text[did] = s

            results.append(
                {
                    "machine_id": machine_id,
                    "machine_type": machine_type,
                    "timestamp": timestamp,
                    "is_stale": stale,
                    "is_startup": startup,
                    "numeric": numeric,
                    "boolean": boolean,
                    "text": text,
                }
            )

    return results
