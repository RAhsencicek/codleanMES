"""
pipeline/ml_predictor.py — ML Risk Tahmincisi
═══════════════════════════════════════════════
Eğitilmiş XGBoost modelini (model.pkl) yükleyerek
State Store'dan gelen anlık sensör durumundan
ML tabanlı risk skoru (0-100) üretir.

Kullanım (risk_scorer.py içinden):
    from pipeline.ml_predictor import MLPredictor
    predictor = MLPredictor()  # Singleton, sadece bir kez yükle
    result = predictor.predict_risk(machine_id, state)
    # result → MLRiskResult(score, confidence, top_features, explanation)
"""

import os
import json
import pickle
import logging
import warnings
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

warnings.filterwarnings("ignore")
log = logging.getLogger("ml_predictor")

# ─── Model dosya yolları ─────────────────────────────────────────────────────
_DIR          = os.path.dirname(os.path.abspath(__file__))
MODEL_PKL     = os.path.join(_DIR, "model", "model.pkl")
FEATURE_JSON  = os.path.join(_DIR, "model", "feature_names.json")

# ─── violation_log'dan öğrenilen sensör sırası ───────────────────────────────
HPR_SENSORS = [
    "oil_tank_temperature",
    "main_pressure",
    "horizontal_press_pressure",
    "lower_ejector_pressure",
    "horitzonal_infeed_speed",
    "vertical_infeed_speed",
]


@dataclass
class MLRiskResult:
    """ML modeli çıktısı. risk_scorer.py bu nesneyi tüketir."""
    score:        float               # 0-100 arası ML risk skoru
    confidence:   float               # 0-1 arası model güveni (anomali olasılığı)
    active:       bool                # Model yüklü ve çalışıyor mu?
    explanation:  str = ""            # İnsan okunabilir açıklama
    top_features: list[str] = field(default_factory=list)  # En önemli tetikleyiciler


