# Codlean MES — Production-Ready Fault Prediction Pipeline (Hybrid System)

> **Son güncelleme:** 2026-03-18  
> **Durum:** ✅ Faz 2 Başladı | 🧠 Zengin Context Toplama Aktif | 📊 30-Gün Veri Kampanyası  
> **Author:** R. Ahsen Çiçek  
> **Strateji:** Rule-Based (kesin) + ML Pre-Fault (olası) + Physics-Informed Context + **Rich Context Windows**

---

## 📋 CURRENT STATE (Güncel Durum - 18 Mart 2026)

| Bileşen | Durum | Son Güncelleme | Açıklama |
|---------|-------|----------------|----------|
| **Faz 1.5 (Physics-Informed)** | ✅ Tamamlandı | 2026-03-17 | Operating Minutes, Hydraulic Strain, Cold Startup |
| **Faz 2 (Rich Context)** | 🟢 **Aktif** | 2026-03-18 | ±30dk zaman penceresi, sebep-sonuç analizi |
| **DLIME Fallback** | ✅ Entegre | 2026-03-17 | Deterministic LIME ile XAI |
| **NLG Motor** | ✅ Canlı | 2026-03-17 | Türkçe doğal dil açıklamaları |
| **Context Collector** | 🟢 **Yeni** | 2026-03-18 | `context_collector.py` devrede |
| **Veri Toplama** | 🟢 Aktif (7+ saat) | 2026-03-18 | Kafka bağlantısı stabil |
| **Sistem** | 🟢 Çalışıyor | 2026-03-18 | PID: 64219 |

### 🆕 YENİ: Zengin Context Toplama Sistemi (18 Mart 2026)

**Yeni Modül:** `scripts/data_tools/context_collector.py`

| Özellik | Değer | Amaç |
|---------|-------|------|
| **Pre-fault pencere** | 30 dk | Trend başlangıcını yakalama |
| **Fault anı** | Anlık | Limit aşımı tespiti |
| **Post-fault pencere** | 10 dk | Stabilizasyon analizi |
| **Cold start filtresi** | 60 dk | Sahte FAULT eliminasyonu |
| **Korelasyon analizi** | Çoklu sensör | Neden-sonuç ilişkisi |
| **Operating minutes** | Entegre | Makine yaşını hesaplama |

**Çıktı Dosyası:** `rich_context_windows.json`
- Her FAULT için zengin bağlam penceresi
- Pre/post-fault trend verileri
- Sensör korelasyon matrisleri
- Cold start etiketlemesi

---

## 🎯 30-GÜN VERİ KAMPANYASI (Mart-Nisan 2026)

### Hedef
Gerçek bağlam-aware AI için **yeterli ve kaliteli veri** toplamak.

### Zaman Çizelgesi

| Dönem | Tarih | Hedef | Çıktı |
|-------|-------|-------|-------|
| **Gün 1-30** | 18 Mart - 17 Nisan | Zengin context toplama | ~1,500 valid FAULT context |
| **Gün 30-35** | 17-22 Nisan | Veri temizliği & feature engineering | Temizlenmiş veri seti |
| **Gün 35-40** | 22-27 Nisan | Model eğitimi & validasyon | TreeSHAP + DLIME + NLG entegre model |
| **Gün 40+** | 27 Nisan+ | Production deployment | Gerçek zamanlı açıklanabilir AI |

### Beklenen Veri Seti (30 gün sonunda)

```
Toplam Hedef: 11,500+ örnek
├── Valid FAULT:    1,500+ (zengin context ile)
├── Cold Start:     ~300 (filtrelenmiş)
└── NORMAL:         10,000+ (dengeli sampling)
```

### Etiketleme Stratejisi (Teknisyensiz)

| Durum | Kural | Etiket |
|-------|-------|--------|
| Limit aşımı + Cold start değil | `is_valid_fault = true` | ✅ GERÇEK FAULT |
| Limit aşımı + Cold start (<60dk) | `is_valid_fault = false` | 🚫 IGNORE |
| Normal çalışma | - | ⚪ NORMAL |

---

## 📊 MEVCUT VERİ ENVANTERİ (18 Mart 2026)

