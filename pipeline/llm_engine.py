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
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

# .env dosyasından API key yükle
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    load_dotenv(_env_path)
    _dotenv_loaded = True
except ImportError:
    _dotenv_loaded = False

log = logging.getLogger("llm_engine")

# ─── Sistem Promptu ──────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """Sen Codlean MES fabrikasının kıdemli Usta Başı'sın.
30 yıldır bu atölyedesin. Her presin sesinden, yağının kokusundan ne olduğunu anlarsın.
Az konuşursun ama her sözün yerindedir. Teknisyenler sana güvenir çünkü boş laf etmezsin.

KİM OLDUĞUN:
Adın yok — herkes sana "Usta" der. Maddeleme yapmazsın, rapor yazmazsın.
Bir teknisyen yanına gelip "Usta, HPR001 nasıl?" dediğinde, elindeki çayı bırakıp
"Yağı biraz sıcak, göz kulak ol" dersin — uzun uzun anlatmazsın.
Ama iş ciddi olduğunda sesi sert koyarsın: "Dur, bu makineyi durdur, şu valfı kontrol et."

ATÖLYENİ BİLİRSİN:
- 6 tane hidrolik presin var: HPR001-HPR006
- Dikey Presler (HPR001, 003, 005): Yağ sıcaklığı, ana basınç, yatay basınç, alt ejektör, hız sensörleri var
- Yatay Presler (HPR002, 004, 006): Yağ sıcaklığı sensörü YOK — sadece basınç ve hız
- Operasyonel sınırlar: Yağ 39.5°C'de dikkat, 45°C'de tehlike. Basınç 95 bar'da dikkat, 110 bar'da tehlike.
- Sıcaklık yükselince yağ incelir → sızıntı başlar → basınç düşer. Bunu ezbere bilirsin.
- Basınç yüksek ama hız yoksa: bir yerde sıkışma var demektir.

NASIL KONUŞURSUN:
- Doğal, akıcı, sohbet gibi. Madde madde sıralama YAPMA. Paragraf halinde, kısa konuş.
- Somut ol: "biraz yüksek" deme, "48 derece — limitin 3 derece üstünde" de.
- Duruma göre ton değiştir:
  · Sensör normal aralıktaysa (ör. yağ 32°C): "Makine daha yeni uyanmış, yağ henüz ısınmamış bile. Rahat ol."
  · Sensör uyarı bölgesinde (ör. yağ 40°C): "Yağ biraz fazla ısınmış, soğutmaya bir bak derim."
  · Sensör tehlike bölgesinde (ör. yağ 48°C): "DUR. Yağ 48 dereceye çıkmış, bu iş sızıntıya gider. Soğutmayı hemen kontrol et."
  · Sensör çok düşükse (ör. basınç 20 bar): "Basınç hiç yok gibi, makine ya yüklenmiyor ya da bir yerde kaçak var."
- İç keşif yap: Tek sensöre bakma, sensörler arası bağlantı kur.
  "Basınç düşük ama sıcaklık yüksek — bu iç kaçağa benziyor, enerji ısıya dönüşüyor" gibi.
- Geçmişi hatırla: "Bu tablo daha önce de olmuştu, o seferki filtre tıkanmıştı" gibi.
- ETA ver: "Bu gidişle 2 saate limite dayanır" gibi.

NE KADAR KONUŞURSUN:
- Basit soru → 1-2 cümle. "Kritik mi?" → "Şu an değil, ama yağa göz kulak ol."
- Makine analizi → 3-5 cümle. Duruma özel, maddesiz, akıcı.
- Acil durum → İlk söz uyarı: "DUR!" veya "DİKKAT!" ile başla, sonra ne yapılacağını söyle.

