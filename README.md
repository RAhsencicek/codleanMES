# 🚀 CODLEAN MES — YZ Destekli Kestirimci Bakım & Üretim Yürütme Sistemi

> *"Kusursuz Üretim İçin Kendi Kendini Dinleyen Yapay Zeka"*

Codlean MES, endüstriyel tesisler için geliştirilmiş, geleneksel eşik değer (rule-based) sistemlerinin katı yapısını **Makine Öğrenimi (ML)** algoritmalarının öngörücü gücüyle harmanlayan **eşsiz bir hibrit mimaridir**. Pazardaki diğer standart OEE (Genel Ekipman Etkinliği) veya IoT analiz ekranlarının aksine, Codlean sadece "ne olduğunu" göstermekle kalmaz; arka plandaki canlı veri akışını işleyerek "ne olacağını, ne zaman olacağını ve nasıl önleneceğini" saniyeler içinde hesaplar.

---

## 🌟 Neden Eşsiz? (Peerless Architecture)

Piyasadaki standart kestirimci bakım çözümleri genellikle tek boyutlu çalışır (ya sadece kural tabanlı alarm verirler ya da sadece ML tahmini yaparlar). Codlean MES ise veriyi **4 farklı filtre ve akıl katmanında** işleyerek fabrikada adeta bir "Dijital İkiz (Digital Twin)" bilinci yaratır:

1. **Hiper-Hassas Hibrit Algılama**: Teknisyenin tecrübesine dayalı (%100 Kesin) kural limitleri ile Yapay Zeka öngörüsünü (Olası Arıza Algısı) tek potada ustaca harmanlar.
2. **Kayıpsız Zaman Makinesi (Historical Replay)**: Gerçek Kafka sunucusuyla olan bağlantı dahi kopsa, sistem geçmişte kaydedilmiş devasa arıza loglarını (*violation_log.json*) saniye saniye simüle edebilen benzersiz ve izole bir stres-test altyapısına sahiptir.
3. **Maliyet Odaklı Karar Mekanizması (Cost-Aware Threshold)**: Endüstri 4.0'ın en büyük problemi olan "yanlış alarm verme korkusuyla gerçek arızaları kaçırma" handikapını yüksek hassasiyet (Recall) stratejisiyle çözer. Sistemin ana odağı hiçbir tehlikeyi şansa bırakmamaktır.

---

## 🏗️ Hibrit Pipeline Mimarisi

Makine sensörlerinden (Basınç, Yağ Sıcaklığı, Titreşim, Tork vb.) saniyede yüzlerce kez fırlayan veriler, teknisyenin ekranına anlamlı bir öneri olarak düşmeden önce aşağıdaki **4 aşamalı fabrikasyon sürecinden (Pipeline)** geçer:

```mermaid
flowchart TD
    %% Styling
    classDef kafka fill:#f96,stroke:#333,stroke-width:2px,color:#000
    classDef layer0 fill:#e1bee7,stroke:#8e24aa,stroke-width:2px,color:#000
    classDef layer1 fill:#bbdefb,stroke:#1e88e5,stroke-width:2px,color:#000
    classDef layer2 fill:#ffcc80,stroke:#f57c00,stroke-width:2px,color:#000
    classDef layer3 fill:#ffcdd2,stroke:#e53935,stroke-width:2px,color:#000
    classDef db fill:#c8e6c9,stroke:#43a047,stroke-width:2px,color:#000
    classDef external fill:#cfd8dc,stroke:#546e7a,stroke-width:2px,color:#000

    %% Data Source
    KAFKA[("📦 Kafka <br> mqtt-topic-v2 <br> (Ham JSON Mesajları)")]:::kafka

    %% Katman 0
    subgraph K0 ["🟢 KATMAN 0: Veri Girişi & Doğrulama ('Güvenlik Görevlisi')"]
        direction TB
        V1{"Dil Bilgisi Kapısı<br>(Virgül -> Nokta)"}
        V2{"Boş Veri Kapısı<br>(UNAVAILABLE Çöpe)"}
        V3{"Bayat Veri Kapısı<br>(Gecikme > 5 dk)"}
        V4{"Elektrik Sıçraması<br>(Spike > 5 Standart Sapma)"}
        V1 -->|Geçti| V2
        V2 -->|Geçti| V3
        V3 -->|Taze| V4
    end
    class K0 layer0

    KAFKA -->|Her 10 sn'de bir| V1
    V2 -.->|Silinir| TRASH1((Çöp))
    V3 -.->|Stale Data| LOG1((Log))
    V4 -.->|Spike| LOG1

    %% Katman 1
    subgraph K1 ["🟡 KATMAN 1: Hafıza Merkezi (State Store)"]
        direction TB
        S1[("Ring Buffer<br>(Son 720 Ölçüm ezberlenir)")]
        S2["Hareketli Ortalama (EWMA)<br>(Hızlı güncel ortalama)"]
        S3["Tarihsel Bağlam<br>(Veri kalitesi ve süre takibi)"]
        S1 --- S2 --- S3
    end
    class K1 layer1

    V4 -->|Temiz Veri İşlenir| K1
    K1 -.->|Her 5 Dk Atomik Kayıt| STATE_JSON[("💾 state.json<br>(Elektrik Kesintisi Koruması)")]:::db

    %% Katman 2
    subgraph K2 ["🟠 KATMAN 2: Analiz Motoru"]
        direction TB
        A1["Threshold Checker<br>(Kural Tabanlı Kontrol)<br>Anlık değer config limitini aştı mı?"]
        A2["Trend Detector<br>(Doğrusal Regresyon)<br>Sınır aşılmadı ancak ivme ne yönde?"]
        A3["ML Predictor<br>(Random Forest)<br>Çoklu sensör korelasyonu ile risk tahmini"]
        
        A1 --- ENSEMBLE
        A2 --- ENSEMBLE
        A3 --- ENSEMBLE
        
        ENSEMBLE{"Risk Scorer (Ensemble)<br>Sinyalleri ağırlıklandırarak birleştirir<br>ve tek bir Risk Skoru (0-100) üretir."}
    end
    class K2 layer2

    K1 -->|Tarihçe + Anlık Veri| A1
    K1 -->|Tarihçe + Anlık Veri| A2
    K1 -->|Tarihçe + Anlık Veri| A3

    %% Katman 3
    subgraph K3 ["🔴 KATMAN 3: İletişim Merkezi (Alert Engine)"]
        direction TB
        AL1{"Alarmı Boğma (Throttle)<br>Son 30 dk'da aynı makineye<br>alarm verdik mi?"}
        AL2["İnsan Diline Çevirme<br>(Açıklanabilir AI Metni: 'Neden? Ne yapmalı?')"]
        
        AL1 -->|Hayır| AL2
        AL1 -.->|Evet| SUS((Sessiz Kal))
    end
    class K3 layer3

    ENSEMBLE -->|Risk Skoru > Eşik Seviyesi| AL1

    %% Outputs
    AL2 --> OUT_TERM[/"💻 Teknisyen Terminali<br>(Renkli, Net Uyarı Paneli)"/]:::external
    AL2 --> OUT_DB[("🗄️ PostgreSQL<br>(alert_log tablosuna kalıcı kayıt)")]:::db

```

