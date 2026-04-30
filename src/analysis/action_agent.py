"""
action_agent.py — Eylem Planı Ajanı
═════════════════════════════════════
Teşhis, kök neden ve tahmin sonuçlarına dayalı somut, öncelikli bakım
eylem planları üreten uzman ajan. Gemini API ile çalışır, API devre dışı
kaldığında yerel şablon motoruna düşerek çalışmaya devam eder.

Fabrika benzetmesi: 25 yıllık kıdemli bakım şefi.
Teşhis raporunu alır, adım adım bakım planı hazırlar.
Ustaya ulaşılamazsa standart planı uygular, makine plansız kalmaz.

Kullanım:
    from src.analysis.action_agent import get_action_agent
    agent = get_action_agent()
    plan = await agent.create_action_plan(context, diagnosis_result)
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
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"
    )
    load_dotenv(_env_path)
    _dotenv_loaded = True
except ImportError:
    _dotenv_loaded = False

log = logging.getLogger("action_agent")

# ─── Enumerasyonlar ──────────────────────────────────────────────────────────

class PriorityLevel(Enum):
    """Bakım eyleminin aciliyet seviyesi."""
    IMMEDIATE = "immediate"      # İlk 15 dakika (ACİL)
    SHORT_TERM = "short_term"    # 1-2 saat (KISA VADELİ)
    LONG_TERM = "long_term"      # 1 hafta (UZUN VADELİ)


class DifficultyLevel(Enum):
    """Bakım eyleminin zorluk derecesi."""
    EASY = "Kolay"
    MEDIUM = "Orta"
    HARD = "Zor"


# ─── Veri Yapıları ───────────────────────────────────────────────────────────

@dataclass
class RequiredPart:
    """Bakım için gerekli yedek parça bilgisi."""
    part_number: str
    name: str
    quantity: int
    in_stock: Optional[bool] = None
    stock_count: Optional[int] = None
    estimated_cost_try: Optional[float] = None


@dataclass
class Action:
    """Tek bir bakım eylemi (adım)."""
    step_number: int
    priority: PriorityLevel
    description_tr: str
    estimated_time_min: int
    difficulty: DifficultyLevel
    tools_required: list[str] = field(default_factory=list)
    required_parts: list[RequiredPart] = field(default_factory=list)
    safety_warnings: list[str] = field(default_factory=list)
    success_criteria: str = ""


@dataclass
class ActionPlan:
    """Eylem Planı Ajanının nihai çıktısı."""
    machine_id: str
    timestamp: str
    immediate_actions: list[Action] = field(default_factory=list)
    short_term_actions: list[Action] = field(default_factory=list)
    long_term_actions: list[Action] = field(default_factory=list)
    total_estimated_downtime_min: int = 0
    total_parts_cost_try: Optional[float] = None
    all_required_parts: list[RequiredPart] = field(default_factory=list)
    critical_safety_warnings: list[str] = field(default_factory=list)
    success_criteria: str = ""
    based_on_diagnosis: str = ""
    based_on_root_cause: Optional[str] = None
    execution_time_sec: float = 0.0
    agent_version: str = "1.0"


# ─── Sistem Promptu ──────────────────────────────────────────────────────────

_ACTION_SYSTEM_PROMPT = """Sen Codlean MES fabrikasının kıdemli bakım şefisin.
25 yıldır hidrolik preslerin bakımından sorumlusun. Teşhis raporu alırsın,
ona göre somut, adım adım, öncelikli bir bakım eylem planı hazırlarsın.

KURALLAR:
- Sadece JSON çıktısı üret, başka metin yazma.
- Güvenlik uyarılarını HER ZAMAN ilk sıraya koy.
- Süreler gerçekçi olsun: Kolay 5-30 dk, Orta 30-90 dk, Zor 90-180 dk.
- Alet listesi somut olsun: "13mm kombine anahtar" gibi.
- Parça numaraları varsa yaz, yoksa parça ismi yeterli.
- Türkçe açıklamalar kullan.
- BAŞLIK YAZMA, sadece JSON döndür.
"""

_JSON_OUTPUT_SCHEMA = """
ÇIKTI FORMATI — Sadece bu JSON şemasını kullan, başka metin yazma:

