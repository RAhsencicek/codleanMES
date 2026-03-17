"""
Katman 2c — Risk Scorer (Risk Puanlama) — v2 (ML Ensemble)
═══════════════════════════════════════════════════════════
Threshold, Trend ve ML sinyallerini confidence ile ağırlıklandırıp
0-100 arası tek bir risk skoru üretir.

Ağırlıklandırma (confidence'a göre dinamik):
  confidence ≥ 0.7  → ML: 40%  Threshold: 35%  Trend: 25%
  confidence ≥ 0.3  → ML: 25%  Threshold: 45%  Trend: 30%
  confidence <  0.3 → ML: 10%  Threshold: 55%  Trend: 35%
"""

from dataclasses import dataclass, field
from src.analysis.threshold_checker import ThresholdSignal
from src.analysis.trend_detector import TrendSignal
from src.core.state_store import get_operating_minutes
import json, os, logging

log = logging.getLogger("risk")

# ─── ML Predictor (opsiyonel — model yoksa gracefully degrade) ───────────────
try:
    from pipeline.ml_predictor import predictor as _ml_predictor
    ML_AVAILABLE = _ml_predictor.is_active
    if ML_AVAILABLE:
        log.info("✅ ML Predictor aktif — ensemble modda çalışıyor.")
    else:
        log.warning("⚠️  ML Predictor yüklü değil — sadece Threshold+Trend.")
except Exception as _e:
    _ml_predictor = None
    ML_AVAILABLE  = False
    log.warning("⚠️  ML Predictor import edilemedi (%s)", _e)


@dataclass
class RiskEvent:
    machine_id:       str
    risk_score:       float          # 0-100
    severity:         str            # DÜŞÜK / ORTA / YÜKSEK / KRİTİK
    confidence:       float          # 0-1
    reasons:          list[str] = field(default_factory=list)
    eta_minutes:      float | None = None
    sensor_values:    dict = field(default_factory=dict)
    threshold_signals: list = field(default_factory=list)
    trend_signals:     list = field(default_factory=list)
    ml_score:         float = 0.0        # ML'in katkısı (0-100)
    ml_confidence:    float = 0.0        # Anomali olasılığı
    ml_explanation:   str  = ""          # ML açıklama cümlesi


# Threshold severity → baz puan
THRESHOLD_WEIGHTS = {
    "ORTA":   30,
    "YÜKSEK": 60,
    "KRİTİK": 80,
}

# Risk skoru → severity
SEVERITY_MAP = [
    (75, "KRİTİK"),
    (55, "YÜKSEK"),
    (30, "ORTA"),
    (0,  "DÜŞÜK"),
]


def _ensemble_weights(confidence: float) -> tuple[float, float, float]:
    """
    Confidence'a göre (threshold_w, trend_w, ml_w) döner.
    Toplam = 1.0
    """
    if confidence >= 0.7:
        return 0.35, 0.25, 0.40
    elif confidence >= 0.3:
        return 0.45, 0.30, 0.25
    else:
        return 0.55, 0.35, 0.10


# ─── Physics-Informed Kurallar (Faz 1.5) ────────────────────────────────────

# Causal Rules JSON yükleme
_CAUSAL_RULES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "docs", "causal_rules.json"
)
try:
    with open(_CAUSAL_RULES_PATH) as _f:
        CAUSAL_RULES = json.load(_f).get("rules", {})
    log.info("✅ Causal Rules yüklendi: %s", list(CAUSAL_RULES.keys()))
except Exception as _e:
    CAUSAL_RULES = {}
    log.warning("⚠️  Causal Rules yüklenemedi (%s): %s", _CAUSAL_RULES_PATH, _e)


def _apply_physics_rules(
    machine_id: str,
    sensor_values: dict,
    machine_limits: dict,
    state: dict | None,
) -> tuple[float, list[str]]:
    """
    Physics-Informed kuralları uygular.
    Dönüş: (ek risk puanı, nedenler listesi)

    Kural 1 — Hidrolik Zorlanma (Hydraulic Strain):
      Ana basınç limitin %80'ini aşmasına rağmen hız %20'nin altında
      kalıyorsa makine mekanik olarak sıkışmış demektir.

    Kural 2 — Soğuk Makine Toleransı (Cold Startup Mask):
      Makine 60 dakikadan kısa süredir çalışıyorsa, fiziksel kural
      çıktıları %50 dampen edilir (Isınma dönemi toleransı).
    """
    bonus = 0.0
    reasons = []

    if not sensor_values or not machine_limits:
        return bonus, reasons

    # ─── Kural 1: Hidrolik Zorlanma ─────────────────────────────────────────
    pressure_val = sensor_values.get("main_pressure")
    h_speed_val  = sensor_values.get("horitzonal_infeed_speed")
    v_speed_val  = sensor_values.get("vertical_infeed_speed")

    p_limit = machine_limits.get("main_pressure", {}).get("max")
    h_limit = machine_limits.get("horitzonal_infeed_speed", {}).get("max")
    v_limit = machine_limits.get("vertical_infeed_speed", {}).get("max")

    if pressure_val is not None and p_limit and p_limit > 0:
        pressure_ratio = pressure_val / p_limit

        # Hız değerlerini yüzdeye çevir (mutlak değer, çünkü hız eksi olabilir)
        h_speed_ratio = abs(h_speed_val) / abs(h_limit) if (h_speed_val is not None and h_limit and h_limit != 0) else 1.0
        v_speed_ratio = abs(v_speed_val) / abs(v_limit) if (v_speed_val is not None and v_limit and v_limit != 0) else 1.0

        if pressure_ratio > 0.80 and h_speed_ratio < 0.20 and v_speed_ratio < 0.20:
            rule_info = CAUSAL_RULES.get("hydraulic_strain", {})
            strain_bonus = rule_info.get("risk_multiplier", 30.0)
            explanation = rule_info.get(
                "explanation_tr",
                "Hidrolik zorlanma tespit edildi (basınç yüksek, hız yok)."
            )
            action = rule_info.get("action_tr", "")
            bonus += strain_bonus
            reasons.append(f"🔧 {explanation}")
            if action:
                reasons.append(f"🛠️  Öneri: {action}")
            log.warning(
                "[PHYSICS] %s: Hidrolik Zorlanma! Basınç oranı=%.1f%%, "
                "Yatay hız=%.1f%%, Dikey hız=%.1f%% → +%.0f puan",
                machine_id, pressure_ratio * 100, h_speed_ratio * 100,
                v_speed_ratio * 100, strain_bonus
            )

    # ─── Kural 2: Soğuk Makine Toleransı ──────────────────────────────────
    if state is not None:
        op_minutes = get_operating_minutes(state, machine_id)
        if op_minutes < 60 and bonus > 0:
            rule_info = CAUSAL_RULES.get("cold_startup_mask", {})
            dampen = rule_info.get("risk_multiplier", 0.5)
            old_bonus = bonus
            bonus = bonus * dampen
            reasons.append(
                f"❄️ Makine henüz {op_minutes:.0f} dakikadır çalışıyor "
                f"(ısınma toleransı: {dampen:.0%} dampen)"
            )
            log.info(
                "[PHYSICS] %s: Soğuk makine toleransı — %.0f dk. "
                "Bonus %.0f → %.0f (%.0f%% dampen)",
                machine_id, op_minutes, old_bonus, bonus, dampen * 100
            )

    return bonus, reasons


