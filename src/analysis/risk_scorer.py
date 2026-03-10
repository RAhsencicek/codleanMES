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
import logging

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


def calculate_risk(
    machine_id:         str,
    threshold_signals:  list[ThresholdSignal],
    trend_signals:      list[TrendSignal],
    confidence:         float,
    sensor_values:      dict | None = None,
    state:              dict | None = None,   # ML için State Store verisi
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
