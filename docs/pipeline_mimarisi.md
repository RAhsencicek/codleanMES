# 🏭 Codlean MES — Öncü Arıza Tahmin Pipeline Mimari Özeti

> **Amaç:** Bu doküman, projeyi bilen ya da bilmeyen herkesin pipeline'ı başından sonuna ana hatlarıyla kavrayabilmesi için yazılmıştır. Detaylı teknik süreçler alt dokümanlara bölünmüştür.

**Son güncelleme:** 2026-03-13
**Durum:** ✅ Hibrit AI ve Açıklanabilir AI (TreeSHAP) entegre edildi.

---

## 🏗️ Genel Pipeline Mimarisi (Kuşbakışı)

Pipeline, Kafka'dan ham veriyi okuyup teknisyene anlamlı bir uyarı üretene kadar 4 (+1) ana katmandan geçirir. Her katman bir öncekinden **temizlenmiş ve zenginleştirilmiş** veri alır. Bir katman hata verirse sistem çökmez.

```text
┌─────────────────────────────────────────────────────────┐
│                    KAFKA CONSUMER                       │
│          mqtt-topic-v2 @ 10.71.120.10:7001              │
└───────────────────────┬─────────────────────────────────┘
                        │  Ham JSON mesajı
                        ▼
┌─────────────────────────────────────────────────────────┐
│         KATMAN 0: VERİ GİRİŞ & DOĞRULAMA                │
│  "Bu veri güvenilir mi, işlenebilir mi?"                │
│  👉 Detay: [Katman 0 Dokümanı](pipeline_detay_katman0.md)      │
└───────────────────────┬─────────────────────────────────┘
                        │  Doğrulanmış veri paketi
                        ▼
┌─────────────────────────────────────────────────────────┐
│         KATMAN 1: STATE STORE (Bellek)                  │
│  "Bu makinenin geçmişini ve bağlamını biliyorum."       │
│  👉 Detay: [Katman 1 Dokümanı](pipeline_detay_katman1.md)      │
└───────────────────────┬─────────────────────────────────┘
                        │  Zenginleştirilmiş durum verisi
                        ▼
┌─────────────────────────────────────────────────────────┐
│         KATMAN 2: ANALİZ MOTORU                         │
│  "Bu makinede risk var mı? Varsa ne kadar acil?"        │
│  👉 Detay: [Katman 2 Dokümanı](pipeline_detay_katman2.md)      │
└───────────────────────┬─────────────────────────────────┘
                        │  Risk skoru
                        ▼
┌─────────────────────────────────────────────────────────┐
│         KATMAN 2.5: BAĞLAM MOTORU (PHYSICS & XAI)       │
│  "KÖK NEDEN nedir? (Physics-Informed + SHAP + NLG)"     │
│  👉 Detay: [Katman 2 Dokümanı](pipeline_detay_katman2.md)      │
└───────────────────────┬─────────────────────────────────┘
                        │  Açıklanabilir (XAI) Cümle
                        ▼
┌─────────────────────────────────────────────────────────┐
│         KATMAN 3: ALERT ENGINE                          │
│  "Teknisyen ne görüyor? Ne zaman, nasıl bildirilecek?"  │
│  👉 Detay: [Katman 3 Dokümanı](pipeline_detay_katman3.md)      │
└─────────────────────────────────────────────────────────┘
```

---

## 🛠️ Modüller ve Sorumluluklar (GÜNCEL YAPI)

| Modül | Sorumluluk | Girdi | Çıktı |
|-------|-----------|-------|-------|
| `src/app/hpr_monitor.py` | Ana Canlı İzleme Sistemi | Kafka topic | UI Console Log |
| `src/core/data_validator.py` | Schema, UNAVAILABLE, spike, stale, startup | Raw JSON | Temiz dict veya None |
| `src/core/state_store.py` | Ring buffer, EWMA, confidence, boolean | Temiz dict | Güncellenen state |
| `src/analysis/threshold_checker.py` | Anlık değer vs config limiti | Sensör değeri + limits | ThresholdSignal |
| `src/analysis/trend_detector.py` | Doğrusal regresyon, ETA tahmini | Ring buffer + limit | TrendSignal |
| `src/analysis/risk_scorer.py` | Kural Tabanlı sinyaller | İki signal + confidence | RiskEvent (0-100) |
| `pipeline/ml_predictor.py`| Pre-Fault Makine Öğrenimi Tahminleri | Window İstatistikleri | Model Prediction |
| `src/analysis/nlg_engine.py`| SHAP'tan Doğal Dile Açıklama Üretimi | SHAP Values | Natural Language |
| `src/alerts/alert_engine.py` | Throttle, XAI çeviri, DB kaydı, terminal | RiskEvent + ML | Ekran çıktısı |
| `config/limits_config.yaml` | Min/max değerleri, tüm parametreler | — | Config dict |

---

## Makine Envanteri ve Hedef Segmenti (3 Mart Kontrolü)

Sistem Kafka verilerine göre HPR (Hidrolik Pres), IND (Endüksiyon), TST (Testere) ve RBT (Robot) makinelerini tarar. Arızaya en yatkın olan ve üzerinde veri zenginliği yakalanan 3 pilot makine üzerine inşa edilmiştir: **HPR001**, **HPR003**, **HPR005**.

Sensörler ana hatlarıyla şöyledir:
- *Yağ tankı sıcaklığı, ana hidrolik devresi basıncı, yatay/dikey besleme hızı*

---

*Detaylı kod akışı ve algoritma açıklamaları için yukarıdaki `pipeline_detay_katman[N].md` dosyalarına başvurunuz.*
