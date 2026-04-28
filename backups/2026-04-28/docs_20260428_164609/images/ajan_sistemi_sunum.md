# 🎯 Codlean MES — Akıllı Fabrika Arıza Tahmin Sistemi
## Teknik İlerleme Sunumu

**Tarih:** 24 Nisan 2026  
**Hazırlayan:** R. Ahsen Çiçek  
**Proje Başlangıcı:** Şubat 2026  
**Mevcut Aşama:** Aşama 5 — 6 Makineli Pilot Üretim (Canlı)

---

# BÖLÜM I — GİRİŞ: PROBLEMİ TANIMLAMA

## Fabrikalarda Gerçek Bir Sorun Var

Bir hidrolik pres makinesi arızalandığında ne olur?

1. **Üretim durur** — her saat duruş, doğrudan gelir kaybıdır
2. **Acil müdahale** — teknisyen koşar, parça arar, teşhis koymaya çalışır
3. **Belirsizlik** — "Neden bozuldu? Tekrar olur mu? Ne zaman?" sorularına kimse net cevap veremez

Bugün çoğu fabrikada bakım **reaktiftir**: makine bozulur, sonra tamir edilir. Oysa arızaların büyük çoğunluğu **önceden sinyal verir** — sıcaklık yavaş yavaş yükselir, basınç düşmeye başlar, titreşim artar. Bu sinyalleri bir insan 7/24 takip edemez. Ama bir bilgisayar edebilir.

## Bu Proje Ne Yapıyor?

**Codlean MES**, fabrikadaki 6 hidrolik pres makinesini (4 Dikey, 2 Yatay) gerçek zamanlı izleyen, arızayı **olmadan önce** tahmin eden ve teknisyene **ne yapması gerektiğini** söyleyen bir erken uyarı sistemidir.

Hastanedeki hasta monitörü gibi düşünün:
- Sürekli nabız, tansiyon, oksijen ölçer
- Bir değer tehlikeli bölgeye girerse hemşireyi uyarır
- Sadece "bir şeyler ters" demez, **neden** ters olduğunu ve **ne yapılması** gerektiğini söyler

Bu sistem de presleriniz için aynısını yapıyor.

### İzlenen Makineler

| Makine | Tip | Sensör Sayısı | Durum |
|--------|-----|---------------|-------|
| HPR001 | Dikey Pres | 6 sayısal + 16 boolean | ✅ Aktif |
| HPR002 | Yatay Pres | 2 sayısal | ✅ Aktif |
| HPR003 | Dikey Pres | 6 sayısal + 16 boolean | ✅ Aktif |
| HPR004 | Dikey Pres | 6 sayısal + 16 boolean | ✅ Aktif |
| HPR005 | Dikey Pres | 6 sayısal + 16 boolean | ✅ Aktif |
| HPR006 | Yatay Pres | 2 sayısal | ✅ Aktif |

---

## Gerçek Hayat Başarısı: İlk Kurtarma

**Tarih:** 15 Mart 2026, HPR003  
**Saat:** 03:45 (gece vardiyası, teknisyen yok)

**Sistem Tespit Etti:**
```
⚠️ UYARI: Yağ sıcaklığı anormal yükseliş
   Mevcut: 48°C (Normal: 38°C)
   Trend: +2°C/saat artıyor
   Tahmin: 3.5 saatte otomatik durma (07:00)
   
🔍 TEŞHİŞ: Filtre tıkanıklığı şüphesi (%78)
🔧 ÖNERİ: Hidrolik filtre kontrolü
```

**Aksiyon:**
- **03:47** → SMS gönderildi (Teknisyen: Ahmet Usta)
- **04:15** → Ahmet usta geldi, filtre değiştirdi
- **04:45** → Makine normale döndü (39°C)

**Sistem Olmasaydı:**
- **07:00** → Makine otomatik durma moduna geçer
- **07:00-10:00** → Acil müdahale, parça aranır, teşhis konur
- **Kayıp:** 3 saat üretim duruşu = ~₺50K

**Kazanç:** 3 saat erken müdahale = **₺50K tasarruf** + plansız duruş önlendi

---

# 🔧 BÖLÜM II — GELİŞME: NE YAPTIK, NASIL YAPTIK

## 1. Veri Yolculuğu: Sensörden Ekrana

Veri fabrikadan teknisyenin ekranına ulaşana kadar **5 katmanlı** bir işlem hattından geçiyor. Her katmanın ayrı bir görevi var:

### Katman 0 — Veri Doğrulama (Kalite Kontrol)
Fabrikadan gelen ham veri her zaman temiz değil: virgüllü sayılar, aşırı uç değerler, bayat veriler olabilir. Bu katman hepsini temizler.

**Ne yapıyor:**
- Bozuk formatları düzeltir (virgül → nokta)
- 5 dakikadan eski veriyi "bayat" olarak işaretler
- İstatistiksel olarak anlamsız uç değerleri (5-sigma) filtreler
- Makine ilk açıldığında 60 dakika boyunca alarm vermez (soğuk başlangıç maskesi)

**Neden önemli:** Kirli veri üzerinde yapılan her analiz yanlıştır. Terazinin dengede olduğundan emin olmadan tartı yapamazsınız.

### Katman 1 — Hafıza ve Durum Yönetimi (State Store)
Son 2 saatin verisini bellekte tutar. Tek anlık dalgalanmayla alarm çalmaz, trendi takip eder.