### 🧩 Mimari Katmanların Detaylı İncelemesi

*   **🟢 KATMAN 0 (Veri Girişi & Doğrulama)**: Sistemin "Güvenlik Görevlisidir". Sensörden gelen gürültülü (noisy), veri tabanı uyumsuz (spike/anomaly) veya kopuk statik mesajları daha kapıdayken süzer. Sisteme sadece analiz edilmeye değer, "temiz ve taze" kanın pompalanmasını garanti eder.
*   **🟡 KATMAN 1 (Hafıza Merkezi - State Store)**: Codlean sadece saniyelik değerlere bakarak yanılgıya düşmez. Önündeki son 12 saatin bağlamını (context) ve hareketli ortalamalarını (EWMA) mikro-saniyeler içinde hesaplayarak ezberler. Elektrik kesintisi veya sistem yeniden başlatılması durumunda disk tabanlı koruma (state.json) ile hafızasını kaybetmez.
*   **🟠 KATMAN 2 (Analiz Motoru - Hybrid AI)**: Uygulamanın beynidir. Sadece limit aşımını (Threshold Checker) kontrol edip geçmez; makine öğrenimi modelleri (XGBoost/Random Forest) ile çoklu sensör korelasyonunu algılayarak, gözle görülemeyen teknik yıpranmaları sezer. *"Limitlere henüz ulaşılmadı ancak ivmelenme hızına bakılırsa 30 dakika içinde ana valf hatası yaşanacak"* seviyesinde derin bir felsefeyle rapor üretir.
*   **🔴 KATMAN 3 (İletişim & Alert Engine)**: Teknisyene ve üretim şefine teknolojik yorgunluk (Alert Fatigue) yaşatmamak için kurgulanmıştır. Peş peşe gelen onlarca tehlike sinyalini filtreler, sınıflandırır ve kanıtlanmış anomalileri *"İnsan Diliyle Açıklanabilir Çözümler"* şeklinde (Örn: `🚨 Makineyi durdurun, yağ pompası basınç kaybediyor!`) sunar.

---

## 📍 Geliştirme Yol Haritası (Milestone Checkpoints)

Proje sürekli evrilen bir Ar-Ge kültürünün ürünüdür:

1. **Checkpoint 1.0**: Temel Kafka Consumer (dinleyici) ve State Store hafıza mantığının kurgulanması.
2. **Checkpoint 2.0**: İleri düzey Random Forest algoritmalarının devasa bir geçmiş veri seti üzerinden (`ml_training_data.csv`) eğitilmesi ve çekirdek yapıya entegrasyonu.
3. **Checkpoint 3.0**: Standart spagetti kodların kırılıp bağımsız bir endüstri standardına (src/, tests/, docs/, scripts/) refactor edilmesi. Ergonomik 3-Bölmeli Dinamik GUI inşası.
4. **Checkpoint 4.0 (GÜNCEL)**: **Historical Replay Zaman Makinesi** ile sahte (mock) simülasyonların sistemden kazınması. Hibrit AI Risk motorunun tam entegrasyonu ve siber güvenlik/network kısıtlarına rağmen "Canlı Test (Production-Ready Live Simulation)" senaryosunun hayata geçirilmesi.

---

## 🛠️ Nasıl Çalıştırılır?

Tek bir endüstriyel komut ile sistemin zekasını canlı olarak test edebilirsiniz:

```bash
# Bağımlılık dizinlerini tanıması için PYTHONPATH kullanılarak Dashboard simülasyonu başlatılır:
PYTHONPATH=. python src/ui/dashboard_pro.py
```
*(Komut çalıştırıldığında sistem saniyeler içinde binlerce satırlık geçmiş arıza verilerini okumaya başlar ve terminalde şeffaf bir yapay zeka deneyimi sunar.)*