| Kaynak | Boyut | Dönem | Kalite |
|--------|-------|-------|--------|
| `violation_log.json` | 346 KB | 3-5 Mart | 🟡 Sadece anlık değerler |
| `historical_violations_mart_2026.json` | 2.9 MB | 16 Mart | 🟡 Metadata only |
| `live_windows.json` | 21 KB | 18 Mart+ | 🟡 Basit pencere |
| `rich_context_windows.json` | - | 18 Mart+ | 🟢 **Zengin context** (yeni) |
| `incident_*.json` (41 adet) | - | Şubat-Mart | 🟡 Etiketsiz |

**Not:** Eski veriler bağlam analizi için yetersiz. **30 gün yeni veri toplama** kritik önemde.

---

---

## 🎯 Proje Amacı — GÜNCELLENMİŞ FELSEFE

### TEMEL PRENSİP:
> "Teknisyen onayı: Min/max limit aşımı = GERÇEK FAULT (kesin doğru)"
> 
> "Model alarmı false positive olabilir, ama limit aşımı KESİN hatadır"
>
> "Arıza anında teknisyene sadece skoru değil, KÖK NEDENİ (Bağlamı) sunmalıyız."

**ÜÇ KATMANLI HYBRID (BAĞLAM-FARKINDALIKLI) SİSTEM:**

1. **Rule-Based Fault Detection (KESİN)**
   - `limits_config.yaml` kullanılıyor
   - Min/max limit kontrolü
   - ✅ Açıklanabilir: "Hangi sensör, hangi limit, ne kadar aşıldı"
   - ✅ Güvenilir: Teknisyen onaylı
   - ✅ Actionable: "Ne yapmalı?" önerisi

2. **ML Pre-Fault Prediction (OLASI)**
   - Random Forest / XGBoost
   - 30-60 dakika önce uyarı
   - ✅ Trend analizi: "Sıcaklık 3 gündür yükseliyor"
   - ✅ Multi-sensor correlation
   - ⚠️ Olasılık: %50-80 confidence

3. **[YENİ] AI Usta Başı / Bağlam Motoru (PHYSICS-INFORMED)**
   - Olaylar arası nedensellik bağı kurar ve makine fiziğini anlar (Faz 1.5).
   - Neo4j yerine, RAM tabanlı hızlı Causal JSON kuralları işletir.
   - ✅ Açıklanabilir AI (XAI): "Hidrolik zorlanma tespit edildi."
   - ✅ Actionable NLG: Şablonlarla teknisyene Türkçe bakım tavsiyesi verir.
   - ✅ Operating Minutes ile soğuk makine toleransı tanır.

---

## 📊 VERİ SETİ — ŞEFFAF ANALİZ

### Ana Kaynak: violation_log.json

**Kaynak:** `kafka_scan.py` ile tarihsel Kafka verisi tarandı (3-5 Mart 2026)

```python
Toplam Kafka mesajı:   15,517,524 (tüm sistem)
HPR mesajları:          2,691,005 (sadece HPR makineleri)
Window boyutu:          10 dakika (6 Kafka mesajı/window)
Toplam window:          2,691,005 (HPR)
```

**Makine bazlı dağılım:**
| Makine | Normal | Fault | Toplam | Fault Rate | Durum |
|--------|--------|-------|--------|------------|-------|
| HPR001 | 426,173 | 26,965 | 453,138 | %5.95 🔴 | Kritik |
| HPR005 | 432,337 | 20,723 | 453,060 | %4.57 🟡 | Dikkat |
| HPR003 | 450,363 | 2,693 | 453,056 | %0.59 ✅ | Sağlıklı |
| HPR006 | 452,811 | 244 | 453,055 | %0.05 ✅ | Sağlıklı |
| HPR002 | 425,614 | 61 | 425,675 | %0.01 ✅ | Sağlıklı |
| HPR004 | 452,997 | 24 | 453,021 | %0.01 ✅ | Sağlıklı |
| **TOPLAM** | **2,640,295** | **50,710** | **2,691,005** | **%1.88** | |

### ML Eğitim Verisi: ml_training_data.csv

**Feature engineering:** 10 dakikalık window'lardan 33 özellik çıkarıldı

