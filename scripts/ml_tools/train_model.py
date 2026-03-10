"""
train_model.py — HPR Arıza Öncüsü ML Modeli
═══════════════════════════════════════════════
violation_log.json → feature engineering → Random Forest + XGBoost + LightGBM
En yüksek F1 skorunu alan model pipeline/model/ altına kaydedilir.

Çalıştır:
  python3 train_model.py
"""

import json, os, sys, time, pickle, warnings, logging
from datetime import datetime, timezone, timedelta
from collections import defaultdict

import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("train_model")

# ─── Kütüphane kontrolleri ───────────────────────────────────────────────────
try:
    from sklearn.ensemble import RandomForestClassifier, IsolationForest
    from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import classification_report, roc_auc_score, f1_score, confusion_matrix
    from sklearn.utils.class_weight import compute_class_weight
    SKLEARN_OK = True
except ImportError:
    print("❌ scikit-learn yok. Yükle: pip3 install scikit-learn"); sys.exit(1)

try:
    import xgboost as xgb
    _test = xgb.XGBClassifier(n_estimators=1, verbosity=0)
    _test.fit([[0]], [0])          # libxgboost.dylib / libomp testi
    XGBOOST_OK = True
    print("✅ XGBoost hazır")
except Exception as e:
    XGBOOST_OK = False
    print(f"⚠️  XGBoost devre dışı ({e})\n   brew install libomp  →  sorunu çözer")

try:
    import lightgbm as lgb
    LGBM_OK = True
    print("✅ LightGBM hazır")
except ImportError:
    LGBM_OK = False
    print("ℹ️  LightGBM yok (opsiyonel). Yüklemek: pip3 install lightgbm")

# ─── Sabitler ────────────────────────────────────────────────────────────────
VIOLATION_LOG    = "violation_log.json"
LIVE_WINDOWS     = "live_windows.json"   # hpr_monitor.py'nin window_collector'ı yazar
MODEL_DIR        = "pipeline/model"
PRE_FAULT_MINS   = 60     # FAULT'tan kaç dk önce PRE-FAULT sayılır
TIME_WINDOW_MIN  = 10     # Her kaç dk'da bir satır üretilir
MIN_FAULT_ROWS   = 30     # Bu altındaysa Isolation Forest'a geç

HPR_SENSORS = [
    "oil_tank_temperature",
    "main_pressure",
    "horizontal_press_pressure",
    "lower_ejector_pressure",
    "horitzonal_infeed_speed",
    "vertical_infeed_speed",
]

# ─── Yardımcılar ─────────────────────────────────────────────────────────────

def _parse_ts(ts: str):
    if not ts: return None
    try:
        if ts.endswith("Z"): ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except ValueError:
        return None

# ═══════════════════════════════════════════════════════════════════════════
# ADIM 1 — violation_log.json → ham FAULT DataFrame
# ═══════════════════════════════════════════════════════════════════════════

def load_faults(path: str):
    """
    violation_log.json'ı okur.
    Dönüş: (fault_df, normal_windows_df, raw_data)
      fault_df          : FAULT event kayıtları (violations bölümünden)
      normal_windows_df : Gerçek NORMAL ölçümler (normal_windows bölümünden)
                          Eski formatla uyumlu: normal_windows yoksa boş df döner.
    """
    log.info("📂 %s okunuyor...", path)
    t0 = time.time()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    log.info("   JSON yüklendi (%.1fs)", time.time() - t0)

    # ── Scan istatistikleri ──
    stats = data.get("scan_stats", {})
    log.info("   Toplam mesaj : %s", f"{stats.get('total', '?'):,}" if isinstance(stats.get('total'), int) else stats.get('total', '?'))
    log.info("   İlk mesaj    : %s", stats.get("first_ts", "?")[:19])
    log.info("   Son mesaj    : %s", stats.get("last_ts",  "?")[:19])

    # ── label_counts özeti ──
    lc = data.get("label_counts", {})
    for mid, counts in sorted(lc.items()):
        total  = counts.get("normal", 0) + counts.get("fault", 0)
        ratio  = counts["fault"] / total * 100 if total else 0
        icon   = "🔴" if ratio > 5 else "🟡" if ratio > 1 else "✅"
        log.info("   %s %s | normal: %s | fault: %s | oran: %.1f%%",
                 icon, mid, f"{counts.get('normal',0):,}",
                 f"{counts.get('fault',0):,}", ratio)

    # ── FAULT satırlarını çıkar (violations bölümü) ──
    records = []
    for machine_id, sensors in data.get("violations", {}).items():
        for sensor, info in sensors.items():
            total_v = info.get("total", 0)
            for v in info.get("violations", []):
                ts  = _parse_ts(v.get("ts", ""))
                val = v.get("value")
                if ts is None or val is None: continue
                records.append({
                    "machine_id":    machine_id,
                    "sensor":        sensor,
                    "timestamp":     ts,
                    "value":         float(val),
                    "limit_max":     float(v.get("limit_max") or 9999),
                    "limit_min":     float(v.get("limit_min") or -9999),
                    "total_sensor_faults": total_v,
                })

    fault_df = pd.DataFrame(records)
    if fault_df.empty:
        log.error("❌ Hiç FAULT kaydı bulunamadı!"); sys.exit(1)

    if fault_df["timestamp"].dt.tz is None:
        fault_df["timestamp"] = fault_df["timestamp"].dt.tz_localize("UTC")

    fault_df.sort_values("timestamp", inplace=True)
    fault_df.reset_index(drop=True, inplace=True)
    log.info("✅ %d FAULT kaydı | %d makine | %d sensör tür",
             len(fault_df), fault_df["machine_id"].nunique(), fault_df["sensor"].nunique())

    # ── NORMAL pencerelerini çıkar (normal_windows bölümü — yeni format) ──
    normal_records = []
    nw = data.get("normal_windows", {})
    for machine_id, windows in nw.items():
        for win in windows:
            ts  = _parse_ts(win.get("ts", ""))
            if ts is None: continue
            readings = win.get("readings", {})
            for sensor, val in readings.items():
                if sensor not in HPR_SENSORS: continue
                lim = HPR_SENSORS.index(sensor) if isinstance(HPR_SENSORS, list) else None
                # limit_max: sabit tabloya bak
                _lim_map = {
                    "oil_tank_temperature":      45.0,
                    "main_pressure":             110.0,
                    "horizontal_press_pressure": 120.0,
                    "lower_ejector_pressure":    110.0,
                    "horitzonal_infeed_speed":   300.0,
                    "vertical_infeed_speed":     300.0,
                }
                normal_records.append({
                    "machine_id": machine_id,
                    "sensor":     sensor,
                    "timestamp":  ts,
                    "value":      float(val),
                    "limit_max":  _lim_map.get(sensor, 9999.0),
                    "limit_min":  0.0,
                    "total_sensor_faults": 0,
                })

    if normal_records:
        normal_df = pd.DataFrame(normal_records)
        if normal_df["timestamp"].dt.tz is None:
            normal_df["timestamp"] = normal_df["timestamp"].dt.tz_localize("UTC")
        normal_df.sort_values("timestamp", inplace=True)
        normal_df.reset_index(drop=True, inplace=True)
        log.info("✅ %d NORMAL sensör kaydı | %d makine (%d pencere)",
                 len(normal_df), normal_df["machine_id"].nunique(), len(nw))
    else:
        normal_df = pd.DataFrame(columns=fault_df.columns)
        log.warning("⚠️  normal_windows bulunamadı — eski format. "
                    "NORMAL örnekler sadece fault olmayan pencerelerden çıkarılacak.")

    return fault_df, normal_df, data