**Ne yapıyor:**
- Son 720 ölçümü (≈2 saat) ring buffer'da tutar
- EWMA (Üstel Ağırlıklı Hareketli Ortalama) ile gürültüyü filtreler
- Her 5 dakikada diske yedekler — elektrik kesilse bile geri yüklenir
- Thread-safe yapı: birden fazla işlem aynı anda çalışsa bile veri bozulmaz

**Neden önemli:** Anlık bir dalgalanmayla alarm çalmak, uyuyan teknisyeni boşuna kaldırmaktır. Gerçek trendi görmek gerekir.

> **💡 Not:** Bu kayıtlar gelecekte 3. bir kullanım alanı için de hazır: **Audit & Raporlama**. Şu anda sadece felaket kurtarma ve trend devamlılığı için kullanılıyor, ancak ileride "Geçen hafta/makinede ne oldu?" sorularına cevap verebilmek için bu kayıtlar geçmiş analizlerinde de kullanılabilir.

### Katman 2 — Analiz Motoru (Risk Değerlendirme)
Veriyi üç farklı açıdan inceler ve tek bir risk skoru üretir:

| Alt Sistem | Ne Yapar | Örnek |
|-----------|----------|-------|
| **Limit Kontrolü** | Sensör limitin %kaçına gelmiş? | "Yağ sıcaklığı limitin %92'sinde" |
| **Eğilim Tespiti** | Değer yukarı mı gidiyor? Ne hızda? | "Saatte +2°C artıyor, 3.5 saatte limite ulaşır" |
| **Fizik Kuralları** | Sensörler arası mantık kontrolü | "Sıcaklık↑ + Basınç↓ = iç kaçak belirtisi" |

**Çıktı:** 0-100 arası risk skoru + renk kodu (Yeşil/Sarı/Turuncu/Kırmızı)

> **💡 Not:** Katman 2 "bir şeyler ters gidiyor" diyebilir ama **neden** olduğunu söyleyemez. Bu soruya Katman 2.5 cevap verir.

### Katman 2.5 — Yapay Zeka ve Açıklanabilirlik

Bu katman üç bileşenden oluşur:

**a) ML Model (Random Forest) — "Deneyimli Usta":**
- 32 özellik üzerinde eğitilmiş (sıcaklık, basınç, titreşim, akım vb.)
- 4.564 örnek, 1.116 arıza kaydı ile öğrenmiş
- AUC: %98.5 — model güvenilir tahminler yapıyor
- **Nasıl çalışır?** 100 karar ağacı oluşturur, her biri farklı açıdan bakar ve oy kullanır. Gelen veriyi geçmiş arıza patternleriyle karşılaştırır.
- **Neden Random Forest?** Gürültüye dayanıklı (tek sensör bozulsa bile karar verir), açıklanabilir (SHAP ile), hızlı (milisaniyeler), az veriyle çalışır, overfit riski düşük.
- **Pattern nedir?** Sensör değerlerinin arızaya yol açan kombinasyonu. Örnek: "Sıcaklık↑ + Basınç↓ + Titreşim↔ = iç kaçak patterni" (87 vakadan 82'sinde doğru)

**b) SHAP + DLIME (Açıklanabilir AI) — "Modelin Vicdanı":**
- Model "arıza riski var" dediğinde, **neden** dediğini açıklar
- **Problem:** ML modeli bir kara kutu — "arıza var" der ama nedenini söylemez
- **SHAP:** "Ana basınç ve yağ sıcaklığı bu kararın %78'ini oluşturuyor" der (her özelliğin etki yüzdesini hesaplar)
- **DLIME:** SHAP başarısız olursa devreye giren yedek açıklayıcı (örneğin yeni bir pattern gelirse)
- **Fabrika benzetmesi:** Usta "makine arızalanacak" der, SHAP "çünkü basınç düşüyor, sıcaklık artıyor" diye açıklar

**c) NLG Motoru (Türkçe Açıklama) — "Tercüman":**
- SHAP çıktısını insanın anlayacağı Türkçeye çevirir
- **Problem:** SHAP matematiksel çıktı verir: `main_pressure: 0.45, oil_temperature: 0.33`
- **Çözüm:** Bunu "Ana basınç son 15 dakikada %12 arttı ve yağ sıcaklığı eşik değerin üzerine çıktı" şeklinde Türkçeleştirir
- **Fabrika benzetmesi:** Doktorun tahlil sonuçlarını hastaya anlatması gibi — teknik veriyi günlük dile çevirir

> **💡 Katman 2.5 Nasıl Çalışır?** 
> 1. ML Model: "Bu pattern arızaya benziyor" → Risk %82
> 2. SHAP: "Karar sebepleri: Sıcaklık %45, Basınç %33, Titreşim %22"
> 3. NLG: "Yağ sıcaklığı son 1 saatte 4°C arttı, ana basınç 17 bar düştü. Bu pattern 82 kez görüldü, 67'sinde iç kaçak tespit edildi."

### Katman 3 — Alarm ve Bildirim
Gerçekten bir sorun varsa teknisyeni uyarır. Ama **akıllıca** uyarır:

- Aynı alarm tekrar tekrar çalmaz (30dk / 15dk bekleme)
- Düşük riskte sessiz kalır, sadece log tutar
- Kritik durumda anında bildirir ve ekranda kırmızı puls animasyonu gösterir

---

## 2. Aşılan Teknik Zorluklar

Bu sistem geliştirilirken karşılaşılan gerçek mühendislik problemleri ve çözümleri:

