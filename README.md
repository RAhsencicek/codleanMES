<div align="center">

# 🔥 CODLEAN MES 
### The Intelligent Nervous System for Manufacturing Execution

*Kusursuz Üretim İçin Kendi Kendini Dinleyen Yapay Zeka*

[![Python](https://img.shields.io/badge/Python-3.14-blue.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/Status-Production_Ready-success.svg)]()
[![System](https://img.shields.io/badge/Architecture-Hybrid_AI-orange.svg)]()

---

**Endüstriyel üretim hatları devasa, gürültülü ve karmaşıktır.**
Geleneksel OEE panelleri size sadece makinenin "bozulduğunu" veya "durduğunu" söyler — yani iş işten geçtikten sonra müdahale edersiniz.

**Codlean MES**, makine sensörlerinden (Basınç, Yağ Sıcaklığı, Titreşim, Tork vb.) saniyede fırlayan devasa verinin içine dalarak **"Yapay Zeka Destekli Bir Zaman Makinesi"** gibi çalışır. Sadece mevcut durumu göstermekle kalmaz; makinenin geçmişini ezberler, şimdisini denetler ve gelecekte ne zaman, hangi parçanın arıza vereceğini saniyeler öncesinden hesaplar.

</div>

<br>

## 📸 Canlı İzleme Terminali (Dashboard)

Codlean, veri karmaşasını şık, modern, göz yormayan ve "renklerle konuşan" dinamik bir arayüze dönüştürür. 

<div align="center">
  <img src="docs/images/dashboard-preview.png" alt="Codlean MES Dashboard" width="100%">
  <br>
  <i>Şekil 1: Canlı Arıza Tahmin Arayüzü (Hybrid AI Modu)</i>
</div>

<br>

Göz alıcı arayüzü terminalinizde canlı olarak test etmek için:
```bash
# Zaman Makinesi (Historical Replay) simülasyonunu başlatın:
PYTHONPATH=. python src/ui/dashboard_pro.py
```

---

## 🏗️ 4-Katmanlı Yapay Zeka Pipeline Mimarisi

Makineden fırlayan anlık, gürültülü (noisy) bir titreşim verisinin teknisyenin ekranına "anlamlı bir öneri" olarak düşmesi süreci sanatsal bir mimari gerektirir.

<div align="center">
  <img src="docs/images/Gemini_Generated_Image_4ztegx4ztegx4zte.png" alt="Codlean MES Architecture" width="100%">
  <br>
  <i>Şekil 2: 4-Katmanlı Hibrit Yapay Zeka Fabrikasyon Mimarisi</i>
</div>

<br>

Veri akışı şu teknik süzgeçlerden geçer:

```text
┌─────────────────────────────────────────────────────────┐
│                    KAFKA CONSUMER                       │
│          mqtt-topic-v2 @ 10.71.120.10:7001              │
│                                                         │
│  Her ~10 saniyede bir tüm makinelerin snapshot'ı gelir. │
│  Biz sadece okuruz, sisteme müdahale etmeyiz.           │
└───────────────────────┬─────────────────────────────────┘
                        │  Ham JSON mesajı
                        │  (string'ler, UNAVAILABLE'lar,
                        │   gecikmiş timestamp'lar dahil)
                        ▼
┌─────────────────────────────────────────────────────────┐
│     [YENİ] VERİ TOPLAYICI: window_collector.py          │
│                                                         │
│  Ham Kafka verisini analiz katmanından bağımsız dinler. │
│  Her saat başı normal operasyon profillerini kaydeder.  │
│  ML modeli için canlı eğitim verisini (live_windows)    │
│  oluşturarak hibrit yaklaşıma zemin hazırlar.           │
└───────────────────────┬─────────────────────────────────┘
                        │  Ham JSON mesajı devam eder
                        ▼
┌─────────────────────────────────────────────────────────┐
│         KATMAN 0: VERİ GİRİŞ & DOĞRULAMA                │
│                                                         │
│  "Bu veri güvenilir mi, işlenebilir mi?"                │
│                                                         │
│  • Schema kontrolü  → gerekli alanlar var mı?           │
│  • UNAVAILABLE → None dönüşümü                          │
│  • Timestamp kontrolü → veri 5 dk'dan eski mi?          │
│  • String → float dönüşümü (result alanı hep string)    │
│  • Spike filtresi → sensör aniden 10x değer attı mı?    │
│  • Startup mask → makine yeni açıldı mı? (60 dk)        │
│                                                         │
│  ÇIKIŞ: Temiz, tip-güvenli, işlenmeye hazır veri        │
└───────────────────────┬─────────────────────────────────┘
                        │  Doğrulanmış veri paketi
                        ▼
┌─────────────────────────────────────────────────────────┐
│         KATMAN 1: STATE STORE (Bellek)                  │
│                                                         │
│  "Bu makinenin geçmişini ve bağlamını biliyorum."       │
│                                                         │
│  • Ring buffer: her sensörün son 720 değeri (2 saat)    │
│  • EWMA: canlı güncellenen ortalama ve standart sapma   │
│  • Confidence: veri kalitesine göre 0-1 güven skoru     │
│  • Boolean takibi: "bu filtre kaç saattir kirli?"       │
│  • Checkpoint: 5 dk'da bir atomik JSON'a yedek          │
│                                                         │
│  ÇIKIŞ: Her sensörün trend hesabı için gereken geçmiş   │
└───────────────────────┬─────────────────────────────────┘
                        │  Zenginleştirilmiş durum verisi
                        ▼
┌─────────────────────────────────────────────────────────┐
│         KATMAN 2: ANALİZ MOTORU                         │
│                                                         │
│  "Bu makinede risk var mı? Varsa ne kadar acil?"        │
│                                                         │
│  ┌──────────────────────┐  ┌─────────────────────────┐  │
│  │   ThresholdChecker   │  │     TrendDetector       │  │
│  │                      │  │                         │  │
│  │  Anlık değeri config │  │  Son 30 ölçümün eğimini │  │
│  │  min/max ile karşı-  │  │  hesaplar. Eğim pozitif │  │
│  │  laştırır.           │  │  ve güçlüyse (R²>0.7)   │  │
│  │                      │  │  limite kaç saat kaldı- │  │
│  │  %85 → ORTA uyarı    │  │  ğını tahmin eder.      │  │
│  │  %100 → YÜKSEK       │  │                         │  │
│  │  %110 → KRİTİK       │  │  Startup phase'de çalış-│  │
│  │                      │  │  maz (ısınma maskelenir)│  │
│  └──────────┬───────────┘  └────────────┬────────────┘  │
│             └──────────────┬────────────┘               │
│                            ▼                            │
│                     RiskScorer                          │
│                                                         │
│         İki sinyali confidence ile ağırlıklandırıp      │
│         0-100 arası tek bir risk skoru üretir.          │
│                                                         │
│  ÇIKIŞ: RiskEvent (skor, neden, ETA, hangi sensör)      │
└───────────────────────┬─────────────────────────────────┘
                        │  Risk skoru ≥ eşik ise devam
                        │  Risk skoru < eşik ise atla
                        ▼
┌─────────────────────────────────────────────────────────┐
│         KATMAN 3: ALERT ENGINE                          │
│                                                         │
│  "Teknisyen ne görüyor? Ne zaman, nasıl bildirilecek?"  │
│                                                         │
│  • Throttle kontrolü: 30 dk'da 1 alert / makine         │
│  • Severity belirleme: DÜŞÜK/ORTA/YÜKSEK/KRİTİK         │
│  • Açıklama üretimi: "Neden? Hangi sensör? Ne öneriyiz?"│
│  • DB kaydı: alert_log tablosuna sensör değerleriyle    │
│  • Terminal çıktısı: renkli, okunabilir panel           │
│                                                         │
│  ÇIKIŞ: Teknisyen ekranı + PostgreSQL kaydı             │
└─────────────────────────────────────────────────────────┘
```

---

## ⚡ Sistemi Benzersiz Kılan Özellikler

- **Maliyet-Farkındalıklı (Cost-Aware) Tahminleme:** Makinelerin duruş maliyeti, onarım maliyetinden katbekat yüksektir. Algoritma **Recall** (Duyarlılık) oranını maksimize eder; asgari bir şüphede dahi teknik ekibi tetikler, böylece potansiyel arızalar şansa bırakılmaz.
- **Kayıpsız Zaman Makinesi (Historical Replay Engine):** Fabrika lokal ağ bağlantısını veya Kafka erişimini kaybetse dahi, sistem kendi içindeki *Event Loop* motoru sayesinde gigabytelarca geçmiş *violation_log.json* verisini saniye saniye işleyerek sahte olmayan, kanıtlanmış bir test & simülasyon altyapısı sunar.

---

## ⚙️ Geliştirici Kaynakları

Daha derinlemesine teknik detaylar, sınıf yapıları, XGBoost model eğitim matrisleri ve veri hazırlık (preprocessing) pipeline analizleri için [Geliştirici Dokümantasyonunu (PROJECT_DETAILS.md)](./PROJECT_DETAILS.md) inceleyebilirsiniz.
