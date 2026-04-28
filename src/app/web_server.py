"""
Codlean MES — Web Dashboard Server
====================================
Çalıştır:  PYTHONPATH=. python3 src/app/web_server.py
Aç:        http://localhost:5001

Endpoint'ler:
  GET  /               → index.html
  GET  /api/machines   → Tüm makine verileri
  GET  /api/status     → Sistem durumu
  POST /api/ask        → Usta Başı'na soru sor {machine_id, question}
  GET  /api/fleet      → Tüm filo analizi (Gemini)
  GET  /stream         → Server-Sent Events (2sn)
"""

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from flask import Flask, jsonify, Response, send_from_directory, request

# ─── Yollar ──────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).resolve().parents[2]
STATE_PATH   = BASE_DIR / "state.json"
CONTEXT_PATH = BASE_DIR / "rich_context_windows.jsonl"
LIMITS_PATH  = BASE_DIR / "config" / "limits_config.yaml"
RULES_PATH   = BASE_DIR / "docs" / "causal_rules.json"
STATIC_DIR   = BASE_DIR / "src" / "ui" / "web"

# pipeline/ paketine erişim için path ekle
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

app = Flask(
    __name__,
    static_folder=str(STATIC_DIR),
    static_url_path='',
)

# ─── Async-Flask Bridge ──────────────────────────────────────────────────────
def async_route(f):
    """Flask route'larında async fonksiyon çalıştırmak için decorator."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(f(*args, **kwargs))
        finally:
            loop.close()
    return wrapper

# ─── Global Coordinator (lazy init) ──────────────────────────────────────────
_multi_agent_coordinator = None

def get_coordinator():
    """AgentCoordinator singleton — tembel başlatma."""
    global _multi_agent_coordinator
    if _multi_agent_coordinator is None:
        from src.analysis.agent_coordinator import AgentCoordinator
        _multi_agent_coordinator = AgentCoordinator()
    return _multi_agent_coordinator

# ─── Report Store (in-memory + optional file persistence) ────────────────────
_report_store = {}  # {report_id: report_data}
_MAX_REPORT_STORE = 50

def _store_report(report_id: str, data: dict):
    """Raporu sakla (max 50 entry, en eski silinir)."""
    global _report_store
    if len(_report_store) >= _MAX_REPORT_STORE:
        oldest_key = next(iter(_report_store))
        del _report_store[oldest_key]
    _report_store[report_id] = data

# ─── Rate Limiting ───────────────────────────────────────────────────────────
_rate_limits = defaultdict(list)

def check_rate_limit(machine_id: str, max_requests: int = 5, window: int = 60) -> bool:
    """Aynı makine için dakikada max 5 istek."""
    now = time.time()
    requests = [t for t in _rate_limits[machine_id] if now - t < window]
    if len(requests) >= max_requests:
        return False
    requests.append(now)
    _rate_limits[machine_id] = requests
    return True

# ─── Performance Tracking ────────────────────────────────────────────────────
_performance_stats = {
    "total_requests": 0,
    "total_execution_time": 0.0,
    "cache_hits": 0,
}

# ─── Limitleri yükle ─────────────────────────────────────────────────────────
def _load_limits():
    try:
        import yaml
        with open(LIMITS_PATH) as f:
            cfg = yaml.safe_load(f)
        return cfg.get("machine_limits", {})
    except Exception:
        return {}

LIMITS = _load_limits()

# ─── Causal Rules v2 Yükle ───────────────────────────────────────────────────
def _load_causal_rules():
    try:
        with open(RULES_PATH) as f:
            data = json.load(f)
        return data.get("rules", {}), data.get("hpr_type_filter", {})
    except Exception:
        return {}, {}

CAUSAL_RULES, HPR_TYPE_MAP = _load_causal_rules()
DIKEY_PRESLER = HPR_TYPE_MAP.get("dikey_pres", ["HPR001", "HPR003", "HPR005"])
YATAY_PRESLER = HPR_TYPE_MAP.get("yatay_pres", ["HPR002", "HPR004", "HPR006"])

# ─── API Cache Layer (10dk TTL) ──────────────────────────────────────────────
class CacheLayer:
    def __init__(self, ttl_seconds=600, max_size=50):
        self._cache = OrderedDict()
        self._ttl = ttl_seconds
        self._max_size = max_size

    def get(self, key: str):
        if key in self._cache:
            entry = self._cache[key]
            if time.time() - entry["ts"] < self._ttl:
                return entry["value"]
            del self._cache[key]
        return None

    def set(self, key: str, value):
        if len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)
        self._cache[key] = {"value": value, "ts": time.time()}

    def stats(self):
        valid = sum(1 for e in self._cache.values() if time.time() - e["ts"] < self._ttl)
        return {"cached": valid, "total": len(self._cache), "ttl_seconds": self._ttl}

_api_cache = CacheLayer(ttl_seconds=600)

# ─── Sensör Türkçe İsimleri ──────────────────────────────────────────────────
SENSOR_TR = {
    "main_pressure":              "Ana Basınç",
    "horizontal_press_pressure":  "Yatay Basınç",
    "oil_tank_temperature":       "Yağ Sıcaklığı",
    "lower_ejector_pressure":     "Alt İtici Bas.",
    "horitzonal_infeed_speed":    "Yatay İlerleme",
    "vertical_infeed_speed":      "Dikey İlerleme",
    "part_count":                 "Parça Sayacı",
}
def _tr(s): return SENSOR_TR.get(s, s.replace("_", " ").title())

# ─── Causal Teşhis Motoru ────────────────────────────────────────────────────
def _evaluate_causal_rules(machine_id: str, sensor_values: dict, operating_minutes: float = 120) -> list:
    """Canlı sensör verisiyle causal rules v2 değerlendir. Aktif teşhis listesi döner."""
    diagnoses = []
    lims = LIMITS.get(machine_id, {})

    # HPR tipi belirle
    if machine_id in DIKEY_PRESLER:
        machine_type = "dikey_pres"
    elif machine_id in YATAY_PRESLER:
        machine_type = "yatay_pres"
    else:
        return diagnoses

    for rule_name, rule in CAUSAL_RULES.items():
        allowed = rule.get("hpr_types", ["all"])
        if "all" not in allowed and machine_type not in allowed:
            continue

        condition = rule.get("condition", {})
        all_met = True

        for cond_key, cond_expr in condition.items():
            op = ">" if ">" in cond_expr else "<"
            threshold = float(cond_expr.replace(">", "").replace("<", "").strip())

            if cond_key.endswith("_ratio"):
                base = cond_key.replace("_ratio", "")
                val = sensor_values.get(base)
                lim_max = lims.get(base, {}).get("max")
                if val is None or not lim_max or lim_max == 0:
                    all_met = False; break
                actual = abs(val) / abs(lim_max)
            elif cond_key == "operating_minutes":
                actual = operating_minutes
            elif cond_key == "pressure_line_filter_dirty_minutes":
                actual = sensor_values.get("_filter_dirty_minutes", 0)
            else:
                actual = sensor_values.get(cond_key)
                if actual is None:
                    all_met = False; break

            if op == ">" and not (actual > threshold):
                all_met = False; break
            if op == "<" and not (actual < threshold):
                all_met = False; break

        if all_met:
            diagnoses.append({
                "rule":           rule_name,
                "risk_add":       rule.get("risk_multiplier", 0),
                "explanation_tr": rule.get("explanation_tr", ""),
                "action_tr":      rule.get("action_tr", ""),
            })

    return diagnoses

# ─── Kafka Lag Hesapla ────────────────────────────────────────────────────────
def _get_kafka_lag() -> dict:
    """state.json yaşına göre veri gecikmesini hesaplar."""
    try:
        mtime = os.path.getmtime(STATE_PATH)
        lag_seconds = time.time() - mtime
        if lag_seconds < 30:
            level = "CANLI"
        elif lag_seconds < 300:
            level = "NORMAL"
        elif lag_seconds < 3600:
            level = "GECİKMELİ"
        else:
            level = "KRİTİK"
        return {
            "lag_seconds": round(lag_seconds),
            "level": level,
            "last_update": datetime.fromtimestamp(mtime).strftime("%H:%M:%S"),
        }
    except Exception:
        return {"lag_seconds": -1, "level": "BİLİNMİYOR", "last_update": "—"}

# ─── State okuma yardımcıları (I/O Optimized) ──────────────────────────────
_state_cache = {"mtime": 0.0, "data": {}}
_context_cache = {"mtime": 0.0, "data": {}}

def read_state() -> dict:
    """Disk I/O optimize edilmiş state okuması (mtime control)"""
    try:
        if not os.path.exists(STATE_PATH):
            return {}
        mtime = os.path.getmtime(STATE_PATH)
        if mtime > _state_cache["mtime"]:
            with open(STATE_PATH) as f:
                raw = json.load(f)
            _state_cache["data"] = raw.get("machines", {})
            _state_cache["mtime"] = mtime
        return _state_cache["data"]
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("State okuma hatası:")
        return _state_cache["data"]

def read_context() -> dict:
    """JSONL formatındaki context dosyasından istatistik okur."""
    try:
        if not os.path.exists(CONTEXT_PATH):
            return {}
        mtime = os.path.getmtime(CONTEXT_PATH)
        if mtime > _context_cache["mtime"]:
            total_windows = 0
            total_valid = 0
            with open(CONTEXT_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        total_windows += 1
                        if data.get("labels", {}).get("is_valid_fault"):
                            total_valid += 1
                    except json.JSONDecodeError:
                        continue
            _context_cache["data"] = {
                "summary": {
                    "total_context_windows": total_windows,
                    "total_valid_faults": total_valid,
                }
            }
            _context_cache["mtime"] = mtime
        return _context_cache["data"]
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Context okuma hatası:")
        return _context_cache["data"]

# ─── Makine payload ───────────────────────────────────────────────────────────
def build_machines_payload() -> list:
    state = read_state()
    result = []

    for mid in sorted(state.keys()):
        if not mid.startswith("HPR"):
            continue
        if mid not in LIMITS:
            continue

        ms = state[mid]
        means  = ms.get("ewma_mean",    {}) or {}
        counts = ms.get("sample_count", {}) or {}
        lims   = LIMITS.get(mid, {})

        # Risk skoru
        risk_score = ms.get("risk_score", 5.0) or 5.0
        severity   = ms.get("severity",   "NORMAL") or "NORMAL"
        if risk_score >= 75:
            severity = "KRİTİK"
        elif risk_score >= 55:
            severity = "YÜKSEK"
        elif risk_score >= 30:
            severity = "ORTA"

        # Sensörler + limit yüzdesi
        sensors = []
        for skey, val in means.items():
            if val is None:
                continue
            lim     = lims.get(skey, {})
            if not lim:
                continue
                
            max_l   = lim.get("max")
            warn_l  = lim.get("warn_level")

            if max_l and max_l > 0:
                pct = abs(val) / max_l * 100
            else:
                pct = 0.0

            # Uyarı seviyesi belirle
            if warn_l and abs(val) >= warn_l and max_l and abs(val) < max_l:
                status = "warn"
            elif max_l and abs(val) >= max_l:
                status = "critical"
            else:
                status = "normal"

            # Pre-Fault: %90'a yaklaşma uyarısı
            pre_fault = False
            if max_l and max_l > 0 and status == "normal":
                ratio = abs(val) / max_l
                if ratio >= 0.90:
                    status = "pre_fault"
                    pre_fault = True

            sensors.append({
                "key":    skey,
                "label":  _tr(skey),
                "value":  round(val, 2),
                "unit":   lim.get("unit", ""),
                "pct":    round(pct, 1),
                "warn_level": warn_l,
                "max":    max_l,
                "status": status,
                "pre_fault": pre_fault,
            })

        sensors.sort(key=lambda x: x["pct"], reverse=True)

        # Causal Rules Teşhis (hpr_monitor.py'nin CausalEvaluator çıktısı)
        diag_name = ms.get("diagnosis", "")
        diag_desc = ms.get("diagnosis_desc", "")
        diagnoses = [{"rule": diag_name, "explanation_tr": diag_desc, "risk_add": ""}] if diag_name else []

        # Makine tipi
        if mid in YATAY_PRESLER:
            machine_type = "Yatay Pres"
        elif mid in DIKEY_PRESLER:
            machine_type = "Dikey Pres"
        else:
            machine_type = "HPR"

        result.append({
            "id":        mid,
            "type":      machine_type,
            "execution": ms.get("last_execution", "—"),
            "risk_score": round(risk_score, 1),
            "severity":   severity,
            "sensors":    sensors[:6],
            "diagnoses":  diagnoses,
            "total_samples": counts.get(list(counts.keys())[0], 0) if counts else 0,
        })

    return result

# ─── AI Usta Başı ─────────────────────────────────────────────────────────────
_usta_instance = None

def _get_usta():
    """Lazy-init UstaBasi singleton."""
    global _usta_instance
    if _usta_instance is not None:
        return _usta_instance
    try:
        from pipeline.llm_engine import get_usta
        _usta_instance = get_usta()
        return _usta_instance
    except Exception as e:
        return None

def _build_context_for(machine_id: str, machine_payload: dict) -> dict:
    """Web server için makine bağlam paketi oluşturur. Causal teşhisleri Gemini'ye aktarır."""
    state = read_state()
    ms    = state.get(machine_id, {})
    means = ms.get("ewma_mean", {}) or {}
    sensors = {k: v for k, v in means.items() if v is not None}

    # Sensor states
    sensor_states = {}
    lims = LIMITS.get(machine_id, {})
    limit_violations = []
    critical_sensors = []

    for s, v in sensors.items():
        lim   = lims.get(s, {})
        max_l = lim.get("max")
        warn_l = lim.get("warn_level")
        pct   = abs(v) / max_l * 100 if max_l and max_l > 0 else 0.0

        # Limit ihlali ve kritik sensör tespiti
        if max_l and abs(v) >= max_l:
            limit_violations.append(
                f"{_tr(s)}: {v:.1f} {lim.get('unit','')} (limit: {max_l} — %{pct:.0f} AŞILDI)"
            )
        elif max_l and pct >= 85:
            critical_sensors.append(
                f"{_tr(s)}: {v:.1f} {lim.get('unit','')} (limitin %{pct:.0f}'ine ulaştı)"
            )

        sensor_states[s] = {
            "turkish_name": _tr(s),
            "value":        round(v, 2),
            "unit":         lim.get("unit", ""),
            "limit_pct":    round(pct, 1),
            "status_label": "⛔ LİMİT AŞILDI" if pct >= 100 else ("🟡 DİKKAT" if pct >= 75 else "✅ Normal"),
            "trend_arrow":  "→",
            "slope_per_hour": None,
        }

    risk_score = machine_payload.get("risk_score", 0)
    severity   = machine_payload.get("severity",   "NORMAL")

    # Causal teşhisleri aktif fizik kurallarına dönüştür
    active_rules = []
    diagnoses = machine_payload.get("diagnoses", [])
    for d in diagnoses:
        active_rules.append(
            f"🩺 {d['rule'].upper()}: {d['explanation_tr']} (risk: +{d['risk_add']}) → Öneri: {d['action_tr']}"
        )

    # Benzer geçmiş olaylar
    similar = []
    try:
        from pipeline.similarity_engine import find_similar
        similar = find_similar(sensors, machine_id, top_k=3, min_similarity=0.75)
    except Exception:
        pass

    return {
        "machine_id":          machine_id,
        "timestamp":           datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "risk_score":          risk_score,
        "severity":            severity,
        "confidence":          ms.get("confidence", 0) or 0,
        "operating_time":      f"{(ms.get('operating_minutes', 0) or 0) // 60} saat",
        "operating_minutes":   ms.get("operating_minutes", 0) or 0,
        "last_alert_source":   ms.get("last_alert_source", ""),
        "alert_count_session": ms.get("alert_count", 0) or 0,
        "sensor_states":       sensor_states,
        "limit_violations":    limit_violations,
        "critical_sensors":    critical_sensors,
        "eta_predictions":     {},
        "active_physics_rules": active_rules,
        "last_alerts":         ms.get("last_alerts", [])[-3:],
        "similar_past_events": similar,
    }

