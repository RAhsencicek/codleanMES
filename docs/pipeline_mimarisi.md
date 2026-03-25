# Codlean MES — Sistem Mimarisi

> **Son güncelleme:** 2026-03-24
> **Durum:** Canlı — Kafka bağlantısı aktif, 6 HPR makinesi izleniyor

---

## Sistem Ne Yapar?

Fabrikadaki hidrolik pres makinelerinin (HPR) sensör verilerini gerçek zamanlı okur. Anlık limit aşımlarını, yavaş tırmanan tehlikeli trendleri ve karmaşık çok-sensörlü örüntüleri tespit eder. Bir arıza olmadan önce teknisyeni Türkçe, somut, aksiyona dönüştürülebilir bir uyarıyla bilgilendirir.

---

## Veri Akışı (Uçtan Uca)

```
Fabrika PLC'leri
     │
     │  JSON mesajı (her ~10 saniyede bir)
     ▼
Kafka Broker (mqtt-topic-v2, 10.71.120.10:7001)
     │
     ▼
┌─────────────────────────────────────────────────┐
│  KATMAN 0 — Veri Doğrulama                      │
│  data_validator.py                              │
│  • Virgüllü sayıları düzelt ("37,5" → 37.5)     │
│  • UNAVAILABLE → None                           │
│  • 5 dakikadan eski mesajları işaretle           │
│  • 5-sigma spike filtresi                       │
│  • Startup maskesi (ilk 60 dakika)              │
└─────────────────────┬───────────────────────────┘
                      │ Temiz veri paketi
                      ▼
┌─────────────────────────────────────────────────┐
│  KATMAN 1 — Hafıza (State Store)                │
│  state_store.py                                 │
│  • Ring buffer: son 720 ölçüm (~2 saat) RAM'de  │
│  • EWMA: gürültü filtrelenmiş hareketli ortalama│
│  • Güven skoru: az veriyle alarm verme          │
│  • 5 dakikada bir state.json'a yedekle          │
└─────────────────────┬───────────────────────────┘
                      │ Geçmiş + anlık durum
                      ▼
┌─────────────────────────────────────────────────┐
│  KATMAN 2 — Analiz Motoru                       │
│                                                 │
│  threshold_checker.py                           │
│  • Anlık değer vs IK limitleri                  │
│  • %85 soft, %100 yüksek, %110 kritik           │
│  • Boolean sensörler: kaç dakikadır sorunlu?    │
│                                                 │
│  trend_detector.py                              │
│  • Son 30 ölçüme lineer regresyon               │
│  • R² ≥ 0.70 → güvenilir trend                 │
│  • ETA: limite kaç dakika kaldığını hesapla     │
│                                                 │
│  risk_scorer.py                                 │
│  • Threshold + Trend + ML → ensemble 0-100 skor │
│  • Physics kuralları (causal_rules.json)        │
│  • Hidrolik zorlanma, termal stres tespiti      │
└─────────────────────┬───────────────────────────┘
                      │ Risk skoru + sebepler
                      ▼
┌─────────────────────────────────────────────────┐
│  KATMAN 2.5 — ML & Açıklanabilirlik             │
│                                                 │
│  ml_predictor.py                                │
│  • XGBoost/Random Forest modeli                 │
│  • State store'dan özellik vektörü oluştur      │
│  • Anomali olasılığı (0-1) → 0-100 skor         │
│                                                 │
│  SHAP → DLIME (fallback) → NLG                  │
│  • Hangi sensör neden katkıda bulunuyor?        │
│  • Türkçe açıklama cümlesi üret                 │
│                                                 │
│  context_builder.py + llm_engine.py             │
│  • Alarm sonrası tüm bağlamı Gemini'ye gönder   │
│  • "Ne oluyor, neden, ne yapmalı?" analizi      │
└─────────────────────┬───────────────────────────┘
                      │ Açıklanabilir alarm
                      ▼
┌─────────────────────────────────────────────────┐
│  KATMAN 3 — Alert Engine                        │
│  alert_engine.py                                │
│  • Throttle: 30 dk normal, 15 dk kritik         │
│  • FAULT vs PRE_FAULT_WARNING ayrımı            │
│  • Renkli terminal paneli (rich)                │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
              Teknisyen Ekranı
              (2×3 HPR grid dashboard)
```

---

## Modül Haritası