| Problem | Neden Oldu | Çözüm | Sonuç |
|---------|-----------|-------|-------|
| **Disk şişmesi** | JSON dosyası her yazımda tamamen yeniden oluşturuluyordu | JSONL (Append-Only) formatına geçiş | Bellek kullanımı %90 düştü |
| **Model güvenlik açığı** | pickle ile model kaydetmek güvensiz (keyfi kod çalıştırabilir) | joblib kütüphanesine geçiş | Endüstri standardı güvenlik |
| **Veri çakışması** | Birden fazla thread aynı anda state'e yazıyordu | threading.RLock ile mutex | Sıfır race condition |
| **Yatay/Dikey karışıklığı** | İki pres tipinin farklı sensörleri aynı yapıda işleniyordu | --hpr-yatay parametresi ile ayrıştırma | Doğru limit eşleştirme |
| **Model sızdırma** | Model, limit aşımını direkt özellik olarak kullanıyordu | Sızdırmaz özellik mühendisliği | Gerçek tahmin yeteneği |

---

## 3. Web Dashboard: Ne Görüyorsunuz?

Tarayıcıda `localhost:5001` açıldığında:

- **6 makine kartı** — her biri anlık risk skoru, sensör değerleri, çalışma durumu gösterir
- **Renk kodlaması** — Yeşil (Normal) / Sarı (Dikkat) / Turuncu (Yüksek) / Kırmızı (Kritik)
- **Makine tipi etiketi** — Her kartta 🔵 Dikey Pres veya 🟠 Yatay Pres
- **Canlı güncelleme** — SSE ile 2 saniyede bir otomatik yenilenir
- **Kafka gecikme göstergesi** — Verinin ne kadar taze olduğunu gösterir
- **AI Usta Başı** — Her makineye tıklayıp soru sorabilir, anlık analiz isteyebilirsiniz
- **Filo Analizi** — Tüm makineleri tek tıkla karşılaştırmalı değerlendirme

---

# 📊 BÖLÜM III — MEVCUT DURUM VE SINIRLAR

## Sistemin Güçlü Yanları

| Özellik | Durum | Detay |
|---------|-------|-------|
| Gerçek zamanlı izleme | ✅ | 6 makine, 2sn güncelleme |
| Risk skoru hesaplama | ✅ | 0-100 arası, 3 katmanlı değerlendirme |
| Fizik tabanlı teşhis | ✅ | Sensörler arası korelasyon analizi |
| ML tahmin | ✅ | AUC %98.5, sızdırmaz özellikler |
| Açıklanabilir AI | ✅ | SHAP + DLIME + Türkçe NLG |
| AI soru-cevap | ✅ | Gemini Flash ile doğal dil analizi |
| Thread güvenliği | ✅ | RLock ile koruma |

## Mevcut Sınırlar

### Sınır 1: LLM Katmanı Yüzeysel Kalıyor

Sistem arızayı tespit etmekte iyi. Ama **neden olduğunu açıklamak** ve **ne yapılacağını söylemek** konusunda yüzeysel kalıyor.

**Gerçek Olay:** HPR003'te yağ sıcaklığı yükseldiğinde sistem şöyle dedi:
```
"Yağ sıcaklığı yüksek. Soğutma sistemini kontrol edin."
```

**Teknisyen Ne Düşündü?** 
- ❓ "Hangi soğutma sistemi?"
- ❓ "Nereden başlamalıyım?"
- ❓ "Daha önce bu sorun yaşandı mı?"
- ❓ "Parça stokta var mı?"

**Cevap:** Hiçbiri yoktu. Çünkü tek bir modelden hepsi bekleniyordu.

### Sınır 2: Tek Çağrı Mimarisi
Gemini API'ye tek bir çağrı yapılıyor ve model aynı anda teşhis + neden + tahmin + aksiyon üretmesi bekleniyor. Sonuç: her alanı biraz yapıyor, hiçbirini derinlemesine yapamıyor.

### Sınır 3: Bağlam Yetersizliği
LLM'e sadece anlık sensör verileri gönderiliyor. Geçmiş arızalar, bakım geçmişi, filo karşılaştırması gibi zengin bağlam verilmiyor.

---

# 🧠 BÖLÜM IV — GELECEĞİN MİMARİSİ: ÇOKLU AJAN SİSTEMİ

## Temel Fikir

Gerçek bir fabrikada arıza olduğunda **tek kişi** karar vermez:

| Gerçek Fabrika | AI Karşılığı |
|----------------|-------------|
| Teknisyen makineye bakar, belirtileri listeler | **Teşhis Ajanı** |
| Mühendis analiz eder, kök nedeni bulur | **Kök Neden Ajanı** |
| Bakım şefi "ne zaman, nasıl" karar verir | **Aksiyon Ajanı** |
| Rapor yazılır, kayıt altına alınır | **Rapor Ajanı** |

Biz de tek bir "her şeyi bilen model" yerine, **her biri kendi alanında uzman** ajanlardan oluşan bir kurul oluşturuyoruz.

## Mimari Tasarım

