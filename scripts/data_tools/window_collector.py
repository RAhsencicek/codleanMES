"""
window_collector.py — Canlı Pipeline Window Toplayıcı
═══════════════════════════════════════════════════════
hpr_monitor.py'nin process() fonksiyonundan çağrılır.
Her gelen HPR mesajı için:
  - NORMAL: saatte 3 pencere kaydeder → {sensor: value} snapshot
  - FAULT  : her limit aşımı anını kaydeder → {sensor: value, faults: [...]}

Dosya: live_windows.json
  {
    "meta": {"started_at": ..., "updated_at": ...},
    "normal_windows": {
      "HPR001": [ {"ts": ..., "readings": {sensor: value, ...}}, ... ],
      ...
    },
    "fault_windows": {
      "HPR001": [ {"ts": ..., "readings": {...}, "faults": [sensor, ...]}, ... ],
      ...
    }
  }

train_model.py bu dosyayı violation_log.json ile birlikte okur.
"""

import json
import os
import threading
from datetime import datetime, timezone
from collections import defaultdict

OUTPUT_FILE         = "live_windows.json"
NORMAL_PER_HOUR     = 3       # Saatte makine başına max normal pencere
MAX_NORMAL_MACHINE  = 10_000  # Toplam üst sınır
MAX_FAULT_MACHINE   = 10_000  # Toplam üst sınır

HPR_SENSORS = [
    "oil_tank_temperature",
    "main_pressure",
    "horizontal_press_pressure",
    "lower_ejector_pressure",
    "horitzonal_infeed_speed",
    "vertical_infeed_speed",
]

HPR_LIMITS = {
    "oil_tank_temperature":      {"min": 0,    "max": 45.0},
    "main_pressure":             {"min": 0,    "max": 110.0},
    "horizontal_press_pressure": {"min": 0,    "max": 120.0},
    "lower_ejector_pressure":    {"min": 0,    "max": 110.0},
    "horitzonal_infeed_speed":   {"min": -300, "max": 300.0},
    "vertical_infeed_speed":     {"min": -300, "max": 300.0},
}

# ─── Bellekte tutulan state ───────────────────────────────────────────────────
_normal_windows: dict[str, list] = defaultdict(list)
_fault_windows:  dict[str, list] = defaultdict(list)
_normal_hour_counts: dict[tuple, int] = defaultdict(int)  # (machine_id, "YYYY-MM-DD-HH") → int
_started_at: str = datetime.now(timezone.utc).isoformat()
_lock = threading.Lock()

# ─── Disk'ten yükle (varsa önceki oturum) ────────────────────────────────────
def _load_existing():
    global _started_at
    if not os.path.exists(OUTPUT_FILE):
        return
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _started_at = data.get("meta", {}).get("started_at", _started_at)
        for mid, wins in data.get("normal_windows", {}).items():
            _normal_windows[mid].extend(wins)
            # Saat sayaçlarını restore et
            for w in wins:
                hkey = (mid, _hour_key(w.get("ts", "")))
                _normal_hour_counts[hkey] = _normal_hour_counts[hkey] + 1
        for mid, wins in data.get("fault_windows", {}).items():
            _fault_windows[mid].extend(wins)
    except Exception:
        pass  # Bozuk dosya → sıfırdan başla

_load_existing()


# ─── Yardımcılar ─────────────────────────────────────────────────────────────
def _hour_key(ts_str: str) -> str:
    """'2026-03-06T14:32:11+03:00' → '2026-03-06-14'"""
    try:
        return ts_str[:13].replace("T", "-")
    except Exception:
        return "unknown"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save():
    """JSON dosyasına yaz (lock içinde çağrılır)."""
    data = {
        "meta": {
            "started_at": _started_at,
            "updated_at": _now_iso(),
            "normal_windows_total": sum(len(v) for v in _normal_windows.values()),
            "fault_windows_total":  sum(len(v) for v in _fault_windows.values()),
        },
        "normal_windows": dict(_normal_windows),
        "fault_windows":  dict(_fault_windows),
    }
    tmp = OUTPUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, OUTPUT_FILE)  # Atomik yazım


# ─── Kayıt sayacı (her N mesajda bir kaydet) ─────────────────────────────────
_save_counter = 0
SAVE_EVERY    = 100   # 100 mesajda bir diske yaz


def _maybe_save():
    global _save_counter
    _save_counter += 1
    if _save_counter >= SAVE_EVERY:
        _save_counter = 0
        _save()


# ─── Ana API ─────────────────────────────────────────────────────────────────

def record(machine_id: str, sensor_values: dict):
    """
    hpr_monitor.py'nin process() fonksiyonundan çağrılır.

    Parametre:
        machine_id   : "HPR001" vb.
        sensor_values: {sensor_name: float_value, ...}
                       HPR_SENSORS dışındaki sensörler yok sayılır.
    """
    if not machine_id.startswith("HPR"):
        return
    if not sensor_values:
        return

    ts = _now_iso()

    # Sadece HPR sensörlerini filtrele
    readings = {
        s: float(v) for s, v in sensor_values.items()
        if s in HPR_SENSORS and v is not None
    }
    if not readings:
        return

    # Hangi sensörler limiti aşıyor?
    fault_sensors = []
    for sensor, val in readings.items():
        lim = HPR_LIMITS.get(sensor, {})
        if val > lim.get("max", float("inf")) or val < lim.get("min", float("-inf")):
            fault_sensors.append(sensor)

    with _lock:
        if fault_sensors:
            # ── FAULT penceresi ──────────────────────────────────────────────
            if len(_fault_windows[machine_id]) < MAX_FAULT_MACHINE:
                _fault_windows[machine_id].append({
                    "ts":       ts,
                    "readings": readings,
                    "faults":   fault_sensors,
                })
        else:
            # ── NORMAL penceresi ─────────────────────────────────────────────
            if len(_normal_windows[machine_id]) < MAX_NORMAL_MACHINE:
                hkey = (machine_id, _hour_key(ts))
                if _normal_hour_counts[hkey] < NORMAL_PER_HOUR:
                    _normal_windows[machine_id].append({
                        "ts":       ts,
                        "readings": readings,
                    })
                    _normal_hour_counts[hkey] += 1

        _maybe_save()


def force_save():
    """Sistem kapanmadan önce çağrılır (hpr_monitor.py shutdown hook)."""
    with _lock:
        _save()


def summary() -> str:
    """Dashboard/log için kısa özet string."""
    with _lock:
        n = sum(len(v) for v in _normal_windows.values())
        f = sum(len(v) for v in _fault_windows.values())
    return f"📦 Windows: N={n} F={f}"


def stats() -> dict:
    """Detaylı istatistik dict'i."""
    with _lock:
        return {
            mid: {
                "normal": len(_normal_windows.get(mid, [])),
                "fault":  len(_fault_windows.get(mid, [])),
            }
            for mid in sorted(set(list(_normal_windows.keys()) + list(_fault_windows.keys())))
        }
