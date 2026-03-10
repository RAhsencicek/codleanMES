# 🏭 Codlean MES — Öncü Arıza Tahmin Pipeline Mimari Dokümanı

> **Amaç:** Bu doküman, projeyi bilen ya da bilmeyen herkesin pipeline'ı başından sonuna anlayabilmesi için yazılmıştır. Teknik kararların *ne* olduğunu değil, *neden* öyle alındığını da açıklar.

**Son güncelleme:** 2026-03-05
**Durum:** ✅ Hibrit model eğitimi hazır (violation_log + live_windows)

---

## 1. Projenin Amacı ve Bağlamı

Codlean MES (Manufacturing Execution System) sistemi, fabrikadaki makinelerin anlık durumunu izlemektedir. Fabrikada çeşitli tipte üretim makineleri bulunmaktadır: hidrolik presler, endüksiyon makineleri, testere/kesim makineleri ve robotlar.

**Mevcut problem:** Makineler arıza yapmadan önce genellikle ölçülebilir belirtiler verirler — sıcaklık yükselir, basınç düşer, akım artar. Ancak bu belirtiler şu an sistem tarafından izlenmiyor veya teknisyenlere düzgün iletilmiyor. Arıza makinenin durmasıyla fark ediliyor.

**Hedef:** Kafka üzerinden akan gerçek zamanlı sensör verilerini işleyerek, arızadan **saatler önce** uyarı üretmek. Bu uyarılar:
- **Açıklanabilir** olmalı: *"Yağ sıcaklığı 3 saattir artan bir trendde, şu an 42°C, limit 45°C"*
- **Tahmin içermeli:** *"Tahminen 2.5 saat sonra kritik eşiği geçer"*
- **Güvenilir olmalı:** Yanlış alarm üretmemeli

---

## 2. Veri Kaynağı — Kafka

### 2.1 Bağlantı Bilgileri

| Parametre | Değer |
|-----------|-------|
| **Broker** | `10.71.120.10:7001` |
| **Topic** | `mqtt-topic-v2` |
| **Format** | JSON (MTConnect-style nested) |
| **Erişim** | VPN gerektirir (şirket içi ağ) |

### 2.2 Kafka'nın Rolü

Kafka bu projede üretici (producer) değil **tüketici (consumer)** tarafında kullanılmaktadır. CODLEAN-155 adlı broker makinelerin verilerini MQTT protokolüyle toplar ve Kafka'ya iletir. Biz sadece bu veriyi okuruz, sisteme müdahale etmeyiz.

```
[Fabrika Makineleri]
        │  (MTConnect / MQTT)
        ▼
[CODLEAN-155 Broker]
        │
        ▼
[Kafka: mqtt-topic-v2]
        │
        ▼  ← Biz buradan okuyoruz
[Pipeline]
```

### 2.3 Payload Yapısı

Her Kafka mesajı bir makinenin **o anki tam durum snapshot'ını** içerir:

```json
{
  "header": {
    "sender":        "CODLEAN-155",
    "version":       "6.8.0.0",
    "creationTime":  "2026-03-04T05:52:44.174Z",
    "firstSequence": 124598102,
    "lastSequence":  124729173
  },
  "streams": [{
    "name": "HPR005_TYPE_007",
    "uuid": "HPR005",
    "componentStream": [{
      "componentId": "HPR005",
      "samples": [
        {"dataItemId": "oil_tank_temperature",      "result": "52.1"},
        {"dataItemId": "main_pressure",             "result": "142.0"},
        {"dataItemId": "horizontal_press_pressure", "result": "138.5"}
      ],
      "events": [
        {"dataItemId": "execution",              "result": "RUNNING"},
        {"dataItemId": "mode",                   "result": "AUTO"},
        {"dataItemId": "cooling_tower_active",   "result": "TRUE"},
        {"dataItemId": "pressure_line_filter_1_dirty", "result": "FALSE"}
      ]
    }]
  }]
}
```

**Kritik veri yapısı notları:**
- `samples` → Genellikle sürekli sayısal ölçümler (hız, akım)
- `events` → Durum bilgileri; hem sayısal hem boolean hem enum olabiliyor
- **⚠️ Saha bulgusu:** Aynı sensör (`oil_tank_temperature`, `main_pressure`) bazı makinelerde `samples`'da, bazılarında `events`'te geliyor! Parser her ikisini de taramalı.
- `result` alanı **her zaman string** ve **Türkçe locale ile virgüllü ondalık** (`"37,022568"`)
- `result: "UNAVAILABLE"` gerçek veriyle gözlemlendi → `None` olarak işlenmeli
- `creationTime` makine tarafındaki oluşum zamanı, işlem zamanı değil

---

## 3. Makine Envanteri

> **Saha Doğrulaması — 2026-03-04:** 300 Kafka mesajı üzerinde yapılan canlı analizle aşağıdaki tablo doğrulandı.

### 3.1 HPR — Hidrolik Pres
**Makineler:** HPR001 ✅, HPR002 🟡, HPR003 🔴 KAPALI, HPR004 🔴 KAPALI, HPR005 🟡, HPR006 🟡 (kısmi veri)  
**Kullanım:** Parça şekillendirme, delme, baskı

| Sensör (samples) | Birim | Açıklama |
|---|---|---|
| `oil_tank_temperature` | °C | Yağ tankı sıcaklığı — **en kritik sensör** |
| `main_pressure` | bar | Ana hidrolik devre basıncı |
| `horizontal_press_pressure` | bar | Yatay pres silindiri basıncı |
| `lower_ejector_pressure` | bar | Alt ejektör basıncı |
| `vertical_infeed_speed` | mm/s | Dikey besleme hızı |
| `horitzonal_infeed_speed` | mm/s | Yatay besleme hızı |

| Sensör (events) | Tip | Açıklama |
|---|---|---|
| `execution` | ENUM | RUNNING / IDLE / STOPPED / INTERRUPTED |
| `mode` | ENUM | AUTO / MANUAL / MAINTENANCE |
| `part_count` | INT | Üretilen toplam parça |
| `cycle_time` | INT (ms) | Son döngü süresi |
| `punch_active` | BOOL | Zımba hareketi aktif mi |
| `oil_tank_level_low` | BOOL | Yağ seviyesi düşük uyarısı |
| `cooling_tower_active` | BOOL | Soğutma kulesi çalışıyor mu |
| `pilot_pump_active` | BOOL | Pilot pompa çalışıyor mu |
| `pilot_pump_filter_1/2_dirty` | BOOL | Pilot pompa filtre kirli mi |
| `pressure_line_filter_1..5_dirty` | BOOL | Basınç hattı filtre durumu |
| `return_line_filter_1..2_dirty` | BOOL | Dönüş hattı filtre durumu |
| `pump_1..5_suction_valve_ok` | BOOL | Pompa valf durumu |

