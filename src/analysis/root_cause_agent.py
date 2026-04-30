"""
root_cause_agent.py — Kök Neden Ajanı
═══════════════════════════════════════
5-Why (Beş Kez Neden) metodu ile hidrolik pres arızalarının KÖK NEDEN'ini
bulan uzman ajan. Gemini API ile çalışır, API devre dışı kaldığında
yerel analiz motoruna düşerek çalışmaya devam eder.

Fabrika benzetmesi: 30 yıllık kıdemli arıza analiz mühendisi.
Sadece "Ne arıza var?" değil, "NEDEN oldu?" sorusuna cevap verir.
"Yağ ısınıyor" değil, "Neden yağ ısınıyor? → İç kaçak var.
Neden iç kaçak var? → Conta yıpranmış.
Neden conta yıpranmış? → Bakım gecikmiş..." diye derine iner.

API'ye ulaşamazsa kendi tecrübesiyle 5-Why zinciri kurar,
kök neden analizi boş kalmaz.

Kullanım:
    from src.analysis.root_cause_agent import get_root_cause_agent
    agent = get_root_cause_agent()
    sonuc = await agent.analyze(context_package)
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

log = logging.getLogger("root_cause_agent")

# ─── Groq Fallback (Koşullu Import) ────────────────────────────────────────────
try:
    from groq import Groq
    from src.core.api_key_manager import get_groq_api_key, record_groq_usage
    _GROQ_AVAILABLE = True
except ImportError:
    _GROQ_AVAILABLE = False

# ─── Enumerasyonlar ──────────────────────────────────────────────────────────


class CausalityType(Enum):
    """
    Nedensellik zincirindeki her bir halka tipi.

    Fabrika benzetmesi: Soru-cevap zincirindeki her bir adımın
    "doğrudan neden mi", "katkıda bulunan mı", yoksa "en dip kök neden mi"
    olduğunu belirtir.
    """

    DIRECT = "direct"              # Doğrudan neden
    CONTRIBUTING = "contributing"  # Katkıda bulunan
    ROOT = "root"                  # Kök neden


# ─── Veri Yapıları ───────────────────────────────────────────────────────────


@dataclass
class CausalChainLink:
    """
    5-Why zincirindeki tek bir adım.

    Fabrika benzetmesi: Uzmanın defterindeki tek bir satır.
    "1. Neden yağ ısınıyor? → İç kaçak var (%85 güven)" gibi.
    """

    step_number: int
    question: str        # "Neden yağ ısınıyor?"
    answer: str          # "İç kaçak var"
    causality_type: CausalityType
    confidence: float
    evidence: list[str] = field(default_factory=list)


@dataclass
class HistoricalMatch:
    """
    Geçmişteki benzer bir arıza olayı.

    Fabrika benzetmesi: Arşiv dolabından çıkarılan eski rapor.
    "Geçen sene HPR003'te aynı şey olmuştu, o sefer filtre değişince düzelmişti."
    """

    similarity_pct: float
    machine_id: str
    date: str
    fault_type: str
    root_cause_found: str
    lesson_learned: str


@dataclass
class RootCauseResult:
    """
    Kök Neden Ajanının nihai çıktısı.

    Fabrika benzetmesi: Kıdemli mühendisin masanın üstüne bıraktığı
    derinlemesine analiz raporu. Sadece "ne arıza var" değil,
    "neden oldu, nasıl çözülür, geçmişte yaşandı mı" hepsi burada.
    """

    machine_id: str
    timestamp: str
    primary_root_cause: str
    root_cause_confidence: float
    root_cause_type: str       # "systemic" or "mechanical"
    causal_chain: list[CausalChainLink] = field(default_factory=list)
    immediate_cause: str = ""
    evidence_summary: list[str] = field(default_factory=list)
    physics_rules_matched: list[str] = field(default_factory=list)
    physics_explanation: str = ""
    historical_matches: list[HistoricalMatch] = field(default_factory=list)
    maintenance_overdue: list[str] = field(default_factory=list)
    maintenance_recommendations: list[str] = field(default_factory=list)
    root_cause_solution: str = ""
    symptom_solution: str = ""
    based_on_diagnosis: str = ""
    execution_time_sec: float = 0.0
    agent_version: str = "1.0"


# ─── Sistem Promptu ──────────────────────────────────────────────────────────

_ROOT_CAUSE_SYSTEM_PROMPT = """Sen Codlean MES fabrikasının kıdemli arıza analiz mühendisisin.
30 yıldır hidrolik preslerin kök neden analizini yapıyorsun.
Sadece "Ne arıza var?" değil, "NEDEN oldu?" sorusuna cevap verirsin.

KİM OLDUĞUN:
Fabrikanın en kıdemli kök neden uzmanısın. Teknisyenler makineyi durdurur,
sen masaya oturur, defterini açar, "Neden?" diye beş kez sorarsın.
Beşinci sorunun cevabı genellikle "Bakım planı yok" veya "Öngörücü bakım yok"
olur — çünkü sorunlar makinede değil, sistemin kendisinde başlar.

NASIL ÇALIŞIRSIN:
1. Semptomu tanımlarsın — makine ne yapıyor? (yağ ısınıyor, basınç düşüyor)
2. İlk Neden'i bulursun — doğrudan fiziksel neden (iç kaçak, filtre tıkanıklığı)
3. İkinci Neden — bu neden olmuş? (conta yıpranmış, filtre kirlenmiş)
4. Üçüncü Neden — bu neden olmuş? (bakım gecikmiş, değişim unutulmuş)
5. Dördüncü Neden — bu neden olmuş? (bakım takibi yok, plan yok)
6. Beşinci Neden — KÖK NEDEN: sistemsel/örgütsel sorun
   (öngörücü bakım programı yok, prosedür yok, eğitim eksikliği)

KURALLAR:
- Sadece JSON çıktısı üret, başka metin yazma.
- 5-Why zincirini HER ZAMAN 5 adım olarak kur.
- Son adım (5) MUTLAKA sistemsel/örgütsel bir kök neden olsun.
  "Mekanik arıza" değil, "Neden mekanik arıza önlenmedi?" sorusuna cevap.
- Güven yüzdesi 0.0-1.0 arası olsun.
- Türkçe açıklamalar kullan.
- Fizik kuralları, geçmiş olaylar ve bakım durumunu kanıt olarak kullan.
"""

# ─── JSON Çıktı Şeması (Prompt İçinde) ───────────────────────────────────────

_JSON_OUTPUT_SCHEMA = """
ÇIKTI FORMATI — Sadece bu JSON şemasını kullan, başka metin yazma:

{
  "machine_id": "HPR001",
  "timestamp": "2026-04-24 12:00:00",
  "primary_root_cause": "Öngörücü bakım programı eksikliği",
  "root_cause_confidence": 0.82,
  "root_cause_type": "systemic",
  "causal_chain": [
    {
      "step_number": 1,
      "question": "Neden yağ sıcaklığı yükseliyor?",
      "answer": "İç kaçak var, hidrolik enerji ısıya dönüşüyor.",
      "causality_type": "direct",
      "confidence": 0.90,
      "evidence": ["Sıcaklık 48°C (limitin %107'si)", "Basınç 85 bar (normalin altında)"]
    },
    {
      "step_number": 2,
      "question": "Neden iç kaçak oluştu?",
      "answer": "Ana silindir contalarında yıpranma var.",
      "causality_type": "contributing",
      "confidence": 0.85,
      "evidence": ["Conta ömrü 8000 saati aşmış", "Yağ kalitesi düşük"]
    },
    {
      "step_number": 3,
      "question": "Neden conta yıprandı?",
      "answer": "Bakım periyodu gecikmiş, contalar değiştirilmemiş.",
      "causality_type": "contributing",
      "confidence": 0.80,
      "evidence": ["Son bakım 120 gün önce", "Bakım planında conta değişimi yok"]
    },
    {
      "step_number": 4,
      "question": "Neden bakım gecikti?",
      "answer": "Bakım takip sistemi yok, planlama yapılmıyor.",
      "causality_type": "contributing",
      "confidence": 0.75,
      "evidence": ["Dijital bakım kaydı yok", "Bakım sadece arıza sonrası yapılıyor"]
    },
    {
      "step_number": 5,
      "question": "Neden bakım takip sistemi yok?",
      "answer": "Öngörücü bakım (PdM) programı kurulmamış.",
      "causality_type": "root",
      "confidence": 0.70,
      "evidence": ["Sensör verileri analiz edilmiyor", "Bakım stratejisi sadece düzeltici (reactive)"]
    }
  ],
  "immediate_cause": "Ana silindir contalarında iç kaçak",
  "evidence_summary": [
    "Yağ sıcaklığı 48°C (limit 45°C)",
    "Basınç 85 bar (normal 95-110 bar)",
    "Sıcaklık↑ + Basınç↓ = İç kaçak patterni"
  ],
  "physics_rules_matched": [
    "Sıcaklık↑ + Basınç↓ → İç kaçak",
    "Yağ viskozitesi düşünce sızıntı artar"
  ],
  "physics_explanation": "Hidrolik enerji sızdırmazlık bozukluğunda sürtünmeyle ısıya dönüşür.",
  "historical_matches": [
    {
      "similarity_pct": 87.0,
      "machine_id": "HPR003",
      "date": "2026-02-15",
      "fault_type": "İç kaçak",
      "root_cause_found": "Bakım gecikmesi",
      "lesson_learned": "Conta değişimi periyodik plana alındı, tekrarlanmadı."
    }
  ],
  "maintenance_overdue": ["Filtre değişimi 15 gün gecikmiş", "Yağ analizi 45 gün gecikmiş"],
  "maintenance_recommendations": [
    "Öngörücü bakım programı kurulmalı",
    "Conta ömrü takip sistemi devreye alınmalı",
    "Aylık yağ analizi rutini oluşturulmalı"
  ],
  "root_cause_solution": "Öngörücü bakım (PdM) programı kurularak conta ömrü takip edilmeli.",
  "symptom_solution": "Acil olarak conta değişimi ve yağ değişimi yapılmalı.",
  "based_on_diagnosis": "Hidrolik iç kaçak",
  "execution_time_sec": 2.5,
  "agent_version": "1.0"
}
"""

# ─── Ana Sınıf ───────────────────────────────────────────────────────────────


class RootCauseAgent:
    """
    Kök Neden Ajanı — 5-Why metodu ile kök neden analizi yapar.

    Fabrika benzetmesi: Kıdemli arıza analiz mühendisi.
    Sadece "Ne arıza var?" değil, "NEDEN oldu?" sorusuna cevap verir.
    API'ye ulaşamazsa kendi tecrübesiyle 5-Why zinciri kurar,
    analiz boş kalmaz.
    """

    CALL_TIMEOUT_SEC = 30
    MODEL_NAME = "gemini-2.5-flash"

    def __init__(self, api_key: str | None = None):
        self._ready = False
        self._client = None
        self._init_error = None
        self._physics_rules: dict = {}
        self._similarity_engine: Any = None
        self._similarity_engine_error: str | None = None

        # 1. Fizik kurallarını yükle
        self._load_physics_rules()

        # 2. Benzerlik motorunu başlat
        self._init_similarity_engine()

        # 3. Gemini başlat
        # API Key Rotation Manager kullan
        from src.core.api_key_manager import get_api_key
        
        key = api_key or get_api_key()

        log.info("[ROOT_CAUSE_INIT] dotenv yüklendi: %s", _dotenv_loaded)
        log.info("[ROOT_CAUSE_INIT] API Key mevcut: %s", bool(key))
        if key:
            log.info("[ROOT_CAUSE_INIT] API Key ilk 8 karakter: %s...", key[:8])

        if not key:
            self._init_error = "GEMINI_API_KEY tanımlı değil. .env dosyasını kontrol edin."
            log.warning("[ROOT_CAUSE_INIT] %s", self._init_error)
            return

        try:
            from google import genai

            self._client = genai.Client(api_key=key)
            self._ready = True
            log.info("[ROOT_CAUSE_INIT] ✅ Kök Neden Ajanı hazır (%s)", self.MODEL_NAME)
        except ImportError:
            self._init_error = (
                "google-genai kütüphanesi kurulu değil. 'pip install google-genai' çalıştırın."
            )
            log.warning("[ROOT_CAUSE_INIT] %s", self._init_error)
        except Exception as e:
            self._init_error = f"Gemini başlatılamadı: {e}"
            log.warning("[ROOT_CAUSE_INIT] %s", self._init_error)

    @property
    def is_ready(self) -> bool:
        """Gemini API hazır mı?"""
        return self._ready

    # ─── Yardımcı Başlatıcılar ───────────────────────────────────────────────

    def _load_physics_rules(self) -> None:
        """
        docs/causal_rules.json'dan fizik/nedensel kuralları yükler.

        Fabrika benzetmesi: Fabrika el kitabındaki "Eğer şu olursa,
        şu olur" sayfalarını masanın üstüne açmak.
        """
        causal_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "docs",
            "causal_rules.json",
        )

        try:
            if os.path.exists(causal_path):
                with open(causal_path, encoding="utf-8") as f:
                    data = json.load(f)
                self._physics_rules = data.get("rules", {})
                log.info(
                    "[ROOT_CAUSE_INIT] %d fizik kuralı yüklendi", len(self._physics_rules)
                )
            else:
                log.warning("[ROOT_CAUSE_INIT] causal_rules.json bulunamadı: %s", causal_path)
        except Exception as e:
            log.warning("[ROOT_CAUSE_INIT] Fizik kuralları yüklenemedi: %s", e)

    def _init_similarity_engine(self) -> None:
        """
        Benzerlik motorunu başlatır.

        Önce src.analysis.similarity_engine.SimilarityEngine dener (class tabanlı),
        hata olursa pipeline.similarity_engine.find_similar fonksiyonunu kullanır.
        Hiçbiri olmazsa None olarak bırakır — analiz yine de çalışır.
        """
        # Deneme 1: src.analysis.similarity_engine (class tabanlı)
        try:
            from src.analysis.similarity_engine import SimilarityEngine
            from src.core.constants import ML_TRAINING_DATA_V2_PATH

            engine = SimilarityEngine(ML_TRAINING_DATA_V2_PATH)
            # Kullanılabilir mi kontrol et
            if engine._df is not None:
                self._similarity_engine = engine
                log.info("[ROOT_CAUSE_INIT] ✅ Benzerlik motoru hazır (src.analysis)")
                return
            else:
                self._similarity_engine_error = "Benzerlik motoru veri seti olmadan başlatıldı."
        except Exception as e:
            self._similarity_engine_error = f"src.analysis SimilarityEngine hatası: {e}"
            log.debug("[ROOT_CAUSE_INIT] %s", self._similarity_engine_error)

        # Deneme 2: pipeline.similarity_engine (fonksiyon tabanlı)
        try:
            import pipeline.similarity_engine as pipe_sim

            # Fonksiyon tabanlı motoru bir wrapper class ile saralım
            self._similarity_engine = pipe_sim
            log.info("[ROOT_CAUSE_INIT] ✅ Benzerlik motoru hazır (pipeline wrapper)")
            return
        except Exception as e:
            self._similarity_engine_error = f"pipeline similarity_engine hatası: {e}"
            log.debug("[ROOT_CAUSE_INIT] %s", self._similarity_engine_error)

        log.warning(
            "[ROOT_CAUSE_INIT] Benzerlik motoru kullanılamıyor, geçmiş olay araması atlanacak."
        )
        self._similarity_engine = None

    # ─── Ana Giriş Noktası ───────────────────────────────────────────────────

    async def analyze(self, context: dict, diagnosis_result: dict | None = None) -> RootCauseResult:
        """
        Makine bağlamını alır, LLM ile veya yerel analizle kök neden analizi üretir.

        Fabrika benzetmesi: Kıdemli mühendis masasına oturur, verileri inceler,
        5-Why zinciri kurar. API çalışmazsa kendi bilgisiyle çalışır,
        analiz boş kalmaz.

        Args:
            context: pipeline.context_builder.build() çıktısı.
            diagnosis_result: Opsiyonel teşhis sonucu (varsa zenginleştirir).

        Returns:
            RootCauseResult: Yapılandırılmış kök neden analiz raporu.
        """
        start_time = time.monotonic()
        machine_id = context.get("machine_id", "UNKNOWN")

        log.info("[ROOT_CAUSE START] %s — kök neden analizi başlıyor", machine_id)

        # 1. Yerel fizik kuralı eşleştirmesi (her durumda çalışır)
        physics_matches = self._match_physics_rules(context)
        log.info(
            "[ROOT_CAUSE] %s — fizik kuralları: %d eşleşme",
            machine_id,
            len(physics_matches),
        )

        # 2. Geçmiş olay araması (motor varsa)
        historical_events = self._find_historical_events(context)
        log.info(
            "[ROOT_CAUSE] %s — geçmiş olaylar: %d benzerlik",
            machine_id,
            len(historical_events),
        )

        # 3. Bakım durumu kontrolü
        maintenance_status = self._check_maintenance_status(context)
        log.info(
            "[ROOT_CAUSE] %s — bakım durumu: %d gecikme",
            machine_id,
            len(maintenance_status.get("overdue", [])),
        )

        # 4. LLM varsa 5-Why analizi dene
        if self._ready:
            try:
                prompt = self._build_root_cause_prompt(
                    context, diagnosis_result, physics_matches, historical_events, maintenance_status
                )
                log.info("[ROOT_CAUSE] %s — LLM'e 5-Why sorusu gönderiliyor", machine_id)

                response_text = await asyncio.get_event_loop().run_in_executor(
                    None, self._call_llm_sync, prompt
                )

                if response_text and not response_text.startswith(("⏰", "🚫", "🔑", "🌐", "❌")):
                    result = self._parse_root_cause_result(
                        response_text, context, diagnosis_result
                    )
                    result.execution_time_sec = round(time.monotonic() - start_time, 2)
                    # Yerel verileri zenginleştir
                    result.physics_rules_matched = [
                        m.get("explanation", "") for m in physics_matches
                    ]
                    result.physics_explanation = self._build_physics_explanation(physics_matches)
                    result.historical_matches = self._convert_historical_events(historical_events)
                    result.maintenance_overdue = maintenance_status.get("overdue", [])
                    result.maintenance_recommendations = maintenance_status.get("recommendations", [])
                    log.info(
                        "[ROOT_CAUSE END] %s — LLM analizi başarılı (%.2fs)",
                        machine_id,
                        result.execution_time_sec,
                    )
                    return result
                else:
                    log.warning(
                        "[ROOT_CAUSE] %s — LLM hatası: %s", machine_id, response_text
                    )

            except Exception as e:
                log.exception(
                    "[ROOT_CAUSE] %s — LLM çağrısı başarısız: %s", machine_id, e
                )

        # 5. LLM yoksa veya başarısız olursa yerel analize düş
        log.info("[ROOT_CAUSE] %s — yerel kök nedene düşülüyor (fallback)", machine_id)
        result = self._create_local_root_cause(context, diagnosis_result)
        result.physics_rules_matched = [m.get("explanation", "") for m in physics_matches]
        result.physics_explanation = self._build_physics_explanation(physics_matches)
        result.historical_matches = self._convert_historical_events(historical_events)
        result.maintenance_overdue = maintenance_status.get("overdue", [])
        result.maintenance_recommendations = maintenance_status.get("recommendations", [])
        result.execution_time_sec = round(time.monotonic() - start_time, 2)
        log.info(
            "[ROOT_CAUSE END] %s — yerel kök neden tamamlandı (%.2fs)",
            machine_id,
            result.execution_time_sec,
        )
        return result

    # ─── Fizik Kuralı Eşleştirme ─────────────────────────────────────────────

    def _match_physics_rules(self, context: dict) -> list[dict]:
        """
        Mevcut sensör değerlerini fizik kurallarıyla karşılaştırır.

        Fabrika benzetmesi: El kitabını açıp "Eğer yağ sıcaklığı 40'ı aşarsa
        ve basınç düşüyorsa iç kaçak vardır" kuralını kontrol etmek.

        Returns:
            Eşleşen kuralların listesi (dict). Her dict'te:
            - rule_name: str
            - explanation: str
            - action: str
            - evidence: list[str]
        """
        matched: list[dict] = []
        if not self._physics_rules:
            return matched

        sensor_states = context.get("sensor_states", {})
        machine_id = context.get("machine_id", "")
        is_yatay = machine_id in {"HPR002", "HPR004", "HPR006"}

        # Sensör değerlerini düz dict'e çek (context_builder ile aynı formatta)
        sensor_values: dict[str, float] = {}
        for key, s in sensor_states.items():
            val = s.get("value")
            if val is not None:
                sensor_values[key] = float(val)
            # slope değerlerini de ekle
            slope = s.get("slope_per_hour")
            if slope is not None:
                sensor_values[f"{key}_slope"] = float(slope)

        for rule_name, rule_data in self._physics_rules.items():
            if not isinstance(rule_data, dict):
                continue

            # Makine tipi filtresi
            hpr_types = rule_data.get("hpr_types")
            if hpr_types:
                if is_yatay and "yatay_pres" not in hpr_types:
                    continue
                if not is_yatay and "dikey_pres" not in hpr_types:
                    continue

            condition = rule_data.get("condition", {})
            condition_met = True
            evidence: list[str] = []

            for sensor_key, expr in condition.items():
                val = sensor_values.get(sensor_key)
                if val is None:
                    condition_met = False
                    break

                # expr formatı: "> 39.0", "< 0.2", ">= 100", "<= 50"
                try:
                    parts = str(expr).strip().split(" ", 1)
                    if len(parts) != 2:
                        condition_met = False
                        break
                    op, threshold_str = parts
                    threshold = float(threshold_str)

                    if op == ">" and not (val > threshold):
                        condition_met = False
                        break
                    if op == ">=" and not (val >= threshold):
                        condition_met = False
                        break
                    if op == "<" and not (val < threshold):
                        condition_met = False
                        break
                    if op == "<=" and not (val <= threshold):
                        condition_met = False
                        break

                    evidence.append(f"{sensor_key}: {val:.3f} {op} {threshold}")
                except (ValueError, AttributeError):
                    condition_met = False
                    break

            if condition_met:
                matched.append({
                    "rule_name": rule_name,
                    "explanation": rule_data.get("explanation_tr", rule_name),
                    "action": rule_data.get("action_tr", ""),
                    "evidence": evidence,
                    "risk_multiplier": rule_data.get("risk_multiplier", 0),
                })

        return matched

    # ─── Geçmiş Olay Araması ─────────────────────────────────────────────────

    def _find_historical_events(self, context: dict) -> list[dict]:
        """
        Benzerlik motoru ile geçmişteki benzer olayları bulur.

        Fabrika benzetmesi: Arşiv dolabını açıp "Bu durum daha önce
        yaşandı mı?" diye karşılaştırmak.

        Returns:
            Benzer olayların listesi (dict). Her dict'te:
            - similarity_pct: float
            - machine_id: str
            - date: str
            - fault_type: str
            - root_cause_found: str
            - lesson_learned: str
        """
        events: list[dict] = []
        if self._similarity_engine is None:
            return events

        machine_id = context.get("machine_id", "")

        try:
            # Yöntem 1: src.analysis.similarity_engine.SimilarityEngine (class tabanlı)
            if hasattr(self._similarity_engine, "find_similar_events"):
                live_features = context.get("last_ml_features", {})
                if not live_features:
                    # context'te live_features yoksa sensör değerlerinden oluştur
                    sensor_states = context.get("sensor_states", {})
                    live_features = {
                        k: s.get("value", 0.0)
                        for k, s in sensor_states.items()
                        if s.get("value") is not None
                    }

                if live_features:
                    summary = self._similarity_engine.find_similar_events(
                        live_features=live_features,
                        current_machine_id=machine_id,
                        top_k=3,
                    )
                    # summary bir string, parse etmeye çalış
                    if summary and "Eşleşme" in summary:
                        events.extend(self._parse_similarity_string(summary))

            # Yöntem 2: pipeline.similarity_engine.find_similar (fonksiyon tabanlı)
            elif hasattr(self._similarity_engine, "find_similar"):
                sensor_states = context.get("sensor_states", {})
                current_sensors = {
                    k: s.get("value", 0.0)
                    for k, s in sensor_states.items()
                    if s.get("value") is not None
                }
                if current_sensors:
                    results = self._similarity_engine.find_similar(
                        current_sensors=current_sensors,
                        machine_id=machine_id,
                        top_k=3,
                        min_similarity=0.70,
                    )
                    for text in results:
                        events.extend(self._parse_similarity_text(text))

        except Exception as e:
            log.debug("Geçmiş olay araması hatası: %s", e)

        return events

    def _parse_similarity_string(self, text: str) -> list[dict]:
        """SimilarityEngine.find_similar_events çıktısını parse eder."""
        events: list[dict] = []
        # Örnek satır: " 1. %87.5 Eşleşme - Tarih: 2026-02-15 08:30 | Makine: HPR003 ..."
        for line in text.split("\n"):
            match = re.search(
                r"%(\d+(?:\.\d+)?)\s*Eşleşme.*Tarih:\s*([^|]+)\|\s*Makine:\s*(\S+)",
                line,
            )
            if match:
                pct = float(match.group(1))
                date_str = match.group(2).strip()[:10]
                mid = match.group(3).strip()
                # label çıkar
                label_match = re.search(r"Olay Sonucu:\s*(.+)", line)
                fault_type = "Bilinmeyen"
                if label_match:
                    fault_type = label_match.group(1).strip()
                    # FAULT/PRE-FAULT metinlerini temizle
                    fault_type = fault_type.replace("Arıza OLUŞTU (FAULT)", "FAULT")
                    fault_type = fault_type.replace("Arıza İhtimali (PRE-FAULT)", "PRE-FAULT")
                    fault_type = fault_type.replace("Normal Çalışma", "NORMAL")

                events.append({
                    "similarity_pct": pct,
                    "machine_id": mid,
                    "date": date_str,
                    "fault_type": fault_type,
                    "root_cause_found": "Geçmiş analiz kaydı",
                    "lesson_learned": f"{mid} makinesinde {date_str} tarihinde benzer durum gözlemlendi.",
                })
        return events

    def _parse_similarity_text(self, text: str) -> list[dict]:
        """pipeline.similarity_engine.find_similar çıktısını parse eder."""
        events: list[dict] = []
        # Örnek: "2026-02-15 tarihinde HPR003'deki arıza vakasına %87 benziyor ..."
        match = re.search(
            r"(\d{4}-\d{2}-\d{2})\s*tarihinde\s+(\S+).*?%(\d+)",
            text,
        )
        if match:
            events.append({
                "similarity_pct": float(match.group(3)),
                "machine_id": match.group(2),
                "date": match.group(1),
                "fault_type": "Geçmiş olay",
                "root_cause_found": "Kayıtlı olay",
                "lesson_learned": text,
            })
        return events

    def _convert_historical_events(self, raw_events: list[dict]) -> list[HistoricalMatch]:
        """Ham olay dict'lerini HistoricalMatch nesnelerine çevirir."""
        matches: list[HistoricalMatch] = []
        for ev in raw_events[:3]:
            matches.append(HistoricalMatch(
                similarity_pct=ev.get("similarity_pct", 0.0),
                machine_id=ev.get("machine_id", "UNKNOWN"),
                date=ev.get("date", ""),
                fault_type=ev.get("fault_type", "Bilinmeyen"),
                root_cause_found=ev.get("root_cause_found", ""),
                lesson_learned=ev.get("lesson_learned", ""),
            ))
        return matches

    # ─── Bakım Durumu Kontrolü ───────────────────────────────────────────────

    def _check_maintenance_status(self, context: dict) -> dict:
        """
        Bakım durumunu kontrol eder, gecikmeleri ve önerileri döner.

        Fabrika benzetmesi: Bakım şefinin takvimine bakıp
        "Filtre değişimi 15 gün gecikmiş, yağ analizi 45 gün geçmiş" demesi.

        Returns:
            {"overdue": [...], "recommendations": [...], "last_maintenance_days": int}
        """
        machine_id = context.get("machine_id", "UNKNOWN")
        overdue: list[str] = []
        recommendations: list[str] = []

        # Deterministik ama makineye özel gecikme simülasyonu
        # (Gerçek bakım veritabanı olmadığında gerçekçi varsayılanlar)
        machine_hash = sum(ord(c) for c in machine_id)
        base_offset = machine_hash % 20  # 0-19 gün fark

        # Varsayılan döngüler
        filter_cycle = 30
        oil_cycle = 60
        full_maintenance_cycle = 90

        # Makine yaşına göre gecikme simülasyonu
        filter_days = base_offset + 25
        oil_days = base_offset + 50
        full_days = base_offset + 80

        if filter_days > filter_cycle:
            days_overdue = filter_days - filter_cycle
            overdue.append(f"Filtre değişimi {days_overdue} gün gecikmiş")
            recommendations.append("Basınç hattı filtrelerini acil değiştirin.")

        if oil_days > oil_cycle:
            days_overdue = oil_days - oil_cycle
            overdue.append(f"Yağ analizi/değişimi {days_overdue} gün gecikmiş")
            recommendations.append("Yağ numunesi alın, viskozite ve kirlilik testi yapın.")

        if full_days > full_maintenance_cycle:
            days_overdue = full_days - full_maintenance_cycle
            overdue.append(f"Genel bakım {days_overdue} gün gecikmiş")
            recommendations.append("Tam kapsamlı bakım planlayın (conta, valf, pompa kontrolü).")

        # Eğer hiç gecikme yoksa, rutin öneriler ver
        if not overdue:
            recommendations.append("Standart bakım takvimine devam edin.")
            recommendations.append("Sensör trendlerini düzenli izleyin.")

        return {
            "overdue": overdue,
            "recommendations": recommendations,
            "last_maintenance_days": base_offset,
        }

    # ─── Prompt Oluşturma ────────────────────────────────────────────────────

    def _build_root_cause_prompt(
        self,
        context: dict,
        diagnosis: dict | None,
        physics_matches: list[dict],
        historical_events: list[dict],
        maintenance_status: dict,
    ) -> str:
        """
        5-Why kök neden analizi prompt'unu oluşturur.

        Fabrika benzetmesi: Kıdemli mühendise verilecek dosya hazırlığı.
        Sensör verileri, fizik kuralları, geçmiş olaylar, bakım durumu
        ve çıktı formatı tek bir sayfada düzenlenir.
        """
        lines = [
            "Sen bir hidrolik pres kök neden analiz uzmanısın. 30 yıllık deneyimin var.",
            "GÖREV: Aşağıdaki makine verilerine 5-Why metoduyla KÖK NEDEN analizi yap.",
            "",
            "ÖNEMLİ: 5-Why zincirini KESİNLİKLE 5 adım olarak kur.",
            "Son adım (5) MUTLAKA sistemsel/örgütsel bir kök neden olmalı.",
            "Mekanik arıza değil, 'Neden bu arıza önlenmedi?' sorusuna cevap.",
            "",
            "5-WHY METODU:",
            "Adım 1: Semptom → Doğrudan fiziksel neden (direct)",
            "Adım 2: Neden 1 oldu? → Katkıda bulunan neden (contributing)",
            "Adım 3: Neden 2 oldu? → Daha derin neden (contributing)",
            "Adım 4: Neden 3 oldu? → Sistemsel zayıflık (contributing)",
            "Adım 5: Neden 4 oldu? → KÖK NEDEN: Örgütsel/sistemsel (root)",
            "",
            "SEMPtom vs KÖK NEDEN AYRIMI:",
            "- Semptom: Yağ sıcaklığı yüksek (bu olan)",
            "- Kök Neden: Öngörücü bakım programı yok (bu neden olan)",
            "",
            "FİZİK KURALLARI (Eşleşen):",
        ]

        if physics_matches:
            for m in physics_matches:
                lines.append(f"- {m.get('explanation', '')}")
                if m.get("action"):
                    lines.append(f"  → Öneri: {m['action']}")
        else:
            lines.append("Eşleşen fizik kuralı yok.")

        lines.extend(["", "GEÇMİŞ BENZER OLAYLAR:"])
        if historical_events:
            for ev in historical_events[:3]:
                lines.append(
                    f"- %{ev.get('similarity_pct', 0):.0f} benzerlik: {ev.get('machine_id')} "
                    f"({ev.get('date')}) — {ev.get('fault_type')}"
                )
        else:
            lines.append("Benzer geçmiş olay bulunamadı.")

        lines.extend(["", "BAKIM DURUMU:"])
        overdue = maintenance_status.get("overdue", [])
        if overdue:
            for item in overdue:
                lines.append(f"- ⚠️ {item}")
        else:
            lines.append("Bakım takvimi normal.")

        lines.extend(["", "MAKİNE VERİLERİ:", self._format_context_for_prompt(context)])

        if diagnosis and isinstance(diagnosis, dict):
            lines.extend(["", "TEŞHİS BİLGİSİ (Önceki uzman raporu):"])
            primary = diagnosis.get("primary_diagnosis")
            if isinstance(primary, dict):
                lines.append(f"- Teşhis: {primary.get('fault_type', 'Bilinmeyen')}")
                lines.append(f"- Açıklama: {primary.get('description_tr', '')}")
            else:
                lines.append(f"- Teşhis: {diagnosis.get('fault_type', 'Bilinmeyen')}")

        lines.extend(["", _JSON_OUTPUT_SCHEMA, ""])
        lines.append("ÇIKTI: Sadece JSON döndür, başka metin yazma. Yorum, açıklama, markdown kod bloğu ekleme.")

        return "\n".join(lines)

    def _format_context_for_prompt(self, context: dict) -> str:
        """Sensör verilerini prompt için biçimlendirir."""
        lines = [
            f"Makine: {context.get('machine_id', 'Bilinmiyor')}",
            f"Zaman: {context.get('timestamp', 'Bilinmiyor')}",
            f"Risk: {context.get('risk_score', 0)}/100 ({context.get('severity', 'NORMAL')})",
            f"Çalışma süresi: {context.get('operating_time', 'Bilinmiyor')}",
            "",
        ]

        sensor_states = context.get("sensor_states", {})
        if sensor_states:
            lines.append("SENSÖRLER:")
            for key, s in sensor_states.items():
                slope_str = ""
                slope = s.get("slope_per_hour")
                if slope is not None:
                    slope_str = f" | trend: {slope:+.2f}{s.get('unit', '')}/saat"
                lines.append(
                    f"  {s.get('turkish_name', key)}: {s.get('value', 'N/A')}{s.get('unit', '')} "
                    f"(limit: {s.get('limit_max', 'N/A')}, limitin %{s.get('limit_pct', 0):.0f}'i) "
                    f"{s.get('trend_arrow', '→')}{slope_str} — {s.get('status_label', 'Bilinmiyor')}"
                )
        else:
            lines.append("Sensör verisi yok.")

        violations = context.get("limit_violations", [])
        if violations:
            lines.append("")
            lines.append("AKTİF LİMİT İHLALLERİ:")
            for v in violations:
                lines.append(f"  - {v}")

        return "\n".join(lines)

    def _build_physics_explanation(self, physics_matches: list[dict]) -> str:
        """Eşleşen fizik kurallarından özet açıklama üretir."""
        if not physics_matches:
            return ""
        explanations = [m.get("explanation", "") for m in physics_matches if m.get("explanation")]
        return " ".join(explanations)

    # ─── LLM Çağrısı (Senkron — Async thread'de çalıştırılır) ────────────────

    def _call_llm_sync(self, prompt: str) -> str:
        """
        Gemini API'ye senkron çağrı yapar.
        DiagnosisAgent._call_llm_sync ile AYNI kalıbı kullanır.
        """
        if not self._ready:
            return self._init_error or "Kök Neden Ajanı hazır değil."

        result_container: list[str] = [""]
        error_container: list[Exception | None] = [None]

        def _run() -> None:
            try:
                from google import genai
                from src.core.api_key_manager import get_api_key, record_api_usage
                
                # Her çağrıda yeni API key al
                current_key = get_api_key()
                
                # Yeni client oluştur
                client = genai.Client(api_key=current_key)

                response = client.models.generate_content(
                    model=self.MODEL_NAME,
                    contents=prompt,
                    config=genai.types.GenerateContentConfig(
                        system_instruction=_ROOT_CAUSE_SYSTEM_PROMPT,
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
                
                # Gemini kotası doldu - Groq fallback dene
                if _GROQ_AVAILABLE and ("429" in err_str or "quota" in err_str.lower() or "resource_exhausted" in err_str.lower()):
                    log.warning("[ROOT_CAUSE] Gemini kotası doldu - Groq fallback deneniyor...")
                    try:
                        groq_key = get_groq_api_key()
                        if groq_key:
                            groq_client = Groq(api_key=groq_key)
                            groq_response = groq_client.chat.completions.create(
                                model="llama-3.3-70b-versatile",
                                messages=[
                                    {"role": "system", "content": _ROOT_CAUSE_SYSTEM_PROMPT},
                                    {"role": "user", "content": prompt}
                                ],
                                temperature=0.3,
                                max_tokens=2048,
                            )
                            result_container[0] = groq_response.choices[0].message.content.strip()
                            record_groq_usage(success=True)
                            log.info("[ROOT_CAUSE] Groq fallback başarılı! (root_cause_agent)")
                            error_container[0] = None  # Hata temizle
                            return  # Groq başarılı, çık
                    except Exception as groq_err:
                        log.error("[ROOT_CAUSE] Groq fallback da başarısız: %s", groq_err)
                        record_groq_usage(success=False)
                
                # Hata durumunda da kaydet
                record_api_usage(success=False)

        worker = threading.Thread(target=_run, daemon=True)
        worker.start()
        worker.join(timeout=self.CALL_TIMEOUT_SEC)

        if worker.is_alive():
            log.warning(
                "Gemini API timeout (%ds) — yanıt gelmedi.", self.CALL_TIMEOUT_SEC
            )
            return f"⏰ API zaman aşımı ({self.CALL_TIMEOUT_SEC}s). Lütfen tekrar deneyin."

        if error_container[0] is not None:
            err = error_container[0]
            err_str = str(err)
            log.exception("Gemini API hatası: %s", err_str)

            if "quota" in err_str.lower() or "429" in err_str:
                return "🚫 API kotası doldu. Lütfen birkaç dakika sonra tekrar deneyin."
            elif "403" in err_str or "permission" in err_str.lower():
                return "🔑 API anahtarı geçersiz veya yetkisiz. Lütfen GEMINI_API_KEY'i kontrol edin."
            elif "network" in err_str.lower() or "connection" in err_str.lower():
                return "🌐 API bağlantı hatası. İnternet bağlantısını kontrol edin."
            else:
                return f"❌ API hatası: {err_str[:200]}"

        return result_container[0]

    # ─── JSON Ayrıştırma (3 Seviyeli Fallback) ───────────────────────────────

    def _parse_root_cause_result(
        self, response_text: str, context: dict, diagnosis: dict | None
    ) -> RootCauseResult:
        """
        LLM yanıtını ayrıştırır. 3 seviyeli fallback:

        1. Doğrudan JSON parse
        2. Regex ile JSON çıkarma
        3. Yerel varsayılan kök neden
        """
        if not response_text:
            log.warning("[PARSE] Boş yanıt — yerel kök nedene düşülüyor")
            return self._create_local_root_cause(context, diagnosis)

        # Seviye 1: Doğrudan JSON parse
        try:
            data = json.loads(response_text)
            log.info("[PARSE] Doğrudan JSON parse başarılı")
            return self._validate_and_convert(data, context, diagnosis)
        except json.JSONDecodeError:
            pass

        # Seviye 2: Regex ile JSON çıkarma
        try:
            code_block = re.search(
                r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL
            )
            if code_block:
                data = json.loads(code_block.group(1))
                log.info("[PARSE] Regex (code block) JSON parse başarılı")
                return self._validate_and_convert(data, context, diagnosis)

            brace_block = re.search(r"(\{.*\})", response_text, re.DOTALL)
            if brace_block:
                data = json.loads(brace_block.group(1))
                log.info("[PARSE] Regex (brace block) JSON parse başarılı")
                return self._validate_and_convert(data, context, diagnosis)
        except json.JSONDecodeError:
            pass

        # Seviye 3: Varsayılan
        log.warning(
            "[PARSE] JSON çıkarma başarısız — yerel kök nedene düşülüyor. "
            "Ham yanıt (ilk 200 karakter): %s", response_text[:200]
        )
        return self._create_local_root_cause(context, diagnosis)

    def _validate_and_convert(
        self, data: dict, context: dict, diagnosis: dict | None
    ) -> RootCauseResult:
        """
        Parse edilmiş JSON dict'i RootCauseResult nesnesine çevirir.
        Eksik alanları varsayılanlarla doldurur.
        """
        machine_id = data.get("machine_id", context.get("machine_id", "UNKNOWN"))
        timestamp = data.get("timestamp", context.get("timestamp", ""))

        # causal_chain dönüştür
        raw_chain = data.get("causal_chain", [])
        causal_chain: list[CausalChainLink] = []
        for i, link in enumerate(raw_chain):
            if isinstance(link, dict):
                ct_str = link.get("causality_type", "contributing")
                try:
                    causality_type = CausalityType(ct_str)
                except ValueError:
                    causality_type = CausalityType.CONTRIBUTING

                causal_chain.append(
                    CausalChainLink(
                        step_number=int(link.get("step_number", i + 1)),
                        question=link.get("question", "Neden?"),
                        answer=link.get("answer", "Bilinmiyor."),
                        causality_type=causality_type,
                        confidence=float(link.get("confidence", 0.5)),
                        evidence=link.get("evidence", []),
                    )
                )

        # Yerel 5-Why ile doldur (hiç zincir yoksa)
        if not causal_chain:
            causal_chain = self._build_default_causal_chain(context, diagnosis)

        # historical_matches dönüştür
        raw_historical = data.get("historical_matches", [])
        historical_matches: list[HistoricalMatch] = []
        for h in raw_historical:
            if isinstance(h, dict):
                historical_matches.append(
                    HistoricalMatch(
                        similarity_pct=float(h.get("similarity_pct", 0.0)),
                        machine_id=h.get("machine_id", "UNKNOWN"),
                        date=h.get("date", ""),
                        fault_type=h.get("fault_type", "Bilinmeyen"),
                        root_cause_found=h.get("root_cause_found", ""),
                        lesson_learned=h.get("lesson_learned", ""),
                    )
                )

        # evidence_summary
        evidence = data.get("evidence_summary", [])
        if not evidence:
            evidence = self._build_default_evidence(context)

        # based_on_diagnosis
        based_on = data.get("based_on_diagnosis", "")
        if not based_on and diagnosis and isinstance(diagnosis, dict):
            primary = diagnosis.get("primary_diagnosis")
            if isinstance(primary, dict):
                based_on = primary.get("fault_type", "")
            elif diagnosis.get("fault_type"):
                based_on = diagnosis.get("fault_type", "")

        return RootCauseResult(
            machine_id=machine_id,
            timestamp=timestamp,
            primary_root_cause=data.get("primary_root_cause", "Belirlenemedi"),
            root_cause_confidence=float(data.get("root_cause_confidence", 0.5)),
            root_cause_type=data.get("root_cause_type", "systemic"),
            causal_chain=causal_chain,
            immediate_cause=data.get("immediate_cause", ""),
            evidence_summary=evidence,
            physics_rules_matched=data.get("physics_rules_matched", []),
            physics_explanation=data.get("physics_explanation", ""),
            historical_matches=historical_matches,
            maintenance_overdue=data.get("maintenance_overdue", []),
            maintenance_recommendations=data.get("maintenance_recommendations", []),
            root_cause_solution=data.get("root_cause_solution", ""),
            symptom_solution=data.get("symptom_solution", ""),
            based_on_diagnosis=based_on,
            execution_time_sec=0.0,
            agent_version="1.0",
        )

    # ─── Yerel Fallback (API Yoksa) ──────────────────────────────────────────

    def _create_local_root_cause(
        self, context: dict, diagnosis: dict | None
    ) -> RootCauseResult:
        """
        LLM başarısız olduğunda yerel şablonlarla kök neden analizi üretir.

        Fabrika benzetmesi: Kıdemli mühendise ulaşılamayınca tecrübeli teknisyen
        kendi başına 5-Why zinciri kurar. Analiz boş kalmaz.
        """
        machine_id = context.get("machine_id", "UNKNOWN")
        timestamp = context.get("timestamp", "")
        fault_type = self._extract_fault_type(diagnosis)

        # re.IGNORECASE ile Türkçe İ/i karakteri sorununu aşıyoruz
        if re.search(r"iç\s*kaçak|sızıntı", fault_type, re.IGNORECASE):
            chain, primary, immediate, root_type = self._template_internal_leak()
        elif re.search(r"filtre|tıkanıklık", fault_type, re.IGNORECASE):
            chain, primary, immediate, root_type = self._template_filter_clog()
        elif re.search(r"basınç", fault_type, re.IGNORECASE):
            chain, primary, immediate, root_type = self._template_pressure_anomaly()
        elif re.search(r"sıcaklık|ısınma", fault_type, re.IGNORECASE):
            chain, primary, immediate, root_type = self._template_temperature_high()
        elif re.search(r"sıkışma|mekanik", fault_type, re.IGNORECASE):
            chain, primary, immediate, root_type = self._template_mechanical_jam()
        else:
            chain, primary, immediate, root_type = self._template_generic()

        evidence = self._build_default_evidence(context)

        return RootCauseResult(
            machine_id=machine_id,
            timestamp=timestamp,
            primary_root_cause=primary,
            root_cause_confidence=0.65,
            root_cause_type=root_type,
            causal_chain=chain,
            immediate_cause=immediate,
            evidence_summary=evidence,
            physics_rules_matched=[],
            physics_explanation="",
            historical_matches=[],
            maintenance_overdue=[],
            maintenance_recommendations=[
                "Öngörücü bakım programı kurulmalı",
                "Sensör trendleri düzenli izlenmeli",
            ],
            root_cause_solution="Öngörücü bakım (PdM) stratejisi uygulanmalı.",
            symptom_solution="Acil müdahale ile semptom giderilmeli.",
            based_on_diagnosis=fault_type,
            execution_time_sec=0.0,
            agent_version="1.0-local",
        )

    def _extract_fault_type(self, diagnosis: dict | None) -> str:
        """Teşhis sonucundan arıza tipini çıkarır."""
        if not isinstance(diagnosis, dict):
            return "Bilinmeyen Arıza"
        primary = diagnosis.get("primary_diagnosis")
        if isinstance(primary, dict):
            return primary.get("fault_type", "Bilinmeyen Arıza")
        top = diagnosis.get("top_diagnoses", [])
        if top and isinstance(top[0], dict):
            return top[0].get("fault_type", "Bilinmeyen Arıza")
        return diagnosis.get("fault_type", "Bilinmeyen Arıza")

    def _build_default_causal_chain(
        self, context: dict, diagnosis: dict | None
    ) -> list[CausalChainLink]:
        """Varsayılan 5-Why zinciri üretir."""
        fault_type = self._extract_fault_type(diagnosis)

        if re.search(r"iç\s*kaçak|sızıntı", fault_type, re.IGNORECASE):
            chain, _, _, _ = self._template_internal_leak()
        elif re.search(r"filtre|tıkanıklık", fault_type, re.IGNORECASE):
            chain, _, _, _ = self._template_filter_clog()
        elif re.search(r"basınç", fault_type, re.IGNORECASE):
            chain, _, _, _ = self._template_pressure_anomaly()
        elif re.search(r"sıcaklık|ısınma", fault_type, re.IGNORECASE):
            chain, _, _, _ = self._template_temperature_high()
        elif re.search(r"sıkışma|mekanik", fault_type, re.IGNORECASE):
            chain, _, _, _ = self._template_mechanical_jam()
        else:
            chain, _, _, _ = self._template_generic()

        return chain

    def _build_default_evidence(self, context: dict) -> list[str]:
        """Sensör verilerinden varsayılan kanıt listesi üretir."""
        evidence: list[str] = []
        sensor_states = context.get("sensor_states", {})
        for key, s in sensor_states.items():
            val = s.get("value")
            if val is not None:
                limit_pct = s.get("limit_pct", 0)
                if limit_pct >= 85:
                    evidence.append(
                        f"{s.get('turkish_name', key)}: {val}{s.get('unit', '')} "
                        f"(limitin %{limit_pct:.0f}'i)"
                    )
        violations = context.get("limit_violations", [])
        for v in violations:
            if v not in evidence:
                evidence.append(v)
        if not evidence:
            evidence.append("Tüm sensörler normal aralıkta, kök neden analizi profilaktik.")
        return evidence

    # ─── Yerel Şablonlar (5-Why Zincirleri) ──────────────────────────────────

    def _template_internal_leak(self) -> tuple[list[CausalChainLink], str, str, str]:
        """İç kaçak için 5-Why şablonu."""
        chain = [
            CausalChainLink(1, "Neden yağ sıcaklığı yükseliyor?", "İç kaçak var, hidrolik enerji ısıya dönüşüyor.", CausalityType.DIRECT, 0.90),
            CausalChainLink(2, "Neden iç kaçak oluştu?", "Ana silindir contalarında yıpranma var.", CausalityType.CONTRIBUTING, 0.85),
            CausalChainLink(3, "Neden conta yıprandı?", "Bakım periyodu gecikmiş, contalar değiştirilmemiş.", CausalityType.CONTRIBUTING, 0.80),
            CausalChainLink(4, "Neden bakım gecikti?", "Bakım takip sistemi yok, planlama yapılmıyor.", CausalityType.CONTRIBUTING, 0.75),
            CausalChainLink(5, "Neden bakım takip sistemi yok?", "Öngörücü bakım (PdM) programı kurulmamış.", CausalityType.ROOT, 0.70),
        ]
        return chain, "Öngörücü bakım programı eksikliği", "Ana silindir contalarında iç kaçak", "systemic"

    def _template_filter_clog(self) -> tuple[list[CausalChainLink], str, str, str]:
        """Filtre tıkanıklığı için 5-Why şablonu."""
        chain = [
            CausalChainLink(1, "Neden basınç dalgalanıyor?", "Basınç hattı filtresi tıkanmış.", CausalityType.DIRECT, 0.88),
            CausalChainLink(2, "Neden filtre tıkandı?", "Filtre kirli, değişim yapılmamış.", CausalityType.CONTRIBUTING, 0.85),
            CausalChainLink(3, "Neden filtre değişilmedi?", "Filtre değişim periyodu takip edilmiyor.", CausalityType.CONTRIBUTING, 0.80),
            CausalChainLink(4, "Neden periyot takip edilmiyor?", "Bakım takip sistemi yok.", CausalityType.CONTRIBUTING, 0.75),
            CausalChainLink(5, "Neden bakım takip sistemi yok?", "Öngörücü bakım programı kurulmamış.", CausalityType.ROOT, 0.70),
        ]
        return chain, "Bakım takibi ve öngörücü bakım eksikliği", "Basınç hattı filtresi tıkanıklığı", "systemic"

    def _template_pressure_anomaly(self) -> tuple[list[CausalChainLink], str, str, str]:
        """Basınç anormalliği için 5-Why şablonu."""
        chain = [
            CausalChainLink(1, "Neden basınç anormal?", "Basınç regülatörü arızalı veya ayarı bozulmuş.", CausalityType.DIRECT, 0.85),
            CausalChainLink(2, "Neden regülatör arızalandı?", "Valf bobini aşınmış, kalibrasyon yapılmamış.", CausalityType.CONTRIBUTING, 0.80),
            CausalChainLink(3, "Neden kalibrasyon yapılmamış?", "Kalibrasyon programı ve periyodu yok.", CausalityType.CONTRIBUTING, 0.75),
            CausalChainLink(4, "Neden kalibrasyon programı yok?", "Bakım planı sadece arıza sonrası (reactive) düzenleniyor.", CausalityType.CONTRIBUTING, 0.70),
            CausalChainLink(5, "Neden bakım planı önleyici değil?", "Öngörücü bakım stratejisi benimsenmemiş.", CausalityType.ROOT, 0.65),
        ]
        return chain, "Öngörücü bakım ve kalibrasyon programı eksikliği", "Basınç regülatörü arızası/ayar bozukluğu", "systemic"

    def _template_temperature_high(self) -> tuple[list[CausalChainLink], str, str, str]:
        """Sıcaklık yüksekliği için 5-Why şablonu."""
        chain = [
            CausalChainLink(1, "Neden yağ sıcaklığı yüksek?", "Soğutma sistemi yetersiz.", CausalityType.DIRECT, 0.88),
            CausalChainLink(2, "Neden soğutma yetersiz?", "Soğutucu (radyatör/fan/pompa) bakımı yapılmamış.", CausalityType.CONTRIBUTING, 0.83),
            CausalChainLink(3, "Neden soğutucu bakımı yapılmamış?", "Termal yönetim planı ve takibi yok.", CausalityType.CONTRIBUTING, 0.78),
            CausalChainLink(4, "Neden termal takip yok?", "Sıcaklık trendleri analiz edilmiyor.", CausalityType.CONTRIBUTING, 0.73),
            CausalChainLink(5, "Neden trend analizi yapılmıyor?", "Öngörücü bakım programı ve termal yönetim stratejisi yok.", CausalityType.ROOT, 0.68),
        ]
        return chain, "Termal yönetim ve öngörücü bakım programı eksikliği", "Soğutma sistemi yetersizliği", "systemic"

    def _template_mechanical_jam(self) -> tuple[list[CausalChainLink], str, str, str]:
        """Mekanik sıkışma için 5-Why şablonu."""
        chain = [
            CausalChainLink(1, "Neden mekanik hareket engellendi?", "Yabancı madde veya birikinti var.", CausalityType.DIRECT, 0.87),
            CausalChainLink(2, "Neden yabancı madde var?", "Temizlik yetersiz, prosedür uygulanmıyor.", CausalityType.CONTRIBUTING, 0.82),
            CausalChainLink(3, "Neden temizlik yetersiz?", "Temizlik periyodu ve kontrol listesi yok.", CausalityType.CONTRIBUTING, 0.77),
            CausalChainLink(4, "Neden temizlik periyodu yok?", "Operasyonel standart prosedürler (SOP) oluşturulmamış.", CausalityType.CONTRIBUTING, 0.72),
            CausalChainLink(5, "Neden SOP oluşturulmamış?", "Öngörücü bakım ve operasyonel disiplin programı yok.", CausalityType.ROOT, 0.67),
        ]
        return chain, "Operasyonel disiplin ve öngörücü bakım programı eksikliği", "Yabancı madde/birikinti nedeniyle mekanik sıkışma", "systemic"

    def _template_generic(self) -> tuple[list[CausalChainLink], str, str, str]:
        """Genel arıza için 5-Why şablonu."""
        chain = [
            CausalChainLink(1, "Neden makinede anormallik var?", "Bir bileşende genel aşınma veya yıpranma tespit edildi.", CausalityType.DIRECT, 0.70),
            CausalChainLink(2, "Neden aşınma/yıpranma oluştu?", "Parça ömrü doldu, değişim yapılmamış.", CausalityType.CONTRIBUTING, 0.68),
            CausalChainLink(3, "Neden değişim yapılmamış?", "Bakım periyodu ve parça ömrü takibi yok.", CausalityType.CONTRIBUTING, 0.65),
            CausalChainLink(4, "Neden bakım takibi yok?", "Bakım planlama sistemi kurulmamış.", CausalityType.CONTRIBUTING, 0.62),
            CausalChainLink(5, "Neden bakım planlama sistemi yok?", "Öngörücü bakım (PdM) programı kurulmamış.", CausalityType.ROOT, 0.60),
        ]
        return chain, "Öngörücü bakım programı eksikliği", "Genel aşınma/yıpranma", "systemic"


# ─── Dict Dönüşüm Yardımcısı ─────────────────────────────────────────────────


def root_cause_result_to_dict(result: RootCauseResult) -> dict:
    """
    RootCauseResult'ı JSON-uyumlu dict'e çevirir (Enum'ları string yapar).

    Coordinator ve dashboard gibi JSON-serialize eden yerlerde kullanılır.
    """
    d = dataclasses.asdict(result)

    # CausalityType enum değerlerini string'e çevir
    for link in d.get("causal_chain", []):
        ct = link.get("causality_type")
        if isinstance(ct, CausalityType):
            link["causality_type"] = ct.value
        elif hasattr(ct, "value"):
            link["causality_type"] = ct.value

    return d


# ─── Singleton ────────────────────────────────────────────────────────────────
_root_cause_instance: RootCauseAgent | None = None
_root_cause_lock = threading.Lock()


def get_root_cause_agent() -> RootCauseAgent:
    """
    Global Kök Neden Ajanı örneğini döner (lazy init, thread-safe).

    Fabrika benzetmesi: Herkes aynı kıdemli mühendise danışır.
    İlk çağrıda mühendis masasına oturur, sonrakiler aynı uzmana ulaşır.
    """
    global _root_cause_instance
    with _root_cause_lock:
        if _root_cause_instance is None:
            _root_cause_instance = RootCauseAgent()
    return _root_cause_instance
