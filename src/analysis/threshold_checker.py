"""
Katman 2a — Threshold Checker (Eşik Kontrolü)
═══════════════════════════════════════════════
Anlık sensör değerini limits_config.yaml ile karşılaştırır.
Üç uyarı seviyesi:
  ORTA    → Değer soft limitin (%85) üzerine çıktı
  YÜKSEK  → Değer max limiti aştı
  KRİTİK  → Değer max limitin %110'unu aştı

Hem üst (HIGH) hem alt (LOW) taraf kontrol edilir.
"""

from dataclasses import dataclass
import logging

log = logging.getLogger("threshold")


@dataclass
class ThresholdSignal:
    machine_id: str
    sensor:     str
    value:      float
    limit:      float
    direction:  str      # "HIGH" | "LOW"
    severity:   str      # "ORTA" | "YÜKSEK" | "KRİTİK"
    percent:    float    # Limitin yüzde kaçında
    unit:       str
    message:    str


def check_threshold(
    machine_id: str,
    sensor: str,
    value: float,
    limits: dict,        # limits_config.yaml'dan yüklenen machine_limits
    soft_ratio: float = 0.85,
) -> ThresholdSignal | None:
    """
    Sensör değerini config limitleriyle karşılaştırır.
    Limit tanımlı değilse None döner (sessiz geçer).
    """
    machine_limits = limits.get(machine_id, {})
    sensor_limit   = machine_limits.get(sensor)

    if sensor_limit is None:
        return None  # Bu sensör için limit tanımlı değil

    max_val = sensor_limit.get("max")
    min_val = sensor_limit.get("min")
    unit    = sensor_limit.get("unit", "")

    # ─── YÜKSEK TARAF ────────────────────────────────────────────────────────
    if max_val is not None:
        pct = (value / max_val * 100) if max_val != 0 else 0

        if value > max_val * 1.10:
            return ThresholdSignal(
                machine_id=machine_id, sensor=sensor, value=value,
                limit=max_val, direction="HIGH", severity="KRİTİK",
                percent=pct, unit=unit,
                message=f"{sensor}: {value:.1f}{unit} — limit {max_val}{unit} (%{pct:.0f})"
            )
        if value > max_val:
            return ThresholdSignal(
                machine_id=machine_id, sensor=sensor, value=value,
                limit=max_val, direction="HIGH", severity="YÜKSEK",
                percent=pct, unit=unit,
                message=f"{sensor}: {value:.1f}{unit} — limit {max_val}{unit} (%{pct:.0f})"
            )
        if value > max_val * soft_ratio:
            return ThresholdSignal(
                machine_id=machine_id, sensor=sensor, value=value,
                limit=max_val, direction="HIGH", severity="ORTA",
                percent=pct, unit=unit,
                message=f"{sensor}: {value:.1f}{unit} — limite %{pct:.0f} yakın (max: {max_val})"
            )

    # ─── DÜŞÜK TARAF ─────────────────────────────────────────────────────────
    if min_val is not None and value < min_val:
        pct = (value / min_val * 100) if min_val != 0 else 0
        return ThresholdSignal(
            machine_id=machine_id, sensor=sensor, value=value,
            limit=min_val, direction="LOW", severity="YÜKSEK",
            percent=pct, unit=unit,
            message=f"{sensor}: {value:.1f}{unit} — alt limit {min_val}{unit} altında"
        )

    return None  # Normal aralıkta


def check_boolean(
    machine_id: str,
    sensor: str,
    bad_minutes: float | None,
    boolean_rules: dict,
) -> ThresholdSignal | None:
    """
    Boolean sensör kaç dakikadır kötü durumda?
    alert_after_minutes eşiğini geçince sinyal üretir.
    """
    if bad_minutes is None:
        return None  # İyi durumda

    rule = None
    # Tam eşleşme dene
    rule = boolean_rules.get(sensor)
    # Yoksa kısmi eşleşme (ör: "pressure_line_filter_1_dirty" → prefix kuralı)
    if rule is None:
        for pattern, r in boolean_rules.items():
            if sensor.startswith(pattern.rstrip("0123456789")):
                rule = r
                break

    if rule is None:
        return None

    threshold_min = rule.get("alert_after_minutes", 60)
    if bad_minutes >= threshold_min:
        severity = "YÜKSEK" if bad_minutes > threshold_min * 2 else "ORTA"
        return ThresholdSignal(
            machine_id=machine_id, sensor=sensor,
            value=bad_minutes, limit=threshold_min,
            direction="BOOL", severity=severity,
            percent=bad_minutes / threshold_min * 100, unit="dk",
            message=f"{sensor}: {bad_minutes:.0f} dakikadır sorunlu"
        )

    return None