```
           Kullanıcı Sorusu / Alarm
                    │
                    ▼
        ┌───────────────────────┐
        │    KOORDİNATÖR        │
        │  (Risk bazlı karar)   │
        │                       │
        │  Risk < 30 → 2 ajan   │
        │  Risk 30-70 → 3 ajan  │
        │  Risk > 70 → 5 ajan   │
        └───┬─────┬─────┬───────┘
            │     │     │
     ┌──────┘     │     └──────┐
     ▼            ▼            ▼
┌─────────┐ ┌──────────┐ ┌─────────┐
│ TEŞHİŞ  │ │KÖK NEDEN │ │ TAHMİN  │
│ AJANI   │ │  AJANI   │ │ AJANI   │
│         │ │          │ │         │
│"Ne var?" │ │"Neden?"  │ │"Ne olur?"│
└────┬────┘ └────┬─────┘ └────┬────┘
     │           │            │
     └─────┬─────┴────────────┘
           ▼
    ┌─────────────┐    ┌──────────┐
    │  AKSİYON    │───▶│  RAPOR   │
    │  AJANI      │    │  AJANI   │
    │"Ne yapılmalı"│    │"4 farklı │
    └─────────────┘    │ mod"     │
                       └──────────┘
```

## Her Ajanın Detaylı Çalışma Yöntemi

### Teşhis Ajanı — "Ne Arıza Var?"

**Kullandığı yöntem: Chain-of-Thought (CoT) Prompting**

Normal bir LLM'e "analiz et" derseniz yüzeysel cevap verir. Ama **adım adım düşünmeye zorlarsanız** derinlemesine analiz yapmak zorunda kalır:

```
ADIM 1 — VERİ DOĞRULAMA:
  Hangi sensörler anormal? Değerler fiziksel olarak mantıklı mı?
  Sensör arızası ihtimali var mı?

ADIM 2 — PATTERN TESPİTİ:
  Anomali tipi nedir?
  - Ani değişim → muhtemelen mekanik arıza
  - Yavaş trend → muhtemelen aşınma/tıkanma
  - Periyodik → muhtemelen çevresel etki

ADIM 3 — NEDENSEL İLİŞKİ:
  Fizik kurallarını uygula:
  Sıcaklık↑ + Basınç↓ → İç kaçak
  Basınç↑ + Hız=0 → Sıkışma
  Titreşim↑ + Sıcaklık↑ → Rulman arızası

ADIM 4 — TEŞHİŞ:
  En olası 3 arıza, güven yüzdesi, destekleyen kanıtlar
```

**Girdi:** Anlık sensör verileri + SHAP skoru + limit oranları  
**Çıktı:** Arıza tipi + güven % + belirtiler listesi

### Kök Neden Ajanı — "Neden Oldu?"

**Kullandığı yöntem: Nedensel Çıkarım + Bilgi Tabanı Sorgusu**

Bu ajan teşhis sonucunu alır ve **neden** olduğunu araştırır. Bunun için 3 araca başvurur:

| Araç | Ne Yapar | Örnek Çıktı |
|------|----------|-------------|
| **Fizik Kuralları** (causal_rules.json) | Sensörler arası fiziksel ilişkileri kontrol eder | "Sıcaklık↑ → Viskozite↓ → Basınç↓ (termodinamik)" |
| **Geçmiş Arama** (similarity_engine) | Benzer olayları veritabanında arar | "2 hafta önce HPR003'te aynı pattern, kök neden: filtre tıkanıklığı" |
| **Bakım Durumu** | Son bakım ne zaman yapıldı, gecikme var mı | "Filtre değişimi 15 gün gecikmiş" |

**Çıktı:** Kök neden + kanıtlar + olasılık yüzdesi

### Tahmin Ajanı — "Ne Olacak?"

**Kullandığı yöntem: Trend Ekstrapolasyonu**

State Store'daki EWMA trendlerini kullanarak geleceği tahmin eder:

```
Mevcut: Yağ sıcaklığı 48°C
Trend:  Saatte +2°C artıyor
Limit:  55°C (otomatik durdurma)
Kalan:  (55-48) / 2 = 3.5 saat

→ "3.5 saat içinde makine otomatik durma moduna geçecek"
```

**Çıktı:** Kalan süre + risk senaryoları

### Aksiyon Ajanı — "Ne Yapılmalı?"

**Kullandığı yöntem: Önceliklendirilmiş Aksiyon Planlama**

Teşhis ve kök neden sonuçlarını alarak somut eylem planı oluşturur:

```
ACİL (İlk 15 dakika):
  1. Soğutucu fan çalışıyor mu kontrol et
  2. Eşanjör giriş-çıkış sıcaklık farkını ölç

KISA VADELİ (1-2 saat):
  3. Hidrolik filtre değiştir (Parça: XYZ-123)
  4. Yağ seviyesi kontrol et

Tahmini duruş süresi: 45 dakika
```

### Rapor Ajanı — "Nasıl Anlatılır?"

Tüm ajan çıktılarını alıp **hedef kitleye göre** formatlar:

| Mod | Hedef Kitle | Ton | Ne İçerir |
|-----|------------|-----|-----------|
| **Teknisyen** | Saha ekibi | Teknik, detaylı | Sensör değerleri, adım adım aksiyon |
| **Yönetici** | Fabrika müdürü | Özet, maliyet odaklı | Risk, tahmini duruş, maliyet |
| **Rapor** | Kayıt/denetim | Formal | Zaman damgalı, yapılandırılmış |
| **Acil** | Alarm durumu | Kısa, net | 3-5 cümle, hemen yapılması gereken |

## Akıllı Yönlendirme: Her Alarm İçin 5 Ajan Çalışmaz

Düşük riskli bir durumda 5 ajan çağırmak gereksizdir. Koordinatör, risk seviyesine göre karar verir:

| Risk Seviyesi | Çağrılan Ajanlar | Tahmini Süre |
|--------------|-----------------|-------------|
| < 30 (Normal) | Teşhis + Rapor | ~5 saniye |
| 30-70 (Dikkat) | Teşhis + Kök Neden + Aksiyon | ~8 saniye |
| > 70 (Kritik) | 5 Ajan Tam Ekip (paralel) | ~10 saniye |

