# 📊 Veri Toplama Stratejisi ve 30-Gün Kampanyası

> **Doküman Tipi:** Strateji ve Operasyonel Plan  
> **Son Güncelleme:** 2026-03-18  
> **Sorumlu:** R. Ahsen Çiçek  
> **Durum:** 🟢 Aktif Uygulamada

---

## 🎯 Vizyon: Gerçek Bağlam-Aware AI

### Neden Bu Strateji?

Endüstriyel arıza tahmininde **başarısız AI projelerinin** en büyük nedeni **yetersiz ve bağlamdan yoksun veridir**:

```
❌ Sadece "anlık değer" toplamak
   → "Basınç 120 bar" (Ne oldu? Neden? Ne olacak?)

✅ Zengin bağlam penceresi toplamak
   → "Basınç 30 dk'da 90→120 bar yükseldi, 
      yağ sıcaklığı paralel artış gösterdi,
      makine 2 saattir çalışıyordu (cold start değil),
      son 24 saatte 3 benzer olay yaşandı"
```

**Fark:** Teknisyene "Ne yapmalıyım?" sorusunun cevabını verebilmek için **sebep-sonuç zinciri** gerekir.

---

## 🆕 Yeni Sistem: Rich Context Collector

### Dosya
- **Konum:** [`scripts/data_tools/context_collector.py`](../scripts/data_tools/context_collector.py)
- **Çıktı:** `rich_context_windows.json`
- **Entegrasyon:** [`src/app/hpr_monitor.py`](../src/app/hpr_monitor.py) (satır 21-22, 531-540)

### Zaman Penceresi Mimarisi

```
┌─────────────────────────────────────────────────────────────┐
│                    ZAMAN PENCERESİ (40 dk)                   │
├─────────────────┬─────────────────┬─────────────────────────┤
│  PRE-FAULT      │    FAULT ANI    │    POST-FAULT           │
│  (30 dk)        │    (anlık)      │    (10 dk)              │
├─────────────────┼─────────────────┼─────────────────────────┤
│ • Trend analizi │ • Limit aşımı   │ • Stabilizasyon         │
│ • Korelasyon    │ • Tüm sensörler │ • Dönüşüm hızı          │
│ • İvme hesabı   │ • Etiketleme    │ • Kalıcı mı geçici mi   │
└─────────────────┴─────────────────┴─────────────────────────┘
         ↑                ↑                  ↑
    "Neden oldu?"    "Ne oldu?"        "Sonuç ne?"
```

### Toplanan Bağlam Öğeleri

| Öğe | Açıklama | Örnek |
|-----|----------|-------|
| **Pre-fault trend** | 30 dk'lık sensör geçmişi | Basınç: 90→95→102→110→120 bar |
| **Korelasyon matrisi** | Sensörler arası ilişki | Basınç-Sıcaklık korelasyonu: 0.85 |
| **Operating minutes** | Makine çalışma süresi | 145 dakika (cold start değil) |
| **Recent fault history** | Son 24 saat olayları | 3 benzer FAULT yaşandı |
| **Cold start flag** | Başlangıç durumu | `is_cold_start: false` |
| **Post-fault recovery** | 10 dk'lık stabilizasyon | Değer normal sınırlara döndü |

---

## 📅 30-Gün Veri Kampanyası Planı

### Faz 1: Veri Toplama (Gün 1-30: 18 Mart - 17 Nisan 2026)

**Hedef:** ~1,500 valid FAULT context + 10,000 NORMAL örnek

#### Günlük Beklentiler

```
6 makine × 24 saat × ~0.8 FAULT/makine/gün = ~50 FAULT/gün
30 gün × 50 FAULT = ~1,500 FAULT (hedef)
```

#### Valid FAULT Kriterleri

| Kriter | Değer | Açıklama |
|--------|-------|----------|
| Limit aşımı | ✅ Zorunlu | Min/max değer aşılmalı |
| Cold start | ❌ Hariç | Operating minutes > 60 dk |
| Pre-fault veri | ✅ Zorunlu | En az 20 örnek (10 dk) |
| Post-fault veri | 🟡 Tercih | 10 dk stabilizasyon |

### Faz 2: Veri Temizliği (Gün 30-35: 17-22 Nisan)

**İşlemler:**
1. Cold start FAULT'ları filtrele (~%20)
2. Düşük kaliteli pre-fault verilerini ele (~%10)
3. Sensör korelasyonlarını normalize et
4. Feature engineering (türetilmiş özellikler)

**Beklenen çıktı:** ~1,200 high-quality FAULT + 10,000 NORMAL

### Faz 3: Model Eğitimi (Gün 35-40: 22-27 Nisan)

**Eğitim Stratejisi:**
```python
# Hedef model mimarisi
Model: XGBoost / Random Forest Ensemble
XAI: TreeSHAP (primary) + DLIME (fallback)
NLG: CodleanNLGEngine (Türkçe açıklamalar)
Input: 33+ features (rich context'den türetilmiş)
Output: Risk skoru (0-100) + Açıklama + ETA
```

### Faz 4: Production (Gün 40+: 27 Nisan+)

**Deployment:**
- Gerçek zamanlı tahmin (canlı pipeline)
- Açıklanabilir AI çıktıları
- Teknisyen feedback loop (opsiyonel)

---

## 🏷️ Etiketleme Stratejisi (Teknisyensiz)

### Problemler ve Çözümler

| Problem | Çözüm | Uygulama |
|---------|-------|----------|
| Teknisyen feedback yok | Kural-based etiketleme | Limit aşımı = GERÇEK FAULT |
| Cold start sahtekarlığı | Operating minutes filtresi | <60 dk = IGNORE |
| Dengesiz veri | Stratified sampling | %20 FAULT / %80 NORMAL hedefi |

