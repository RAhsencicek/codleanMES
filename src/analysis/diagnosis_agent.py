"""
diagnosis_agent.py — Teşhis Ajanı
═══════════════════════════════════
Chain-of-Thought (Adım Adım Düşünme) yöntemiyle hidrolik pres arızalarını
teşhis eden uzman ajan. Gemini API ile çalışır, API devre dışı kaldığında
yerel analiz motoruna düşerek çalışmaya devam eder.

Fabrika benzetmesi: 20 yıllık kıdemli arıza teşhis mühendisi.
Makineye bakar, sensörleri analiz eder, adım adım düşünerek teşhis koyar.
API'ye ulaşamazsa kendi tecrübesiyle değerlendirir, teşhis boş kalmaz.

Kullanım:
    from src.analysis.diagnosis_agent import get_diagnosis_agent
    agent = get_diagnosis_agent()
    sonuc = await agent.diagnose(context_package)
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

log = logging.getLogger("diagnosis_agent")

# ─── Veri Yapıları ───────────────────────────────────────────────────────────


@dataclass
class SensorAnomaly:
    """
    Tek bir sensördeki anormalliği tanımlar.

    Fabrika benzetmesi: Bir gösterge panosundaki tek bir ibrenin durumu.
    Normalde kaçta durması gerektiği, şu an kaçta olduğu,
    ne yöne doğru hareket ettiği.
    """

    sensor_name: str        # "oil_tank_temperature"
    current_value: float    # 48.0
    normal_value: float     # 32.0
    deviation_pct: float    # +50.0
    trend: str              # "increasing", "decreasing", "stable"
    slope_per_hour: float   # +8.0
    status: str             # "critical", "warning", "normal"
    description_tr: str = ""  # Detaylı sensör açıklaması (Türkçe)


@dataclass
class DiagnosisCandidate:
    """
    Olası bir arıza teşhisini tanımlar.

    Fabrika benzetmesi: Şüpheli arıza listesindeki bir satır.
    "Büyük ihtimalle bu, şu sensörler buna işaret ediyor,
     yapmanız gereken şu."
    """

    rank: int               # 1, 2, 3
    fault_type: str         # "Hidrolik iç kaçak"
    confidence: float       # 0.82
    description_tr: str     # Turkish description
    supporting_sensors: list[str]
    evidence: list[str]
    recommended_action: str
    severity: str = ""              # "CRITICAL", "HIGH", "MEDIUM", "LOW"
    category_tr: str = ""           # "Hidrolik", "Mekanik", "Elektrik", "Termal", "Kontrol"
    root_cause_analysis_tr: str = ""  # 5-Why detaylı kök neden analizi


@dataclass
class DiagnosisResult:
    """
    Teşhis ajanının nihai çıktısı.

    Fabrika benzetmesi: Uzmanın masanın üstüne bıraktığı teşhis raporu.
    Makine kimliği, zaman, veri kalitesi, bulunan anormallikler,
    en olası 3 arıza, birincil teşhis ve düşünme adımları.
    """

    machine_id: str
    timestamp: str
    data_quality: str       # "reliable", "suspicious", "unreliable"
    data_quality_notes: list[str]
    anomaly_pattern: str    # "slow_trend", "sudden_change", "periodic", "none"
    pattern_description_tr: str
    sensor_anomalies: dict  # {sensor_name: SensorAnomaly}
    top_diagnoses: list     # List[DiagnosisCandidate], max 3
    primary_diagnosis: object  # DiagnosisCandidate or None
    reasoning_steps: list[str]
    execution_time_sec: float
    agent_version: str = "1.0"
    immediate_actions_tr: list[str] = field(default_factory=list)
    maintenance_recommendations_tr: list[str] = field(default_factory=list)
    eta_to_failure: str = ""
    production_impact_tr: str = ""
    confidence_notes_tr: str = ""


# ─── Sistem Promptu ──────────────────────────────────────────────────────────

_DIAGNOSIS_SYSTEM_PROMPT = "Sen hidrolik pres arıza teşhis uzmanısın. 20+ yıllık saha deneyimin var. Her makinenin sesinden, titreşiminden, yağ kokusundan arızayı anlarsın."

# ─── JSON Çıktı Şeması (Prompt İçinde) ───────────────────────────────────────

_FORMAT_SCHEMA = """{
  "machine_id": "HPR001",
  "timestamp": "2026-04-29 18:30:00",
  "data_quality": "reliable|degraded|unreliable",
  "data_quality_notes": ["Veri kalitesi hakkında notlar..."],
  "anomaly_pattern": "thermal_runaway|pressure_decay|mechanical_jam|normal|other",
  "pattern_description_tr": "Tespit edilen pattern'in detaylı açıklaması (3-5 cümle)...",
  "sensor_anomalies": {
    "sensor_key": {
      "value": 0.0,
      "limit": 0.0,
      "deviation_pct": 0.0,
      "status": "critical|warning|normal",
      "description_tr": "Bu sensörün durumu ve anlamı (2-3 cümle)..."
    }
  },
  "top_diagnoses": [
    {
      "description_tr": "Teşhis: Detaylı açıklama (5-8 cümle). Kök neden, etkilenen sistemler, risk seviyesi...",
      "confidence": 0.95,
      "severity": "CRITICAL|HIGH|MEDIUM|LOW",
      "category_tr": "Hidrolik|Mekanik|Elektrik|Termal|Kontrol",
      "root_cause_analysis_tr": "5-Why metodunun detaylı sonucu (5-7 cümle)..."
    }
  ],
  "primary_diagnosis": {
    "description_tr": "ANA TEŞHİS: En olası arızanın KAPSAMLI açıklaması (10-15 cümle)...",
    "confidence": 0.92,
    "severity": "CRITICAL|HIGH|MEDIUM|LOW",
    "category_tr": "Hidrolik|Mekanik|Elektrik|Termal|Kontrol",
    "root_cause_analysis_tr": "Kök neden analizi detaylı (7-10 cümle)..."
  },
  "immediate_actions_tr": [
    "ACİL 1: Şu anda yapılması gereken (detaylı açıklama)",
    "ACİL 2: İkinci öncelikli aksiyon (detaylı açıklama)"
  ],
  "maintenance_recommendations_tr": [
    "KISA VADELİ: Bugün yapılması gerekenler (detaylı)",
    "UZUN VADELİ: Bu hafta planlanması gerekenler (detaylı)"
  ],
  "eta_to_failure": "Tahmini arıza süresi (örn: '2-4 saat', '1-2 gün', 'Bilinmiyor')",
  "production_impact_tr": "Üretim etkisi açıklaması (3-5 cümle)...",
  "confidence_notes_tr": "Bu teşhisin güven seviyesi neden bu kadar? (3-5 cümle)",
  "reasoning_steps": ["Adım 1: ...", "Adım 2: ...", "Adım 3: ...", "Adım 4: ...", "Adım 5: ...", "Adım 6: ..."]
}"""

# ─── Ana Sınıf ───────────────────────────────────────────────────────────────


class DiagnosisAgent:
    """
    Teşhis Ajanı — Chain-of-Thought ile arıza teşhisi koyar.

    Fabrika benzetmesi: Kıdemli arıza teşhis mühendisi.
    Makineye bakar, sensörleri analiz eder, adım adım düşünerek teşhis koyar.
    Uzmana ulaşılamazsa (API kapalıysa) kendi bilgisiyle teşhis üretir,
    makine teşhissiz kalmaz.
    """

    # FIX: Gemini API için maksimum bekleme süresi
    CALL_TIMEOUT_SEC = 30
    MODEL_NAME = "gemini-2.5-flash"

    def __init__(self, api_key: str | None = None):
        self._ready = False
        self._client = None
        self._init_error = None

        # API Key Rotation Manager kullan
        from src.core.api_key_manager import get_api_key
        
        key = api_key or get_api_key()

        log.info("[DIAGNOSIS_INIT] dotenv yüklendi: %s", _dotenv_loaded)
        log.info("[DIAGNOSIS_INIT] API Key mevcut: %s", bool(key))
        if key:
            log.info("[DIAGNOSIS_INIT] API Key ilk 8 karakter: %s...", key[:8])

        if not key:
            self._init_error = "GEMINI_API_KEY tanımlı değil. .env dosyasını kontrol edin."
            log.warning("[DIAGNOSIS_INIT] %s", self._init_error)
            return

        try:
            from google import genai

            self._client = genai.Client(api_key=key)
            self._ready = True
            log.info("[DIAGNOSIS_INIT] ✅ Teşhis Ajanı hazır (%s)", self.MODEL_NAME)
        except ImportError:
            self._init_error = (
                "google-genai kütüphanesi kurulu değil. 'pip install google-genai' çalıştırın."
            )
            log.warning("[DIAGNOSIS_INIT] %s", self._init_error)
        except Exception as e:
            self._init_error = f"Gemini başlatılamadı: {e}"
            log.warning("[DIAGNOSIS_INIT] %s", self._init_error)

    @property
    def is_ready(self) -> bool:
        """Gemini API hazır mı?"""
        return self._ready

    # ─── Ana Giriş Noktası ───────────────────────────────────────────────────

    async def diagnose(self, context: dict) -> DiagnosisResult:
        """
        Makine bağlamını alır, LLM ile veya yerel analizle teşhis üretir.

        Fabrika benzetmesi: Uzman masasına oturur, verileri inceler,
        teşhis raporu hazırlar. API çalışmazsa kendi bilgisiyle çalışır,
        makine asla teşhissiz kalmaz.

        Args:
            context: pipeline.context_builder.build() çıktısı.

        Returns:
            DiagnosisResult: Yapılandırılmış teşhis raporu.
        """
        start_time = time.monotonic()
        machine_id = context.get("machine_id", "UNKNOWN")

        log.info("[DIAGNOSE START] %s — teşhis başlıyor", machine_id)

        # 1. Yerel anormallik tespiti (her durumda çalışır — zenginleştirme için)
        local_anomalies = self._detect_anomalies_locally(context)
        log.info(
            "[DIAGNOSE] %s — yerel analiz: %d sensör değerlendirildi, %d anomali",
            machine_id,
            len(local_anomalies),
            sum(1 for a in local_anomalies.values() if a.status in ("critical", "warning")),
        )

        # 2. LLM varsa Chain-of-Thought teşhis dene
        if self._ready:
            try:
                prompt = self._build_diagnosis_prompt(context)
                log.info("[DIAGNOSE] %s — LLM'e teşhis sorusu gönderiliyor", machine_id)

                # Senkron LLM çağrısını async olarak çalıştır (thread havuzunda)
                response_text = await asyncio.get_event_loop().run_in_executor(
                    None, self._call_llm_sync, prompt
                )

                # Hata mesajı değilse (emoji ile başlayanlar hata mesajıdır)
                if response_text and not response_text.startswith(("⏰", "🚫", "🔑", "🌐", "❌")):
                    result = self._parse_diagnosis_result(response_text, context)
                    result.execution_time_sec = round(time.monotonic() - start_time, 2)
                    log.info(
                        "[DIAGNOSE END] %s — LLM teşhisi başarılı (%.2fs)",
                        machine_id,
                        result.execution_time_sec,
                    )
                    return result
                else:
                    log.warning(
                        "[DIAGNOSE] %s — LLM hatası: %s", machine_id, response_text
                    )

            except Exception as e:
                log.exception(
                    "[DIAGNOSE] %s — LLM çağrısı başarısız: %s", machine_id, e
                )

        # 3. LLM yoksa veya başarısız olursa yerel teşhise düş
        log.info("[DIAGNOSE] %s — yerel teşhise düşülüyor (fallback)", machine_id)
        result = self._default_diagnosis(context, local_anomalies)
        result.execution_time_sec = round(time.monotonic() - start_time, 2)
        log.info(
            "[DIAGNOSE END] %s — yerel teşhis tamamlandı (%.2fs)",
            machine_id,
            result.execution_time_sec,
        )
        return result

    # ─── LLM Çağrısı (Senkron — Async thread'de çalıştırılır) ────────────────

    def _call_llm_sync(self, prompt: str) -> str:
        """
        Gemini API'ye senkron çağrı yapar.

        UstaBasi._call ile AYNI kalıbı kullanır:
        - google.genai Client
        - GenerateContentConfig(system_instruction, temperature, max_output_tokens)
        - threading.Thread + join(timeout)
        - Kota, yetki, ağ hatalarını ayırt eder.

        Args:
            prompt: Gemini'ye gönderilecek tam metin.

        Returns:
            API yanıt metni veya hata mesajı (emoji ile başlar).
        """
        if not self._ready:
            return self._init_error or "Teşhis Ajanı hazır değil."

        result_container: list[str] = [""]
        error_container: list[Exception | None] = [None]

        def _run() -> None:
            try:
                from google import genai
                from src.core.api_key_manager import get_api_key, record_api_usage, get_groq_api_key, record_groq_usage
                import groq
                
                # Her çağrıda yeni API key al
                current_key = get_api_key()
                
                # Yeni client oluştur (her request için)
                client = genai.Client(api_key=current_key)

                response = client.models.generate_content(
                    model=self.MODEL_NAME,
                    contents=prompt,
                    config=genai.types.GenerateContentConfig(
                        system_instruction=_DIAGNOSIS_SYSTEM_PROMPT,
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
                if "429" in err_str or "quota" in err_str.lower() or "resource_exhausted" in err_str.lower():
                    log.warning("[DIAGNOSIS] Gemini kotası doldu - Groq fallback deneniyor...")
                    try:
                        # Groq client
                        groq_key = get_groq_api_key()
                        print(f"[GROQ DEBUG] Key alınıyor: {groq_key[:20]}...")
                        groq_client = groq.Groq(api_key=groq_key)
                        
                        print(f"[GROQ DEBUG] Model: llama-3.3-70b-versatile")
                        groq_response = groq_client.chat.completions.create(
                            model='llama-3.3-70b-versatile',
                            messages=[
                                {"role": "system", "content": _DIAGNOSIS_SYSTEM_PROMPT},
                                {"role": "user", "content": prompt}
                            ],
                            temperature=0.3,
                            max_tokens=4096,
                        )
                        
                        result_container[0] = groq_response.choices[0].message.content.strip()
                        record_groq_usage(success=True)
                        log.info("[DIAGNOSIS] Groq fallback başarılı!")
                        print(f"[GROQ DEBUG] Başarılı! Yanıt uzunluğu: {len(result_container[0])}")
                        return  # Groq başarılı, çık
                        
                    except Exception as groq_err:
                        log.exception("[DIAGNOSIS] Groq fallback da başarısız: %s", groq_err)
                        print(f"[GROQ DEBUG] HATA: {groq_err}")
                        record_groq_usage(success=False)
                        # Groq da başarısız, orijinal hatayı döndür
                
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
                return "🚫 API kotası doldu. Groq fallback denendi ama başarısız oldu."
            elif "403" in err_str or "permission" in err_str.lower():
                return "🔑 API anahtarı geçersiz veya yetkisiz. Lütfen GEMINI_API_KEY'i kontrol edin."
            elif "network" in err_str.lower() or "connection" in err_str.lower():
                return "🌐 API bağlantı hatası. İnternet bağlantısını kontrol edin."
            else:
                return f"❌ API hatası: {err_str[:200]}"

        return result_container[0]

    # ─── Prompt Oluşturma ────────────────────────────────────────────────────

    def _build_diagnosis_prompt(self, context: dict) -> str:
        """
        Chain-of-Thought prompt'unu oluşturur.

        Fabrika benzetmesi: Uzmana verilecek dosya hazırlığı.
        Sensör verileri, nedensel kurallar ve çıktı formatı tek bir
        sayfada düzenlenir ki uzman tek bakışta durumu kavrasın.
        """
        format_schema = _FORMAT_SCHEMA

        prompt = """GÖREV: Aşağıdaki sensör verilerini analiz et ve DETAYLI teşhis raporu hazırla.