**Örnekleme stratejisi:**
```python
# Class imbalance yönetimi:
✅ TÜM FAULT'LAR:    534 window (%11.8)
✅ PRE-FAULT:        582 window (%12.9) - Fault'tan 60 dk önce
✅ NORMAL ÖRNEKLEM: 3,402 window (%75.3) - 2.64M'den stratified sampling

TOPLAM: 4,518 satır × 33 özellik
```

**Neden sadece 4,518 satır?**
- ❌ 2.64M normal alırsak → Class imbalance %98 olur
- ✅ 3,402 normal yeterli → Model "normal profili" öğrenir
- ✅ Dengeli veri → Daha iyi generalization

**Labeling stratejisi (HYBRID):**
```python
# Rule-based labeling (limits_config.yaml):
if value > max_limit or value < min_limit:
    label = FAULT  # KESİN - teknisyen onaylı

# Pre-fault labeling:
if fault_at_time_t:
    for window in range(t-60min, t):
        label[window] = PRE_FAULT  # 60 dk önce uyarı
```

**Label dağılımı:**
| Label | Açıklama | Nasıl belirlenir | Oran |
|-------|----------|------------------|------|
| **FAULT** | Limit aşımı var | Min/max limit kontrolü (rule-based) | %11.8 |
| **PRE_FAULT** | Fault öncesi 60 dk | Sonraki window'da fault gelecek | %12.9 |
| **NORMAL** | Limit aşımı yok | Tüm sensörler min/max içinde | %75.3 |

---

## 🗂️ Dosya Yapısı

Proje, endüstri standartlarına uygun modüler düzende organize edilmiştir.

### 🌟 Yeni Dizin Yapısı
```
kafka/
├── src/                    # Ana Kaynak Kodları (Uygulama Mantığı)
│   ├── app/                # Çekirdek pipeline (hpr_monitor.py vd.)
│   ├── models/             # ML model loading/prediction
│   ├── core/               # Konfigürasyon, veritabanı, loglama altyapısı
│   └── ui/                 # 3-Bölmeli AI Dashboard (dashboard_pro.py)
├── scripts/                # Utility & Data Extraction scriptleri (kafka_scan.py)
├── tests/                  # Birim ve entegrasyon testleri (test_*.py)
├── config/                 # limits_config.yaml ve DB ayarları
├── docs/                   # Dokümantasyon (pipeline_mimarisi.md)
├── data/                   # JSON logları ve CSV eğitim verileri
├── logs/                   # Sistem log çıktıları
└── pipeline/               # ML Eğitim Artefaktları (model.pkl)
```

### Konfigürasyon
```
limits_config.yaml     → Makine limitleri (min/max), EWMA alpha
```

### Dokümantasyon
```
README.md              → Bu dosya (ANA BAĞLAM - HYBRID SYSTEM)
pipeline_mimarisi.md   → Detaylı mimari doküman
ml_iyilestirme_analizi.md.resolved → ML analiz notları
```

---

## 🚀 HIZLI BAŞLANGIÇ

### 1. Syntax Kontrolü
```bash
cd /Users/mac/kafka
python3 -m py_compile scripts/ml_tools/train_model.py && echo "✅ OK"
```

### 2. Model Eğitimi
```bash
cd /Users/mac/kafka
source venv/bin/activate
python3 scripts/ml_tools/train_model.py
```

