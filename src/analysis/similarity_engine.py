"""
src/analysis/similarity_engine.py
═══════════════════════════════════════════════
Geçmiş olay hafızası (Contextual Memory).
ML için oluşturulan data/ml_training_data_v2.csv dosyasını okuyup,
Anlık makine durumunun geçmişteki olaylara (FAULT/PRE-FAULT) ne kadar
benzediğini hesaplar (Cosine Similarity).

Usta Başı'nın (Gemini) "Bu olay daha önce yaşanmış mı?"
sorusuna istatistiksel yanıt üretir.
"""

import os
import pandas as pd
import numpy as np
import logging
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import StandardScaler

log = logging.getLogger("similarity_engine")

class SimilarityEngine:
    _instance = None
    
    def __new__(cls, dataset_path="data/ml_training_data_v2.csv"):
        if cls._instance is None:
            cls._instance = super(SimilarityEngine, cls).__new__(cls)
            cls._instance._df = None
            cls._instance._feature_matrix = None
            cls._instance._scaler = None
            cls._instance._feature_cols = []
            cls._instance._load_data(dataset_path)
        return cls._instance

    def _load_data(self, dataset_path: str):
        if not os.path.exists(dataset_path):
            log.warning("⚠️ SimilarityEngine veri seti bulamadı: %s", dataset_path)
            return

        try:
            df = pd.read_csv(dataset_path)
            # Sadece anormal durumları (FAULT/PRE-FAULT) arayalım ki Gemini onlara benzeyip benzemediğini görsün.
            # Ancak Normal'leri de tutarsak tam spektrum görür.
            # En öğretici olan: "Bu durum, geçmişteki şu arızalara X derece benziyor" diyebilmek.
            # O yüzden tüm datayı yükleyip KNN/Cosine yapalım ama sonuçları filtreleyelim.
            
            meta_cols = ["machine_id", "timestamp", "label", "binary_label"]
            self._feature_cols = [c for c in df.columns if c not in meta_cols]
            
            df.fillna(0, inplace=True)
            X = df[self._feature_cols].values
            
            # Normalizasyon önemli çünkü farklı sensörlerin (sıcaklık vs basınç) skalaları farklı!
            self._scaler = StandardScaler()
            self._feature_matrix = self._scaler.fit_transform(X)
            self._df = df
            
            log.info("✅ SimilarityEngine hazır. %d satır, %d özellik geçmiş hafızaya alındı.", len(df), len(self._feature_cols))
            
        except Exception as e:
            log.error("SimilarityEngine yükleme hatası: %s", e)

    def find_similar_events(self, live_features: dict, current_machine_id: str, top_k: int = 3) -> str:
        """
        Canlı veriyi alır, ML model formatındaki dictionary'yi vektörleştirir,
        geçmiş hafıza tablosu ile kosinüs benzerliğini hesaplar ve insan okunabilir
        bir özet (örneğin Gemini'nin tüketmesi için) string olarak döndürür.
        """
        if self._df is None or self._feature_matrix is None:
            return "Geçmiş olay hafızası veritabanı aktif değil."

        try:
            # 1. Gelen sözlüğü eğitim sırasına diz
            vec = np.array([live_features.get(c, 0.0) for c in self._feature_cols], dtype=float).reshape(1, -1)
            
            # 2. Vektörü normalize et
            vec_scaled = self._scaler.transform(vec)
            
            # 3. Tüm hafızaya karşı Kosinüs Benzerliği (Cosine Similarity) matrisi çıkar
            # Sonuç shape: (1, N)
            similarities = cosine_similarity(vec_scaled, self._feature_matrix)[0]
            
            # 4. En çok benzeyen (skoru en yüksek olan) indeksleri bul
            # Kendisini bulmasını engellemek için %99 üstünü kesebiliriz ama test için bırakalım
            top_indices = np.argsort(similarities)[::-1][:top_k*3] # Ekstra alıp filtreleriz
            
            events = []
            seen_dates = set()
            
            for idx in top_indices:
                score = similarities[idx]
                if score < 0.60:  # %60'tan az benziyorsa önemseme
                    continue
                    
                row = self._df.iloc[idx]
                dt = str(row['timestamp'])[:10]  # Sadece YYYY-MM-DD
                
                # Aynı gün içindeki birbirine yapışık pencereleri tekrar tekrar söyleme
                if dt in seen_dates:
                    continue
                    
                seen_dates.add(dt)
                events.append({
                    'score': score * 100,
                    'machine': row['machine_id'],
                    'date': row['timestamp'],
                    'label': row['label']
                })
                
                if len(events) >= top_k:
                    break
                    
            if not events:
                return "Şu anki makine davranışı geçmişteki hiçbir kritik olaya (%60'tan fazla) benzemiyor (Güvenli/Benzersiz durum)."
                
            # 5. Gemini için Context Metni Oluştur
            lines = ["🕒 GEÇMİŞ OLAY HAFIZASI (Cosine Similarity Araması):"]
            lines.append("Şu anki makine sensör hareketleri, geçmişteki veri tabanıyla tarandığında şu tarihi olaylarla eşleşti:")
            
            for i, ev in enumerate(events):
                # Aynı makine mi?
                same_mac = "(Bu Makinenin Kendisi!)" if ev['machine'] == current_machine_id else ""
                
                label_tr = "Arıza OLUŞTU (FAULT)" if ev['label'] == 'FAULT' else "Arıza İhtimali (PRE-FAULT)" if ev['label'] == 'PRE-FAULT' else "Normal Çalışma"
                
                txt = f" {i+1}. %{ev['score']:.1f} Eşleşme - Tarih: {ev['date'][:16]} | Makine: {ev['machine']} {same_mac} | Olay Sonucu: {label_tr}"
                lines.append(txt)
                
            # Makinenin kendi geneline dair basit fault sayacı
            machine_faults = len(self._df[(self._df['machine_id'] == current_machine_id) & (self._df['label'] == 'FAULT')])
            if machine_faults > 20:
                lines.append(f"\n⚠️ NOT: Bu makine ({current_machine_id}) geçmişte çok sık ({machine_faults} kez) arıza vermiş, KRONİK sorunlu olabilir.")
            elif machine_faults == 0:
                lines.append(f"\n✅ NOT: Bu makine ({current_machine_id}) geçmiş kayıtlarında hiç arıza YAPMAMIŞ çok sağlam bir makinedir.")
                
            return "\n".join(lines)

        except Exception as e:
            log.exception("Similarity hesaplama hatası:")
            return f"Benzerlik araması teknik bir nedenden yapılamadı: {str(e)}"