# ─── Context Builder için Machine Data Hazırlama ─────────────────────────────
def _build_machine_data_for_context(machine_id: str) -> dict:
    """
    state.json'dan context_builder.build() için machine_data dict'i oluşturur.
    EWMA ortalamaları sensör değeri, buffer'dan trend eğimi hesaplanır.
    """
    state = read_state()
    ms = state.get(machine_id, {})

    # Sensör değerleri: EWMA ortalamadan
    sensors = {}
    for sensor, val in (ms.get("ewma_mean") or {}).items():
        if val is not None:
            sensors[sensor] = round(val, 2)

    # Trend bilgisi: buffer'dan basit eğim hesabı (10 sn örnekleme varsayımı)
    trend_info = {}
    for sensor, buf in (ms.get("buffers") or {}).items():
        if isinstance(buf, list) and len(buf) >= 2:
            # saat başına eğim: (son - ilk) / n * 360
            slope = (buf[-1] - buf[0]) / max(len(buf), 1) * 360
            trend_info[sensor] = round(slope, 4)

    # Boolean sensörler: kaç dakikadır aktif?
    booleans = {}
    for sensor, ts_str in (ms.get("bool_active_since") or {}).items():
        if ts_str:
            try:
                since = datetime.fromisoformat(ts_str)
                minutes = (datetime.now(timezone.utc) - since).total_seconds() / 60
                booleans[sensor] = round(minutes, 1)
            except Exception:
                booleans[sensor] = 0.0
        else:
            booleans[sensor] = None

    # Çalışma süresi
    startup_ts = ms.get("startup_ts")
    operating_minutes = 0.0
    if startup_ts:
        try:
            operating_minutes = round((time.time() - startup_ts) / 60, 1)
        except Exception:
            pass

    return {
        "sensors": sensors,
        "trend_info": trend_info,
        "risk_score": ms.get("risk_score", 0.0) or 0.0,
        "severity": ms.get("severity", "NORMAL") or "NORMAL",
        "operating_minutes": operating_minutes,
        "last_alert_source": ms.get("last_alert_source", "") or "",
        "alert_count": ms.get("alert_count", 0) or 0,
        "confidence": ms.get("confidence", 0.0) or 0.0,
        "last_alerts": ms.get("last_alerts", []) or [],
        "diagnosis": ms.get("diagnosis", "") or "",
        "diagnosis_desc": ms.get("diagnosis_desc", "") or "",
        "last_ml_features": ms.get("last_ml_features", {}) or {},
        "booleans": booleans,
    }