YAPMA:
- "1. 2. 3." diye maddeleme
- "Sonuç olarak", "Maalesef", "Ne yazık ki" gibi dolgu kelimeler kullanma
- Sadece veriyi tekrarlama — yorumla, nedensellik kur
- Yatay presler (HPR002/004/006) için yağ sıcaklığından bahsetme — o sensör yok
- Akademik rapor gibi yazma — sen profesör değilsin, ustasın
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
    CALL_TIMEOUT_SEC = 30  # 30 saniyede yanıt gelmezse hata dön

    def __init__(self, api_key: str = None, model_name: str = "gemini-2.5-flash"):
        self._ready = False
        self._client = None
        self._model_name = model_name
        self._init_error = None

        key = api_key or os.environ.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")

        log.info(f"[LLM_INIT] dotenv yüklendi: {_dotenv_loaded}")
        log.info(f"[LLM_INIT] API Key mevcut: {bool(key)}")
        if key:
            log.info(f"[LLM_INIT] API Key ilk 8 karakter: {key[:8]}...")

        if not key:
            self._init_error = "GEMINI_API_KEY tanımlı değil. .env dosyasını kontrol edin."
            log.warning(f"[LLM_INIT] {self._init_error}")
            return
        try:
            from google import genai
            self._client = genai.Client(api_key=key)
            self._ready = True
            log.info(f"[LLM_INIT] ✅ AI Usta Başı hazır ({model_name})")
        except ImportError:
            self._init_error = "google-generativeai kütüphanesi kurulu değil. 'pip install google-genai' çalıştırın."
            log.exception(f"[LLM_INIT] {self._init_error}")
        except Exception as e:
            self._init_error = f"Gemini başlatılamadı: {e}"
            log.exception(f"[LLM_INIT] {self._init_error}")

    @property
    def is_ready(self) -> bool:
        return self._ready

    # API Request Caching (Maliyet ve Hız Optimizasyonu)  
    _cache: dict[str, tuple[float, str]] = {}  # {key: (timestamp, response)}
    CACHE_TTL_SEC: int = 600  # 10 dakika önbellek süresi

    # ── Temel çağrı ──────────────────────────────────────────────────────────
    def _call(self, prompt: str, cache_key: str = None) -> str:
        """
        Gemini API'ye senkron çağrı yapar.
        Hata durumunda kullanıcıya anlamlı mesaj döner.
        """
        if not self._ready:
            return self._init_error or "AI Usta Başı hazır değil."

        # Cache Kontrolü
        if cache_key:
            now_ts = time.time()
            if cache_key in self._cache:
                cached_ts, cached_res = self._cache[cache_key]
                if now_ts - cached_ts < self.CACHE_TTL_SEC:
                    log.info(f"⚡ [CACHE HIT] {cache_key} bulundu. Maliyet $0.")
                    return cached_res

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
                "Gemini API timeout (%ds) — yanıt gelmedi.",
                self.CALL_TIMEOUT_SEC,
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

        if cache_key and result_container[0]:
            self._cache[cache_key] = (time.time(), result_container[0])

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
        
        # Cache Key: Makine ID + Severity + Aktif Teşhis + Alert Durumu (Bağlam değişmemişse önbellekten oku)
        sev = context.get("severity", "")
        rules = str(context.get("active_rules", []))
        c_key = f"analyze_{mid}_{sev}_{rules}"
        
        return self._call(prompt, cache_key=c_key)

    # ── Soru-cevap modu ───────────────────────────────────────────────────────
    def ask(self, context: dict, question: str) -> str:
        """
        Kullanıcının sorusunu bağlamla birlikte yanıtlar.
        Throttle yok — kullanıcı sorduğunda her zaman cevap ver.
        """
        prompt = _build_question_prompt(context, question)
        
        mid = context.get("machine_id", "unknown")
        sev = context.get("severity", "")
        # Kullanıcının tam sorusuna, o makinedeki o anki riske göre cache et
        c_key = f"ask_{mid}_{sev}_{question}"
        
        return self._call(prompt, cache_key=c_key)

    # ── Filo özeti ────────────────────────────────────────────────────────────
    def fleet_summary(self, all_contexts: dict) -> str:
        """Tüm makineleri karşılaştırır, en kritiklerini öne çıkarır."""
        prompt = _build_fleet_prompt(all_contexts)
        
        # Makine ID'leri ve severity'lerinden oluşan eşsiz profil (Bağlam aynıysa API'ye gitme)
        sig = "-".join([f"{m}{c.get('severity','')}" for m, c in all_contexts.items()])
        c_key = f"fleet_{sig}"
        
        return self._call(prompt, cache_key=c_key)

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
