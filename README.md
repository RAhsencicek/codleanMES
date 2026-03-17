<div align="center">

# 🔥 CODLEAN MES 
### The Intelligent Nervous System for Manufacturing Execution

*Kusursuz Üretim İçin Kendi Kendini Dinleyen Yapay Zeka*

[![Python](https://img.shields.io/badge/Python-3.14-blue.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/Status-Pilot_Phase-yellow.svg)]()
[![System](https://img.shields.io/badge/Architecture-Hybrid_AI-orange.svg)]()

---

**Endüstriyel üretim hatları devasa, gürültülü ve karmaşıktır.**
Geleneksel OEE panelleri size sadece makinenin "bozulduğunu" veya "durduğunu" söyler — yani iş işten geçtikten sonra müdahale edersiniz.

**Codlean MES**, makine sensörlerinden (Basınç, Yağ Sıcaklığı, Titreşim, Tork vb.) saniyede fırlayan devasa verinin içine dalarak **"Yapay Zeka Destekli Bir Zaman Makinesi"** gibi çalışır. Sadece mevcut durumu göstermekle kalmaz; makinenin geçmişini ezberler, şimdisini denetler ve gelecekte ne zaman, hangi parçanın arıza vereceğini saniyeler öncesinden hesaplar.

</div>

<br>

## 🚦 Sistem Durumu (Gerçek Zamanlı)

| Bileşen | Durum | Açıklama | Son Güncelleme |
|---------|-------|----------|----------------|
| **Rule-Based Alert** | ✅ Canlı | Katı eşik sınırları aktif | 2026-03-13 |
| **ML Pre-Fault** | ✅ Model eğitildi | XGBoost çalışıyor | 2026-03-06 |
| **SHAP XAI** | ✅ Entegre | Lazy evaluation: Risk > %50'de çalışır (~100ms) | 2026-03-13 |
| **NLG Motor** | ✅ Canlı | Türkçe açıklamalar üretiliyor | 2026-03-13 |
| **DLIME Fallback** | ✅ Sigorta | XGBoost dışı modeller için backup | 2026-03-13 |
| **Physics-Informed (Faz 1.5)** | 🚧 Aktif | Operating Minutes + Hydraulic Strain | 2026-03-20 |
| **AI Usta Başı (Context)** | ✅ Faz 1.5 | Causal JSON kuralları (Neo4j iptal) | 2026-03-20 |
| **Data Collection** | ✅ Otomatize | `hpr_monitor_fixed.py` içinde entegre | 2026-03-13 |

---

## 🚀 Hızlı Başlangıç (Quick Start)

Yeni bir geliştirici olarak projeyi derhal ayağa kaldırmak için:

```bash
# 1. Depoyu klonladıktan veya indirdikten sonra proje dizinine geçin:
cd kafka

# 2. Virtual Environment oluşturun ve aktif edin:
python3 -m venv venv
source venv/bin/activate

# 3. Bağımlılıkları (requirements) kurun (Opsiyonel: SHAP dahil):
pip install -r requirements.txt
pip install shap matplotlib

# 4. Veri Toplama Otomatiktir
# hpr_monitor_fixed.py başlatıldığında otomatik olarak Kafka'dan veri toplar
# Ayrı bir servis başlatmaya gerek yok

# 5. HPR (Hidrolik Pres) Canlı İzleme Terminalini (App) Başlatın:
PYTHONPATH=. python3 src/app/hpr_monitor_fixed.py
```

Makine izleme ve uyarı dökümünü terminalden göreceksiniz. Arıza modellerinin tahminini `data/ml_training_data.csv` oluşturucusundan takip edebilirsiniz.

---

## 📸 Canlı İzleme Terminali (Dashboard)

Codlean, veri karmaşasını şık, modern, göz yormayan ve "renklerle konuşan" dinamik bir arayüze dönüştürür. Sayı kalabalığı değil, renkli **eylem çağrıları** (Call-to-Action) sunar.

<div align="center">
  <img src="docs/images/dashboard-preview.png" alt="Codlean MES Dashboard" width="100%">
  <br>
  <i>Şekil 1: Canlı Arıza Tahmin Arayüzü (Hybrid AI Modu)</i>
</div>

### 🧩 Dashboard Neyi Anlatıyor? (Modül Açıklamaları)

Arayüzümüz, teknisyenin bilişsel yükünü (cognitive load) sıfıra indirmek için özel tasarlandı:
- **Ana Sensör Barları (Sol Üst):** Makinenin anlık Basınç, Yağ Sıcaklığı ve Titreşim değerlerini gösterir. Yeşil renk optimum seviyeyi, sarı limitlere yaklaşmayı, kırmızı ise tehlikeyi belirtir.
- **🤖 AI-Analiz Metni (Ortadaki Beyaz Metin):** Sistemin karar motorudur. Sensörler yeşil bile olsa, yapay zeka arka planda mikroskobik bir ivmelenme görüyorsa burada teknisyeni insan diliyle doğrudan uyarır: *"Valf sınır değerlere yaklaşıyor, makineyi rölantiye alın."*
- **Risk Durumu & Skoru (0-100):** Tüm sensör parametrelerinin ve yapay zeka tahminlerinin (Ensemble) tek bir skora indirgenmiş halidir. Skor %85'i geçerse sistem otomatik olarak alarm üretir.
- **ETA (Estimated Time of Arrival):** Yapay zekanın "Eğer bu ivme böyle devam ederse X dakika sonra makine kesin arıza verecek" diyerek hesapladığı geri sayım sayacıdır.
- **Olay Akışı Paneli (En Alt):** Fabrikadaki tüm makinelerdeki "Yapay Zeka Uyarılarını" ve "Olayları" (Örn: Zaman makinesi simülasyonu başlıyor) kronolojik bir log ekranı gibi teknisyenin önüne serer.

Göz alıcı arayüzü terminalinizde canlı olarak test etmek için:
```bash
# Zaman Makinesi (Historical Replay) simülasyonunu başlatın:
PYTHONPATH=. python src/ui/dashboard_pro.py
```

---

## 🏗️ 4-Katmanlı Yapay Zeka Pipeline Mimarisi

Sistemimiz sıradan bir veri okuyucu değildir. Makineden fırlayan anlık, gürültülü (noisy) bir titreşim verisinin teknisyenin ekranına "anlamlı bir öneri" olarak düşmesi süreci sanatsal bir endüstri mühendisliği gerektirir. 

<div align="center">
  <img src="docs/images/Gemini_Generated_Image_4ztegx4ztegx4zte.png" alt="Codlean MES Architecture" width="100%">
  <br>
  <i>Şekil 2: 4-Katmanlı Hibrit Yapay Zeka Fabrikasyon Mimarisi</i>
</div>

Pipeline mimarimiz, Kafka'dan ham veriyi okuyup teknisyene anlamlı bir uyarı üretene kadar dört ana katmandan (+1 Bağlam Katmanı) geçirir. Her katman bir öncekinden temizlenmiş ve zenginleştirilmiş veri alır. Veri akışı şu teknik süzgeçlerden geçer:

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
│  ML modeli için canlı eğitim verisini (live_windows)    │
│  oluşturarak hibrit yaklaşıma zemin hazırlar.           │
└───────────────────────┬─────────────────────────────────┘
                        │  Ham JSON mesajı devam eder
                        ▼
┌─────────────────────────────────────────────────────────┐
│         KATMAN 0: VERİ GİRİŞ & DOĞRULAMA                │
│                                                         │
│  "Bu veri güvenilir mi, işlenebilir mi?"                │
│  ÇIKIŞ: Temiz, tip-güvenli, işlenmeye hazır veri        │
└───────────────────────┬─────────────────────────────────┘
                        │  Doğrulanmış veri paketi
                        ▼
┌─────────────────────────────────────────────────────────┐
│         KATMAN 1: STATE STORE (Bellek)                  │
│                                                         │
│  "Bu makinenin geçmişini ve bağlamını biliyorum."       │
│  ÇIKIŞ: Her sensörün trend hesabı için gereken geçmiş   │
└───────────────────────┬─────────────────────────────────┘
                        │  Zenginleştirilmiş durum verisi
                        ▼
┌─────────────────────────────────────────────────────────┐
│         KATMAN 2: ANALİZ MOTORU                         │
│                                                         │
│  "Bu makinede risk var mı? Varsa ne kadar acil?"        │
│  ÇIKIŞ: RiskEvent (skor, neden, ETA, hangi sensör)      │
└───────────────────────┬─────────────────────────────────┘
                        │  Risk skoru ≥ eşik ise devam
                        ▼
┌─────────────────────────────────────────────────────────┐
│         [YENİ] KATMAN 2.5: BAĞLAM MOTORU (USTA BAŞI)    │
│                                                         │
│  "Bu arızanın KÖK NEDENİ (Root Cause) nedir?"           │
│  ÇIKIŞ: Nedensel Açıklama (Örn: Termal Stres)           │
└───────────────────────┬─────────────────────────────────┘
                        │  Zenginleştirilmiş Bağlam
                        ▼
┌─────────────────────────────────────────────────────────┐
│         KATMAN 3: ALERT ENGINE                          │
│                                                         │
│  "Teknisyen ne görüyor? Ne zaman, nasıl bildirilecek?"  │
│  ÇIKIŞ: Teknisyen ekranı + PostgreSQL kaydı             │
└─────────────────────────────────────────────────────────┘
```

### 🟢 KATMAN 0: Ağ Geçidi & Güvenlik Görevlisi (Gateway Layer)
Bu katman **güvenlik görevlisi** gibi davranır. Sensörlerden fırlayan devasa Kafka verisi ana sisteme ulaşmaya çalışırken filtrelenir. Eğer veri bozuksa yapay zeka yanlış kararlar alabilir, bu nedenle katı kurallar uygulanır:
- **Format ও Dil Bilgisi Kontrolü:** Kimi makine ondalık sayıları virgülle (`37,02`) kimi noktayla (`37.02`) gönderir. Sistem anında bunları standartlaştırır.
- **Kopuk Sensör Reddi:** Makine kapalıysa gelen `UNAVAILABLE` stringini engeller, programın çökmesini (Crash) önler.
- **Bayat Veri (Stale Data) Engeli:** Ağ pingi gecikirse 5 dakika geç gelen paketler zaman çizelgesini bozmamak adına trend hesaplarına katılmaz.
- **Spike Filtresi:** Elektrik sıçramaları gibi 5 standart sapmalık (*5-sigma*) anlık voltaj pikleri silinir ki ML modelleri bunu gerçek bir "arıza" sanmasın.

### 🟡 KATMAN 1: Kısa Süreli Hafıza Merkezi (State Store)
Yapay Zeka izole 1 saniyelik değerlere bakarak karar veremez. "Şu an sıcaklık 60 derece" demek tek başına anlamsızdır. Dün nasıldı?
- **Ring Buffer (Kayan Pencere):** Tüm makine sensörlerinin son 12 saatteki (veya son 720 kayıt) ölçümlerini RAM üzerinde (anlık bellekte) milisaniyeler içinde saklar ve ezberler.
- **Hareketli Ortalama (EWMA):** Zaman serilerindeki anlık gürültüleri filtreleyip eylemsizlik trendini hesaplar. Sıcaklığın "yönünü" bulur.
- **Disk Koruması (State Persistence):** Fabrikada elektrik kesilip sistem aniden kapansa dahi `state.json` üzerinden tüm hafızasını (son 12 saatlik geçmişi) saniyede geri yükler. Uçak kara kutusu gibi çalışır.

### 🔴 KATMAN 2: Karar Motoru & Hibrit Zeka (AI Engine)
Uygulamanın ana beynidir. İki bağımsız otonom sistemi (İnsan Aklı ve Makine Öğrenimi) tek potada (Ensemble) eritir:
- **Kural Tabanlı Threshold (%100 Kesinlik):** Basınç 150 Bar sınırını aştı ise bu teknisyen onaylı "kesin" bir arızadır. Şansa veya makine öğrenimi tahminine bırakılmaz; sistem derhal en yüksek perdeden müdahale emri verir.
- **Makine Öğrenimi (ML Predictor - Random Forest/XGBoost):** Değerler henüz 120 Bar gibi normal sınırlardadır. Ancak model; Tork, Titreşim ve Sıcaklık parametrelerindeki eş zamanlı ufak dalgalanmaları ve kimsenin göremediği "mikro ivmelenmeleri" saptayarak: *"Mevcut ivme korunursa ana valf 45 dakika içinde arızaya geçecek"* (Pre-Fault) öngörüsünü üretir.
- **Ensemble Risk Scorer:** İki sistemin çıktılarını (Kesin Kural ve YZ Tahmini) ağırlıklandırarak harmanlar ve 0-100 arasında net bir risk skoru basar.

### 🧠 [YENİ] KATMAN 2.5: Bağlam Motoru & Nedensellik (AI Usta Başı)
Sadece min/max limitlerini izleyen alarm sistemini **makineler arası "neden-sonuç" ilişkilerini (bağlam/context) açıklayan** canlı bir asistana dönüştüren merkezdir.
- **Kök Neden Analizi:** "Ana basınç son 2 saattir yüksek seyrettiği için yağ sıcaklığı arttı ve termal strese yol açtı" gibi açıklanabilir (Explainable AI) bağlamlar kurar.
- **Dinamik Kural & ML Entegrasyonu:** Hibrit yaklaşımla beslenir; hem usta sezgilerini yansıtan "Bağlam Sözlüğü" kurallarını barındırır, hem de "Termal Stres", "Valf Kaçağı" gibi olay paketleriyle eğitilmiş (Labeling) özel makine öğrenimi mantıklarını içerir.

### 🟢 KATMAN 3: İletişim & Alert Engine
Teknisyene giden son kapıdır. Bu katman "Açıklanabilir Yapay Zeka" (XAI) ilkesini benimser.
- **Alarm Boğma (Throttle):** "Teknoloji Yorgunluğunu (Alert Fatigue)" engellemek adına aynı makine için saniyede 10 kez alarm üretip insanları paniğe sokmak yerine; 30 dakikalık periyotlarla tok ve net uyarılar geçer.
- **Actionable AI (Eyleme Dönüştürülebilir Çıktı):** Ekrana `Hata Kodu 404` veya `Skor %84` şeklinde anlamsız çıktılar basmaz. Doğrudan: 
  > 🚨 *AI Usta Başı Yorumu: Makine son 2 saattir basınçtan sınırda çalışıyor. Bu durum yağ sıcaklığını tetikledi. Geçmişteki benzer kalıplara göre 45 dk içinde valf kaçağı riski (Termal Stres) var. Rölantiye alın.* 
şeklinde insan dilinde direktif verir.

---

## ⚡ Sistemi Benzersiz Kılan Özellikler

- **Maliyet-Farkındalıklı (Cost-Aware) Tahminleme:** Makinelerin plansız duruş maliyeti, onarım maliyetinden katbekat yüksektir. Algoritma **Recall** (Duyarlılık) oranını maksimize eder; asgari bir şüphede dahi teknik ekibi tetikler, "Yanlış Alarm olsa bile" hiçbir gerçek arıza potansiyeli şansa bırakılmaz.
- **Kayıpsız Zaman Makinesi (Historical Replay Engine):** Fabrika lokal ağ bağlantısını veya Kafka erişimini kaybetse dahi, sistem kendi içindeki *Event Loop* motoru sayesinde gigabytelarca geçmiş *violation_log.json* verisini saniye saniye işleyerek sahte olmayan, kanıtlanmış bir test & simülasyon altyapısı sunar.

---

## ⚙️ Geliştirici Kaynakları

Daha derinlemesine teknik detaylar, sınıf yapıları ve kod analizleri için modüler Dokümantasyon setimizi inceleyebilirsiniz:
- 📖 [Mimarî Genel Bakış](./docs/pipeline_mimarisi.md)
- 📖 [Katman 0: Veri Doğrulama](./docs/pipeline_detay_katman0.md)
- 📖 [Katman 1: State Store](./docs/pipeline_detay_katman1.md)
- 📖 [Katman 2: Analiz Motoru ve AI Usta Başı](./docs/pipeline_detay_katman2.md)
- 📖 [Katman 3: Alert Engine](./docs/pipeline_detay_katman3.md)
- 🛠️ [ML Geliştirici Dokümantasyonu (PROJECT_DETAILS.md)](./PROJECT_DETAILS.md)