class MLPredictor:
    """
    Singleton benzeri yapı — risk_scorer import ettiğinde tek seferlik yüklenir.

    Dahili mantık:
      1. State Store'daki ring buffer ve EWMA'dan özellik vektörü oluştur
      2. Eğitim sırasında kullanılan feature_names.json ile hizalama yap
      3. Model.predict_proba() → anomali olasılığı → 0-100 skora çevir
      4. Feature importance ile hangi sensörün tetiklediğini açıkla
    """

    def __init__(self):
        self._model        = None
        self._feature_meta = None
        self._feature_names: list[str] = []
        self._importances:   np.ndarray | None = None
        self._active        = False
        self._shap_explainer = None
        self._dlime_explainer = None
        self._nlg_engine    = None
        self._load()

    # ─── Yükleme ─────────────────────────────────────────────────────────────

    def _load(self):
        if not os.path.exists(MODEL_PKL):
            log.warning("ML model dosyası bulunamadı: %s", MODEL_PKL)
            log.warning("  → Önce 'python3 train_model.py' çalıştırın.")
            return

        try:
            with open(MODEL_PKL, "rb") as f:
                self._model = pickle.load(f)
            log.info("✅ ML model yüklendi: %s", MODEL_PKL)
        except Exception as e:
            log.error("Model yüklenemedi: %s", e)
            return

        if os.path.exists(FEATURE_JSON):
            with open(FEATURE_JSON, "r") as f:
                self._feature_meta = json.load(f)
            if isinstance(self._feature_meta, list):
                self._feature_names = self._feature_meta
                log.info("   Özellik sayısı : %d", len(self._feature_names))
            else:
                self._feature_names = self._feature_meta.get("feature_names", [])
                log.info("   Özellik sayısı : %d", len(self._feature_names))
                log.info("   Model türü     : %s", self._feature_meta.get("model_name", "?"))
        else:
            log.warning("feature_names.json bulunamadı, özellikler hizalanamayacak.")

        # Feature importance (XGBoost / Random Forest / LightGBM hepsi destekler)
        if hasattr(self._model, "feature_importances_"):
            self._importances = self._model.feature_importances_
        else:
            self._importances = None

        # SHAP ve NLG Motorlarını Başlat
        try:
            import shap
            import sys as _local_sys
            import os as _local_os
            
            # src path to path 
            root_dir = _local_os.path.dirname(_local_os.path.dirname(_local_os.path.abspath(__file__)))
            if root_dir not in _local_sys.path:
                _local_sys.path.append(root_dir)
                
            from src.analysis.nlg_engine import CodleanNLGEngine
            from src.analysis.dlime_explainer import DLIMEExplainer
            
            self._shap_explainer = shap.TreeExplainer(self._model)
            # data/ dizinine taşıdığımız yeni dev veri setini (v2) göster
            dataset_path = _local_os.path.join(root_dir, "data", "ml_training_data_v2.csv")
            self._dlime_explainer = DLIMEExplainer(self._model, dataset_path)
            self._nlg_engine = CodleanNLGEngine()
            log.info("✅ XAI (SHAP/DLIME) ve NLG Motoru başarıyla yüklendi.")
        except Exception as e:
            log.warning("⚠️ SHAP/DLIME/NLG başlatılamadı: %s", e)

        self._active = True

    @property
    def is_active(self) -> bool:
        return self._active

    # ─── Ana tahmin fonksiyonu ───────────────────────────────────────────────

    def predict_risk(self, machine_id: str, state: dict) -> MLRiskResult:
        """
        Canlı pipeline'dan çağrılır.

        Parametre:
            machine_id : "HPR001" vb.
            state      : state_store.py'nin döndürdüğü makine state dict'i
                         Şu alanlar kullanılır:
                           state["buffers"]    → {sensor: [float, ...]}
                           state["ewma_mean"]  → {sensor: float}
                           state["ewma_var"]   → {sensor: float}
                           state["sample_count"] → {sensor: int}

        Dönüş:
            MLRiskResult(score=0-100, confidence=0-1, ...)
        """
        if not self._active:
            return MLRiskResult(score=0.0, confidence=0.0, active=False,
                                explanation="ML model yüklü değil.")

        try:
            feature_vector = self._build_features(machine_id, state)
            return self._predict(feature_vector, machine_id)
        except Exception as e:
            log.exception("predict_risk hatası (%s): %s", machine_id, e)
            return MLRiskResult(score=0.0, confidence=0.0, active=False,
                                explanation=f"Tahmin hatası: {e}")

    # ─── Özellik vektörü oluştur ─────────────────────────────────────────────

    def _build_features(self, machine_id: str, state: dict) -> np.ndarray:
        """
        State Store verilerinden eğitimde kullanılan özellik vektörünü üretir.

        Eğitimde pencere bazlı özellikler üretildi; canlıda ring buffer'ın
        son değerlerine bakarak aynı mantığı simüle ediyoruz:
          - fault_count  → son 720 değerde (2 saat) limit aşan kaç tane var
          - value_mean   → EWMA mean (zaten State Store'da hazır)
          - value_std    → EWMA std
          - value_max    → ring buffer'ın son [window] değerindeki max
          - over_ratio   → mean / limit_max

        Sınır değerleri feature_names.json'dan (train sırasında yazılan) alınır.
        """
        from import_limits import get_limits   # ← limits_config.yaml wrapper
        limits = get_limits(machine_id)        # {sensor: {"min":…, "max":…}}
        buffers     = state.get("buffers", {})
        ewma_mean   = state.get("ewma_mean", {})
        ewma_var    = state.get("ewma_var", {})
        sample_cnt  = state.get("sample_count", {})

        from scipy import stats
        from datetime import datetime
        now = datetime.utcnow()
        feat: dict[str, float] = {}

        for sensor in HPR_SENSORS:
            buf = list(buffers.get(sensor, []))
            
            if not buf or len(buf) < 3:
                feat[f"{sensor}_mean"] = 0.0
                feat[f"{sensor}_max"] = 0.0
                feat[f"{sensor}_std"] = 0.0
                feat[f"{sensor}_slope"] = 0.0
                feat[f"{sensor}_volatility"] = 0.0
                continue

            # Son 10 dakika (her mesaj ~10s = ~60 mesaj eder)
            recent = buf[-60:]
            if len(recent) < 3:
                # fallback
                feat[f"{sensor}_mean"] = 0.0
                feat[f"{sensor}_max"] = 0.0
                feat[f"{sensor}_std"] = 0.0
                feat[f"{sensor}_slope"] = 0.0
                feat[f"{sensor}_volatility"] = 0.0
                continue

            arr = np.array(recent, dtype=float)
            mean_v = float(arr.mean())
            std_v = float(arr.std())
            max_v = float(arr.max())
            
            x = np.arange(len(arr))
            slope, _, _, _, _ = stats.linregress(x, arr)
            slope_p_min = slope * 6
            volatility = float(std_v / mean_v) if mean_v != 0 else 0.0
            
            feat[f"{sensor}_mean"] = round(mean_v, 2)
            feat[f"{sensor}_max"] = round(max_v, 2)
            feat[f"{sensor}_std"] = round(std_v, 2)
            feat[f"{sensor}_slope"] = round(slope_p_min, 4)
            feat[f"{sensor}_volatility"] = round(volatility, 4)

        # Eski leaky feature'lar sistemden tamamen çıkarıldı (active_sensors vb.)

        # Eğitim sırasındaki sütun sırasına hizala
        if self._feature_names:
            vector = np.array(
                [feat.get(fname, 0.0) for fname in self._feature_names],
                dtype=float
            )
        else:
            vector = np.array(list(feat.values()), dtype=float)

        state["last_ml_features"] = dict(feat) # ContextBuilder içindeki SimilarityEngine için sakla
        vector = np.nan_to_num(vector, nan=0.0)
        return vector.reshape(1, -1)

    # ─── Tahmin ve skor üretimi ──────────────────────────────────────────────

    def _predict(self, X: np.ndarray, machine_id: str) -> MLRiskResult:
        # Anomali olasılığı (sınıf 1 = FAULT/PRE-FAULT)
        if hasattr(self._model, "predict_proba"):
            proba = float(self._model.predict_proba(X)[0][1])
        elif hasattr(self._model, "score_samples"):
            # Isolation Forest
            raw = float(self._model.score_samples(X)[0])
            proba = max(0.0, min(1.0, (0.0 - raw) / 0.5))
        else:
            proba = 0.0

        # 0-100 skor: logaritmik sıkıştırma ile 0.5 üzeri daha hızlı yükselir
        if proba < 0.5:
            score = proba * 60          # 0-30 arası
        else:
            score = 30 + (proba - 0.5) * 140  # 30-100 arası

        score = round(min(max(score, 0.0), 100.0), 1)

        # En önemli tetikleyicileri bul
        top_features = self._get_top_features(X)
        explanation  = self._build_explanation(proba, top_features)
        
        # ─── SHAP / DLIME ve NLG Entegrasyonu ───
        if self._nlg_engine and proba > 0.01:
            shap_impacts = {}
            used_explainer = "NONE"
            
            try:
                if self._shap_explainer:
                    shap_values = self._shap_explainer.shap_values(X)
                    
                    # Multi-class / 3D array handle
                    if isinstance(shap_values, list):
                        sv = shap_values[1][0]
                    elif len(shap_values.shape) == 3:
                        sv = shap_values[0, :, 1]
                    else:
                        sv = shap_values[0] if not hasattr(shap_values, 'values') else shap_values.values[0]
                    
                    # Dictionary map
                    shap_impacts = {name: float(val) for name, val in zip(self._feature_names, sv)}
                    used_explainer = "SHAP"
                
            except Exception as e:
                log.warning("TreeSHAP hatası, DLIME fallback tetikleniyor: %s", e)
                
            # SHAP Çöktüyse veya yoksa DLIME Devreye Girer
            if not shap_impacts and self._dlime_explainer:
                import pandas as pd
                df_inst = pd.DataFrame(X, columns=self._feature_names)
                dlime_res = self._dlime_explainer.explain(df_inst)
                if "error" not in dlime_res:
                    shap_impacts = dlime_res
                    used_explainer = "DLIME"

            if shap_impacts:
                try:
                    # Sadece skor 0-1 arasında gönderilmeli
                    nlg_exp = self._nlg_engine.generate_explanation(
                        risk_score=score/100.0,
                        shap_impacts=shap_impacts,
                        machine_id=machine_id
                    )
                    if nlg_exp:
                        # Hangi XAI'ın kullanıldığını nota ekle (debugging için)
                        explanation = f"[{used_explainer}] " + nlg_exp
                except Exception as e:
                    log.error("SHAP/DLIME NLG hata: %s", e)
                    import traceback
                    traceback.print_exc()

        return MLRiskResult(
            score=score,
            confidence=round(proba, 3),
            active=True,
            explanation=explanation,
            top_features=top_features,
        )

    def _get_top_features(self, X: np.ndarray, top_n: int = 3) -> list[str]:
        """Feature importance × mevcut değer kombinasyonuyla öne çıkan sütunlar."""
        if self._importances is None or not self._feature_names:
            return []

        x_flat = X.flatten()
        n = min(len(self._importances), len(x_flat), len(self._feature_names))

        # importance × |normalized_value| → en etkili özellikler
        scores = self._importances[:n] * np.abs(x_flat[:n])
        top_idx = np.argsort(scores)[-top_n:][::-1]

        return [self._feature_names[i] for i in top_idx
                if i < len(self._feature_names) and scores[i] > 0]

    def _build_explanation(self, proba: float, top_feats: list[str]) -> str:
        """İnsan okunabilir açıklama cümlesi."""
        pct = int(proba * 100)
        if pct < 20:
            return f"ML: Normal operasyon ({pct}% anomali)."
        if pct < 50:
            return f"ML: Hafif anormallik ({pct}%). Takip: {', '.join(top_feats[:2]) or '—'}"
        return (f"ML Modeli %{pct} ihtimalle yakın arıza öngörüyor. "
                f"Tetikleyenler: {', '.join(top_feats) or '—'}")


# ─── Import yardımcısı (limits_config.yaml olmayan ortamlar için fallback) ────

def _limits_fallback():
    """limits_config.yaml erişimi yoksa basit sabit limitler döner."""
    return {
        "oil_tank_temperature":      {"min": 0,    "max": 45.0},
        "main_pressure":             {"min": 0,    "max": 110.0},
        "horizontal_press_pressure": {"min": 0,    "max": 120.0},
        "lower_ejector_pressure":    {"min": 0,    "max": 110.0},
        "horitzonal_infeed_speed":   {"min": -300, "max": 300.0},
        "vertical_infeed_speed":     {"min": -300, "max": 300.0},
    }


# import_limits modülü yoksa monkey-patch et
import sys as _sys
import types as _types

if "import_limits" not in _sys.modules:
    _mod = _types.ModuleType("import_limits")
    _mod.get_limits = lambda machine_id: _limits_fallback()
    _sys.modules["import_limits"] = _mod


# ─── Modül seviyesi singleton ─────────────────────────────────────────────────
# risk_scorer.py şöyle import eder:
#   from pipeline.ml_predictor import predictor
#   result = predictor.predict_risk(machine_id, state)
predictor = MLPredictor()
