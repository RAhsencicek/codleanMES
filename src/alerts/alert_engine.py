"""
Katman 3 — Alert Engine (HYBRID SYSTEM)
════════════════════════════════════════
İKİ MODDA ÇALIŞIR:

1. HYBRID MODE (YENİ):
   → detect_faults_direct() → Rule-based fault (KESİN)
   → predict_pre_fault_direct() → ML pre-fault (OLASI)
   → generate_hybrid_alert() → İkisini birleştirir

2. RISK EVENT MODE (ESKİ):
   → process_alert() → risk_scorer'dan gelen alert basar

Alert Prioritization:
  FAULT > PRE_FAULT_WARNING > NORMAL (alert yok)
"""

from datetime import datetime
from src.analysis.risk_scorer import RiskEvent
import logging
import json

log = logging.getLogger("alert")

# Throttle state: {machine_id: last_alert_datetime}
_last_alert: dict = {}

THROTTLE_NORMAL_MIN   = 30
THROTTLE_CRITICAL_MIN = 15

# ─── Severity renk & sembol haritası ─────────────────────────────────────────
SEVERITY_STYLE = {
    "DÜŞÜK":   ("blue",   "ℹ️ "),
    "ORTA":    ("yellow", "⚠️ "),
    "YÜKSEK":  ("red",    "🔴"),
    "KRİTİK":  ("bold red", "🚨"),
}

# ─── Alert Type Maps ─────────────────────────────────────────────────────────
ALERT_TYPE_MAP = {
    "FAULT":              ("bold red", "🔴"),
    "PRE_FAULT_WARNING":  ("yellow",   "🟡"),
    "SOFT_LIMIT_WARNING": ("blue",     "⚠️ "),
    "NORMAL":             ("green",    "✅"),
}


def should_alert(machine_id: str, severity: str) -> bool:
    """Throttle kontrolü. Son alertten yeterince süre geçti mi?"""
    now = datetime.utcnow()
    last = _last_alert.get(machine_id)
    if last is None:
        return True
    elapsed = (now - last).total_seconds() / 60
    limit = THROTTLE_CRITICAL_MIN if severity == "KRİTİK" else THROTTLE_NORMAL_MIN
    return elapsed >= limit


def _format_bar(score: float, width: int = 20) -> str:
    """0-100 arası skoru ASCII bar olarak gösterir."""
    filled = int(score / 100 * width)
    return "█" * filled + "░" * (width - filled)


# ============================================================================
# HYBRID ALERT ENGINE — YENİ FONKSİYONLAR
# ============================================================================