**Beklenen çıktı:**
```
═══════════════════════════════════════════════════════
  HPR ML Model Eğitimi  —  2026-03-06 15:35:20
  Validation: Stratified Time-based + 5-fold CV
═══════════════════════════════════════════════════════

📊 Train/Test Split (Time-based):
   Train: 3,614 window (2026-02-27 → 2026-03-04)
   Test:    904 window (2026-03-04 → 2026-03-06)

🔧 Stratified 5-Fold Cross-Validation:
   Fold 1: F1=0.698 | Fault rate: 23.0%
   Fold 2: F1=0.667 | Fault rate: 23.0%
   Fold 3: F1=0.672 | Fault rate: 23.0%
   Fold 4: F1=0.718 | Fault rate: 23.0%
   Fold 5: F1=0.675 | Fault rate: 22.9%
   ────────────────────────────────────────
   CV F1: 0.686 ± 0.019 (STABİL ✅)

🎯 Threshold Tuning (Recall-focused):
   Threshold 0.35: P=1.00, R=0.50, F1=0.67
   Threshold 0.25: P=0.32, R=1.00, F1=0.48 ← RECALL-OPTIMAL

💰 Cost Analysis:
   False Positive cost: $10,000
   False Negative cost: $50,000
   
   Threshold 0.35: Total cost = $9.32M
   Threshold 0.25: Total cost = $6.17M ← MINIMUM ($3.15M tasarruf!)

🏆 EN İYİ MODEL: RandomForest
   Test F1: 0.48
   Test Precision: 0.32
   Test Recall: 1.00 (TÜM ARIZALAR YAKALANDI!)
   Threshold: 0.25 (recall-focused)
   
📊 Feature Importance (Top 5):
   1. total_faults_window (28.7%)
   2. active_sensors (25.6%)
   3. main_pressure__over_ratio (6.0%)
   4. main_pressure__value_max (5.6%)
   5. horizontal_press_pressure__value_max (5.1%)
```

### 3. Hybrid Alert System Testi
```bash
python3 test_hybrid_alerts.py
```

**Örnek output:**
```
🔴 FAULT ALERT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Makine: HPR001
Tip:    KESİN (confidence: 100%)
Sebep:
  • main_pressure: 126.5 bar (max: 120) → %5.4 aşım
  • horizontal_press_pressure: 125.3 (max: 120) → %4.4 aşım
  • ⚠️  MULTI-SENSOR FAULT: 2 sensör limit dışı!

Öneri: ACİL: Makineyi durdur, basınç sistemini kontrol et
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🟡 PRE-FAULT WARNING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Makine: HPR002
Tip:    OLASI (confidence: 75%)
Zaman:  Önümüzdeki 30-60 dakika

Belirtiler:
  • main_pressure trend: Son 3 saatte %15 artış ↑
  • active_sensors: 1 → 3 arttı (multi-sensor activity)

Öneri: 24 saat içinde bakım planla
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 🧠 HYBRID SYSTEM MİMARİSİ

### NEDEN HYBRID?

**GEÇMİŞTEKİ SORUN:**
```python
❌ Sadece ML model:
   → "FAULT" diyor ama "neden" demiyor
   → Black box, açıklanamıyor
   → Teknisyen güvenmiyor
   → False alarm çok
```

**HYBRID (BAĞLAMLI) ÇÖZÜM:**
```python
✅ Rule-Based (kesin) + AI Usta Başı (Bağlam) + ML Pre-Fault (olası):
   → Rule-based: "main_pressure > 120 → FAULT" (açıklanabilir)
   → AI Usta Başı: "Bu bir Termal Stres olayıdır, çünkü sıcaklık da fırlamış." (Kök Neden)
   → ML: "Önümüzdeki 30 dk fault olasılığı %75" (erken uyarı)
   → Hepsi birlikte: Güvenilir, Açıklanabilir ve Tam Zamanlı Koruma
```

---

## 📋 KATMAN 1: RULE-BASED FAULT DETECTION (KESİN)

### Çalışma Prensibi:
```python
def detect_faults(window_data, limits_config):
    """Min/max limit kontrolü - KESİN SONUÇ"""
    
    faults = []
    for sensor, value in window_data.items():
        limit_min = limits_config[sensor]['min']
        limit_max = limits_config[sensor]['max']
        
        if value > limit_max:
            faults.append({
                'sensor': sensor,
                'value': value,
                'limit': limit_max,
                'type': 'MAX_EXCEEDED',
                'over_ratio': (value - limit_max) / limit_max
            })
        elif value < limit_min:
            faults.append({
                'sensor': sensor,
                'value': value,
                'limit': limit_min,
                'type': 'MIN_EXCEEDED',
                'under_ratio': (limit_min - value) / limit_min
            })
    
    return faults
