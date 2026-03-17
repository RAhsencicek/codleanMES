import os
import joblib
import pandas as pd
import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from collections import defaultdict

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | DLIME | %(message)s")
log = logging.getLogger(__name__)

class DLIMEExplainer:
    """
    Deterministik LIME (DLIME) Uygulaması.
    TreeSHAP'ın hata vermesi veya karar ağacı olmayan bir modele geçilmesi durumunda,
    kara kutu makine öğrenimi modellerini açıklamak için KÜMELEME tabanlı (AHC) ve deterministik
    bir 'Local Linear Model' (Ridge Regression) fallback mekanizması sağlar.

    Çalışma Mantığı:
    1. Eğitim verisini (X_train) Agglomerative Clustering ile K kümeye böler.
    2. Yeni bir X_test geldiğinde, ona en yakın kümeyi bulur.
    3. O kümedeki "komşu" veriler üzerinde kara kutu modelin tahminlerini (y) hesaplar.
    4. Bu komşu veriler ve tahminleri üzerinden şeffaf, açıklanabilir bir LOKAL regülasyon modeli
       (Ridge) eğitir ve sonucu döndürür. Normal LIME gibi rastgele (random) veri türetmez.
    """
    def __init__(self, model_pipeline, training_data_path: str, n_clusters: int = 5):
        self.model_pipeline = model_pipeline
        self.training_data_path = training_data_path
        self.n_clusters = n_clusters
        
        self.feature_names = None
        self.scaler = StandardScaler()
        self.clustering_model = AgglomerativeClustering(n_clusters=self.n_clusters)
        self.local_models = {}  # {cluster_id: RidgeModel}
        
        # Küme merkezleri (yeni gelen verinin hangi kümeye ait olduğunu bulmak için)
        self.cluster_centers = {} 
        self.clusters_X = defaultdict(list)
        self.clusters_y = defaultdict(list)

        self._fit()

    def _fit(self):
        """Eğitim verisini okur, kümelere ayırır ve lokal modelleri oluşturur."""
        if not os.path.exists(self.training_data_path):
            log.warning(f"DLIME Training data bulunamadı: {self.training_data_path}. DLIME çalışmayacak.")
            return

        log.info("DLIME Fallback sistemi hazırlanıyor (AHC Clustering)...")
        df = pd.read_csv(self.training_data_path)
        
        # Meta verileri (machine_id vb) atıp sadece özellikleri al
        drop_cols = ["machine_id", "window_start", "_source", "label", "binary_label"]
        features_df = df.drop(columns=[c for c in drop_cols if c in df.columns], errors='ignore')
        self.feature_names = features_df.columns.tolist()

        # Standartlaştırma (Kümeleme için şarttır)
        X_scaled = self.scaler.fit_transform(features_df)
        
        # 1. Kümeleri Oluştur (Agglomerative Hierarchical Clustering)
        cluster_labels = self.clustering_model.fit_predict(X_scaled)
        
        # 2. Her Küme için Kara Kutu modelinin tahminlerini al
        #    Pipeline doğrudan df bekleyebilir, o yüzden orjinal özellikleri kullanırız
        black_box_y = self.model_pipeline.predict_proba(features_df)[:, 1]

        # Verileri kümelere ayır
        for i, label in enumerate(cluster_labels):
            self.clusters_X[label].append(X_scaled[i])
            self.clusters_y[label].append(black_box_y[i])

        # 3. Merkezleri hesapla ve Lokal modelleri (Ridge) eğit
        for cluster_id in range(self.n_clusters):
            X_c = np.array(self.clusters_X[cluster_id])
            y_c = np.array(self.clusters_y[cluster_id])
            
            # Merkeze ihtiyacımız var ki çalışma anında (inference) yeni datayı eşleştirelim
            self.cluster_centers[cluster_id] = X_c.mean(axis=0)

            # Lokal Lineer (Açıklanabilir) Model - Ridge Regression
            ridge = Ridge(alpha=1.0)
            if len(np.unique(y_c)) > 1: # Eğer o kümedeki her tahmin aynıysa regresyon fit etmez
                ridge.fit(X_c, y_c)
            self.local_models[cluster_id] = ridge

        log.info(f"✅ DLIME: {self.n_clusters} küme ve Lokal Ridge modelleri başarıyla oluşturuldu.")

    def explain(self, current_instance: pd.DataFrame) -> dict:
        """
        Canlı uyarı anında (fail-over durumunda) modelin neden riskli gördüğünü
        deterministik (DLIME) yollarla açıklar.
        """
        if not self.local_models:
            return {"error": "DLIME is not trained."}

        # Sadece özellikleri al
        X_inst = current_instance[self.feature_names].copy()
        X_inst_scaled = self.scaler.transform(X_inst)[0]

        # 1. Tüm kümeleri uzaklığa göre sırala (Oklüd uzaklığı)
        distances = {
            c_id: np.linalg.norm(X_inst_scaled - center)
            for c_id, center in self.cluster_centers.items()
        }
        # En yakından en uzağa küme listesi
        sorted_clusters = sorted(distances.keys(), key=lambda c: distances[c])

        # 2. İlk çalışan (degenerate olmayan) kümeyi bul
        for closest_cluster in sorted_clusters:
            local_model = self.local_models[closest_cluster]

            # Ridge fitlenmemiş (tek düze küme) → sonrakine geç
            if not hasattr(local_model, 'coef_'):
                continue

            # 3. Katsayıları (Coefficients) ve Çarpımları hesapla
            # LIME mantığı: Etki = Özellik Değeri * Lokal Model Katsayısı
            effects = local_model.coef_ * X_inst_scaled

            # SHAP ile aynı formatta sözlük döndür (NLG motoruna bağlanabilsin diye)
            explanation_dict = {}
            for idx, feat_name in enumerate(self.feature_names):
                if abs(effects[idx]) > 0.001:  # Çok çok küçük etkileri yoksay
                    explanation_dict[feat_name] = float(effects[idx])

            if not explanation_dict:
                continue  # Bu küme boş sonuç verdi, sonrakine geç

            # Büyükten küçüğe (mutlak değerce) sırala
            sorted_exp = dict(sorted(explanation_dict.items(), key=lambda item: abs(item[1]), reverse=True))
            return sorted_exp

        return {"error": "All clusters degenerate or empty — no valid explanation found."}