# ═══════════════════════════════════════════════════════════════════════════
# ADIM 2 — Zaman penceresi bazlı özellik mühendisliği
# ═══════════════════════════════════════════════════════════════════════════

def engineer_features(fault_df: pd.DataFrame,
                      normal_df: pd.DataFrame) -> pd.DataFrame:
    """
    Her makine için TIME_WINDOW_MIN'lik pencerelerle özellik matrisi üretir.

    İki kaynak:
      1. fault_df     : limit aşan anlar → FAULT pencereleri
      2. normal_df    : gerçek normal ölçümler → NORMAL pencereleri
                        (kafka_scan.py'nin normal_windows bölümünden gelir)

    Özellikler (her sensör × 5):
      _fault_count  : penceredeki FAULT sayısı (normal pencerelerde = 0)
      _value_mean   : ortalama sensör değeri
      _value_std    : standart sapma
      _value_max    : maks değer
      _over_ratio   : ortalama (value / limit_max)  > 1 ise aşım

    Makine geneli:
      active_sensors       : kaç sensörde FAULT var
      multi_sensor_fault   : 2+ sensörde eş zamanlı FAULT
      total_faults_window  : penceredeki toplam FAULT
    """
    log.info("🔧 Özellik mühendisliği başlıyor...")
    rows = []
    machines = sorted(fault_df["machine_id"].unique())
    log.info("   Makineler: %s", machines)

    _lim_map = {
        "oil_tank_temperature":      45.0,
        "main_pressure":             110.0,
        "horizontal_press_pressure": 120.0,
        "lower_ejector_pressure":    110.0,
        "horitzonal_infeed_speed":   300.0,
        "vertical_infeed_speed":     300.0,
    }

    # ── 1. FAULT pencereleri (violations kaynaklı) ──────────────────────────
    for machine_id in machines:
        mdf = fault_df[fault_df["machine_id"] == machine_id].copy()
        mdf = mdf.set_index("timestamp").sort_index()

        t_start = mdf.index.min().floor("h")
        t_end   = mdf.index.max().ceil("h")
        if pd.isnull(t_start) or pd.isnull(t_end): continue

        delta = timedelta(minutes=TIME_WINDOW_MIN)
        t_cur = t_start
        while t_cur < t_end:
            t_next = t_cur + delta
            window = mdf.loc[t_cur:t_next]

            row = {
                "machine_id":   machine_id,
                "window_start": t_cur,
                "_source":      "fault",
            }

            active_sensors = 0
            for sensor in HPR_SENSORS:
                sdata = window[window["sensor"] == sensor]
                n = len(sdata)
                if n == 0:
                    row[f"{sensor}__fault_count"] = 0
                    row[f"{sensor}__value_mean"]  = 0.0
                    row[f"{sensor}__value_std"]   = 0.0
                    row[f"{sensor}__value_max"]   = 0.0
                    row[f"{sensor}__over_ratio"]  = 0.0
                else:
                    lim = sdata["limit_max"].iloc[0]
                    row[f"{sensor}__fault_count"] = n
                    row[f"{sensor}__value_mean"]  = sdata["value"].mean()
                    row[f"{sensor}__value_std"]   = sdata["value"].std() if n > 1 else 0.0
                    row[f"{sensor}__value_max"]   = sdata["value"].max()
                    row[f"{sensor}__over_ratio"]  = sdata["value"].mean() / lim if lim > 0 else 0.0
                    active_sensors += 1

            row["active_sensors"]      = active_sensors
            row["multi_sensor_fault"]  = 1 if active_sensors >= 2 else 0
            row["total_faults_window"] = len(window)
            rows.append(row)
            t_cur = t_next

    # ── 2. NORMAL pencereler (normal_windows kaynaklı) ──────────────────────
    has_normal_source = not normal_df.empty
    if has_normal_source:
        log.info("   Normal kaynak: %d gerçek ölçüm kaydı var", len(normal_df))
        for machine_id in normal_df["machine_id"].unique():
            ndf = normal_df[normal_df["machine_id"] == machine_id].copy()
            ndf = ndf.set_index("timestamp").sort_index()

            t_start = ndf.index.min().floor("h")
            t_end   = ndf.index.max().ceil("h")
            if pd.isnull(t_start) or pd.isnull(t_end): continue

            delta = timedelta(minutes=TIME_WINDOW_MIN)
            t_cur = t_start
            while t_cur < t_end:
                t_next = t_cur + delta
                window = ndf.loc[t_cur:t_next]
                if window.empty:
                    t_cur = t_next
                    continue

                row = {
                    "machine_id":   machine_id,
                    "window_start": t_cur,
                    "_source":      "normal",
                }

                for sensor in HPR_SENSORS:
                    sdata = window[window["sensor"] == sensor]
                    n = len(sdata)
                    lim = _lim_map.get(sensor, 9999.0)
                    if n == 0:
                        row[f"{sensor}__fault_count"] = 0
                        row[f"{sensor}__value_mean"]  = 0.0
                        row[f"{sensor}__value_std"]   = 0.0
                        row[f"{sensor}__value_max"]   = 0.0
                        row[f"{sensor}__over_ratio"]  = 0.0
                    else:
                        row[f"{sensor}__fault_count"] = 0   # NORMAL → fault_count=0
                        row[f"{sensor}__value_mean"]  = sdata["value"].mean()
                        row[f"{sensor}__value_std"]   = sdata["value"].std() if n > 1 else 0.0
                        row[f"{sensor}__value_max"]   = sdata["value"].max()
                        row[f"{sensor}__over_ratio"]  = sdata["value"].mean() / lim if lim > 0 else 0.0

                row["active_sensors"]      = 0
                row["multi_sensor_fault"]  = 0
                row["total_faults_window"] = 0
                rows.append(row)
                t_cur = t_next
    else:
        log.warning("   ⚠️  Normal kaynak yok — model sadece fault pencereleri görüyor!")
        log.warning("   → kafka_scan.py'yi güncelleyip yeniden tarama yapmanız önerilir.")

    feat_df = pd.DataFrame(rows)
    if feat_df.empty:
        log.error("❌ Özellik matrisi boş!"); sys.exit(1)

    feat_df.fillna(0, inplace=True)

    fault_rows  = (feat_df["_source"] == "fault").sum()  if "_source" in feat_df.columns else len(feat_df)
    normal_rows = (feat_df["_source"] == "normal").sum() if "_source" in feat_df.columns else 0
    log.info("✅ %d satır × %d özellik  (fault=%d | normal_window=%d)",
             len(feat_df), len(feat_df.columns) - 3,   # machine_id, window_start, _source hariç
             fault_rows, normal_rows)
    return feat_df