══════════════════════════════════════════════════════
ANALİZ METODOLOJİSİ (MUTLAKA SIRAYLA TAMAMLA)
══════════════════════════════════════════════════════

ADIM 1 — VERİ DOĞRULAMA:
• Hangi sensörler normal aralıkta?
• Hangi sensörler kritik/uyarı bölgesinde?
• Değerler fiziksel olarak mantıklı mı? (ör: basınç 0 ama makine çalışıyor → sensör arızası)
• Makine durduğunda 0.0 değerler NORMALDIR, arıza sayma!
• CNC kodu ve operasyon bilgisi var mı? (varsa üretim bağlamını değerlendir)

ADIM 2 — ANORMALLİK TESPİTİ:
Her sensör için:
- Ani değişim (1-2 dakika içinde) → Mekanik arıza, valf sıkışması
- Yavaş trend (saatler içinde) → Aşınma, tıkanma, bozulma
- Periyodik dalgalanma → Çevresel etki, sıcaklık değişimi
- Stabil → Normal çalışma

ADIM 3 — NEDENSEL İLİŞKİLER (EN KRİTİK ADIM):
Şu kalıpları ara:
• Sıcaklık ↑ + Basınç ↓ = İç kaçak (enerji ısıya dönüşüyor)
• Basınç ↑ + Hız ↓ = Sıkışma, mekanik direnç
• Basınç ↓ + Hız ↓ = Pompa zayıflaması veya kaçak
• Sıcaklık normal + Basınç dalgalanması = Valf arızası veya hava kabarcığı
• Tüm değerler düşük = Makine yüklenmiyor veya idle