def detect_faults_direct(
    machine_id: str,
    sensor_values: dict,
    limits_config: dict,
    soft_limit_ratio: float = 0.85,  # %85 soft limit threshold
) -> list[dict]:
    """
    RULE-BASED FAULT DETECTION (KESİN)
    + SOFT LIMIT WARNING (YAKLAŞIYOR)
    
    Parametreler:
        machine_id: "HPR001"
        sensor_values: {"main_pressure": 126.5, "oil_temperature": 45.2, ...}
        limits_config: limits_config.yaml'dan yüklenen machine_limits
        soft_limit_ratio: Soft limit threshold (default: 0.85 = %85)
    
    Dönüş:
        faults: [
            {
                'sensor': 'main_pressure',
                'value': 126.5,
                'limit': 120,
                'direction': 'HIGH',
                'over_ratio': 0.054,  # %5.4 aşım
                'severity': 'YÜKSEK'
            },
            ...
        ]
    """
    faults = []
    machine_limits = limits_config.get(machine_id, {})
    
    for sensor, value in sensor_values.items():
        if value is None:
            continue
            
        sensor_limit = machine_limits.get(sensor, {})
        max_val = sensor_limit.get("max")
        min_val = sensor_limit.get("min")
        unit = sensor_limit.get("unit", "")
        
        # ─── HIGH TARAF KONTROLÜ ──────────────────────────────────────
        if max_val is not None:
            ratio = value / max_val if max_val != 0 else 0
            
            # KRİTİK: %110+ aşım
            if value > max_val * 1.10:
                over_ratio = (value - max_val) / max_val
                severity = "KRİTİK"
                faults.append({
                    'sensor': sensor,
                    'value': value,
                    'limit': max_val,
                    'direction': 'HIGH',
                    'over_ratio': over_ratio,
                    'severity': severity,
                    'message': f"{sensor}: {value:.1f}{unit} (max: {max_val}{unit}) → %{over_ratio*100:.1f} aşım"
                })
            
            # YÜKSEK: %100-110 aşım
            elif value > max_val:
                over_ratio = (value - max_val) / max_val
                severity = "YÜKSEK"
                faults.append({
                    'sensor': sensor,
                    'value': value,
                    'limit': max_val,
                    'direction': 'HIGH',
                    'over_ratio': over_ratio,
                    'severity': severity,
                    'message': f"{sensor}: {value:.1f}{unit} (max: {max_val}{unit}) → %{over_ratio*100:.1f} aşım"
                })
            
            # SOFT LIMIT: %85-100 (henüz aşım yok, ama yakın)
            elif ratio >= soft_limit_ratio:
                near_ratio = (max_val - value) / max_val  # Ne kadar yakın?
                faults.append({
                    'sensor': sensor,
                    'value': value,
                    'limit': max_val,
                    'direction': 'HIGH',
                    'near_ratio': near_ratio,  # % kaç yakın?
                    'severity': 'DÜŞÜK',  # Soft limit = düşük severity
                    'message': f"{sensor}: {value:.1f}{unit} (max: {max_val}{unit}) → %{ratio*100:.0f} (limite yakın)"
                })
        
        # ─── LOW TARAF KONTROLÜ ───────────────────────────────────────
        if min_val is not None and value < min_val:
            # Division by zero önleme
            if min_val != 0:
                under_ratio = (min_val - value) / min_val
            else:
                # Min limit 0 ise, value negatif ise under_ratio hesapla
                under_ratio = abs(value) / 100.0  # Normalized ratio
            
            severity = "YÜKSEK"  # Alt limit aşımı her zaman ciddi
            
            faults.append({
                'sensor': sensor,
                'value': value,
                'limit': min_val,
                'direction': 'LOW',
                'under_ratio': under_ratio,
                'severity': severity,
                'message': f"{sensor}: {value:.1f}{unit} (min: {min_val}{unit}) → %{under_ratio*100:.1f} düşük"
            })
    
    return faults


def predict_pre_fault_direct(
    machine_id: str,
    window_features: dict,
    ml_predictor,
    threshold: float = 0.50,
) -> dict | None:
    """
    ML PRE-FAULT PREDICTION (OLASI)
    
    Parametreler:
        machine_id: "HPR001"
        window_features: State store'dan alınan özellikler
                         (buffers, ewma_mean, ewma_var, sample_count)
        ml_predictor: pipeline.ml_predictor.predictor nesnesi
        threshold: ML probability threshold (default: 0.50, precision-focused)
    
    Dönüş:
        pre_fault: {
            'probability': 0.75,
            'confidence': 'HIGH',  # >0.7
            'trends': ["main_pressure trend: +%15 artış"],
            'top_features': ["main_pressure__value_max", "active_sensors"],
            'explanation': "ML Modeli %75 ihtimalle yakın arıza öngörüyor"
        }
    """
    if not ml_predictor or not ml_predictor.is_active:
        return None
    
    try:
        # ML prediction
        result = ml_predictor.predict_risk(machine_id, window_features)
        
        # Threshold kontrolü (recall-focused)
        if result.confidence < threshold:
            return None
        
        # Confidence seviyesi
        if result.confidence >= 0.7:
            confidence_level = "HIGH"
        elif result.confidence >= 0.5:
            confidence_level = "MEDIUM"
        else:
            confidence_level = "LOW"
        
        # Trend analizi (basit)
        trends = []
        ewma_mean = window_features.get("ewma_mean", {})
        
        for sensor, mean_val in ewma_mean.items():
            if mean_val and isinstance(mean_val, (int, float)):
                if mean_val > 0:
                    trends.append(f"{sensor}: yükseliş trendi (+{mean_val:.1f})")
        
        return {
            'probability': result.confidence,
            'score': result.score,
            'confidence': confidence_level,
            'trends': trends[:3],  # İlk 3 trend
            'top_features': result.top_features[:3],  # Top 3 feature
            'explanation': result.explanation
        }
        
    except Exception as e:
        log.debug("ML pre-fault prediction hatası: %s", e)
        return None