# ═══════════════════════════════════════════════════════════════════════════
# ADIM 3 — Etiketleme
# ═══════════════════════════════════════════════════════════════════════════

def label_windows(feat_df: pd.DataFrame, fault_df: pd.DataFrame) -> pd.DataFrame:
    """
    PRE-FAULT: FAULT penceresinden PRE_FAULT_MINS dk öncesi
    FAULT    : Doğrudan FAULT olan pencere
    NORMAL   : Diğerleri
    Binary   : NORMAL=0, (PRE-FAULT + FAULT)=1
    """
    log.info("🏷️  Etiketleme (pre-fault penceresi: %d dk)...", PRE_FAULT_MINS)

    # Makine → FAULT pencere zamanları seti
    fault_windows = defaultdict(set)
    pre_delta     = timedelta(minutes=PRE_FAULT_MINS)
    win_delta     = timedelta(minutes=TIME_WINDOW_MIN)

    for machine_id in fault_df["machine_id"].unique():
        for ts in fault_df[fault_df["machine_id"] == machine_id]["timestamp"]:
            fault_windows[machine_id].add(ts.floor(f"{TIME_WINDOW_MIN}min"))

    labels = []
    for _, row in feat_df.iterrows():
        mid = row["machine_id"]
        ws  = row["window_start"]
        fts = fault_windows.get(mid, set())

        if ws in fts:
            labels.append("FAULT")
        elif any(ws <= ft < ws + pre_delta for ft in fts):
            labels.append("PRE-FAULT")
        else:
            labels.append("NORMAL")

    feat_df = feat_df.copy()
    feat_df["label"]        = labels
    feat_df["binary_label"] = (feat_df["label"] != "NORMAL").astype(int)

    dist = feat_df["label"].value_counts()
    log.info("   Etiket dağılımı:")
    icons = {"FAULT": "🔴", "PRE-FAULT": "🟡", "NORMAL": "✅"}
    for lbl in ["FAULT", "PRE-FAULT", "NORMAL"]:
        cnt = dist.get(lbl, 0)
        log.info("     %s %-10s : %5d  (%.1f%%)",
                 icons[lbl], lbl, cnt, cnt / len(feat_df) * 100)
    return feat_df

# ═══════════════════════════════════════════════════════════════════════════
# ADIM 4 — Model eğitimi (RF + XGBoost + LightGBM)
# ═══════════════════════════════════════════════════════════════════════════