### 3.2 IND — EndüksiyonMakinesi
**Makineler:** IND001 ✅ RUNNING, IND002 ✅ RUNNING, IND003 ✅ RUNNING | **Kullanım:** Isıl işlem, sertleştirme
> IND makineler sürekli üretimde: IND001 48.257 parça, IND002 19.440 parça, IND003 44.050 parça

| Sensör | Birim | Açıklama |
|---|---|---|
| `current` | A | Ana akım (değer: ~2100A) |
| `additional_current` | A | İkincil akım |
| `estimated_part_temperature` | °C | Parça sıcaklığı tahmini (850°C) |
| `power` | kW | Anlık güç (~400-510 kW) |
| `power_percent` | % | Kapasite kullanım oranı |
| `cycle_time` | s | Döngü süresi (IND001: 24-62s, IND003: 95-130s) |

### 3.3 TST — Testere / Kesim Makinesi
**Makineler:** TST001 🟡 IDLE, TST002 🔴 KAPALI, TST003 🔴 KAPALI, TST004 🔴 KAPALI | **Kullanım:** Malzeme kesimi

| Sensör | Birim | Açıklama |
|---|---|---|
| `saw_speed` | RPM | Testere dönüş hızı (~75 RPM) |
| `feed_speed` | mm/dk | İlerleme hızı (3.7 mm/dk) |
| `servo_torque` | Nm | Servo motor torku |
| `main_motor_current` | A | Ana motor akımı |
| `cut_time` | ms | Kesim süresi |
| `cut_length` | mm | Kesim uzunluğu (418 mm) |
| `cut_count` | INT | O oturumda yapılan kesim |
| `total_cut_count` | INT | Toplam kesim sayısı |
| `total_cut_area` | mm² | Toplam kesilen alan |
| `target_cut_size` | STRING | Hedef çap ("Ø 150") |

### 3.4 RBT — Robot
**Makineler:** RBT001-004, RBT007, RBT008, RBT011, RBT012, RBT047 🔴 KAPALI | **Kullanım:** Parça taşıma, aparat yükleme

| Sensör | Tip | Açıklama |
|---|---|---|
| `fixture_mode` | INT | Aparat modu (0=kapalı, 3=tek taraflı, 4=çift taraflı) |
| `cycle_1_time` / `cycle_2_time` | INT (ms) | Döngü süreleri |
| `fixture_1_count` / `fixture_2_count` | INT | Aparattaki parça sayısı |
| `fixture_1_data` / `fixture_2_data` | STRING | Aparat doluluk matrisi |
| `error_count` | INT | Hata sayısı |
| `robot_id` | STRING | Robot kimliği |

**`fixture_data` formatı:** 30 pozisyonluk binary matris: `"00,00,10,10,10,..."`
- `00` = boş pozisyon
- `10` = dolu pozisyon  
- `01` = kısmen dolu / işlemde

```
RBT011 örneği: fixture_2_data = "10,10,10,...,10" (30/30 dolu)
              fixture_2_completed = TRUE → Aparat doldu, boşaltma bekliyor
```

---

## 4. Neden Alarm Tabanlı Değil, Min/Max Tabanlı Yaklaşım?

Bu kararın arkasında doğrudan saha gözlemi var.

### 4.1 Mevcut alarm sisteminin problemi

Kafka mesajlarında `alarm_1` ile `alarm_22` arasında 22 adet alarm alanı bulunmaktadır. Teoride bunları izleyip uyarı vermek mantıklı görünür. Ancak sahada şu gözlemler yapıldı:

- Alarmlar **gereksiz ve tutarsız** tetikleniyor — makine normal çalışırken bile alarm state'inde olabiliyor
- Alarm değerlerinin büyük çoğunluğu `"UNAVAILABLE"` ya da boş string (`""`) olarak geliyor
- Alarm anlamları makine bazında farklılık gösteriyor, standart bir mapping yok
- Hangi alarmın kritik olduğunu ayırt etmek için sistemi derinlemesine bilmek gerekiyor

**Sonuç:** 22 alarm alanı gürültüden ibaret. Bu veriye güvenerek sistem kurmak yanlış alarmlarla dolu bir pipeline doğurur.

### 4.2 Min/Max tabanlı yaklaşımın avantajları

Sistemin mühendisleri her sensör için **minimum** ve **maksimum** güvenli çalışma sınırlarını belirlemiş ve bunları bir config dosyasında tutmaktadır. Bu değerler:

- Makine üreticisi ve saha mühendislerinin birikimine dayanır
- Makinenin fiziğiyle uyumludur
- Değişmez ya da çok nadir değişir
- Net ve herkes tarafından yorumlanabilir

```
"Yağ sıcaklığı 65°C'yi geçti"  → herkes anlar
"alarm_7 = TRUE"                → ne anlama geliyor?
```

### 4.3 Yaklaşımın bilinçli sınırları

Min/max tabanlı yaklaşım her şeyi çözmez:
- Limit **henüz aşılmamışsa** ama hızla yaklaşıyorsa uyarı üretmez → **Trend analizi katmanı** bu boşluğu kapatır
- Boolean sensörler için sayısal sınır yoktur → **Süre + kombinasyon mantığı** bunu ele alır

### 4.4 Codlean MES Veri Şeması — PDF Dokümanı Bulguları

IT departmanının paylaştığı **"CODLEAN MES DATA ITEMS DOKÜMANTASYONU"** PDF'i, sistemin veri mimarisini açıklayan 4 tablo içermektedir. Bu bulgular pipeline tasarımımızı doğrudan etkiliyor.

#### Tablo 1: `DataItems` — Global Sensör Tanımları

Her sensörün sistem genelinde tek bir kaydı var. Makineye bağımsız.

| Alan | Açıklama | Örnek |
|------|----------|-------|
| `DataItemId` | Kafka'daki teknik isim | `oil_tank_temperature` |
| `Name` | UI'da kullanıcıya gösterilen isim | `Yağ Tankı Sıcaklığı` |
| `DataType` | `numeric`, `text`, `boolean` | `numeric` |

#### Tablo 2: `MachineTypeDataItems` — Makine Tipi Bazlı Konfigürasyon

**Pipeline'ımızın min/max referansı buradan geliyor.** Makine tipine göre (HPR, IND, TST, RBT) toplu ayar.