def generate_hybrid_alert(
    machine_id: str,
    sensor_values: dict,
    window_features: dict,
    limits_config: dict,
    ml_predictor=None,
) -> list[dict]:
    """
    HYBRID ALERT GENERATION (İKİ KATMANLI)
    
    Çalışma Mantığı:
    1. Önce rule-based fault detection (KESİN)
    2. Eğer fault yoksa, ML pre-fault prediction (OLASI)
    3. Alert prioritization: FAULT > PRE_FAULT_WARNING
    
    Parametreler:
        machine_id: "HPR001"
        sensor_values: Anlık sensör değerleri
        window_features: State store verisi (ML için)
        limits_config: limits_config.yaml
        ml_predictor: pipeline.ml_predictor.predictor (opsiyonel)
    
    Dönüş:
        alerts: [
            {
                'type': 'FAULT' | 'PRE_FAULT_WARNING',
                'machine_id': 'HPR001',
                'confidence': 1.0 | 0.75,
                'reasons': [...],
                'recommendation': 'ACİL: Makineyi durdur' | '24 saat içinde bakım planla',
                'sensor_values': {...},
                'timestamp': datetime
            }
        ]
    """
    alerts = []
    
    # ─── KATMAN 1: RULE-BASED FAULT (KESİN) ──────────────────────────
    faults = detect_faults_direct(machine_id, sensor_values, limits_config)
    
    hard_faults = [f for f in faults if f['severity'] != 'DÜŞÜK']
    soft_faults = [f for f in faults if f['severity'] == 'DÜŞÜK']
    
    if faults:
        # Eğer HARD_FAULT varsa, onu kullan
        if hard_faults:
            # Multi-sensor fault check (sadece hard faults)
            multi_sensor = len(hard_faults) >= 2
            
            # Reasons oluştur
            reasons = []
            for fault in hard_faults:
                reasons.append(fault['message'])
            
            if multi_sensor:
                reasons.append(f"⚠️  MULTI-SENSOR FAULT: {len(hard_faults)} sensör limit dışı!")
            
            # Recommendation
            main_pressure_fault = any(f['sensor'] == 'main_pressure' for f in hard_faults)
            if main_pressure_fault:
                recommendation = "ACİL: Makineyi durdur, basınç sistemini kontrol et"
            elif multi_sensor:
                recommendation = "Makineyi durdur, çoklu sensör arızası"
            else:
                recommendation = "İlk fırsatta bakım planla"
            
            # En yüksek severity'yi bul
            severities = [f['severity'] for f in hard_faults]
            if "KRİTİK" in severities:
                overall_severity = "KRİTİK"
            elif "YÜKSEK" in severities:
                overall_severity = "YÜKSEK"
            else:
                overall_severity = "ORTA"
            
            alert = {
                'type': 'FAULT',
                'machine_id': machine_id,
                'confidence': 1.0,  # KESİN
                'severity': overall_severity,
                'reasons': reasons,
                'recommendation': recommendation,
                'sensor_values': sensor_values,
                'fault_count': len(hard_faults),
                'multi_sensor': multi_sensor,
                'timestamp': datetime.utcnow()
            }
            
            alerts.append(alert)
        
        # Eğer sadece SOFT_FAULT varsa (hiç hard fault yok)
        elif soft_faults and not hard_faults:
            # Soft limit warning
            reasons = []
            for fault in soft_faults:
                reasons.append(fault['message'])
            
            if len(soft_faults) >= 2:
                reasons.append(f"⚠️  MULTI-SENSOR: {len(soft_faults)} sensör limite yakın!")
            
            alert = {
                'type': 'SOFT_LIMIT_WARNING',
                'machine_id': machine_id,
                'confidence': 0.8,  # Yüksek ama kesin değil
                'severity': 'DÜŞÜK',
                'reasons': reasons,
                'recommendation': 'Dikkat: Sensör değerlerini izlemeye devam et',
                'sensor_values': sensor_values,
                'soft_fault_count': len(soft_faults),
                'timestamp': datetime.utcnow()
            }
            
            alerts.append(alert)
    
    # ─── KATMAN 2: ML PRE-FAULT PREDICTION (OLASI) ───────────────────
    # Sadece HARD fault yoksa ML uyarısı ver (alert spam önleme)
    if not hard_faults and ml_predictor:
        pre_fault = predict_pre_fault_direct(
            machine_id, 
            window_features, 
            ml_predictor,
            threshold=0.50  # precision-focused (was 0.25)
        )
        
        if pre_fault:
            # Recommendation
            if pre_fault['confidence'] == "HIGH":
                recommendation = "24 saat içinde bakım planla"
            elif pre_fault['confidence'] == "MEDIUM":
                recommendation = "48 saat içinde bakım planla"
            else:
                recommendation = "İzlemeye devam et"
            
            # Reasons: trends + top features
            reasons = []
            if pre_fault['trends']:
                reasons.extend(pre_fault['trends'])
            if pre_fault['top_features']:
                reasons.append(f"Tetikleyenler: {', '.join(pre_fault['top_features'])}")
            if not reasons:
                reasons.append(pre_fault['explanation'])
            
            alert = {
                'type': 'PRE_FAULT_WARNING',
                'machine_id': machine_id,
                'confidence': pre_fault['probability'],
                'severity': 'ORTA' if pre_fault['probability'] > 0.5 else 'DÜŞÜK',
                'reasons': reasons,
                'recommendation': recommendation,
                'sensor_values': sensor_values,
                'ml_score': pre_fault['score'],
                'time_horizon': '30-60 dakika',
                'timestamp': datetime.utcnow()
            }
            
            alerts.append(alert)
    
    # ─── ALERT PRIORITIZATION ────────────────────────────────────────
    # Eğer birden fazla alert varsa, en önemliyi seç
    if len(alerts) > 1:
        def get_priority(atype):
            if atype == 'FAULT': return 3
            if atype == 'PRE_FAULT_WARNING': return 2
            if atype == 'SOFT_LIMIT_WARNING': return 1
            return 0
            
        alerts.sort(key=lambda x: get_priority(x['type']), reverse=True)
        # Sadece ilk alert'i döndür (spam önleme)
        alerts = alerts[:1]
    
    return alerts


