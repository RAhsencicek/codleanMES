"""
prediction_agent.py — Tahmin Ajanı
═══════════════════════════════════
Trend ekstrapolasyonu ile hidrolik preslerin gelecek durumunu tahmin eden
matematiksel ajan. EWMA eğimlerini kullanarak "bu gidişle ne zaman limit
aşılır?" sorusuna kesin cevap verir.

Fabrika benzetmesi: Deneyimli planlama mühendisi.
"Bu gidişle ne zaman başımıza iş açar?" sorusuna matematiksel cevap verir.
Her sensörün trendini izler, limiti ne zaman aşacağını hesaplar,
en iyi / orta / en kötü senaryoları çizer.

API (Gemini) sadece senaryo yorumları için kullanılır;
temel değer — ETA hesaplamaları — matematikseldir ve API'siz de çalışır.

Kullanım:
    from src.analysis.prediction_agent import get_prediction_agent
    agent = get_prediction_agent()
    sonuc = await agent.predict(context_package)
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

# .env dosyasından API key yükle — proje kökündeki .env'i bul
try:
    from dotenv import load_dotenv

    _env_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        ".env",
    )
    load_dotenv(_env_path)
    _dotenv_loaded = True
except ImportError:
    _dotenv_loaded = False

log = logging.getLogger("prediction_agent")

# ─── Enumerasyonlar ──────────────────────────────────────────────────────────


class PredictionConfidence(Enum):
    """
    Tahminin güvenilirlik seviyesi.

    Fabrika benzetmesi: Planlama mühendisinin "Bu hesap ne kadar sağlam?"
    sorusuna verdiği cevap. Veri çoksa "Yüksek", azsa "Düşük".
    """

    HIGH = "Yüksek"
    MEDIUM = "Orta"
    LOW = "Düşük"


# ─── Veri Yapıları ───────────────────────────────────────────────────────────


@dataclass
class SensorTrend:
    """
    Tek bir sensörün trend analizi sonucu.

    Fabrika benzetmesi: Bir göstergenin son 2 saatteki hareket özeti.
    "Saatte 8 derece artıyor, yön yukarı, veri 45 nokta, güven %75".
    """

    sensor_name: str
    current_value: float
    unit: str
    slope_per_hour: float
    slope_per_minute: float
    trend_direction: str       # "increasing", "decreasing", "stable"
    data_points: int
    r_squared: float


@dataclass
class ETAPrediction:
    """
    Bir sensörün limit aşımına kadar kalan süre tahmini.

    Fabrika benzetmesi: Termometreye bakıp
    "Şu an 42 derece, saatte 3 derece artıyor, limit 45 ise
    1 saat sonra alarm çalar" demek.
    """

    sensor_name: str
    sensor_name_tr: str        # Turkish name
    current_value: float
    limit_value: float
    limit_type: str            # "soft" or "hard"
    time_to_limit_min: float
    time_to_limit_human: str   # "3.5 saat"
    will_breach: bool
    breach_time: Optional[str] = None
    confidence: PredictionConfidence = PredictionConfidence.MEDIUM


@dataclass
class ScenarioPrediction:
    """
    Gelecek için bir senaryo tahmini.

    Fabrika benzetmesi: Planlama toplantısındaki "Ya şöyle olursa?" soruları.
    En iyi durum, orta durum, en kötü durum.
    """

    scenario_name: str
    description_tr: str
    time_to_failure_min: float
    probability: float
    outcome: str


@dataclass
class PredictionResult:
    """
    Tahmin Ajanının nihai çıktısı.

    Fabrika benzetmesi: Planlama mühendisinin masaya bıraktığı rapor.
    "HPR001'de yağ sıcaklığı 1.5 saat sonra kiritk olacak,
    en kötü senaryoda 45 dakika, en iyi senaryoda 3 saat".
    """

    machine_id: str
    timestamp: str
    overall_status: str         # "critical", "warning", "normal"
    time_to_critical_min: Optional[float] = None
    time_to_critical_human: str = ""
    sensor_trends: dict = field(default_factory=dict)
    eta_predictions: list = field(default_factory=list)
    scenarios: list = field(default_factory=list)
    summary_tr: str = ""
    urgency_level: str = "monitor"  # "immediate", "soon", "monitor"
    recommended_action: str = ""
    based_on_diagnosis: str = ""
    execution_time_sec: float = 0.0
    agent_version: str = "1.0"


# ─── Sensör İsimleri Çevirisi ────────────────────────────────────────────────

_SENSOR_NAMES_TR = {
    "oil_tank_temperature": "Yağ sıcaklığı",
    "main_pressure": "Ana basınç",
    "horizontal_press_pressure": "Yatay pres basıncı",
    "lower_ejector_pressure": "Alt ejektör basıncı",
    "horitzonal_infeed_speed": "Yatay besleme hızı",  # Note: typo in original data
    "vertical_infeed_speed": "Dikey besleme hızı",
}

# ─── Sistem Promptu ──────────────────────────────────────────────────────────

_PREDICTION_SYSTEM_PROMPT = """Sen Codlean MES fabrikasının planlama mühendisisin.
15 yıldır hidrolik preslerin bakım planlamasını yapıyorsun.
Sensör trendlerine bakarak "bu gidişle ne olur?" sorusuna cevap verirsin.

