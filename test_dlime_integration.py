import os
import sys
import numpy as np

# Proje dizinini (hpr_monitor_fixed.py'nin bulunduğu ana dizini) yola ekle
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = current_dir  # Betiği ana dizinde varsayıyoruz
if root_dir not in sys.path:
    sys.path.append(root_dir)

from pipeline.ml_predictor import MLPredictor

def test_dlime_fallback():
    print("--- DLIME Fallback Testi Başlıyor ---")
    predictor = MLPredictor()
    
    if not predictor.is_active:
        print("ML Model yüklenemedi. 'python3 train_model.py' çalıştırın.")
        return

    # Kasten TreeSHAP explainer'ı bozuyoruz ki Fallback (DLIME) devreye girsin.
    # predictor._shap_explainer objesini None yaparak sanki SHAP hata vermiş/yüklenememiş gibi simüle ediyoruz.
    predictor._shap_explainer = None
    print("⚠️  SHAP Simulator: Kasten Kapatıldı (SHAP=None). DLIME Fallback bekleniyor...")

    # Arıza Riski Çok Yüksek olan yapay bir state (Risk üretmesi için)
    # Eğitim verisinden esinlenerek `main_pressure` ve `oil_tank_temperature` yüksek ayarlandı.
    dummy_machine = "HPR_TEST_001"
    dummy_state = {
        "buffers": {
            "main_pressure": [125.0] * 30,             # Limit 110
            "oil_tank_temperature": [55.0] * 30,       # Limit 45
            "horizontal_press_pressure": [60.0] * 30,  # Normal
            "lower_ejector_pressure": [50.0] * 30,     # Normal
            "horitzonal_infeed_speed": [0.0] * 30,     # Normal
            "vertical_infeed_speed": [0.0] * 30        # Normal
        },
        "ewma_mean": {
            "main_pressure": 125.0,
            "oil_tank_temperature": 55.0,
            "horizontal_press_pressure": 60.0,
            "lower_ejector_pressure": 50.0,
            "horitzonal_infeed_speed": 0.0,
            "vertical_infeed_speed": 0.0
        },
        "ewma_var": {
            "main_pressure": 2.0,
            "oil_tank_temperature": 1.5,
            "horizontal_press_pressure": 0.0,
            "lower_ejector_pressure": 0.0,
            "horitzonal_infeed_speed": 0.0,
            "vertical_infeed_speed": 0.0
        },
        "sample_count": {"main_pressure": 100, "oil_tank_temperature": 100}
    }

    # Tahmin yap. Beklenti: Yüksek risk ve _dlime_explainer'ın açıklamayı devralması.
    result = predictor.predict_risk(dummy_machine, dummy_state)

    print(f"\nScore: {result.score}")
    print(f"Confidence: {result.confidence}")
    print(f"Top Features: {result.top_features}")
    print("-" * 50)
    print("NLG + DLIME Açıklaması:\n" + result.explanation)
    print("-" * 50)
    
    if "[DLIME]" in result.explanation:
        print("✅ TEST BAŞARILI: SHAP çöktüğü anda DLIME fallback devralarak başarıyla insan okunabilir açıklama üretti!")
    else:
        print("❌ TEST BAŞARISIZ: DLIME etiketi metnin içinde bulunamadı. SHAP kapanmış olmasına rağmen DLIME devreye girmemiş olabilir veya NLG hata verdi.")

if __name__ == "__main__":
    test_dlime_fallback()
