# Codlean MES — Gelecek Planları ve Yol Haritası

**Doküman Tarihi:** 30 Nisan 2026  
**Versiyon:** 1.0  
**Yazar:** R. Ahsen Çiçek  
**Toplantı Tarihi:** 30 Nisan 2026

---

## 📌 Doküman Amacı

Bu doküman, Codlean MES sisteminin **gelecek geliştirme planlarını**, **LLM stratejisini**, **mimari kararları** ve **uzun vadeli vizyonunu** detaylı olarak açıklar.

Toplantılarda referans olarak kullanılabilir, yeni ekip üyelerine sistemi tanıtmak için kaynak olabilir.

---

## 1. MEVCUT DURUM ANALİZİ

### 1.1 Bugün Neredeyiz?

**✅ Tamamlananlar:**

| Özellik | Durum | Açıklama |
|---------|-------|----------|
| **Multi-Agent AI** | ✅ Canlı | 5 uzman ajan paralel çalışıyor |
| **API Fallback** | ✅ Canlı | Gemini → Groq otomatik geçiş |
| **Dashboard** | ✅ Canlı | Gerçek zamanlı monitoring |
| **API Key Tracking** | ✅ Canlı | 750 istek/gün kapasite |
| **Cache Sistemi** | ✅ Canlı | 10 dakika önbellek |
| **Responsive UI** | ✅ Canlı | Desktop + Mobile |
| **Dokümantasyon** | ✅ Tamamlandı | FAZ6_MULTI_AGENT_SISTEMI.md |

**⚠️ Kısmi Tamamlananlar:**

| Özellik | Durum | Eksik |
|---------|-------|-------|
| **Context Builder** | ⚠️ Kısmi | Sadece sensör verisi var |
| **Prompt Kalitesi** | ⚠️ Orta | 1-2 cümle yerine 10-15 hedefleniyor |
| **Feedback Sistemi** | ⚠️ Planlandı | Kod yazılmadı |
| **Fleet Comparison** | ⚠️ Planlandı | Dashboard'da yok |

**❌ Yapılacaklar:**

- Context Builder'a 5 modül ekleme
- Prompt optimizasyonu
- Feedback UI + backend
- Export özellikleri (PDF, CSV, Email)
- Performance monitoring
- LLM model stratejisi

---

## 2. LLM STRATEJİSİ (Kritik Kararlar)

### 2.1 Mevcut LLM Yapısı

```
ŞU AN:
├── Gemini 2.5 Flash (Google)
│   ├── 10 API key
│   ├── 20 istek/key/gün
│   └── TOPLAM: 200 istek/gün
│
└── Groq Llama 3.3 70B (Meta)
    ├── 11 API key
    ├── 50 istek/key/gün
    └── TOPLAM: 550 istek/gün

GENEL TOPLAM: 750 API çağrısı/gün
```

### 2.2 LLM Değerlendirme Matrisi

| Model | Ücretsiz Limit | Türkçe | Mantık | Hız | Öneri |
|-------|---------------|--------|--------|-----|-------|
| **Gemini 2.5 Flash** | 200/gün | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | **Ana model** |
| **Groq Llama 3.3 70B** | 550/gün | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | **Fallback + yüksek volume** |
| **DeepSeek-R1** | 1M token/gün | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | **İleride eklenebilir** |
| **Claude 3.5 Sonnet** | 500K token/gün | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | **İleride eklenebilir** |
| **Ollama (Lokal)** | ∞ (sınırsız) | ⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | **Şu an GEREKSIZ** |

### 2.3 Neden Lokal Model (Ollama) Şimdi DEĞİL?

