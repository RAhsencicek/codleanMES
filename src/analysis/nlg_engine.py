import os

class CodleanNLGEngine:
    """
    AI Usta Başı (Context Engine) - Doğal Dil Üretme Modülü (NLG)
    SHAP değerlerini ve risk skorlarını alıp, teknisyenin anlayabileceği
    aksiyona dönüştürülebilir Türkçe metinler (Natural Language) üretir.
    """
    def __init__(self):
        # Sensör ve özellik isimleri için sözlük (İngilizce -> Türkçe)
        self.feature_translations = {
            "total_faults_window": "Penceredeki Toplam Hata Veren Sensör Sayısı",
            "active_sensors": "Aynı Anda Aktif Olan Sensör Sayısı",
            "main_pressure__over_ratio": "Ana Basınç (% Aşım Oranı)",
            "main_pressure__value_max": "Ana Basınç (Maksimum Değer)",
            "main_pressure__value_mean": "Ana Basınç (Ortalama Değer)",
            "horizontal_press_pressure__val": "Yatay Pres Basıncı",
            "horizontal_press_pressure__value_max": "Yatay Pres Basıncı (Maksimum)",
            "horizontal_press_pressure__over_ratio": "Yatay Pres Basıncı (% Aşım)",
            "oil_tank_temperature__value_max": "Yağ Tankı Sıcaklığı (Maksimum)",
            "oil_tank_temperature__over_ratio": "Yağ Tankı Sıcaklığı (% Aşım)",
            "main_pressure__fault_count": "Ana Basınç Arıza Sıklığı",
            "vertical_infeed_speed__value_max": "Dikey Besleme Hızı (Maksimum)",
            "horitzonal_infeed_speed__value_max": "Yatay Besleme Hızı (Maksimum)"
        }
    
    def _translate_feature(self, feature_name):
        """İngilizce özellik isimlerini okunabilir Türkçe karşılıklarına çevirir."""
        if feature_name in self.feature_translations:
            return self.feature_translations[feature_name]
        
        # Bilinmeyen özellikler için alt tireleri boşluğa çevir ve baş harfleri büyüt
        return feature_name.replace("__", " ").replace("_", " ").title()
        
    def generate_explanation(self, risk_score: float, shap_impacts: dict, machine_id: str = "Bilinmeyen Makine"):
        """
        Risk skoru ve SHAP katkılarına (impacts) dayanarak açıklama üretir.
        
        Args:
            risk_score (float): 0.0 - 1.0 arası risk tahmini
            shap_impacts (dict): Örn. {"main_pressure__value_max": 0.015, ...}
            machine_id (str): Makine numarası (Örn: HPR001)
        """
        # SHAP değerlerine göre en çok etki eden (mutlak değerce en büyük) 3 özelliği bul
        top_features = sorted(
            shap_impacts.items(),
            key=lambda x: abs(x[1]),
            reverse=True
        )[:3]
        
        explanation_parts = []
        
        # 1. Başlık ve Risk Seviyesi (Actionable Alert)
        if risk_score > 0.85:
            risk_text = f"🚨 KRİTİK RİSK DURUMU ({machine_id} - Risk: %{risk_score*100:.1f})"
            action = "HEMEN MÜDAHALE EDİN: Makineyi rölantiye alın veya durdurun. Fiziksel bir arıza başlamak üzere."
            eta = "30-45 dakika"
        elif risk_score > 0.70:
            risk_text = f"⚠️ YÜKSEK RİSK ({machine_id} - Risk: %{risk_score*100:.1f})"
            action = "Makineyi yakından izleyin, ilk fırsatta soğutma/basınç kontrolü planlayın."
            eta = "1-2 saat"
        elif risk_score > 0.50:
            risk_text = f"⚡ ORTA RİSK ({machine_id} - Risk: %{risk_score*100:.1f})"
            action = "Dikkat: Sensör değerlerinde istikrarsızlık var. Gözlemlemeye devam edin."
            eta = "Belirsiz"
        else:
            risk_text = f"✅ DÜŞÜK RİSK ({machine_id} - Risk: %{risk_score*100:.1f})"
            action = "Cihaz normal operasyon sınırları içinde çalışıyor."
            eta = None

        explanation_parts.append(f"{risk_text}")
        
        # 2. XAI (SHAP) Kök Neden Açıklamaları
        if top_features and risk_score > 0.50:
            explanation_parts.append("\n🔍 AI Usta Başı Analizi (Neden Riskli?):")
            for feature_name, impact in top_features:
                # Çok düşük (noise) olan shap değerlerini gösterme
                if abs(impact) < 0.005:
                    continue 
                
                tr_name = self._translate_feature(feature_name)
                
                if impact > 0:
                    severity = "ciddi ölçüde" if impact > 0.02 else "hafifçe"
                    explanation_parts.append(f"  • {tr_name} arıza riskini {severity} ARTIRIYOR (+{impact:.3f} katkı).")
                else:
                    explanation_parts.append(f"  • {tr_name} arıza riskini DÜŞÜRÜYOR ({impact:.3f} katkı).")
                    
        # 3. Önerilen Aksiyon ve Gelecek Tahmini
        explanation_parts.append(f"\n💡 ÖNERİLEN AKSİYON: {action}")
        
        if eta:
            explanation_parts.append(f"⏱️ ETA: Eğer müdahale edilmezse {eta} içinde donanımsal arıza beklenmektedir.")
            
        return "\n".join(explanation_parts)

if __name__ == "__main__":
    # Test Modu
    engine = CodleanNLGEngine()
    
    test_shap = {
        "active_sensors": 0.0565,
        "main_pressure__over_ratio": 0.0119,
        "oil_tank_temperature__value_max": -0.002
    }
    
    print(engine.generate_explanation(risk_score=0.88, shap_impacts=test_shap, machine_id="HPR001"))
