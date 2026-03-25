"""
llm_engine.py — AI Usta Başı Beyin Motoru
══════════════════════════════════════════
Google Gemini API kullanarak makine bağlamını anlayan,
Türkçe açıklama ve tahmin üreten zeka katmanı.

Kullanım:
    from pipeline.llm_engine import UstaBasi
    usta = UstaBasi()
    analiz = usta.analyze(context_package)
    cevap  = usta.ask(context_package, "Bu makine neden bu kadar ısınıyor?")
"""

from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

log = logging.getLogger("llm_engine")

# ─── Sistem Promptu ──────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """Sen Codlean MES'in AI Usta Başı'sın.
HPR (Hidrolik Pres) makinelerinde uzmanlaşmış, 15 yıllık deneyimli bir bakım mühendisi gibi düşünürsün.
Fabrika ortamında çalışan teknisyenlere, vardiya şeflerine ve mühendislere destek verirsin.

KURALLARIN:
- Türkçe yanıt ver, sade ve anlaşılır ol
- Gereksiz teknik jargon kullanma; kullanmak zorundaysan açıkla
- Her analizde şu 3 soruyu yanıtla: (1) Ne oluyor ve neden? (2) Devam ederse ne olur? (3) Şimdi ne yapmalı?
- Sayıları ve ölçümleri kullan — somut ol
- Geçmişteki benzer olaylar varsa mutlaka bahset
- ETA tahmini varsa belirt, ama aşırı kesin konuşma ("yaklaşık", "tahminen" kullan)
- Yanıtın 3-6 cümle arasında olsun — ne çok kısa ne çok uzun
- Acil durumlarda ilk cümle uyarı olsun