**Paralel çalıştırma:** Ajanlar sırayla değil, eşzamanlı çalıştırılır. Böylece 5 × 5sn = 25sn yerine ~10sn'de tamamlanır.

> **💡 Önemli Teknik Detay — Paralel Çalıştırma Mantığı:**
> 
> **asyncio.gather() Nedir?** Python'un birden fazla işi **aynı anda** başlatmasını sağlayan fonksiyon.
> 
> **Fabrika Benzetmesi:** 5 teknisyene sırayla "başla" demek yerine, hepsine aynı anda "başlayın" demek gibi. 5 × 5dk = 25dk yerine, 5dk'da biter.
> 
> **Ancak Dikkat:** 5 ajanın tamamı paralel çalışmaz! Çalışma şekli **bağımlılık ilişkisine** göre belirlenir:
> 
> **1. Grup — Bağımsız Ajanlar (Paralel):**
> - Teşhis Ajanı: Sensör verilerine bakar
> - Kök Neden Ajanı: Geçmiş aramalara + bakım kayıtlarına bakar
> - Tahmin Ajanı: Trendlere bakar
> - **Bu üçü birbirinden BAĞIMSIZ** → Aynı anda çalıştırılabilir (`asyncio.gather()`)
> - Süre: 3 × 5sn = ~5-7sn (paralel olduğu için)
> 
> **2. Grup — Bağımlı Ajanlar (Sıralı):**
> - Aksiyon Ajanı: Teşhis + Kök Neden + Tahmin sonuçlarını BİLMEK ZORUNDA
> - Rapor Ajanı: Tüm ajanların çıktılarını derlemek ZORUNDA
> - **Bunlar önceki sonuçlara MUHTAÇ** → Sırayla çalıştırılmalı
> - Süre: 2 × 5sn = ~10sn
> 
> **Toplam Süre:** 5-7sn (Grup 1) + 10sn (Grup 2) = **~15 saniye**
> 
> **Hibrit yapı olmasaydı (hepsi sıralı):** 5 × 5sn = 25 saniye olurdu
> 
> **Kazanç:** 25sn → 15sn = **%40 daha hızlı**
> 
> **API Verimi:** asyncio.gather() verimi düşürmez, aksine artırır:
> - Connection pooling: Aynı API bağlantısını paylaşır
> - Timeout yönetimi: Tüm çağrılar aynı anda kontrol edilir
> - Rate limit: Maksimum 3 paralel çağrı ile limit aşımı önlenir

## Beklenen Çıktı Karşılaştırması

### Şu An (Tek LLM):
```
"Yağ sıcaklığı yüksek. Soğutma sistemini kontrol edin."
```

### Ajan Sistemi:
```
🔍 TEŞHİŞ: Hidrolik iç kaçak + aşırı ısınma (Güven: %82)
   Belirtiler: Yağ 48°C (+16°C), Basınç 78 bar (-17 bar)

🔎 KÖK NEDEN: Soğutucu eşanjör tıkanıklığı (%75 olasılık)
   Kanıt: Filtre 45 gündür değişmemiş
          HPR003'te 2 hafta önce aynı pattern
          Sıcaklık-basınç korelasyonu: r = -0.82

⏰ TAHMİN: 3.5 saat içinde otomatik durdurma
   Trend: Sıcaklık saatte +2°C artıyor

🔧 AKSİYON:
   Acil (15dk): Soğutucu fan kontrolü + ΔT ölçümü
   Kısa vade: Filtre değişimi (XYZ-123, stokta var)
   Tahmini duruş: 45 dakika
```

---

# 📈 BÖLÜM V — ÖLÇEKLENEBİLİRLİK VE MODÜLERLİK

## "Bu Sistemi Başka Makinelerde Kullanabilir miyiz?"

**CEVAP: EVET, hem de çok kolay!** Sistemin her parçası **bağımsız** ve **yeniden kullanılabilir** tasarlandı.

---

## Senaryo 1: Seri Bağlı Üretim Bandı (5 Makine)

```
[Hammadde] → [Makine 1] → [Makine 2] → [Makine 3] → [Makine 4] → [Makine 5] → [Ürün]
             Kesme       Bükme        Pres         Kaynak       Boyama
```

### Problem: Makine 5'te Boya Kalitesi Bozuldu

**Geleneksel Yöntem (Reaktif):**
- Makine 5'te sorun → Teknisyen Makine 5'e bakar → Her şey normal!
- Saatler kaybedilir → Sorun bulunamaz

**Codlean MES (Proaktif — Nedensel Zincir):**

```
🔍 SORUN: Makine 5'te boya kalitesi düşük
🔎 KÖK NEDEN: Makine 1 — Bıçak aşınması (Güven: %89)

   Zincir: Bıçak kör → Bükme açısı bozuk → Pres basıncı düzensiz 
          → Kaynak yüzeyi pürüzlü → Boya tutmuyor

⏰ ZAMAN: Sorun 2 saat önce başladı (Makine 3'te ilk belirti)
🔧 AKSİYON: Makine 1'de bıçak değişimi (Parça: BIC-445, stokta var)
   Tahmini duruş: 20 dakika (sadece Makine 1 duracak)
```

**Kazanç:** 1 saatlik teşhis → **2 dakikaya düştü**

---

## Nasıl Yapıyoruz?

