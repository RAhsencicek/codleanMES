# Katman 2 — Analiz Motoru ve Risk Skoru

> **Modüller:** `src/analysis/threshold_checker.py`, `src/analysis/trend_detector.py`, `src/analysis/risk_scorer.py`
> **Son güncelleme:** 2026-03-24

---

## Ne Yapar?

State store'dan gelen geçmiş + anlık sensör verisini üç bağımsız sinyal kaynağından geçirir ve 0-100 arası tek bir risk skoru üretir. Her kaynak farklı türde tehlikeyi yakalar:

| Kaynak | Ne Yakalar? | Güveni |
|--------|------------|--------|
| Threshold | Anlık limit aşımı | %100 deterministik |
| Trend | Yavaş tırmanan tehlike + ETA | R² kalitesine göre |
| ML | Çok-sensörlü örüntü | Model güvenine göre |
| Physics | Makine fiziği ihlali | Kural tabanlı |

---

## 2a — Threshold Checker

**Dosya:** `src/analysis/threshold_checker.py`

Anlık sensör değerini `limits_config.yaml`'daki limitlerle karşılaştırır.

### Sayısal Sensörler — Üç Seviye

```
değer > max × 1.10  → KRİTİK  (limitin %110 üstü)
değer > max         → YÜKSEK  (limit aşıldı)
değer > max × 0.85  → ORTA    (limite %85 yaklaştı)
değer < min         → YÜKSEK  (alt limit altına indi)
```

`soft_limit_ratio = 0.85` değeri `limits_config.yaml`'da ayarlıdır.

### Boolean Sensörler

Sayısal eşik değil, süre kontrolü:

```python
check_boolean(machine_id, sensor, bad_minutes, boolean_rules)
# bad_minutes: update_boolean()'dan gelir — kaç dakikadır kötü durumda?
# alert_after_minutes eşiğini geçince sinyal üretir
```

`alert_after_minutes` her sensör için `limits_config.yaml`'da tanımlı (filtreler: 60 dk, pompalar: 5 dk, tank seviyesi: 10 dk).

### Çıktı — `ThresholdSignal`

```python
@dataclass
class ThresholdSignal:
    machine_id: str
    sensor:     str
    value:      float
    limit:      float
    direction:  str    # "HIGH" | "LOW" | "BOOL"
    severity:   str    # "ORTA" | "YÜKSEK" | "KRİTİK"
    percent:    float  # Limitin yüzde kaçında
    unit:       str
    message:    str    # İnsan okunabilir açıklama
```

---

## 2b — Trend Detector

**Dosya:** `src/analysis/trend_detector.py`

Ring buffer'daki son 30 ölçüme doğrusal regresyon uygular. Değer henüz limitte değilken "bu hızla devam ederse X dakika sonra aşar" tahminini üretir.

### Nasıl Çalışır?

```
Son 30 ölçüm → Lineer regresyon (scipy.linregress veya yerli fallback)
                     ↓
              slope (eğim) + R² (uyum kalitesi)
                     ↓
R² < 0.70 → Trend gürültülü, sinyal üretme
R² ≥ 0.70 → Trend güvenilir
                     ↓
ETA = (limit - mevcut_değer) / slope × interval_sec / 60
```

### Filtreler

- **Minimum örnek:** 30 ölçüm gerekli, altında sessiz kal
- **R² eşiği:** 0.70 — dağınık trendlere inanma
- **ETA aralığı:** 5-480 dakika arası anlamlı. 5 dakikadan kısa ise threshold zaten yakalar; 8 saatten uzun ise çok belirsiz
- **Startup maskesi:** `is_startup=True` ise trend hesaplanmaz
- **Stale maskesi:** `is_stale=True` ise trend hesaplanmaz

### Scipy Yoksa

```python
try:
    from scipy.stats import linregress
except ImportError:
    # Yerli numpy-free regresyon kullanılır
    # Sistem scipy olmadan da çalışır
```

### Çıktı — `TrendSignal`

```python
@dataclass
class TrendSignal:
    machine_id:     str
    sensor:         str
    slope_per_hour: float   # Saat başına değişim (ölçüm birimi ile)
    eta_minutes:    float   # Limite kaç dakika kaldığı
    r_squared:      float   # Trendin güvenilirliği (0-1)
    current_value:  float
    limit:          float
    direction:      str     # "HIGH" | "LOW"
    unit:           str
    message:        str
```

---