ADIM 4 — KÖK NEDEN ANALİZİ (5-WHY METODU):
Her bulgu için "neden?" sorusunu 3-5 kez tekrarla.
Örnek:
  1. Yağ sıcaklığı yüksek → Neden?
  2. Soğutma yetersiz → Neden?
  3. Soğutucu tıkanmış → Neden?
  4. Bakım yapılmamış → KÖK NEDEN: Planlı bakım eksikliği

ADIM 5 — RİSK DEĞERLENDİRME:
• KRİTİK: 30 dakika içinde makine durabilir, üretim kaybı riski
• YÜKSEK: 2-4 saat içinde arıza büyüyebilir, acil müdahale gerekli
• ORTA: 1-2 gün içinde kontrol edilmeli, izleme yeterli
• DÜŞÜK: Normal çalışma, periyodik kontrol yeterli

ADIM 6 — AKSİYON PLANI:
Her sorun için:
1. ACİL MÜDAHALE (şimdi yapılması gereken): "Makineyi durdur", "Vana 3'ü kontrol et"
2. KISA VADELİ (bugün): "Filtreyi değiştir", "Yağ seviyesini kontrol et"
3. UZUN VADELİ (bu hafta): "Pompa revizyonu planla", "Sensör kalibrasyonu yap"

══════════════════════════════════════════════════════
ÇIKTI FORMATI (MUTLAKA BU YAPIDA YANITLA)
══════════════════════════════════════════════════════