def format_hybrid_alert_plain(alert: dict) -> str:
    """Hybrid alert'i düz metin formatında formatla."""
    now = alert['timestamp'].strftime("%H:%M:%S")
    
    # Alert type'a göre sembol ve renk
    alert_type = alert['type']
    symbol, _ = ALERT_TYPE_MAP.get(alert_type, ("⚠️ ", ""))
    
    lines = [
        "",
        f"  {'─'*55}",
        f"  {symbol} {alert_type} ALERT",
        f"  {'─'*55}",
        f"  Makine: {alert['machine_id']}",
    ]
    
    # Type-specific fields
    if alert_type == 'FAULT':
        lines.append(f"  Tip:    KESİN (confidence: %{alert['confidence']*100:.0f})")
        if alert.get('multi_sensor'):
            lines.append(f"  ⚠️  MULTI-SENSOR FAULT: {alert['fault_count']} sensör!")
    elif alert_type == 'PRE_FAULT_WARNING':
        lines.append(f"  Tip:    OLASI (confidence: %{alert['confidence']*100:.0f})")
        lines.append(f"  Zaman:  Önümüzdeki {alert.get('time_horizon', '30-60 dakika')}")
    elif alert_type == 'SOFT_LIMIT_WARNING':
        lines.append(f"  Tip:    YAKLAŞIYOR (confidence: %{alert['confidence']*100:.0f})")
        if alert.get('soft_fault_count'):
            lines.append(f"  ⚠️  {alert['soft_fault_count']} sensör limite yakın!")
    
    lines.append(f"  Saat:   {now}")
    lines.append(f"  {'─'*55}")
    lines.append("  Sebep:")
    
    for reason in alert['reasons']:
        lines.append(f"    • {reason}")
    
    lines.append(f"  {'─'*55}")
    lines.append(f"  Öneri: {alert['recommendation']}")
    lines.append(f"  {'─'*55}\n")
    
    return "\n".join(lines)


