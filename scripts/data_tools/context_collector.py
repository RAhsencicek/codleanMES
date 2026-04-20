"""
context_collector.py — Zengin Bağlam Toplayıcı (JSON Lines Version)
═══════════════════════════════════════════════════════════════════
FAULT anlarında ±30dk zaman penceresi toplar.
RAM'de milyonlarca satır tutmak yerine Append-Only (JSONL) yazar.

Dosya: rich_context_windows.jsonl
"""

import json
import os
import threading
import logging
from datetime import datetime, timezone, timedelta
from collections import defaultdict, deque
from typing import Dict, List, Optional

OUTPUT_FILE = "rich_context_windows.jsonl"

log = logging.getLogger("context_collector")

# Zaman penceresi ayarları
PRE_FAULT_MINUTES = 30
POST_FAULT_MINUTES = 10
COLD_START_MINUTES = 60

HPR_SENSORS = [
    "oil_tank_temperature",
    "main_pressure", 
    "horizontal_press_pressure",
    "lower_ejector_pressure",
    "horitzonal_infeed_speed",
    "vertical_infeed_speed",
]

def _load_hpr_limits() -> dict:
    _default = {
        "oil_tank_temperature":      {"min": 0,    "max": 45.0},
        "main_pressure":             {"min": 0,    "max": 110.0},
        "horizontal_press_pressure": {"min": 0,    "max": 120.0},
        "lower_ejector_pressure":    {"min": 0,    "max": 110.0},
        "horitzonal_infeed_speed":   {"min": -300, "max": 300.0},
        "vertical_infeed_speed":     {"min": -300, "max": 300.0},
    }
    try:
        import yaml
        cfg_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "config", "limits_config.yaml")
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)
        hpr_limits = cfg.get("machine_limits", {}).get("HPR001", {})
        result = {}
        for sensor in HPR_SENSORS:
            sl = hpr_limits.get(sensor, {})
            base_max = sl.get("max", _default.get(sensor, {}).get("max", float("inf")))
            base_min = sl.get("min", _default.get(sensor, {}).get("min", float("-inf")))
            warn = sl.get("warn_level", None)
            effective_max = warn if warn and warn < base_max else base_max
            result[sensor] = {"min": base_min, "max": effective_max}
        return result
    except Exception:
        return _default

HPR_LIMITS = _load_hpr_limits()

# ─── Bellekte tutulan state ───────────────────────────────────────────────────
_machine_buffers: Dict[str, deque] = defaultdict(lambda: deque(maxlen=2000))
_machine_startup: Dict[str, datetime] = {}
_machine_fault_history: Dict[str, List[datetime]] = defaultdict(list)

# İstatistikler (RAM'de tutulur)
_total_context_windows = 0
_total_valid_faults = 0

_started_at: str = datetime.now(timezone.utc).isoformat()
_lock = threading.Lock()

def _load_existing():
    """Mevcut JSONL dosyasındaki basit istatistikleri okur."""
    global _total_context_windows, _total_valid_faults
    if not os.path.exists(OUTPUT_FILE):
        return
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                data = json.loads(line)
                _total_context_windows += 1
                if data.get("labels", {}).get("is_valid_fault"):
                    _total_valid_faults += 1
    except Exception:
        pass

_load_existing()

_active_faults: Dict[str, dict] = {}

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _parse_ts(ts_str: str) -> datetime:
    try:
        return datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
    except:
        return _now()

def _is_cold_start(machine_id: str, current_ts: datetime) -> bool:
    startup = _machine_startup.get(machine_id)
    if not startup: return True
    elapsed = (current_ts - startup).total_seconds() / 60
    return elapsed < COLD_START_MINUTES

def _get_operating_minutes(machine_id: str, current_ts: datetime) -> float:
    startup = _machine_startup.get(machine_id)
    if not startup: return 0.0
    return (current_ts - startup).total_seconds() / 60

def _get_recent_fault_count(machine_id: str, current_ts: datetime, hours: int = 24) -> int:
    cutoff = current_ts - timedelta(hours=hours)
    return sum(1 for f in _machine_fault_history[machine_id] if f > cutoff)

def _calculate_correlations(readings: dict) -> dict:
    correlations = {}
    pressure_sensors = ['main_pressure', 'horizontal_press_pressure', 'lower_ejector_pressure']
    pressures = {s: readings.get(s, 0) for s in pressure_sensors if s in readings}
    if len(pressures) >= 2:
        values = list(pressures.values())
        correlations['pressure_mean'] = sum(values) / len(values)
        correlations['pressure_max'] = max(values)
    speed_sensors = ['horitzonal_infeed_speed', 'vertical_infeed_speed']
    speeds = {s: abs(readings.get(s, 0)) for s in speed_sensors if s in readings}
    if speeds:
        correlations['max_speed'] = max(speeds.values())
        correlations['speed_ratio'] = speeds.get('vertical_infeed_speed', 0) / (speeds.get('horitzonal_infeed_speed', 0.001) or 0.001)
    if 'oil_tank_temperature' in readings and 'main_pressure' in readings:
        temp = readings['oil_tank_temperature']
        pressure = readings['main_pressure']
        correlations['thermal_pressure_index'] = temp * pressure / 1000
    return correlations

def _extract_pre_fault_window(machine_id: str, fault_ts: datetime) -> List[dict]:
    buffer = _machine_buffers[machine_id]
    cutoff = fault_ts - timedelta(minutes=PRE_FAULT_MINUTES)
    window = []
    for record in buffer:
        record_ts = _parse_ts(record['ts'])
        if cutoff <= record_ts < fault_ts:
            window.append(record)
    return window