### Etiketleme Kuralları

```python
# context_collector.py içinde uygulanan kurallar

if limit_aşımı and operating_minutes > 60:
    label = "VALID_FAULT"        # ✅ Model eğitimi için
    is_valid_fault = True
elif limit_aşımı and operating_minutes <= 60:
    label = "COLD_START_FAULT"   # 🚫 Filtrelenir
    is_valid_fault = False
else:
    label = "NORMAL"             # ⚪ Referans veri
```

---

## 📁 Veri Dosyaları ve Yapıları

### 1. `rich_context_windows.json` (Yeni)

**Yapı:**
```json
{
  "meta": {
    "started_at": "2026-03-18T08:16:22+00:00",
    "updated_at": "2026-03-18T11:26:19+00:00",
    "version": "2.0-rich-context",
    "config": {
      "pre_fault_minutes": 30,
      "post_fault_minutes": 10,
      "cold_start_minutes": 60
    }
  },
  "machines": {
    "HPR001": {
      "context_windows": [
        {
          "ts": "2026-03-18T10:15:30+00:00",
          "machine_id": "HPR001",
          "fault_sensors": ["main_pressure"],
          "readings": { /* anlık değerler */ },
          "pre_fault_window": {
            "duration_minutes": 30,
            "samples": 45,
            "summary": {
              "main_pressure": {
                "mean": 105.2,
                "min": 98.5,
                "max": 118.3,
                "trend": "increasing",
                "samples": 45
              }
            }
          },
          "context": {
            "is_cold_start": false,
            "operating_minutes": 145.5,
            "recent_faults_24h": 2,
            "correlations": {
              "pressure_mean": 112.4,
              "thermal_pressure_index": 4.2
            }
          },
          "labels": {
            "is_valid_fault": true,
            "fault_type": "single_sensor"
          }
        }
      ]
    }
  }
}
```

### 2. Eski Dosyalar (Referans)

| Dosya | Amaç | Durum |
|-------|------|-------|
| `live_windows.json` | Basit pencere (geriye uyumluluk) | 🟡 Aktif ama eski |
| `violation_log.json` | Tarihsel violation kayıtları | 🟡 Arşiv |
| `historical_violations_mart_2026.json` | Mart 16 tarihsel veri | 🟡 Arşiv |

---

## 🔧 Operasyonel Detaylar

### Sistem Başlatma

```bash
# Zengin context toplama ile başlat
PYTHONPATH=/Users/mac/kafka:$PYTHONPATH python src/app/hpr_monitor.py

# Çıktı:
# - live_windows.json (basit)
# - rich_context_windows.json (zengin) ← YENİ
# - state.json (sistem durumu)
```

### İzleme ve Kontrol

```bash
# Sistem durumu
./sistem_durum.sh

# Zengin context özeti (Python)
python3 -c "from scripts.data_tools.context_collector import summary; print(summary())"
# Çıktı: 🧠 Rich Context: Total=15 Valid=12
```

### Haftalık Kontrol Listesi

- [ ] `rich_context_windows.json` boyutu kontrolü
- [ ] Valid FAULT sayısı takibi (hedef: ~350/hafta)
- [ ] Cold start oranı kontrolü (hedef: <%20)
- [ ] Pre-fault sample kalitesi (hedef: >30 örnek/FAULT)
- [ ] Kafka bağlantısı stabilite kontrolü

---

## 📊 Başarı Metrikleri

### 30 Gün Sonunda Hedeflenen

| Metrik | Hedef | Minimum Kabul |
|--------|-------|---------------|
| Valid FAULT context | 1,500 | 1,000 |
| Ortalama pre-fault sample | 40 | 20 |
| Cold start filtresi oranı | %20 | %30 |
| Sensör korelasyon kapsamı | 6/6 | 4/6 |
| Makine başına veri dengesi | Eşit | ±%50 |

### Kalite Kontrol

```python
# Her FAULT context için kalite skoru
quality_score = (
    (pre_fault_samples / 40) * 0.4 +      # %40 ağırlık
    (1 if not is_cold_start else 0) * 0.3 +  # %30 ağırlık
    (correlation_completeness / 6) * 0.3     # %30 ağırlık
)

# quality_score > 0.7 → "High Quality"
# quality_score 0.4-0.7 → "Medium Quality"
# quality_score < 0.4 → "Low Quality" (filtrele)
```

---

## 🚨 Riskler ve Önlemler

| Risk | Olasılık | Etki | Önlem |
|------|----------|------|-------|
| Kafka bağlantı kesintisi | Orta | Yüksek | Otomatik retry + yedekleme |
| Düşük FAULT oranı | Düşük | Yüksek | 45 güne uzatma opsiyonu |
| Cold start baskınlığı | Orta | Orta | Filtreleme + stratified sampling |
| Disk alanı yetersizliği | Düşük | Orta | Haftalık arşivleme |

---

## 📝 Tarihçe ve Değişiklikler

| Tarih | Değişiklik | Sorumlu |
|-------|-----------|---------|
| 2026-03-18 | İlk versiyon - Rich Context Collector devreye alındı | R. Ahsen Çiçek |

---

## 🔗 İlgili Dokümanlar

- [`PROJECT_DETAILS.md`](../PROJECT_DETAILS.md) - Genel proje durumu
- [`README.md`](../README.md) - Hızlı başlangıç
- [`docs/pipeline_mimarisi.md`](pipeline_mimarisi.md) - Teknik mimari
- [`scripts/data_tools/context_collector.py`](../scripts/data_tools/context_collector.py) - Kaynak kod

---

> **Not:** Bu strateji, teknik detaylar ve güncellemeler için `PROJECT_DETAILS.md`'yi takip edin.
