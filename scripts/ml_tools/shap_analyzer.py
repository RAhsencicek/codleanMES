import shap
import joblib
import json
import pandas as pd
import os
import matplotlib.pyplot as plt
import numpy as np

def analyze_model_with_shap():
    print("="*50)
    print("🔍 SHAP ANALİZİ BAŞLATILIYOR")
    print("="*50)
    
    model_path = 'pipeline/model/model.pkl'
    feature_names_path = 'pipeline/model/feature_names.json'
    training_data_path = 'data/ml_training_data.csv'

    print("\n📦 Artefaktlar yükleniyor...")
    
    # 1. Load Model
    if not os.path.exists(model_path):
        print(f"❌ Model bulunamadı: {model_path}")
        return
    model = joblib.load(model_path)
    print("✅ Model yüklendi.")

    # 2. Load Feature Names
    if not os.path.exists(feature_names_path):
        print(f"❌ Özellik adları bulunamadı: {feature_names_path}")
        return
    with open(feature_names_path, 'r') as f:
        feature_data = json.load(f)
        
    # JSON yapısına göre düzeltme (liste mi dict mi kontrolü)
    if isinstance(feature_data, dict) and 'feature_names' in feature_data:
        feature_names = feature_data['feature_names']
    else:
        feature_names = feature_data
        
    print(f"✅ Özellik adları yüklendi ({len(feature_names)} özellik).")

    # 3. Load Training Data
    if not os.path.exists(training_data_path):
        print(f"❌ Eğitim verisi bulunamadı: {training_data_path}")
        return
    
    df = pd.read_csv(training_data_path)
    
    # Pre-processing to match the training pipeline format
    # The training pipeline drops label, machine_id, window_start, timestamp
    drop_cols = ['label', 'machine_id', 'window_start', 'timestamp']
    cols_to_drop = [c for c in drop_cols if c in df.columns]
    X = df.drop(cols_to_drop, axis=1)
    
    # Ensure columns match training feature names exactly
    # We might need to filter or reorder columns to match feature_names
    missing_cols = [c for c in feature_names if c not in X.columns]
    if missing_cols:
        print(f"⚠️ Eğitim verisinde eksik özellikler var: {missing_cols}")
        print("Modelin gerektirdiği özellik seti veri setiyle tam eşleşmiyor olabilir.")
    
    # Take a sample for SHAP background (1000 samples for speed)
    print(f"\n📊 Veri seti boyutu: {X.shape}. SHAP için 1000 örnek seçiliyor...")
    X_sample = X.sample(n=min(1000, len(X)), random_state=42)
    
    # Align columns
    try:
         X_sample = X_sample[feature_names]
    except KeyError as e:
         print(f"❌ Özellik hizalama hatası: {e}. SHAP hesaplanamıyor.")
         return

    print("\n🧠 TreeSHAP Explainer oluşturuluyor (Bu işlem biraz sürebilir)...")
    try:
        # Create TreeExplainer. TreeExplainer is optimized for tree-based models like RF/XGBoost
        explainer = shap.TreeExplainer(model)
        
        # Calculate SHAP values for the sample
        shap_values = explainer.shap_values(X_sample)
        print("✅ SHAP değerleri hesaplandı.")
        
        # Determine the shape of shap_values
        # For Random Forest classification (binary), shap_values is often a list of arrays [negative_class, positive_class]
        # For XGBoost, it might just be the positive class.
        
        if isinstance(shap_values, list):
            print("Çoklu sınıf (liste format). Sınıf 1 (Fault) incelenecek.")
            sv_to_use = shap_values[1]
        elif len(shap_values.shape) == 3:
            print("Çoklu sınıf (3D array). Sınıf 1 (Fault) incelenecek.")
            sv_to_use = shap_values[:, :, 1]
        else:
             sv_to_use = shap_values
             
        # Geri dönüş değerlerinin numpy array olup olmadığını kontrol edelim
        if hasattr(sv_to_use, 'values'):
            sv_to_use = sv_to_use.values
            
        # Mean absolute SHAP values for global importance
        # Calculate global importance
        mean_abs_shap = np.abs(sv_to_use).mean(axis=0)
        
        # Mean absolute shap shape mismatch check
        if len(mean_abs_shap) != len(feature_names):
            print(f"❌ UYUMSUZLUK: mean_abs_shap boyutu ({len(mean_abs_shap)}) ile özellik sayısı ({len(feature_names)}) uyuşmuyor.")
            return

        feature_importance = pd.DataFrame({
            'feature': feature_names,
            'mean_abs_shap': mean_abs_shap
        }).sort_values('mean_abs_shap', ascending=False)
        
        print("\n🏆 GLOBAL ÖNEM (Mean |SHAP|):")
        print("-" * 40)
        for idx, row in feature_importance.head(10).iterrows():
            print(f"{row['feature'][:30]:<30} | {row['mean_abs_shap']:.4f}")
            
        # Check for potential overfitting or leakages
        print("\n🔬 SAÇMALIK KONTROLÜ (Overfitting / Leakage Analizi):")
        print("-" * 40)
        top_feature = feature_importance.iloc[0]['feature']
        top_shap = feature_importance.iloc[0]['mean_abs_shap']
        second_shap = feature_importance.iloc[1]['mean_abs_shap']
        
        if top_feature.startswith('machine_id') or top_feature.startswith('timestamp') or top_feature.startswith('window'):
            print(f"🚨 KRİTİK UYARI: Model makine ID'sine veya zamana ({top_feature}) odaklanmış!")
            print("Bu bir ezberleme (overfitting) göstergesidir. Model fiziksel durumdan çok zamanı öğrenmiş.")
            
        elif top_shap > second_shap * 3:
             print(f"⚠️ UYARI: '{top_feature}' aşırı dominant. Model neredeyse sadece bu değere bakıyor.")
        else:
             print(f"✅ Görünürde bariz bir zaman/makine ezberlemesi yok. Ana sürücü: {top_feature}")
            
        # Generate Summary Plot
        out_dir = 'pipeline/model/xai_reports'
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, 'shap_summary_plot.png')
        
        plt.figure(figsize=(12, 8))
        shap.summary_plot(sv_to_use, X_sample, plot_type="bar", show=False)
        plt.title("SHAP Feature Importance (Bar Plot)")
        plt.tight_layout()
        plt.savefig(out_file)
        plt.close()
        print(f"\n📈 SHAP Grafiği kaydedildi: {out_file}")
        
    except Exception as e:
        print(f"❌ SHAP analizi sırasında hata: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    analyze_model_with_shap()