def train_and_evaluate(feat_df: pd.DataFrame) -> dict:
    """
    PRODUCTION-READY MODEL EĞİTİMİ
    
    ADIMLAR:
    1. Time-based split (temporal validation)
    2. 5-Fold Cross-Validation (stability check)
    3. 3-Way split ile threshold tuning (train/val/test)
    4. Cost analysis (business impact)
    """
    drop_cols    = ["machine_id", "window_start", "label", "binary_label", "_source"]
    feature_cols = [c for c in feat_df.columns if c not in drop_cols]

    X = feat_df[feature_cols].values
    y = feat_df["binary_label"].values
    
    # ═══════════════════════════════════════════════════════════════════
    # ADIM 1: TIME-BASED SPLIT (Temporal Validation)
    # ═══════════════════════════════════════════════════════════════════
    log.info("\n" + "═"*60)
    log.info("📅 ADIM 1: TIME-BASED SPLIT")
    log.info("═"*60)
    
    # Timestamp'e göre sırala
    feat_df_sorted = feat_df.copy()
    feat_df_sorted['window_start'] = pd.to_datetime(feat_df_sorted['window_start'])
    feat_df_sorted.sort_values('window_start', inplace=True)
    
    # İlk %80 train, son %20 test (geçmişten geleceğe)
    split_idx = int(len(feat_df_sorted) * 0.8)
    train_df = feat_df_sorted.iloc[:split_idx]
    test_df = feat_df_sorted.iloc[split_idx:]
    
    log.info("\n   Train: %d window (tarih: %s → %s)", 
             len(train_df),
             train_df['window_start'].min().strftime('%Y-%m-%d %H:%M'),
             train_df['window_start'].max().strftime('%Y-%m-%d %H:%M'))
    log.info("   Test:  %d window (tarih: %s → %s)",
             len(test_df),
             test_df['window_start'].min().strftime('%Y-%m-%d %H:%M'),
             test_df['window_start'].max().strftime('%Y-%m-%d %H:%M'))
    
    # Train ve test ayır
    X_train = train_df[feature_cols].values
    y_train = train_df['binary_label'].values
    X_test = test_df[feature_cols].values
    y_test = test_df['binary_label'].values

    n_pos = y_train.sum()
    n_neg = (y_train == 0).sum()
    log.info("\n🤖 Model eğitimi | Train - Anomali: %d | Normal: %d | Oran: %.1f%%",
             n_pos, n_neg, n_pos / len(y_train) * 100)
    
    n_pos_test = y_test.sum()
    n_neg_test = (y_test == 0).sum()
    log.info("🤖 Model testi   | Test  - Anomali: %d | Normal: %d | Oran: %.1f%%",
             n_pos_test, n_neg_test, n_pos_test / len(y_test) * 100)

    if n_pos < MIN_FAULT_ROWS:
        log.warning("   Yeterli anomali yok (%d), Isolation Forest kullanılıyor.", n_pos)
        return _train_isolation_forest(X_train, y_train, feature_cols)

    # Sınıf ağırlıkları
    cw = compute_class_weight("balanced", classes=np.array([0, 1]), y=y_train)
    cw_dict = {0: cw[0], 1: cw[1]}
    scale_pw = n_neg / n_pos  # XGBoost için

    # ═══════════════════════════════════════════════════════════════════
    # ADIM 2: 5-FOLD CROSS-VALIDATION (Stability Check)
    # ═══════════════════════════════════════════════════════════════════
    log.info("\n" + "═"*60)
    log.info("🔄 ADIM 2: 5-FOLD CROSS-VALIDATION (Stratified)")
    log.info("═"*60)
    
    from sklearn.model_selection import StratifiedKFold
    
    # Stratified K-Fold: Her fold'da class distribution aynı
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores_f1 = []
    cv_scores_auc = []
    
    log.info("\n   Fold skorları (stratified):")
    for fold, (train_idx, val_idx) in enumerate(skf.split(X_train, y_train)):
        X_tr_fold, X_val_fold = X_train[train_idx], X_train[val_idx]
        y_tr_fold, y_val_fold = y_train[train_idx], y_train[val_idx]
        
        # Class distribution kontrol
        train_fault_rate = y_tr_fold.mean() * 100
        val_fault_rate = y_val_fold.mean() * 100
        
        rf_fold = RandomForestClassifier(
            n_estimators=300, max_depth=14, min_samples_leaf=2,
            class_weight=cw_dict, n_jobs=-1, random_state=42)
        rf_fold.fit(X_tr_fold, y_tr_fold)
        
        y_pred_fold = rf_fold.predict(X_val_fold)
        f1_fold = f1_score(y_val_fold, y_pred_fold)
        
        try:
            y_proba_fold = rf_fold.predict_proba(X_val_fold)[:,1]
            auc_fold = roc_auc_score(y_val_fold, y_proba_fold)
        except:
            auc_fold = 0.0
        
        cv_scores_f1.append(f1_fold)
        cv_scores_auc.append(auc_fold)
        log.info("   Fold %d: F1=%.4f | AUC=%.4f | Fault rate: train=%.1f%%, val=%.1f%%", 
                 fold+1, f1_fold, auc_fold, train_fault_rate, val_fault_rate)
    
    mean_f1 = np.mean(cv_scores_f1)
    std_f1 = np.std(cv_scores_f1)
    mean_auc = np.mean(cv_scores_auc)
    std_auc = np.std(cv_scores_auc)
    
    log.info("\n   ─────────────────────────────────────")
    log.info("   CV F1:  %.4f ± %.4f  (%s)", 
             mean_f1, std_f1, 
             "STABİL ✅" if std_f1 < 0.03 else "INSTABİL ⚠️")
    log.info("   CV AUC: %.4f ± %.4f", mean_auc, std_auc)
    
    stability_status = "STABİL" if std_f1 < 0.03 else "INSTABİL"

    # ═══════════════════════════════════════════════════════════════════
    # ADIM 3: 3-WAY SPLIT İLE THRESHOLD TUNING
    # ═══════════════════════════════════════════════════════════════════
    log.info("\n" + "═"*60)
    log.info("🎯 ADIM 3: THRESHOLD TUNING (3-Way Split)")
    log.info("═"*60)
    
    # Train'den validation ayır (70% train, 30% validation)
    X_tr_final, X_val, y_tr_final, y_val = train_test_split(
        X_train, y_train, test_size=0.3, random_state=42, stratify=y_train)
    
    log.info("\n   Final Train: %d | Validation: %d", len(X_tr_final), len(X_val))
    
    # Random Forest eğit (final train set)
    log.info("\n   🌲 Random Forest eğitiliyor (final train)...")
    rf = RandomForestClassifier(
        n_estimators=300, max_depth=14, min_samples_leaf=2,
        class_weight=cw_dict, n_jobs=-1, random_state=42)
    rf.fit(X_tr_final, y_tr_final)
    
    # Threshold sweep - Recall odaklı optimizasyon
    log.info("\n   Threshold taraması (validation set - recall odaklı):")
    best_threshold = 0.5
    best_f1_val = 0
    threshold_results = []
    
    # Daha ince grid + düşük threshold'lar dahil
    for threshold in np.arange(0.15, 0.60, 0.05):
        y_pred_val = (rf.predict_proba(X_val)[:,1] > threshold).astype(int)
        f1_val = f1_score(y_val, y_pred_val)
        precision_val = np.sum((y_pred_val == 1) & (y_val == 1)) / max(np.sum(y_pred_val == 1), 1)
        recall_val = np.sum((y_pred_val == 1) & (y_val == 1)) / max(np.sum(y_val == 1), 1)
        
        threshold_results.append({
            'threshold': threshold,
            'f1': f1_val,
            'precision': precision_val,
            'recall': recall_val
        })
        
        # F1 + recall trade-off visible
        marker = ""
        if recall_val >= 0.60 and precision_val >= 0.70:
            marker = " ← BALANCED ✓"
        if f1_val > best_f1_val:
            best_f1_val = f1_val
            best_threshold = threshold
            marker = " ← OPTIMAL (F1-max)"
        
        log.info("   Threshold %.2f: F1=%.4f | P=%.3f | R=%.3f%s",
                 threshold, f1_val, precision_val, recall_val, marker)
    
    log.info("\n   ✅ Optimum threshold (F1-max): %.2f (Validation F1=%.4f)",
             best_threshold, best_f1_val)
    
    # Balanced threshold bul (recall >= 0.60, precision >= 0.70)
    balanced_threshold = None
    for result in threshold_results:
        if result['recall'] >= 0.60 and result['precision'] >= 0.70:
            balanced_threshold = result['threshold']
            break
    
    if balanced_threshold:
        log.info("   🎯 BALANCED threshold: %.2f (R>=0.60, P>=0.70)", balanced_threshold)
        final_threshold = balanced_threshold
    else:
        log.info("   ⚠️  Balanced threshold bulunamadı, F1-optimal kullanılıyor: %.2f", best_threshold)
        final_threshold = best_threshold
    
    # ═══════════════════════════════════════════════════════════════════
    # TEST İÇİN THRESHOLD OVERRIDE (Production'da config'den okunacak)
    # ═══════════════════════════════════════════════════════════════════
    # Recall artışı için threshold düşürülüyor (trade-off: precision azalır)
    RECALL_FOCUSED_THRESHOLD = 0.25  # Deneme threshold'u
    if RECALL_FOCUSED_THRESHOLD != final_threshold:
        log.info("\n   🧪 TEST İÇİN: Threshold %.2f → %.2f (recall odaklı)",
                 final_threshold, RECALL_FOCUSED_THRESHOLD)
        final_threshold = RECALL_FOCUSED_THRESHOLD
        log.info("   ⚠️  Beklenen: Precision ↓, Recall ↑↑, F1 →")

    # ═══════════════════════════════════════════════════════════════════
    # ADIM 4: COST ANALYSIS
    # ═══════════════════════════════════════════════════════════════════
    log.info("\n" + "═"*60)
    log.info("💰 ADIM 4: COST ANALYSIS")
    log.info("═"*60)
    
    FALSE_POSITIVE_COST = 10_000  # Üretim kaybı
    FALSE_NEGATIVE_COST = 50_000  # Makine arızası
    
    log.info("\n   Maliyetler:")
    log.info("   • False Positive: $%s (üretim kaybı, teknisyen zamanı)", 
             f"{FALSE_POSITIVE_COST:,}")
    log.info("   • False Negative: $%s (makine arızası, acil duruş)", 
             f"{FALSE_NEGATIVE_COST:,}")
    
    log.info("\n   Threshold bazında toplam maliyet:")
    cost_results = []
    
    for result in threshold_results:
        threshold = result['threshold']
        y_pred_val = (rf.predict_proba(X_val)[:,1] > threshold).astype(int)
        
        tn, fp, fn, tp = confusion_matrix(y_val, y_pred_val).ravel()
        total_cost = fp * FALSE_POSITIVE_COST + fn * FALSE_NEGATIVE_COST
        
        cost_results.append({
            'threshold': threshold,
            'total_cost': total_cost,
            'fp': fp,
            'fn': fn
        })
        
        log.info("   Threshold %.2f: Toplam maliyet = $%s (FP=%d, FN=%d)",
                 threshold, f"{total_cost:,}", fp, fn)
    
    # Minimum cost threshold bul
    min_cost_result = min(cost_results, key=lambda x: x['total_cost'])
    optimal_threshold_cost = min_cost_result['threshold']
    min_cost = min_cost_result['total_cost']
    
    log.info("\n   ✅ Minimum maliyet threshold: %.2f ($%s)",
             optimal_threshold_cost, f"{min_cost:,}")
    
    # Final threshold seçimi (F1 vs Cost trade-off)
    # Balanced threshold zaten seçilmiş olabilir, cost ile conflict varsa F1 öncelikli
    if abs(final_threshold - optimal_threshold_cost) > 0.15:
        log.info("   ⚠️  WARNING: F1-optimal (%.2f) ve cost-optimal (%.2f) çok farklı!",
                 final_threshold, optimal_threshold_cost)
        log.info("   → Balanced/Recall-focused threshold korunuyor: %.2f", final_threshold)
    else:
        log.info("   ✓ Threshold ve cost optimizasyonu uyumlu")

    # ═══════════════════════════════════════════════════════════════════
    # FİNAL TEST SET DEĞERLENDİRMESİ
    # ═══════════════════════════════════════════════════════════════════
    log.info("\n" + "═"*60)
    log.info("🏆 FİNAL TEST SET PERFORMANSI")
    log.info("═"*60)
    
    # Final model (tam train set ile eğit)
    rf_final = RandomForestClassifier(
        n_estimators=300, max_depth=14, min_samples_leaf=2,
        class_weight=cw_dict, n_jobs=-1, random_state=42)
    rf_final.fit(X_train, y_train)
    
    # Test set üzerinde prediction
    y_pred_test = (rf_final.predict_proba(X_test)[:,1] > final_threshold).astype(int)
    
    test_f1 = f1_score(y_test, y_pred_test)
    test_precision = np.sum((y_pred_test == 1) & (y_test == 1)) / max(np.sum(y_pred_test == 1), 1)
    test_recall = np.sum((y_pred_test == 1) & (y_test == 1)) / max(np.sum(y_test == 1), 1)
    
    try:
        y_proba_test = rf_final.predict_proba(X_test)[:,1]
        test_auc = roc_auc_score(y_test, y_proba_test)
    except:
        test_auc = 0.0
    
    tn, fp, fn, tp = confusion_matrix(y_test, y_pred_test).ravel()
    test_cost = fp * FALSE_POSITIVE_COST + fn * FALSE_NEGATIVE_COST
    
    log.info("\n   Test Set Metrikleri:")
    log.info("   • Precision: %.4f", test_precision)
    log.info("   • Recall:    %.4f", test_recall)
    log.info("   • F1 Score:  %.4f", test_f1)
    log.info("   • AUC:       %.4f", test_auc)
    
    log.info("\n   Confusion Matrix:")
    log.info("                Tahmin NORMAL  Tahmin FAULT")
    log.info("   Gerçek NORMAL      %6d        %6d", tn, fp)
    log.info("   Gerçek FAULT       %6d        %6d", fn, tp)
    
    log.info("\n   Production Maliyet Tahmini:")
    log.info("   • False Positive: %d × $%s = $%s", fp, f"{FALSE_POSITIVE_COST:,}", f"${fp * FALSE_POSITIVE_COST:,}")
    log.info("   • False Negative: %d × $%s = $%s", fn, f"{FALSE_NEGATIVE_COST:,}", f"${fn * FALSE_NEGATIVE_COST:,}")
    log.info("   • TOPLAM MALİYET: $%s", f"{test_cost:,}")
    
    log.info("\n   Model Kalitesi:")
    log.info("   • CV F1: %.4f ± %.4f (%s)", mean_f1, std_f1, stability_status)
    log.info("   • Test F1: %.4f (unbiased)", test_f1)
    
    if abs(test_f1 - mean_f1) < 0.05:
        log.info("   ✅ Model GENERALIZATION başarılı (CV ve Test uyumlu)")
    else:
        log.info("   ⚠️  Model overfitting olabilir (CV ve Test farklı)")

    results = {}
    
    # Random Forest sonuçlarını kaydet
    _eval_with_threshold("RandomForest", rf_final, X_test, y_test, feature_cols, 
                        results, threshold=final_threshold)
    
    log.info("\n   En önemli 15 özellik:")
    importances = rf_final.feature_importances_
    sorted_idx = np.argsort(importances)[::-1][:15]
    for idx in sorted_idx:
        log.info("     %-50s %.4f", feature_cols[idx], importances[idx])

    # ── XGBoost ve LightGBM (opsiyonel) ───────────────────────────────────
    if XGBOOST_OK:
        log.info("\n   ⚡ XGBoost eğitiliyor...")
        xgb_m = xgb.XGBClassifier(
            n_estimators=500, max_depth=6, learning_rate=0.04,
            subsample=0.8, colsample_bytree=0.8,
            scale_pos_weight=scale_pw,
            eval_metric="logloss", early_stopping_rounds=30,
            random_state=42, verbosity=0)
        xgb_m.fit(X_tr_final, y_tr_final, eval_set=[(X_val, y_val)], verbose=False)
        _eval_with_threshold("XGBoost", xgb_m, X_test, y_test, feature_cols, 
                            results, threshold=final_threshold)

    if LGBM_OK:
        log.info("\n   🚀 LightGBM eğitiliyor...")
        lgb_m = lgb.LGBMClassifier(
            n_estimators=500, max_depth=8, learning_rate=0.04,
            num_leaves=63, subsample=0.8, colsample_bytree=0.8,
            class_weight=cw_dict, random_state=42)
        lgb_m.fit(X_tr_final, y_tr_final)
        _eval_with_threshold("LightGBM", lgb_m, X_test, y_test, feature_cols, 
                            results, threshold=final_threshold)

    # ═══════════════════════════════════════════════════════════════════
    # EN İYİ MODELİ SEÇ VE KAYDET
    # ═══════════════════════════════════════════════════════════════════
    log.info("\n" + "═"*60)
    best_name = max(results, key=lambda k: results[k]['f1'])
    best = results[best_name]
    
    log.info("\n  ╔══════════════════════════════════════╗")
    log.info("  ║  🏆 EN İYİ MODEL : %-14s ║", best_name)
    log.info("  ║     F1  Skoru    : %.4f             ║", best['f1'])
    log.info("  ║     AUC          : %.4f             ║", best['auc'])
    log.info("  ║     Threshold    : %.2f               ║", final_threshold)
    log.info("  ║     CV F1        : %.4f ± %.4f       ║", mean_f1, std_f1)
    log.info("  ╚══════════════════════════════════════╝")
    
    log.info("\n   Model Karşılaştırması:")
    for name, res in sorted(results.items(), key=lambda x: x[1]['f1'], reverse=True):
        marker = " ← SEÇİLDİ" if name == best_name else ""
        log.info("     %-15s F1=%.4f  AUC=%.4f%s", name, res['f1'], res['auc'], marker)
    
    log.info("\n   Sınıflandırma Raporu (%s):", best_name)
    log.info("%s", classification_report(y_test, best['preds'], 
                                        target_names=["NORMAL", "ANOMALİ"]))
    
    # Kaydetme işlemleri
    os.makedirs(MODEL_DIR, exist_ok=True)
    
    with open(os.path.join(MODEL_DIR, "model.pkl"), "wb") as f:
        pickle.dump(best['model'], f)
    log.info("✅ model.pkl        → %s/model.pkl", MODEL_DIR)
    
    with open(os.path.join(MODEL_DIR, "feature_names.json"), "w") as f:
        json.dump(feature_cols, f, indent=2)
    log.info("✅ feature_names    → %s/feature_names.json", MODEL_DIR)
    
    # Model report (production-ready metrikler)
    report = {
        "training_date": datetime.now().isoformat(),
        "best_model": best_name,
        "metrics": {
            "f1": best['f1'],
            "auc": best['auc'],
            "precision": best['precision'],
            "recall": best['recall']
        },
        "threshold": final_threshold,
        "cross_validation": {
            "cv_f1_mean": mean_f1,
            "cv_f1_std": std_f1,
            "cv_auc_mean": mean_auc,
            "cv_auc_std": std_auc,
            "stability_status": stability_status
        },
        "cost_analysis": {
            "false_positive_cost": FALSE_POSITIVE_COST,
            "false_negative_cost": FALSE_NEGATIVE_COST,
            "total_cost_test": int(test_cost),
            "optimal_threshold_cost": int(optimal_threshold_cost)
        },
        "data_split": {
            "train_size": len(X_train),
            "test_size": len(X_test),
            "train_date_range": [
                train_df['window_start'].min().isoformat(),
                train_df['window_start'].max().isoformat()
            ],
            "test_date_range": [
                test_df['window_start'].min().isoformat(),
                test_df['window_start'].max().isoformat()
            ]
        }
    }
    
    with open(os.path.join(MODEL_DIR, "model_report.json"), "w") as f:
        json.dump(report, f, indent=2)
    log.info("✅ model_report     → %s/model_report.json", MODEL_DIR)
    
    log.info("\n" + "═"*60)
    log.info("✅ EĞİTİM TAMAMLANDI  (%.0f sn)", time.time() - t0_global if 't0_global' in globals() else 0)
    log.info("   Model    : %s", best_name)
    log.info("   Test F1  : %.4f", best['f1'])
    log.info("   CV F1    : %.4f ± %.4f", mean_f1, std_f1)
    log.info("   Threshold: %.2f", final_threshold)
    log.info("   Dosya    : %s/model.pkl", MODEL_DIR)
    log.info("\n   Sonraki adım → python3 build_ml_predictor.py")
    log.info("═"*60 + "\n")

    # Production-ready result dict döndür
    return {
        "models": results,  # Tüm modeller
        "best_model_name": best_name,
        "feature_cols": feature_cols,
        "cv_stats": {
            "cv_f1_mean": float(mean_f1),
            "cv_f1_std": float(std_f1),
            "cv_auc_mean": float(mean_auc),
            "cv_auc_std": float(std_auc),
            "stability_status": stability_status
        },
        "cost_analysis": {
            "false_positive_cost": FALSE_POSITIVE_COST,
            "false_negative_cost": FALSE_NEGATIVE_COST,
            "total_cost_test": int(test_cost),
            "optimal_threshold_cost": int(optimal_threshold_cost)
        },
        "data_split": {
            "train_size": int(len(X_train)),
            "test_size": int(len(X_test)),
            "train_date_range": [
                train_df['window_start'].min().isoformat(),
                train_df['window_start'].max().isoformat()
            ],
            "test_date_range": [
                test_df['window_start'].min().isoformat(),
                test_df['window_start'].max().isoformat()
            ]
        }
    }