YAPMA:
- "Maalesef", "Ne yazık ki", "Mükemmel" gibi gereksiz dolgu kelimeler kullanma
- Sadece veriyi tekrarlama, yorumla
- Soru sormadan yanıt verme diye bir kuralın yok — direkt konuya gir
"""


# ─── Prompt Şablonları ────────────────────────────────────────────────────────
def _build_analysis_prompt(ctx: dict) -> str:
    lines = [
        f"=== MAKİNE ANALİZİ: {ctx['machine_id']} ===",
        f"Zaman: {ctx['timestamp']}",
        f"Çalışma süresi: {ctx['operating_time']}",
        f"Risk skoru: {ctx['risk_score']}/100 ({ctx['severity']})",
        "",
    ]

    # Limit ihlalleri — en kritik bilgi
    if ctx["limit_violations"]:
        lines.append("⛔ AKTİF LİMİT İHLALLERİ:")
        for v in ctx["limit_violations"]:
            lines.append(f"  - {v}")
        lines.append("")

    # Kritik yaklaşan sensörler
    if ctx["critical_sensors"]:
        lines.append("⚠️ KRİTİK YAKLAŞIM:")
        for s in ctx["critical_sensors"]:
            lines.append(f"  - {s}")
        lines.append("")

    # Tüm sensör durumları
    lines.append("SENSÖR DURUMU:")
    for key, s in ctx["sensor_states"].items():
        slope_str = ""
        if s["slope_per_hour"]:
            slope_str = f" | trend: {s['slope_per_hour']:+.2f}{s['unit']}/saat"
        lines.append(
            f"  {s['turkish_name']}: {s['value']}{s['unit']} "
            f"(limitin %{s['limit_pct']:.0f}'i) {s['trend_arrow']}{slope_str} — {s['status_label']}"
        )
    lines.append("")

    # ETA tahminleri
    if ctx["eta_predictions"]:
        lines.append("⏱️ LİMİTE KALAN SÜRE TAHMİNİ:")
        for key, eta in ctx["eta_predictions"].items():
            lines.append(
                f"  {eta['sensor_name']}: şu an {eta['current_value']}{eta['unit']} → "
                f"tahminen {eta['eta_minutes']} dakika içinde {eta['limit']}{eta['unit']} limitine ulaşır"
            )
        lines.append("")

    # Aktif fizik kuralları
    if ctx["active_physics_rules"]:
        lines.append("🔬 TETİKLENEN FİZİK KURALLARI:")
        for rule in ctx["active_physics_rules"]:
            lines.append(f"  - {rule}")
        lines.append("")

    # Benzer geçmiş olaylar
    if ctx["similar_past_events"]:
        lines.append("📚 BENZER GEÇMİŞ OLAYLAR:")
        for event in ctx["similar_past_events"]:
            lines.append(f"  - {event}")
        lines.append("")

    # Son uyarılar
    if ctx["last_alerts"]:
        lines.append("📋 SON UYARILAR:")
        for alert in ctx["last_alerts"]:
            lines.append(f"  - {alert}")
        lines.append("")

    lines.append(
        "Bu makinenin mevcut durumunu analiz et. Ne oluyor, neden, ne yapılmalı?"
    )
    return "\n".join(lines)


def _build_question_prompt(ctx: dict, question: str) -> str:
    base = _build_analysis_prompt(ctx)
    # Son satırı (analiz isteği) soruyla değiştir
    lines = base.split("\n")
    lines[-1] = f"SORU: {question}"
    return "\n".join(lines)


def _build_fleet_prompt(all_contexts: dict) -> str:
    lines = ["=== FİLO ANALİZİ — TÜM HPR MAKİNELERİ ===", ""]
    for mid, ctx in all_contexts.items():
        lines.append(
            f"[{mid}] Risk: {ctx['risk_score']}/100 ({ctx['severity']}) | "
            f"Çalışma: {ctx['operating_time']}"
        )
        if ctx["limit_violations"]:
            lines.append(f"  ⛔ İhlal: {', '.join(ctx['limit_violations'])}")
        if ctx["critical_sensors"]:
            lines.append(f"  ⚠️  Kritik: {', '.join(ctx['critical_sensors'])}")
        if ctx["eta_predictions"]:
            etas = [
                f"{e['sensor_name']} ~{e['eta_minutes']}dk"
                for e in ctx["eta_predictions"].values()
            ]
            lines.append(f"  ⏱️  ETA: {', '.join(etas)}")
        lines.append("")

    lines.append(
        "Tüm filo değerlendirmesi yap: En kritik makine hangisi ve neden? "
        "Toplam bakım önceliğini sırala."
    )
    return "\n".join(lines)


# ─── Ana Motor ────────────────────────────────────────────────────────────────
class UstaBasi:
    """
    AI Usta Başı — Gemini tabanlı fabrika zekası.

    Örnek:
        usta = UstaBasi()
        print(usta.analyze(context))
        print(usta.ask(context, "Bu makine neden bu kadar ısınıyor?"))
        print(usta.fleet_summary(all_contexts))
    """

    # Makine başına son analiz zamanı — throttle için
    _last_analysis: dict[str, float] = {}
    _lock = threading.Lock()

    # FIX P1-2: Thread havuzu — sınırsız thread açılmasını önler
    # max_workers=3: aynı anda en fazla 3 eş zamanlı Gemini çağrısı
    _executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="llm_usta")

    # Throttle: aynı makine için minimum kaç saniyede bir LLM çağrısı
    AUTO_INTERVAL_SEC = 300  # Otomatik analizde 5 dakika
    ALERT_INTERVAL_SEC = 60  # Alert sonrası 1 dakika
    # FIX P1-2: Gemini API için maksimum bekleme süresi
    CALL_TIMEOUT_SEC = 10  # 10 saniyede yanıt gelmezse boş dön

    def __init__(self, api_key: str = None, model_name: str = "gemini-2.0-flash"):
        self._ready = False
        self._client = None
        self._model_name = model_name
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            log.warning("GEMINI_API_KEY tanımlı değil — LLM devre dışı")
            return
        try:
            from google import genai

            self._client = genai.Client(api_key=key)
            self._ready = True
            log.info(f"AI Usta Başı hazır ({model_name})")
        except Exception as e:
            log.error(f"Gemini başlatılamadı: {e}")

    @property
    def is_ready(self) -> bool:
        return self._ready

    # ── Temel çağrı ──────────────────────────────────────────────────────────
    def _call(self, prompt: str) -> str:
        """
        Gemini API'ye senkron çağrı yapar.
        CALL_TIMEOUT_SEC içinde yanıt gelmezse boş string döner.

        FIX P1-2: Timeout mekanizması — API askıda kalırsa thread sonsuza
        beklemesin. Timeout dolunca warning log'u üretilir ve "" döner.
        """
        if not self._ready:
            return ""

        result_container: list[str] = [""]
        error_container: list[Exception | None] = [None]

        def _run() -> None:
            try:
                from google import genai

                response = self._client.models.generate_content(
                    model=self._model_name,
                    contents=prompt,
                    config=genai.types.GenerateContentConfig(
                        system_instruction=_SYSTEM_PROMPT,
                        temperature=0.4,
                        max_output_tokens=2048,
                    ),
                )
                result_container[0] = response.text.strip()
            except Exception as e:
                error_container[0] = e

        worker = threading.Thread(target=_run, daemon=True)
        worker.start()
        worker.join(timeout=self.CALL_TIMEOUT_SEC)

        if worker.is_alive():
            log.warning(
                "Gemini API timeout (%ds) — yanıt gelmedi, boş döndürülüyor. "
                "Prompt uzunluğu: %d karakter",
                self.CALL_TIMEOUT_SEC,
                len(prompt),
            )
            return ""

        if error_container[0] is not None:
            log.error("Gemini API hatası: %s", error_container[0])
            return ""

        return result_container[0]

    # ── Makine analizi (otomatik mod) ─────────────────────────────────────────
    def analyze(self, context: dict, force: bool = False) -> str:
        """
        Tek makine için otomatik analiz üretir.
        force=True ile throttle bypass edilir (alert sonrası).
        """
        mid = context.get("machine_id", "")
        now = time.monotonic()
        interval = self.ALERT_INTERVAL_SEC if force else self.AUTO_INTERVAL_SEC

        with self._lock:
            last = self._last_analysis.get(mid, 0)
            if not force and (now - last) < interval:
                return ""  # Throttle — henüz zamanı değil
            self._last_analysis[mid] = now

        prompt = _build_analysis_prompt(context)
        return self._call(prompt)

    # ── Soru-cevap modu ───────────────────────────────────────────────────────
    def ask(self, context: dict, question: str) -> str:
        """
        Kullanıcının sorusunu bağlamla birlikte yanıtlar.
        Throttle yok — kullanıcı sorduğunda her zaman cevap ver.
        """
        prompt = _build_question_prompt(context, question)
        return self._call(prompt)

    # ── Filo özeti ────────────────────────────────────────────────────────────
    def fleet_summary(self, all_contexts: dict) -> str:
        """Tüm makineleri karşılaştırır, en kritiklerini öne çıkarır."""
        prompt = _build_fleet_prompt(all_contexts)
        return self._call(prompt)

    # ── Async wrapper (dashboard'u bloklamaz) ─────────────────────────────────
    def analyze_async(
        self,
        context: dict,
        callback: Callable[[str, str], None],
        force: bool = False,
    ) -> None:
        """
        Gemini çağrısını arka planda çalıştırır.
        callback(machine_id, analiz_metni) ile sonucu iletir.

        FIX P1-2: threading.Thread yerine ThreadPoolExecutor kullanılıyor.
        max_workers=3 ile aynı anda en fazla 3 eş zamanlı Gemini çağrısı yapılır.
        4. ve sonraki çağrılar kuyrukta bekler — sınırsız thread birikmez.
        """
        mid = context.get("machine_id", "")

        def _run() -> None:
            result = self.analyze(context, force=force)
            if result:
                callback(mid, result)

        self._executor.submit(_run)

    def ask_async(
        self,
        context: dict,
        question: str,
        callback: Callable[[str, str], None],
    ) -> None:
        """
        Soruyu arka planda yanıtlar.
        FIX P1-2: ThreadPoolExecutor ile sınırlı eş zamanlılık.
        """
        mid = context.get("machine_id", "")

        def _run() -> None:
            result = self.ask(context, question)
            if result:
                callback(mid, result)

        self._executor.submit(_run)


# ─── Singleton ────────────────────────────────────────────────────────────────
_instance: UstaBasi | None = None


def get_usta() -> UstaBasi:
    """Global UstaBasi örneğini döner (lazy init)."""
    global _instance
    if _instance is None:
        _instance = UstaBasi()
    return _instance
