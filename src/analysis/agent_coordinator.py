"""
agent_coordinator.py — Çoklu Ajan Koordinatörü
════════════════════════════════════════════════
Bir fabrika şefinin uzman ekibini yönettiği gibi çalışır:
Risk düşükse az kişiyle çözer, risk yükseldikçe tüm uzmanları
masaya çağırır. Bağımsız uzmanlar aynı anda çalışır,
bağımlı olanlar sırayla gelir.

Kullanım:
    from src.analysis.agent_coordinator import get_coordinator
    koordinator = get_coordinator()
    sonuc = await koordinator.analyze(context_package)

Geriye uyumluluk: pipeline/llm_engine.py (UstaBasi) dokunulmadan
kalır, yeni sistem üzerine inşa edilir.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import time
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, UTC
from typing import Optional

from src.analysis.diagnosis_agent import DiagnosisAgent, get_diagnosis_agent
from src.analysis.action_agent import ActionAgent, get_action_agent, action_plan_to_dict
from src.analysis.root_cause_agent import RootCauseAgent, get_root_cause_agent, root_cause_result_to_dict

log = logging.getLogger("agent_coordinator")

# ─── Ana Sınıf ────────────────────────────────────────────────────────────────


class AgentCoordinator:
    """
    Risk bazlı çok ajanlı koordinatör.

    Fabrika şefi gibi düşün: Her makine için risk seviyesine bakar,
    kaç uzman çağıracağına karar verir. Bağımsız uzmanları aynı anda
    görevlendirir (paralel), raporcu ise hepsinin sonucunu bekler (sıralı).
    """

    # ── Önbellek (Cache) ────────────────────────────────────────────────────
    _cache: dict[str, tuple[float, dict]] = {}
    _cache_ttl: int = 600  # 10 dakika

    # ── Throttle (Tıkama) ───────────────────────────────────────────────────
    # Aynı makine için ne kadar sıklıkla analiz yapılacağı
    _last_analysis: dict[str, float] = {}
    AUTO_INTERVAL_SEC: int = 300  # Otomatik analiz: 5 dakika
    ALERT_INTERVAL_SEC: int = 60  # Alert sonrası: 1 dakika

    # ── Thread Havuzu ───────────────────────────────────────────────────────
    # Senkron işlemler için (örneğin I/O bloklayan kütüphaneler)
    _executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="agent_")

    # ── Kilit (Thread-safe) ─────────────────────────────────────────────────
    _lock: asyncio.Lock | None = None  # İlk async çağrıda oluşturulacak

    def __init__(self):
        """Koordinatörü başlatır. Şef masasına oturur."""
        pass

    # ── Risk Seviyesi Belirleme ─────────────────────────────────────────────

    def _get_risk_level(self, risk_score: float) -> str:
        """
        Risk skorunu kategori etiketine çevirir.

        0-30   → normal   (Makine rahat, ekibe gerek yok)
        31-70  → medium   (Dikkatli ol, birkaç uzman çağır)
        71-100 → critical (Tam ekip devreye girsin)
        """
        if risk_score <= 30:
            return "normal"
        elif risk_score <= 70:
            return "medium"
        else:
            return "critical"

    def _determine_agents_to_call(self, risk_score: float) -> list[str]:
        """
        Risk skoruna göre hangi ajanların çağrılacağına karar verir.

        Fabrika şefinin sabah toplantısı gibidir:
        - Her şey yolundaysa sadece teşhisçi ve raportör yetişir.
        - Durum kararsızsa kök neden ve önlem uzmanları da gelir.
        - Alarm çalıyorsa tüm ekip masadadır.
        """
        if risk_score <= 30:
            return ["diagnosis", "report"]
        elif risk_score <= 70:
            return ["diagnosis", "root_cause", "prediction", "action", "report"]
        else:
            return ["diagnosis", "root_cause", "prediction", "action", "report"]

    # ── Önbellek Yönetimi ───────────────────────────────────────────────────

    def _build_cache_key(self, context: dict, agent_type: str) -> str:
        """
        Ajan çağrısı için eşsiz önbellek anahtarı üretir.

        Format: agent_{tip}_{makine_id}_{risk_seviyesi}
        Aynı makine, aynı risk seviyesindeyse API'ye tekrar gitme.
        """
        machine_id = context.get("machine_id", "unknown")
        risk_level = self._get_risk_level(context.get("risk_score", 0))
        return f"agent_{agent_type}_{machine_id}_{risk_level}"

    def _is_cache_valid(self, cache_key: str) -> bool:
        """
        Önbellekteki kaydın hâlâ taze olup olmadığını kontrol eder.

        10 dakikadan eskiyse çürümüş sayılır, yeniden çalışılır.
        """
        if cache_key not in self._cache:
            return False
        timestamp, _ = self._cache[cache_key]
        return (time.time() - timestamp) < self._cache_ttl

    def _read_cache(self, cache_key: str) -> Optional[dict]:
        """Önbellekten ajan sonucunu okur."""
        if not self._is_cache_valid(cache_key):
            return None
        _, result = self._cache[cache_key]
        log.info("[CACHE HIT] %s — önbellekten döndü", cache_key)
        return result

    def _write_cache(self, cache_key: str, result: dict) -> None:
        """Ajan sonucunu önbelleğe yazar."""
        self._cache[cache_key] = (time.time(), result)
        log.info("[CACHE WRITE] %s — önbelleğe yazıldı", cache_key)

    # ── Temel Analiz Metodu ─────────────────────────────────────────────────

    async def analyze(self, context: dict, force: bool = False) -> dict:
        """
        Makine bağlamına göre uzman ajanları çağırır ve sonuçları birleştirir.

        Adımlar:
        1. Throttle kontrolü: Aynı makineye çok sık sorma.
        2. Risk seviyesine göre ajanları belirle.
        3. Bağımsız ajanları paralel çalıştır (asyncio.gather).
        4. Bağımlı ajanları sırayla çalıştır.
        5. Tüm sonuçları paketle, logla, döndür.

        Args:
            context: pipeline.context_builder.build() çıktısı.
            force: True ise throttle'i bypass et (alert sonrası).

        Returns:
            Tüm ajan çıktılarını ve meta verileri içeren sözlük.
        """
        mid = context.get("machine_id", "")
        now = time.monotonic()
        interval = self.ALERT_INTERVAL_SEC if force else self.AUTO_INTERVAL_SEC

        # Lock'u ilk async çağrıda oluştur (import sırasında event loop olmayabilir)
        if self._lock is None:
            self._lock = asyncio.Lock()

        # Throttle kontrolü
        async with self._lock:
            last = self._last_analysis.get(mid, 0)
            if not force and (now - last) < interval:
                log.info(
                    "[THROTTLE] %s için henüz zamanı değil (%.0f saniye kaldı)",
                    mid, interval - (now - last),
                )
                return {
                    "diagnosis": None,
                    "root_cause": None,
                    "prediction": None,
                    "action": None,
                    "report": {
                        "status": "throttled",
                        "message": "Analiz henüz yapılmadı, bekleme süresi devam ediyor.",
                    },
                    "execution_time_sec": 0.0,
                    "agents_called": [],
                    "risk_level": self._get_risk_level(context.get("risk_score", 0)),
                    "cache_hit": False,
                }
            self._last_analysis[mid] = now

        start_time = time.monotonic()
        risk_score = context.get("risk_score", 0)
        risk_level = self._get_risk_level(risk_score)
        agents_to_call = self._determine_agents_to_call(risk_score)

        log.info(
            "[ANALYZE START] %s | Risk: %.1f (%s) | Ajanlar: %s",
            mid, risk_score, risk_level, ", ".join(agents_to_call),
        )

        # Ajanları gruplara ayır
        independent_names = [a for a in agents_to_call if a in ("diagnosis", "root_cause", "prediction")]
        dependent_names = [a for a in agents_to_call if a in ("action", "report")]

        # Önbellekten bağımsız ajan sonuçlarını dene
        independent_results: dict[str, dict] = {}
        uncached_independent: list[str] = []

        for agent in independent_names:
            ckey = self._build_cache_key(context, agent)
            cached = self._read_cache(ckey)
            if cached is not None:
                independent_results[agent] = cached
            else:
                uncached_independent.append(agent)

        # Bağımsızları çalıştır (paralel)
        if uncached_independent:
            new_results = await self._run_independent_agents(context, uncached_independent)
            for agent, result in new_results.items():
                independent_results[agent] = result
                ckey = self._build_cache_key(context, agent)
                self._write_cache(ckey, result)

        # Bağımlıları çalıştır (sıralı)
        dependent_results = await self._run_dependent_agents(context, independent_results, dependent_names)
        for agent, result in dependent_results.items():
            ckey = self._build_cache_key(context, agent)
            self._write_cache(ckey, result)

        execution_time = time.monotonic() - start_time

        log.info(
            "[ANALYZE END] %s | Süre: %.2fs | Ajanlar: %s",
            mid, execution_time, ", ".join(agents_to_call),
        )

        return {
            "diagnosis": independent_results.get("diagnosis"),
            "root_cause": independent_results.get("root_cause"),
            "prediction": independent_results.get("prediction"),
            "action": dependent_results.get("action"),
            "report": dependent_results.get("report"),
            "execution_time_sec": round(execution_time, 2),
            "agents_called": agents_to_call,
            "risk_level": risk_level,
            "cache_hit": False,  # Toplu cache hit bilgisi; detay loglarda
        }

    # ── Paralel Çalıştırma (Grup 1) ─────────────────────────────────────────

    async def _run_independent_agents(self, context: dict, agents: list[str]) -> dict:
        """
        Bağımsız ajanları aynı anda çalıştırır.

        Teşhisçi, kök neden uzmanı ve trend analisti birbirinden
        bağımsız çalışır; hepsini aynı anda masalarına yollarız.
        """
        tasks = []
        agent_names = []

        for agent in agents:
            if agent == "diagnosis":
                tasks.append(self._call_diagnosis_agent(context))
                agent_names.append("diagnosis")
            elif agent == "root_cause":
                tasks.append(self._call_root_cause_agent(context))
                agent_names.append("root_cause")
            elif agent == "prediction":
                tasks.append(self._call_prediction_agent(context))
                agent_names.append("prediction")

        log.info("[PARALLEL START] %s ajan aynı anda çalışıyor: %s", len(tasks), ", ".join(agent_names))
        group_start = time.monotonic()

        # return_exceptions=True: biri patlasa da diğerleri çalışsın
        gathered = await asyncio.gather(*tasks, return_exceptions=True)

        group_time = time.monotonic() - group_start
        log.info("[PARALLEL END] Süre: %.2fs", group_time)

        results: dict[str, dict] = {}
        for name, res in zip(agent_names, gathered):
            if isinstance(res, Exception):
                log.error("[AGENT FAIL] %s: %s", name, res)
                results[name] = {"status": "error", "message": str(res)}
            else:
                log.info("[AGENT SUCCESS] %s — tamamlandı", name)
                results[name] = res

        return results

    # ── Sıralı Çalıştırma (Grup 2) ──────────────────────────────────────────

    async def _run_dependent_agents(
        self, context: dict, independent_results: dict, agents: list[str]
    ) -> dict:
        """
        Bağımlı ajanları sırayla çalıştırır.

        Önlem uzmanı teşhis ve kök neden bilgisi olmadan karar veremez.
        Raporcu ise tüm masadaki konuşmaları bitirmeden yazamaz.
        Bu yüzden tek tek, sırayla çalıştırılır.
        """
        results: dict[str, dict] = {}

        for agent in agents:
            agent_start = time.monotonic()
            try:
                if agent == "action":
                    log.info("[AGENT START] action — önlem ajanı çalışıyor")
                    results["action"] = await self._call_action_agent(context, independent_results)
                elif agent == "report":
                    log.info("[AGENT START] report — raportör çalışıyor")
                    all_results = {**independent_results, **results}
                    results["report"] = await self._call_report_agent(context, all_results)
                else:
                    continue

                agent_time = time.monotonic() - agent_start
                log.info("[AGENT SUCCESS] %s — tamamlandı (%.2fs)", agent, agent_time)
            except Exception as e:
                agent_time = time.monotonic() - agent_start
                log.error("[AGENT FAIL] %s: %s (%.2fs)", agent, e, agent_time)
                results[agent] = {"status": "error", "message": str(e)}

        return results

    # ── Ajan Çağrıları (Placeholder — Task 1.2+ Implementasyon) ─────────────

    async def _call_diagnosis_agent(self, context: dict) -> dict:
        """
        Teşhis Ajanı — Sensör verilerine bakar, makinenin neyin var olduğunu söyler.

        DiagnosisAgent'i çağırır, sonucu dict olarak döndürür.
        API çalışmazsa yerel analizle teşhis üretir (graceful degradation).
        """
        agent = get_diagnosis_agent()
        result = await agent.diagnose(context)
        result_dict = dataclasses.asdict(result)
        result_dict["status"] = "success"
        return result_dict

    async def _call_root_cause_agent(self, context: dict) -> dict:
        """
        Kök Neden Ajanı — 5-Why metoduyla kök neden analizi yapar.

        RootCauseAgent'i çağırır, sonucu dict olarak döndürür.
        API çalışmazsa yerel 5-Why şablonlarıyla analiz üretir (graceful degradation).
        """
        agent = get_root_cause_agent()
        result = await agent.analyze(context)
        result_dict = root_cause_result_to_dict(result)
        result_dict["status"] = "success"
        return result_dict

    async def _call_prediction_agent(self, context: dict) -> dict:
        """
        Tahmin Ajanı — Trendleri analiz eder, gelecekte ne olabileceğini söyler.

        TODO: PredictionAgent implementasyonu Task 1.2'de yapılacak.
        Şimdilik yer tutucu döndürür.
        """
        # TODO: PredictionAgent implementasyonu Task 1.2'de yapılacak
        return {
            "status": "placeholder",
            "message": "Prediction Agent henüz implement edilmedi",
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def _call_action_agent(self, context: dict, prior_results: dict) -> dict:
        """
        Önlem Ajanı — Teşhis, kök neden ve tahmin sonuçlarına bakarak ne yapılması
        gerektiğini önerir.

        ActionAgent'i çağırır, sonucu dict olarak döndürür.
        API çalışmazsa yerel şablonlarla eylem planı üretir (graceful degradation).
        """
        agent = get_action_agent()

        # Önceki ajan sonuçlarını çıkar
        diagnosis_result = prior_results.get("diagnosis")
        root_cause_result = prior_results.get("root_cause")
        prediction_result = prior_results.get("prediction")

        result = await agent.create_action_plan(
            context=context,
            diagnosis_result=diagnosis_result,
            root_cause_result=root_cause_result,
            prediction_result=prediction_result,
        )
        result_dict = action_plan_to_dict(result)
        result_dict["status"] = "success"
        return result_dict

    async def _call_report_agent(self, context: dict, all_results: dict) -> dict:
        """
        Rapor Ajanı — Tüm ajan çıktılarını derleyip tek bir özete dönüştürür.

        TODO: ReportAgent implementasyonu Task 1.2'de yapılacak.
        Şimdilik yer tutucu döndürür.
        """
        # TODO: ReportAgent implementasyonu Task 1.2'de yapılacak
        return {
            "status": "placeholder",
            "message": "Report Agent henüz implement edilmedi",
            "inputs": list(all_results.keys()),
            "timestamp": datetime.now(UTC).isoformat(),
        }


# ─── Singleton ────────────────────────────────────────────────────────────────
_coordinator_instance: AgentCoordinator | None = None


def get_coordinator() -> AgentCoordinator:
    """
    Global AgentCoordinator örneğini döner (lazy init).

    Tüm sistem tek bir koordinatör üzerinden çalışır;
    aynı önbellek ve throttle durumunu paylaşır.
    """
    global _coordinator_instance
    if _coordinator_instance is None:
        _coordinator_instance = AgentCoordinator()
    return _coordinator_instance