| Alan | Pipeline'a Etkisi |
|------|------------------|
| `MinValue` | ThresholdChecker'ın alt sınırı |
| `MaxValue` | ThresholdChecker'ın üst sınırı |
| `Unit` | Alert mesajında gösterilecek birim (°C, bar, A...) |
| `IsViolationEnabled` | **FALSE ise bu sensörü izleme** — gürültüyü baştan eliminedir |
| `SuccessKey` | **Boolean sensör kritik!** TRUE=OK mu, FALSE=OK mi? |
| `AllowedValues` | String sensörler için kabul edilen değerler listesi |
| `NotAllowedValues` | String sensörler için reddedilen değerler listesi |

> **`SuccessKey` Neden Kritik?**
> ```
> pump_1_suction_valve_ok → SuccessKey = TRUE  (TRUE=sağlıklı, FALSE=sorun)
> pressure_line_filter_1_dirty → SuccessKey = FALSE (FALSE=temiz, TRUE=kirli)
> ```
> Bu değeri bilmeden boolean alarmları tersine yorumlayabiliriz.
> Bu nedenle IT'den gelecek config'de her boolean sensör için `success_key` alanı da istenecek.

#### Tablo 3: `MachineDataItems` — Makine Bazlı Override

Belirli bir makine için tablo 2'deki tipik değerleri geçersiz kılar. Örneğin HPR005'in yağ sıcaklığı limiti HPR003'ten farklıysa burada tanımlanır. Pipeline'ımız önce bu tabloyu, yoksa tablo 2'yi kullanacak:

```python
# Pseudo-code: limit öncelik sırası
limit = machine_overrides.get(machine_id, {}).get(sensor) \
     or type_defaults.get(machine_type, {}).get(sensor)
```

#### Tablo 4: `ViolationDataItemValue` — Tarihsel İhlal Kaydı

`IsViolationEnabled = TRUE` olan sensörde değer limit dışına çıkınca **sistem otomatik yazar**. E-posta servisi bu tabloyu dinliyor.

**Pipeline'a etkisi:**
- Bu tablo **tarihe ait doğrulanmış ihlalleri** içeriyor
- Geçmişte hangi makine, hangi sensörde, ne zaman limit dışına çıktı → bulunabilir
- ML aşamasında (3-4 hafta sonra) etiketli veri kaynağı olarak kullanılabilir
- Şu an DB bağlantısı anlık veri için güvenilir değil; bu tablo ileride sorgulanacak

#### Özet: PDF'ten Alınan Tasarım Kararları

| Karar | Kaynak | Uygulama |
|-------|--------|----------|
| `IsViolationEnabled = FALSE` olan sensörler izlenmez | PDF Tablo 2 | `limits_config.yaml`'da sadece enabled sensörler |
| Boolean her sensör için `success_key` tanımlanır | PDF Tablo 2 | Config'e `success_key: TRUE/FALSE` alanı eklenir |
| `MachineDataItems` override'ı önce kontrol edilir | PDF Tablo 3 | limit yükleme fonksiyonunda öncelik sırası |
| `ViolationDataItemValue` ileride ML verisi | PDF Tablo 4 | Ertelenen konular listesinde |

---


## 5. Pipeline Mimarisi — Genel Görünüm

Pipeline, Kafka'dan ham veriyi okuyup teknisyene anlamlı bir uyarı üretene kadar dört katmandan geçirir. Her katman bir öncekinden **temizlenmiş ve zenginleştirilmiş** veri alır. Bir katman hata verirse veya veriyi reddederse sistem çökmez — o veriyi atlar ve loglar.

```
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
│         KATMAN 0: VERİ GİRİŞ & DOĞRULAMA               │
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
│         KATMAN 2: ANALİZ ENJİNİ                         │
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
│  │                      │  │  maz (ısınma maskelenir) │  │
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
│  • Throttle kontrolü: 30 dk'da 1 alert / makine        │
│  • Severity belirleme: DÜŞÜK/ORTA/YÜKSEK/KRİTİK        │
│  • Açıklama üretimi: "Neden? Hangi sensör? Ne öneriyiz?"│
│  • DB kaydı: alert_log tablosuna sensör değerleriyle    │
│  • Terminal çıktısı: renkli, okunabilir panel           │
│                                                         │
│  ÇIKIŞ: Teknisyen ekranı + PostgreSQL kaydı             │
└─────────────────────────────────────────────────────────┘
```

### 5.1 Veri Akışı — Somut Örnek

Yukarıdaki soyut diyagramı gerçek bir senaryo üzerinden izleyelim:

```
[Kafka'dan Gelen Ham Mesaj]
HPR005 | oil_tank_temperature = "37,022568" | creationTime = "2026-03-04T08:33:00Z"
         ← DİKKAT: ondalık ayracı NOKTA değil VİRGÜL (Türkçe locale)

        │
        ▼ KATMAN 0
"37,022568" → replace(",",".") → "37.022568" → float(37.022568) ✅
lag = 2 saniye → tamam, stale değil
Sensör HPR005'te events içinde *de* aranır (sadece samples değil)
37.02 > 35.5 + 5*1.2 = 41.5? → hayır, spike değil → GEÇTİ

        │
        ▼ KATMAN 1
ring_buffer["oil_tank_temperature"].append(37.02)
ewma_mean güncellendi: 37.0 → 37.01
sample_count: 4822 → confident: %87

        │
        ▼ KATMAN 2
ThresholdChecker: 37.02 < 65*0.85 = 55.25 → Henüz soft limit yok, sessiz
TrendDetector:    son 30 ölçüm eğimi = +0.05°C/10sn = +1.8°C/saat (R²=0.91)
                  ETA = (65-37.02) / 1.8 = ~15.5 saat → 8h'den uzun, sinyal yok
RiskScorer:       Her iki sinyal yok → score = 0 → Alert üretilmez ✅

        │
        ▼ KATMAN 3
Son alert: 4 saat önce → throttle yok
Severity: ORTA (skor 0.55)
→ Terminal'e panel bas, PostgreSQL'e yaz
```

---

## 6. Katman 0 — Veri Girişi ve Doğrulama

Bu katman **güvenlik görevlisi** gibi davranır. Ham Kafka verisini inceler, sorunlu olanları reddeder ya da işaretler. Kabul edilen veri temiz ve tip-güvenlidir.

**Neden bu katman kritik?**
Kafka'dan gelen `result` alanları *her zaman string*. `"52.1"` ile `52.1` arasındaki fark matematiksel olarak kritik. Üstelik `"UNAVAILABLE"` değerini `float()`'a verirseniz program çöker. Bu katman olmadan Katman 1 ve 2 her ölçümde hatayla karşılaşır.

### 6.1 Schema Doğrulama

Her Kafka mesajında bulunması *zorunlu* alanları kontrol eder. Bu alanlar yoksa mesaj tamamen atlanır.

