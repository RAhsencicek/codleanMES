"""
pipeline/similarity_engine.py — Benzer Geçmiş Olay Bulucu
═══════════════════════════════════════════════════════════
violation_log.json ve günlük context'leri cosine similarity ile tarar,
mevcut sensör durumuna en benzer 3 geçmiş olayı döner.

context_builder.py içinde similar_past_events doldurmak için kullanılır.
Gemini'ye: "Bu durum, 2 ay önce HPR003'te yaşanan 'Filtre Tıkanması' vakasına
            %85 benzemektedir." gibi bağlam sağlar.
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime
from typing import NamedTuple

log = logging.getLogger("similarity_engine")

_BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VIOLATION_LOG = os.path.join(_BASE_DIR, "data", "violation_log.json")
_DAILY_DIR    = os.path.join(_BASE_DIR, "data", "daily")

# Karşılaştırılacak sensör anahtarları (sayısal, mevcut tüm makinelerde ortak)
_COMPARE_SENSORS = [
    "main_pressure",
    "horizontal_press_pressure",
    "lower_ejector_pressure",
    "oil_tank_temperature",
    "horitzonal_infeed_speed",
    "vertical_infeed_speed",
]


class SimilarEvent(NamedTuple):
    machine_id:   str
    timestamp:    str
    similarity:   float    # 0.0 - 1.0
    description:  str      # Gemini'ye verilecek metin
    sensor_snapshot: dict  # Olayın sensör değerleri


# ─── Vektör yardımcıları ────────────────────────────────────────────────────────
def _to_vec(sensor_dict: dict) -> list[float]:
    """Sensör dict'ini normalize edilmiş vektöre çevirir."""
    return [
        float(sensor_dict.get(s) or 0.0)
        for s in _COMPARE_SENSORS
    ]


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity: 0.0 (tamamen farklı) → 1.0 (aynı yön)."""
    dot   = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return round(dot / (mag_a * mag_b), 4)


# ─── Veri yükleme ────────────────────────────────────────────────────────────────
def _load_historical_events() -> list[dict]:
    """violation_log.json + günlük context dosyalarından tüm geçmiş olayları yükler."""
    events: list[dict] = []

    # 1. violation_log.json
    if os.path.exists(_VIOLATION_LOG):
        try:
            data = json.load(open(_VIOLATION_LOG, encoding="utf-8"))
            # Format: {"machines": {"HPR001": {"context_windows": [...]}}}
            if isinstance(data, dict) and "machines" in data:
                for mid, mdata in data["machines"].items():
                    for win in mdata.get("context_windows", []):
                        readings = win.get("current_readings", {})
                        if readings:
                            events.append({
                                "machine_id": mid,
                                "timestamp":  win.get("timestamp", ""),
                                "source":     "violation_log",
                                "sensors":    {k: v for k, v in readings.items() if isinstance(v, (int, float))},
                                "context_type": win.get("context_type", "fault"),
                            })
        except Exception as e:
            log.warning("violation_log.json yüklenemedi: %s", e)

    # 2. Günlük context dosyaları — data/daily/YYYY-MM-DD/contexts.json
    if os.path.isdir(_DAILY_DIR):
        for day_dir in sorted(os.listdir(_DAILY_DIR))[-30:]:  # Son 30 gün
            ctx_path = os.path.join(_DAILY_DIR, day_dir, "contexts.json")
            if not os.path.exists(ctx_path):
                continue
            try:
                data = json.load(open(ctx_path, encoding="utf-8"))
                machines = data.get("machines", {})
                for mid, mdata in machines.items():
                    for win in mdata.get("context_windows", []):
                        readings = win.get("current_readings", {})
                        if readings:
                            events.append({
                                "machine_id": mid,
                                "timestamp":  win.get("timestamp", ""),
                                "source":     f"daily/{day_dir}",
                                "sensors":    {k: v for k, v in readings.items() if isinstance(v, (int, float))},
                                "context_type": win.get("context_type", "window"),
                            })
            except Exception as e:
                log.debug("Context dosyası okunamadı %s: %s", ctx_path, e)

    log.info("SimilarityEngine: %d geçmiş olay yüklendi", len(events))
    return events


# ─── Singleton önbellek ─────────────────────────────────────────────────────────
_cache: list[dict] | None = None
_cache_time: float = 0.0
_CACHE_TTL = 300.0  # 5 dakika


def _get_events() -> list[dict]:
    global _cache, _cache_time
    import time
    now = time.monotonic()
    if _cache is None or (now - _cache_time) > _CACHE_TTL:
        _cache = _load_historical_events()
        _cache_time = now
    return _cache


# ─── Ana Fonksiyon ───────────────────────────────────────────────────────────────
def find_similar(
    current_sensors: dict,
    machine_id: str,
    top_k: int = 3,
    min_similarity: float = 0.75,
) -> list[str]:
    """
    Mevcut sensör durumuna en benzer geçmiş olayları bulur.

    Returns:
        Gemini'ye verilecek açıklama metinleri listesi.
        Örn: ["2 ay önce HPR003'te filtre tıkanması vakasına %87 benziyor (basınç 95 bar, sıcaklık 42°C)."]
    """
    events = _get_events()
    if not events:
        return []

    current_vec = _to_vec(current_sensors)
    if all(v == 0.0 for v in current_vec):
        return []  # Anlık sensör verisi yoksa karşılaştırma yapma

    scored: list[tuple[float, dict]] = []
    for event in events:
        event_vec = _to_vec(event["sensors"])
        sim = _cosine(current_vec, event_vec)
        if sim >= min_similarity:
            scored.append((sim, event))

    # En yüksek benzerlikten sırala
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    results = []
    for sim, event in top:
        mid  = event["machine_id"]
        ts   = event["timestamp"][:10] if event["timestamp"] else "?"
        ctx  = event["context_type"]
        pct  = int(sim * 100)

        # Sensören en belirgin değerler
        sensor_details = ", ".join(
            f"{s.replace('_',' ')}: {event['sensors'].get(s, '?'):.1f}"
            for s in _COMPARE_SENSORS[:3]
            if isinstance(event["sensors"].get(s), (int, float))
        )

        label = "arıza vakası" if "fault" in ctx or "violation" in ctx else "operasyonel kayıt"
        text = (
            f"{ts} tarihinde {mid}'deki {label}a %{pct} benziyor "
            f"({sensor_details})."
        )
        results.append(text)

    return results