# ─── Endpoint'ler ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(str(STATIC_DIR), "index.html")

@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(str(STATIC_DIR), filename)


@app.route("/api/machines")
def api_machines():
    return jsonify({
        "machines":       build_machines_payload(),
        "updated_at":     datetime.now().strftime("%H:%M:%S"),
        "context_faults": read_context().get("summary", {}).get("total_valid_faults", 0),
        "kafka_lag":      _get_kafka_lag(),
    })


@app.route("/api/status")
def api_status():
    state = read_state()
    ctx   = read_context()
    return jsonify({
        "machine_count": len(state),
        "valid_faults":  ctx.get("summary", {}).get("total_valid_faults", 0),
        "state_updated": os.path.getmtime(STATE_PATH) if STATE_PATH.exists() else 0,
        "server_time":   datetime.now().isoformat(),
        "kafka_lag":     _get_kafka_lag(),
        "cache_stats":   _api_cache.stats(),
    })


@app.route("/api/lag")
def api_lag():
    """Kafka veri gecikmesi detayları."""
    return jsonify(_get_kafka_lag())


@app.route("/api/ask", methods=["POST"])
def api_ask():
    """Usta Başı'na makine bazlı soru sor. Body: {machine_id, question}"""
    body       = request.get_json(force=True) or {}
    machine_id = body.get("machine_id", "").strip()
    question   = body.get("question",   "").strip()

    if not machine_id or not question:
        return jsonify({"error": "machine_id ve question gerekli"}), 400

    usta = _get_usta()
    if not usta or not usta.is_ready:
        return jsonify({
            "machine_id": machine_id,
            "question":   question,
            "answer":     "AI Usta Başı şu an kullanılamıyor. GEMINI_API_KEY tanımlı mı?",
            "timestamp":  datetime.now().strftime("%H:%M:%S"),
        })

    # Cache kontrolü — aynı makine + aynı soru = 10dk cache
    cache_key = f"{machine_id}:{question[:100]}"
    cached = _api_cache.get(cache_key)
    if cached:
        cached["from_cache"] = True
        return jsonify(cached)

    machines = build_machines_payload()
    payload  = next((m for m in machines if m["id"] == machine_id), {})
    ctx      = _build_context_for(machine_id, payload)
    answer   = usta.ask(ctx, question)

    response = {
        "machine_id": machine_id,
        "question":   question,
        "answer":     answer or "Yanıt üretilmedi.",
        "timestamp":  datetime.now().strftime("%H:%M:%S"),
        "from_cache": False,
    }
    if answer:
        _api_cache.set(cache_key, response)

    return jsonify(response)