```

### Alert Formatı:
```json
{
  "type": "FAULT",
  "machine": "HPR001",
  "confidence": 1.0,
  "reasons": [
    "main_pressure: 126.5 bar (max: 120) → %5.4 aşım",
    "horizontal_press_pressure: 125.3 (max: 120) → %4.4 aşım",
    "⚠️  MULTI-SENSOR FAULT: 2 sensör limit dışı!"
  ],
  "recommendation": "ACİL: Makineyi durdur, basınç sistemini kontrol et"
}
```

### Avantajlar:
- ✅ **Açıklanabilir:** Hangi sensör, hangi limit, ne kadar aşıldı
- ✅ **Güvenilir:** Min/max aşımı = gerçek fault (teknisyen onaylı)
- ✅ **Actionable:** "Ne yapmalı?" önerisi veriyor
- ✅ **Basit:** limits_config.yaml kullanıyor (zaten var)

---

## 📋 KATMAN 2: ML PRE-FAULT PREDICTION (OLASI)

### Çalışma Prensibi:
```python
def predict_pre_fault(window_features, model):
    """ML modeli - 30-60 dk önce uyarı"""
    
    probability = model.predict_proba(window_features)[0, 1]
    
    if probability > 0.25:  # Recall-focused threshold
        # Trend analizi ekle
        trends = analyze_trends(window_features)
        
        return {
            'probability': probability,
            'trends': trends,
            'warning_level': 'HIGH' if probability > 0.7 else 'MEDIUM'
        }
    
    return None
```

### Alert Formatı:
```json
{
  "type": "PRE_FAULT_WARNING",
  "machine": "HPR002",
  "confidence": 0.75,
  "time_horizon": "30-60 dakika",
  "reasons": [
    "main_pressure trend: Son 3 saatte %15 artış ↑",
    "active_sensors: 1 → 3 arttı (multi-sensor activity)",
    "oil_temperature: 38°C → 42°C (yükselişte)"
  ],
  "recommendation": "24 saat içinde bakım planla"
}
```

### Avantajlar:
- ✅ **Erken uyarı:** 30-60 dakika önce haber veriyor
- ✅ **Trend analizi:** "Sıcaklık 3 gündür yükseliyor" diyebiliyor
- ✅ **Multi-sensor correlation:** 2+ sensör aynı anda fault veriyor
- ✅ **Olasılık bazlı:** Confidence score veriyor

---

## 🎯 HYBRID ALERT ENGINE

### Birleştirme Mantığı:
```python
def generate_alert(window_data, window_features, model, limits_config):
    """
    Hybrid alert system:
    1. Rule-based fault detection (kesin)
    2. ML pre-fault prediction (olası)
    3. Explanation generation
    """
    
    alerts = []
    
    # ─── KATMAN 1: RULE-BASED FAULT (KESİN) ──────────────────────────────
    faults = detect_faults(window_data, limits_config)
    
    if faults:
        alert = {
            'type': 'FAULT',
            'machine': window_data['machine_id'],
            'confidence': 1.0,
            'reasons': [],
            'recommendation': ''
        }
        
        for fault in faults:
            # Explanation üret
            reason = f"{fault['sensor']}: {fault['value']:.1f} ({fault['limit']})"
            alert['reasons'].append(reason)
        
        # Multi-sensor fault check
        if len(faults) >= 2:
            alert['reasons'].append(f"⚠️  MULTI-SENSOR FAULT: {len(faults)} sensör!")
        
        # Recommendation
        if any(f['sensor'] == 'main_pressure' for f in faults):
            alert['recommendation'] = "ACİL: Makineyi durdur"
        elif len(faults) >= 2:
            alert['recommendation'] = "Makineyi durdur, çoklu sensör arızası"
        else:
            alert['recommendation'] = "İlk fırsat bakım planla"
        
        alerts.append(alert)
    
    # ─── KATMAN 2: ML PRE-FAULT PREDICTION (OLASI) ───────────────────────
    pre_fault = predict_pre_fault(window_features, model)
    
    if pre_fault and not faults:  # Fault yoksa pre-fault uyarısı ver
        warning = {
            'type': 'PRE_FAULT_WARNING',
            'machine': window_data['machine_id'],
            'confidence': pre_fault['probability'],
            'time_horizon': '30-60 dakika',
            'reasons': pre_fault['trends'],
            'recommendation': ''
        }
        
        if pre_fault['probability'] > 0.7:
            warning['recommendation'] = "24 saat içinde bakım planla"
        elif pre_fault['probability'] > 0.5:
            warning['recommendation'] = "48 saat içinde bakım planla"
        else:
            warning['recommendation'] = "İzlemeye devam et"
        
        alerts.append(warning)
    
    return alerts
