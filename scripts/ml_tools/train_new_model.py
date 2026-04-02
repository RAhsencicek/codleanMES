#!/usr/bin/env python3
import pandas as pd
import numpy as np
import pickle
import os
import json
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, f1_score, roc_auc_score, confusion_matrix
from sklearn.model_selection import train_test_split, TimeSeriesSplit

CSV_PATH = "data/ml_training_data_v2.csv"
MODEL_DIR = "pipeline/model"

def main():
    print("=" * 60)
    print("🧠 FAZ E - ML MODEL TRAINING (Sızdırmaz Dataset)")
    print("=" * 60)
    
    if not os.path.exists(CSV_PATH):
        print(f"❌ {CSV_PATH} bulunamadı!")
        return

    df = pd.read_csv(CSV_PATH)
    print(f"📂 Veri seti yüklendi: {df.shape[0]} satır, {df.shape[1]} özellik.")
    
    # Zaman sırasına göre diz (TimeSeries için önemli)
    df = df.sort_values(by="timestamp").reset_index(drop=True)
    
    # Drop metadata columns
    meta_cols = ["machine_id", "timestamp", "label", "binary_label"]
    feature_cols = [c for c in df.columns if c not in meta_cols]
    
    # NaN temizliği
    df.fillna(0, inplace=True)
    
    X = df[feature_cols].values
    y = df["binary_label"].values
    
    n_pos = np.sum(y)
    n_neg = len(y) - n_pos
    print(f"📊 Etiketler - NORMAL (0): {n_neg}, FAULT/PRE-FAULT (1): {n_pos}")
    
    if n_pos < 10:
        print("❌ Eğitim için yeterli arıza örneği yok!")
        return

    # Zaman bazlı Split (%80 eğitim, %20 test)
    split_idx = int(len(df) * 0.8)
    X_train, y_train = X[:split_idx], y[:split_idx]
    X_test,  y_test  = X[split_idx:], y[split_idx:]
    
    print("\n🌲 Random Forest Modeli Eğitiliyor (Sızdırmaz - Zaman Serisi uyumlu)...")
    
    # Dengeli sınıf ağırlığı (Imbalanced veri olduğu için normali baskılar)
    # class_weight="balanced" kullanıyoruz
    rf = RandomForestClassifier(
        n_estimators=300,
        max_depth=12,
        min_samples_split=4,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1
    )
    
    rf.fit(X_train, y_train)
    
    # Değerlendirme
    print("\n" + "=" * 60)
    print("🏆 TEST PERFORMANSI (Gelecek Verisi)")
    print("=" * 60)
    
    y_pred = rf.predict(X_test)
    y_proba = rf.predict_proba(X_test)[:, 1]
    
    print(classification_report(y_test, y_pred, target_names=["NORMAL", "FAULT"]))
    
    auc = roc_auc_score(y_test, y_proba)
    print(f"🔥 ROC AUC Skoru: {auc:.4f}")
    
    cm = confusion_matrix(y_test, y_pred)
    print("Confusion Matrix:")
    print(cm)
    
    print("\n🔑 En Önemli 10 Özellik:")
    importances = rf.feature_importances_
    sorted_idx = np.argsort(importances)[::-1][:10]
    for idx in sorted_idx:
        print(f"  - {feature_cols[idx]:<45} : {importances[idx]:.4f}")
        
    print("\n💾 Model Kaydediliyor...")
    os.makedirs(MODEL_DIR, exist_ok=True)
    
    with open(os.path.join(MODEL_DIR, "model.pkl"), "wb") as f:
        pickle.dump(rf, f)
        
    with open(os.path.join(MODEL_DIR, "feature_names.json"), "w") as f:
        json.dump(feature_cols, f, indent=2)
        
    print(f"✅ Başarılı! Model ve sensör isimleri '{MODEL_DIR}' dizinine yazıldı.")
    print("  (Pipeline içerisinde otomatik kullanılacaktır.)")

if __name__ == '__main__':
    main()