**Avantajları:**
- ✅ Sınırsız kullanım (API limit yok)
- ✅ Veri gizliliği (cloud'a gitmiyor)
- ✅ Offline çalışabilir

**Dezavantajları (KRİTİK):**
- ❌ **Donanım gereksinimi:** 70B model = 40GB RAM + güçlü GPU
- ❌ **Türkçe kalitesi düşük:** Eğitim verisi az
- ❌ **Mantık zayıf:** Karmaşık çıkarım yapamıyor
- ❌ **Bakım zor:** Model güncellemeleri manuel
- ❌ **Yavaş:** GPU yoksa 30-60 saniye yanıt süresi

**Karar:** 
> **Şu an için cloud API'lar (Gemini + Groq) YETERLI.**
> Lokal model ancak:
> - API maliyetleri artarsa (günde 1000+ istek)
> - Veri gizliliği zorunlu olursa (fabrika politikası)
> - Donanım altyapısı hazır olursa
> 
> ...o zaman düşünülmeli.

### 2.4 İlerideki LLM Mimari Seçenekleri

#### SEÇENEK A: Mevcut Yapıyı Koru (ÖNERİLEN)
```
Gemini (kritik analizler) + Groq (yüksek volume)
```
**Artılar:**
- ✅ Basit, bakımı kolay
- ✅ 750 istek/gün yeterli (şimdilik)
- ✅ Türkçe mükemmel
- ✅ Maliyet: 0₺ (ücretsiz tier)

**Eksiler:**
- ❌ Limit dolunca bekleme gerekiyor
- ❌ Cloud bağımlılığı

**Ne zaman yeterli olur?**
- Günlük < 500 API çağrısı
- 10'dan fazla makine yok
- Gerçek zamanlı PDF rapor üretimi gerekmiyor

---

#### SEÇENEK B: DeepSeek-R1 Ekle (ORTA VADE)
```
Gemini (Türkçe) + Groq (hız) + DeepSeek (derin analiz)
```
**Artılar:**
- ✅ 1M token/gün (ÇÖMERT!)
- ✅ Matematik + mantık çok güçlü
- ✅ Açık kaynak, özelleştirilebilir

**Eksiler:**
- ❌ API entegrasyonu lazım (yeni kod)
- ❌ Fallback mekanizması karmaşıklaşır
- ❌ Test süresi uzar

**Ne zaman eklenmeli?**
- 750 istek/gün yetmemeye başlayınca
- PDF/rapor analizi ihtiyacı doğunca
- Derin kök neden analizi gerekince

---

#### SEÇENEK C: Hibrit Cloud + Lokal (UZUN VADE)
```
Cloud (Gemini/Groq/DeepSeek) → Kritik analizler
Lokal (Ollama) → Basit sınıflandırma, format kontrol
```
**Artılar:**
- ✅ API kotası korunur (basit işler lokal)
- ✅ Veri gizliliği (ham veri cloud'a gitmez)
- ✅ Hız (lokal yanıtlar anında)

**Eksiler:**
- ❌ Donanım yatırımı gerekli (GPU sunucu)
- ❌ Mimari karmaşık
- ❌ Bakım maliyeti yüksek

**Ne zaman düşünülmeli?**
- Fabrika veri gizliliği politikası değişirse
- 50+ makine izleniyorsa
- API maliyetleri aylık 1000₺'yi geçerse

---

### 2.5 LLM Stratejisi Özeti

| Zaman | Yapı | Kapasite | Maliyet |
|-------|------|----------|---------|
| **ŞIMDI (Nisan 2026)** | Gemini + Groq | 750/gün | 0₺ |
| **3 AY SONRA** | + DeepSeek-R1 | 2M token/gün | 0₺ |
| **6 AY SONRA** | + Feedback analizi | - | 0₺ |
| **1 YIL SONRA** | ? (karar verilecek) | - | ? |

**KARAR NOKTASI (3 ay sonra):**
```
Eğer:
- Günlük API kullanımı > 600 ise
- Kullanıcılar "daha detaylı rapor" istiyorsa
- PDF/Excel export gerekiyorsa

→ DeepSeek-R1 ekle!

Aksi halde:
- Mevcut yapıyı koru
- Sadece prompt optimizasyonu yap
```

---

## 3. GELIŞTIRME PLANLARI (Detaylı)

### FAZA 1: Context Zenginleştirme (1-2 Hafta)

**Öncelik:** ⭐⭐⭐⭐⭐ (EN YÜKSEK)

**Neden?** AI ancak zengin veriyle iyi analiz yapabilir. Şu an sadece sensör verisi var, bu yetersiz!

#### 1.1 Makine Profili Modülü

**Dosya:** `src/analysis/machine_profile.py` (zaten var, entegre edilecek)

**Veri Kaynağı:** `data/machine_profiles.json`

**Veri Yapısı:**
```json
{
  "HPR001": {
    "model": "Dikey Hidrolik Pres",
    "manufacturer": "XYZ Makina",
    "installation_date": "2023-10-15",
    "age_years": 2.5,
    "total_operating_hours": 18500,
    "capacity_tons": 500,
    "known_issues": [
      "Ana basınç valfi aşınması (2026-03)",
      "Yağ soğutucu verim düşüşü (2026-01)"
    ],
    "warranty_expiry": "2025-10-15",
    "last_calibration": "2026-04-15",
    "next_calibration_due": "2026-07-15",
    "sensor_specifications": {
      "oil_tank_temperature": {"range": "0-100°C", "accuracy": "±0.5°C"},
      "main_pressure": {"range": "0-150 bar", "accuracy": "±1 bar"}
    }
  }
}
```

**Context Builder Entegrasyonu:**
```python
# pipeline/context_builder.py içinde:
from src.analysis.machine_profile import MachineProfileManager

profile_mgr = MachineProfileManager()
profile = profile_mgr.get_profile(machine_id)

context["machine_profile"] = {
    "age_years": profile.age_years,
    "total_hours": profile.total_operating_hours,
    "known_issues": profile.known_issues,
    "last_calibration": profile.last_calibration
}
```

**Ajan Bu Veriyi Nasıl Kullanır?**
> "HPR001 2.5 yaşında ve ana valf aşınması bilinen bir sorun. 
>  18,500 saat çalışma sonrası bu aşınma normal.
>  Bugünkü basınç düşüşü (98.2 → 85 bar) bu aşınmayla doğrudan ilişkili."

---

#### 1.2 Bakım Geçmişi Modülü

**Dosya:** `src/analysis/maintenance_history.py` (zaten var)

**Veri Kaynağı:** `data/maintenance_log.json`

**Veri Yapısı:**
```json
{
  "HPR001": [
    {
      "date": "2026-04-15",
      "type": "planlı_bakım",
      "technician": "Ahmet Yılmaz",
      "tasks": [
        {"name": "valf_kontrol", "status": "tamamlandı", "notes": "aşınma tespit edildi"},
        {"name": "yağ_seviyesi", "status": "tamamlandı", "notes": "normal"}
      ],
      "next_due": "2026-05-15",
      "cost": 1500
    },
    {
      "date": "2026-03-20",
      "type": "arıza_bakımı",
      "technician": "Mehmet Demir",
      "tasks": [
        {"name": "filtre_degisimi", "status": "tamamlandı", "notes": "tıkanmıştı"}
      ],
      "downtime_hours": 4,
      "cost": 800
    }
  ]
}
```

**Context Builder Entegrasyonu:**
```python
from src.analysis.maintenance_history import MaintenanceHistory

maint = MaintenanceHistory()
context["maintenance_history"] = {
    "last_date": maint.get_last_date(machine_id),
    "days_since": maint.days_since_last_maintenance(machine_id),
    "overdue_tasks": maint.get_overdue_maintenance(machine_id),
    "recent_records": maint.get_recent_records(machine_id, limit=3),
    "avg_downtime": maint.get_avg_downtime(machine_id)
}
```

**Ajan Bu Veriyi Nasıl Kullanır?**
> "Son bakım 15 gün önce yapılmış ama valf aşınması not edilmiş.
>  O tarihte değişiklik yapılmamış, sadece izlenmiş.
>  Bu, bugünkü basınç düşüşünü açıklıyor - valf zamanla daha da aşınmış."

---

#### 1.3 Envanter Durumu Modülü

**Dosya:** `src/analysis/inventory_manager.py` (zaten var)

**Veri Kaynağı:** `data/inventory.json`

**Veri Yapısı:**
```json
{
  "consumables": [
    {
      "name": "Hidrolik Yağ ISO-46",
      "current_stock": 50,
      "unit": "litre",
      "minimum_stock": 20,
      "reorder_level": 30,
      "supplier": "Petrol Ofisi",
      "lead_time_days": 3,
      "cost_per_unit": 45
    },
    {
      "name": "Yağ Filtresi HF-2024",
      "current_stock": 2,
      "unit": "adet",
      "minimum_stock": 5,
      "reorder_level": 8,
      "supplier": "Bosch Rexroth",
      "lead_time_days": 7,
      "cost_per_unit": 120
    }
  ],
  "critical_parts": [
    {
      "name": "Ana Basınç Valfi Contası",
      "current_stock": 0,
      "unit": "adet",
      "minimum_stock": 2,
      "lead_time_days": 14,
      "cost_per_unit": 850,
      "status": "SİPARİŞ GEREKLİ"
    }
  ]
}
```

**Context Builder Entegrasyonu:**
```python
from src.analysis.inventory_manager import InventoryManager

inventory = InventoryManager()
context["inventory_status"] = {
    "low_stock_alerts": inventory.get_low_stock_alerts(),
    "critical_parts_missing": inventory.get_critical_parts_missing(),
    "available_for_repair": inventory.get_available_parts(machine_id)
}
```

**Aksiyon Ajanı Bu Veriyi Nasıl Kullanır?**
> "ÖNERİ 1: Ana basınç valfi contasını değiştir
>  - STOKTA YOK! (0 adet)
>  - Sipariş süresi: 14 gün
>  - Maliyet: 850₺
>  - Acil sipariş ver!
>
>  GEÇİÇİ ÇÖZÜM: Basınç limitini %80'e düşür (95 → 76 bar)
>  - Bu şekilde 2 hafta idare edilebilir
>  - Ama verim %15 düşer"

---

#### 1.4 Filo Karşılaştırma Modülü

**Dosya:** Yeni oluşturulacak: `src/analysis/fleet_comparison.py`

**Veri Kaynağı:** `state.json` (canlı veri)

**Veri Yapısı:**
```python
{
    "machines": {
        "HPR001": {
            "oil_temp": 42.5,
            "main_pressure": 98.2,
            "status": "critical",
            "risk_score": 72.5
        },
        "HPR002": {
            "oil_temp": 35.1,
            "main_pressure": 82.0,
            "status": "normal",
            "risk_score": 15.2
        },
        # ... HPR003-006
    },
    "fleet_averages": {
        "avg_temp": 37.2,
        "avg_pressure": 85.4,
        "avg_risk_score": 32.1
    },
    "rankings": {
        "worst_machine": "HPR001",
        "best_machine": "HPR002",
        "most_improved": "HPR004",
        "most_degraded": "HPR001"
    }
}
```

**Context Builder Entegrasyonu:**
```python
from src.analysis.fleet_comparison import FleetComparison

fleet = FleetComparison()
context["fleet_comparison"] = fleet.build_comparison()
```

**Ajan Bu Veriyi Nasıl Kullanır?**
> "HPR001'in sıcaklığı (42.5°C) filo ortalamasının (37.2°C) 
>  5.3°C üstünde. Bu makine filodaki EN KÖTÜ durumda.
>  
>  HPR002 ise en iyi durumda (35.1°C, risk skoru 15.2).
>  
>  Karşılaştırma: HPR001, HPR002'ye göre:
>  - Sıcaklık: +7.4°C daha yüksek
>  - Basınç: +16.2 bar daha yüksek
>  - Risk: +57.3 puan daha yüksek
>  
>  Bu makineye ACİL müdahale edilmeli."

---

#### 1.5 Operatör Feedback İstatistikleri

**Dosya:** `src/analysis/feedback_system.py` (zaten var)

**Veri Kaynağı:** `data/feedback_log.jsonl`

**Veri Yapısı:**
```json
{"report_id": "RPT-20260430-103000-HPR001", "machine_id": "HPR001", "rating": 4, "accuracy": "mostly_correct", "user_note": "Valf aşınması teşhisi doğruydu", "timestamp": "2026-04-30T11:00:00Z"}
{"report_id": "RPT-20260429-150000-HPR003", "machine_id": "HPR003", "rating": 5, "accuracy": "correct", "user_note": "Tam isabet!", "timestamp": "2026-04-29T15:30:00Z"}
```

**Context Builder Entegrasyonu:**
```python
from src.analysis.feedback_system import FeedbackSystem

feedback = FeedbackSystem()
context["feedback_stats"] = {
    "avg_rating": feedback.get_avg_rating(machine_id),
    "accuracy_rate": feedback.get_accuracy_rate(machine_id),
    "total_feedbacks": feedback.get_total_count(machine_id),
    "common_corrections": feedback.get_common_corrections(machine_id)
}
```

**Ajan Bu Veriyi Nasıl Kullanır?**
> "Geçmişte HPR001 için 23 feedback alındı, ortalama puan 4.2/5.
>  Teşhis doğruluk oranı: %87.
>  
>  En sık yapılan düzeltme: 'Parça önerileri güncel değil'
>  → Bu sefer envanter durumunu kontrol ettim, stok bilgisi dahil edildi."

---

### FAZA 2: Prompt Optimizasyonu (3-5 Gün)

**Öncelik:** ⭐⭐⭐⭐⭐

**Hedef:** AI çıktılarını 1-2 cümleden 10-15 cümleye çıkarmak, derin analiz sağlamak.

#### 2.1 Teşhis Ajanı Prompt Güncelleme

**Dosya:** `src/analysis/diagnosis_agent.py` → `_build_diagnosis_prompt()`

**Eklenmesi Gerekenler:**
```python
prompt += """
═════════════════════════════════════════════════════
ÇIKTI KALİTE KRİTERLERİ (MUTLAKA UYGULA)
═════════════════════════════════════════════════════

1. UZUNLUK ZORUNLULUĞU:
   - Ana teşhis: EN AZ 5 cümle, tercihen 10-15 cümle
   - Her bölüm: EN AZ 3 cümle
   - KISA CEVAPLAR YASAK: "Normal çalışıyor", "Bilinmiyor" KABUL EDİLMEZ

2. FİZİKSEL MEKANİZMA AÇIKLAMASI:
   - "Neden" sorusunu cevapla
   - "Nasıl" sorusunu cevapla
   - Sensörler arası ilişkiyi kur
   
   ÖRNEK:
   ❌ "Basınç yüksek"
   ✅ "Ana basınç 98.2 bar (limit: 95 bar). Bu yükseklik, 
       valf aşınmasından kaynaklanan iç kaçak nedeniyle oluşuyor.
       Kaçak, yüksek basınçlı hattan düşük basınçlı hatta yağ geçişi
       yaratıyor ve bu da ısı artışına neden oluyor (42.5°C)."

3. SOMUT VERİLER KULLAN:
   ❌ "biraz yüksek", "çok sıcak"
   ✅ "48°C (limitin 3°C üstü)", "98.2 bar (%110)"

4. SENSÖR İLİŞKİLERİ:
   - Basınç + Sıcaklık birlikte artıyor mu? → İç kaçak
   - Basınç düşük + Hız yok → Pompa sorunu
   - Sıcaklık yüksek + Basınç normal → Soğutucu sorunu

5. GEÇMİŞ OLAYLARLA BAĞLA:
   - "Bu tablo 15 Mart'ta da olmuştu, o zaman filtre tıkanmıştı"
   - "Son bakımda valf aşınması not edilmiş, değişmemiş"

6. ETA VER (Tahmini Süre):
   - "Bu gidişle 2 saat içinde limite ulaşır"
   - "3 gün içinde arıza kesinleşir"
   - "1 hafta içinde müdahale edilmezse pompa hasarı riski"

7. FİLO KARŞILAŞTIRMASI:
   - "Bu makine filodaki en kötü durumda"
   - "Sıcaklık filo ortalamasından 5°C yüksek"
   
8. BAKIM GEÇMİŞİ:
   - "Son bakım 15 gün önce, ama sorunlu parça değiştirilmedi"
   - "Filtre değişimi 2 aydır yapılmadı"

═════════════════════════════════════════════════════
YASAKLAR
═════════════════════════════════════════════════════

❌ "1. 2. 3." diye maddeleme (sadece aksiyon planında izinli)
❌ "Sonuç olarak", "Maalesef" gibi dolgu kelimeler
❌ Sadece veriyi tekrarlama — yorumla, nedensellik kur
❌ Akademik rapor gibi yazma — sen saha mühendisisin
❌ Kısa cevaplar (1-2 cümle) — DETAYLI yaz!
"""
```

---

#### 2.2 Kök Neden Ajanı Prompt Güncelleme

**Dosya:** `src/analysis/root_cause_agent.py`

**Eklenmesi Gerekenler:**
```python
prompt += """
5-WHY METODOLOJİSİ (DETAYLI):

Her "Neden" adımı için:
1. Somut kanıt göster (sensör verisi, bakım kaydı, fizik kuralı)
2. Güven yüzdesi ver (örn: %85 eminim)
3. Alternatif açıklama sun (örn: %15 ihtimalle başka neden)
4. Fiziksel mekanizmayı açıkla

ÖRNEK FORMAT:

Neden 1: Basınç neden düştü?
→ Ana valf açık kalmış
→ Kanıt: Valf pozisyon sensörü %78 açık (normal: %0)
→ Güven: %90
→ Alternatif: İç kaçak (%10)
→ Fizik: Valf açık kalınca yağ düşük basınçlı hatta akıyor

Neden 2: Valf neden açık kaldı?
→ Valf aşınması nedeniyle kapanamıyor
→ Kanıt: Son bakımda (15 gün önce) aşınma not edilmiş
→ Güven: %85
→ Alternatif: Aktuatör arızası (%15)
→ Fizik: Aşınma toleransı 0.5mm'yi geçti, valf tam kapanamıyor

Neden 3: Aşınma neden oldu?
→ 18,500 saat kullanım sonrası normal yıpranma
→ Kanıt: Makine yaşı 2.5 yıl, toplam çalışma süresi 18,500 saat
→ Güven: %95
→ Alternatif: Kalitesiz yedek parça (%5)
→ Fizik: Valf contası 15,000 saat ömrü var, 3,500 saat超额 çalışmış

[... devam et, minimum 5 why ...]
"""
```

---

#### 2.3 Aksiyon Ajanı Prompt Güncelleme

**Dosya:** `src/analysis/action_agent.py`

**Eklenmesi Gerekenler:**
```python
prompt += """
AKSİYON PLANI FORMATI (DETAYLI):

Her öneri için şu bilgileri ver:

1. ÖNCELİK:
   - ACIL: Hemen yap (0-2 saat)
   - BUGÜN: Gün içinde yap (2-8 saat)
   - BU HAFTA: 7 gün içinde yap
   - PLANLI: Sonraki bakımda yap

2. SÜRE TAHMİNİ:
   - "30 dakika", "2 saat", "1 gün"
   - Makine duruş süresi dahil

3. PARÇA DURUMU:
   - "Stokta var (5 adet)"
   - "Stokta az (2 adet, minimum 5 olması lazım)"
   - "Stokta YOK - sipariş gerekli (14 gün)"

4. GÜVENLİK UYARILARI:
   - "⚠️ Makineyi ÖNCE durdur!"
   - "⚠️ Basınç sıfırlanana kadar bekle"
   - "⚠️ Yüksek sıcaklık - eldiven kullan"

5. MALİYET:
   - Parça maliyeti
   - İşçilik süresi
   - Üretim kaybı tahmini

6. ALTERNATİF (PARÇA YOKSA):
   - "Geçici çözüm: Basınç limitini %80'e düşür"
   - "İdare etmek için: Yağ seviyesini her 2 saatte kontrol et"
   - "Risk: 2 hafta içinde arıza kesinleşir"

7. SONRAKİ ADIMLAR:
   - "Değişiklik sonrası 24 saat izlemeye al"
   - "1 hafta sonra tekrar kontrol et"
   - "Feedback sisteminde sonucu bildir"

ÖRNEK:

1. [ACİL] Ana basınç valfi contasını değiştir
   - Süre: 45 dakika (makine duruş dahil)
   - Parça: Valf contası (STOKTA YOK! - acil sipariş ver)
   - Sipariş süresi: 14 gün
   - Maliyet: 850₺ (parça) + 200₺ (işçilik) = 1,050₺
   - Üretim kaybı: 45 dakika × 500₺/saat = 375₺
   - Güvenlik: ⚠️ Makineyi DURDUR, basınç düşene kadar bekle (15 dakika)
   - Alternatif (parça gelene kadar):
     * Basınç limitini 95 → 76 bar'a düşür (%80)
     * Her 2 saatte yağ sıcaklığını kontrol et
     * Bu şekilde 2 hafta idare edilebilir
     * Ama verim %15 düşer, üretim yavaşlar
   - Sonrası: Değişiklik sonrası 24 saat yakından izle
"""
```

---

### FAZA 3: Feedback Sistemi (1 Hafta)

**Öncelik:** ⭐⭐⭐⭐

**Neden?** AI'nın doğruluğunu ölçmezsek geliştiremeyiz!

#### 3.1 Dashboard UI

**Dosya:** `src/ui/web/index.html` + `app.js`

**Tasarım:**
```html
<!-- Teşhis sonucunun altına eklenecek -->
<div class="feedback-section">
  <h4>📊 Bu teşhis doğru muydu?</h4>
  
  <div class="star-rating">
    <span class="star" data-rating="1">⭐</span>
    <span class="star" data-rating="2">⭐</span>
    <span class="star" data-rating="3">⭐</span>
    <span class="star" data-rating="4">⭐</span>
    <span class="star" data-rating="5">⭐</span>
  </div>
  
  <select class="accuracy-select">
    <option value="correct">✅ Tam Doğru</option>
    <option value="mostly_correct">🟡 Çoğunlukla Doğru</option>
    <option value="partially_correct">🟠 Kısmen Doğru</option>
    <option value="incorrect">❌ Yanlış</option>
  </select>
  
  <textarea placeholder="Notunuz (opsiyonel): Valf değişti, teşhis doğruydu..."></textarea>
  
  <button onclick="submitFeedback()">📤 Gönder</button>
</div>
```

#### 3.2 Backend API

**Dosya:** `src/app/web_server.py`

**Endpoint:**
```python
@app.route("/api/feedback", methods=["POST"])
def submit_feedback():
    """Kullanıcı feedback'ini kaydet."""
    data = request.json
    
    feedback = {
        "report_id": data["report_id"],
        "machine_id": data["machine_id"],
        "rating": data["rating"],  # 1-5
        "accuracy": data["accuracy"],  # correct, mostly_correct, etc.
        "user_note": data.get("note", ""),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    # feedback_log.jsonl'a ekle
    with open("data/feedback_log.jsonl", "a") as f:
        f.write(json.dumps(feedback) + "\n")
    
    return jsonify({"success": True})
```

#### 3.3 Feedback'i Context'e Entegre Et

**Dosya:** `pipeline/context_builder.py`

```python
# Context Builder'a eklenecek:
from src.analysis.feedback_system import FeedbackSystem

feedback = FeedbackSystem()
context["feedback_stats"] = feedback.get_machine_stats(machine_id)
```

#### 3.4 Feedback Analizi

**İleride yapılacak:**
```python
# Her hafta otomatik analiz:
feedback_analytics = {
    "avg_rating_trend": [4.1, 4.2, 4.3, 4.2],  # Son 4 hafta
    "most_accurate_agent": "diagnosis",  # En doğru ajan
    "least_accurate_agent": "prediction",  # En az doğru ajan
    "common_corrections": [
        "parça önerileri güncel değil",
        "bakım geçmişi dikkate alınmamış"
    ]
}
```

---

### FAZA 4: Dashboard İyileştirmeleri (1 Hafta)

**Öncelik:** ⭐⭐⭐

#### 4.1 API Key Dashboard Detaylandırma

**Mevcut:**
```
🔑 API Kotası: 127/750
```

**Eklenecekler:**
```
┌──────────────────────────────────────┐
│ 📊 API Kullanım Detayları            │
├──────────────────────────────────────┤
│ Ajan Bazlı Kullanım:                 │
│ 🔍 Teşhis:      45 çağrı             │
│ 🎯 Kök Neden:   32 çağrı             │
│ 📈 Tahmin:      28 çağrı             │
│ 🛠️ Aksiyon:     22 çağrı             │
│                                      │
│ Cache Performansı:                   │
│ Cache Hit Rate:  62%                 │
│ Cache Miss:      38%                 │
│                                      │
│ Fallback Durumu:                     │
│ Gemini kullanımı: 78                 │
│ Groq fallback:    49                 │
│                                      │
│ Model Dağılımı:                      │
│ Gemini 2.5: 61%                      │
│ Groq Llama: 39%                      │
└──────────────────────────────────────┘
```

#### 4.2 Makine Kartlarına Hızlı Aksiyon Butonları

**Mevcut:**
```
┌─────────────────────────────┐
│ HPR001 - KRİTİK 🔴          │
│ Basınç: 98.2 bar            │
└─────────────────────────────┘
```

**Güncellenecek:**
```
┌─────────────────────────────┐
│ HPR001 - KRİTİK 🔴          │
│ Basınç: 98.2 bar            │
│                             │
│ [🔍 Teşhis] [📊 Rapor]     │
│ [🛠️ Aksiyon]               │
└─────────────────────────────┘
```

**Tıklama davranışı:**
- `🔍 Teşhis` → Sağ panelde teşhis açılır
- `📊 Rapor` → Detaylı rapor modal'ı
- `🛠️ Aksiyon` → Aksiyon planı açılır

#### 4.3 Export Özellikleri

**PDF Rapor Export:**
```python
@app.route("/api/export/report/<report_id>/pdf")
def export_report_pdf(report_id):
    """Raporu PDF olarak export et."""
    report = _report_store.get(report_id)
    
    # PDF oluştur (WeasyPrint veya ReportLab)
    pdf = generate_pdf_report(report)
    
    return send_file(
        pdf,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"rapor_{report_id}.pdf"
    )
```

**CSV Veri Export:**
```python
@app.route("/api/export/machine/<machine_id>/csv")
def export_machine_csv(machine_id):
    """Makine verisini CSV olarak export et."""
    data = get_machine_data(machine_id)
    
    # CSV oluştur
    csv = generate_csv(data)
    
    return Response(
        csv,
        mimetype='text/csv',
        headers={"Content-Disposition": f"attachment;filename={machine_id}.csv"}
    )
```

**Email ile Rapor Gönder:**
```python
@app.route("/api/email/report", methods=["POST"])
def email_report():
    """Raporu email ile gönder."""
    data = request.json
    
    # Email gönder (SMTP)
    send_email(
        to=data["email"],
        subject=f"HPR Raporu - {data['machine_id']}",
        body=data["report_text"],
        attachments=data.get("attachments", [])
    )
    
    return jsonify({"success": True})
```

---

### FAZA 5: Performance & Monitoring (2-3 Hafta)

**Öncelik:** ⭐⭐⭐

#### 5.1 Sistem Metrikleri

**Endpoint:** `/api/system/metrics`

```json
{
  "uptime": "15 gün 3 saat",
  "avg_response_time": "8.2 saniye",
  "api_calls_today": 127,
  "cache_hit_rate": 0.62,
  "error_rate": 0.02,
  "last_kafka_message": "2 saniye önce",
  "memory_usage": "256MB",
  "disk_usage": "45%"
}
```

#### 5.2 Alert Threshold'ları

```python
# Sistem kendini izliyor:
ALERT_RULES = {
    "api_response_time": {
        "warning": 15,   # saniye
        "critical": 30
    },
    "cache_hit_rate": {
        "warning": 0.40,  # %40
        "critical": 0.20
    },
    "kafka_latency": {
        "warning": 30,   # saniye
        "critical": 60
    },
    "error_rate": {
        "warning": 0.05,  # %5
        "critical": 0.10
    }
}
```

#### 5.3 Otomatik Raporlama

**Her sabah 08:00:**
```
📊 GÜNLÜK ÖZET RAPORU

Makine Durumu:
✅ HPR002, HPR004, HPR005: Normal
⚠️ HPR003: Dikkat (basınç yükselişi)
🔴 HPR001: Kritik (valf aşınması)

API Kullanımı:
- Toplam: 127/750 (%17)
- Cache hit rate: %62
- Fallback: 49 kez Groq kullanıldı

Önerilen Aksiyonlar:
1. HPR001 valf contası sipariş et
2. HPR003 yağ filtresi kontrol et
```

---

## 4. UZUN VADELI VIZYON (6-12 Ay)

### 4.1 Makine Öğrenmesi Entegrasyonu

**Şu an:** Kural tabanlı + AI açıklama

**Hedef:** Gerçek tahmin modeli

```python
# XGBoost modeli ile arıza tahmini:
model = xgboost.XGBClassifier()
model.fit(X_train, y_train)

# Tahmin:
prediction = model.predict(current_sensors)
# → "48 saat içinde arıza riski: %73"
```

**Veri toplama:**
- Her gün sensör verileri kaydediliyor ✅
- Arıza olayları etiketlenmeli ❌
- Minimum 1000 etiketli örnek lazım

**Tahmini süre:** 3-6 ay (veri toplama + model eğitimi)

---

### 4.2 Predictive Maintenance (Kestirimci Bakım)

**Şu an:** Arıza olunca veya yaklaşınca uyarı

**Hedef:** Arıza olmadan ÖNCE tahmin

```
Geleneksel: Arıza → Uyarı → Müdahale
Kestirimci: Veri analizi → Tahmin → Planlı müdahale → Arıza YOK
```

**Gereksinimler:**
- Geçmiş arıza verisi (minimum 1 yıl)
- Sensör trend analizi
- ML model eğitimi
- Bakım planlama entegrasyonu

---

### 4.3 Çoklu Fabrika Desteği

**Şu an:** Tek fabrika (6 makine)

**Hedef:** Birden fazla fabrika

```
Fabrika A (İstanbul):
├── HPR001-006
└── Lokal dashboard

Fabrika B (Ankara):
├── HPR007-012
└── Lokal dashboard

Merkez (Cloud):
├── Tüm fabrikalar
├── Filo karşılaştırma
└── Raporlama
```

---

### 4.4 Mobil Uygulama

**Şu an:** Web dashboard (desktop + mobile responsive)

**Hedef:** Native mobil app

```
iOS/Android:
├── Push notification (kritik alarm)
├── Offline mode (son veriler cache'de)
├── Fotoğraf çek → Arıza raporuna ekle
└── Sesli komut → AI'a soru sor
```

---

### 4.5 Dijital İkiz (Digital Twin)

**Hedef:** Makinenin sanal kopyası

```
Fiziksel Makine → Sensör verileri → Digital Twin
                                              ↓
                                        Simülasyon
                                              ↓
                                    "Senaryo: Basınç 100 bar olursa ne olur?"
                                              ↓
                                    Tahmin: "2 saatte valf patlar"
```

---

## 5. RİSK ANALİZİ

### 5.1 Teknik Riskler

| Risk | Olasılık | Etki | Önlem |
|------|----------|------|-------|
| **API limit dolması** | Orta | Yüksek | DeepSeek ekle, cache optimize et |
| **Veri kaybı** | Düşük | Kritik | Günlük backup, replication |
| **Sistem çökmesi** | Düşük | Yüksek | PM2 auto-restart, health check |
| **Model kalitesi düşerse** | Orta | Orta | Feedback sistemi, prompt tuning |

### 5.2 İş Riskleri

| Risk | Olasılık | Etki | Önlem |
|------|----------|------|-------|
| **Kullanıcılar kullanmazsa** | Orta | Yüksek | UI/UX iyileştirme, eğitim |
| **Yanlış teşhis güven kaybettirir** | Orta | Kritik | Feedback sistemi, insan onayı |
| **Bakım ekibi direnç gösterirse** | Yüksek | Orta | Değişim yönetimi, demo |

---

## 6. MALIYET ANALİZİ

### 6.1 Mevcut Maliyet (AYLIK)

| Kalem | Maliyet |
|-------|---------|
| Gemini API | 0₺ (ücretsiz tier) |
| Groq API | 0₺ (ücretsiz tier) |
| Sunucu | 0₺ (lokal Mac) |
| **TOPLAM** | **0₺** |

### 6.2 Gelecek Maliyet (Tahmini)

| Kalem | 3 Ay | 6 Ay | 1 Yıl |
|-------|------|------|-------|
| API (DeepSeek?) | 0₺ | 0₺ | 0-500₺ |
| Sunucu (cloud?) | 0₺ | 500₺ | 1000₺ |
| Donanım (GPU?) | 0₺ | 0₺ | 50,000₺ |
| **TOPLAM** | **0₺** | **500₺** | **51,500₺** |

---

## 7. BAŞARI KRİTERLERİ (KPI)

### 7.1 Teknik KPI'lar

| Metrik | Hedef | Şu An |
|--------|-------|-------|
| API yanıt süresi | < 10 saniye | 8.2 saniye ✅ |
| Cache hit rate | > 60% | 62% ✅ |
| Teşhis doğruluğu | > 85% | ? (ölçülecek) |
| Sistem uptime | > 99% | ? (ölçülecek) |

### 7.2 İş KPI'lar

| Metrik | Hedef | Şu An |
|--------|-------|-------|
| Arıza öncesi uyarı süresi | > 24 saat | ? (ölçülecek) |
| Yanlış alarm oranı | < 10% | ? (ölçülecek) |
| Kullanıcı memnuniyeti | > 4/5 | ? (ölçülecek) |
| Bakım maliyet düşüşü | %20 | ? (ölçülecek) |

---

## 8. KARAR NOKTALARI

### 8.1 3 Ay Sonra (Temmuz 2026)

**Sorulacak sorular:**
1. Günlük API kullanımı kaç? (500+ ise DeepSeek ekle)
2. Kullanıcı feedback ortalaması kaç? (4.0+ ise devam, altındaysa düzelt)
3. Teşhis doğruluğu nedir? (%85+ ise devam, altındaysa model değiştir)

**Kararlar:**
- DeepSeek-R1 entegrasyonu? (EVET/HAYIR)
- Prompt optimizasyonu yeterli mi? (EVET/HAYIR)
- Yeni özelliklere geçelim mi? (EVET/HAYIR)

---

### 8.2 6 Ay Sonra (Ekim 2026)

**Sorulacak sorular:**
1. Lokal model gerekli mi? (GPU altyapısı var mı?)
2. Cloud migration gerekli mi? (10+ fabrika?)
3. ML model eğitimi başlayabilir mi? (1000+ etiketli veri?)

**Kararlar:**
- Ollama kurulumu? (EVET/HAYIR)
- Cloud migration? (EVET/HAYIR)
- ML model eğitimi? (EVET/HAYIR)

---

### 8.3 1 Yıl Sonra (Nisan 2027)

**Sorulacak sorular:**
1. Dijital İkiz projesi başlansın mı?
2. Mobil uygulama gerekli mi?
3. Çoklu fabrika desteği?

**Kararlar:**
- Digital Twin POC? (EVET/HAYIR)
- Mobile app development? (EVET/HAYIR)
- Multi-factory architecture? (EVET/HAYIR)

---

## 9. EKİP VE SORUMLULUKLAR

### 9.1 Mevcut Ekip

| Rol | Kişi | Sorumluluk |
|-----|------|-----------|
| **Proje Yöneticisi** | R. Ahsen Çiçek | Genel koordinasyon, mimari kararlar |
| **AI/ML Mühendisi** | - | Prompt engineering, model optimizasyonu |
| **Backend Geliştirici** | - | API, database, performance |
| **Frontend Geliştirici** | - | Dashboard UI/UX |
| **DevOps** | - | Deployment, monitoring, backup |

### 9.2 İhtiyaç Duyulan Roller

| Rol | Öncelik | Neden |
|-----|---------|-------|
| **Veri Bilimci** | Orta | ML model eğitimi için |
| **UI/UX Tasarımcı** | Düşük | Mobil app için |
| **Saha Mühendisi** | Yüksek | Arıza doğrulama, feedback |

---

## 10. SONUÇ VE ÖNERİLER

### 10.1 Kısa Vadeli (1-2 Hafta)

**Yapılacaklar:**
1. ✅ Context Builder'a 5 modül ekle
2. ✅ Prompt optimizasyonu yap
3. ✅ Feedback sistemi kur
4. ✅ Dashboard iyileştirmeleri

**Beklenen Fayda:**
- AI doğruluğu: +20%
- Kullanıcı memnuniyeti: +30%
- API verimliliği: +15%

---

### 10.2 Orta Vadeli (1-3 Ay)

**Yapılacaklar:**
1. ✅ Export özellikleri (PDF, CSV, Email)
2. ✅ Performance monitoring
3. ✅ Otomatik raporlama
4. ❓ DeepSeek-R1 entegrasyonu (karar verilecek)

**Beklenen Fayda:**
- Raporlama süresi: -50%
- Sistem görünürlüğü: +40%
- API kapasitesi: +100% (DeepSeek ile)

---

### 10.3 Uzun Vadeli (6-12 Ay)

**Yapılacaklar:**
1. ❓ ML model eğitimi (veri toplanırsa)
2. ❓ Predictive maintenance
3. ❓ Mobil uygulama
4. ❓ Digital Twin

**Beklenen Fayda:**
- Arıza öncesi uyarı: +48 saat
- Bakım maliyeti: -20%
- Üretim kaybı: -30%

---

## 11. TOPLANTI NOTLARI İÇİN ÖZET

### Bugünkü Toplantıda Konuşulacaklar:

1. **Mevcut Durum:**
   - 5 uzman ajan çalışıyor ✅
   - 750 API/gün kapasite ✅
   - Dashboard canlı ✅

2. **LLM Stratejisi:**
   - Şimdi: Gemini + Groq (YETERLI)
   - 3 ay sonra: DeepSeek-R1? (karar verilecek)
   - 1 yıl sonra: Lokal model? (şimdi GEREKSIZ)

3. **Öncelikler:**
   - Context Builder zenginleştirme (1-2 hafta)
   - Prompt optimizasyonu (3-5 gün)
   - Feedback sistemi (1 hafta)

4. **Karar Noktaları:**
   - 3 ay: API kullanım analizi → DeepSeek kararı
   - 6 ay: Donanım yatırımı → Lokal model kararı
   - 1 yıl: Dijital İkiz → Büyük proje başlangıcı

5. **Bütçe:**
   - Şu an: 0₺ (ücretsiz)
   - 6 ay: ~500₺/ay (opsiyonel cloud)
   - 1 yıl: ~50,000₺ (GPU sunucu, opsiyonel)

---

**Doküman Sonu** 📚

Bu doküman canlı bir belgedir. Her çeyrekte güncellenmelidir.

**Son Güncelleme:** 30 Nisan 2026  
**Sonraki Güncelleme:** 31 Temmuz 2026