```

---

## 📊 MODEL PERFORMANS RAPORU

### Production Model (2026-03-06) — Final Results

**Eğitim verisi:** 4,518 satır × 33 özellik  
**Validation:** Stratified 5-fold CV + Time-based split  
**Model:** RandomForest (threshold=0.25, recall-focused)

```
Cross-Validation (Stratified 5-Fold):
Fold 1: F1=0.6980 | AUC=0.7681 | Fault rate: 23.0%
Fold 2: F1=0.6667 | AUC=0.7500 | Fault rate: 23.0%
Fold 3: F1=0.6720 | AUC=0.7530 | Fault rate: 23.0%
Fold 4: F1=0.7181 | AUC=0.7801 | Fault rate: 23.0%
Fold 5: F1=0.6747 | AUC=0.7545 | Fault rate: 22.9%
───────────────────────────────────────
CV F1: 0.686 ± 0.019 (STABİL ✅)
CV AUC: 0.761 ± 0.011

Test Set Performansı (Threshold=0.25):
Precision: 0.32  (false alarm var - kabul edilebilir)
Recall:    1.00  (TÜM ARIZALAR YAKALANDI!)
F1 Score:  0.48
AUC:       0.67

Business Impact:
False Positive cost: $10,000
False Negative cost: $50,000
Total Cost: $6.17M  (threshold 0.35'e göre $3.15M tasarruf!)
```

### Threshold Kararı: RECALL-OPTIMAL

**Trade-off analizi:**
```
Threshold 0.35:
  Precision: 1.00 (hiç false alarm yok)
  Recall:    0.35 (arı zaların %65'i kaçıyor)
  Cost:      $9.32M

Threshold 0.25 (SEÇİLEN):
  Precision: 0.32 (bazı false alarm var)
  Recall:    1.00 (TÜM arızalar yakalanıyor)
  Cost:      $6.17M  ($3.15M TASARRUF!)
```

**Karar:**
> "Safety-critical sistem → Recall öncelikli
> False alarm kabul edilebilir, ama arıza kaçırma kabul edilemez!"

---

## 🔍 FEATURE IMPORTANCE ANALİZİ

**Top 10 Features (RandomForest):**
| Rank | Feature | Importance | Kategori |
|------|---------|------------|----------|
| 1 | `total_faults_window` | 28.7% | Multi-sensor |
| 2 | `active_sensors` | 25.6% | Multi-sensor |
| 3 | `main_pressure__over_ratio` | 6.0% | Pressure |
| 4 | `main_pressure__value_max` | 5.6% | Pressure |
| 5 | `horizontal_press_pressure__value_max` | 5.1% | Pressure |
| 6 | `main_pressure__value_mean` | 5.0% | Pressure |
| 7 | `main_pressure__fault_count` | 4.6% | Pressure |
| 8 | `horizontal_press_pressure__over_ratio` | 4.4% | Pressure |
| 9 | `horizontal_press_pressure__fault_count` | 3.7% | Pressure |
| 10 | `horizontal_press_pressure__value_mean` | 3.2% | Pressure |

**Insight'ler:**
1. **Multi-sensor fault detection** (%54 importance) → En kritik feature!
2. **Main pressure** en önemli sensör (%26 importance)
3. **Horizontal press pressure** ikinci önemli (%16 importance)
4. **Over ratio** (limit aşım oranı) çok önemli

---

## ⚠️ KRİTİK TASARIM KARARLARI

### 1. Neden Hybrid System?

**Alternatifler:**
- ❌ Sadece ML → Black box, açıklanamıyor, technisyen güvenmiyor
- ❌ Sadece Rule-based → Erken uyarı yok, pre-fault prediction yok
- ✅ Hybrid → İkisinin avantajlarını birleştiriyor

**Karar:**
> "Rule-based (kesin) + ML pre-fault (olası) → Güvenilir + Erken uyarı"

---

### 2. Neden Recall-Optimal Threshold?

**Trade-off:**
```
Precision-Optimal (0.35):
  ✅ Hiç false alarm yok
  ❌ Arızaların %65'i kaçıyor
  ❌ $9.32M cost

Recall-Optimal (0.25):
  ✅ TÜM arızalar yakalanıyor
  ⚠️ Bazı false alarm var (kabul edilebilir)
  ✅ $6.17M cost ($3.15M tasarruf!)
```

**Karar:**
> "Safety-critical sistem → Recall öncelikli
> Technisyen: 'Bazen false alarm gelsin, ama hiç arıza kaçırma'"

---

### 3. Neden TimeSeriesSplit?

**Sorun:**
- Normal K-Fold veya Stratified K-Fold zaman sırasını karıştırır
- Gelecek veri geçmişi eğitmek için kullanılabilir (temporal leakage)

**Çözüm:**
- TimeSeriesSplit → Zaman sırası korunur, gelecek sızıntısı olmaz
- Her fold gerçekçi bir "forward test" simüle eder

**⚠️ Bilinen Sınırlama (P0-2):**
- Mevcut veri seti sadece 3 gün → Temporal diversity yetersiz
- CV F1=0.686 güvenilir değil; gerçek genelleme kapasitesi Test F1=0.48'den de düşük olabilir
- Walk-forward validation 30 günlük veri birikince uygulanacak

**Karar:**
> "Production'da güvenilir olması için temporal sıra şart — CV stabilitesi ikincil öncelik"

---

## 🧪 EDGE CASE VALIDATION (ROI-Conscious)

### Manuel Etiketleme Yapmıyoruz. Sebepler:

**ROI Analizi:**
```
Manuel etiketleme:
- 4,518 window × 2 dk = 9,036 dk = 150 SAAT = 6.25 GÜN!
- Beklenen iyileşme: +2% F1 (0.68 → 0.70)
- ROI: KÖTÜ ❌

Violation_log zaten güvenilir:
- limits_config.yaml kullanılıyor (technisyen onaylı)
- Min/max aşımı = KESİN fault
- Edge case'ler nadir
```

### Yerine Ne Yapıyoruz:

**Validation Sampling (30 dk):**
```python
# Validation set'ten 50 satır örneklem
sample_50 = validation_set.sample(50, random_state=42)

# Her satırı manuel incele:
for row in sample_50:
    - Gerçekten fault mu?
    - Edge case var mı?
    - Pre-fault doğru etiketlenmiş mi?
```

**Edge Case Rules (20 dk):**
```python
# Sadece bulunan problemleri düzelt
if label == FAULT and total_faults_window == 0:
    if max_over_ratio < 0.01:  # %1 aşım
        label = NORMAL  # False positive
```

**Hybrid System (30 dk):**
```python
# Rule-based + ML
def hybrid_label(...):
    # 1. Min/max limits
    # 2. Trend analysis
    # 3. Multi-sensor correlation
```

**TOPLAM:** ~1.5 saat  
**BEKLENEN:** +2-4% F1, +25-50% precision  
**ROI:** MÜKEMMEL! ✅

---

## 📈 ROADMAP — SONRAKİ ADIMLAR

### Hafta 1 (2026-03-06 → 2026-03-13)
**Hybrid System Implementation**
- ✅ Rule-based fault detection kodu yazıldı
- 🔄 Alert engine hybrid hale getiriliyor
- 📊 Validation sampling yapılacak (50 satır)
- 🔍 Edge case rules eklenecek

### Hafta 2 (2026-03-13 → 2026-03-20)
**Production Testing**
- 🎯 Sliding window inference testi
- ⏱️ Latency ölçümü (10 dakikada bir prediction)
- 📊 False positive/negative cost tracking
- 🛠️ Technician feedback loop

### Hafta 3 (2026-03-20 → 2026-03-27)
**Deployment Preparation**
- 🚀 Docker container hazırlığı
- 📦 Model versioning (MLflow/DVC)
- 📈 Monitoring dashboard (Prometheus+Grafana)
- 🔄 Retrain strategy (haftalık mı, günlük mü?)

---

## 🆘 TROUBLESHOOTING

### Problem: Model çok fazla false alarm üretiyor
```python
# Çözüm: Threshold'u artır
RECALL_FOCUSED_THRESHOLD = 0.35  # 0.25 yerine

# Beklenen:
Precision: 0.32 → 1.00 (false alarm yok)
Recall:    1.00 → 0.35 (arı zaların %65'i kaçıyor)
Cost:      $6.17M → $9.32M (daha pahalı)

# Trade-off: Güvenlik vs Maliyet
```

### Problem: CV skorları instabil
```python
# Çözüm: Stratified K-Fold kullan
from sklearn.model_selection import StratifiedKFold

skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
for train_idx, val_idx in skf.split(X_train, y_train):
    # Her fold'da aynı class distribution
```

### Problem: Rule-based çok katı, çok alarm veriyor
```python
# Çözüm: Over_ratio threshold ekle
if over_ratio > 0.05:  # %5+ aşım
    alert("FAULT")
else:
    alert("WARNING")  # Hafif aşım
```

---

## 📞 İLETİŞİM VE KAYNAKLAR

**Proje Sahibi:** R. Ahsen Çiçek  
**Kaynak Kodlar:** `/Users/mac/kafka/`  
**Kafka Broker:** `KAFKA_BOOTSTRAP_SERVERS` env variable ile konfigüre edilir  
**Topic:** `KAFKA_TOPIC` env variable ile konfigüre edilir  

**Dokümantasyon:**
- `pipeline_mimarisi.md` → Detaylı teknik doküman
- `limits_config.yaml` → Makine limitleri ve parametreler
- `ml_iyilestirme_analizi.md.resolved` → ML analiz notları

**Veri Dosyaları:**
- `violation_log.json` → 2.69M window, 50K+ fault (ANA KAYNAK)
- `ml_training_data.csv` → 4,518 satır feature-engineering yapılmış veri
- `pipeline/model/model.pkl` → Eğitilmiş Random Forest modeli
- `pipeline/model/model_report.json` → Performance metrikleri + CV scores + Feature importance

---

## ⚠️ BİLİNEN TEKNİK BORÇLAR

Bu sorunlar bilinçli olarak ertelendi. Veri kampanyası tamamlanınca (17 Nisan 2026+) ele alınacak.

| # | Sorun | Etki | Ne Zaman Çözülecek |
|---|-------|------|---------------------|
| **P0-1** | Feature Leakage: `total_faults_window` + `active_sensors` toplam önem %54. Model threshold checker'ın bilgisini ezberlemiş, gerçek pre-fault öğrenemiyor. | Test F1=0.48'nin temel nedeni | 30 günlük veri birikince feature engineering ile |
| **P0-2** | Temporal Leakage: CV F1=0.686 güvenilir değil. TimeSeriesSplit'e geçildi ama 3 günlük veriyle gerçek temporal diversity yok. | Gerçek performans test F1=0.48'den de düşük olabilir | Walk-forward validation 30 gün sonra |
| **P1** | PRE_FAULT labeling: "Fault'tan 60 dk öncesi PRE_FAULT" bazen o 60 dk içinde limitler zaten aşılmış olabilir. | Label gürültüsü, model sinyali geç öğreniyor | Yeniden eğitim sırasında |

---

## 📈 SONRAKİ ADIMLAR

### Şu An (18 Mart - 17 Nisan 2026)
- `rich_context_windows.json` dolsun — sistem çalışıyor, dokunma
- 1 Nisan ara kontrolü: Kaç FAULT context toplandı? Kalite yeterli mi?

### 17 Nisan Sonrası
1. Feature engineering — `total_faults_window` ve `active_sensors` çıkar, gerçek öncü sinyaller türet
2. Walk-forward validation uygula
3. PRE_FAULT labeling düzelt (limit aşılmamış pencereler)
4. Model yeniden eğit → F1 ≥ 0.65 hedefi
5. F1 hedefi tutarsa ML → Production

### Gelecek (Mayıs 2026+)
- Docker container hazırlığı
- Model versioning (MLflow/DVC)
- Monitoring (Prometheus + Grafana)
- Boolean sensör desteği (`filter_clogging`, `pump_status`)


---

> **Son güncelleme:** 2026-03-23 | Bir sonraki büyük güncelleme: 1 Nisan ara veri kontrolü

