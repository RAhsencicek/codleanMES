"""
context_collector.py — Zengin Bağlam Toplayıcı
═══════════════════════════════════════════════════════
FAULT anlarında ±30dk zaman penceresi toplar:
  - Pre-fault: FAULT'tan önceki 30 dk (trend analizi için)
  - Fault anı: Limit aşımı anı
  - Post-fault: FAULT'tan sonraki 10 dk (stabilizasyon için)

Context özellikleri:
  - Tüm sensörlerin değerleri
  - Sensörler arası korelasyonlar
  - Operating minutes (makine çalışma süresi)
  - Cold start durumu
  - Önceki FAULT geçmişi (son 24 saat)

Dosya: rich_context_windows.json
"""

import json
import os
import threading
from datetime import datetime, timezone, timedelta
from collections import defaultdict, deque
from typing import Dict, List, Optional

OUTPUT_FILE = "rich_context_windows.json"

# Zaman penceresi ayarları
PRE_FAULT_MINUTES = 30   # FAULT'tan önce
POST_FAULT_MINUTES = 10  # FAULT'tan sonra
COLD_START_MINUTES = 60  # Cold start threshold

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
# Her makine için son 30 dk verisini halka tamponunda tut
_machine_buffers: Dict[str, deque] = defaultdict(lambda: deque(maxlen=2000))
_machine_startup: Dict[str, datetime] = {}
_machine_fault_history: Dict[str, List[datetime]] = defaultdict(list)

# Tamamlanmış context pencereleri
_context_windows: Dict[str, List[dict]] = defaultdict(list)

_started_at: str = datetime.now(timezone.utc).isoformat()
_lock = threading.Lock()


def _load_existing():
    """Başlangıçta mevcut JSON dosyasını belleğe yükle."""
    if not os.path.exists(OUTPUT_FILE):
        return
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        machines = data.get("machines", {})
        for mid, mdata in machines.items():
            windows = mdata.get("context_windows", [])
            if windows:
                _context_windows[mid].extend(windows)
        meta = data.get("meta", {})
        global _started_at
        if meta.get("started_at"):
            _started_at = meta["started_at"]
    except Exception:
        pass


_load_existing()

# Periyodik otomatik kayıt (her 5 dakikada bir)
_AUTO_SAVE_INTERVAL = 300  # saniye
_last_auto_save: float = 0.0

# Aktif FAULT takibi (post-fault verisi için)
_active_faults: Dict[str, dict] = {}  # machine_id → fault_info


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _parse_ts(ts_str: str) -> datetime:
    """ISO timestamp'i datetime'e çevir."""
    try:
        return datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
    except:
        return _now()


def _is_cold_start(machine_id: str, current_ts: datetime) -> bool:
    """Makine cold start durumunda mı?"""
    startup = _machine_startup.get(machine_id)
    if not startup:
        return True
    elapsed = (current_ts - startup).total_seconds() / 60
    return elapsed < COLD_START_MINUTES


def _get_operating_minutes(machine_id: str, current_ts: datetime) -> float:
    """Makinenin çalışma süresi (dakika)."""
    startup = _machine_startup.get(machine_id)
    if not startup:
        return 0.0
    return (current_ts - startup).total_seconds() / 60


def _get_recent_fault_count(machine_id: str, current_ts: datetime, hours: int = 24) -> int:
    """Son N saatteki FAULT sayısı."""
    cutoff = current_ts - timedelta(hours=hours)
    return sum(1 for f in _machine_fault_history[machine_id] if f > cutoff)


