<p align="center">
  <img src="docs/images/codlean_banner.png" alt="Codlean MES" width="720" />
</p>

<h1 align="center">🏭 Codlean MES</h1>
<h3 align="center">Akıllı Fabrika Arıza Tahmin ve Erken Uyarı Sistemi</h3>

<p align="center">
  <img src="https://img.shields.io/badge/durum-🟢%20Canlı%20Pilot-brightgreen?style=for-the-badge" alt="Durum" />
  <img src="https://img.shields.io/badge/makineler-6%20HPR%20Aktif-blue?style=for-the-badge" alt="Makineler" />
  <img src="https://img.shields.io/badge/model%20AUC-98.5%25-blueviolet?style=for-the-badge" alt="AUC" />
  <img src="https://img.shields.io/badge/maliyet-₺0-success?style=for-the-badge" alt="Maliyet" />
</p>

<p align="center">
  <em>Fabrikadaki 6 hidrolik presi 7/24 izler, arızayı <strong>olmadan önce</strong> tahmin eder<br/>ve teknisyene Türkçe, somut, aksiyona dönüştürülebilir uyarı verir.</em>
</p>

---

## 📋 İçindekiler

- [Ne Yapar?](#-ne-yapar)
- [İlk Gerçek Başarı](#-i̇lk-gerçek-başarı)
- [Mimari](#-mimari-sensörden-ekrana-5-katman)
- [Hızlı Başlangıç](#-hızlı-başlangıç)
- [Web Dashboard](#-web-dashboard)
- [Sistem Bileşenleri](#-sistem-bileşenleri)
- [Proje Yapısı](#-proje-yapısı)
- [Ortam Değişkenleri](#-ortam-değişkenleri)
- [Modülerlik ve Ölçeklenebilirlik](#-modülerlik-ve-ölçeklenebilirlik)
- [Yol Haritası](#-yol-haritası)
- [Dokümanlar](#-dokümanlar)
- [Önemli Notlar](#-önemli-notlar)

---

## 🎯 Ne Yapar?

Codlean MES, Türkiye'deki bir üretim tesisinde **6 hidrolik pres makinesini** (4 Dikey, 2 Yatay) gerçek zamanlı izleyen, **arızayı olmadan önce tahmin eden** ve teknisyene **ne yapması gerektiğini** söyleyen yapay zeka destekli bir erken uyarı sistemidir.

```
Fabrika PLC ──→ Kafka ──→ ┌─────────────────────────────────┐ ──→ Teknisyen
                          │  0. Temizle (Veri Doğrulama)     │
                          │  1. Hafızala (State Store / EWMA) │
                          │  2. Analiz Et (Risk Skoru)        │
                          │  2.5 AI (ML + SHAP + NLG)        │
                          │  3. Alarm Ver (Akıllı Bildirim)   │
                          └─────────────────────────────────┘
```

### İzlenen Makineler

| Makine | Tip | Sensörler | Durum |
|--------|-----|-----------|-------|
| **HPR001** | 🔵 Dikey Pres | 6 sayısal + 16 boolean | ✅ Aktif |
| **HPR002** | 🟠 Yatay Pres | 2 sayısal | ✅ Aktif |
| **HPR003** | 🔵 Dikey Pres | 6 sayısal + 16 boolean | ✅ Aktif |
| **HPR004** | 🔵 Dikey Pres | 6 sayısal + 16 boolean | ✅ Aktif |
| **HPR005** | 🔵 Dikey Pres | 6 sayısal + 16 boolean | ✅ Aktif |
| **HPR006** | 🟠 Yatay Pres | 2 sayısal | ✅ Aktif |

---

## 🏆 İlk Gerçek Başarı

> **15 Mart 2026, 03:45 — Gece Vardiyası, HPR003**

| Aşama | Zaman | Olay |
|-------|-------|------|
| ⚠️ Tespit | 03:45 | Yağ sıcaklığı 48°C'ye çıktı (Normal: 38°C, Trend: +2°C/saat) |
| 🔍 Teşhis | 03:45 | Filtre tıkanıklığı şüphesi (%78) |
| 📲 Bildirim | 03:47 | SMS gönderildi |
| 🔧 Müdahale | 04:15 | Teknisyen filtre değiştirdi |
| ✅ Çözüm | 04:45 | Makine 39°C'ye döndü |

**Sistem olmasaydı:** Saat 07:00'de otomatik durma → 3 saat üretim kaybı → **~₺50.000 zarar**  
**Kazanç:** 3 saat erken müdahale = **₺50K tasarruf** + plansız duruş engellendi

---

## 🧱 Mimari: Sensörden Ekrana 5 Katman

Sistem, ham sensör verisini **5 katmanlı** bir işlem hattından geçirerek anlamlı uyarılara dönüştürür:

### Katman 0 — Veri Doğrulama
Kirli fabrika verisini temizler: format düzeltme (virgül → nokta), bayat veri tespiti (>5dk), uç değer filtreleme (5-sigma), soğuk başlangıç maskesi (60dk).

### Katman 1 — State Store (Hafıza)
Son **720 ölçümü** (~2 saat) ring buffer'da tutar. EWMA ile gürültüyü filtreler, gerçek trendi ortaya çıkarır. Her 5 dakikada diske yedekler — elektrik kesilse bile kaldığı yerden devam eder. `threading.RLock` ile tam thread-safe.

### Katman 2 — Analiz Motoru (Risk Skoru)

| Alt Sistem | Görevi | Örnek |
|-----------|--------|-------|
| Limit Kontrolü | Sensör limitlerin %kaçında? | "Yağ sıcaklığı limitin %92'sinde" |
| Eğilim Tespiti | Trend yönü ve hızı | "Saatte +2°C artıyor → 3.5 saatte limite ulaşır" |
| Fizik Kuralları | Sensörler arası nedensel ilişki | "Sıcaklık↑ + Basınç↓ = iç kaçak belirtisi" |

**Çıktı:** 0-100 arası risk skoru + renk kodu (🟢 Normal → 🟡 Dikkat → 🟠 Yüksek → 🔴 Kritik)

### Katman 2.5 — Yapay Zeka Katmanı

| Bileşen | Ne Yapar |
|---------|---------|
| **ML Model** (Random Forest) | 4.564 örnek, 1.116 arıza kaydı ile eğitildi. AUC: **%98.5** |
| **SHAP + DLIME** | Modelin kararını açıklar: "Ana basınç kararın %45'ini oluşturuyor" |
| **NLG Motoru** | Matematiksel çıktıyı insanın anlayacağı Türkçeye çevirir |
| **AI Usta Başı** (Gemini Flash) | Doğal dille soru-cevap + filo karşılaştırmalı analiz |

### Katman 3 — Akıllı Alarm
Aynı alarmı üst üste çalmaz (30dk/15dk cooldown). Düşük riskte sessiz kalır. Kritik durumda anında bildirir.

---

## 🚀 Hızlı Başlangıç

```bash
# 1. Ortamı kur
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Ortam değişkenlerini ayarla
cp .env.example .env
# .env içine KAFKA_BOOTSTRAP_SERVERS ve GEMINI_API_KEY ekle

# 3. Monitörü başlat (Kafka verisi okur + analiz eder)
PYTHONPATH=. python3 src/app/hpr_monitor.py

# 4. Web Dashboard'u başlat (ayrı terminalde)
PYTHONPATH=. python3 src/app/web_server.py
# → http://localhost:5001
```

### Tek Komutla Başlatma

```bash
# Tüm sistemi başlat (monitor + web server)
./sistem_baslat.sh

# Durumu kontrol et
./sistem_durum.sh

# Durdur
./sistem_durdur.sh
```

---

## 🖥️ Web Dashboard

Tarayıcıda `http://localhost:5001` adresini açın:

| Özellik | Açıklama |
|---------|----------|
| **6 Makine Kartı** | Her biri anlık risk skoru, sensör değerleri ve çalışma durumu gösterir |
| **Renk Kodlaması** | 🟢 Normal / 🟡 Dikkat / 🟠 Yüksek / 🔴 Kritik |
| **Makine Tipi** | Her kartta 🔵 Dikey Pres veya 🟠 Yatay Pres etiketi |
| **Canlı Güncelleme** | SSE (Server-Sent Events) ile 2 saniyede bir otomatik yenileme |
| **Kafka Gecikme** | Verinin ne kadar taze olduğunu gösterir (Canlı / Normal / Gecikmeli / Kritik) |
| **AI Usta Başı** | Her makineye tıklayıp doğal dilde soru sorun, anlık analiz isteyin |
| **Filo Analizi** | Tek tıkla tüm makineleri karşılaştırmalı değerlendirme |

### API Endpoint'leri

| Endpoint | Metod | Açıklama |
|----------|-------|----------|
| `/` | GET | Dashboard ana sayfası |
| `/api/machines` | GET | Tüm makine verileri (JSON) |
| `/api/status` | GET | Sistem durum bilgisi |
| `/api/ask` | POST | AI Usta Başı'na soru sor `{machine_id, question}` |
| `/api/fleet` | GET | Filo karşılaştırmalı analiz (Gemini) |
| `/api/lag` | GET | Kafka gecikme detayları |
| `/stream` | GET | Server-Sent Events (2sn periyot) |

---

## ✅ Sistem Bileşenleri

| Bileşen | Durum | Detay |
|---------|-------|-------|
| Gerçek zamanlı izleme | ✅ Canlı | 6 makine, 2sn güncelleme |
| Threshold alarmları | ✅ Aktif | IK veritabanı limitleriyle eşik kontrolü |
| Trend tespiti + ETA | ✅ Aktif | EWMA + lineer regresyon, limite kalan süre |
| Fizik tabanlı teşhis | ✅ Aktif | `causal_rules.json` ile sensörler arası korelasyon |
| ML tahmin modeli | ✅ Aktif | Random Forest — AUC %98.5, sızdırmaz özellikler |
| SHAP + DLIME (XAI) | ✅ Aktif | Açıklanabilir AI — her kararın nedenini gösterir |
| NLG motoru | ✅ Aktif | Türkçe doğal dil açıklamaları |
| AI Usta Başı | ✅ Aktif | Gemini Flash ile doğal dil soru-cevap |
| Filo analizi | ✅ Aktif | Tüm makineleri karşılaştırmalı değerlendirme |
| Web Dashboard | ✅ Aktif | Flask + SSE, renk kodlu, canlı güncelleme |
| Benzer olay arama | ✅ Aktif | Geçmiş arızalarla benzerlik motoru |
| Thread güvenliği | ✅ Aktif | `threading.RLock` ile tam koruma |
| Felaket kurtarma | ✅ Aktif | State 5dk'da bir diske yedeklenir |

---

## 📁 Proje Yapısı

```
kafka/
├── src/
│   ├── app/
│   │   ├── hpr_monitor.py            ← Ana izleme uygulaması (Kafka → Analiz → Alarm)
│   │   ├── web_server.py             ← Flask web dashboard (localhost:5001)
│   │   └── mock_hpr_monitor.py       ← Geliştirme/test için sahte veri üretici
│   ├── core/
│   │   ├── data_validator.py         ← Katman 0: Veri temizleme, format düzeltme, 5-sigma
│   │   ├── state_store.py            ← Katman 1: Ring buffer, EWMA, disk yedekleme
│   │   ├── kafka_consumer.py         ← Kafka bağlantısı ve mesaj okuma
│   │   ├── data_feeder.py            ← Veri besleme katmanı
│   │   └── constants.py              ← Sabitler ve konfigürasyon
│   ├── analysis/
│   │   ├── risk_scorer.py            ← Katman 2: Ensemble risk skoru (0-100)
│   │   ├── threshold_checker.py      ← Anlık limit kontrolü
│   │   ├── trend_detector.py         ← Eğilim tespiti + ETA tahmini
│   │   ├── causal_evaluator.py       ← Fizik tabanlı nedensel kural motoru
│   │   ├── similarity_engine.py      ← Geçmiş olaylarla benzerlik arama
│   │   ├── nlg_engine.py             ← Katman 2.5: Türkçe açıklama üretici (NLG)
│   │   └── dlime_explainer.py        ← SHAP yedek açıklayıcı (DLIME)
│   ├── alerts/
│   │   └── alert_engine.py           ← Katman 3: Akıllı alarm motoru (cooldown + throttle)
│   └── ui/
│       └── web/                      ← Dashboard HTML/CSS/JS dosyaları
├── pipeline/
│   ├── ml_predictor.py               ← ML model tahmin motoru (Random Forest)
│   ├── context_builder.py            ← Gemini bağlam paketleyici
│   ├── llm_engine.py                 ← AI Usta Başı (Gemini Flash API)
│   ├── similarity_engine.py          ← Geçmiş olay benzerlik motoru
│   ├── model/                        ← Eğitilmiş model dosyaları
│   └── model_enhanced/               ← Geliştirilmiş model versiyonları
├── scripts/
│   ├── kafka_env.py                  ← Ortak Kafka bağlantı ayarları
│   ├── ml_tools/
│   │   ├── train_model.py            ← Model eğitim scripti
│   │   └── shap_analyzer.py          ← SHAP analiz aracı
│   └── data_tools/
│       ├── window_collector.py       ← Veri penceresi toplayıcı
│       ├── context_collector.py      ← Zengin bağlam toplayıcı
│       └── sync_limits_from_db.py    ← IK veritabanından limit senkronizasyonu
├── config/
│   └── limits_config.yaml            ← Makine limitleri, eşik değerleri, sistem ayarları
├── docs/
│   ├── causal_rules.json             ← Fizik tabanlı nedensel kurallar (v2)
│   ├── pipeline_mimarisi.md          ← Sistem mimarisi detayları
│   ├── pipeline_detay_katman[0-3].md ← Her katmanın teknik dokümanı
│   ├── PROJE_DURUM_RAPORU.md         ← Kapsamlı proje durum raporu
│   └── TODO_VE_TEKNIK_BORC.md       ← Yapılacaklar ve teknik borç takibi
├── tests/                            ← Birim ve entegrasyon testleri
├── sistem_baslat.sh                  ← Tek komutla sistemi başlat
├── sistem_durdur.sh                  ← Sistemi durdur
├── sistem_durum.sh                   ← Sistem durumunu kontrol et
├── requirements.txt                  ← Python bağımlılıkları
└── .env.example                      ← Ortam değişkenleri şablonu
```

---

## ⚙️ Ortam Değişkenleri

```bash
cp .env.example .env
```

| Değişken | Varsayılan | Açıklama |
|----------|-----------|----------|
| `KAFKA_BOOTSTRAP_SERVERS` | `10.71.120.10:7001` | Kafka broker adresi |
| `KAFKA_TOPIC` | `mqtt-topic-v2` | Kafka topic adı |
| `GEMINI_API_KEY` | — | AI Usta Başı için (yoksa sessizce devre dışı kalır) |
| `CONFIG_PATH` | `config/limits_config.yaml` | Limit konfigürasyon dosyası yolu |

> **Not:** `GEMINI_API_KEY` tanımlı olmasa bile sistem çalışmaya devam eder. Sadece AI Usta Başı devre dışı kalır; threshold, trend, ML ve fizik kuralları bağımsız çalışır.

---

## 🔌 Modülerlik ve Ölçeklenebilirlik

Codlean MES, sadece hidrolik presler için değil, **her türlü endüstriyel makine** için kullanılabilecek şekilde tasarlandı. Sisteme yeni bir makine veya üretim hattı eklemek için **tek satır kod yazmaya gerek yoktur.**

### Config-Driven Mimari

Yeni makine ekleme süreci:

| Adım | Ne Yapılır | Süre | Kod Değişikliği |
|------|-----------|------|-----------------|
| 1. Veri Toplama | Sensör listesi + geçmiş arızalar | 1-2 hafta | ❌ Yok |
| 2. Config Yazma | `limits_config.yaml` + `causal_rules.json` | 30 dakika | ❌ Yok |
| 3. Model Eğitimi | Yeni verilerle `train_model.py` çalıştır | 1-3 gün | ❌ Yok |
| 4. Dashboard | Otomatik kart oluşturma | 0 dakika | ❌ Yok |
| 5. Test | Doğrulama senaryoları | 2-3 gün | ❌ Yok |

**Geleneksel sistemlerde:** 6-9 ay + ₺500K  
**Codlean MES ile:** 2.5 hafta + ₺0

### Seri Bağlı Üretim Bandı Desteği

Sistem, tek makine izlemenin ötesinde **makineler arası nedensel zincirleri** de takip edebilir:

```
[Hammadde] → [Kesme] → [Bükme] → [Pres] → [Kaynak] → [Boyama] → [Ürün]
```

Makine 5'teki boya kalitesi düştüğünde, sistem `causal_rules.json` üzerinden geriye doğru tarama yaparak kök nedeni (örneğin Makine 1'deki bıçak aşınması) otomatik olarak tespit eder.

### Uygulanabilir Sektörler

| Sektör | Makine Tipleri | Sensörler |
|--------|---------------|-----------|
| **Otomotiv** | Robot kollar, CNC, Pres | Akım, titreşim, sıcaklık |
| **Gıda** | Mikser, Fırın, Paketleme | Nem, sıcaklık, hız |
| **Tekstil** | Dokuma, Boyama, Kesme | Gerilim, hız, sıcaklık |
| **İlaç** | Reaktör, Kurutucu, Tablet | Basınç, pH, nem |

---

## 🗺️ Yol Haritası

```
  Şubat 2026          Mart 2026            Nisan 2026           Mayıs 2026          Yaz 2026
  ─────────          ──────────           ───────────          ───────────         ──────────
  ┌──────────┐       ┌──────────────┐     ┌───────────────┐    ┌──────────────┐    ┌──────────────┐
  │ Kafka'dan │  ───▶ │ ML + Fizik   │ ──▶ │ Dashboard +   │ ─▶ │ Çoklu Ajan   │ ─▶ │ Yerel AI +   │
  │ veri okuma│       │ kuralları +  │     │ AI Usta Başı +│    │ sistemi +    │    │ sıfır API    │
  │           │       │ SHAP/DLIME   │     │ 6 makine canlı│    │ 5 uzman ajan │    │ maliyeti     │
  └──────────┘       └──────────────┘     └───────────────┘    └──────────────┘    └──────────────┘
    Hammadde            Altyapı             ★ Pilot Canlı        Uzman Sistem        Bağımsız Sistem
```

### Çoklu Ajan Sistemi (Sonraki Aşama)

Mevcut tek-LLM yapısını, her biri kendi alanında uzman **5 AI Ajanına** bölüyoruz:

| Ajan | Görev | Yöntem |
|------|-------|--------|
| 🔍 **Teşhis** | "Ne arıza var?" | Chain-of-Thought (CoT) Prompting |
| 🔎 **Kök Neden** | "Neden oldu?" | Nedensel çıkarım + geçmiş arama |
| ⏰ **Tahmin** | "Ne zaman duracak?" | Trend ekstrapolasyonu |
| 🔧 **Aksiyon** | "Ne yapılmalı?" | Önceliklendirilmiş eylem planı |
| 📋 **Rapor** | "Kim için, nasıl anlatılsın?" | 4 farklı çıktı modu |

---

## 📚 Dokümanlar

| Doküman | İçerik |
|---------|--------|
| [`docs/pipeline_mimarisi.md`](docs/pipeline_mimarisi.md) | Sistem mimarisi ve veri akışı |
| [`docs/pipeline_detay_katman0.md`](docs/pipeline_detay_katman0.md) | Veri doğrulama katmanı detayları |
| [`docs/pipeline_detay_katman1.md`](docs/pipeline_detay_katman1.md) | State store ve hafıza yönetimi |
| [`docs/pipeline_detay_katman2.md`](docs/pipeline_detay_katman2.md) | Analiz motoru, ML, AI Usta Başı |
| [`docs/pipeline_detay_katman3.md`](docs/pipeline_detay_katman3.md) | Alert engine ve alarm formatları |
| [`docs/causal_rules.json`](docs/causal_rules.json) | Fizik tabanlı nedensel kurallar |
| [`docs/TODO_VE_TEKNIK_BORC.md`](docs/TODO_VE_TEKNIK_BORC.md) | Proje durumu, yapılacaklar |
| [`docs/PROJE_DURUM_RAPORU.md`](docs/PROJE_DURUM_RAPORU.md) | Kapsamlı proje durum raporu |

---

## IK Veritabanından Limit Güncelleme

IK yeni CSV gönderdiğinde:

```bash
python3 scripts/data_tools/sync_limits_from_db.py \
  --typefile /path/to/machinetypedataitems.csv \
  --machinefile /path/to/machinedataitems.csv \
  --machines HPR001,HPR003,HPR004,HPR005 \
  --tst-machines TST001,TST002,TST003,TST004 \
  --dry-run
```

> HPR002 ve HPR006 Yatay Pres tipindedir — bunları ayrıca kontrol edin.

---

## ⚠️ Önemli Notlar

- `horitzonal_infeed_speed` yazımı **kasıtlıdır** — PLC cihazı bu ismi kullanıyor, değiştirmeyin.
- `state.json` dosyasını silmeyin — sistemin 2 saatlik hafızası buradadır.
- `GEMINI_API_KEY` yoksa AI Usta Başı sessizce devre dışı kalır, diğer tüm katmanlar çalışmaya devam eder.
- Sistem her katmanda bağımsız çalışır: ML yoksa threshold+trend, Gemini yoksa NLG template yeterlidir.
- Pipeline modülleri bağımsızdır: biri çökerse diğerleri etkilenmez.

---

## 📄 Lisans

Bu proje **Codlean** bünyesinde geliştirilmektedir. Tüm hakları saklıdır.

---

<p align="center">
  <strong>Codlean MES</strong> — Bozulmadan önle, durmadan üret. 🏭
</p>