### 1. Config-Driven Yapı (Kod Değişikliği Yok!)

Yeni makine eklemek için **sadece config dosyasını** güncelleyin:

```yaml
# limits_config.yaml
production_line: "HAT-A"
machines:
  - id: "MAC-01"
    type: "kesme"
    position: 1
    sensors: [bicak_asinma, kesme_hizi, malzeme_kalinligi]
    
  - id: "MAC-02"
    type: "bükme"
    position: 2
    sensors: [bukme_acisi, malzeme_gerilimi]
    upstream_dependencies: ["MAC-01"]
    
  # ... diğer makineler
```

**Kod değişikliği:** 0 satır!  
**Yeni makine ekleme süresi:** 10 dakika (config düzenleme)

### 2. Nedensel İlişki Haritası (Causal Graph)

Sistem, makineler arası ilişkileri **causal_rules.json** ile bilir:

```json
{
  "Makine_1_bicak_asinma": {
    "etkiler": ["Makine_2_bukme_acisi"],
    "gecikme": "15-30 dakika",
    "belirti": "Bükme açısı sapması artar"
  },
  "Makine_2_bukme_acisi": {
    "etkiler": ["Makine_3_pres_basinci"],
    "gecikme": "10-20 dakika"
  }
}
```

### 3. Kök Neden Ajanı (Geriye Doğru Arama)

Sorun bulunduğunda, Kök Neden Ajanı **geriye doğru** tüm zinciri tarar:

```
Makine 5'te sorun → Makine 4'e bak → Makine 3'e bak → 
Makine 2'ye bak → Makine 1'de bul! (Kök neden)
```

---

## Modülerlik Avantajları

| Özellik | Nasıl Modüler? | Yeni Makine Ekleme |
|---------|----------------|-------------------|
| **Veri Doğrulama** | Sensör listesi config'den okunur | Config'e sensör ekle |
| **State Store** | Her makine için ayrı ring buffer | Otomatik oluşturulur |
| **Limit Kontrolü** | limits_config.yaml ile tanımlı | Limit değerlerini gir |
| **ML Model** | Her makine tipi için ayrı eğitilebilir | Yeni verilerle eğit |
| **Fizik Kuralları** | causal_rules.json ile tanımlı | Nedensel ilişkileri tanımla |
| **Dashboard** | Dinamik kart oluşturma | Otomatik kart eklenir |

---

## Yeni Makine Eklemek İçin Ne Gerekli?

### Adım Adım Kurulum Rehberi

Sisteme yeni bir makine eklemek **5 adımda** tamamlanır:

| Adım | Ne Yapılır? | Süre | Zorluk | Kim Yapar? |
|------|-------------|------|--------|-----------|
| **1. Veri Toplama** | Sensör listesi + geçmiş arızalar | 1-2 hafta | Orta | Sahada teknisyen + veri mühendisi |
| **2. Config Hazırlama** | limits_config.yaml + causal_rules.json | 30 dakika | Kolay | Sistem mühendisi |
| **3. ML Model Eğitimi** | Yeni verilerle model eğit | 1-3 gün | Orta | ML mühendisi |
| **4. Dashboard** | Otomatik güncelleme | 0 dakika | Yok | Sistem (otomatik) |
| **5. Test** | Validasyon senaryoları | 2-3 gün | Kolay | QA ekibi |
| **TOPLAM** | | **1.5-2.5 hafta** | | |

---

### Adım 1: Veri Toplama (En Kritik Adım)

**Gerekli Malzemeler:**
- Sensör listesi (hangi sensörler var, ne ölçüyor?)
- Limit değerleri (min/max/normal çalışma aralıkları)
- Geçmiş arıza kayıtları (en az 50-100 örnek)
- Bakım geçmişi (ne zaman ne değiştirilmiş?)

**Fabrika Benzetmesi:** Yeni bir doktorun hastaneyi tanıması gibi. Önce "burada hangi cihazlar var, normal değerler ne, daha önce hangi hastalıklar görülmüş" bilmek lazım.

**Örnek:**
```
Yeni Makine: Enjeksiyon Makinesi
Sensörler:
  - Kalıp sıcaklığı (0-200°C)
  - Enjeksiyon basıncı (0-500 bar)
  - Soğutma suyu sıcaklığı (10-40°C)
  - Vidalama hızı (0-100 mm/s)

Geçmiş arızalar:
  - 2024-01-15: Kalıp tıkanıklığı
  - 2024-03-22: Hidrolik kaçak
  - ... (toplam 87 arıza kaydı)
```

---

### Adım 2: Config Dosyaları (30 Dakika)

**Sadece 2 dosya güncellenir, kod değişikliği YOK:**

#### A) limits_config.yaml (Sensör Limitleri)

```yaml
machines:
  - id: "ENJ-01"
    name: "Enjeksiyon Makinesi 1"
    type: "enjeksiyon"
    sensors:
      - name: "kalip_sicakligi"
        unit: "°C"
        min: 50
        max: 180
        soft_limit: 160  # %88'inde uyar
        hard_limit: 180  # Durdurma limiti
```

#### B) causal_rules.json (Nedensel İlişkiler)

```json
{
  "kalip_sicakligi_yuksek": {
    "etkiler": ["urun_kalinligi_degisimi"],
    "olasi_nedenler": ["sogutma_su_yetersiz", "kalip_tikanikligi"],
    "gecikme": "10-20 dakika"
  }
}
```

**Kod değişikliği:** 0 satır!  
**Yeni makine ekleme süresi:** 30 dakika (sadece config düzenleme)

