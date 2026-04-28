"""
report_agent.py — Rapor Ajanı
═══════════════════════════════
4 farklı formatta rapor üreten uzman ajan. Teknisyene detaylı,
müdüre özet, denetçiye resmi, SMS'e kısa mesaj.

Gemini API ile çalışır, API devre dışı kaldığında yerel şablon
motoruna düşerek çalışmaya devam eder. Teknisyen raporu tamamen
template-based (LLM'siz), diğer raporlar zenginleştirilebilir.

Fabrika benzetmesi: Fabrika sekreteri / raporlama uzmanı.
Ustanın bulduğu arızayı herkesin anlayacağı dilde yazar:
- Teknisyene: "Şurada kaçak var, şunu yap"
- Müdüre: "Duruş 45 dk, maliyet 450 TL"
- Denetçiye: "Resmi rapor, tarih, imza yeri"
- SMS: "⚠️ HPR001 KRİTİK: İç kaçak, 3.5 saat"

Kullanım:
    from src.analysis.report_agent import get_report_agent
    agent = get_report_agent()
    sonuc = await agent.generate_report(context, prior_results)
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
import random
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

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

log = logging.getLogger("report_agent")

# ─── Enumerasyonlar ──────────────────────────────────────────────────────────


class ReportMode(Enum):
    """
    Rapor üretim modu.

    Fabrika benzetmesi: Sekreterin masasındaki 4 farklı rapor şablonu.
    Her kitleye göre ayrı format, ayrı dil, ayrı uzunluk.
    """

    TECHNICIAN = "technician"    # Teknisyen: Detaylı, teknik, adım adım
    MANAGER = "manager"          # Yönetici: Özet, maliyet odaklı
    FORMAL = "formal"            # Formal: Resmi, denetim amaçlı
    EMERGENCY = "emergency"      # Acil Alert: Kısa, SMS uyumlu (280 karakter)


# ─── Veri Yapıları ───────────────────────────────────────────────────────────


@dataclass
class TechnicianReport:
    """
    Teknisyen raporu — detaylı, teknik, adım adım.

    Fabrika benzetmesi: Ustanın el yazısıyla yazdığı tam teşhis ve
    tamir talimatları. Her somun, her conta, her adım yazılı.
    """

    title: str                    # "HPR001 Arıza Raporu - Hidrolik İç Kaçak"
    summary: str                  # 2-3 cümle özet
    diagnosis_section: str        # Teşhis detayları (markdown)
    root_cause_section: str       # Kök neden analizi (markdown)
    action_plan_section: str      # Adım adım eylem planı (markdown)
    prediction_section: str       # Tahmin ve zaman bilgisi (markdown)
    sensor_data_section: str      # Sensör verileri tablosu (markdown)
    safety_warnings: list[str]    # Güvenlik uyarıları
    full_markdown: str            # Tüm rapor birleştirilmiş markdown


@dataclass
class ManagerReport:
    """
    Yönetici raporu — özet, maliyet odaklı.

    Fabrika benzetmesi: Müdürün masasına bırakılan tek sayfalık özet.
    "Ne oldu, ne kadar süre, ne kadar para, ne yapmalıyız?"
    """

    title: str                    # "HPR001 Durum Özeti"
    executive_summary: str        # 1 paragraf, en önemli bilgi
    risk_level: str               # "YÜKSEK", "ORTA", "DÜŞÜK"
    estimated_downtime: str       # "Tahmini duruş: 45 dakika"
    estimated_cost: str           # "Tahmini maliyet: 450 TL"
    recommended_action: str       # "Acil müdahale gerekli"
    full_markdown: str            # Tam rapor markdown


@dataclass
class FormalReport:
    """
    Formal rapor — resmi, denetim amaçlı.

    Fabrika benzetmesi: ISO denetçisine verilen resmi evrak.
    Tarih, numara, imza yeri, her şey kayıtlı ve takip edilebilir.
    """

    report_id: str                # "RPT-2026-04-24-001"
    title: str                    # "Resmi Arıza Raporu"
    date: str                     # "24 Nisan 2026"
    machine_info: str             # Makine bilgileri
    incident_description: str     # Olay tanımı
    analysis_results: str         # Analiz sonuçları
    corrective_actions: str       # Düzeltici faaliyetler
    preventive_actions: str       # Önleyici faaliyetler
    signatures_section: str       # İmza bölümü (placeholder)
    full_markdown: str            # Tam rapor markdown


@dataclass
class EmergencyAlert:
    """
    Acil alert — kısa, SMS uyumlu (280 karakter).

    Fabrika benzetmesi: Fabrika anons sisteminden yapılan kısa uyarı.
    "HPR001'de kritik durum, bakım ekibi hemen sahaya!"
    """

    alert_text: str               # Max 280 karakter
    machine_id: str
    severity: str                 # "KRİTİK", "UYARI"
    timestamp: str


@dataclass
class ReportResult:
    """
    Rapor Ajanı'nın nihai çıktısı.

    Fabrika benzetmesi: Sekreterin hazırladığı 4 farklı raporun
    hepsini içeren zarf. Herkes kendi raporunu alır.
    """

    machine_id: str
    timestamp: str
    report_id: str                # "RPT-2026-04-24-001"

    # 4 rapor modu
    technician_report: Optional[TechnicianReport] = None
    manager_report: Optional[ManagerReport] = None
    formal_report: Optional[FormalReport] = None
    emergency_alert: Optional[EmergencyAlert] = None

    # Hangi modlar üretildi
    generated_modes: list[str] = field(default_factory=list)

    # Meta
    execution_time_sec: float = 0.0
    agent_version: str = "1.0"


# ─── Sistem Promptu (Sadece Manager raporu için) ─────────────────────────────

_MANAGER_SYSTEM_PROMPT = """Sen Codlean MES fabrikasının raporlama uzmanısın.
Yönetici özetleri yazarsın. Kısa, öz, maliyet ve risk odaklı.
Teknik detaylara girme, sonuç ve eylem odaklı ol.
Türkçe yaz. Sadece özet metin üret, başka metin yazma.
"""


# ─── Ana Sınıf ───────────────────────────────────────────────────────────────


class ReportAgent:
    """
    Rapor Ajanı - 4 farklı formatta rapor üretir.

    Fabrika benzetmesi: Fabrika sekreteri / raporlama uzmanı.
    Ustanın bulduğu arızayı herkesin anlayacağı dilde yazar.
    API'ye ulaşamazsa şablonlarla çalışmaya devam eder,
    rapor asla boş kalmaz.
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

        log.info("[REPORT_INIT] dotenv yüklendi: %s", _dotenv_loaded)
        log.info("[REPORT_INIT] API Key mevcut: %s", bool(key))
        if key:
            log.info("[REPORT_INIT] API Key ilk 8 karakter: %s...", key[:8])

        if not key:
            self._init_error = "GEMINI_API_KEY tanımlı değil. .env dosyasını kontrol edin."
            log.warning("[REPORT_INIT] %s", self._init_error)
            return

        try:
            from google import genai

            self._client = genai.Client(api_key=key)
            self._ready = True
            log.info("[REPORT_INIT] ✅ Rapor Ajanı hazır (%s)", self.MODEL_NAME)
        except ImportError:
            self._init_error = (
                "google-genai kütüphanesi kurulu değil. 'pip install google-genai' çalıştırın."
            )
            log.warning("[REPORT_INIT] %s", self._init_error)
        except Exception as e:
            self._init_error = f"Gemini başlatılamadı: {e}"
            log.warning("[REPORT_INIT] %s", self._init_error)

    @property
    def is_ready(self) -> bool:
        """Gemini API hazır mı?"""
        return self._ready

    # ─── Ana Giriş Noktası ───────────────────────────────────────────────────

    async def generate_report(
        self,
        context: dict,
        prior_results: dict,
        modes: list[ReportMode] | None = None,
    ) -> ReportResult:
        """
        Makine bağlamı ve önceki ajan sonuçlarına göre rapor üretir.

        Fabrika benzetmesi: Sekreter tüm uzmanların raporlarını alır,
        her kitleye uygun formatta yeniden yazar ve zarfa koyar.
        API çalışmazsa şablonlarla çalışır, rapor boş kalmaz.

        Args:
            context: pipeline.context_builder.build() çıktısı.
            prior_results: Diğer ajanların sonuçlarını içeren sözlük.
            modes: Hangi rapor modları üretilecek. None = hepsi.

        Returns:
            ReportResult: Yapılandırılmış rapor çıktısı.
        """
        start_time = time.monotonic()
        machine_id = context.get("machine_id", "UNKNOWN")
        timestamp = context.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        log.info("[REPORT START] %s — rapor üretiliyor", machine_id)

        report_id = self._generate_report_id()
        result = ReportResult(
            machine_id=machine_id,
            timestamp=timestamp,
            report_id=report_id,
        )

        # Varsayılan: tüm modlar
        if modes is None:
            modes = [ReportMode.TECHNICIAN, ReportMode.MANAGER, ReportMode.FORMAL, ReportMode.EMERGENCY]

        for mode in modes:
            try:
                if mode == ReportMode.TECHNICIAN:
                    log.info("[REPORT] %s — teknisyen raporu oluşturuluyor", machine_id)
                    result.technician_report = self._build_technician_report(context, prior_results, report_id=report_id)
                    result.generated_modes.append("technician")

                elif mode == ReportMode.MANAGER:
                    log.info("[REPORT] %s — yönetici özeti oluşturuluyor", machine_id)
                    result.manager_report = await self._build_manager_report(context, prior_results)
                    result.generated_modes.append("manager")

                elif mode == ReportMode.FORMAL:
                    log.info("[REPORT] %s — formal rapor oluşturuluyor", machine_id)
                    result.formal_report = self._build_formal_report(context, prior_results, report_id=report_id)
                    result.generated_modes.append("formal")

                elif mode == ReportMode.EMERGENCY:
                    log.info("[REPORT] %s — acil alert oluşturuluyor", machine_id)
                    result.emergency_alert = self._build_emergency_alert(context, prior_results)
                    result.generated_modes.append("emergency")

            except Exception as e:
                log.exception("[REPORT] %s — %s raporu hatası: %s", machine_id, mode.value, e)

        result.execution_time_sec = round(time.monotonic() - start_time, 2)
        log.info(
            "[REPORT END] %s — %d rapor modu tamamlandı (%.2fs)",
            machine_id,
            len(result.generated_modes),
            result.execution_time_sec,
        )
        return result

    # ─── Rapor ID Üretimi ────────────────────────────────────────────────────

    def _generate_report_id(self) -> str:
        """
        Benzersiz rapor ID'si üretir.

        Format: RPT-YYYY-MM-DD-XXX (XXX = 1-999 arası sıra numarası)
        """
        now = datetime.now()
        seq = random.randint(1, 999)
        return f"RPT-{now.strftime('%Y-%m-%d')}-{seq:03d}"

    # ─── Bilgi Çıkarma Yardımcıları (Graceful) ───────────────────────────────

    def _extract_diagnosis_info(self, prior_results: dict) -> dict:
        """Önceki sonuçlardan teşhis bilgisini güvenli şekilde çıkarır."""
        diagnosis = prior_results.get("diagnosis") or {}
        if not isinstance(diagnosis, dict):
            diagnosis = {}

        primary = diagnosis.get("primary_diagnosis") or {}
        if not isinstance(primary, dict):
            primary = {}

        top = diagnosis.get("top_diagnoses") or []
        if isinstance(top, list) and len(top) > 0 and isinstance(top[0], dict):
            top0 = top[0]
        else:
            top0 = {}

        fault_type = primary.get("fault_type") or top0.get("fault_type") or "Bilinmeyen Arıza"
        confidence = primary.get("confidence") or top0.get("confidence") or 0.5
        description = primary.get("description_tr") or top0.get("description_tr") or "Açıklama mevcut değil."
        recommendation = primary.get("recommended_action") or top0.get("recommended_action") or "Teknisyen kontrolü önerilir."

        return {
            "fault_type": fault_type,
            "confidence": confidence,
            "description": description,
            "recommendation": recommendation,
            "reasoning_steps": diagnosis.get("reasoning_steps", []),
            "sensor_anomalies": diagnosis.get("sensor_anomalies", {}),
            "pattern_description": diagnosis.get("pattern_description_tr", ""),
        }

    def _extract_root_cause_info(self, prior_results: dict) -> dict:
        """Önceki sonuçlardan kök neden bilgisini güvenli şekilde çıkarır."""
        root_cause = prior_results.get("root_cause") or {}
        if not isinstance(root_cause, dict):
            root_cause = {}

        causal_chain = root_cause.get("causal_chain", [])
        if not isinstance(causal_chain, list):
            causal_chain = []

        return {
            "primary_root_cause": root_cause.get("primary_root_cause", "Belirlenemedi"),
            "root_cause_confidence": root_cause.get("root_cause_confidence", 0.5),
            "immediate_cause": root_cause.get("immediate_cause", ""),
            "causal_chain": causal_chain,
            "evidence_summary": root_cause.get("evidence_summary", []),
            "physics_rules": root_cause.get("physics_rules_matched", []),
            "maintenance_recommendations": root_cause.get("maintenance_recommendations", []),
        }

    def _extract_prediction_info(self, prior_results: dict) -> dict:
        """Önceki sonuçlardan tahmin bilgisini güvenli şekilde çıkarır."""
        prediction = prior_results.get("prediction") or {}
        if not isinstance(prediction, dict):
            prediction = {}

        eta_list = prediction.get("eta_predictions", [])
        if not isinstance(eta_list, list):
            eta_list = []

        scenarios = prediction.get("scenarios", [])
        if not isinstance(scenarios, list):
            scenarios = []

        return {
            "overall_status": prediction.get("overall_status", "normal"),
            "time_to_critical_min": prediction.get("time_to_critical_min"),
            "time_to_critical_human": prediction.get("time_to_critical_human", ""),
            "summary": prediction.get("summary_tr", ""),
            "urgency": prediction.get("urgency_level", "monitor"),
            "recommended_action": prediction.get("recommended_action", ""),
            "eta_predictions": eta_list,
            "scenarios": scenarios,
        }

    def _extract_action_info(self, prior_results: dict) -> dict:
        """Önceki sonuçlardan eylem planı bilgisini güvenli şekilde çıkarır."""
        action = prior_results.get("action") or {}
        if not isinstance(action, dict):
            action = {}

        immediate = action.get("immediate_actions", [])
        short_term = action.get("short_term_actions", [])
        long_term = action.get("long_term_actions", [])

        if not isinstance(immediate, list):
            immediate = []
        if not isinstance(short_term, list):
            short_term = []
        if not isinstance(long_term, list):
            long_term = []

        total_time = action.get("total_estimated_downtime_min", 0)
        total_cost = action.get("total_parts_cost_try")
        safety = action.get("critical_safety_warnings", [])

        return {
            "immediate_actions": immediate,
            "short_term_actions": short_term,
            "long_term_actions": long_term,
            "total_downtime_min": total_time,
            "total_cost": total_cost,
            "safety_warnings": safety if isinstance(safety, list) else [],
            "success_criteria": action.get("success_criteria", ""),
        }

    # ─── Teknisyen Raporu (Template-Based, NO LLM) ───────────────────────────

    def _build_technician_report(self, context: dict, prior_results: dict, report_id: str) -> TechnicianReport:
        """
        En detaylı rapor. Önceki ajan sonuçlarından markdown şablonuyla üretir.

        Fabrika benzetmesi: Ustanın el yazısıyla yazdığı tam teşhis ve
        tamir talimatları. Her somun, her conta, her adım yazılı.
        LLM gerektirmez — bilgi zaten masada.
        """
        machine_id = context.get("machine_id", "UNKNOWN")
        diagnosis = self._extract_diagnosis_info(prior_results)
        root_cause = self._extract_root_cause_info(prior_results)
        prediction = self._extract_prediction_info(prior_results)
        action = self._extract_action_info(prior_results)

        fault_type = diagnosis["fault_type"]
        title = f"🔧 {machine_id} Arıza Raporu - {fault_type}"
        now_str = datetime.now().strftime("%d %B %Y, %H:%M")
        # Güvenlik uyarıları
        safety_warnings = list(action["safety_warnings"])
        if not safety_warnings:
            safety_warnings = [
                "MAKİNEYİ DURDURMADAN MÜDAHALE ETMEYİN!",
                "Basınç sıfırlandığından emin olun.",
            ]
        safety_md = "\n".join(f"- {w}" for w in safety_warnings)

        # Teşhis bölümü
        conf_pct = int(diagnosis["confidence"] * 100)
        diagnosis_md = f"""**Ana Teşhis:** {fault_type} (Güven: %{conf_pct})

Belirtiler:
- {diagnosis['description']}"""

        # Sensör anormallikleri varsa ekle
        anomalies = diagnosis.get("sensor_anomalies", {})
        if anomalies and isinstance(anomalies, dict):
            diagnosis_md += "\n"
            for key, sa in anomalies.items():
                if isinstance(sa, dict):
                    curr = sa.get("current_value", "N/A")
                    normal = sa.get("normal_value", "N/A")
                    dev = sa.get("deviation_pct", 0)
                    name = sa.get("sensor_name", key)
                    diagnosis_md += f"\n- {name}: {curr} (Normal: {normal}, {dev:+.0f}% sapma)"

        # Kök neden bölümü
        chain = root_cause["causal_chain"]
        if chain and len(chain) >= 1:
            root_md = f"**Kök Neden:** {root_cause['primary_root_cause']}\n\n5-Why Analizi:\n"
            for link in chain[:5]:
                if isinstance(link, dict):
                    q = link.get("question", "Neden?")
                    a = link.get("answer", "Bilinmiyor.")
                    root_md += f"\n1. {q} → {a}"
        else:
            root_md = f"**Kök Neden:** {root_cause['primary_root_cause']}\n\nDetaylı analiz mevcut değil."

        # Eylem planı bölümü
        action_md = ""
        if action["immediate_actions"]:
            action_md += "\n### ACİL (0-15 dakika)\n"
            for i, act in enumerate(action["immediate_actions"][:3], 1):
                if isinstance(act, dict):
                    desc = act.get("description_tr", "Açıklama yok.")
                    t = act.get("estimated_time_min", 5)
                    d = act.get("difficulty", "Kolay")
                    action_md += f"{i}. {desc} ({t} dk, {d})\n"

        if action["short_term_actions"]:
            action_md += "\n### KISA VADELİ (1-2 saat)\n"
            for i, act in enumerate(action["short_term_actions"][:3], 1):
                if isinstance(act, dict):
                    desc = act.get("description_tr", "Açıklama yok.")
                    t = act.get("estimated_time_min", 30)
                    d = act.get("difficulty", "Orta")
                    parts = act.get("required_parts", [])
                    part_str = ""
                    if parts and isinstance(parts, list) and isinstance(parts[0], dict):
                        pnum = parts[0].get("part_number", "")
                        pname = parts[0].get("name", "")
                        if pnum or pname:
                            part_str = f"\n   - Parça: {pnum} {pname}"
                    action_md += f"{i}. {desc} ({t} dk, {d}){part_str}\n"

        if action["long_term_actions"]:
            action_md += "\n### UZUN VADELİ (1 hafta)\n"
            for i, act in enumerate(action["long_term_actions"][:2], 1):
                if isinstance(act, dict):
                    desc = act.get("description_tr", "Açıklama yok.")
                    t = act.get("estimated_time_min", 60)
                    d = act.get("difficulty", "Zor")
                    action_md += f"{i}. {desc} ({t} dk, {d})\n"

        if not action_md:
            action_md = "Eylem planı mevcut değil. Teknisyen kontrolü önerilir."

        # Tahmin bölümü
        pred_md = ""
        if prediction["time_to_critical_human"]:
            pred_md += f"- **Kritik süre:** {prediction['time_to_critical_human']}\n"
        if prediction["summary"]:
            pred_md += f"- **Durum:** {prediction['summary']}\n"
        if prediction["recommended_action"]:
            pred_md += f"- **Öneri:** {prediction['recommended_action']}\n"
        if not pred_md:
            pred_md = "Tahmin verisi mevcut değil."

        # Sensör verileri tablosu
        sensor_states = context.get("sensor_states", {})
        sensor_md = "| Sensör | Değer | Limit | Durum |\n|--------|-------|-------|-------|"
        if sensor_states and isinstance(sensor_states, dict):
            for key, s in sensor_states.items():
                if isinstance(s, dict):
                    name = s.get("turkish_name", key)
                    val = s.get("value", "N/A")
                    unit = s.get("unit", "")
                    limit = s.get("limit_max", "N/A")
                    lpct = s.get("limit_pct", 0)
                    if lpct >= 100:
                        status = "🔴 KRİTİK"
                    elif lpct >= 85:
                        status = "🟡 UYARI"
                    else:
                        status = "🟢 Normal"
                    sensor_md += f"\n| {name} | {val}{unit} | {limit}{unit} | {status} |"
        else:
            sensor_md += "\n| Veri yok | - | - | - |"

        # Tam markdown
        full_md = f"""# {title}

📅 Tarih: {now_str}
🆔 Rapor ID: {report_id}

---

## ⚠️ Güvenlik Uyarıları
{safety_md}

---

## 🩺 Teşhis
{diagnosis_md}

---

## 🔍 Kök Neden
{root_md}

---

## 🚨 Eylem Planı
{action_md}

---

## ⏱️ Tahmin
{pred_md}

---

## 📊 Sensör Verileri
{sensor_md}
"""

        summary = f"{machine_id} makinesinde {fault_type} tespit edildi. Güven: %{conf_pct}. "
        if prediction["time_to_critical_human"]:
            summary += f"Tahmini kritik süre: {prediction['time_to_critical_human']}."
        else:
            summary += "Acil müdahale gerekebilir."

        return TechnicianReport(
            title=title,
            summary=summary,
            diagnosis_section=diagnosis_md,
            root_cause_section=root_md,
            action_plan_section=action_md,
            prediction_section=pred_md,
            sensor_data_section=sensor_md,
            safety_warnings=safety_warnings,
            full_markdown=full_md,
        )

    # ─── Yönetici Raporu (Özet, Maliyet Odaklı) ──────────────────────────────

    async def _build_manager_report(self, context: dict, prior_results: dict) -> ManagerReport:
        """
        Yönetici özeti. LLM ile zenginleştirilebilir, şablon fallback vardır.

        Fabrika benzetmesi: Müdürün masasına bırakılan tek sayfalık özet.
        "Ne oldu, ne kadar süre, ne kadar para, ne yapmalıyız?"
        """
        machine_id = context.get("machine_id", "UNKNOWN")
        diagnosis = self._extract_diagnosis_info(prior_results)
        prediction = self._extract_prediction_info(prior_results)
        action = self._extract_action_info(prior_results)

        fault_type = diagnosis["fault_type"]
        title = f"📊 {machine_id} Yönetici Özeti"

        # Risk seviyesi belirle
        urgency = prediction["urgency"]
        if urgency == "immediate":
            risk_level = "🔴 YÜKSEK RİSK"
        elif urgency == "soon":
            risk_level = "🟡 ORTA RİSK"
        else:
            risk_level = "🟢 DÜŞÜK RİSK"

        # Duruş ve maliyet
        downtime_min = action["total_downtime_min"]
        if downtime_min > 0:
            if downtime_min < 60:
                downtime_str = f"Tahmini duruş: {downtime_min} dakika"
            else:
                hours = downtime_min / 60.0
                downtime_str = f"Tahmini duruş: {hours:.1f} saat ({downtime_min} dk)"
        else:
            downtime_str = "Tahmini duruş: Değerlendiriliyor"

        total_cost = action["total_cost"]
        if total_cost is not None and total_cost > 0:
            cost_str = f"Tahmini maliyet: ~{total_cost:,.0f} TL"
        else:
            # Varsayılan maliyet tahmini
            cost_str = "Tahmini maliyet: ~450 TL (parça + işçilik)"

        rec_action = prediction["recommended_action"] or action["success_criteria"] or "Teknisyen kontrolü önerilir."

        # LLM ile zenginleştirme dene
        executive_summary = ""
        if self._ready:
            try:
                prompt = self._build_manager_prompt(machine_id, fault_type, prediction, action)
                llm_text = await asyncio.get_event_loop().run_in_executor(
                    None, self._call_llm_sync, prompt
                )
                if llm_text and not llm_text.startswith(("⏰", "🚫", "🔑", "🌐", "❌")):
                    executive_summary = llm_text.strip()
            except Exception as e:
                log.warning("[MANAGER] LLM zenginleştirme hatası: %s", e)

        # LLM başarısız olursa şablon özet
        if not executive_summary:
            exec_summary = f"""{machine_id} makinesinde {fault_type} tespit edildi.
Müdahale edilmezse {prediction['time_to_critical_human'] or 'belirsiz süre içinde'} üretim durabilir.
Bakım ekibinin acil yönlendirilmesi önerilir."""
        else:
            exec_summary = executive_summary

        full_md = f"""# {title}

**Durum:** {risk_level}

**Özet:** {exec_summary}

| Bilgi | Değer |
|-------|-------|
| Tahmini duruş | {downtime_str} |
| Parça maliyeti | {cost_str} |
| Risk seviyesi | {risk_level} |
| Aciliyet | {rec_action} |

**Öneri:** Bakım ekibini yönlendirin, parça stokta mevcut.
"""

        return ManagerReport(
            title=title,
            executive_summary=exec_summary,
            risk_level=risk_level.replace("🔴 ", "").replace("🟡 ", "").replace("🟢 ", ""),
            estimated_downtime=downtime_str,
            estimated_cost=cost_str,
            recommended_action=rec_action,
            full_markdown=full_md,
        )

    def _build_manager_prompt(
        self, machine_id: str, fault_type: str, prediction: dict, action: dict
    ) -> str:
        """Yönetici özeti için LLM prompt'u oluşturur."""
        lines = [
            "Bir fabrika yöneticisine kısa, öz, maliyet odaklı bir durum özeti yaz.",
            "Teknik detaylara girme. 1 paragraf, 3-4 cümle.",
            "",
            f"Makine: {machine_id}",
            f"Arıza: {fault_type}",
            f"Tahmini kritik süre: {prediction['time_to_critical_human'] or 'belirsiz'}",
            f"Tahmini duruş: {action['total_downtime_min']} dakika",
            f"Tahmini maliyet: {action['total_cost'] or 'belirsiz'} TL",
            "",
            "ÖZET (Türkçe, 1 paragraf):",
        ]
        return "\n".join(lines)

    # ─── Formal Rapor (Denetim Amacılı) ──────────────────────────────────────

    def _build_formal_report(self, context: dict, prior_results: dict, report_id: str) -> FormalReport:
        """
        Resmi, denetim amaçlı rapor. Template-based.

        Fabrika benzetmesi: ISO denetçisine verilen resmi evrak.
        Tarih, numara, imza yeri, her şey kayıtlı.
        """
        machine_id = context.get("machine_id", "UNKNOWN")
        diagnosis = self._extract_diagnosis_info(prior_results)
        root_cause = self._extract_root_cause_info(prior_results)
        prediction = self._extract_prediction_info(prior_results)
        action = self._extract_action_info(prior_results)

        now_str = datetime.now().strftime("%d %B %Y")
        now_iso = datetime.now().strftime("%Y-%m-%d")
        title = "Resmi Arıza Raporu"

        fault_type = diagnosis["fault_type"]

        machine_info = f"""- Makine ID: {machine_id}
- Tip: Hidrolik Pres
- Konum: Üretim Hattı
- Rapor No: {report_id}"""

        incident_desc = f"""{now_str} tarihinde {machine_id} makinesinde {fault_type} tespit edilmiştir.

Sensör verilerindeki anormallikler sistem tarafından otomatik olarak algılanmış ve analiz edilmiştir.
Teşhis güveni: %{int(diagnosis['confidence'] * 100)}."""

        analysis_md = f"""**Teşhis:** {fault_type}

**Kök Neden:** {root_cause['primary_root_cause']}

**Fiziksel Kanıtlar:**
"""
        for ev in root_cause["evidence_summary"][:5]:
            analysis_md += f"\n- {ev}"

        if not root_cause["evidence_summary"]:
            analysis_md += "\n- Sensör verileri değerlendirilmiştir."

        # Düzeltici faaliyetler
        corrective_md = ""
        if action["immediate_actions"]:
            corrective_md += "**Acil Düzeltici Faaliyetler:**\n"
            for act in action["immediate_actions"][:3]:
                if isinstance(act, dict):
                    corrective_md += f"\n- {act.get('description_tr', '')}"
        if action["short_term_actions"]:
            corrective_md += "\n\n**Kısa Vadeli Düzeltici Faaliyetler:**\n"
            for act in action["short_term_actions"][:3]:
                if isinstance(act, dict):
                    corrective_md += f"\n- {act.get('description_tr', '')}"

        if not corrective_md:
            corrective_md = "Düzeltici faaliyetler planlanmaktadır."

        # Önleyici faaliyetler
        preventive_md = ""
        if root_cause["maintenance_recommendations"]:
            preventive_md = "**Önleyici Faaliyetler:**\n"
            for rec in root_cause["maintenance_recommendations"][:5]:
                preventive_md += f"\n- {rec}"
        else:
            preventive_md = "Önleyici bakım programının gözden geçirilmesi önerilir."

        # Tahmin bilgisi
        if prediction["time_to_critical_human"]:
            preventive_md += f"\n\n**Tahmini Kritik Süre:** {prediction['time_to_critical_human']}"

        # İmza bölümü
        signatures = f"""| Hazırlayan | İmza | Tarih |
|-----------|------|-------|
| Sistem (Otomatik) | Otomatik | {now_iso} |
| Bakım Şefi | _______ | _______ |
| Üretim Müdürü | _______ | _______ |"""

        full_md = f"""# ARIZA RAPORU

**Rapor No:** {report_id}
**Tarih:** {now_str}
**Hazırlayan:** Codlean MES Otomatik Raporlama Sistemi

## 1. Makine Bilgileri
{machine_info}

## 2. Olay Tanımı
{incident_desc}

## 3. Analiz Sonuçları
{analysis_md}

## 4. Düzeltici Faaliyetler
{corrective_md}

## 5. Önleyici Faaliyetler
{preventive_md}

## 6. Onay
{signatures}
"""

        return FormalReport(
            report_id=report_id,
            title=title,
            date=now_str,
            machine_info=machine_info,
            incident_description=incident_desc,
            analysis_results=analysis_md,
            corrective_actions=corrective_md,
            preventive_actions=preventive_md,
            signatures_section=signatures,
            full_markdown=full_md,
        )

    # ─── Acil Alert (280 karakter max) ───────────────────────────────────────

    def _build_emergency_alert(self, context: dict, prior_results: dict) -> EmergencyAlert:
        """
        Kısa, SMS uyumlu acil alert. Max 280 karakter.

        Fabrika benzetmesi: Fabrika anons sisteminden yapılan kısa uyarı.
        "HPR001'de kritik durum, bakım ekibi hemen sahaya!"
        """
        machine_id = context.get("machine_id", "UNKNOWN")
        diagnosis = self._extract_diagnosis_info(prior_results)
        prediction = self._extract_prediction_info(prior_results)

        fault_type = diagnosis["fault_type"]
        now_str = datetime.now().strftime("%H:%M")

        # Urgency'e göre severity
        urgency = prediction["urgency"]
        if urgency == "immediate":
            severity = "KRİTİK"
        elif urgency == "soon":
            severity = "UYARI"
        else:
            severity = "BİLGİ"

        # Sensörlerden en kritik değeri bul
        sensor_states = context.get("sensor_states", {})
        critical_sensor = ""
        if sensor_states and isinstance(sensor_states, dict):
            for key, s in sensor_states.items():
                if isinstance(s, dict):
                    lpct = s.get("limit_pct", 0)
                    if lpct >= 100:
                        name = s.get("turkish_name", key)
                        val = s.get("value", "N/A")
                        unit = s.get("unit", "")
                        limit = s.get("limit_max", "N/A")
                        critical_sensor = f" {name} {val}{unit} (limit {limit}{unit})."
                        break

        # Alert metni oluştur
        eta = prediction["time_to_critical_human"] or "belirsiz süre"
        alert = f"⚠️ {machine_id} {severity}: {fault_type} tespit edildi.{critical_sensor} {eta} içinde otomatik durdurma. Acil müdahale gerekli."

        # 280 karakter sınırı
        if len(alert) > 280:
            # Kısalt
            alert = f"⚠️ {machine_id} {severity}: {fault_type}. {eta} içinde durma. Müdahale gerekli."
            if len(alert) > 280:
                alert = alert[:277] + "..."

        return EmergencyAlert(
            alert_text=alert,
            machine_id=machine_id,
            severity=severity,
            timestamp=now_str,
        )

    # ─── LLM Çağrısı (Senkron — Async thread'de çalıştırılır) ────────────────

    def _call_llm_sync(self, prompt: str) -> str:
        """
        Gemini API'ye senkron çağrı yapar.
        DiagnosisAgent._call_llm_sync ile AYNI kalıbı kullanır.
        """
        if not self._ready:
            return self._init_error or "Rapor Ajanı hazır değil."

        result_container: list[str] = [""]
        error_container: list[Exception | None] = [None]

        def _run() -> None:
            try:
                from google import genai

                response = self._client.models.generate_content(
                    model=self.MODEL_NAME,
                    contents=prompt,
                    config=genai.types.GenerateContentConfig(
                        system_instruction=_MANAGER_SYSTEM_PROMPT,
                        temperature=0.3,
                        max_output_tokens=512,
                    ),
                )
                result_container[0] = response.text.strip()
            except Exception as e:
                error_container[0] = e

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
                return "🚫 API kotası doldu. Lütfen birkaç dakika sonra tekrar deneyin."
            elif "403" in err_str or "permission" in err_str.lower():
                return "🔑 API anahtarı geçersiz veya yetkisiz. Lütfen GEMINI_API_KEY'i kontrol edin."
            elif "network" in err_str.lower() or "connection" in err_str.lower():
                return "🌐 API bağlantı hatası. İnternet bağlantısını kontrol edin."
            else:
                return f"❌ API hatası: {err_str[:200]}"

        return result_container[0]


# ─── Dict Dönüşüm Yardımcısı ─────────────────────────────────────────────────


def report_result_to_dict(result: ReportResult) -> dict:
    """
    ReportResult'ı JSON-uyumlu dict'e çevirir.

    Coordinator ve dashboard gibi JSON-serialize eden yerlerde kullanılır.
    """
    d = dataclasses.asdict(result)

    # ReportMode yok (generate_report çağrısında kullanılır, çıktıda string)
    # Ancak generated_modes zaten string listesi

    return d


# ─── Singleton ────────────────────────────────────────────────────────────────
_report_instance: ReportAgent | None = None
_report_lock = threading.Lock()


def get_report_agent() -> ReportAgent:
    """
    Global Rapor Ajanı örneğini döner (lazy init, thread-safe).

    Fabrika benzetmesi: Herkes aynı sekretere rapor yazdırır.
    İlk çağrıda sekreter masasına oturur, sonrakiler aynı uzmana ulaşır.
    """
    global _report_instance
    with _report_lock:
        if _report_instance is None:
            _report_instance = ReportAgent()
    return _report_instance