def _eval(name: str, model, X_te, y_te, feature_cols: list, results: dict):
    """Modeli değerlendir, results dict'e ekle."""
    preds = model.predict(X_te)
    proba = model.predict_proba(X_te)[:, 1]
    f1  = f1_score(y_te, preds, zero_division=0)
    auc = roc_auc_score(y_te, proba) if len(np.unique(y_te)) > 1 else 0.5
    log.info("     → F1=%.4f | AUC=%.4f", f1, auc)
    results[name] = {"model": model, "f1": f1, "auc": auc,
                     "preds": preds, "proba": proba}


def _eval_with_threshold(name: str, model, X_te, y_te, feature_cols: list, 
                         results: dict, threshold: float = 0.5):
    """Modeli threshold ile değerlendir, results dict'e ekle."""
    proba = model.predict_proba(X_te)[:, 1]
    preds = (proba > threshold).astype(int)
    
    f1 = f1_score(y_te, preds, zero_division=0)
    precision = np.sum((preds == 1) & (y_te == 1)) / max(np.sum(preds == 1), 1)
    recall = np.sum((preds == 1) & (y_te == 1)) / max(np.sum(y_te == 1), 1)
    auc = roc_auc_score(y_te, proba) if len(np.unique(y_te)) > 1 else 0.5
    
    log.info("     → F1=%.4f | AUC=%.4f | P=%.3f | R=%.3f", f1, auc, precision, recall)
    
    results[name] = {
        "model": model, 
        "f1": f1, 
        "auc": auc,
        "precision": precision,
        "recall": recall,
        "preds": preds, 
        "proba": proba,
        "threshold": threshold
    }