def format_hybrid_alert_rich(alert: dict):
    """Hybrid alert'i rich kütüphanesiyle renkli formatla."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich import box
    
    console = Console()
    
    # Alert type'a göre renk ve sembol
    alert_type = alert['type']
    color, symbol = ALERT_TYPE_MAP.get(alert_type, ("white", "⚠️ "))
    
    now = alert['timestamp'].strftime("%H:%M:%S")
    
    body = Text()
    
    # Başlık
    body.append(f"{symbol} {alert_type} ALERT\n", style=f"bold {color}")
    body.append(f"{'─'*50}\n", style="dim")
    
    # Makine bilgisi
    body.append(f"Makine: ", style="bold")
    body.append(f"{alert['machine_id']}\n", style=color)
    
    if alert_type == 'FAULT':
        body.append(f"Tip:    ", style="bold")
        body.append(f"KESİN (confidence: %{alert['confidence']*100:.0f})\n", style="bold green")
        if alert.get('multi_sensor'):
            body.append(f"⚠️  MULTI-SENSOR FAULT: {alert['fault_count']} sensör!\n", style="bold red")
    elif alert_type == 'PRE_FAULT_WARNING':
        body.append(f"Tip:    ", style="bold")
        body.append(f"OLASI (confidence: %{alert['confidence']*100:.0f})\n", style="yellow")
        body.append(f"Zaman:  ", style="bold")
        body.append(f"Önümüzdeki {alert.get('time_horizon', '30-60 dakika')}\n", style="dim")
    elif alert_type == 'SOFT_LIMIT_WARNING':
        body.append(f"Tip:    ", style="bold")
        body.append(f"YAKLAŞIYOR (confidence: %{alert['confidence']*100:.0f})\n", style="blue")
        if alert.get('soft_fault_count'):
            body.append(f"⚠️  {alert['soft_fault_count']} sensör limite yakın!\n", style="blue")
    
    body.append(f"Saat:   {now}\n", style="dim")
    body.append(f"\n{'─'*50}\n", style="dim")
    
    # Sebep
    body.append("Sebep:\n", style="bold")
    for reason in alert['reasons']:
        body.append(f"  • {reason}\n", style="white")
    
    body.append(f"\n{'─'*50}\n", style="dim")
    
    # Öneri
    body.append("Öneri: ", style="bold yellow")
    body.append(f"{alert['recommendation']}\n", style="yellow")
    
    body.append(f"{'─'*50}\n", style="dim")
    
    # Panel oluştur
    panel = Panel(
        body,
        title=f"[{color}]{alert['machine_id']} — {alert_type}[/{color}]",
        border_style=color,
        box=box.ROUNDED,
        padding=(0, 2),
    )
    
    console.print(panel)


def process_hybrid_alert(
    alert: dict,
    use_rich: bool = True,
) -> bool:
    """
    HYBRID ALERT İŞLEME
    
    Parametreler:
        alert: generate_hybrid_alert()'tan dönen alert dict
        use_rich: rich kütüphanesi kullanılsın mı?
    
    Dönüş: True = alert işlendi, False = throttle edildi
    """
    alert_type = alert['type']
    severity = alert.get('severity', 'ORTA')
    machine_id = alert['machine_id']
    
    # Throttle kontrolü
    if not should_alert(machine_id, severity):
        log.debug("THROTTED | %s | %s | confidence=%.2f", 
                 machine_id, alert_type, alert['confidence'])
        return False
    
    # Alert'i işaretle
    _last_alert[machine_id] = datetime.utcnow()
    
    log.info("HYBRID_ALERT | %s | %s | confidence=%.2f | reasons=%d",
             machine_id, alert_type, alert['confidence'], len(alert['reasons']))
    
    # Format ve print
    try:
        if use_rich:
            format_hybrid_alert_rich(alert)
        else:
            print(format_hybrid_alert_plain(alert))
    except Exception as e:
        log.error("Alert formatting hatası: %s", e)
        print(format_hybrid_alert_plain(alert))
    
    return True


# ============================================================================

def _format_plain(event: RiskEvent) -> str:
    """rich yoksa düz metin format."""
    now  = datetime.now().strftime("%H:%M:%S")
    sym  = SEVERITY_STYLE.get(event.severity, ("", "⚠️ "))[1]
    lines = [
        "",
        f"  {'─'*55}",
        f"  {sym} {event.machine_id} — {event.severity}  [{now}]",
        f"  Risk: {_format_bar(event.risk_score)} {event.risk_score:.0f}/100  "
        f"| Güven: %{event.confidence*100:.0f}",
        f"  {'─'*55}",
    ]
    for r in event.reasons:
        lines.append(f"  • {r}")

    if event.eta_minutes:
        h, m = divmod(int(event.eta_minutes), 60)
        lines.append(f"  ⏱  Tahmini kritik eşiğe süre: {h}sa {m}dk")

    # ─── ML Blok ──────────────────────────────────
    if getattr(event, "ml_score", 0) > 0:
        ml_pct = int(getattr(event, "ml_confidence", 0) * 100)
        ml_bar = _format_bar(event.ml_score, width=15)
        lines.append(f"  {'─'*55}")
        lines.append(f"  🧠 ML Analizi:")
        lines.append(f"    Anomali Olasılığı : %{ml_pct}  |  "
                     f"Skor: {ml_bar} {event.ml_score:.0f}/100")
        if event.ml_explanation:
            lines.append(f"    {event.ml_explanation}")
    # ─────────────────────────────────────────────

    if event.sensor_values:
        lines.append(f"  {'─'*55}")
        lines.append("  Anlık değerler:")
        for k, v in list(event.sensor_values.items())[:6]:
            lines.append(f"    {k}: {v}")

    lines.append(f"  {'─'*55}\n")
    return "\n".join(lines)



def _format_rich(event: RiskEvent):
    """rich kütpüphanesiyle renkli panel."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich import box

    console = Console()
    color   = SEVERITY_STYLE.get(event.severity, ("white", "⚠️ "))[0]
    sym     = SEVERITY_STYLE.get(event.severity, ("white", "⚠️ "))[1]
    now     = datetime.now().strftime("%H:%M:%S")

    body = Text()
    body.append(f"Risk: ", style="bold")
    body.append(f"{_format_bar(event.risk_score)} {event.risk_score:.0f}/100\n", style=color)
    body.append(f"Güven: %{event.confidence*100:.0f}  |  Zaman: {now}\n\n")

    for r in event.reasons:
        body.append(f"• {r}\n", style="white")

    if event.eta_minutes:
        h, m = divmod(int(event.eta_minutes), 60)
        body.append(f"\n⏱  Kritik eşiğe tahmini süre: ", style="bold")
        body.append(f"{h}sa {m}dk\n", style="bold " + color)

    # ─── ML Blok ──────────────────────────────────────────────────────
    if getattr(event, "ml_score", 0) > 0:
        ml_pct = int(getattr(event, "ml_confidence", 0) * 100)
        body.append(f"\n🧠 ML Analizi:\n", style="bold cyan")
        body.append(f"  Anomali Olasılığı : %{ml_pct}  |  "
                    f"ML Skoru: {event.ml_score:.0f}/100\n", style="cyan")
        if event.ml_explanation:
            body.append(f"  {event.ml_explanation}\n", style="italic cyan")
    # ──────────────────────────────────────────────────────────────────

    if event.sensor_values:
        body.append("\nAnlık değerler:\n", style="dim")
        for k, v in list(event.sensor_values.items())[:6]:
            body.append(f"  {k}: {v}\n", style="dim")

    panel = Panel(
        body,
        title=f"[{color}]{sym} {event.machine_id} — {event.severity}[/{color}]",
        border_style=color,
        box=box.ROUNDED,
        padding=(0, 2),
    )
    console.print(panel)



def process_alert(event: RiskEvent, min_score: float = 20.0) -> bool:
    """
    Alert üretme kararı verir ve terminale basar.
    Dönüş: True = alert üretildi, False = atlandı.
    
    NOT: Bu fonksiyon eski mod için (risk_scorer'dan gelen alert'ler).
    Yeni hybrid mode için generate_hybrid_alert() kullan.
    """
    if event.risk_score < min_score:
        return False

    if not should_alert(event.machine_id, event.severity):
        log.debug("THROTTLED | %s | skor=%.0f", event.machine_id, event.risk_score)
        return False

    # Alert üret
    _last_alert[event.machine_id] = datetime.utcnow()
    log.info("ALERT | %s | %s | skor=%.0f | güven=%.2f",
             event.machine_id, event.severity, event.risk_score, event.confidence)

    try:
        _format_rich(event)
    except ImportError:
        print(_format_plain(event))

    return True
