import os
from pathlib import Path

# Kodun çalıştığı ana dizini (Codlean MES Root) dinamik olarak bulur
ROOT_DIR = Path(__file__).resolve().parents[2]

# Veri Yolları
DATA_DIR = ROOT_DIR / "data"
ML_TRAINING_DATA_V2_PATH = str(DATA_DIR / "ml_training_data_v2.csv")
VIOLATION_LOG_PATH = str(DATA_DIR / "violation_log.json")

# Model Yolları
MODEL_DIR = ROOT_DIR / "pipeline" / "model"
ML_MODEL_PKL = str(MODEL_DIR / "model.pkl")
ML_FEATURE_JSON = str(MODEL_DIR / "feature_names.json")

# Dokümantasyon ve Kurallar
CAUSAL_RULES_PATH = str(ROOT_DIR / "docs" / "causal_rules.json")

# Durum ve Yapılandırma
STATE_JSON_PATH = str(ROOT_DIR / "state.json")
LIMITS_YAML_PATH = str(ROOT_DIR / "config" / "limits_config.yaml")
