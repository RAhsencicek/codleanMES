# 🏭 Katman 2 ve Katman 2.5 — Karar Motoru & AI Usta Başı

> **Son güncelleme:** 2026-03-17  
> **Durum:** ✅ Güncel (Faz 1.5 Tamamlandı)  
> **Sorumlu Modül:** `src/analysis/risk_scorer.py`, `pipeline/ml_predictor.py`, `src/analysis/nlg_engine.py`, `src/analysis/dlime_explainer.py`

---

Bu katman **değerlendirme merkezidir**. State store'dan gelen zenginleştirilmiş veriyi hem Kural Tabanlı sistem (Threshold & Trend) ile hem de **Açıklanabilir Makine Öğrenimi (SHAP)** ile iki farklı açıdan analiz eder ve sonuçları tek bir risk skorunda birleştirir.

## KATMAN 2: Kural Tabanlı Sinyal Üreticiler

### 1. ThresholdChecker (Birincil Sinyal)
Sensörün anlık değerini config'deki sınırlarla karşılaştırır. 
- **KRİTİK:** %110 eşiği aşıldı!
- **YÜKSEK:** %100 limit aşıldı!
- **ORTA:** %85 ile yaklaştı.

### 2. TrendDetector (İkincil Sinyal)
Anahtarı anlık değerin ötesinde **yönü ve hızı** ölçmesidir. Doğrusal Regresyon kullanır. Son 30 ölçümün eğimi eğer artış yönündeyse ve R² değeri iyi uyumdaysa "Tahmini Kalan Saat (ETA)" hesaplaması yapar. Startup sürecindeyse bu filtre maskelenir.

### 3. RiskScorer — Sinyalleri Birleştirme
Eğer iki sistem birlikte uyarı yapıyorsa ETA süre kısalığına göre `(1.0 - ETA/240dk)` aciliyet ve eşik tehlike çarpanlarıyla toplam bir risk listesi türeterek `0.0-100.0` arası nihai skor doğurur ve Confidence durumu (örn: zayıf veriye düşük risk skor ağırlığı) ile çarpılır.

---

## 🚀 KATMAN 2.5: Bağlam Motoru & Nedensellik (AI Usta Başı)

Katı kuralları (Threshold & Trend) aşan ama yine de fiziksel anomalilerin habercisi veriler (Pre-Fault Pattern) devreye girer.

### XGBoost / Random Forest Predicter:
Canlı pipeline `ml_predictor.py` üzerinden 3 günlük "Violation Log" veri serileriyle eğitilmiş (4,518 snapshot) ML modelimiz devreye girer. Yalnızca min/max aşımlarına değinmez; özelliklerin birbirine göre durumunu da çıkarır.

### TreeSHAP (Açıklanabilir AI / XAI):
Model siyah kutu (black-box) değildir! Modele her tahmininde **"Neden %85 risk verdin?"** sorusunu sorarak Şapley istatistiksel katkılarını döndürür (`shap_analyzer.py`).
- **Örnek SHAP Çıktısı:** `{"total_faults_window": +0.173, "active_sensors": +0.155}`
- **Performans:** Risk > %50 olduğunda çalışır (~100ms)

### DLIME Fallback (Deterministic LIME)
TreeSHAP sadece ağaç tabanlı modeller (XGBoost, Random Forest) ile çalışır. **DLIME (Deterministic LIME)** diğer model türleri için "sigorta" görevi görür:
- **AHC Clustering:** Veriyi otomatik kümelere ayırır
- **Lokal Ridge Regresyon:** Her küme için basit, açıklanabilir model
- **Fallback:** SHAP başarısız olursa DLIME devreye girer
- **Deterministik:** Rastgelelik yok, tekrarlanabilir sonuçlar
- **Konum:** `src/analysis/dlime_explainer.py`

### NLG (Doğal Dil Üretimi)
Teknisyene SHAP değerleri gibi teknik matematiksel loglar gitmez. `nlg_engine.py` modülü `CodleanNLGEngine` sınıfı ile bu sayıları Türkçe insan diline çevirir ve "Acil Müdahale / ETA" önerisi ekler.

**NLG Motoru Özellikleri:**
- **Şablon Tabanlı:** Önceden tanımlı Türkçe şablonlar
- **Bağlam Farkındalığı:** Risk seviyesine göre farklı ton (Düşük/Orta/Yüksek/Kritik)
- **Aksiyon Önerileri:** Her risk seviyesi için spesifik bakım talimatları
- **Physics-Informed:** Fizik kurallarından gelen ek açıklamalar (Hydraulic Strain, Thermal Stress)
- **Konum:** `src/analysis/nlg_engine.py`

> **Örnek Çalışan NLG Çıktısı (Risk: %100):**
> 🔍 **AI Usta Başı Analizi (Neden Riskli?):**
> • Penceredeki Toplam Hata Veren Sensör Sayısı arıza riskini ciddi ölçüde ARTIRIYOR (+0.173 katkı).
> • Aynı Anda Aktif Olan Sensör Sayısı arıza riskini ciddi ölçüde ARTIRIYOR (+0.155 katkı).
> 
> 💡 **ÖNERİLEN AKSİYON:** HEMEN MÜDAHALE EDİN: Makineyi rölantiye alın veya durdurun.
> ⏱️ **ETA:** Eğer müdahale edilmezse 30-45 dakika içinde donanımsal arıza beklenmektedir.

---

## 🆕 FAZ 1.5: Physics-Informed Kurallar (Fizik Temelli Zeka)

### Operating Minutes (Çalışma Süresi)
Makinenin startup anından itibaren geçen süreyi RAM'de tutar.
- **Formül:** `(time.time() - state["startup_time"]) / 60`
- **Amaç:** Soğuk makine maskelemesini dinamik bir xAI özelliği haline getirmek
- **Konum:** `state_store.py` içinde hesaplanır

### Hydraulic Strain (Hidrolik Zorlanma)
Yüksek basınç noktalarında düşük hareket gözlemlenmesi = Sıkışma/Kaçak tespiti.
- **Formül:** `pressure_ratio > 0.8 AND speed < 0.2`
- **Risk Çarpanı:** Olay bazlı +30 puan (Çok yüksek)
- **NLG Açıklaması:** "Hidrolik zorlanma tespit edildi, mekanik sıkışma veya valf kaçağı olabilir."

### Causal Rules (JSON Tabanlı)
Neo4j (Knowledge Graph) israfı yerine, endüstri standardı RAM bazlı basit JSON kuralları işletilir:
```json
{
  "thermal_stress": {
    "condition": "temp > 40 AND pressure > 100",
    "action": "Soğutma vanasını kontrol edin",
    "root_cause": "Yüksek basınç ve sıcaklık kombinasyonu termal stres oluşturuyor"
  }
}
```