def _create_fault_context(machine_id: str, fault_ts: datetime, 
                          readings: dict, fault_sensors: List[str]) -> dict:
    pre_fault_window = _extract_pre_fault_window(machine_id, fault_ts)
    pre_fault_summary = {}
    if pre_fault_window:
        for sensor in HPR_SENSORS:
            values = [r['readings'].get(sensor) for r in pre_fault_window if r['readings'].get(sensor) is not None]
            if values:
                pre_fault_summary[sensor] = {
                    'mean': sum(values) / len(values),
                    'min': min(values),
                    'max': max(values),
                    'trend': 'increasing' if values[-1] > values[0] else 'decreasing' if values[-1] < values[0] else 'stable',
                    'samples': len(values)
                }
    
    correlations = _calculate_correlations(readings)
    is_cold = _is_cold_start(machine_id, fault_ts)
    operating_minutes = _get_operating_minutes(machine_id, fault_ts)
    recent_faults = _get_recent_fault_count(machine_id, fault_ts, hours=24)
    
    context = {
        'ts': fault_ts.isoformat(),
        'machine_id': machine_id,
        'fault_sensors': fault_sensors,
        'readings': readings,
        'pre_fault_window': {
            'duration_minutes': PRE_FAULT_MINUTES,
            'samples': len(pre_fault_window),
            'summary': pre_fault_summary,
        },
        'context': {
            'is_cold_start': is_cold,
            'operating_minutes': operating_minutes,
            'recent_faults_24h': recent_faults,
            'correlations': correlations,
        },
        'labels': {
            'is_valid_fault': not is_cold,
            'fault_type': 'multi_sensor' if len(fault_sensors) > 1 else 'single_sensor',
        }
    }
    return context

def _append_to_jsonl(context: dict):
    """Context'i dosyanın sonuna tek satır halinde yazar."""
    global _total_context_windows, _total_valid_faults
    try:
        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(context) + "\n")
        
        _total_context_windows += 1
        if context.get('labels', {}).get('is_valid_fault'):
            _total_valid_faults += 1
    except Exception as e:
        log.error(f"[CONTEXT] Dosyaya yazılamadı: {e}")

def record(machine_id: str, sensor_values: dict, startup_ts: Optional[str] = None):
    if not machine_id.startswith("HPR"): return
    if not sensor_values: return
    
    current_ts = _now()
    if startup_ts and machine_id not in _machine_startup:
        try:
            _machine_startup[machine_id] = datetime.fromisoformat(startup_ts.replace('Z', '+00:00'))
        except:
            _machine_startup[machine_id] = current_ts
    elif machine_id not in _machine_startup:
        _machine_startup[machine_id] = current_ts
    
    readings = {s: float(v) for s, v in sensor_values.items() if s in HPR_SENSORS and v is not None}
    if not readings: return
    
    fault_sensors = []
    for sensor, val in readings.items():
        lim = HPR_LIMITS.get(sensor, {})
        if val > lim.get("max", float("inf")) or val < lim.get("min", float("-inf")):
            fault_sensors.append(sensor)
    
    with _lock:
        record_data = {'ts': current_ts.isoformat(), 'readings': readings}
        _machine_buffers[machine_id].append(record_data)
        
        if fault_sensors:
            if machine_id not in _active_faults:
                context = _create_fault_context(machine_id, current_ts, readings, fault_sensors)
                if not context['context']['is_cold_start']:
                    _machine_fault_history[machine_id].append(current_ts)
                    # Aktif fault tamamlandığında diske yazılmak üzere bekletiliyor
                    _active_faults[machine_id] = {
                        'fault_ts': current_ts,
                        'fault_sensors': fault_sensors,
                        'post_fault_data': [],
                        'pending_context': context
                    }
                    log.info(f"[CONTEXT] New fault context started for {machine_id}")
                else:
                    log.info(f"[CONTEXT] Cold start FAULT ignored: {machine_id}")
        
        if machine_id in _active_faults:
            fault_info = _active_faults[machine_id]
            elapsed = (current_ts - fault_info['fault_ts']).total_seconds() / 60
            
            if elapsed <= POST_FAULT_MINUTES:
                fault_info['post_fault_data'].append({
                    'ts': current_ts.isoformat(),
                    'elapsed_minutes': elapsed,
                    'readings': readings,
                })
            else:
                # Post-fault bitti, diske yaz
                context = fault_info['pending_context']
                context['post_fault_window'] = {
                    'duration_minutes': POST_FAULT_MINUTES,
                    'samples': len(fault_info['post_fault_data']),
                    'data': fault_info['post_fault_data'],
                }
                _append_to_jsonl(context)
                log.info(f"[CONTEXT] Context appended to JSONL: {machine_id} (samples={len(fault_info['post_fault_data'])})")
                del _active_faults[machine_id]

# Eski json mantığı kaldırıldığı için dummy ediliyor (Hata vermemesi adına)
def _save(): pass
def force_save(): pass

def summary() -> str:
    with _lock:
        return f"🧠 Rich Context: Total={_total_context_windows} Valid={_total_valid_faults}"

def stats() -> dict:
    with _lock:
        return {
            'global': {
                'total_windows': _total_context_windows,
                'total_valid': _total_valid_faults,
            }
        }