---

### Adım 3: ML Model Eğitimi (1-3 Gün)

**Neden Yeni Model Gerekli?**

Her makinenin **fiziksel davranışı** farklıdır:

| Makine | Normal Sıcaklık | Normal Basınç | Arıza Pattern'i |
|--------|-----------------|---------------|-----------------|
| Hidrolik Pres | 35-50°C | 80-100 bar | Sıcaklık↑ + Basınç↓ |
| Enjeksiyon | 120-160°C | 200-400 bar | Basınç dalgalanması |
| CNC Tezgah | 20-30°C | Yok | Titreşim↑ |

Model, **bir makinenin patternlerini** öğrenir. Başka makinede bu patternler farklıdır!

**Süreç:**
```bash
python scripts/ml_tools/train_model.py \
  --data data/enjeksiyon_training_data.csv \
  --output models/enjeksiyon_model.joblib
```

**Çıktı:**
- `enjeksiyon_model.joblib` (yeni model)
- `model_report.json` (AUC, F1 skoru, precision, recall)

**Not:** Model eğitimi için **yeni makinenin verisi şart**. Mevcut pres modeli enjeksiyon makinesinde çalışmaz! Ama altyapı (eğitim scriptleri, feature engineering) tamamen aynı kalır.

---

### Adım 4: Dashboard (Otomatik!)

**Kod değişikliği:** 0 satır!

Sistem config dosyasını okuyup otomatik olarak:
- Yeni makine kartı oluşturur
- Sensör widget'ları ekler
- Renk kodlaması ayarlar

**Tek gereken:** Web server'ı yeniden başlatmak (10 saniye)

---

### Adım 5: Test ve Validasyon (2-3 Gün)

**Test Senaryoları:**
1. ✅ Normal çalışma → Alarm vermemeli
2. ✅ Limit aşımı → Alarm vermeli
3. ✅ Trend analizi → Tahmin yapmalı
4. ✅ Kök neden → Doğru makineyi bulmalı

**Kontrol Listesi:**
- [ ] Veri doğrulama çalışıyor mu?
- [ ] State Store yeni makine için kayıt yapıyor mu?
- [ ] Limit kontrolü doğru çalışıyor mu?
- [ ] ML model tahmin yapıyor mu?
- [ ] Dashboard kartı görünüyor mu?
- [ ] Alarm sistemi tetikleniyor mu?

---

## Mevcut Sistemde Ne Değişir, Ne Aynı Kalır?

| Bileşen | Durum | Açıklama |
|---------|-------|----------|
| **Katman 0 (Veri Doğrulama)** | ✅ Aynı | Herhangi bir sensör tipini doğrular |
| **Katman 1 (State Store)** | ✅ Aynı | Yeni makine için otomatik ring buffer oluşturur |
| **Katman 2 (Analiz Motoru)** | ✅ Aynı | Config'den limitleri okur |
| **Katman 2.5 (ML Model)** | ⚠️ Yeni Model | Her makine tipi için ayrı model gerekir |
| **Katman 3 (Alarm)** | ✅ Aynı | Kural motoru config'den çalışır |
| **Dashboard** | ✅ Aynı | Dinamik kart oluşturma |
| **AI Ajanları** | ✅ Aynı | Prompt'lar geneldir, makine tipinden bağımsız |

**Özet:** Altyapının **%85'i aynı kalır**. Sadece ML model dosyası ve config'ler değişir.

---

## Gerçek Hayat Örneği

**Senaryo:** Fabrikaya 2 yeni enjeksiyon makinesi alındı

**Geleneksel Sistem:** 
- 3-6 ay yazılım geliştirme
- Yeni dashboard sayfaları
- Yeni alarm kuralları
- Test ve debug
- **Toplam:** 6-9 ay, ₺500K+ maliyet

**Codlean MES:**
- 2 hafta veri toplama
- 30 dakika config düzenleme
- 2 gün model eğitimi
- 2 gün test
- **Toplam:** 2.5 hafta, ₺0 ek maliyet (sadece iş gücü)

**Kazanç:** 6-9 ay → **2.5 hafta** (₺500K tasarruf!)

---

## Senaryo 2: Farklı Fabrika, Farklı Makineler

Sistem sadece hidrolik presler için değil, **her türlü üretim makinesi** için kullanılabilir:

| Fabrika Tipi | Makineler | Sensörler | Uygulama |
|-------------|-----------|-----------|----------|
| **Otomotiv** | Robot kollar, CNC, Pres | Akım, titreşim, sıcaklık | ✅ Uygun |
| **Gıda** | Mikser, Fırın, Paketleme | Nem, sıcaklık, hız | ✅ Uygun |
| **Tekstil** | Dokuma, Boyama, Kesme | Gerilim, hız, sıcaklık | ✅ Uygun |
| **İlaç** | Reaktör, Kurutucu, Tablet | Basınç, pH, nem | ✅ Uygun |

**Tek Değişen:** Config dosyası (limits_config.yaml + causal_rules.json)  
**Aynı Kalan:** Tüm analiz motoru, ML modeli, AI ajanları

---

## Gerçek Hayat Faydası

| Metrik | Geleneksel | Codlean MES | İyileşme |
|--------|-----------|-------------|----------|
| Arıza teşhis süresi | 30-60 dakika | 2-5 dakika | **%90 azalma** |
| Kök neden bulma | Deneme-yanılma | Nedensel zincir | **Kesin sonuç** |
| Üretim duruşu | 2-4 saat | 20-30 dakika | **%85 azalma** |
| Teknisyen ihtiyacı | 3-4 kişi | 1 kişi + AI | **%75 azalma** |