{format_schema}

══════════════════════════════════════════════════════
KALİTE KRİTERLERİ (BUNLARA UYMAZSAN YANIT REDDEDİLİR)
══════════════════════════════════════════════════════

✅ YAPILMASI GEREKENLER:
• description_tr alanları EN AZ 5 cümle olmalı (primary_diagnosis için 10-15 cümle)
• Fiziksel mekanizmaları açıkla (NEDEN oluyor, nasıl etki ediyor)
• Sensörler arası ilişkileri kur (X artınca Y neden düşüyor)
• Somut sayılar ver ("48°C — limitin 3°C üstünde")
• Kök neden analizini derinlemesine yap (yüzeysel kalma)
• Üretim etkisini hesapla (duruş süresi, maliyet)
• Gerçekçi zaman tahminleri ver

❌ ASLA YAPMA:
• "Normal çalışma", "Veri yok" gibi kısa yanıtlar (EN AZ 5 cümle yaz!)
• "Bilinmiyor", "Belirsiz" gibi kaçamak cevaplar
• Sadece sensör değerlerini tekrarlamak (yorum ekle!)
• Yüzeysel teşhisler (derinlemesine analiz yap)
• Maddeler halinde kısa cevaplar (paragraf halinde, akıcı yaz)

══════════════════════════════════════════════════════
ÖNEMLİ HATIRLATMALAR
══════════════════════════════════════════════════════

1. Makine DURMUŞSA (CNC=IDLE veya sensörler 0):
   → "Makine şu an çalışmıyor. Tüm değerler 0. Bu normaldir, arıza değildir."
   → Ama geçmiş veride anormallik varsa: "Makine durmuş ama durmadan önce X sorun vardı..."

2. Yatay presler (HPR002/004/006):
   → Yağ sıcaklığı sensörü YOK! Bundan bahsetme.

3. CNC kodu ve operasyon varsa:
   → Üretim bağlamını değerlendir (örn: "Bu operasyon yüksek basınç gerektiriyor...")

4. Benzer geçmiş olaylar varsa:
   → "Bu pattern daha önce [tarih] görülmüştü, o zaman [sonuç]..."

ŞİMDİ VERİLERİ ANALİZ ET VE YUKARIDAKİ FORMATTA DETAYLI YANITLA:

{context_data}"""

        return prompt.format(format_schema=format_schema, context_data=self._format_context_for_prompt(context))

    def _load_causal_rules_for_prompt(self, context: dict) -> list[str]:
        """
        docs/causal_rules.json'dan ilgili kuralları yükler.

        Fabrika benzetmesi: Fabrika el kitabındaki "Eğer şu olursa,
        şu yapın" sayfalarından makine tipine uygun olanları seçmek.
        """
        rules_lines = []
        machine_id = context.get("machine_id", "")
        is_yatay = machine_id in {"HPR002", "HPR004", "HPR006"}

        causal_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "docs",
            "causal_rules.json",
        )

        try:
            if os.path.exists(causal_path):
                with open(causal_path, encoding="utf-8") as f:
                    data = json.load(f)
                rules = data.get("rules", {})

                for rule_name, rule_data in rules.items():
                    if not isinstance(rule_data, dict):
                        continue

                    # Makine tipi filtresi
                    hpr_types = rule_data.get("hpr_types")
                    if hpr_types:
                        if is_yatay and "yatay_pres" not in hpr_types:
                            continue
                        if not is_yatay and "dikey_pres" not in hpr_types:
                            continue

                    explanation = rule_data.get("explanation_tr", rule_name)
                    action = rule_data.get("action_tr", "")
                    rules_lines.append(f"- {explanation}")
                    if action:
                        rules_lines.append(f"  → Öneri: {action}")

        except Exception as e:
            log.warning("Nedensel kurallar yüklenemedi: %s", e)

        # Hiç kural yoksa veya dosya yoksa varsayılan kurallar
        if not rules_lines:
            rules_lines = [
                "- Sıcaklık↑ + Basınç↓ → İç kaçak (sızdırmazlık bozukluğu)",
                "- Basınç↑ + Hız≈0 → Mekanik sıkışma",
                "- Sıcaklık↑ + Hız↓ → Yağ viskozitesi düşüklüğü / aşırı sürtünme",
                "- Basınç dalgalanması + Filtre kirli → Filtre tıkanıklığı",
            ]

        return rules_lines

    def _format_context_for_prompt(self, context: dict) -> str:
        """
        Sensör verilerini prompt için biçimlendirir.

        Fabrika benzetmesi: Uzmanın önüne konan sensör tablosu.
        Her satırda sensör adı, değeri, limiti, limitin yüzde kaçı,
        trend yönü ve saatlik eğimi net şekilde yazar.
        """
        lines = [
            f"Makine: {context.get('machine_id', 'Bilinmiyor')}",
            f"Zaman: {context.get('timestamp', 'Bilinmiyor')}",
            f"Risk: {context.get('risk_score', 0)}/100 ({context.get('severity', 'NORMAL')})",
            f"Çalışma süresi: {context.get('operating_time', 'Bilinmiyor')}",
            f"Güven: %{context.get('confidence', 0)}",
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

        # Limit ihlalleri
        violations = context.get("limit_violations", [])
        if violations:
            lines.append("")
            lines.append("AKTİF LİMİT İHLALLERİ:")
            for v in violations:
                lines.append(f"  - {v}")

        # Kritik yaklaşan sensörler
        critical = context.get("critical_sensors", [])
        if critical:
            lines.append("")
            lines.append("KRİTİK YAKLAŞIM:")
            for c in critical:
                lines.append(f"  - {c}")

        # ETA tahminleri
        etas = context.get("eta_predictions", {})
        if etas:
            lines.append("")
            lines.append("LİMİTE KALAN SÜRE TAHMİNİ:")
            for eta in etas.values():
                lines.append(
                    f"  {eta.get('sensor_name')}: ~{eta.get('eta_minutes')} dakika "
                    f"(şu an {eta.get('current_value')}{eta.get('unit', '')})"
                )

        # Aktif fizik kuralları
        physics = context.get("active_physics_rules", [])
        if physics:
            lines.append("")
            lines.append("TETİKLENEN FİZİK KURALLARI:")
            for rule in physics:
                lines.append(f"  - {rule}")

        # Benzer geçmiş olaylar
        similar = context.get("similar_past_events", [])
        if similar:
            lines.append("")
            lines.append("BENZER GEÇMİŞ OLAYLAR:")
            for event in similar:
                lines.append(f"  - {event}")

        return "\n".join(lines)

    # ─── JSON Ayrıştırma (3 Seviyeli Fallback) ───────────────────────────────

    def _parse_diagnosis_result(self, response_text: str, context: dict) -> DiagnosisResult:
        """
        LLM yanıtını ayrıştırır. 3 seviyeli fallback:

        1. Doğrudan JSON parse (yanıt saf JSON ise)
        2. Regex ile JSON çıkarma (yanıt metin arasında gizliyse)
        3. Yerel varsayılan teşhis (hiçbiri olmazsa)

        Fabrika benzetmesi: Uzmanın el yazısı raporu okunamıyorsa,
        önce düz yazıyı dene, sonra arasından bul, en kötü ihtimalle
        kendi gözlemlerinle rapor yaz.
        """
        if not response_text:
            log.warning("[PARSE] Boş yanıt — yerel teşhise düşülüyor")
            return self._default_diagnosis(context)

        # Seviye 1: Doğrudan JSON parse
        try:
            data = json.loads(response_text)
            log.info("[PARSE] Doğrudan JSON parse başarılı")
            return self._validate_and_convert(data, context)
        except json.JSONDecodeError:
            pass

        # Seviye 2: Regex ile JSON çıkarma
        try:
            # Markdown kod bloğu içinde JSON ara: ```json { ... } ```
            code_block = re.search(
                r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL
            )
            if code_block:
                data = json.loads(code_block.group(1))
                log.info("[PARSE] Regex (code block) JSON parse başarılı")
                return self._validate_and_convert(data, context)

            # Düz süslü parantez bloğu ara — en uzun { ... } eşleşmesi
            brace_block = re.search(r"(\{.*\})", response_text, re.DOTALL)
            if brace_block:
                data = json.loads(brace_block.group(1))
                log.info("[PARSE] Regex (brace block) JSON parse başarılı")
                return self._validate_and_convert(data, context)

        except json.JSONDecodeError:
            pass

        # Seviye 3: Varsayılan
        log.warning(
            "[PARSE] JSON çıkarma başarısız — yerel teşhise düşülüyor. "
            "Ham yanıt (ilk 200 karakter): %s", response_text[:200]
        )
        return self._default_diagnosis(context)

    def _validate_and_convert(self, data: dict, context: dict) -> DiagnosisResult:
        """
        Parse edilmiş JSON dict'i DiagnosisResult nesnesine çevirir.
        Eksik alanları varsayılanlarla doldurur, yerel analizle tamamlar.

        Fabrika benzetmesi: Uzmanın el yazısı raporunu resmi formata
        aktarırken eksik satırları kendi gözlemlerinle tamamlamak.
        """
        machine_id = data.get("machine_id", context.get("machine_id", "UNKNOWN"))
        timestamp = data.get("timestamp", context.get("timestamp", ""))

        # sensor_anomalies dönüştür — yeni format (value/limit) ve eski format (current_value/normal_value) desteği
        raw_anomalies = data.get("sensor_anomalies", {})
        sensor_anomalies: dict[str, SensorAnomaly] = {}
        for key, val in raw_anomalies.items():
            if isinstance(val, dict):
                # Yeni format: "value" / "limit" ; Eski format: "current_value" / "normal_value"
                current_val = val.get("current_value", val.get("value", 0))
                normal_val = val.get("normal_value", val.get("limit", 0))
                sensor_anomalies[key] = SensorAnomaly(
                    sensor_name=val.get("sensor_name", key),
                    current_value=float(current_val),
                    normal_value=float(normal_val),
                    deviation_pct=float(val.get("deviation_pct", 0)),
                    trend=val.get("trend", "stable"),
                    slope_per_hour=float(val.get("slope_per_hour", 0)),
                    status=val.get("status", "normal"),
                    description_tr=val.get("description_tr", ""),
                )
            elif isinstance(val, SensorAnomaly):
                sensor_anomalies[key] = val

        # Yerel anormalliklerle eksik kalanları tamamla
        local_anomalies = self._detect_anomalies_locally(context)
        for key, anomaly in local_anomalies.items():
            if key not in sensor_anomalies:
                sensor_anomalies[key] = anomaly

        # top_diagnoses dönüştür — yeni format (severity/category_tr/root_cause_analysis_tr) desteği
        raw_diagnoses = data.get("top_diagnoses", [])
        top_diagnoses: list[DiagnosisCandidate] = []
        for i, d in enumerate(raw_diagnoses[:3]):
            if isinstance(d, dict):
                top_diagnoses.append(
                    DiagnosisCandidate(
                        rank=int(d.get("rank", i + 1)),
                        fault_type=d.get("fault_type", "Bilinmeyen Arıza"),
                        confidence=float(d.get("confidence", 0.5)),
                        description_tr=d.get("description_tr", "Açıklama yok."),
                        supporting_sensors=d.get("supporting_sensors", []),
                        evidence=d.get("evidence", []),
                        recommended_action=d.get(
                            "recommended_action", "Teknisyen kontrolü önerilir."
                        ),
                        severity=d.get("severity", ""),
                        category_tr=d.get("category_tr", ""),
                        root_cause_analysis_tr=d.get("root_cause_analysis_tr", ""),
                    )
                )

        # Yerel teşhisle doldur (hiç yoksa)
        if not top_diagnoses:
            top_diagnoses = self._build_local_diagnoses(sensor_anomalies, context)

        # primary_diagnosis çözümle — yeni alanlarla birlikte
        primary: DiagnosisCandidate | None = None
        raw_primary = data.get("primary_diagnosis")
        if raw_primary and isinstance(raw_primary, dict):
            primary = DiagnosisCandidate(
                rank=int(raw_primary.get("rank", 1)),
                fault_type=raw_primary.get("fault_type", "Bilinmeyen Arıza"),
                confidence=float(raw_primary.get("confidence", 0.5)),
                description_tr=raw_primary.get("description_tr", "Açıklama yok."),
                supporting_sensors=raw_primary.get("supporting_sensors", []),
                evidence=raw_primary.get("evidence", []),
                recommended_action=raw_primary.get(
                    "recommended_action", "Teknisyen kontrolü önerilir."
                ),
                severity=raw_primary.get("severity", ""),
                category_tr=raw_primary.get("category_tr", ""),
                root_cause_analysis_tr=raw_primary.get("root_cause_analysis_tr", ""),
            )
        elif top_diagnoses:
            primary = top_diagnoses[0]

        # Yeni alanlar: immediate_actions_tr, maintenance_recommendations_tr, eta_to_failure, vb.
        immediate_actions = data.get("immediate_actions_tr", [])
        maintenance_recs = data.get("maintenance_recommendations_tr", [])
        eta = data.get("eta_to_failure", "")
        prod_impact = data.get("production_impact_tr", "")
        conf_notes = data.get("confidence_notes_tr", "")

        return DiagnosisResult(
            machine_id=machine_id,
            timestamp=timestamp,
            data_quality=data.get("data_quality", "reliable"),
            data_quality_notes=data.get("data_quality_notes", []),
            anomaly_pattern=data.get("anomaly_pattern", "none"),
            pattern_description_tr=data.get(
                "pattern_description_tr", "Pattern tespit edilemedi."
            ),
            sensor_anomalies=sensor_anomalies,
            top_diagnoses=top_diagnoses,
            primary_diagnosis=primary,
            reasoning_steps=data.get("reasoning_steps", []),
            execution_time_sec=0.0,
            agent_version="1.0",
            immediate_actions_tr=immediate_actions,
            maintenance_recommendations_tr=maintenance_recs,
            eta_to_failure=eta,
            production_impact_tr=prod_impact,
            confidence_notes_tr=conf_notes,
        )

    def _default_diagnosis(
        self, context: dict, local_anomalies: dict[str, SensorAnomaly] | None = None
    ) -> DiagnosisResult:
        """
        LLM başarısız olduğunda yerel analizle basit teşhis üretir.

        Fabrika benzetmesi: Uzmana ulaşılamayınca tecrübeli teknisyen
        kendi başına değerlendirir. Teşhis boş kalmaz, makine bekletilmez.
        """
        machine_id = context.get("machine_id", "UNKNOWN")
        timestamp = context.get("timestamp", "")

        if local_anomalies is None:
            local_anomalies = self._detect_anomalies_locally(context)

        top_diagnoses = self._build_local_diagnoses(local_anomalies, context)
        pattern, pattern_desc = self._detect_pattern_locally(local_anomalies, context)
        data_quality, quality_notes = self._assess_data_quality(context)
        primary = top_diagnoses[0] if top_diagnoses else None

        reasoning = [
            "Yerel analiz: LLM bağlantısı olmadan sensör verileri değerlendirildi.",
        ]
        if local_anomalies:
            anom_count = sum(
                1 for a in local_anomalies.values() if a.status in ("critical", "warning")
            )
            reasoning.append(f"{anom_count} sensörde anormallik tespit edildi.")
        else:
            reasoning.append("Tüm sensörler normal aralıkta.")

        return DiagnosisResult(
            machine_id=machine_id,
            timestamp=timestamp,
            data_quality=data_quality,
            data_quality_notes=quality_notes,
            anomaly_pattern=pattern,
            pattern_description_tr=pattern_desc,
            sensor_anomalies=local_anomalies,
            top_diagnoses=top_diagnoses,
            primary_diagnosis=primary,
            reasoning_steps=reasoning,
            execution_time_sec=0.0,
            agent_version="1.0",
            immediate_actions_tr=["Sensör verilerini manuel olarak kontrol edin."] if primary and primary.severity in ("CRITICAL", "HIGH") else [],
            maintenance_recommendations_tr=["LLM bağlantısı kurulamadı, sensör verilerini periyodik izleyin."] if primary and primary.severity in ("CRITICAL", "HIGH") else [],
            eta_to_failure="Bilinmiyor — LLM analizi yapılamadı",
            production_impact_tr="LLM bağlantısı olmadan üretim etkisi tahmin edilemiyor. Sensör verilerini manuel olarak izleyin ve durumu değerlendirin.",
            confidence_notes_tr="Bu teşhis yerel analizle üretilmiştir. LLM bağlantısı sağlandığında daha detaylı analiz yapılacaktır.",
        )

    def _build_local_diagnoses(
        self, anomalies: dict[str, SensorAnomaly], context: dict
    ) -> list[DiagnosisCandidate]:
        """
        Yerel anormalliklere dayalı basit teşhis adayları üretir.

        Fabrika benzetmesi: Tecrübeli teknisyenin günlük gözlemlerinden
        çıkardığı şüpheli arıza listesi. Uzman kadar derin değil ama
        yön gösterir.
        """
        diagnoses: list[DiagnosisCandidate] = []

        # Sıcaklık ve basınç ilişkisi — iç kaçak
        temp_anom = anomalies.get("oil_tank_temperature")
        press_anom = anomalies.get("main_pressure")

        if temp_anom and temp_anom.status in ("critical", "warning"):
            press_low = False
            if press_anom:
                # Basınç normalin altında mı? (normal değerin %90'ı)
                press_low = press_anom.current_value < press_anom.normal_value * 0.9

            if press_low:
                diagnoses.append(
                    DiagnosisCandidate(
                        rank=1,
                        fault_type="Hidrolik iç kaçak",
                        confidence=0.75,
                        description_tr="Yağ sıcaklığı yüksekken basınç düşük. İç kaçak enerjiyi ısıya çeviriyor.",
                        supporting_sensors=["oil_tank_temperature", "main_pressure"],
                        evidence=[
                            f"Sıcaklık: {temp_anom.current_value}°C ({temp_anom.status})",
                            f"Basınç: {press_anom.current_value} bar (normalin altında)",
                        ],
                        recommended_action="Ana silindir contalarını ve soğutma devresini kontrol edin.",
                        severity="HIGH",
                        category_tr="Hidrolik",
                        root_cause_analysis_tr="Sıcaklık yükselmiş ve basınç düşmüş. Bu pattern iç kaçağa işaret ediyor. İç kaçakta hidrolik yağı contalardan sızar, sürtünme artar, enerji ısıya dönüşür. Basınç düşer çünkü yağ doğru yere gitmek yerine kaçak yoluyla geri döner.",
                    )
                )
            else:
                diagnoses.append(
                    DiagnosisCandidate(
                        rank=1,
                        fault_type="Yağ sıcaklığı yüksekliği",
                        confidence=0.70,
                        description_tr=f"Yağ sıcaklığı {temp_anom.current_value}°C'ye çıkmış. Soğutma sistemi yetersiz veya yağ yaşlanmış.",
                        supporting_sensors=["oil_tank_temperature"],
                        evidence=[f"Sıcaklık: {temp_anom.current_value}°C ({temp_anom.status})"],
                        recommended_action="Soğutma kulesi, pompa ve radyatörleri kontrol edin.",
                        severity="MEDIUM",
                        category_tr="Termal",
                        root_cause_analysis_tr="Yağ sıcaklığı limitin üzerinde. Soğutma sistemi yetersiz kalmış veya yağ ömrünü tamamlamış olabilir. Yağ viskozitesi düştükçe sürtünme artar ve sıcaklık daha da yükselir.",
                    )
                )

        # Basınç yüksek + hız düşük = sıkışma
        hp_press = anomalies.get("horizontal_press_pressure")
        h_speed = anomalies.get("horitzonal_infeed_speed")

        if hp_press and h_speed:
            if hp_press.current_value > 100 and abs(h_speed.current_value) < 5:
                diagnoses.append(
                    DiagnosisCandidate(
                        rank=len(diagnoses) + 1,
                        fault_type="Mekanik sıkışma",
                        confidence=0.65,
                        description_tr="Basınç yüksek ama hız sıfıra yakın. Besleme mekanizmasında bir yerde sıkışma var.",
                        supporting_sensors=["horizontal_press_pressure", "horitzonal_infeed_speed"],
                        evidence=[
                            f"Basınç: {hp_press.current_value} bar",
                            f"Hız: {h_speed.current_value} mm/s",
                        ],
                        recommended_action="Besleme mekanizması raylarını temizleyip gresleyin.",
                        severity="HIGH",
                        category_tr="Mekanik",
                        root_cause_analysis_tr="Basınç yüksek ancak hız çok düşük. Bu, besleme mekanizmasında mekanik bir direnç olduğunu gösteriyor. Piston veya ray sisteminde sıkışma, kirlenme veya yağlama eksikliği olabilir.",
                    )
                )

        # Alt ejektör basıncı anormalliği
        ejector = anomalies.get("lower_ejector_pressure")
        if ejector and ejector.status in ("critical", "warning"):
            diagnoses.append(
                DiagnosisCandidate(
                    rank=len(diagnoses) + 1,
                    fault_type="Alt ejektör basınç arızası",
                    confidence=0.60,
                    description_tr=f"Alt ejektör basıncı {ejector.current_value} bar. Valf veya silindir sorunu olabilir.",
                    supporting_sensors=["lower_ejector_pressure"],
                    evidence=[f"Basınç: {ejector.current_value} bar ({ejector.status})"],
                    recommended_action="Alt ejektör valfini ve hortum bağlantılarını kontrol edin.",
                    severity="MEDIUM",
                    category_tr="Hidrolik",
                    root_cause_analysis_tr="Alt ejektör basıncı anormal. Valf sıkışması, contanın yıpranması veya hortum bağlantısında kaçak olabilir.",
                )
            )

        # Filtre kirlenmesi — aktif fizik kurallarından
        physics_rules = context.get("active_physics_rules", [])
        for rule in physics_rules:
            if "filtre" in rule.lower():
                diagnoses.append(
                    DiagnosisCandidate(
                        rank=len(diagnoses) + 1,
                        fault_type="Filtre kirlenmesi",
                        confidence=0.60,
                        description_tr="Basınç hattı filtrelerinde kirlenme tespit edildi. Basınç dalgalanmasına neden olabilir.",
                        supporting_sensors=["main_pressure"],
                        evidence=[rule],
                        recommended_action="İlgili filtreleri temizleyin veya değiştirin.",
                        severity="MEDIUM",
                        category_tr="Hidrolik",
                        root_cause_analysis_tr="Filtre kirlenmesi basınç dalgalanmasına neden oluyor. Filtre tıkandığında yağ akışı düzensizleşir, pompa aşırı yüklenir ve basınç dalgalanır.",
                    )
                )
                break

        # Hiç teşhis yoksa normal çalışma
        if not diagnoses:
            diagnoses.append(
                DiagnosisCandidate(
                    rank=1,
                    fault_type="Normal çalışma",
                    confidence=0.95,
                    description_tr="Tüm sensörler normal aralıkta. Anormal durum tespit edilmedi.",
                    supporting_sensors=[],
                    evidence=["Tüm sensör değerleri limitler içinde."],
                    recommended_action="Standart bakım takvimine devam edin.",
                    severity="LOW",
                    category_tr="Kontrol",
                    root_cause_analysis_tr="Tüm sensör değerleri normal aralıkta. Herhangi bir anormallik veya arıza belirtisi tespit edilmedi. Makine normal çalışma koşullarında.",
                )
            )

        # 1'den başlayarak rank'leri sıralı yap
        for i, d in enumerate(diagnoses):
            d.rank = i + 1

        return diagnoses[:3]

    def _detect_pattern_locally(
        self, anomalies: dict[str, SensorAnomaly], context: dict
    ) -> tuple[str, str]:
        """
        Yerel olarak anomali pattern'ini tespit eder.

        Fabrika benzetmesi: Gösterge paneline bakıp "Bu ani mi oldu,
        yoksa yavaş yavaş mı geldi?" diye karar vermek.
        """
        if not anomalies:
            return "none", "Tüm sensörler stabil ve normal aralıkta."

        slopes = [
            a.slope_per_hour
            for a in anomalies.values()
            if a.slope_per_hour != 0 and a.status in ("critical", "warning")
        ]
        if not slopes:
            return "sudden_change", "Ani değişim tespit edildi, trend bilgisi mevcut değil."

        avg_slope = sum(slopes) / len(slopes)
        max_slope = max(abs(s) for s in slopes)

        if max_slope > 50:
            return (
                "sudden_change",
                "Çok ani ve sert değişim — mekanik arıza veya sensör hatası ihtimali yüksek.",
            )
        elif avg_slope > 5:
            return (
                "slow_trend",
                "Yavaş ama istikrarlı artış trendi — aşınma, tıkanma veya iç kaçak belirtisi.",
            )
        elif any(s < 0 for s in slopes) and any(s > 0 for s in slopes):
            return (
                "periodic",
                "Karşıt yönlü dalgalanmalar — çevresel etki veya regülatör salınımı.",
            )
        else:
            return "slow_trend", "Kademeli değişim gözlemleniyor."

    def _assess_data_quality(self, context: dict) -> tuple[str, list[str]]:
        """
        Veri kalitesini değerlendirir.

        Fabrika benzetmesi: Veriler gelmeden önce "Bu kayıtlar sağlam mı,
        eksik bilgi var mı?" diye kontrol etmek.
        """
        notes: list[str] = []
        sensor_states = context.get("sensor_states", {})

        if not sensor_states:
            notes.append("Sensör verisi eksik.")
            return "unreliable", notes

        total = len(sensor_states)
        missing = sum(1 for s in sensor_states.values() if s.get("value") is None)

        if missing > 0:
            notes.append(f"{missing}/{total} sensörde veri eksik.")

        if missing > total / 2:
            return "unreliable", notes
        elif missing > 0:
            return "suspicious", notes
        else:
            return "reliable", notes

    def _detect_anomalies_locally(self, context: dict) -> dict[str, SensorAnomaly]:
        """
        LLM olmadan yerel anormallik tespiti yapar.

        Sensör değerlerini limitlerle karşılaştırır, sapma yüzdelerini
        hesaplar, trend yönünü belirler. Fabrika benzetmesi: Panodaki
        ibrelere tek tek bakıp hangileri kırmızı bölgede diye kontrol etmek.

        Returns:
            {sensor_name: SensorAnomaly} — Tüm sensörler için değerlendirme.
        """
        anomalies: dict[str, SensorAnomaly] = {}
        sensor_states = context.get("sensor_states", {})

        for key, s in sensor_states.items():
            val = s.get("value")
            if val is None:
                continue

            limit_max = s.get("limit_max")
            limit_pct = s.get("limit_pct", 0)
            slope = s.get("slope_per_hour")

            # Normal değer tahmini: limitin ~%70'i (tipik çalışma noktası)
            if limit_max and limit_max > 0:
                normal_val = limit_max * 0.7
                # Sapma yüzdesi: limit aşılmışsa ne kadar aşılmış
                deviation = limit_pct - 100.0 if limit_pct > 100 else 0.0
            else:
                normal_val = val
                deviation = 0.0

            # Trend yönü
            if slope is not None:
                if slope > 0.05:
                    trend = "increasing"
                elif slope < -0.05:
                    trend = "decreasing"
                else:
                    trend = "stable"
            else:
                trend = "stable"
                slope = 0.0

            # Durum etiketi
            if limit_pct >= 100:
                status = "critical"
            elif limit_pct >= 85:
                status = "warning"
            else:
                status = "normal"

            anomalies[key] = SensorAnomaly(
                sensor_name=key,
                current_value=round(float(val), 2),
                normal_value=round(float(normal_val), 2),
                deviation_pct=round(float(deviation), 1),
                trend=trend,
                slope_per_hour=round(float(slope), 3),
                status=status,
            )

        return anomalies


# ─── Singleton ────────────────────────────────────────────────────────────────
_diagnosis_instance: DiagnosisAgent | None = None
_diagnosis_lock = threading.Lock()


def get_diagnosis_agent() -> DiagnosisAgent:
    """
    Global Teşhis Ajanı örneğini döner (lazy init, thread-safe).

    Fabrika benzetmesi: Herkes aynı uzmana danışır, masanın üstünde
    birden fazla rapor biriktirilmez. İlk çağrıda uzman masasına oturur,
    sonrakiler aynı uzmana ulaşır.
    """
    global _diagnosis_instance
    with _diagnosis_lock:
        if _diagnosis_instance is None:
            _diagnosis_instance = DiagnosisAgent()
    return _diagnosis_instance