@app.route("/api/fleet", methods=["GET"])
def api_fleet():
    """Tüm HPR makineleri karşılaştırmalı analiz."""
    usta = _get_usta()
    if not usta or not usta.is_ready:
        return jsonify({"analysis": "AI Usta Başı kullanılamıyor.", "source": "error"})

    machines = build_machines_payload()
    all_ctx  = {m["id"]: _build_context_for(m["id"], m) for m in machines}
    analysis = usta.fleet_summary(all_ctx)

    return jsonify({
        "analysis":  analysis or "Filo analizi üretilemedi.",
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    })


# ─── Server-Sent Events ───────────────────────────────────────────────────────
def event_stream():
    """2 saniyede bir makine verisi push eder."""
    while True:
        try:
            payload = json.dumps({
                "machines":   build_machines_payload(),
                "updated_at": datetime.now().strftime("%H:%M:%S"),
                "kafka_lag":  _get_kafka_lag(),
            })
            yield f"data: {payload}\n\n"
        except Exception as e:
            yield f"data: {{\"error\": \"{e}\"}}\n\n"
        time.sleep(2)


@app.route("/stream")
def stream():
    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ─── Multi-Agent API Endpoint'leri ───────────────────────────────────────────

@app.route("/api/multi-agent/analyze/<machine_id>", methods=["POST"])
@async_route
async def api_multi_agent_analyze(machine_id):
    """
    Multi-agent analiz başlat.

    Query params:
    - force: bool (cache'i atla)
    - mode: str (rapor modu: technician/manager/formal/emergency — varsayılan: hepsi)
    """
    _performance_stats["total_requests"] += 1
    start_time = time.time()

    # 1. Makine ID doğrulama
    if not machine_id or not machine_id.startswith("HPR"):
        return jsonify({"error": "Geçersiz makine ID. HPR ile başlamalı."}), 400

    # 2. Rate limit kontrolü
    if not check_rate_limit(machine_id):
        return jsonify({"error": "Rate limit aşıldı. Dakikada max 5 istek."}), 429

    # 3. State'den makine verisi oku
    state = read_state()
    if machine_id not in state:
        return jsonify({"error": f"{machine_id} için state verisi bulunamadı."}), 404

    # 4. Context oluştur
    try:
        from pipeline import context_builder
        machine_data = _build_machine_data_for_context(machine_id)
        context = context_builder.build(machine_id, machine_data, LIMITS, str(RULES_PATH))
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.exception("Context oluşturma hatası:")
        return jsonify({"error": f"Context oluşturulamadı: {str(e)}"}), 500

    # Query params
    force = request.args.get("force", "false").lower() in ("true", "1", "yes")
    mode = request.args.get("mode", "all").lower()

    # 5. Coordinator'ı al ve analiz et
    try:
        coordinator = get_coordinator()
        result = await coordinator.analyze(context, force=force)
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.exception("Multi-agent analiz hatası:")
        return jsonify({
            "success": False,
            "machine_id": machine_id,
            "error": f"Analiz sırasında hata oluştu: {str(e)}",
            "fallback_message": "Multi-agent sistem şu an yanıt veremiyor. Lütfen daha sonra tekrar deneyin.",
        }), 500

    # 6. Rapor verilerini çıkar
    execution_time = time.time() - start_time
    _performance_stats["total_execution_time"] += execution_time

    report_data = result.get("report", {}) or {}
    risk_level = result.get("risk_level", "normal")
    risk_score = context.get("risk_score", 0.0)

    # Rapor ID üret
    report_id = report_data.get("report_id") if isinstance(report_data, dict) else None
    if not report_id:
        report_id = f"RPT-{machine_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"

    # 7. Raporu sakla
    report_payload = {
        "report_id": report_id,
        "machine_id": machine_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "risk_score": risk_score,
        "risk_level": risk_level,
        "execution_time_sec": round(execution_time, 2),
        "agents_used": result.get("agents_called", []),
        "report": report_data,
        "diagnosis": result.get("diagnosis"),
        "root_cause": result.get("root_cause"),
        "prediction": result.get("prediction"),
        "action": result.get("action"),
    }
    _store_report(report_id, report_payload)

    # 8. Yanıt oluştur
    response = {
        "success": True,
        "machine_id": machine_id,
        "report_id": report_id,
        "risk_score": round(risk_score, 1),
        "risk_level": risk_level,
        "execution_time": round(execution_time, 2),
        "agents_used": result.get("agents_called", []),
        "report": report_data,
        "metadata": {
            "cache_hit": result.get("cache_hit", False),
            "throttled": report_data.get("status") == "throttled" if isinstance(report_data, dict) else False,
            "force": force,
            "mode": mode,
        },
    }

    return jsonify(response)