def _train_isolation_forest(X, y, feature_cols: list) -> dict:
    contamination = min(y.mean() + 0.02, 0.45)
    log.info("   Isolation Forest | contamination=%.3f", contamination)
    iso = IsolationForest(n_estimators=300, contamination=contamination,
                          random_state=42, n_jobs=-1)
    iso.fit(X)
    preds = (iso.predict(X) == -1).astype(int)
    scores = -iso.score_samples(X)
    f1  = f1_score(y, preds, zero_division=0)
    auc = roc_auc_score(y, scores) if len(np.unique(y)) > 1 else 0.5
    log.info("   Isolation Forest → F1=%.4f | AUC=%.4f", f1, auc)
    return {"model": iso, "model_name": "IsolationForest",
            "feature_cols": feature_cols, "f1": f1, "auc": auc,
            "y_test": y, "y_pred": preds,
            "all_results": {"IsolationForest": {"f1": f1, "auc": auc}}}

# ═══════════════════════════════════════════════════════════════════════════
# ADIM 5 — Kaydet
# ═══════════════════════════════════════════════════════════════════════════

def save_model(result: dict, feat_df: pd.DataFrame, out_dir: str = MODEL_DIR):
    """Yeni production-ready result formatını kaydet."""
    os.makedirs(out_dir, exist_ok=True)
    
    # En iyi modeli bul
    best_name = result.get("best_model_name")
    best_result = result.get("models", {}).get(best_name, {})
    
    if not best_result:
        # Fallback: ilk model
        best_name = list(result.keys())[0] if result else "RandomForest"
        best_result = result.get(best_name, result)
    
    model = best_result.get("model")
    if model is None:
        log.warning("⚠️  Model bulunamadı, kaydetme atlanıyor")
        return None, None
    
    # model.pkl
    model_path = os.path.join(out_dir, "model.pkl")
    with open(model_path, "wb") as f:
        pickle.dump(model, f)
    
    # feature_names.json
    feat_path = os.path.join(out_dir, "feature_names.json")
    feature_cols = result.get("feature_cols", [])
    meta = {
        "feature_names":    feature_cols if feature_cols else list(feat_df.columns[:33]),
        "n_features":       len(feature_cols) if feature_cols else 33,
        "sensors":          HPR_SENSORS,
        "pre_fault_mins":   PRE_FAULT_MINS,
        "time_window_min":  TIME_WINDOW_MIN,
        "model_name":       best_name,
        "generated_at":     datetime.now().isoformat(),
    }
    with open(feat_path, "w") as f:
        json.dump(meta, f, indent=2)
    
    # model_report.json - Production-ready format
    report_path = os.path.join(out_dir, "model_report.json")
    
    # Feature importance hesapla (en iyi modelden)
    feature_importance = []
    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
        sorted_idx = np.argsort(importances)[::-1][:20]  # Top 20
        feature_importance = [
            {"feature": feature_cols[i], "importance": float(importances[i])}
            for i in sorted_idx
        ]
    
    report = {
        "training_date": datetime.now().isoformat(),
        "best_model": best_name,
        "metrics": {
            "f1": float(best_result.get("f1", 0)),
            "auc": float(best_result.get("auc", 0)),
            "precision": float(best_result.get("precision", 0)),
            "recall": float(best_result.get("recall", 0))
        },
        "threshold": float(best_result.get("threshold", 0.5)),
        "cross_validation": result.get("cv_stats", {}),
        "cost_analysis": result.get("cost_analysis", {}),
        "data_split": result.get("data_split", {}),
        "feature_importance": feature_importance,
        "training_rows": int(len(feat_df)),
        "anomaly_rows": int(feat_df["binary_label"].sum()) if "binary_label" in feat_df else 0
    }
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    
    log.info("\n✅ KAYDEDİLEN DOSYALAR:")
    log.info("   • %s/model.pkl", out_dir)
    log.info("   • %s/feature_names.json", out_dir)
    log.info("   • %s/model_report.json", out_dir)
    
    return model_path, report_path

    # ml_training_data.csv (incelemek için)
    csv_path = "ml_training_data.csv"
    feat_df.to_csv(csv_path, index=False)

    log.info("✅ model.pkl        → %s", model_path)
    log.info("✅ feature_names    → %s", feat_path)
    log.info("✅ model_report     → %s", report_path)
    log.info("✅ ml_training_data → %s", csv_path)
    return model_path, feat_path