```python
REQUIRED_PATHS = [
    "header.sender",        # Hangi broker gönderdi?
    "header.creationTime",  # Mesajın makine tarafındaki zamanı
    "streams[].componentStream[].componentId"  # Hangi makine?
]

def validate_schema(data: dict) -> bool:
    # header kontrolü
    if "sender" not in data.get("header", {}):
        log.error("SCHEMA_ERROR: header.sender eksik")
        return False
    if "creationTime" not in data.get("header", {}):
        log.error("SCHEMA_ERROR: header.creationTime eksik")
        return False
    # streams kontrolü
    for stream in data.get("streams", []):
        for comp in stream.get("componentStream", []):
            if "componentId" not in comp:
                log.error("SCHEMA_ERROR: componentId eksik")
                return False
    return True
```

### 6.2 UNAVAILABLE → None Dönüşümü + Ondalık Virgül Düzeltmesi

> **⚠️ Saha Bulgusu (2026-03-04):** Kafka verilerinde tüm sayısal değerler **Türkçe locale** ile geliyor. Ondalık ayracı nokta değil **virgül**: `"37,022568"`, `"2122,9746"`, `"0,5927072"`. `float()` virgülle çalışmaz — program çöker!

```python
def safe_numeric(value) -> float | None:
    """
    String olan result değerini güvenle float'a dönüştür.
    UNAVAILABLE, boş string, None → None döndür.
    Türkçe locale: virgül → nokta dönüşümü zorunlu.

    ❌ Yanlış: float("37,022568")   → ValueError!
    ✅ Doğru:  float("37.022568")   → 37.022568
    """
    if value is None or str(value).strip().upper() in ("UNAVAILABLE", ""):
        return None   # Eksik veri — işleme alma, sadece say
    try:
        normalized = str(value).strip().replace(",", ".")  # TR locale fix
        return float(normalized)
    except (ValueError, TypeError):
        log.warning(f"PARSE_ERROR: '{value}' sayıya dönüştürülemedi")
        return None
```

**Etkisi:** `None` dönen değerler ring buffer'a eklenmez, `valid_count` artmaz, `sample_count` artar. Bu sayede confidence skoru gerçek veri kalitesini yansıtır.

### 6.3 Timestamp Gecikme Kontrolü (Stale Data)

Kafka consumer geride kalırsa (örn. ağ sorunu sonrası toplu veri gelirse) eski mesajlar sırayla işlenir. Sistem bu mesajları "şu an gelen veri" sanırsa trend hesabı bozulur.

```python
def check_staleness(creation_time_str: str, machine_id: str):
    event_time = datetime.fromisoformat(creation_time_str.replace("Z", "+00:00"))
    lag_seconds = (datetime.now(timezone.utc) - event_time).total_seconds()

    if lag_seconds > 300:  # 5 dakikadan eski
        log.warning(f"STALE_DATA | {machine_id} | lag={lag_seconds:.0f}s")
        return True   # is_stale=True → trend hesabına dahil etme

    return False  # Taze veri, her şey normal
```

**Stale veri ne olur?**
- Threshold (eşik) kontrolüne dahil edilir — anlık değer hâlâ önemli
- Trend hesabından çıkarılır — geçmişe ait değer trendi bozar
- `STALE_DATA` olarak loglanır — haftalık raporlarda Kafka sağlığı izlenir

### 6.4 Spike Filtresi

Sensör arızası veya geçici elektrik gürültüsü durumunda bir ölçüm aniden gerçek dışı bir değere atlayabilir. Örneğin yağ sıcaklığı 42°C iken bir anda 890°C okursa bu kesinlikle sensör gürültüsüdür.

```python
def is_spike(new_value: float, machine_id: str, sensor: str, state: dict) -> bool:
    """
    Yeni değer, mevcut EWMA ortalamasından 5 standart sapma uzaktaysa spike say.
    İlk 10 ölçümde spike kontrolü yapma (henüz istatistik yok).
    """
    mean = state[machine_id]["ewma_mean"].get(sensor)
    std  = state[machine_id]["ewma_std"].get(sensor)

    if mean is None or std is None or std < 0.001:
        return False  # Yeterli istatistik yok, geçir

    z_score = abs(new_value - mean) / std
    if z_score > 5:
        log.warning(f"SPIKE | {machine_id}.{sensor} | value={new_value}, z={z_score:.1f}")
        return True
    return False
```

**Neden 5σ seçildi?** Normal dağılımda 5σ'nın ötesine geçme olasılığı yaklaşık 3 milyonda 1'dir. Gerçek bir değerken spike olarak işaretleme riski ihmal edilebilir düzeyde.

### 6.5 Startup Mask

Hidrolik pres gibi makineler bakım veya gece durumu sonrasında soğuk başlar. İlk 60 dakika sıcaklık hızla yükselir — bu artış arıza değil, normal ısınma sürecidir. Startup mask bu süreyi trend hesabından çıkarır.

```python
def check_startup(machine_id: str, new_execution: str, state: dict) -> bool:
    """
    Makine yeni RUNNING state'ine geçtiyse startup_ts'i kaydet.
    Son startup'tan 60 dk geçmediyse startup_phase=True döndür.
    """
    prev_exec = state[machine_id].get("last_execution", "")
    curr_exec  = new_execution

    # OFF/IDLE/STOPPED → RUNNING geçişi
    if curr_exec == "RUNNING" and prev_exec in ("IDLE", "STOPPED", "INTERRUPTED", ""):
        state[machine_id]["last_startup_ts"] = datetime.utcnow().isoformat()

    startup_ts = state[machine_id].get("last_startup_ts")
    if startup_ts:
        minutes_since = (datetime.utcnow() -
                         datetime.fromisoformat(startup_ts)).total_seconds() / 60
        if minutes_since < 60:
            return True  # startup_phase → trend hesabını atla

    return False
```

---

## 7. Katman 1 — State Store

Bu katman pipeline'ın **belleğidir**. Tek bir Kafka mesajı anlık değeri verir ama "bu değer artıyor mu, azalıyor mu, ne kadar süredir bu seviyede?" sorularını yanıtlamak için geçmişe ihtiyaç vardır. State store her makine için bu geçmişi RAM'de tutar.

**Neden RAM?** Disk I/O her güncellemede yavaş olurdu. Her 10 saniyede gelen 10+ makinenin verisini gerçek zamanlı işlemek için bellek şarttır. Checkpoint ile periyodik diske yedekleme yapılır.

### 7.1 Ring Buffer (Kayan Pencere)

Her sensörün son N ölçümü tutulur. N dolarsa en eski değer otomatik silinir. Bu yapıya **ring buffer** (dairesel tampon) denir.