KİM OLDUĞUN:
Fabrikanın trend analisti ve planlama uzmanısın.
Matematiksel hesapları sen yaparsın, senaryoları sen çizersin.
API'ye ihtiyaç duymazsan bile kendi hesaplarınla makineyi izlersin.

NASIL ÇALIŞIRSIN:
1. Her sensörün eğimini (slope) alırsın.
2. Limiti ne zaman aşacağını basit matematikle hesaplarsın.
3. En iyi, orta ve en kötü senaryoyu çizersin.
4. Makine ne kadar süre güvenle çalışır, onu söylersin.

KURALLAR:
- Sadece JSON çıktısı üret, başka metin yazma.
- Senaryolar gerçekçi olsun, uçuk kaçak tahminler yapma.
- Türkçe açıklamalar kullan.
- Zaman birimleri dakika ve saat olarak yaz.
"""

# ─── JSON Çıktı Şeması (Prompt İçinde) ───────────────────────────────────────

_JSON_OUTPUT_SCHEMA = """
ÇIKTI FORMATI — Sadece bu JSON şemasını kullan, başka metin yazma:

{
  "machine_id": "HPR001",
  "timestamp": "2026-04-24 12:00:00",
  "overall_status": "warning",
  "time_to_critical_min": 90.0,
  "time_to_critical_human": "1.5 saat",
  "summary_tr": "Yağ sıcaklığı 1.5 saat sonra kritik seviyeye ulaşacak.",
  "urgency_level": "soon",
  "recommended_action": "Soğutma sistemini kontrol edin, iş yükünü düşürün.",
  "scenarios": [
    {
      "scenario_name": "En iyi senaryo",
      "description_tr": "Soğutma devreye girer, trend yavaşlar.",
      "time_to_failure_min": 180.0,
      "probability": 0.25,
      "outcome": "Müdahale başarılı, makine güvenle çalışmaya devam eder."
    },
    {
      "scenario_name": "Orta senaryo",
      "description_tr": "Trend aynı hızda devam eder.",
      "time_to_failure_min": 90.0,
      "probability": 0.50,
      "outcome": "1.5 saat sonra kritik limit aşılır, bakım gerekir."
    },
    {
      "scenario_name": "En kötü senaryo",
      "description_tr": "İç kaçak büyür, zincirleme arıza başlar.",
      "time_to_failure_min": 45.0,
      "probability": 0.25,
      "outcome": "45 dakika sonra acil durdurma gerekebilir."
    }
  ]
}
"""

# ─── Ana Sınıf ───────────────────────────────────────────────────────────────


class PredictionAgent:
    """
    Tahmin Ajanı — Trend ekstrapolasyonu ile gelecek tahmini yapar.

    Fabrika benzetmesi: Deneyimli planlama mühendisi.
    "Bu gidişle ne zaman başımıza iş açar?" sorgusuna matematiksel cevap verir.
    API (Gemini) sadece senaryo yorumları için kullanılır;
    ETA hesaplamaları matematikseldir ve API'siz de çalışır.
    """

    CALL_TIMEOUT_SEC = 30
    MODEL_NAME = "gemini-2.5-flash"

    # Eğim eşiği — bunun altındaki eğimler "stabil" sayılır
    SLOPE_THRESHOLD = 0.05

    def __init__(self, api_key: str | None = None):
        self._ready = False
        self._client = None
        self._init_error = None

        # API Key Rotation Manager kullan
        from src.core.api_key_manager import get_api_key
        
        key = api_key or get_api_key()

        log.info("[PREDICTION_INIT] dotenv yüklendi: %s", _dotenv_loaded)
        log.info("[PREDICTION_INIT] API Key mevcut: %s", bool(key))
        if key:
            log.info("[PREDICTION_INIT] API Key ilk 8 karakter: %s...", key[:8])

        if not key:
            self._init_error = "GEMINI_API_KEY tanımlı değil. .env dosyasını kontrol edin."
            log.warning("[PREDICTION_INIT] %s", self._init_error)
            return

        try:
            from google import genai

            self._client = genai.Client(api_key=key)
            self._ready = True
            log.info("[PREDICTION_INIT] ✅ Tahmin Ajanı hazır (%s)", self.MODEL_NAME)
        except ImportError:
            self._init_error = (
                "google-genai kütüphanesi kurulu değil. 'pip install google-genai' çalıştırın."
            )
            log.warning("[PREDICTION_INIT] %s", self._init_error)
        except Exception as e:
            self._init_error = f"Gemini başlatılamadı: {e}"
            log.warning("[PREDICTION_INIT] %s", self._init_error)

    @property
    def is_ready(self) -> bool:
        """Gemini API hazır mı?"""
        return self._ready

    # ─── Ana Giriş Noktası ───────────────────────────────────────────────────

    async def predict(self, context: dict, diagnosis_result: dict | None = None) -> PredictionResult:
        """
        Makine bağlamını alır, trendleri analiz eder, ETA tahminleri ve senaryolar üretir.

        Fabrika benzetmesi: Planlama mühendisi masasına oturur,
        sensör trendlerini inceler, "ne zaman limit aşılır?" hesaplar,
        en iyi / orta / en kötü senaryoları çizer.

        Args:
            context: pipeline.context_builder.build() çıktısı.
            diagnosis_result: Opsiyonel teşhis sonucu (senaryoları zenginleştirir).

        Returns:
            PredictionResult: Yapılandırılmış tahmin raporu.
        """
        start_time = time.monotonic()
        machine_id = context.get("machine_id", "UNKNOWN")

        log.info("[PREDICT START] %s — tahmin analizi başlıyor", machine_id)

        # 1. Sensör trendlerini analiz et (her durumda çalışır — matematiksel)
        sensor_trends = self._analyze_sensor_trends(context)
        log.info(
            "[PREDICT] %s — %d sensör trendi analiz edildi",
            machine_id, len(sensor_trends),
        )

        # 2. ETA tahminlerini hesapla (temel değer — matematiksel)
        eta_predictions = self._calculate_eta_predictions(sensor_trends, context)
        log.info(
            "[PREDICT] %s — %d ETA tahmini üretildi",
            machine_id, len(eta_predictions),
        )

        # 3. Genel durum ve aciliyet belirle
        overall_status, urgency_level = self._determine_overall_status(eta_predictions)
        time_to_critical_min, time_to_critical_human = self._extract_most_urgent(eta_predictions)

        # 4. Senaryo üret (API varsa LLM, yoksa yerel)
        scenarios: list[ScenarioPrediction] = []
        if self._ready:
            try:
                scenarios = await self._generate_scenarios(context, diagnosis_result, eta_predictions)
                log.info("[PREDICT] %s — LLM senaryoları üretildi (%d)", machine_id, len(scenarios))
            except Exception as e:
                log.warning("[PREDICT] %s — LLM senaryo hatası: %s", machine_id, e)

        if not scenarios:
            scenarios = self._create_local_scenarios(eta_predictions)
            log.info("[PREDICT] %s — yerel senaryolar üretildi (%d)", machine_id, len(scenarios))

        # 5. Özet ve öneri
        summary_tr = self._build_summary(machine_id, eta_predictions, overall_status)
        recommended_action = self._build_recommendation(eta_predictions, urgency_level)

        # 6. Teşhis bilgisini kaydet
        based_on = ""
        if diagnosis_result and isinstance(diagnosis_result, dict):
            primary = diagnosis_result.get("primary_diagnosis")
            if isinstance(primary, dict):
                based_on = primary.get("fault_type", "")
            elif diagnosis_result.get("fault_type"):
                based_on = diagnosis_result.get("fault_type", "")

        execution_time = round(time.monotonic() - start_time, 2)
        log.info("[PREDICT END] %s — tahmin tamamlandı (%.2fs)", machine_id, execution_time)

        return PredictionResult(
            machine_id=machine_id,
            timestamp=context.get("timestamp", ""),
            overall_status=overall_status,
            time_to_critical_min=time_to_critical_min,
            time_to_critical_human=time_to_critical_human,
            sensor_trends=sensor_trends,
            eta_predictions=eta_predictions,
            scenarios=scenarios,
            summary_tr=summary_tr,
            urgency_level=urgency_level,
            recommended_action=recommended_action,
            based_on_diagnosis=based_on,
            execution_time_sec=execution_time,
            agent_version="1.0",
        )

    # ─── Sensör Trend Analizi ────────────────────────────────────────────────

    def _analyze_sensor_trends(self, context: dict) -> dict[str, SensorTrend]:
        """
        Context'teki sensör verilerinden trendleri çıkarır.

        Fabrika benzetmesi: Her göstergenin son 2 saatteki hareketini
        not almak — "Saatte kaç birim artıyor, yön ne, veri ne kadar güvenilir?"
        """
        trends: dict[str, SensorTrend] = {}
        sensor_states = context.get("sensor_states", {})
        operating_minutes = context.get("operating_minutes", 0)

        # Veri zenginliği tahmini: çalışma süresine göre
        if operating_minutes >= 120:
            base_data_points = 60
            base_r2 = 0.80
        elif operating_minutes >= 60:
            base_data_points = 40
            base_r2 = 0.65
        else:
            base_data_points = 30
            base_r2 = 0.50

        for key, s in sensor_states.items():
            val = s.get("value")
            slope = s.get("slope_per_hour")
            unit = s.get("unit", "")

            if val is None:
                continue

            # Eğim yoksa stabil kabul et
            if slope is None:
                slope = 0.0

            # Trend yönü
            if slope > self.SLOPE_THRESHOLD:
                direction = "increasing"
            elif slope < -self.SLOPE_THRESHOLD:
                direction = "decreasing"
            else:
                direction = "stable"

            # Eğim büyüklüğüne göre r² ayarla — keskin trendler daha güvenilir
            if abs(slope) > 5.0:
                r_squared = min(0.95, base_r2 + 0.15)
            elif abs(slope) > 1.0:
                r_squared = min(0.90, base_r2 + 0.10)
            else:
                r_squared = base_r2

            trends[key] = SensorTrend(
                sensor_name=key,
                current_value=round(float(val), 2),
                unit=unit,
                slope_per_hour=round(float(slope), 4),
                slope_per_minute=round(float(slope) / 60.0, 6),
                trend_direction=direction,
                data_points=base_data_points,
                r_squared=round(r_squared, 2),
            )

        return trends

    # ─── ETA Tahmin Hesaplaması (Kritik Matematik) ───────────────────────────

    def _calculate_eta_predictions(self, sensor_trends: dict[str, SensorTrend], context: dict) -> list[ETAPrediction]:
        """
        Her sensör için limit aşımına kalan süreyi hesaplar.

        Fabrika benzetmesi: Termometreye bakıp "42 derece, saatte 3 artıyor,
        limit 45 ise 1 saat kaldı" demek. Hem yumuşak (soft) hem sert (hard)
        limit için ayrı hesap yapar.

        Formül: time_to_limit = (limit - current) / slope
        """
        predictions: list[ETAPrediction] = []
        machine_id = context.get("machine_id", "UNKNOWN")

        # Makine limitlerini limits_config.yaml'dan yükle
        limits = self._load_machine_limits(machine_id)

        for key, trend in sensor_trends.items():
            slope = trend.slope_per_hour
            current = trend.current_value

            # Eğim sıfırsa — stabil, tahmin yapma
            if abs(slope) < self.SLOPE_THRESHOLD:
                continue

            sensor_limits = limits.get(key, {})
            max_lim = sensor_limits.get("max")
            min_lim = sensor_limits.get("min")
            warn_level = sensor_limits.get("warn_level")

            # --- HARD LIMIT (max) ---
            if max_lim is not None and slope > 0:
                # Artıyor ve max limit var
                remaining = max_lim - current
                if remaining <= 0:
                    # Zaten aşılmış
                    predictions.append(ETAPrediction(
                        sensor_name=key,
                        sensor_name_tr=self._translate_sensor_name(key),
                        current_value=round(current, 2),
                        limit_value=max_lim,
                        limit_type="hard",
                        time_to_limit_min=0.0,
                        time_to_limit_human="Şu an aşılmış",
                        will_breach=True,
                        breach_time="Şimdi",
                        confidence=self._determine_confidence(trend),
                    ))
                else:
                    time_hours = remaining / slope
                    time_min = time_hours * 60.0
                    if time_min > 0:
                        predictions.append(ETAPrediction(
                            sensor_name=key,
                            sensor_name_tr=self._translate_sensor_name(key),
                            current_value=round(current, 2),
                            limit_value=max_lim,
                            limit_type="hard",
                            time_to_limit_min=round(time_min, 1),
                            time_to_limit_human=self._format_time_human(time_min),
                            will_breach=True,
                            confidence=self._determine_confidence(trend),
                        ))

            # --- SOFT LIMIT (warn_level) ---
            if warn_level is not None and slope > 0:
                remaining = warn_level - current
                if remaining > 0:
                    time_hours = remaining / slope
                    time_min = time_hours * 60.0
                    if time_min > 0:
                        predictions.append(ETAPrediction(
                            sensor_name=key,
                            sensor_name_tr=self._translate_sensor_name(key),
                            current_value=round(current, 2),
                            limit_value=warn_level,
                            limit_type="soft",
                            time_to_limit_min=round(time_min, 1),
                            time_to_limit_human=self._format_time_human(time_min),
                            will_breach=True,
                            confidence=self._determine_confidence(trend),
                        ))

            # --- MIN LIMIT (azalma durumunda) ---
            if min_lim is not None and slope < 0:
                # Azalıyor ve min limit var
                remaining = current - min_lim
                if remaining <= 0:
                    predictions.append(ETAPrediction(
                        sensor_name=key,
                        sensor_name_tr=self._translate_sensor_name(key),
                        current_value=round(current, 2),
                        limit_value=min_lim,
                        limit_type="hard",
                        time_to_limit_min=0.0,
                        time_to_limit_human="Şu an alt limitin altında",
                        will_breach=True,
                        breach_time="Şimdi",
                        confidence=self._determine_confidence(trend),
                    ))
                else:
                    time_hours = remaining / abs(slope)
                    time_min = time_hours * 60.0
                    if time_min > 0:
                        predictions.append(ETAPrediction(
                            sensor_name=key,
                            sensor_name_tr=self._translate_sensor_name(key),
                            current_value=round(current, 2),
                            limit_value=min_lim,
                            limit_type="hard",
                            time_to_limit_min=round(time_min, 1),
                            time_to_limit_human=self._format_time_human(time_min),
                            will_breach=True,
                            confidence=self._determine_confidence(trend),
                        ))

        # En acil olanı önce göster (kalan süre artan sıralama)
        predictions.sort(key=lambda x: x.time_to_limit_min if x.time_to_limit_min > 0 else float("inf"))
        return predictions

    def _load_machine_limits(self, machine_id: str) -> dict:
        """
        limits_config.yaml'dan makine limitlerini yükler.

        Fabrika benzetmesi: Fabrika el kitabından "HPR001'in yağ sıcaklığı
        limiti kaç derece?" sorusuna cevap bulmak.
        """
        limits: dict = {}
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "config",
            "limits_config.yaml",
        )

        try:
            if os.path.exists(config_path):
                import yaml
                with open(config_path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                machine_limits = data.get("machine_limits", {})
                limits = machine_limits.get(machine_id, {})
        except Exception as e:
            log.warning("Limit config yüklenemedi: %s", e)

        return limits

    def _determine_confidence(self, trend: SensorTrend) -> PredictionConfidence:
        """
        Trend kalitesine göre tahmin güvenini belirler.

        Fabrika benzetmesi: "Bu hesap ne kadar sağlam?"
        Veri çok ve trend netse "Yüksek", az ve belirsizse "Düşük".
        """
        if trend.r_squared > 0.80 and trend.data_points > 50:
            return PredictionConfidence.HIGH
        elif trend.r_squared > 0.50 and trend.data_points > 20:
            return PredictionConfidence.MEDIUM
        else:
            return PredictionConfidence.LOW

    # ─── Durum ve Aciliyet Belirleme ─────────────────────────────────────────

    def _determine_overall_status(self, eta_predictions: list[ETAPrediction]) -> tuple[str, str]:
        """
        ETA tahminlerine göre genel durum ve aciliyet seviyesi belirler.

        Fabrika benzetmesi: Tüm hesaplar bitince "Durum ne, ne kadar acil?"
        diye masaya vurmak.
        """
        if not eta_predictions:
            return "normal", "monitor"

        # 1) Eğer şimdiden limit aşılmış bir sensör varsa → kritik
        if any(e.time_to_limit_min == 0 and e.will_breach for e in eta_predictions):
            return "critical", "immediate"

        # 2) İleriye dönük ETA'lar üzerinden değerlendirme
        valid_etas = [e for e in eta_predictions if e.time_to_limit_min > 0]
        if not valid_etas:
            return "normal", "monitor"

        shortest = min(valid_etas, key=lambda x: x.time_to_limit_min)
        t = shortest.time_to_limit_min

        if t <= 30:
            return "critical", "immediate"
        elif t <= 120:
            return "warning", "soon"
        else:
            return "normal", "monitor"

    def _extract_most_urgent(self, eta_predictions: list[ETAPrediction]) -> tuple[Optional[float], str]:
        """
        En acil ETA tahminini döner.
        """
        # Önce şu an aşılmış olanları kontrol et
        breached_now = [e for e in eta_predictions if e.time_to_limit_min == 0 and e.will_breach]
        if breached_now:
            return 0.0, "Şu an aşılmış"

        valid_etas = [e for e in eta_predictions if e.time_to_limit_min > 0]
        if not valid_etas:
            return None, ""

        shortest = min(valid_etas, key=lambda x: x.time_to_limit_min)
        return shortest.time_to_limit_min, shortest.time_to_limit_human

    # ─── Yardımcı Metodlar ───────────────────────────────────────────────────

    def _translate_sensor_name(self, sensor_name: str) -> str:
        """
        İngilizce sensör adını Türkçeye çevirir.

        Fabrika benzetmesi: Yabancı isimleri Türkçe karşılıklarıyla
        değiştirmek ki herkes anlasın.
        """
        return _SENSOR_NAMES_TR.get(sensor_name, sensor_name)

    def _format_time_human(self, minutes: float) -> str:
        """
        Dakikayı insanın okuyabileceği Türkçe metne çevirir.

        Fabrika benzetmesi: "90 dakika" demek yerine "1.5 saat" demek.
        """
        if minutes < 1:
            return f"{int(minutes * 60)} saniye"
        elif minutes < 60:
            return f"{int(minutes)} dakika"
        elif minutes < 1440:
            hours = minutes / 60.0
            return f"{hours:.1f} saat"
        else:
            days = minutes / 1440.0
            return f"{days:.1f} gün"

    def _build_summary(self, machine_id: str, eta_predictions: list[ETAPrediction], overall_status: str) -> str:
        """
        Tahminlerden özet metin üretir.
        """
        if not eta_predictions:
            return f"{machine_id}: Tüm sensörler stabil, yakın zamanda limit aşımı beklenmiyor."

        valid_etas = [e for e in eta_predictions if e.time_to_limit_min > 0]
        if not valid_etas:
            return f"{machine_id}: Limit aşımı tespit edildi, acil müdahale gerekebilir."

        shortest = min(valid_etas, key=lambda x: x.time_to_limit_min)
        status_desc = {
            "critical": "kritik",
            "warning": "riskli",
            "normal": "normal",
        }.get(overall_status, overall_status)

        return (
            f"{machine_id}: {shortest.sensor_name_tr} {shortest.time_to_limit_human} sonra "
            f"{shortest.limit_type} limiti aşacak. Genel durum: {status_desc}."
        )

    def _build_recommendation(self, eta_predictions: list[ETAPrediction], urgency: str) -> str:
        """
        Aciliyet seviyesine göre öneri üretir.
        """
        if urgency == "immediate":
            return "Acil müdahale gerekiyor. Makineyi güvenli şekilde durdurun ve teknisyeni çağırın."
        elif urgency == "soon":
            return "1-2 saat içinde kontrol yapın. İş yükünü düşürmeyi ve soğutma/basınç sistemlerini kontrol etmeyi değerlendirin."
        else:
            return "Trendi izlemeye devam edin. Standart bakım takvimine uyun."

    # ─── Senaryo Üretimi (LLM + Yerel Fallback) ──────────────────────────────

    async def _generate_scenarios(
        self, context: dict, diagnosis: dict | None, eta_predictions: list[ETAPrediction]
    ) -> list[ScenarioPrediction]:
        """
        Gemini API ile 3 senaryo (en iyi / orta / en kötü) üretir.

        Fabrika benzetmesi: Planlama toplantısında "Ya şöyle olursa?"
        sorularına uzmanın cevabı.
        """
        if not self._ready:
            return []

        prompt = self._build_scenario_prompt(context, diagnosis, eta_predictions)

        response_text = await asyncio.get_event_loop().run_in_executor(
            None, self._call_llm_sync, prompt
        )

        if not response_text or response_text.startswith(("⏰", "🚫", "🔑", "🌐", "❌")):
            log.warning("[SCENARIO] LLM hatası: %s", response_text)
            return []

        return self._parse_scenario_response(response_text)

    def _build_scenario_prompt(
        self, context: dict, diagnosis: dict | None, eta_predictions: list[ETAPrediction]
    ) -> str:
        """
        Senaryo üretimi için prompt oluşturur.
        """
        lines = [
            "Sen bir hidrolik pres planlama mühendisisin. 15 yıllık deneyimin var.",
            "GÖREV: Aşağıdaki sensör trendlerine dayalı 3 senaryo üret.",
            "",
            "SENARYOLAR:",
            "1. En iyi senaryo (olasılık ~%25): Trend yavaşlar, müdahale başarılı.",
            "2. Orta senaryo (olasılık ~%50): Trend aynı hızda devam eder.",
            "3. En kötü senaryo (olasılık ~%25): Trend hızlanır, zincirleme arıza.",
            "",
            "KURALLAR:",
            "- Senaryolar gerçekçi olsun, uçuk kaçak tahminler yapma.",
            "- Türkçe açıklamalar kullan.",
            "- Zaman birimleri dakika ve saat olarak yaz.",
            "- Sadece JSON çıktısı üret, başka metin yazma.",
            "",
            "ETA TAHMİNLERİ:",
        ]

        for eta in eta_predictions[:5]:
            lines.append(
                f"- {eta.sensor_name_tr}: {eta.current_value}{self._get_unit_for_sensor(eta.sensor_name)} "
                f"→ {eta.limit_type} limit ({eta.limit_value}) {eta.time_to_limit_human} sonra aşılacak"
            )

        if diagnosis and isinstance(diagnosis, dict):
            lines.append("")
            lines.append("TEŞHİS BİLGİSİ:")
            primary = diagnosis.get("primary_diagnosis")
            if isinstance(primary, dict):
                lines.append(f"- Teşhis: {primary.get('fault_type', 'Bilinmeyen')}")
                lines.append(f"- Açıklama: {primary.get('description_tr', '')}")
            else:
                lines.append(f"- Teşhis: {diagnosis.get('fault_type', 'Bilinmeyen')}")

        lines.extend(["", _JSON_OUTPUT_SCHEMA, ""])
        lines.append("ÇIKTI: Sadece JSON döndür, başka metin yazma.")

        return "\n".join(lines)

    def _get_unit_for_sensor(self, sensor_name: str) -> str:
        """Sensör adından birim tahmini."""
        units = {
            "oil_tank_temperature": "°C",
            "main_pressure": " bar",
            "horizontal_press_pressure": " bar",
            "lower_ejector_pressure": " bar",
            "horitzonal_infeed_speed": " mm/s",
            "vertical_infeed_speed": " mm/s",
        }
        return units.get(sensor_name, "")

    def _parse_scenario_response(self, response_text: str) -> list[ScenarioPrediction]:
        """
        LLM yanıtını ayrıştırır. 3 seviyeli fallback.
        """
        if not response_text:
            return []

        # Seviye 1: Doğrudan JSON parse
        try:
            data = json.loads(response_text)
            return self._extract_scenarios_from_dict(data)
        except json.JSONDecodeError:
            pass

        # Seviye 2: Regex ile JSON çıkarma
        try:
            code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
            if code_block:
                data = json.loads(code_block.group(1))
                return self._extract_scenarios_from_dict(data)

            brace_block = re.search(r"(\{.*\})", response_text, re.DOTALL)
            if brace_block:
                data = json.loads(brace_block.group(1))
                return self._extract_scenarios_from_dict(data)
        except json.JSONDecodeError:
            pass

        log.warning("[SCENARIO PARSE] JSON çıkarma başarısız. Ham yanıt (ilk 200 karakter): %s", response_text[:200])
        return []

    def _extract_scenarios_from_dict(self, data: dict) -> list[ScenarioPrediction]:
        """
        Parse edilmiş JSON dict'ten senaryo listesi çıkarır.
        """
        scenarios: list[ScenarioPrediction] = []
        raw_scenarios = data.get("scenarios", [])

        for raw in raw_scenarios:
            if not isinstance(raw, dict):
                continue
            scenarios.append(ScenarioPrediction(
                scenario_name=raw.get("scenario_name", "Bilinmeyen Senaryo"),
                description_tr=raw.get("description_tr", "Açıklama yok."),
                time_to_failure_min=float(raw.get("time_to_failure_min", 0)),
                probability=float(raw.get("probability", 0.33)),
                outcome=raw.get("outcome", ""),
            ))

        return scenarios

    def _create_local_scenarios(self, eta_predictions: list[ETAPrediction]) -> list[ScenarioPrediction]:
        """
        API olmadan yerel şablonlarla 3 senaryo üretir.

        Fabrika benzetmesi: Uzmana ulaşılamayınca planlama mühendisinin
        kendi başına "Ya şöyle olursa?" diye düşünmesi.
        """
        if not eta_predictions:
            return [
                ScenarioPrediction(
                    scenario_name="En iyi senaryo",
                    description_tr="Tüm sensörler stabil kalır, anormal durum gelişmez.",
                    time_to_failure_min=9999.0,
                    probability=0.25,
                    outcome="Makine normal çalışmaya devam eder.",
                ),
                ScenarioPrediction(
                    scenario_name="Orta senaryo",
                    description_tr="Küçük dalgalanmalar olur ama limit aşılmaz.",
                    time_to_failure_min=9999.0,
                    probability=0.50,
                    outcome="Standart bakım yeterli olur.",
                ),
                ScenarioPrediction(
                    scenario_name="En kötü senaryo",
                    description_tr="Beklenmedik bir sensörde anormallik başlar.",
                    time_to_failure_min=480.0,
                    probability=0.25,
                    outcome="8 saat içinde kontrol yapılması önerilir.",
                ),
            ]

        # En acil tahmine göre senaryoları ölçekle
        valid_etas = [e for e in eta_predictions if e.time_to_limit_min > 0]
        if not valid_etas:
            return self._create_local_scenarios([])

        base_time = min(e.time_to_limit_min for e in valid_etas)

        return [
            ScenarioPrediction(
                scenario_name="En iyi senaryo",
                description_tr="Trend yavaşlar, müdahale başarılı olur.",
                time_to_failure_min=round(base_time * 1.8, 1),
                probability=0.25,
                outcome="Müdahale başarılı, makine güvenle çalışmaya devam eder.",
            ),
            ScenarioPrediction(
                scenario_name="Orta senaryo",
                description_tr="Trend aynı hızda devam eder.",
                time_to_failure_min=round(base_time, 1),
                probability=0.50,
                outcome="Hesaplanan süre sonra kritik limit aşılır, bakım gerekir.",
            ),
            ScenarioPrediction(
                scenario_name="En kötü senaryo",
                description_tr="Trend hızlanır, zincirleme arıza riski artar.",
                time_to_failure_min=round(base_time * 0.6, 1),
                probability=0.25,
                outcome="Daha erken müdahale gerekebilir, acil durdurma planlayın.",
            ),
        ]

    # ─── LLM Çağrısı (Senkron — Async thread'de çalıştırılır) ────────────────

    def _call_llm_sync(self, prompt: str) -> str:
        """
        Gemini API'ye senkron çağrı yapar.
        DiagnosisAgent._call_llm_sync ile AYNI kalıbı kullanır.
        """
        if not self._ready:
            return self._init_error or "Tahmin Ajanı hazır değil."

        result_container: list[str] = [""]
        error_container: list[Exception | None] = [None]

        def _run() -> None:
            try:
                from google import genai
                from src.core.api_key_manager import get_api_key, record_api_usage, get_groq_api_key, record_groq_usage
                import groq

                # Her çağrıda yeni API key al
                current_key = get_api_key()

                # Yeni client oluştur
                client = genai.Client(api_key=current_key)

                response = client.models.generate_content(
                    model=self.MODEL_NAME,
                    contents=prompt,
                    config=genai.types.GenerateContentConfig(
                        system_instruction=_PREDICTION_SYSTEM_PROMPT,
                        temperature=0.3,
                        max_output_tokens=2048,
                    ),
                )
                result_container[0] = response.text.strip()

                # Başarılı request'i kaydet
                record_api_usage(success=True)
            except Exception as e:
                error_container[0] = e
                err_str = str(e)

                # Gemini hatası - Groq fallback dene
                if "429" in err_str or "quota" in err_str.lower():
                    log.warning("[PREDICTION] Gemini 429 hatası - Groq fallback deneniyor...")
                    try:
                        # Groq client
                        groq_key = get_groq_api_key()
                        groq_client = groq.Groq(api_key=groq_key)

                        groq_response = groq_client.chat.completions.create(
                            model='llama-3.3-70b-versatile',
                            messages=[
                                {"role": "system", "content": _PREDICTION_SYSTEM_PROMPT},
                                {"role": "user", "content": prompt}
                            ],
                            temperature=0.3,
                            max_tokens=4096,
                        )

                        result_container[0] = groq_response.choices[0].message.content.strip()
                        record_groq_usage(success=True)
                        log.info("[PREDICTION] Groq fallback başarılı!")
                        return  # Groq başarılı, çık

                    except Exception as groq_err:
                        log.exception("[PREDICTION] Groq fallback da başarısız: %s", groq_err)
                        record_groq_usage(success=False)
                        # Groq da başarısız, orijinal hatayı döndür

                # Hata durumunda da kaydet
                record_api_usage(success=False)

        worker = threading.Thread(target=_run, daemon=True)
        worker.start()
        worker.join(timeout=self.CALL_TIMEOUT_SEC)

        if worker.is_alive():
            log.warning("Gemini API timeout (%ds) — yanıt gelmedi.", self.CALL_TIMEOUT_SEC)
            return f"⏰ API zaman aşımı ({self.CALL_TIMEOUT_SEC}s). Lütfen tekrar deneyin."

        if error_container[0] is not None:
            err = error_container[0]
            err_str = str(err)
            log.exception("Gemini API hatası: %s", err_str)

            if "quota" in err_str.lower() or "429" in err_str:
                return "🚫 API kotası doldu. Groq fallback denendi ama başarısız oldu."
            elif "403" in err_str or "permission" in err_str.lower():
                return "🔑 API anahtarı geçersiz veya yetkisiz. Lütfen GEMINI_API_KEY'i kontrol edin."
            elif "network" in err_str.lower() or "connection" in err_str.lower():
                return "🌐 API bağlantı hatası. İnternet bağlantısını kontrol edin."
            else:
                return f"❌ API hatası: {err_str[:200]}"

        return result_container[0]

# ─── Dict Dönüşüm Yardımcısı ─────────────────────────────────────────────────


def prediction_result_to_dict(result: PredictionResult) -> dict:
    """
    PredictionResult'ı JSON-uyumlu dict'e çevirir (Enum'ları string yapar).

    Coordinator ve dashboard gibi JSON-serialize eden yerlerde kullanılır.
    """
    d = dataclasses.asdict(result)

    # PredictionConfidence enum değerlerini string'e çevir
    for eta in d.get("eta_predictions", []):
        conf = eta.get("confidence")
        if isinstance(conf, PredictionConfidence):
            eta["confidence"] = conf.value
        elif hasattr(conf, "value"):
            eta["confidence"] = conf.value

    return d


# ─── Singleton ────────────────────────────────────────────────────────────────
_prediction_instance: PredictionAgent | None = None
_prediction_lock = threading.Lock()


def get_prediction_agent() -> PredictionAgent:
    """
    Global Tahmin Ajanı örneğini döner (lazy init, thread-safe).

    Fabrika benzetmesi: Herkes aynı planlama mühendisine danışır.
    İlk çağrıda mühendis masasına oturur, sonrakiler aynı uzmana ulaşır.
    """
    global _prediction_instance
    with _prediction_lock:
        if _prediction_instance is None:
            _prediction_instance = PredictionAgent()
    return _prediction_instance