def _calculate_correlations(readings: dict) -> dict:
    """Sensörler arası korelasyonları hesapla."""
    correlations = {}
    sensors = list(readings.keys())
    
    # Basit korelasyon: Basınç sensörleri arası ilişki
    pressure_sensors = ['main_pressure', 'horizontal_press_pressure', 'lower_ejector_pressure']
    pressures = {s: readings.get(s, 0) for s in pressure_sensors if s in readings}
    
    if len(pressures) >= 2:
        values = list(pressures.values())
        correlations['pressure_mean'] = sum(values) / len(values)
        correlations['pressure_max'] = max(values)
        correlations['pressure_variance'] = sum((v - correlations['pressure_mean'])**2 for v in values) / len(values)
    
    # Hız sensörleri arası ilişki
    speed_sensors = ['horitzonal_infeed_speed', 'vertical_infeed_speed']
    speeds = {s: abs(readings.get(s, 0)) for s in speed_sensors if s in readings}
    if speeds:
        correlations['max_speed'] = max(speeds.values())
        correlations['speed_ratio'] = speeds.get('vertical_infeed_speed', 0) / (speeds.get('horitzonal_infeed_speed', 0.001) or 0.001)
    
    # Sıcaklık-basınç ilişkisi
    if 'oil_tank_temperature' in readings and 'main_pressure' in readings:
        temp = readings['oil_tank_temperature']
        pressure = readings['main_pressure']
        correlations['thermal_pressure_index'] = temp * pressure / 1000  # Normalleştirilmiş
    
    return correlations


def _extract_pre_fault_window(machine_id: str, fault_ts: datetime) -> List[dict]:
    """FAULT'tan önceki 30 dk verisini çıkar."""
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
    """Zengin FAULT context penceresi oluştur."""
    
    # Pre-fault verisi
    pre_fault_window = _extract_pre_fault_window(machine_id, fault_ts)
    
    # Trend analizi için pre-fault özeti
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
    
    # Korelasyonlar
    correlations = _calculate_correlations(readings)
    
    # Cold start kontrolü
    is_cold = _is_cold_start(machine_id, fault_ts)
    
    # Operating minutes
    operating_minutes = _get_operating_minutes(machine_id, fault_ts)
    
    # Son 24 saatteki FAULT sayısı
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
            'is_valid_fault': not is_cold,  # Cold start değilse gerçek FAULT
            'fault_type': 'multi_sensor' if len(fault_sensors) > 1 else 'single_sensor',
        }
    }
    
    return context


def record(machine_id: str, sensor_values: dict, startup_ts: Optional[str] = None):
    """
    Her gelen HPR mesajı için çağrılır.
    
    Args:
        machine_id: Makine ID (HPR001 vb.)
        sensor_values: Sensör değerleri
        startup_ts: Makine startup zamanı (ISO format)
    """
    import logging
    log = logging.getLogger("context_collector")
    
    if not machine_id.startswith("HPR"):
        return
    
    if not sensor_values:
        return
    
    current_ts = _now()
    
    # Startup zamanını kaydet
    if startup_ts and machine_id not in _machine_startup:
        try:
            _machine_startup[machine_id] = datetime.fromisoformat(startup_ts.replace('Z', '+00:00'))
        except:
            _machine_startup[machine_id] = current_ts
    elif machine_id not in _machine_startup:
        _machine_startup[machine_id] = current_ts
    
    # Sensörleri filtrele
    readings = {
        s: float(v) for s, v in sensor_values.items()
        if s in HPR_SENSORS and v is not None
    }
    if not readings:
        return
    
    # Limit aşımı kontrolü
    fault_sensors = []
    for sensor, val in readings.items():
        lim = HPR_LIMITS.get(sensor, {})
        if val > lim.get("max", float("inf")) or val < lim.get("min", float("-inf")):
            fault_sensors.append(sensor)
    
    with _lock:
        # Her zaman buffer'a ekle (pre-fault için)
        record_data = {
            'ts': current_ts.isoformat(),
            'readings': readings,
        }
        _machine_buffers[machine_id].append(record_data)
        
        if fault_sensors:
            # Yeni FAULT tespiti
            if machine_id not in _active_faults:
                log.info(f"[CONTEXT] FAULT detected: {machine_id} - {fault_sensors}")
                
                # Zengin context oluştur
                context = _create_fault_context(machine_id, current_ts, readings, fault_sensors)
                
                # Cold start değilse kaydet
                if not context['context']['is_cold_start']:
                    _context_windows[machine_id].append(context)
                    _machine_fault_history[machine_id].append(current_ts)
                    log.info(f"[CONTEXT] Rich context saved: {machine_id} (pre_fault_samples={context['pre_fault_window']['samples']})")
                else:
                    log.info(f"[CONTEXT] Cold start FAULT ignored: {machine_id}")
                
                # Post-fault takibi başlat
                _active_faults[machine_id] = {
                    'fault_ts': current_ts,
                    'fault_sensors': fault_sensors,
                    'post_fault_data': [],
                }
        
        # Post-fault verisi toplama
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
                # Post-fault tamamlandı, son context'i güncelle
                if _context_windows[machine_id]:
                    last_context = _context_windows[machine_id][-1]
                    if last_context['ts'] == fault_info['fault_ts'].isoformat():
                        last_context['post_fault_window'] = {
                            'duration_minutes': POST_FAULT_MINUTES,
                            'samples': len(fault_info['post_fault_data']),
                            'data': fault_info['post_fault_data'],
                        }
                        log.info(f"[CONTEXT] Post-fault completed: {machine_id} (samples={len(fault_info['post_fault_data'])})")
                
                del _active_faults[machine_id]

    # Periyodik otomatik kayıt (lock dışında zaman kontrolü, içinde kayıt)
    import time
    global _last_auto_save
    now_ts = time.monotonic()
    if now_ts - _last_auto_save >= _AUTO_SAVE_INTERVAL:
        with _lock:
            _save()
            _last_auto_save = time.monotonic()