## 2c — Risk Scorer

**Dosya:** `src/analysis/risk_scorer.py`

Threshold sinyalleri, trend sinyalleri ve ML çıktısını birleştirip 0-100 arası tek bir risk skoru üretir.

### Ensemble Ağırlıklandırma

Ağırlıklar sabit değil — veri güvenine (confidence) göre dinamik değişir:

| Güven | Threshold | Trend | ML |
|-------|-----------|-------|----|
| ≥ 0.70 | %35 | %25 | %40 |
| ≥ 0.30 | %45 | %30 | %25 |
| < 0.30 | %55 | %35 | %10 |

Az veriyle ML'e güvenmek tehlikeli — güven düştükçe ML ağırlığı azalır, kural tabanlı sistem öne geçer.

### Threshold Skoru

```python
THRESHOLD_WEIGHTS = {
    "ORTA":   30,
    "YÜKSEK": 60,
    "KRİTİK": 80,
}
# Birden fazla sinyal varsa toplanır (max 100)
```

### Trend Skoru

```python
urgency  = max(0.0, min(1.0, 1 - sig.eta_minutes / 480))
tr_score = 40 × urgency × sig.r_squared
# Aciliyeti yüksek (kısa ETA) ve güvenilir (yüksek R²) trendler daha ağır basar
```

### ML Dampening

Az veriyle ML'in katkısı bastırılır:

```python
ml_damp = ml_score_raw × max(confidence, 0.10)
```

### Physics-Informed Bonus

`docs/causal_rules.json`'daki fizik kuralları değerlendirilir. `risk_scorer.py` bu kuralları doğrudan ham `sensor_values` ve `machine_limits` üzerinden uygular (`context_builder.py`'nin `enriched_sensors`'u ile karıştırma — o sadece Gemini bağlamı içindir):

| Kural | Koşul | Bonus |
|-------|-------|-------|
| `hydraulic_strain` | main_pressure_ratio > 0.8 VE her iki hız_ratio < 0.2 | +30 puan |
| `thermal_stress` | oil_tank_temperature > 40 VE main_pressure > 100 | +20 puan |
| `cold_startup_mask` | operating_minutes < 60 | Bonus × 0.5 (azalt) |

**Not:** Bu bonus deterministik — kural tetiklenirse her zaman eklenir, ML'in kararını beklemez.

### Severity Haritası

```python
SEVERITY_MAP = [
    (75, "KRİTİK"),
    (55, "YÜKSEK"),
    (30, "ORTA"),
    (0,  "DÜŞÜK"),
]
```

### Çıktı — `RiskEvent`

```python
@dataclass
class RiskEvent:
    machine_id:        str
    risk_score:        float       # 0-100
    severity:          str         # DÜŞÜK / ORTA / YÜKSEK / KRİTİK
    confidence:        float       # 0-1
    reasons:           list[str]   # İnsan okunabilir sebepler
    eta_minutes:       float|None  # En yakın ETA
    sensor_values:     dict        # Anlık değerler
    threshold_signals: list
    trend_signals:     list
    ml_score:          float       # ML'in katkısı
    ml_confidence:     float       # Anomali olasılığı
    ml_explanation:    str         # ML açıklama cümlesi
```

---

## 2.5 — ML Predictor ve Açıklanabilirlik

**Dosya:** `pipeline/ml_predictor.py`

### Model Yükleme

```python
MODEL_PKL    = "pipeline/model/model.pkl"
FEATURE_JSON = "pipeline/model/feature_names.json"
```

Model yoksa sistem sessizce degrade olur — threshold + trend devam eder.

### Özellik Vektörü

State store'daki ring buffer ve EWMA'dan her sensör için 5 özellik türetilir:

```python
f"{sensor}__fault_count"   # Son 30 ölçümde limit aşan kaç değer
f"{sensor}__value_mean"    # Arıza anlarındaki ortalama (normal → 0)
f"{sensor}__value_std"     # Standart sapma
f"{sensor}__value_max"     # Maksimum değer
f"{sensor}__over_ratio"    # Ortalama / limit_max
```

Artı makine geneli:

```python
"active_sensors"       # Kaç sensörde eş zamanlı fault var
"multi_sensor_fault"   # 2+ sensörde eş zamanlı fault (0/1)
"total_faults_window"  # Toplam fault sayısı
```

