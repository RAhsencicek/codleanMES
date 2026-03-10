# 🔥 CODLEAN MES 
**The Intelligent Nervous System for Manufacturing Execution**

> *"Kusursuz Üretim İçin Kendi Kendini Dinleyen Yapay Zeka"*

Endüstriyel üretim hatları devasa, gürültülü ve karmaşıktır. Geleneksel OEE panelleri size sadece makinenin "bozulduğunu" söyler — yani iş işten geçtikten sonra. 

**Codlean MES**, makine sensörlerinden (Basınç, Yağ Sıcaklığı, Titreşim, Tork vb.) saniyede yüzlerce kez fırlayan anlık verilerin içine dalarak **"Yapay Zeka Destekli Bir Zaman Makinesi"** gibi çalışır. Sadece mevcut durumu göstermekle kalmaz; makinenin geçmişini ezberler, şimdisini denetler ve gelecekte ne zaman, hangi parçanın arıza vereceğini (*ETA: Estimated Time of Arrival*) saniyeler öncesinden hesaplar.

---

## 🌟 Neden Eşsiz? (The Peerless Architecture)

Piyasadaki standart "Kestirimci Bakım" (Predictive Maintenance) çözümleri çoğunlukla tek boyutludur. Codlean ise veriyi **4 farklı Akıl Katmanında** işleyerek bir "Dijital İkiz (Digital Twin)" bilinci yaratır:

### 1. Hiper-Hassas Hibrit Risk Motoru (Hybrid System)
Endüstri 4.0'da yapay zekanın en büyük problemi "Yanlış Alarm (False Positive)" korkusuyla gerçeği kaçırmasıdır. 
Codlean bu sorunu ustaca çözer: 
- **Teknisyen Aklı (%100 Kesin):** Kural tabanlı (Rule-based) limit aşımlarını kesin arıza olarak yakalar. 
- **YZ Aklı (Olası Tehlike):** ML (Random Forest/XGBoost) modelleri ile sınırları aşmamış ama *ivmelenen* mikroskobik trendleri 30-60 dakika önceden sezer.

### 2. Maliyet Odaklı (Cost-Aware) Refleks
Makinelerin patlaması, durmasından daha maliyetlidir. Sistem algoritması, *Recall* öncelikli çalışarak asgari şüphede bile teknik ekibi en açık ve net insan diliyle (Açıklanabilir AI) uyarır. (Örn: `🚨 Makineyi durdurun, yağ pompası basınç kaybediyor!`)

### 3. Zaman Makinesi Simülasyonu (Historical Replay) ⏳
Kafka ağ bağlantınız kopsa bile Codlean kör olmaz. Kendi içindeki eşsiz **Replay Engine** sayesinde, aylar önce yaşanmış devasa gerçek arıza loglarını (`violation_log.json`) sahte simülasyonlara başvurmadan saniye saniye canlı bir şekilde Dashboard'una basar ve sistem stres testine devam eder.

---

## 📸 Canlı İzleme Terminali (Dashboard)

Codlean, veri karmaşasını şık, modern, göz yormayan ve "renklerle konuşan" dinamik bir arayüze dönüştürür. 

🚨 **[Buraya Sistemin Ekran Görüntüsü Gelecek]** 🚨
*(Lütfen terminalde çalıştırdığınız sistemin ekran görüntüsünü `docs/images/dashboard-preview.png` dizinine kaydediniz. Görmek için kodu çalıştırın!)*

![Codlean MES Dashboard Prototype](docs/images/dashboard-preview.png)

```bash
# Efsaneyi kendi bilgisayarınızda canlı izlemek için:
PYTHONPATH=. python src/ui/dashboard_pro.py
```

---

## 🏗️ 4-Katmanlı Yapay Zeka Pipeline (Fabrikasyon Süreci)

Ham veri teknisyenin ekranına düşene kadar şu katı denetimlerden geçer:

```mermaid
flowchart TD
    %% Styling
    classDef kafka fill:#1A1A1A,stroke:#FF5722,stroke-width:2px,color:#FFF
    classDef layer0 fill:#E1F5FE,stroke:#0288D1,stroke-width:2px,color:#000
    classDef layer1 fill:#FFF3E0,stroke:#F57C00,stroke-width:2px,color:#000
    classDef layer2 fill:#FCE4EC,stroke:#C2185B,stroke-width:2px,color:#000
    classDef layer3 fill:#E8F5E9,stroke:#388E3C,stroke-width:2px,color:#000
    classDef external fill:#263238,stroke:#B0BEC5,stroke-width:2px,color:#FFF

    %% Data Source
    KAFKA[("📦 Kafka Stream <br> (Saniyede Yüzlerce Ham JSON)")]:::kafka

    %% Layers
    L0["🟢 Katman 0: Ağ Geçidi (Gateway)<br>Gürültülü, bayat veya defolu sinyaller<br>kapıdan çevrilir."]:::layer0
    
    L1["🟡 Katman 1: Hafıza (State Store)<br>Son 12 saatin bağlamı (Context) ve<br>hareketli ortalamalar (EWMA) ezberlenir."]:::layer1
    
    L2["🔴 Katman 2: Karar Motoru (AI Engine)<br>Eşik kontrolü (Threshold) ve ML modelleri<br>ile çoklu sensör korelasyonu (Risk Skoru) saptanır."]:::layer2
    
    L3["🟢 Katman 3: İletişim (Alert Engine)<br>Art arda gelen yorucu alarmlar süzülür (Throttle).<br>İnsan dilinde eyleme dönüştürülür."]:::layer3

    OUT[/"💻 Dinamik Dashboard<br>& Postgres Veritabanı"/]:::external

    KAFKA --> L0 --> L1 --> L2 --> L3 --> OUT
```

---

## ⚙️ Hemen Başlayın

Bu proje, bir "Hello World" kodlamasından ziyade, dev endüstriyel fabrikalarda doğrudan devreye alınmak üzere (**Production-Ready**) özel olarak inşa edilmiştir ve %100 Python tabanlı modüler bir yapı sunar.

Sistemin kurulum rehberi, derinlemesine geliştirici mimarisi, class hiyerarşileri ve detaylı ML eğitim raporları için [Geliştirici Dokümantasyonunu (PROJECT_DETAILS.md)](./PROJECT_DETAILS.md) inceleyebilirsiniz.