| Modül | Konum | Görevi |
|-------|-------|--------|
| **hpr_monitor.py** | `src/app/` | Ana uygulama — tüm katmanları birbirine bağlar |
| **data_validator.py** | `src/core/` | Katman 0 — ham veriyi temizler |
| **state_store.py** | `src/core/` | Katman 1 — ring buffer, EWMA, disk checkpoint |
| **kafka_consumer.py** | `src/core/` | Genel amaçlı Kafka tüketicisi (tüm makine tipleri) |
| **threshold_checker.py** | `src/analysis/` | Anlık limit kontrolü |
| **trend_detector.py** | `src/analysis/` | Lineer regresyon + ETA hesabı |
| **risk_scorer.py** | `src/analysis/` | Ensemble risk puanı (0-100) |
| **nlg_engine.py** | `src/analysis/` | SHAP değerlerini Türkçeye çevirir |
| **dlime_explainer.py** | `src/analysis/` | SHAP çökünce devreye giren yedek açıklayıcı |
| **alert_engine.py** | `src/alerts/` | Throttle, formatlama, terminale basma |
| **ml_predictor.py** | `pipeline/` | ML modeli yükler ve tahmin üretir |
| **context_builder.py** | `pipeline/` | Alarm bağlamını Gemini için paketler |
| **llm_engine.py** | `pipeline/` | Gemini API — AI Usta Başı analizi |
| **window_collector.py** | `scripts/data_tools/` | Basit veri penceresi kaydeder |
| **context_collector.py** | `scripts/data_tools/` | ±30 dk zengin bağlam penceresi kaydeder |
| **sync_limits_from_db.py** | `scripts/data_tools/` | IK DB → limits_config.yaml senkronizasyonu |
| **kafka_env.py** | `scripts/` | Tüm scriptler için ortak Kafka bağlantı ayarları |
| **train_model.py** | `scripts/ml_tools/` | ML modelini eğitir |
| **shap_analyzer.py** | `scripts/ml_tools/` | SHAP analizi ve görselleştirme |

---

## Konfigürasyon Dosyaları

| Dosya | İçeriği | Değiştirme Yöntemi |
|-------|---------|-------------------|
| `config/limits_config.yaml` | Makine limitleri, EWMA, pipeline parametreleri | `sync_limits_from_db.py` veya elle |
| `docs/causal_rules.json` | Fizik tabanlı bağlam kuralları | Elle — bakım müh. girdisiyle |
| `.env` | API key, Kafka IP (git'e girmiyor) | Elle — `.env.example`'dan kopyala |
| `pipeline/model/model.pkl` | Eğitilmiş ML modeli | `train_model.py` çalıştırınca güncellenir |

---

## Makine Envanteri

| Tip | Prefix | Violation Sensörü | Notlar |
|-----|--------|-------------------|--------|
| Dikey Pres | HPR001,003,004,005 | 6 sayısal + 16 boolean | Tam donanımlı |
| Yatay Pres | HPR002,006 | 2 sayısal | Sadece basınç + hız |
| Testere | TST001-004 | 4 sayısal | Saw speed, torque, current, cut time |
| Endüksiyon | IND | Yok | Sadece trend izleniyor |
| Robot | RBT | Yok | Sadece trend izleniyor |
| CNC | CNC | Yok | Sadece trend izleniyor |

**Not:** `horitzonal_infeed_speed` sensörü kasıtlı yazım hatasıyla var — PLC de bu ismi kullanıyor, değiştirme.

---

## Veri Depolama

| Dosya | Ne Kadar Büyür | Ne Zaman Silinir |
|-------|----------------|------------------|
| `state.json` | ~1-2 MB sabit | Silme — sistem hafızası |
| `live_windows.json` | Yavaş büyür | Eğitimden sonra arşivlenebilir |
| `rich_context_windows.json` | 30 günde ~50-75 MB | ML eğitimi sonrası arşivle |
| `logs/` | Günlük rotasyon | 7 gün sonra silinebilir |

---

## Alarm Mantığı

```
Kafka mesajı geldi
       │
       ├─ Threshold aşıldı? → FAULT alarm (güven %100, IK limiti)
       │
       ├─ Trend > 0 ve güçlü? → TREND uyarısı (ETA: X dakika)
       │
       ├─ ML anomali > %50? → PRE_FAULT_WARNING (olasılıksal)
       │
       └─ Physics kuralı tetiklendi? → Risk skoru +bonus
              │
              └─ Toplam skor > 20 → Alert engine'e gönder
                        │
                        └─ Throttle geçtiyse → Terminale bas
                                  │
                                  └─ Alarm sonrası → Gemini analizi (arka planda)
```

---

## Dayanıklılık

Sistem her katmanda bağımsız çalışabilir:

- ML modeli yoksa → Threshold + Trend yeterli
- Gemini API key yoksa → NLG template açıklaması yeterli
- SHAP başarısız olursa → DLIME devreye girer
- Kafka bağlantısı kopunca → Son state.json'dan devam eder
- Elektrik kesilirse → 5 dk'lık checkpoint kaybı, geri kalanı kurtarılır