**Bilinen sorun (feature leakage):** `total_faults_window` ve `active_sensors` özellikleri threshold checker'ın sayım sonucunu taşıyor. Model gerçek pre-fault sinyali değil, kural tabanlı sistemi taklit ediyor. Test F1=0.48. 30 günlük veri kampanyası sonrası bu özellikler kaldırılacak.

### SHAP → DLIME → NLG Zinciri

```
Model tahmini (proba)
        ↓
TreeSHAP (lazy eval — sadece risk > %50'de çalışır)
        ↓ başarısız olursa
DLIME Fallback (AHC clustering + Ridge regression)
        ↓
NLG Engine → Türkçe açıklama cümlesi
```

**TreeSHAP:** XGBoost/RF için optimize edilmiş. Her özelliğin tahmine katkısını hesaplar. `shap_values[feature]` = o özelliğin anomali olasılığına katkısı.

**DLIME:** SHAP başarısız olursa veya ağaç tabanlı olmayan model kullanılırsa devreye girer. Eğitim verisini 5 kümeye böler, en yakın kümedeki örnekler üzerinde Ridge regresyon eğitir. Deterministik — her çalıştırmada aynı sonucu verir.

**NLG:** SHAP veya DLIME çıktısını alır, özellik adlarını Türkçeye çevirir, risk seviyesine göre tonu ayarlar:

```
%85+ → "🚨 KRİTİK: Hemen müdahale edin..."
%70+ → "⚠️ YÜKSEK: İzlemeye alın..."
%50+ → "⚡ ORTA: Dikkat..."
```

---

## 2.5 — Context Builder ve AI Usta Başı

**Dosyalar:** `pipeline/context_builder.py`, `pipeline/llm_engine.py`

### Context Builder

Alarm üretildiğinde `context_builder.build()` çağrılır. Şu bilgileri Gemini için paketler:

```python
{
    "machine_id": "HPR001",
    "risk_score": 75.0,
    "severity": "YÜKSEK",
    "operating_time": "3 saat 22 dakika",
    "sensor_states": {
        "main_pressure": {
            "value": 102.5, "limit_pct": 93.2,
            "status_label": "🔴 KRİTİK YAKLAŞIM",
            "slope_per_hour": 4.2,   # saatte 4.2 bar artıyor
        },
        ...
    },
    "limit_violations": ["Ana Basınç: 102.5 bar (limit: 110)"],
    "critical_sensors": ["Yağ Sıcaklığı: limitin %91'inde ↑"],
    "eta_predictions": {"main_pressure": {"eta_minutes": 22, ...}},
    "active_physics_rules": [
        "Yüksek sıcaklık ve aşırı ana basınç kombinasyonu termal stres yaratıyor.",
        "→ Öneri: Soğutma sistemini kontrol edin..."
    ],
    "similar_past_events": [],   # Faz 2'de dolacak
}
```

**Enriched Sensors:** Kural değerlendirmesi için türetilmiş değerler hesaplanır:
- `main_pressure_ratio` = main_pressure / max_limit
- `horitzonal_infeed_speed_ratio` = |hız| / max_limit
- `operating_minutes` = machine_data'dan

### AI Usta Başı (Gemini)

Alert üretildiğinde `llm_engine.analyze_async()` arka planda çağrılır. 10 saniyelik timeout ve en fazla 3 eş zamanlı çağrı var (`ThreadPoolExecutor(max_workers=3)`).

```
Alarm tetiklendi
      ↓
context_builder.build() → bağlam paketi
      ↓
_usta.analyze_async(ctx, callback)
      ↓ (arka planda, 10s timeout)
Gemini API → Türkçe analiz
      ↓
_ai_analysis[machine_id] = {"text": ..., "ts": datetime.now()}
      ↓
Dashboard'da 30 dk boyunca gösterilir
```

Gemini'ye şu system prompt gider: "HPR'de uzmanlaşmış 15 yıllık bakım mühendisi gibi düşün. Her analizde: (1) Ne oluyor? (2) Devam ederse ne olur? (3) Şimdi ne yapmalı?"

**GEMINI_API_KEY** ortam değişkeni tanımlı değilse AI Usta Başı sessizce devre dışı kalır — sistem çalışmaya devam eder.

---

## Bağlantılar

- Önceki katman: `docs/pipeline_detay_katman1.md`
- Sonraki katman: `docs/pipeline_detay_katman3.md`
- Kaynak kodlar: `src/analysis/`, `pipeline/`
- Fizik kuralları: `docs/causal_rules.json`
