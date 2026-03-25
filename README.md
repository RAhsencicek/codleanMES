# Codlean MES — Fabrika Arıza Tahmin Sistemi

> **Durum:** 🟡 Pilot Faz — Sistem canlıda, veri kampanyası devam ediyor
> **Son güncelleme:** 2026-03-24

---

## Ne Yapar?

Fabrikadaki hidrolik pres makinelerinin (HPR) sensör verilerini Kafka üzerinden gerçek zamanlı okur. Anlık limit aşımlarını, yavaş tırmanan tehlikeli trendleri ve fizik tabanlı bileşik anomalileri tespit eder. Arıza olmadan önce teknisyene Türkçe, somut, aksiyona dönüştürülebilir bir uyarı verir.

```
Fabrika PLC → Kafka → [Temizle → Hafızala → Analiz Et → Bağlam Kur → Alarm Ver] → Teknisyen
```

---

## Hızlı Başlangıç

```bash
# 1. Ortamı kur
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Ortam değişkenlerini ayarla
cp .env.example .env
# .env içine KAFKA_BOOTSTRAP_SERVERS ve GEMINI_API_KEY ekle

# 3. Çalıştır
PYTHONPATH=. python3 src/app/hpr_monitor.py
```

---

## Sistem Bileşenleri

| Bileşen | Durum | Açıklama |
|---------|-------|----------|
| Threshold alarmları | ✅ Çalışıyor | IK veritabanı limitleriyle anlık eşik kontrolü |
| Trend tespiti + ETA | ✅ Çalışıyor | Lineer regresyon, R²≥0.70, limite kalan dakika |
| Physics kuralları | ✅ Çalışıyor | Termal stres, hidrolik zorlanma, soğuk makine |
| ML modeli | ✅ Yüklü, beta | XGBoost — F1=0.48 (veri birikince yeniden eğitilecek) |
| SHAP + DLIME + NLG | ✅ Çalışıyor | Açıklanabilir AI, Türkçe analiz metni |
| AI Usta Başı (Gemini) | ✅ API key ile | Alarm sonrası bağlam analizi |
| Veri toplama | ✅ Çalışıyor | window_collector + context_collector aktif |
| Dashboard | ✅ Çalışıyor | 2×3 HPR grid, renkli terminal UI |

---

## Dokümanlar

| Doküman | İçerik |
|---------|--------|
| `docs/TODO_VE_TEKNIK_BORC.md` | Proje durumu, yapılacaklar, bilinen sorunlar |
| `docs/MIMARI.md` | Sistem mimarisi ve veri akışı |
| `docs/pipeline_detay_katman0.md` | Veri doğrulama katmanı |
| `docs/pipeline_detay_katman1.md` | State store ve hafıza yönetimi |
| `docs/pipeline_detay_katman2.md` | Analiz motoru, ML, AI Usta Başı |
| `docs/pipeline_detay_katman3.md` | Alert engine ve alarm formatları |
| `docs/causal_rules.json` | Fizik tabanlı bağlam kuralları |

---

## Proje Yapısı

```
kafka/
├── src/
│   ├── app/
│   │   └── hpr_monitor.py          ← Ana uygulama
│   ├── core/
│   │   ├── data_validator.py       ← Katman 0: Veri temizleme
│   │   └── state_store.py          ← Katman 1: Ring buffer, EWMA
│   ├── analysis/
│   │   ├── threshold_checker.py    ← Anlık limit kontrolü
│   │   ├── trend_detector.py       ← Lineer regresyon + ETA
│   │   ├── risk_scorer.py          ← Ensemble risk skoru
│   │   ├── nlg_engine.py           ← Türkçe açıklama üretici
│   │   └── dlime_explainer.py      ← SHAP yedek açıklayıcı
│   └── alerts/
│       └── alert_engine.py         ← Throttle + terminal çıktısı
├── pipeline/
│   ├── ml_predictor.py             ← ML model tahmin motoru
│   ├── context_builder.py          ← Gemini bağlam paketleyici
│   ├── llm_engine.py               ← AI Usta Başı (Gemini)
│   └── model/
│       ├── model.pkl               ← Eğitilmiş model
│       └── feature_names.json      ← Özellik listesi
├── scripts/
│   ├── kafka_env.py                ← Ortak Kafka bağlantı ayarları
│   ├── ml_tools/
│   │   ├── train_model.py          ← Model eğitimi
│   │   └── shap_analyzer.py        ← SHAP analizi
│   └── data_tools/
│       ├── window_collector.py     ← Basit veri penceresi
│       ├── context_collector.py    ← Zengin bağlam penceresi
│       └── sync_limits_from_db.py  ← IK DB → limits_config senkronizasyonu
├── config/
│   └── limits_config.yaml          ← Makine limitleri ve sistem ayarları
├── docs/                           ← Dokümantasyon
├── .env.example                    ← Ortam değişkenleri şablonu
└── requirements.txt
```

---

## Ortam Değişkenleri

| Değişken | Varsayılan | Açıklama |
|----------|-----------|----------|
| `KAFKA_BOOTSTRAP_SERVERS` | `10.71.120.10:7001` | Kafka broker adresi |
| `KAFKA_TOPIC` | `mqtt-topic-v2` | Topic adı |
| `GEMINI_API_KEY` | — | AI Usta Başı için zorunlu |
| `CONFIG_PATH` | `config/limits_config.yaml` | Config dosyası yolu |

---

## IK Veritabanından Limit Güncelleme

IK yeni CSV gönderince:

```bash
python3 scripts/data_tools/sync_limits_from_db.py \
  --typefile /path/to/machinetypedataitems.csv \
  --machinefile /path/to/machinedataitems.csv \
  --machines HPR001,HPR003,HPR004,HPR005 \
  --tst-machines TST001,TST002,TST003,TST004 \
  --dry-run
```

HPR002 ve HPR006 Yatay Pres tipinde — bunları ayrıca kontrol et.

---

## Önemli Notlar

- `horitzonal_infeed_speed` yazımı kasıtlıdır — PLC cihazı bu ismi kullanıyor, değiştirme.
- `state.json` dosyasını silme — sistemin 2 saatlik hafızası burada.
- `GEMINI_API_KEY` yoksa AI Usta Başı sessizce devre dışı kalır, sistem çalışmaya devam eder.
- Sistem her katmanda bağımsız çalışır: ML yoksa threshold+trend, Gemini yoksa NLG template yeterli.