```python
from collections import deque

# HPR005, yağ sıcaklığı için ring buffer
# maxlen=720 → 10sn aralıkla 2 saatlik veri
buffer = deque(maxlen=720)

buffer.append(38.1)  # t=0
buffer.append(38.4)  # t=10sn
buffer.append(38.7)  # t=20sn
# ...
# 721. değer geldiğinde otomatik olarak t=0 değeri (38.1) silinir
```

**Window boyutu neden 720 (2 saat)?**
- Sıcaklık gibi yavaş değişen sensörler için 2 saat anlamlı bir trend penceresidir
- Basınç gibi hızlı değişenler için 30 dk yeterli olabilir — bunu config üzerinden ayarlanabilir yapıyoruz
- İlk veriler geldikçe bu değeri revize edeceğiz

### 7.2 EWMA — Online İstatistik Güncelleme

Klasik ortalama hesaplamak için tüm geçmişi toplamak gerekir. EWMA (Exponentially Weighted Moving Average) bunu her adımda tek bir çarpma işlemiyle günceller.

```python
def update_ewma(old_mean: float, old_var: float, new_value: float, alpha: float):
    """
    Tek geçişte ortalama ve varyansı güncelle.
    alpha: öğrenme hızı. Küçük → yavaş adapte. Büyük → hızlı adapte.

    Örnek:
      Sıcaklık alpha=0.07: Bir önceki 1000 ölçümün ağırlığı hâlâ %7 etkili
      Basınç  alpha=0.25:  Bir önceki 100 ölçümün ağırlığı ~%7'ye düşüyor
    """
    new_mean = alpha * new_value + (1 - alpha) * old_mean
    new_var  = alpha * (new_value - new_mean)**2 + (1 - alpha) * old_var
    return new_mean, new_var
```

**Neden EWMA, neden sabit pencere değil?**
Sabit pencere (son 720 değerin ortalaması) her adımda 720 eleman üzerinde işlem yapar. EWMA tek çarpmayla güncellenir — daha hızlı, daha az bellek.

### 7.3 Confidence Score — Sistem Ne Kadar Güvenilir?

```python
def calculate_confidence(sample_count: int, valid_count: int) -> float:
    """
    Sistem iki soruyu yanıtlar:
    1. Yeterli veri var mı? (sample_count / 500)
       → 500 ölçüm = ~1.4 saat veri → tam güven için yeterli
    2. Verinin kalitesi nasıl? (valid / total)
       → UNAVAILABLE oranı yüksekse güven düşer

    Örnek:
      500 ölçüm, 490 valid → 1.0 * 0.98 = 0.98 → %98 güven
      100 ölçüm, 80 valid  → 0.2 * 0.80 = 0.16 → %16 güven (yeni sistem)
    """
    valid_ratio = valid_count / max(sample_count, 1)
    base_conf   = min(sample_count / 500, 1.0)
    return round(base_conf * valid_ratio, 3)
```

`confidence < 0.3` → Alert üretilir ama başlığa **"[DÜŞÜK GÜVEN]"** eklenir.
`confidence < 0.1` → Alert üretilmez, çok az veri var.

### 7.4 Boolean Sensör Süre Takibi

`pressure_line_filter_2_dirty = TRUE` değeri tek başına anlamsızdır. Filtre az önce mi kirli oldu, yoksa 6 saattir mi kirli? Bu süre bilgisi olmadan karar verilemez.

```python
def update_boolean_state(machine_id: str, sensor: str,
                         new_value: str, state: dict) -> timedelta | None:
    """
    Boolean sensörün ne zamandır aktif olduğunu takip eder.
    TRUE geldiğinde timestamp yaz. FALSE geldiğinde sıfırla.
    """
    is_active = new_value.upper() == "TRUE"
    key = f"{sensor}_active_since"

    if is_active:
        if state[machine_id]["boolean_active_since"].get(sensor) is None:
            # Yeni aktif oldu → başlangıç zamanını kaydet
            state[machine_id]["boolean_active_since"][sensor] = datetime.utcnow()

        # Ne kadar süredir aktif?
        since = state[machine_id]["boolean_active_since"][sensor]
        return datetime.utcnow() - since
    else:
        # Artık aktif değil → sıfırla
        state[machine_id]["boolean_active_since"][sensor] = None
        return None
```

**Alert engine bu bilgiyi kullanır:**
```
pressure_line_filter_2_dirty: 2 saat 14 dakikadır KİRLİ
```

### 7.5 Persistence — Atomik JSON Checkpoint

RAM'deki state her 5 dakikada bir diske yazılır. Böylece sistem yeniden başlatılsa da kaldığı yerden devam eder.

```python
import tempfile, os, json

SCHEMA_VERSION = 1  # Veri yapısı değişince bu artar

def save_state(state: dict, path="state.json"):
    """
    Doğrudan dosyaya yazmak tehlikelidir:
    Process aniden ölürse dosya yarım kalır → corrupt.

    Çözüm: Önce geçici dosyaya yaz, sonra atomik rename yap.
    İşletim sistemi rename'i atomik garanti eder.
    """
    state_copy = dict(state)
    state_copy["_schema_version"] = SCHEMA_VERSION
    state_copy["_saved_at"] = datetime.utcnow().isoformat()

    # Aynı disk bölümünde geçici dosya oluştur
    tmp_dir = os.path.dirname(os.path.abspath(path))
    with tempfile.NamedTemporaryFile("w", dir=tmp_dir,
                                     delete=False, suffix=".tmp") as f:
        json.dump(state_copy, f, indent=2, default=str)
        tmp_path = f.name

    os.replace(tmp_path, path)  # Atomik! Kesinti olsa bile state.json sağlam kalır


def load_state(path="state.json") -> dict:
    """
    Başlangıçta yükle. Dosya yoksa, şema uyumsuzsa sıfırdan başla.
    """
    if not os.path.exists(path):
        log.info("Checkpoint yok, sıfırdan başlanıyor")
        return {}

    with open(path) as f:
        saved = json.load(f)

    # Şema değişmişse eski checkpoint geçersiz
    if saved.get("_schema_version") != SCHEMA_VERSION:
        log.warning(f"Checkpoint v{saved.get('_schema_version')} != "
                    f"current v{SCHEMA_VERSION} → sıfırdan başlanıyor")
        return {}

    log.info(f"Checkpoint yüklendi: {saved.get('_saved_at')}")
    return saved
```

---

## 8. Katman 2 — Analiz Engini

Bu katman **değerlendirme merkezidir**. State store'dan gelen zenginleştirilmiş veriyi iki farklı açıdan analiz eder ve sonuçları tek bir risk skorunda birleştirir.