# ═══════════════════════════════════════════════════════════════════════════
# ANA AKIŞ
# ═══════════════════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    print(f"\n{'═'*60}")
    print(f"  HPR ML Model Eğitimi  —  {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"  Modeller: Random Forest"
          + (" + XGBoost" if XGBOOST_OK else "")
          + (" + LightGBM" if LGBM_OK else ""))
    print(f"{'═'*60}\n")

    if not os.path.exists(VIOLATION_LOG):
        print(f"❌ {VIOLATION_LOG} bulunamadı!"); sys.exit(1)

    fault_df, normal_df, raw = load_faults(VIOLATION_LOG)

    # ── live_windows.json varsa birleştir (window_collector çıktısı) ──
    if os.path.exists(LIVE_WINDOWS):
        try:
            with open(LIVE_WINDOWS, "r", encoding="utf-8") as f:
                lw = json.load(f)
            live_normal  = sum(len(v) for v in lw.get("normal_windows", {}).values())
            live_fault   = sum(len(v) for v in lw.get("fault_windows",  {}).values())
            print(f"  ✅ live_windows.json: {live_normal} normal + {live_fault} fault penceresi")

            # normal_windows → normal_df'e ekle
            live_normal_records = []
            _lim_map = {
                "oil_tank_temperature":      45.0, "main_pressure": 110.0,
                "horizontal_press_pressure": 120.0, "lower_ejector_pressure": 110.0,
                "horitzonal_infeed_speed":   300.0, "vertical_infeed_speed": 300.0,
            }
            for mid, wins in lw.get("normal_windows", {}).items():
                for win in wins:
                    ts = _parse_ts(win.get("ts", ""))
                    if ts is None: continue
                    for sensor, val in win.get("readings", {}).items():
                        if sensor not in HPR_SENSORS: continue
                        live_normal_records.append({
                            "machine_id": mid, "sensor": sensor,
                            "timestamp": ts, "value": float(val),
                            "limit_max": _lim_map.get(sensor, 9999.0),
                            "limit_min": 0.0, "total_sensor_faults": 0,
                        })

            # fault_windows → fault_df'e ekle
            live_fault_records = []
            for mid, wins in lw.get("fault_windows", {}).items():
                for win in wins:
                    ts = _parse_ts(win.get("ts", ""))
                    if ts is None: continue
                    fault_set = set(win.get("faults", []))
                    for sensor, val in win.get("readings", {}).items():
                        if sensor not in fault_set: continue  # sadece aşan sensörler
                        live_fault_records.append({
                            "machine_id": mid, "sensor": sensor,
                            "timestamp": ts, "value": float(val),
                            "limit_max": _lim_map.get(sensor, 9999.0),
                            "limit_min": 0.0, "total_sensor_faults": 1,
                        })

            if live_normal_records:
                lndf = pd.DataFrame(live_normal_records)
                if lndf["timestamp"].dt.tz is None:
                    lndf["timestamp"] = lndf["timestamp"].dt.tz_localize("UTC")
                normal_df = pd.concat([normal_df, lndf], ignore_index=True) if not normal_df.empty else lndf
                log.info("   live normal eklendi: %d kayıt", len(live_normal_records))

            if live_fault_records:
                lfdf = pd.DataFrame(live_fault_records)
                if lfdf["timestamp"].dt.tz is None:
                    lfdf["timestamp"] = lfdf["timestamp"].dt.tz_localize("UTC")
                fault_df = pd.concat([fault_df, lfdf], ignore_index=True)
                log.info("   live fault eklendi: %d kayıt", len(live_fault_records))

        except Exception as e:
            print(f"  ⚠️  live_windows.json okunamadı: {e}")
    else:
        print(f"  ℹ️  live_windows.json henüz yok — hpr_monitor.py çalışınca oluşacak")

    if normal_df.empty:
        print("\n  ⚠️  UYARI: Hiç normal pencere yok!")
        print("     hpr_monitor.py'yi çalıştırın (24 saat → ilk veri birikir).\n")
    else:
        print(f"  ✅ Toplam {len(normal_df):,} normal sensör kaydı (gerçek NORMAL profil)\n")

    feat_df       = engineer_features(fault_df, normal_df)
    feat_df       = label_windows(feat_df, fault_df)
    result        = train_and_evaluate(feat_df)
    model_path, report_path = save_model(result, feat_df)
    
    # Best model bilgilerini al
    best_name = result.get("best_model_name", "RandomForest")
    best_result = result.get("models", {}).get(best_name, {})
    best_f1 = best_result.get("f1", 0)
    best_auc = best_result.get("auc", 0)

    elapsed = time.time() - t0
    print(f"\n{'═'*60}")
    print(f"  ✅ EĞİTİM TAMAMLANDI  ({elapsed:.0f} sn)")
    print(f"     Model    : {best_name}")
    print(f"     F1 Skoru : {best_f1:.4f}")
    print(f"     AUC      : {best_auc:.4f}")
    print(f"     Dosya    : {model_path}")
    has_nw = not normal_df.empty
    print(f"     Normal pencere kaynağı: {'✅ var' if has_nw else '⚠️  YOK (yeni scan önerilir)'}")
    print(f"\n  Sonraki adım → python3 build_ml_predictor.py")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    main()