def calculate_risk(
    machine_id:         str,
    threshold_signals:  list[ThresholdSignal],
    trend_signals:      list[TrendSignal],
    confidence:         float,
    sensor_values:      dict | None = None,
    state:              dict | None = None,
    machine_limits:     dict | None = None,   # Faz 1.5: Physics kuralları için
) -> RiskEvent | None:
    """
    Threshold + Trend + ML sinyallerini birleştirir.
    Hiç sinyal yoksa ve ML skoru düşükse None döner.
    """
    # ─── Threshold skoru ─────────────────────────────────────────────────────
    t_score = 0.0
    reasons = []
    min_eta = None

    for sig in threshold_signals:
        base     = THRESHOLD_WEIGHTS.get(sig.severity, 30)
        t_score += base              # topla: iki aşım tek aşımdan ağırdır
        reasons.append(sig.message)
    t_score = min(t_score, 100.0)   # 100 üstüne çıkmasın

    # ─── Trend skoru ─────────────────────────────────────────────────────────
    tr_score = 0.0
    for sig in trend_signals:
        urgency  = max(0.0, min(1.0, 1 - sig.eta_minutes / 480))
        tr_score += 40 * urgency * sig.r_squared
        reasons.append(sig.message)
        if min_eta is None or sig.eta_minutes < min_eta:
            min_eta = sig.eta_minutes

    # ─── ML skoru ────────────────────────────────────────────────────────────
    ml_result    = None
    ml_score_raw = 0.0
    ml_conf      = 0.0
    ml_expl      = ""

    if ML_AVAILABLE and state is not None:
        try:
            ml_result    = _ml_predictor.predict_risk(machine_id, state)
            ml_score_raw = ml_result.score
            ml_conf      = ml_result.confidence
            ml_expl      = ml_result.explanation
            if ml_conf >= 0.4:
                reasons.append(ml_expl)
        except Exception as e:
            log.debug("ML predict hatası: %s", e)

    # ─── Hiç sinyal yoksa None döndür ────────────────────────────────────────
    if not threshold_signals and not trend_signals and ml_score_raw < 20:
        return None

    # ─── Ensemble ─────────────────────────────────────────────────────────────
    # Threshold deterministik bir kontrol, dampen*EDILMEZ*.
    # Trend ve ML tahmine dayalı, confidence ile ağırlıklandırılır.
    t_w, tr_w, ml_w = _ensemble_weights(confidence)

    # Trend dampening: az veri varsa trende güvenme
    tr_damp  = tr_score * max(confidence, 0.20)
    # ML dampening: az veri varsa ML'e daha az ağırlık
    ml_damp  = ml_score_raw * max(confidence, 0.10)

    score = (t_w * t_score) + (tr_w * tr_damp) + (ml_w * ml_damp)

    # ─── Physics-Informed bonus (Faz 1.5) ───────────────────────────────────
    physics_bonus, physics_reasons = _apply_physics_rules(
        machine_id, sensor_values or {}, machine_limits or {}, state
    )
    score += physics_bonus
    reasons.extend(physics_reasons)

    score = min(round(score, 1), 100.0)

    # ─── Severity ────────────────────────────────────────────────────────────
    severity = "DÜŞÜK"
    for threshold, label in SEVERITY_MAP:
        if score >= threshold:
            severity = label
            break

    return RiskEvent(
        machine_id=machine_id,
        risk_score=score,
        severity=severity,
        confidence=confidence,
        reasons=reasons,
        eta_minutes=min_eta,
        sensor_values=sensor_values or {},
        threshold_signals=threshold_signals,
        trend_signals=trend_signals,
        ml_score=ml_score_raw,
        ml_confidence=ml_conf,
        ml_explanation=ml_expl,
    )