**İki sinyalin farkı:**

| | ThresholdChecker | TrendDetector |
|---|---|---|
| **Soru** | "Şu an problem var mı?" | "Problem yaklaşıyor mu?" |
| **Veri** | Anlık ölçüm + config limiti | Son 30 ölçümün doğrusal eğimi |
| **Tetiklenir** | Değer %85 eşiğini geçince | Eğim pozitif, R²>0.7, artış trend ise |
| **ETA** | Yok | Evet — kaç saat kaldı |
| **Startup phase** | Çalışır | Çalışmaz (maskelenir) |

### 8.1 ThresholdChecker — Birincil Sinyal

Sensörün anlık değerini config'deki sınırlarla karşılaştırır. Üç seviye vardır:

```
     ┌──────────────────────────────────────────────────────┐
     │                  Limit Bölgeleri                     │
     │                                                      │
  65°│ ────────────────────────────── KRİTİK SINIR (max)   │
     │                                                      │
     │ Bu bölgede: YÜKSEK uyarı (limiti geçti)             │
     │                                                      │
55.25│ ────────────────────────────── SOFT SINIR (max*0.85) │
     │                                                      │
     │ Bu bölgede: ORTA uyarı (limite yaklaşıyor)          │
     │                                                      │
     │ Bu bölgede: Normal, sessiz                          │
     │                                                      │
  10°│ ────────────────────────────── MİN SINIR            │
     └──────────────────────────────────────────────────────┘
```

```python
def check_threshold(machine_id: str, sensor: str,
                    value: float, limits: dict) -> ThresholdSignal | None:
    """
    Anlık değeri config limitiyle karşılaştırır.
    Her iki yönde de (HIGH/LOW) kontrol yapar.
    """
    if machine_id not in limits or sensor not in limits[machine_id]:
        return None  # Bu sensör için limit tanımlı değil, kontrol etme

    limit = limits[machine_id][sensor]
    soft_ratio = 0.85  # Config'den gelecek

    # ─── YÜKSEK TARAF ─────────────────────────────────────────
    if value > limit["max"]:
        pct_over = (value - limit["max"]) / limit["max"] * 100
        severity = "KRİTİK" if pct_over > 10 else "YÜKSEK"
        return ThresholdSignal(
            sensor=sensor, value=value,
            limit=limit["max"], direction="HIGH", severity=severity,
            message=f"{sensor}: {value} > limit {limit['max']}"
        )

    # Soft uyarı — limite %85 yaklaştıysa erken uyar
    if value > limit["max"] * soft_ratio:
        return ThresholdSignal(
            sensor=sensor, value=value,
            limit=limit["max"], direction="HIGH", severity="ORTA",
            message=f"{sensor}: {value} limite %{100*value/limit['max']:.0f} yakın"
        )

    # ─── DÜŞÜK TARAF ──────────────────────────────────────────
    if value < limit["min"]:
        return ThresholdSignal(
            sensor=sensor, value=value,
            limit=limit["min"], direction="LOW", severity="YÜKSEK",
            message=f"{sensor}: {value} < alt limit {limit['min']}"
        )

    return None  # Normal aralıkta
```

### 8.2 TrendDetector — İkincil Sinyal

Anlık değeri değil, **yönü ve hızı** ölçer. Doğrusal regresyon kullanır.

**Neden doğrusal regresyon?**
Sıcaklık gibi sensörler genellikle monoton artar ya da azalır — parabolik veya sinüsoidal değil. Doğrusal model hem hesaplaması kolay hem yorumlaması kolaydır: *"Sıcaklık saatte 1.8°C artıyor."*

```python
from scipy.stats import linregress

def detect_trend(buffer: deque, limit_max: float,
                 interval_sec: int = 10) -> TrendSignal | None:
    """
    Son 30 ölçüm üzerinde doğrusal regresyon uygular.

    Parametreler:
        buffer: ring buffer (deque)
        limit_max: config'den gelen maksimum sınır
        interval_sec: ölçümler arası süre (saniye)

    Döndürür:
        TrendSignal: slope (eğim/adım), eta_minutes, r_squared
        None: trend yok veya yetersiz veri
    """
    if len(buffer) < 30:
        return None  # İstatistiksel anlam için minimum 30 veri noktası

    values = list(buffer)[-30:]           # Son 30 değer
    times  = list(range(len(values)))     # 0, 1, 2, ... 29 (adım indeksi)

    slope, intercept, r_value, p_value, _ = linregress(times, values)

    r_squared = r_value ** 2

    # Zayıf trend filtreleri:
    if r_squared < 0.7:
        # R² < 0.7 → veriler dağınık, güvenilir bir trend yok
        # Örn: gürültülü basınç ölçümü, sinyal üretme
        return None

    if slope <= 0:
        # Azalıyor veya stabil → sorun yok
        return None

    if slope < 0.001:
        # Artış var ama ihmal edilebilir küçüklükte
        return None

    # Kaç adımda max'a ulaşır?
    current_value = values[-1]
    remaining     = limit_max - current_value

    if remaining <= 0:
        # Zaten limiti geçmiş — ThresholdChecker bunu zaten yakalamış olmalı
        return None

    eta_steps   = remaining / slope        # kaç adım kaldı
    eta_minutes = eta_steps * interval_sec / 60  # dakikaya çevir

    # ETA çok kısa veya çok uzunsa filtrele
    if eta_minutes < 5:
        return None  # Zaten anlık geçiyor, threshold yakalar
    if eta_minutes > 480:
        return None  # 8 saatten fazla → çok belirsiz, uyarma

    per_hour = slope * (3600 / interval_sec)  # gerçek birim/saat

    return TrendSignal(
        slope_per_step=slope,
        slope_per_hour=per_hour,
        eta_minutes=eta_minutes,
        r_squared=r_squared,
        current_value=current_value,
        sample_count=len(values)
    )
```

**R² nedir?**
Doğrusal trendin veriye ne kadar iyi uyduğunu ölçer.
- R²=1.0 → Mükemmel doğrusal artış, çok güvenilir trend
- R²=0.7 → Kabul edilebilir minimum
- R²=0.3 → Dağınık, güvenilmez — sinyal üretme

### 8.3 RiskScorer — Sinyalleri Birleştirme

İki sinyal varsa nasıl tek skor üretilir? Kural basit ama bilinçli:

