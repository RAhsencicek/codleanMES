"""
Katman 2b — Trend Detector (Eğilim Tespiti)
════════════════════════════════════════════
Son 30 ölçüme doğrusal regresyon uygular.
Güçlü pozitif eğim + yeterli R² varsa sinyal üretir.
ETA: Limite kaç dakika kaldığını hesaplar.

Startup phase'de çalışmaz (ısınma dönemi maskelenir).
"""

from dataclasses import dataclass
from collections import deque
import logging

log = logging.getLogger("trend")

# scipy yoksa numpy ile fallback
try:
    from scipy.stats import linregress as _linregress
    def _regress(x, y):
        res = _linregress(x, y)
        return res.slope, res.rvalue ** 2
except ImportError:
    import math
    def _regress(x, y):
        n = len(x)
        if n < 2:
            return 0.0, 0.0
        xm = sum(x) / n
        ym = sum(y) / n
        num   = sum((xi - xm) * (yi - ym) for xi, yi in zip(x, y))
        denom = sum((xi - xm) ** 2 for xi in x)
        if denom == 0:
            return 0.0, 0.0
        slope = num / denom
        sst   = sum((yi - ym) ** 2 for yi in y)
        if sst == 0:
            return slope, 1.0
        sse   = sum((yi - (slope * xi + (ym - slope * xm))) ** 2
                    for xi, yi in zip(x, y))
        r2    = 1 - sse / sst
        return slope, max(r2, 0.0)


@dataclass
class TrendSignal:
    machine_id:    str
    sensor:        str
    slope_per_step: float    # Adım başına değişim (raw)
    slope_per_hour: float    # Saat başına değişim (ölçüm birimiyle)
    eta_minutes:   float     # Limite kaç dakika kaldığı
    r_squared:     float     # Trendin güvenilirliği (0-1)
    current_value: float
    limit:         float
    direction:     str       # "HIGH" rising, "LOW" falling
    unit:          str
    message:       str


def detect_trend(
    machine_id: str,
    sensor: str,
    buffer: list[float],
    limit_val: float,
    direction: str = "HIGH",   # "HIGH": limitin üstüne çıkacak mı?
    unit: str = "",
    interval_sec: int = 10,
    min_samples: int = 30,
    r2_threshold: float = 0.70,
    eta_min_minutes: float = 5.0,
    eta_max_minutes: float = 480.0,
    is_startup: bool = False,
) -> TrendSignal | None:
    """
    Ring buffer üzerinde doğrusal regresyon.
    """
    if is_startup:
        return None  # Startup phase → maskelendi

    if len(buffer) < min_samples:
        return None  # Yeterli veri yok

    values = buffer[-min_samples:]
    times  = list(range(len(values)))

    slope, r2 = _regress(times, values)

    if r2 < r2_threshold:
        return None  # Trend çok dağınık

    current = values[-1]

    if direction == "HIGH":
        if slope <= 0.001:
            return None  # Artmıyor veya azalıyor
        remaining = limit_val - current
        if remaining <= 0:
            return None  # Zaten aştı — threshold yakalar
    else:  # LOW
        if slope >= -0.001:
            return None  # Azalmıyor
        remaining = current - limit_val
        if remaining <= 0:
            return None  # Zaten aştı

    eta_steps   = abs(remaining / slope)
    eta_minutes = eta_steps * interval_sec / 60

    if eta_minutes < eta_min_minutes or eta_minutes > eta_max_minutes:
        return None  # Çok yakın (threshold zaten yakaladı) veya çok uzak

    slope_per_hour = slope * (3600 / interval_sec)

    if direction == "HIGH":
        msg = (f"{sensor}: +{slope_per_hour:.2f}{unit}/saat trend "
               f"→ {eta_minutes:.0f} dk içinde limit {limit_val}{unit} aşılır "
               f"(R²={r2:.2f})")
    else:
        msg = (f"{sensor}: -{abs(slope_per_hour):.2f}{unit}/saat düşüş "
               f"→ {eta_minutes:.0f} dk içinde alt limit {limit_val}{unit} altına iner "
               f"(R²={r2:.2f})")

    return TrendSignal(
        machine_id=machine_id, sensor=sensor,
        slope_per_step=slope, slope_per_hour=slope_per_hour,
        eta_minutes=eta_minutes, r_squared=r2,
        current_value=current, limit=limit_val,
        direction=direction, unit=unit,
        message=msg,
    )


def analyze_sensor_trend(
    machine_id: str,
    sensor: str,
    buffer: list[float],
    limits: dict,
    unit: str = "",
    interval_sec: int = 10,
    is_startup: bool = False,
    **kwargs,
) -> TrendSignal | None:
    """
    limits dict'ten makine/sensör için max limiti alır, trend hesaplar.
    """
    sensor_limit = limits.get(machine_id, {}).get(sensor)
    if not sensor_limit:
        # Limitsiz makineler (IND, RBT, CNC) için EWMA ± 2σ kullan
        # Bu aşamada None döner, ileride istatistiksel eşik eklenebilir
        return None

    max_v = sensor_limit.get("max")
    min_v = sensor_limit.get("min")
    u     = sensor_limit.get("unit", unit)

    result = None
    if max_v is not None and len(buffer) > 0 and buffer[-1] < max_v:
        result = detect_trend(
            machine_id, sensor, buffer,
            limit_val=max_v, direction="HIGH", unit=u,
            interval_sec=interval_sec, is_startup=is_startup, **kwargs
        )

    if result is None and min_v is not None and len(buffer) > 0 and buffer[-1] > min_v:
        result = detect_trend(
            machine_id, sensor, buffer,
            limit_val=min_v, direction="LOW", unit=u,
            interval_sec=interval_sec, is_startup=is_startup, **kwargs
        )

    return result