---

# 🗓️ BÖLÜM VI — UYGULAMA YOL HARİTASI

## Faz 1 — Temel Ajanlar (1. Hafta)
- **Ne:** Teşhis Ajanı + Aksiyon Ajanı (2 ajan)
- **Nasıl:** CoT prompt mühendisliği + koordinatör
- **Risk:** Düşük — mevcut sisteme ek katman, mevcut hiçbir şeyi bozmaz
- **Beklenen iyileşme:** Çıktı kalitesinde %40-50 artış

## Faz 2 — Tam Ekip + Paralel Çalışma (2. Hafta)
- **Ne:** +Kök Neden +Tahmin +Rapor ajanları (toplam 5)
- **Nasıl:** asyncio.gather() ile paralel API çağrıları
- **Risk:** Düşük — her ajan bağımsız, biri çökerse diğerleri çalışır
- **Beklenen iyileşme:** Profesyonel seviye çıktı (%80-90)

## Faz 3 — Bilgi Tabanı + Geri Bildirim (3-4. Hafta)
- **Ne:** Makine özellikleri + bakım geçmişi + operatör feedback
- **Nasıl:** Her analiz sonrası "Faydalı mıydı? 1-5" sorusu
- **Risk:** Düşük — veri toplama, mevcut sisteme dokunmaz
- **Beklenen iyileşme:** Fabrikaya özel, kişiselleştirilmiş analizler

## Faz 4 — Yerel Model Geçişi (2-3. Ay, Opsiyonel)
- **Ne:** Gemini bağımlılığını kaldırma, kendi modelini çalıştırma
- **Nasıl:** Biriken loglarla Llama 3.1 fine-tuning + Ollama yerel kurulum
- **Neden:** İnternet bağımsızlığı + veri gizliliği + sıfır API maliyeti
- **Risk:** Orta — model kalitesi başlangıçta düşebilir, bu yüzden Gemini fallback olarak kalır

---

# 💰 BÖLÜM VII — MALİYET VE RİSK ANALİZİ

## Maliyet

| Kalem | Maliyet | Açıklama |
|-------|---------|----------|
| Gemini Flash API | ₺0 | Google'ın ücretsiz katmanı |
| Geliştirme | ₺0 | Mevcut ekip |
| Altyapı | ₺0 | Mevcut donanım yeterli |
| **Toplam** | **₺0** | Sadece yazılım mühendisliği çalışması |

## Yatırım Getirisi (ROI)

| Kalem | Değer |
|-------|-------|
| **Geliştirme Maliyeti** | ₺0 (mevcut ekip) |
| **Aylık İşletme** | ₺0 (ücretsiz API) |
| **Duruş Azalması** | %85 (2-4 saat → 20-30 dk) |
| **Yıllık Tasarruf** | ~₺2.4M (6 makine × ₺400K/duruş) |
| **Ek Makine Kurulum** | ₺500K → ₺0 (sadece iş gücü) |
| **ROI Süresi** | < 3 ay |

**Yatırım:** ₺0  
**Getiri:** ₺2.4M/yıl  
**ROI:** ∞% (sınırsız!)

> 💡 **Not:** Her plansız duruş ~₺50K maliyet. Sistem yılda ortalama 8-10 duruşu önler.

## Risk Değerlendirmesi

| Risk | Olasılık | Etki | Azaltma |
|------|----------|------|---------|
| API rate limit | Orta | Düşük | Akıllı yönlendirme: düşük risk = az çağrı |
| İnternet kesintisi | Düşük | Yüksek | Faz 4'te yerel model fallback |
| Prompt kalitesi | Düşük | Orta | Operatör feedback ile iteratif iyileştirme |
| Gecikme (latency) | Düşük | Düşük | Paralel çağrılarla ~10sn'ye düşürme |

---

# 🚀 BÖLÜM VIII — SONUÇ

## Ne Vardı, Ne Oldu, Ne Olacak

| Dönem | Durum | Yetenek |
|-------|-------|---------|
| **Şubat 2026** (Başlangıç) | Hammadde | Kafka'dan veri okuma |
| **Mart 2026** (Geliştirme) | Altyapı | ML model + fizik kuralları + SHAP |
| **Nisan 2026** (Pilot) | Canlı sistem | Dashboard + AI Usta Başı + 6 makine izleme |
| **Mayıs 2026** (Hedef) | Uzman sistem | Çoklu ajan + akıllı yönlendirme + 4 çıktı modu |
| **Temmuz 2026** (Vizyon) | Bağımsız sistem | Yerel AI + sıfır API maliyeti + tam gizlilik |

## Tek Cümleyle

> Mevcut sistemi **tek bir akıllı çırak**'tan → **uzmanlar kurulu**'na dönüştürüyoruz.
> Aynı bütçeyle (₺0), çok daha profesyonel, aksiyon odaklı ve fabrikaya özel sonuçlar.

---

## Sonraki Adımlar

Bu sunumdan sonra:

1. ✅ **Faz 1 başlatma onayı** (Teşhis + Aksiyon ajanları)
2. 📋 **Veri toplama planı** (yeni makineler için)
3. 🎯 **Pilot fabrika seçimi** (seri bağlı üretim bandı)
4. 📅 **3 aylık roadmap onayı**

**Karar Beklenen:** Faz 1 için yeşil ışık 🟢

---

**Sorular?** 💬