```python
def calculate_risk(threshold_sig: ThresholdSignal | None,
                   trend_sig: TrendSignal | None,
                   confidence: float) -> RiskEvent:
    """
    Threshold ve trend sinyallerini 0-1 arası tek skorda birleştirir.
    Confidence ile ölçekler (güven düşükse skor düşer).

    Ağırlıklar şimdilik sabit.
    1-2 ay veri toplandıktan sonra elle kalibre edilecek.
    """
    score = 0.0
    reasons = []

    # ─── THRESHOLD KATKISI ────────────────────────────────────
    if threshold_sig:
        threshold_weights = {
            "KRİTİK": 0.80,   # Zaten limiti %10 aştı
            "YÜKSEK": 0.60,   # Limiti geçti
            "ORTA":   0.30,   # %85 eşiğine yaklaştı
            "DÜŞÜK":  0.10,
        }
        score += threshold_weights.get(threshold_sig.severity, 0.1)
        reasons.append(f"{threshold_sig.sensor}: {threshold_sig.message}")

    # ─── TREND KATKISI ────────────────────────────────────────
    if trend_sig:
        # ETA ne kadar kısaysa urgency o kadar yüksek
        # 4 saat = normalize referans noktası (0 urgency)
        # 0 saat = maksimum urgency (1.0)
        urgency = max(0.0, 1.0 - (trend_sig.eta_minutes / 240))

        # R² ile ağırlıklandır: belirsiz trend daha az katkı yapar
        trend_contribution = 0.4 * urgency * trend_sig.r_squared
        score += trend_contribution

        reasons.append(
            f"Trend: +{trend_sig.slope_per_hour:.1f}/saat, "
            f"ETA ~{trend_sig.eta_minutes:.0f}dk, R²={trend_sig.r_squared:.2f}"
        )

    # ─── CONFIDENCE ÖLÇEKLEME ─────────────────────────────────
    # Güven %30'un altındaysa skor yarıya düşer, alarm yine de üretilir
    # ama [DÜŞÜK GÜVEN] etiketi alır
    score_raw = min(score, 1.0)
    score_final = score_raw * max(confidence, 0.5)  # tam sıfırlamaz

    return RiskEvent(
        machine_id=...,
        score=round(score_final, 3),
        score_display=int(score_final * 100),  # 0-100
        confidence=confidence,
        reasons=reasons,
        threshold_signal=threshold_sig,
        trend_signal=trend_sig,
    )
```

---

## 9. Katman 3 — Alert Engine

Bu katman **iletişim katmanıdır**. Risk skoru eşiği geçtiyse insana anlamlı, eyleme dönüştürülebilir bir uyarı üretir.

### 9.1 Alert Throttling — Alarm Yorgunluğu Önleme

Bir sensör saatlerce limit üzerinde kalabilir. Bu durumda her 10 saniyede bir alert üretmek teknisyeni bunaltır (alarm fatigue) ve önemli uyarıların gözden kaçmasına neden olur.

**Kural:** Aynı makine için 30 dakikada en fazla 1 alert.

```python
def should_alert(machine_id: str, state: dict,
                 throttle_minutes: int = 30) -> bool:
    """
    Son alertten bu yana yeterli süre geçti mi?
    """
    last_alert = state[machine_id].get("last_alert_ts")

    if last_alert is None:
        return True  # İlk alert, üret

    elapsed = (datetime.utcnow() -
               datetime.fromisoformat(last_alert)).total_seconds() / 60

    if elapsed >= throttle_minutes:
        return True

    log.debug(f"THROTTLE | {machine_id} | {elapsed:.0f}dk geçti, "
              f"henüz {throttle_minutes}dk dolmadı")
    return False
```

**İstisnai durum:** Severity KRİTİK ise throttle yarıya indirilir (15 dk). Çünkü limiti %10'dan fazla geçen bir değer bekletilemez.

### 9.2 Açıklama Üretimi (Template Tabanlı)

Her alert için "Neden? Ne? Ne yapmalıyım?" sorularını yanıtlayan bir açıklama üretilir. Bu açıklama kodlanmış bir AI değil, template tabanlıdır — tutarlı ve test edilebilir.

```python
REASON_TEMPLATES = {
    ("oil_tank_temperature", "HIGH", "ORTA"): (
        "Yağ tankı sıcaklığı limite yaklaşıyor.",
        "Soğutma kulesi aktif mi kontrol edin."
    ),
    ("oil_tank_temperature", "HIGH", "YÜKSEK"): (
        "Yağ tankı sıcaklığı maksimum limiti geçti.",
        "Makineyi durdurup yağ soğutma sistemini kontrol edin."
    ),
    ("main_pressure", "LOW", "YÜKSEK"): (
        "Ana hidrolik basınç minimum limitin altına düştü.",
        "Pompa ve valf durumunu kontrol edin."
    ),
    # ... diğer sensörler
}

def build_alert_message(risk_event: RiskEvent,
                         boolean_states: dict) -> str:
    """
    Risk event'inden okunabilir teknisyen mesajı üretir.
    Boolean sensörlerin ne kadar süredir aktif olduğunu ekler.
    """
    # ... template lookup ve boolean süre bilgisi birleştirme
```

### 9.3 Teknisyen Terminal Çıktısı

```
┌─────────────────────────────────────────────────┐
│ ⚠️  HPR005 — ERKEN UYARI                        │
│ Risk Skoru: 55/100  |  Güven: %87               │
├─────────────────────────────────────────────────┤
│ 📈 Tespit: Yağ tankı sıcaklığı artış trendinde  │
│    Mevcut: 58.3°C  |  Soft limit: 55.3°C        │
│    Eğim: +1.8°C/saat  (R²=0.91)                 │
│    ⏱  Tahmini kritik eşik (65°C): ~3.7 saat    │
├─────────────────────────────────────────────────┤
│ 🔗 Eş zamanlı boolean sinyaller:                │
│    - Soğutma kulesi: KAPALI (1sa 42dk süredir)  │
│    - Basınç hattı filtre 2: KİRLİ (0sa 38dk)   │
├─────────────────────────────────────────────────┤
│ 💡 Yorum: Soğutma sistemi yetersiz çalışıyor    │
│    Öneri: Soğutma kulesi durumunu kontrol et    │
└─────────────────────────────────────────────────┘
```

**Çıktının anatomisi:**
- **Satır 1:** Makine ve önem seviyesi
- **Satır 2:** Sayısal skor ve sistemin kendine güveni
- **Blok 1:** Hangi sensör, şu anki değer, limit, eğim ve ETA
- **Blok 2:** Aynı anda aktif olan boolean sinyaller (bağlamsal bilgi)
- **Blok 3:** Olası neden ve teknisyene öneri

### 9.4 Alert Log Tablosu (PostgreSQL)

Her alert veritabanına kaydedilir. Bu tablo hem debugging hem de ilerideki ML eğitimi için temel veri kaynağıdır.