def _save():
    """JSON dosyasına yaz."""
    data = {
        'meta': {
            'started_at': _started_at,
            'updated_at': _now_iso(),
            'version': '2.0-rich-context',
            'config': {
                'pre_fault_minutes': PRE_FAULT_MINUTES,
                'post_fault_minutes': POST_FAULT_MINUTES,
                'cold_start_minutes': COLD_START_MINUTES,
            }
        },
        'machines': {
            mid: {
                'context_windows': windows,
                'total_faults': len(windows),
                'valid_faults': sum(1 for w in windows if w['labels']['is_valid_fault']),
                'cold_start_faults': sum(1 for w in windows if not w['labels']['is_valid_fault']),
            }
            for mid, windows in _context_windows.items()
        },
        'summary': {
            'total_machines': len(_context_windows),
            'total_context_windows': sum(len(w) for w in _context_windows.values()),
            'total_valid_faults': sum(
                sum(1 for w in windows if w['labels']['is_valid_fault'])
                for windows in _context_windows.values()
            ),
        }
    }
    
    tmp = OUTPUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
        f.write("\n")
    os.replace(tmp, OUTPUT_FILE)


def force_save():
    """Sistem kapanmadan önce çağrılır."""
    with _lock:
        _save()


def summary() -> str:
    """Dashboard için özet."""
    with _lock:
        total = sum(len(w) for w in _context_windows.values())
        valid = sum(
            sum(1 for w in windows if w['labels']['is_valid_fault'])
            for windows in _context_windows.values()
        )
        return f"🧠 Rich Context: Total={total} Valid={valid}"


def stats() -> dict:
    """Detaylı istatistik."""
    with _lock:
        return {
            'machines': {
                mid: {
                    'total': len(windows),
                    'valid': sum(1 for w in windows if w['labels']['is_valid_fault']),
                    'avg_pre_fault_samples': sum(w['pre_fault_window']['samples'] for w in windows) / len(windows) if windows else 0,
                }
                for mid, windows in _context_windows.items()
            },
            'global': {
                'total_windows': sum(len(w) for w in _context_windows.values()),
                'total_valid': sum(sum(1 for w in windows if w['labels']['is_valid_fault']) for windows in _context_windows.values()),
            }
        }