@app.route("/api/multi-agent/status", methods=["GET"])
def api_multi_agent_status():
    """Multi-agent sistem durumu."""
    coordinator = get_coordinator()

    # Agent durumlarını kontrol et
    agent_statuses = {}
    try:
        from src.analysis.diagnosis_agent import get_diagnosis_agent
        from src.analysis.root_cause_agent import get_root_cause_agent
        from src.analysis.prediction_agent import get_prediction_agent
        from src.analysis.action_agent import get_action_agent
        from src.analysis.report_agent import get_report_agent

        agents = {
            "diagnosis": get_diagnosis_agent,
            "root_cause": get_root_cause_agent,
            "prediction": get_prediction_agent,
            "action": get_action_agent,
            "report": get_report_agent,
        }

        for name, getter in agents.items():
            try:
                agent = getter()
                agent_statuses[name] = {
                    "ready": getattr(agent, "is_ready", True),
                    "fallback_capable": True,  # Tüm ajanlar yerel şablonla çalışabilir
                }
            except Exception:
                agent_statuses[name] = {
                    "ready": False,
                    "fallback_capable": True,
                }
    except Exception as e:
        agent_statuses = {"error": str(e)}

    # Performans istatistikleri
    total_req = _performance_stats["total_requests"]
    total_exec = _performance_stats["total_execution_time"]
    avg_exec = round(total_exec / total_req, 2) if total_req > 0 else 0.0

    return jsonify({
        "active": True,
        "coordinator_ready": coordinator is not None,
        "cache": _api_cache.stats(),
        "agent_statuses": agent_statuses,
        "performance": {
            "avg_execution_time": avg_exec,
            "total_requests": total_req,
            "cache_hit_rate": 0.0,  # Detaylı cache tracking eklenebilir
        },
        "report_store": {
            "stored_reports": len(_report_store),
            "max_reports": _MAX_REPORT_STORE,
        },
        "timestamp": datetime.now().isoformat(),
    })


@app.route("/api/multi-agent/reports/<report_id>", methods=["GET"])
def api_get_report(report_id):
    """Daha önce oluşturulmuş raporu getir."""
    report = _report_store.get(report_id)
    if not report:
        return jsonify({"error": "Rapor bulunamadı."}), 404
    return jsonify({
        "success": True,
        "report": report,
    })


# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🏭 Codlean MES Web Dashboard başlatılıyor...")
    print(f"   → http://localhost:5001")
    print(f"   Usta Başı API: /api/ask (POST)  /api/fleet (GET)")
    print(f"   Multi-Agent API: /api/multi-agent/analyze/<machine_id> (POST)")
    print(f"   State: {STATE_PATH}")
    
    # Erişim: Local WiFi + VPN (0.0.0.0)
    # Güvenlik: macOS Firewall dış erişimi engelliyor
    print(f"   🚀 Sunucu başlatılıyor: http://0.0.0.0:5001")
    print(f"   📡 Erişim: Local WiFi + VPN")
    print(f"   🔒 Dış internet: ENGELLENDİ (firewall)")
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)
