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

import json
import os
import sys
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, Response, send_from_directory, request

# ─── Yollar ──────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).resolve().parents[2]
STATE_PATH   = BASE_DIR / "state.json"
CONTEXT_PATH = BASE_DIR / "rich_context_windows.json"
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
    """Disk I/O optimize edilmiş context okuması (mtime control)"""
    try:
        if not os.path.exists(CONTEXT_PATH):
            return {}
        mtime = os.path.getmtime(CONTEXT_PATH)
        if mtime > _context_cache["mtime"]:
            with open(CONTEXT_PATH) as f:
                _context_cache["data"] = json.load(f)
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

        result.append({
            "id":        mid,
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


# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🏭 Codlean MES Web Dashboard başlatılıyor...")
    print(f"   → http://localhost:5001")
    print(f"   Usta Başı API: /api/ask (POST)  /api/fleet (GET)")
    print(f"   State: {STATE_PATH}")
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)