```sql
CREATE TABLE alert_log (
    id           SERIAL PRIMARY KEY,
    machine_id   VARCHAR(20)  NOT NULL,
    alert_time   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    severity     VARCHAR(10),           -- DÜŞÜK / ORTA / YÜKSEK / KRİTİK
    risk_score   FLOAT,                 -- 0.0 - 1.0
    confidence   FLOAT,                 -- 0.0 - 1.0

    reason       TEXT,                  -- İnsan okunabilir açıklama
    eta_minutes  FLOAT,                 -- Tahmini kritik eşiğe süre (varsa)

    -- Hangi katman ne kadar katkı verdi?
    -- Örn: {"threshold": 0.30, "trend": 0.25}
    signal_breakdown  JSONB,

    -- Alert anındaki tüm sensör değerleri
    -- FALSE ALARM ANALİZİ İÇİN KRİTİK
    -- Örn: {"oil_tank_temperature": 58.3, "main_pressure": 141.0,
    --        "cooling_tower_active": "FALSE"}
    sensor_values     JSONB,

    -- Teknisyen, alert'i inceleyince buraya yazar (sonradan doldurulur)
    technician_feedback  VARCHAR(20),   -- correct / false_alarm / unknown
    feedback_time        TIMESTAMPTZ,
    feedback_note        TEXT           -- Serbest yorum
);

-- Sık kullanılan sorgular için index
CREATE INDEX idx_alert_machine    ON alert_log (machine_id, alert_time DESC);
CREATE INDEX idx_alert_feedback   ON alert_log (technician_feedback)
    WHERE technician_feedback IS NOT NULL;
```

**Neden `sensor_values` JSONB kritik?**
Bir alert bir hafta sonra "yanlış alarm" olarak işaretlendiğinde, o andaki sensör değerlerini saklamadıysanız ne olduğunu asla anlayamazsınız. Bu sütun hem:
- Debugging: "O an gerçekten ne oluyordu?"
- ML: "Yanlış alarm üretilen koşullar neydi?"

için en değerli veri kaynağıdır.

---

## 10. Modüller ve Sorumluluklar

| Modül | Sorumluluk | Girdi | Çıktı |
|-------|-----------|-------|-------|
| `kafka_consumer.py` | Kafka bağlantısı, mesaj döngüsü | Kafka topic | Raw JSON dict |
| `data_validator.py` | Schema, UNAVAILABLE, spike, stale, startup | Raw JSON | Temiz dict veya None |
| `state_store.py` | Ring buffer, EWMA, confidence, boolean, checkpoint | Temiz dict | Güncellenen state |
| `threshold_checker.py` | Anlık değer vs config limiti | Sensör değeri + limits | ThresholdSignal veya None |
| `trend_detector.py` | Doğrusal regresyon, ETA tahmini | Ring buffer + limit | TrendSignal veya None |
| `risk_scorer.py` | İki sinyali confidence'la birleştirme | İki signal + confidence | RiskEvent (0-100) |
| `alert_engine.py` | Throttle, açıklama, DB kaydı, terminal | RiskEvent | Ekran çıktısı + DB satırı |
| `limits_config.yaml` | Min/max değerleri, tüm parametreler | — | Config dict |

---

## 11. Konfigürasyon Dosyası (Şablon)

`limits_config.yaml` — **`machine_limits` bölümü IT'den bekleniyor, diğerleri kesinleşti:**

```yaml
kafka:
  bootstrap_servers: "10.71.120.10:7001"
  topic: "mqtt-topic-v2"
  group_id: "ariza-tahmin-pipeline"

pipeline:
  stale_data_threshold_seconds: 300    # 5 dk'dan eski → stale
  startup_mask_minutes: 60             # Makine açılışından sonraki maske
  state_window_size: 720               # Ring buffer boyutu (10sn → 2 saat)
  checkpoint_interval_seconds: 300     # State yedekleme sıklığı
  alert_throttle_minutes: 30           # Makine başına min alert aralığı
  soft_limit_ratio: 0.85               # Soft uyarı eşiği
  min_samples_for_trend: 30            # Trend için min veri sayısı
  trend_r2_threshold: 0.7              # Min R² — zayıf trende sinyal üretme
  min_confidence_for_alert: 0.10       # Bu altında hiç alert üretme

ewma_alpha:
  HPR:
    oil_tank_temperature: 0.07         # Yavaş → düşük alpha
    main_pressure: 0.25                # Hızlı spike → yüksek alpha
    horizontal_press_pressure: 0.25
    lower_ejector_pressure: 0.20
    vertical_infeed_speed: 0.15
    horitzonal_infeed_speed: 0.15
  IND:
    current: 0.20
    estimated_part_temperature: 0.10
    power: 0.15
  TST:
    saw_speed: 0.15
    servo_torque: 0.20
    main_motor_current: 0.20
  default: 0.10

machine_limits:    # ← IT'DEN GELECEK — PLACEHOLDER
  HPR003:
    oil_tank_temperature:      {min: 10, max: 65}
    main_pressure:             {min: 80, max: 200}
    horizontal_press_pressure: {min: 0,  max: 250}
  HPR005:
    oil_tank_temperature:      {min: 10, max: 65}
    main_pressure:             {min: 80, max: 200}
    horizontal_press_pressure: {min: 0,  max: 250}
```

---

## 12. Bilinçli Olarak Ertelenen Konular

| Konu | Neden Ertelendi | Ne Zaman |
|------|----------------|----------|
| **Redis** | Restart sıklığı belirsiz; JSON yeterli | Restart sıklığı netleşince |
| **ML / Isolation Forest** | Etiketli arıza verisi yok | 3-4 hafta operasyon sonrası |
| **Fusion ağırlık optimizasyonu** | Alert log dolu olmadan kalibre edilemez | 1 ay log sonrası |
| **Feedback UI** | Önce alert üretmek lazım | İlk ay alert kalitesi netleşince |
| **Webhook / SMS** | Terminal çıktısı şimdilik yeterli | Pipeline kararlı hale gelince |

---

## 13. Açık Kararlar

- [ ] **Makine bazlı min/max değerleri** → IT'den config bekleniyor
- [ ] **Window boyutu** → Sıcaklık 2 saat, basınç için 30 dk mı?
- [ ] **Restart sıklığı** → Redis kararını belirliyor
- [ ] **Boolean süre eşiği** → Filtre kaç saat kirli kalırsa uyarı?
- [ ] **Confidence eşiği** → `confidence < 0.1` altında hiç alert üretme kararı netleşti mi?
- [ ] **KRİTİK throttle istisnası** → 15 dk mı, 10 dk mı?

---

*Bu doküman yaşayan bir belgedir. Config dosyası gelince ve ilk veriler toplandıkça güncellenecektir.*