{
  "machine_id": "HPR001",
  "timestamp": "2026-04-24 12:00:00",
  "immediate_actions": [
    {
      "step_number": 1,
      "priority": "immediate",
      "description_tr": "Makineyi durdur ve acil stop butonuna bas.",
      "estimated_time_min": 5,
      "difficulty": "Kolay",
      "tools_required": ["Acil Stop Butonu"],
      "required_parts": [],
      "safety_warnings": ["MAKİNEYİ DURDURMADAN MÜDAHALE ETMEYİN!"],
      "success_criteria": "Makine tamamen durmuş, basınç sıfırlanmış."
    }
  ],
  "short_term_actions": [...],
  "long_term_actions": [...],
  "total_estimated_downtime_min": 170,
  "total_parts_cost_try": 4500.0,
  "all_required_parts": [
    {"part_number": "CNT-120", "name": "Ana silindir contası", "quantity": 2, "estimated_cost_try": 250.0}
  ],
  "critical_safety_warnings": ["YÜKSEK BASINÇ - Koruyucu ekipman giyin!"],
  "success_criteria": "Tüm basınç değerleri normal aralıkta, sızıntı yok.",
  "based_on_diagnosis": "Hidrolik iç kaçak",
  "based_on_root_cause": "Ana silindir contalarında aşınma"
}
"""

# ─── Ana Sınıf ───────────────────────────────────────────────────────────────

class ActionAgent:
    """
    Eylem Planı Ajanı — Teşhis sonuçlarından somut bakım planı üretir.

    Fabrika benzetmesi: 25 yıllık kıdemli bakım şefi.
    Teşhis raporunu okur, adım adım planlar. API kapalıysa yerel şablonları uygular.
    """

    CALL_TIMEOUT_SEC = 30
    MODEL_NAME = "gemini-2.5-flash"

    def __init__(self, api_key: str | None = None):
        self._ready = False
        self._client = None
        self._init_error = None

        # API Key Rotation Manager kullan
        from src.core.api_key_manager import get_api_key
        
        key = api_key or get_api_key()
        log.info("[ACTION_INIT] dotenv yüklendi: %s", _dotenv_loaded)
        log.info("[ACTION_INIT] API Key mevcut: %s", bool(key))
        if key:
            log.info("[ACTION_INIT] API Key ilk 8 karakter: %s...", key[:8])

        if not key:
            self._init_error = "GEMINI_API_KEY tanımlı değil. .env dosyasını kontrol edin."
            log.warning("[ACTION_INIT] %s", self._init_error)
            return

        try:
            from google import genai
            self._client = genai.Client(api_key=key)
            self._ready = True
            log.info("[ACTION_INIT] ✅ Eylem Ajanı hazır (%s)", self.MODEL_NAME)
        except ImportError:
            self._init_error = "google-genai kütüphanesi kurulu değil. 'pip install google-genai' çalıştırın."
            log.warning("[ACTION_INIT] %s", self._init_error)
        except Exception as e:
            self._init_error = f"Gemini başlatılamadı: {e}"
            log.warning("[ACTION_INIT] %s", self._init_error)

    @property
    def is_ready(self) -> bool:
        """Gemini API hazır mı?"""
        return self._ready

    # ─── Ana Giriş Noktası ───────────────────────────────────────────────────

    async def create_action_plan(
        self,
        context: dict,
        diagnosis_result: dict | None = None,
        root_cause_result: dict | None = None,
        prediction_result: dict | None = None,
    ) -> ActionPlan:
        """
        Makine bağlamı ve önceki ajan sonuçlarına göre eylem planı üretir.

        Fabrika benzetmesi: Bakım şefi teşhis raporunu alır,
        somut bir bakım programı hazırlar. API çalışmazsa standart planı uygular.
        """
        start_time = time.monotonic()
        machine_id = context.get("machine_id", "UNKNOWN")
        log.info("[ACTION START] %s — eylem planı oluşturuluyor", machine_id)

        if diagnosis_result is None:
            log.warning("[ACTION] %s — teşhis sonucu yok, yerel plana düşülüyor", machine_id)
            plan = self._create_local_action_plan(context, diagnosis_result)
            plan.execution_time_sec = round(time.monotonic() - start_time, 2)
            return plan

        if self._ready:
            try:
                prompt = self._build_action_prompt(context, diagnosis_result, root_cause_result, prediction_result)
                log.info("[ACTION] %s — LLM'e eylem planı sorusu gönderiliyor", machine_id)
                response_text = await asyncio.get_event_loop().run_in_executor(
                    None, self._call_llm_sync, prompt
                )
                if response_text and not response_text.startswith(("⏰", "🚫", "🔑", "🌐", "❌")):
                    plan = self._parse_action_result(response_text, context, diagnosis_result)
                    plan.execution_time_sec = round(time.monotonic() - start_time, 2)
                    log.info("[ACTION END] %s — LLM eylem planı başarılı (%.2fs)", machine_id, plan.execution_time_sec)
                    return plan
                else:
                    log.warning("[ACTION] %s — LLM hatası: %s", machine_id, response_text)
            except Exception as e:
                log.exception("[ACTION] %s — LLM çağrısı başarısız: %s", machine_id, e)

        log.info("[ACTION] %s — yerel eylem planına düşülüyor (fallback)", machine_id)
        plan = self._create_local_action_plan(context, diagnosis_result)
        plan.execution_time_sec = round(time.monotonic() - start_time, 2)
        log.info("[ACTION END] %s — yerel eylem planı tamamlandı (%.2fs)", machine_id, plan.execution_time_sec)
        return plan

    # ─── LLM Çağrısı (Senkron — Async thread'de çalıştırılır) ────────────────

    def _call_llm_sync(self, prompt: str) -> str:
        """
        Gemini API'ye senkron çağrı yapar.
        DiagnosisAgent._call_llm_sync ile AYNI kalıbı kullanır.
        """
        if not self._ready:
            return self._init_error or "Eylem Ajanı hazır değil."

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
                        system_instruction=_ACTION_SYSTEM_PROMPT,
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
                    log.warning("[ACTION] Gemini 429 hatası - Groq fallback deneniyor...")
                    try:
                        # Groq client
                        groq_key = get_groq_api_key()
                        groq_client = groq.Groq(api_key=groq_key)

                        groq_response = groq_client.chat.completions.create(
                            model='llama-3.3-70b-versatile',
                            messages=[
                                {"role": "system", "content": _ACTION_SYSTEM_PROMPT},
                                {"role": "user", "content": prompt}
                            ],
                            temperature=0.3,
                            max_tokens=4096,
                        )

                        result_container[0] = groq_response.choices[0].message.content.strip()
                        record_groq_usage(success=True)
                        log.info("[ACTION] Groq fallback başarılı!")
                        return  # Groq başarılı, çık

                    except Exception as groq_err:
                        log.exception("[ACTION] Groq fallback da başarısız: %s", groq_err)
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

    # ─── Prompt Oluşturma ────────────────────────────────────────────────────

    def _build_action_prompt(
        self, context: dict, diagnosis: dict, root_cause: dict | None = None, prediction: dict | None = None
    ) -> str:
        """Eylem planı prompt'unu oluşturur."""
        lines = [
            "Sen bir hidrolik pres bakım şefisin. 25 yıllık deneyimin var.",
            "GÖREV: Aşağıdaki teşhis raporuna dayalı somut, öncelikli bir bakım eylem planı hazırla.",
            "",
            "ÖNEMLİ: Güvenlik uyarılarını HER ZAMAN ilk sıraya koy. Acele etme ama kaybetme.",
            "",
            "KURALLAR:",
            "- Her eylem somut ve ölçülebilir olsun. 'Kontrol et' deme, 'Contada çatlak var mı bak' de.",
            "- Süreler gerçekçi: Kolay 5-30 dk, Orta 30-90 dk, Zor 90-180 dk.",
            "- Alet listesi somut: '13mm kombine anahtar' gibi.",
            "- Güvenlik uyarıları her adımda tekrarla.",
            "- Parça numarası biliyorsan yaz, bilmiyorsan ismi yeterli.",
            "- Türkçe açıklamalar kullan.",
            "",
            "ÖNCEKİ UZMAN RAPORLARI:",
            self._format_prior_results(diagnosis, root_cause, prediction),
            "",
            "MAKİNE VERİLERİ:",
            self._format_context_for_prompt(context),
            "",
            _JSON_OUTPUT_SCHEMA,
            "",
            "ÇIKTI: Sadece JSON döndür, başka metin yazma. Yorum, açıklama, markdown kod bloğu ekleme.",
        ]
        return "\n".join(lines)

    def _format_prior_results(
        self, diagnosis: dict, root_cause: dict | None = None, prediction: dict | None = None
    ) -> str:
        """Önceki ajan sonuçlarını prompt için biçimlendirir."""
        lines = []
        primary = diagnosis.get("primary_diagnosis") if isinstance(diagnosis, dict) else None
        if primary and isinstance(primary, dict):
            lines.append(f"TEŞHİS: {primary.get('fault_type', 'Bilinmeyen')}")
            lines.append(f"  Açıklama: {primary.get('description_tr', 'Açıklama yok.')}")
            lines.append(f"  Güven: {primary.get('confidence', 0)}")
            rec = primary.get("recommended_action", "")
            if rec:
                lines.append(f"  Öneri: {rec}")
        else:
            fault = diagnosis.get("fault_type", "Bilinmeyen") if isinstance(diagnosis, dict) else "Bilinmeyen"
            lines.append(f"TEŞHİS: {fault}")

        if root_cause and isinstance(root_cause, dict):
            rc_msg = root_cause.get("root_cause") or root_cause.get("message") or root_cause.get("description_tr")
            if rc_msg:
                lines.append(f"KÖK NEDEN: {rc_msg}")

        if prediction and isinstance(prediction, dict):
            pred_msg = prediction.get("prediction") or prediction.get("message") or prediction.get("eta_estimate")
            if pred_msg:
                lines.append(f"TAHMİN: {pred_msg}")

        if not lines:
            lines.append("Önceki uzman raporları mevcut değil.")
        return "\n".join(lines)

    def _format_context_for_prompt(self, context: dict) -> str:
        """Sensör verilerini prompt için biçimlendirir."""
        lines = [
            f"Makine: {context.get('machine_id', 'Bilinmiyor')}",
            f"Zaman: {context.get('timestamp', 'Bilinmiyor')}",
            f"Risk: {context.get('risk_score', 0)}/100 ({context.get('severity', 'NORMAL')})",
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

        critical = context.get("critical_sensors", [])
        if critical:
            lines.append("")
            lines.append("KRİTİK YAKLAŞIM:")
            for c in critical:
                lines.append(f"  - {c}")
        return "\n".join(lines)

    # ─── JSON Ayrıştırma (3 Seviyeli Fallback) ───────────────────────────────

    def _parse_action_result(self, response_text: str, context: dict, diagnosis: dict) -> ActionPlan:
        """
        LLM yanıtını ayrıştırır. 3 seviyeli fallback:
        1. Doğrudan JSON parse
        2. Regex ile JSON çıkarma
        3. Yerel varsayılan plan
        """
        if not response_text:
            log.warning("[PARSE] Boş yanıt — yerel plana düşülüyor")
            return self._create_local_action_plan(context, diagnosis)

        try:
            data = json.loads(response_text)
            log.info("[PARSE] Doğrudan JSON parse başarılı")
            return self._validate_and_convert(data, context, diagnosis)
        except json.JSONDecodeError:
            pass

        try:
            code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
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

        log.warning("[PARSE] JSON çıkarma başarısız — yerel plana düşülüyor. Ham yanıt (ilk 200 karakter): %s", response_text[:200])
        return self._create_local_action_plan(context, diagnosis)

    def _validate_and_convert(self, data: dict, context: dict, diagnosis: dict) -> ActionPlan:
        """Parse edilmiş JSON dict'i ActionPlan nesnesine çevirir."""
        machine_id = data.get("machine_id", context.get("machine_id", "UNKNOWN"))
        timestamp = data.get("timestamp", context.get("timestamp", ""))

        immediate = self._parse_actions(data.get("immediate_actions", []))
        short_term = self._parse_actions(data.get("short_term_actions", []))
        long_term = self._parse_actions(data.get("long_term_actions", []))
        all_parts = self._parse_parts(data.get("all_required_parts", []))

        safety = data.get("critical_safety_warnings", [])
        if not safety:
            safety = self._generate_safety_warnings(context)

        based_on = ""
        if isinstance(diagnosis, dict):
            primary = diagnosis.get("primary_diagnosis")
            if isinstance(primary, dict):
                based_on = primary.get("fault_type", "")
            elif diagnosis.get("fault_type"):
                based_on = diagnosis.get("fault_type", "")
            else:
                top = diagnosis.get("top_diagnoses", [])
                if top and isinstance(top[0], dict):
                    based_on = top[0].get("fault_type", "")

        based_on_root = data.get("based_on_root_cause")
        if not based_on_root and isinstance(diagnosis, dict):
            based_on_root = diagnosis.get("root_cause")

        total_time = (
            sum(a.estimated_time_min for a in immediate)
            + sum(a.estimated_time_min for a in short_term)
            + sum(a.estimated_time_min for a in long_term)
        )

        return ActionPlan(
            machine_id=machine_id,
            timestamp=timestamp,
            immediate_actions=immediate,
            short_term_actions=short_term,
            long_term_actions=long_term,
            total_estimated_downtime_min=data.get("total_estimated_downtime_min", total_time),
            total_parts_cost_try=data.get("total_parts_cost_try"),
            all_required_parts=all_parts,
            critical_safety_warnings=safety,
            success_criteria=data.get("success_criteria", ""),
            based_on_diagnosis=data.get("based_on_diagnosis", based_on),
            based_on_root_cause=based_on_root,
            execution_time_sec=0.0,
            agent_version="1.0",
        )

    def _parse_actions(self, raw_actions: list[dict]) -> list[Action]:
        """Ham action dict listesini Action nesnelerine çevirir."""
        actions: list[Action] = []
        for i, raw in enumerate(raw_actions):
            if not isinstance(raw, dict):
                continue
            priority_str = raw.get("priority", "immediate")
            try:
                priority = PriorityLevel(priority_str)
            except ValueError:
                priority = PriorityLevel.IMMEDIATE
            diff_str = raw.get("difficulty", "Orta")
            try:
                difficulty = DifficultyLevel(diff_str)
            except ValueError:
                difficulty = DifficultyLevel.MEDIUM
            parts = self._parse_parts(raw.get("required_parts", []))
            actions.append(Action(
                step_number=raw.get("step_number", i + 1),
                priority=priority,
                description_tr=raw.get("description_tr", "Açıklama yok."),
                estimated_time_min=int(raw.get("estimated_time_min", 15)),
                difficulty=difficulty,
                tools_required=raw.get("tools_required", []),
                required_parts=parts,
                safety_warnings=raw.get("safety_warnings", []),
                success_criteria=raw.get("success_criteria", ""),
            ))
        return actions

    def _parse_parts(self, raw_parts: list[dict]) -> list[RequiredPart]:
        """Ham part dict listesini RequiredPart nesnelerine çevirir."""
        parts: list[RequiredPart] = []
        for raw in raw_parts:
            if not isinstance(raw, dict):
                continue
            parts.append(RequiredPart(
                part_number=raw.get("part_number", "Bilinmiyor"),
                name=raw.get("name", "Bilinmeyen Parça"),
                quantity=int(raw.get("quantity", 1)),
                in_stock=raw.get("in_stock"),
                stock_count=raw.get("stock_count"),
                estimated_cost_try=raw.get("estimated_cost_try"),
            ))
        return parts

    # ─── Yerel Fallback (API Yoksa) ──────────────────────────────────────────

    def _create_local_action_plan(self, context: dict, diagnosis: dict | None) -> ActionPlan:
        """LLM başarısız olduğunda yerel şablonlarla eylem planı üretir."""
        machine_id = context.get("machine_id", "UNKNOWN")
        timestamp = context.get("timestamp", "")
        fault_type = self._extract_fault_type(diagnosis)

        # re.IGNORECASE kullanarak Türkçe İ/i karakteri sorununu aşıyoruz
        if re.search(r"iç\s*kaçak|sızıntı", fault_type, re.IGNORECASE):
            immediate, short_term, long_term, parts = self._template_internal_leak()
        elif re.search(r"filtre|tıkanıklık", fault_type, re.IGNORECASE):
            immediate, short_term, long_term, parts = self._template_filter_clog()
        elif re.search(r"basınç", fault_type, re.IGNORECASE):
            immediate, short_term, long_term, parts = self._template_pressure_anomaly()
        elif re.search(r"sıcaklık|ısınma", fault_type, re.IGNORECASE):
            immediate, short_term, long_term, parts = self._template_temperature_high()
        elif re.search(r"sıkışma|mekanik", fault_type, re.IGNORECASE):
            immediate, short_term, long_term, parts = self._template_mechanical_jam()
        else:
            immediate, short_term, long_term, parts = self._template_generic()

        safety = self._generate_safety_warnings(context)
        total_time = sum(a.estimated_time_min for a in immediate + short_term + long_term)

        return ActionPlan(
            machine_id=machine_id,
            timestamp=timestamp,
            immediate_actions=immediate,
            short_term_actions=short_term,
            long_term_actions=long_term,
            total_estimated_downtime_min=total_time,
            all_required_parts=parts,
            critical_safety_warnings=safety,
            success_criteria="Tüm sensör değerleri normal aralığa dönmüş, sızıntı ve anormallik yok.",
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

    # ─── Yerel Şablonlar ─────────────────────────────────────────────────────

    def _template_internal_leak(self) -> tuple[list[Action], list[Action], list[Action], list[RequiredPart]]:
        immediate = [
            Action(1, PriorityLevel.IMMEDIATE, "Makineyi durdur, acil stop butonuna bas ve basınç sıfırlama valfini aç.", 5, DifficultyLevel.EASY,
                   ["Acil Stop Butonu"], [], ["MAKİNEYİ DURDURMADAN MÜDAHALE ETMEYİN!", "Basınç sıfırlandığından emin olun."], "Makine tamamen durmuş, basınç 0 bar."),
            Action(2, PriorityLevel.IMMEDIATE, "Soğutma fanı ve radyatör yüzeyini görsel olarak kontrol et. Toz/kir varsa temizle.", 10, DifficultyLevel.EASY,
                   ["Fırça", "Basınçlı hava", "Temiz bez"], [], ["YÜKSEK SICAKLIK - Yanık riski! Eldiven giyin."], "Fan dönüyor, radyatör temiz, hava akışı serbest."),
        ]
        short_term = [
            Action(1, PriorityLevel.SHORT_TERM, "Eşanjör giriş-çıkış sıcaklık farkını (ΔT) ölç. ΔT < 5°C ise eşanjör verimsiz.", 20, DifficultyLevel.MEDIUM,
                   ["Kızılötesi termometre", "Not defteri"], [], ["YÜKSEK SICAKLIK - Yanık riski!"], "ΔT değeri kaydedilmiş, eşanjör durumu belirlenmiş."),
            Action(2, PriorityLevel.SHORT_TERM, "Ana silindir contalarını söküp kontrol et. Çatlak, yıpranma veya sızıntı izi var mı?", 45, DifficultyLevel.MEDIUM,
                   ["13mm kombine anahtar", "Conta seti", "Fener", "Temiz bez"],
                   [RequiredPart("CNT-120", "Ana silindir contası", 2)],
                   ["Basınç sıfırlandığından emin olun."], "Contalar temiz, çatlak yok. Gerekirse contalar değişmiş."),
        ]
        long_term = [
            Action(1, PriorityLevel.LONG_TERM, "Tüm hidrolik devrede yağ değişimi, filtre değişimi ve sızıntı testi yap.", 120, DifficultyLevel.HARD,
                   ["Yağ boşaltma pompası", "Filtre anahtarı", "TDP ölçer", "UV lamba"],
                   [RequiredPart("HYD-OIL-68", "Hidrolik yağı ISO VG 68", 200), RequiredPart("FLT-HP-01", "Basınç hattı filtresi", 2)],
                   ["Yağ boşaltmadan önce tankı soğutun.", "Atık yağı çevreye dökmeyin."], "Yağ temiz, filtreler yenilenmiş, UV testinde sızıntı yok."),
        ]
        parts = [
            RequiredPart("CNT-120", "Ana silindir contası", 2, estimated_cost_try=250.0),
            RequiredPart("HYD-OIL-68", "Hidrolik yağı ISO VG 68", 200, estimated_cost_try=3500.0),
            RequiredPart("FLT-HP-01", "Basınç hattı filtresi", 2, estimated_cost_try=180.0),
        ]
        return immediate, short_term, long_term, parts

    def _template_filter_clog(self) -> tuple[list[Action], list[Action], list[Action], list[RequiredPart]]:
        immediate = [
            Action(1, PriorityLevel.IMMEDIATE, "Makineyi durdur ve basıncı sıfırla.", 5, DifficultyLevel.EASY,
                   ["Acil Stop Butonu"], [], ["MAKİNEYİ DURDURMADAN MÜDAHALE ETMEYİN!", "Basınç sıfırlandığından emin olun."], "Makine durmuş, basınç 0 bar."),
        ]
        short_term = [
            Action(1, PriorityLevel.SHORT_TERM, "Basınç hattı filtrelerini (1-5) sök ve kirlenme durumunu kontrol et.", 30, DifficultyLevel.MEDIUM,
                   ["Filtre anahtarı", "Fener", "Temiz bez", "Basınçlı hava"],
                   [RequiredPart("FLT-HP-01", "Basınç hattı filtresi", 5)],
                   ["Basınç sıfırlandığından emin olun."], "Filtreler temizlenmiş veya değişmiş, basınç düşümü normal."),
            Action(2, PriorityLevel.SHORT_TERM, "Yağ tankı seviyesini ve yağ kalitesini kontrol et. Gerekirse yağ ekle.", 15, DifficultyLevel.EASY,
                   ["Dipstick", "Yağ numune şişesi"], [RequiredPart("HYD-OIL-68", "Hidrolik yağı ISO VG 68", 20)],
                   ["Yağ sıcaklığı düşükken kontrol edin."], "Yağ seviyesi normal, renk/koku normal."),
        ]
        long_term = [
            Action(1, PriorityLevel.LONG_TERM, "Filtre değişim döngüsünü optimize et. Yağ analiz raporu iste ve periyodu ayarla.", 60, DifficultyLevel.MEDIUM,
                   ["Bilgisayar", "Bakım planlama yazılımı"], [], [], "Yeni filtre değişim periyodu belirlenmiş, yağ analizi raporu alınmış."),
        ]
        parts = [
            RequiredPart("FLT-HP-01", "Basınç hattı filtresi", 5, estimated_cost_try=450.0),
            RequiredPart("HYD-OIL-68", "Hidrolik yağı ISO VG 68", 20, estimated_cost_try=350.0),
        ]
        return immediate, short_term, long_term, parts

    def _template_pressure_anomaly(self) -> tuple[list[Action], list[Action], list[Action], list[RequiredPart]]:
        immediate = [
            Action(1, PriorityLevel.IMMEDIATE, "Makineyi durdur, basıncı sıfırla ve basınç regülatörü ayarını kontrol et.", 10, DifficultyLevel.EASY,
                   ["Basınç göstergesi", "Tornavida", "Anahtar seti"], [],
                   ["YÜKSEK BASINÇ - Koruyucu ekipman giyin!", "Basınç sıfırlandığından emin olun."], "Basınç regülatörü ayarı normal aralıkta."),
        ]
        short_term = [
            Action(1, PriorityLevel.SHORT_TERM, "Oransal valf bobin direncini ve valf hareketini kontrol et.", 40, DifficultyLevel.MEDIUM,
                   ["Multimetre", "13mm anahtar", "Valf test cihazı"], [RequiredPart("PV-110", "Oransal valf bobini", 1)],
                   ["Basınç sıfırlandığından emin olun."], "Bobin direnci normal, valf hareketi akıcı."),
            Action(2, PriorityLevel.SHORT_TERM, "Hidrolik pompa basınç ayarlarını ve pompa debisini kontrol et.", 30, DifficultyLevel.MEDIUM,
                   ["Basınç test kiti", "Debi ölçer"], [], ["Pompa çalışırken koruyucu gözlük takın."], "Pompa basınç ve debi değerleri normal aralıkta."),
        ]
        long_term = [
            Action(1, PriorityLevel.LONG_TERM, "Basınç sensör kalibrasyonu ve hidrolik devre basınç testi planla.", 90, DifficultyLevel.HARD,
                   ["Kalibrasyon pompası", "Dijital basınç referansı", "Kayıt cihazı"], [], [],
                   "Tüm basınç sensörleri kalibre edilmiş, devre basınç testi tamamlanmış."),
        ]
        parts = [RequiredPart("PV-110", "Oransal valf bobini", 1, estimated_cost_try=850.0)]
        return immediate, short_term, long_term, parts

    def _template_temperature_high(self) -> tuple[list[Action], list[Action], list[Action], list[RequiredPart]]:
        immediate = [
            Action(1, PriorityLevel.IMMEDIATE, "Makineyi durdur ve soğutma sistemini kontrol et. Fan, pompa, radyatör.", 10, DifficultyLevel.EASY,
                   ["Fener", "Temiz bez", "Fırça"], [],
                   ["YÜKSEK SICAKLIK - Yanık riski! Eldiven giyin.", "MAKİNEYİ DURDURMADAN MÜDAHALE ETMEYİN!"],
                   "Soğutma fanı dönüyor, pompa çalışıyor, radyatör temiz."),
        ]
        short_term = [
            Action(1, PriorityLevel.SHORT_TERM, "İş yükünü geçici olarak düşür. Döngü sürelerini ve basınç profilini optimize et.", 20, DifficultyLevel.MEDIUM,
                   ["Operatör paneli", "Proses mühendisi"], [], [], "İş yükü azaltılmış, sıcaklık artış hızı yavaşlamış."),
            Action(2, PriorityLevel.SHORT_TERM, "Yağ numunesi al ve viskozite / renk / koku kontrolü yap.", 15, DifficultyLevel.EASY,
                   ["Yağ numune şişesi", "Viskozite test kiti"], [RequiredPart("HYD-OIL-68", "Hidrolik yağı ISO VG 68", 50)],
                   ["Yağ sıcaklığı düşükken numune alın."], "Yağ numunesi alınmış, viskozite normal aralıkta."),
        ]
        long_term = [
            Action(1, PriorityLevel.LONG_TERM, "Soğutma sistemi kapasite analizi yap. Radyatör, fan, pompa boyutlandırması yeterli mi?", 120, DifficultyLevel.HARD,
                   ["Isı transfer hesaplayıcı", "Akış ölçer", "Termokamera"], [], [],
                   "Soğutma sistemi kapasitesi doğrulanmış, gerekirse upgrade planı hazırlanmış."),
        ]
        parts = [RequiredPart("HYD-OIL-68", "Hidrolik yağı ISO VG 68", 50, estimated_cost_try=875.0)]
        return immediate, short_term, long_term, parts

    def _template_mechanical_jam(self) -> tuple[list[Action], list[Action], list[Action], list[RequiredPart]]:
        immediate = [
            Action(1, PriorityLevel.IMMEDIATE, "ACİL STOP! Makineyi durdur, enerjiyi kes, basıncı sıfırla. Sıkışma bölgesini güvenlik şeridiyle çevir.", 5, DifficultyLevel.EASY,
                   ["Acil Stop Butonu", "Güvenlik şeridi", "Uyarı levhası"], [],
                   ["MAKİNEYİ DURDURMADAN MÜDAHALE ETMEYİN!", "Enerji kesilmeden ve LOTO uygulanmadan içeri girmeyin!"],
                   "Makine durmuş, enerji kesilmiş, basınç 0, bölge şeritlenmiş."),
        ]
        short_term = [
            Action(1, PriorityLevel.SHORT_TERM, "Sıkışma bölgesini aç, yabancı cisim / gevşek parça / birikinti var mı temizle.", 30, DifficultyLevel.MEDIUM,
                   ["El feneri", "Kazıyıcı", "Vakumlu temizleyici", "Temiz bez"], [],
                   ["Enerji kesilmeden ve LOTO uygulanmadan içeri girmeyin!"], "Sıkışma bölgesi temiz, yabancı cisim yok."),
            Action(2, PriorityLevel.SHORT_TERM, "Rayları, kızakları ve pimleri gresle. Aşınma veya deformasyon var mı kontrol et.", 25, DifficultyLevel.MEDIUM,
                   ["Gres pompası", "Fener", "Kumpas"], [RequiredPart("GREASE-LITH", "Lityum gres (kartuş)", 2)],
                   ["Hareketli parçalara dokunurken dikkatli olun."], "Tüm kılavuzlar greslenmiş, aşınma ölçümleri normal."),
        ]
        long_term = [
            Action(1, PriorityLevel.LONG_TERM, "Mekanik hizalama (alignment) ölçümü yap. Kayma, eğrilik, aşınma var mı?", 90, DifficultyLevel.HARD,
                   ["Lazer hizalama cihazı", "Kumpas", "Mikrometre"], [], [],
                   "Hizalama değerleri tolerans içinde, gerekirse ayarlanmış."),
        ]
        parts = [RequiredPart("GREASE-LITH", "Lityum gres (kartuş)", 2, estimated_cost_try=120.0)]
        return immediate, short_term, long_term, parts

    def _template_generic(self) -> tuple[list[Action], list[Action], list[Action], list[RequiredPart]]:
        immediate = [
            Action(1, PriorityLevel.IMMEDIATE, "Makineyi durdur, basıncı sıfırla ve genel görsel kontrol yap.", 10, DifficultyLevel.EASY,
                   ["Fener", "Temiz bez", "Kontrol listesi"], [],
                   ["MAKİNEYİ DURDURMADAN MÜDAHALE ETMEYİN!", "Basınç sıfırlandığından emin olun."],
                   "Makine durmuş, görsel kontrol tamamlanmış, belirgin arıza yok."),
        ]
        short_term = [
            Action(1, PriorityLevel.SHORT_TERM, "Tüm sensör değerlerini kaydet ve trend grafiğini incele.", 20, DifficultyLevel.EASY,
                   ["Bilgisayar", "Trend yazılımı"], [], [], "Son 2 saatin tüm sensör verileri incelenmiş, anormallik not edilmiş."),
        ]
        long_term = [
            Action(1, PriorityLevel.LONG_TERM, "Önleyici bakım programına göre periyodik kontrol ve yağ/filtre planlaması yap.", 60, DifficultyLevel.MEDIUM,
                   ["Bakım planlama yazılımı"], [], [],
                   "Önleyici bakım takvimi güncellenmiş, bir sonraki kontrol tarihi belirlenmiş."),
        ]
        return immediate, short_term, long_term, []

    # ─── Güvenlik Uyarıları Üretimi ──────────────────────────────────────────

    def _generate_safety_warnings(self, context: dict) -> list[str]:
        """Sensör değerlerine göre uygun güvenlik uyarıları üretir."""
        warnings: list[str] = []
        sensor_states = context.get("sensor_states", {})
        for key, s in sensor_states.items():
            if "pressure" in key.lower():
                val = s.get("value")
                if val is not None and val > 80:
                    warnings.append("YÜKSEK BASINÇ - Koruyucu ekipman giyin!")
                    break
        temp = sensor_states.get("oil_tank_temperature")
        if temp:
            val = temp.get("value")
            if val is not None and val > 45:
                warnings.append("YÜKSEK SICAKLIK - Yanık riski! Eldiven giyin.")
        warnings.append("MAKİNEYİ DURDURMADAN MÜDAHALE ETMEYİN!")
        warnings.append("Basınç sıfırlandığından emin olun.")
        seen: set[str] = set()
        unique: list[str] = []
        for w in warnings:
            if w not in seen:
                seen.add(w)
                unique.append(w)
        return unique


# ─── Singleton ────────────────────────────────────────────────────────────────
_action_instance: ActionAgent | None = None
_action_lock = threading.Lock()


def action_plan_to_dict(plan: ActionPlan) -> dict:
    """ActionPlan'ı JSON-uyumlu dict'e çevirir (Enum'ları string yapar)."""
    import dataclasses

    d = dataclasses.asdict(plan)
    # Enum değerlerini string'e çevir
    for group_key in ("immediate_actions", "short_term_actions", "long_term_actions"):
        for action in d.get(group_key, []):
            if isinstance(action.get("priority"), PriorityLevel):
                action["priority"] = action["priority"].value
            elif hasattr(action.get("priority"), "value"):
                action["priority"] = action["priority"].value
            if isinstance(action.get("difficulty"), DifficultyLevel):
                action["difficulty"] = action["difficulty"].value
            elif hasattr(action.get("difficulty"), "value"):
                action["difficulty"] = action["difficulty"].value
    return d


def get_action_agent() -> ActionAgent:
    """Global Eylem Ajanı örneğini döner (lazy init, thread-safe)."""
    global _action_instance
    with _action_lock:
        if _action_instance is None:
            _action_instance = ActionAgent()
    return _action_instance
