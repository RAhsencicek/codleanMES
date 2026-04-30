# Codlean MES — Aşama 6: Çoklu Uzman AI Ajan Sistemi

**Doküman Tarihi:** 30 Nisan 2026  
**Sistem Versiyonu:** 2.0 (Multi-Agent Architecture)  
**Yazar:** R. Ahsen Çiçek  
**Son Güncelleme:** 30 Nisan 2026

---

## 1. Bu Nedir? Neden Böyle Yaptık?

### 1.1 Önceki Sistem Nasıl Çalışıyordu?

Düşünün ki fabrikanızda **tek bir usta** var. Bu usta:
- Makineye bakıyor
- "Yağ sıcak" diyor
- "Basınç yüksek" diyor
- "Git bak" diyor

**Sorun neydi?** Bu usta her şeyi tek başına yapıyordu:
- Teşhis koyuyor ✅
- Kök neden arıyor ✅
- Aksiyon planlıyor ✅
- Geleceği tahmin ediyor ✅
- Rapor yazıyor ✅

**Ama...** Hepsi aynı kişi olunca:
- Detay azalıyordu (kimse her konuda uzman olamaz)
- Hız düşüyordu (tek kişi sırayla yapıyor)
- API kotası quickly tükeniyordu (tek Gemini API'ı, 20 istek/gün)

### 1.2 Yeni Sistem: 5 Uzmanlı Ekip

Artık **5 farklı uzman** var ve her biri **kendi alanında derinlemesine** çalışıyor:

| Uzman | Görevi | Fabrika Benzetmesi |
|-------|--------|-------------------|
| 🔍 **Teşhis Ajanı** | Hangi arıza var? | Kıdemli arıza teşhis mühendisi |
| 🎯 **Kök Neden Ajanı** | Neden oldu? (5-Why) | Kök neden analisti |
| 📈 **Tahmin Ajanı** | Ne olacak? | Gelecek tahmin uzmanı |
| 🛠️ **Aksiyon Ajanı** | Ne yapalım? | Bakım planlama uzmanı |
| 📝 **Rapor Ajanı** | Türkçe rapor | Teknisyen raporcusu |

**Avantajları:**
- ✅ **Paralel çalışma:** Bağımsız uzmanlar aynı anda çalışır
- ✅ **Derin analiz:** Her uzman kendi alanında detaylı
- ✅ **API verimliliği:** Cache + akıllı seçim = az API kullanımı
- ✅ **Groq fallback:** Gemini dolunca Groq devreye girer (11 API key!)
- ✅ **Risk bazlı:** Düşük risk = az uzman, yüksek risk = tüm ekip

---

## 2. Sistem Mimarisi

### 2.1 Genel Akış

```
┌─────────────────────────────────────────────────────────────┐
│                    FABRİKA VERİ AKIŞI                        │
└─────────────────────────────────────────────────────────────┘

[Kafka Topic] 
    ↓
[Context Builder] ← Makine profili, bakım geçmişi, envanter
    ↓
[Agent Coordinator] ← Şef: "Risk kaç? Kimleri çağırayım?"
    ↓
┌──────────┬──────────┬──────────┬──────────┬──────────┐
│ Teşhis   │ Kök Neden│ Tahmin   │ Aksiyon  │ Rapor    │
│ Ajanı    │ Ajanı    │ Ajanı    │ Ajanı    │ Ajanı    │
│ (Paralel)│ (Paralel)│ (Paralel)│ (Paralel)│ (Sıralı) │
└──────────┴──────────┴──────────┴──────────┴──────────┘
    ↓
[Birleştirilmiş Sonuç] → Web Dashboard'a gönder
```

### 2.2 Dosya Yapısı

```
kafka/
├── pipeline/
│   ├── llm_engine.py              # AI Usta Başı (eski sistem, geriye uyumlu)
│   └── context_builder.py         # Veri hazırlama (context pipeline)
│
├── src/
│   ├── analysis/
│   │   ├── agent_coordinator.py   # 🎯 ŞEF: Koordinatör
│   │   ├── diagnosis_agent.py     # 🔍 Teşhis Uzmanı
│   │   ├── root_cause_agent.py    # 🎯 Kök Neden Uzmanı
│   │   ├── prediction_agent.py    # 📈 Tahmin Uzmanı
│   │   ├── action_agent.py        # 🛠️ Aksiyon Uzmanı
│   │   └── report_agent.py        # 📝 Rapor Uzmanı
│   │
│   ├── core/
│   │   └── api_key_manager.py     # 🔑 API Key Rotation (Gemini + Groq)
│   │
│   └── app/
│       └── web_server.py          # Web Dashboard API
│
└── .env                           # API Keys (GEMINI + GROQ)
```

---

## 3. Agent Coordinator (Şef) Detaylı Analiz

### 3.1 Dosya: `src/analysis/agent_coordinator.py`

**Görev:** Fabrika şefi gibi çalışır. Risk seviyesine bakar, kaç uzman çağıracağına karar verir.

### 3.2 Risk Bazlı Ajan Seçimi

```python
# Risk Skoru 0-30: NORMAL (Sadece 2 uzman)
→ Teşhis Ajanı + Rapor Ajanı
"Makine rahat, sadece durum raporu yeterli"

# Risk Skoru 31-70: ORTA (Tüm 5 uzman)
→ Teşhis + Kök Neden + Tahmin + Aksiyon + Rapor
"Dikkatli ol, detaylı analiz lazım"

# Risk Skoru 71-100: KRİTİK (Tüm 5 uzman)
→ Teşhis + Kök Neden + Tahmin + Aksiyon + Rapor
"TAM EKİP DEVREYE! Acil müdahale!"
```

**Neden böyle?** API kotasını korumak için. Her analiz 1-2 API çağrısı demek. Gereksiz yere 5 ajan çağırmak, 20 günlük kotayı 4 analizde bitirir!

### 3.3 Paralel vs Sıralı Çalışma

```python
# BAĞIMSIZ AJANLAR → PARALEL (asyncio.gather)
# Birbirini beklemeye gerek yok, aynı anda çalışsınlar:
await asyncio.gather(
    diagnosis_agent.diagnose(context),      # 5 saniye
    root_cause_agent.analyze(context),      # 5 saniye
    prediction_agent.predict(context),      # 5 saniye
    action_agent.plan(context)              # 5 saniye
)
# Toplam: 5 saniye (hepsi aynı anda)

# BAĞIMLI AJAN → SIRALI (Rapor)
# Raporcu, diğer 4 uzman bitene kadar bekler:
report = report_agent.generate(
    diagnosis=diagnosis_result,
    root_cause=root_cause_result,
    prediction=prediction_result,
    action=action_result
)
# Rapor süresi: 3 saniye
# TOPLAM: 8 saniye (5 + 3)
```

**Eski sistem:** 5 ajan × 5 saniye = **25 saniye** (sıralı)  
**Yeni sistem:** 5 saniye (paralel) + 3 saniye (rapor) = **8 saniye** ⚡

### 3.4 Cache (Önbellek) Sistemi

```python
# Aynı makine, aynı risk seviyesi → API'ye gitme!
# 10 dakika içinde tekrar sorma

# Örnek:
cache_key = "agent_diagnosis_HPR001_medium"

# İlk çağrı: API'ye git → sonucu kaydet (10 dk)
# 2. çağrı (3 dk sonra): Cache'den döndür ✅
# 3. çağrı (11 dk sonra): Cache süresi dolmuş, tekrar API'ye git
```

**Neden önemli?** API kotasını korur! Aynı soruyu 10 kez sormak yerine 1 kez sor, 10 kez cache'den döndür.

### 3.5 Throttle (Tıkama) Sistemi

```python
# Aynı makineye çok sık soru sorma:
AUTO_INTERVAL_SEC = 300    # Otomatik analiz: 5 dakikada bir
ALERT_INTERVAL_SEC = 60    # Alarm sonrası: 1 dakikada bir

# Örnek:
08:00 → HPR001 analizi yapıldı ✅
08:03 → HPR001 analizi istendi → "Çok erken, 2 dakika bekle" ❌
08:05 → HPR001 analizi yapıldı ✅
```

---

## 4. Teşhis Ajanı (Diagnosis Agent) Detayları

### 4.1 Dosya: `src/analysis/diagnosis_agent.py`

**Görev:** Makine verisine bakar, "Hangi arıza var?" sorusunu cevaplar.

### 4.2 6 Adımlı Analiz Metodolojisi

Teşhis ajanı şu sırayla çalışır:

```
1. VERİ KALİTESİ KONTROLÜ
   → Sensörler çalışıyor mu?
   → Veri güvenilir mi?
   → Eksik bilgi var mı?

2. ANOMALİ TESPİTİ
   → Hangi sensör anormal?
   → Normalden ne kadar sapmış?
   → Trend ne yöne? (artıyor/azalıyor/sabit)

3. NEDENSEL İLİŞKİLER
   → Basınç artarken sıcaklık da artıyor mu?
   → Hız düşerken titreşim artıyor mu?
   → Sensörler arası bağlantılar

4. 5-WHY KÖK NEDEN ANALİZİ
   → Neden 1: Basınç neden yüksek?
   → Neden 2: Valf neden açık?
   → Neden 3: Sensör neden yanlış okuyor?
   → Neden 4: Kalibrasyon neden yapılmamış?
   → Neden 5: Bakım planı neden yok?

5. RİSK DEĞERLENDİRMESİ
   → CRITICAL: Hemen durdur!
   → HIGH: 2 saat içinde müdahale
   → MEDIUM: Bugün bak
   → LOW: İzlemeye devam

6. AKSİYON PLANI
   → İlk yapılması gereken
   → İkinci adım
   → Üçüncü adım
```

### 4.3 JSON Çıktı Formatı

```json
{
  "machine_id": "HPR001",
  "timestamp": "2026-04-30 10:30:00",
  "data_quality": "reliable",
  "anomaly_pattern": "basınç_yükselişi",
  "diagnosis": "Hidrolik iç kaçak tespit edildi. Ana basınç son 30 dakikada %18 artarken yağ sıcaklığı 42°C'ye çıktı. Bu durum, yüksek basınçlı hatta iç kaçak olduğunu gösteriyor.",
  "root_cause": "Ana basınç valfi aşınması nedeniyle iç kaçak. Valf, 2 yıllık kullanım sonrası tolerans dışına çıkmış.",
  "prediction": "Bu gidişle 3 saat içinde basınç 110 bar limitine ulaşacak. Acil müdahale edilmezde pompa hasarı riski var.",
  "action": "1. Makineyi durdur. 2. Ana basınç valfini kontrol et. 3. Valf contasını değiştir. 4. Sistem basıncını test et.",
  "confidence": 0.87,
  "severity": "HIGH",
  "supporting_sensors": ["main_pressure", "oil_temperature"],
  "evidence": [
    "Ana basınç 98 bar (limit: 95 bar)",
    "Yağ sıcaklığı 42°C (dikkat limiti: 39.5°C)",
    "Basınç artış hızı: +12 bar/saat"
  ]
}
```

### 4.4 Groq Fallback Mekanizması

**Sorun:** Gemini API ücretsiz versiyonunun limiti 20 istek/gün.

**Çözüm:** Gemini 429 hatası verince (kota doldu), otomatik Groq'a geç:

```python
try:
    # Önce Gemini dene
    response = gemini_client.generate_content(prompt)
except Exception as e:
    if "429" in str(e) or "quota" in str(e).lower():
        # Gemini kotası doldu! Groq fallback:
        try:
            groq_response = groq_client.chat.completions.create(
                model='llama-3.3-70b-versatile',
                messages=[
                    {"role": "system", "content": DIAGNOSIS_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ]
            )
            # Groq başarılı!
        except Exception as groq_err:
            # Groq da başarısız → yerel analiz motoruna düş
```

**Gemini vs Groq Karşılaştırması:**

| Özellik | Gemini 2.5 Flash | Groq Llama 3.3 70B |
|---------|------------------|-------------------|
| Günlük Limit | 20 istek | 50 istek/key |
| API Key Sayısı | 10 | 11 |
| TOPLAM KAPASİTE | 200/gün | 550/gün |
| Model Kalitesi | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Yanıt Hızı | ~3 saniye | ~2 saniye |
| Türkçe | Mükemmel | Çok iyi |

**Toplam Kapasite:** 200 (Gemini) + 550 (Groq) = **750 API çağrısı/gün** 🚀

---

## 5. API Key Rotation Sistemi

### 5.1 Dosya: `src/core/api_key_manager.py`

**Görev:** API key'leri döndürür, kota takibi yapar, otomatik geçiş yapar.

### 5.2 Gemini Key Rotation

```python
# .env dosyasında:
GEMINI_API_KEYS=key1,key2,key3,...,key10

# Sistem:
API_KEY_MAX_REQUESTS_PER_DAY=20

# Nasıl çalışır:
Key #1 → 20 istek → DOLU!
Key #2 → 20 istek → DOLU!
Key #3 → 5 istek → KULLANIMDA (aktif)
Key #4 → 0 istek → BEKLEMEDE
...
Key #10 → 0 istek → BEKLEMEDE

# Key #3 dolunca otomatik Key #4'e geç
```

### 5.3 Groq Key Rotation

```python
# .env dosyasında:
GROQ_API_KEYS=gsk_1,gsk_2,...,gsk_11

GROQ_MAX_REQUESTS_PER_DAY=50

# Nasıl çalışır:
Groq Key #1 → 50 istek → DOLU!
Groq Key #2 → 32 istek → KULLANIMDA (aktif)
Groq Key #3 → 0 istek → BEKLEMEDE
...
Groq Key #11 → 0 istek → BEKLEMEDE

# Thread-safe: Çoklu thread aynı anda key kullanabilir
```

### 5.4 Thread-Safe Kullanım Takibi

```python
import threading

class GroqKeyRotationManager:
    def __init__(self):
        self.usage_lock = threading.Lock()  # Thread kilidi
        self.usage_data = {}  # {key_index: {count, date, last_used}}
    
    def record_usage(self, success: bool):
        with self.usage_lock:  # Kilidi al
            # Sadece 1 thread kullanımı kaydedebilir
            self.usage_data[current_key]['count'] += 1
            # Kilit serbest
```

**Neden önemli?** 3 ajan paralel çalışınca, 3 thread aynı anda "key kullanıldı" kaydetmek ister. Lock olmadan sayaç bozulur!

---

## 6. Web Dashboard API

### 6.1 Dosya: `src/app/web_server.py`

**Endpoint:** `POST /api/multi-agent/analyze/{machine_id}`

### 6.2 API Yanıt Formatı

```json
{
  "success": true,
  "machine_id": "HPR001",
  "report_id": "RPT-20260430-103000-HPR001",
  "risk_score": 72.5,
  "risk_level": "critical",
  "execution_time": 8.3,
  "agents_used": ["diagnosis", "root_cause", "prediction", "action", "report"],
  
  "diagnosis": "Hidrolik iç kaçak tespit edildi...",
  "root_cause": "Ana basınç valfi aşınması...",
  "prediction": "3 saat içinde limite ulaşacak...",
  "action": "1. Makineyi durdur. 2. Valfi kontrol et...",
  
  "report": {
    "summary": "Kritik durum tespit edildi...",
    "details": "...",
    "recommendations": "..."
  },
  
  "metadata": {
    "timestamp": "2026-04-30T10:30:00Z",
    "model": "llama-3.3-70b-versatile",
    "fallback_used": true,
    "cache_hit": false
  }
}
```

### 6.3 Frontend Entegrasyonu

**Dosya:** `src/ui/web/app.js`

```javascript
// Kullanıcı "Teşhis" butonuna tıklar
async function selectMachine(machineId, agentType) {
  // 1. Sağ panel açılır
  openDetailPanel('🔍 Teşhis Analizi', '⏳ Analiz yapılıyor...');
  
  // 2. API çağrısı
  const response = await fetch(`/api/multi-agent/analyze/${machineId}`, {
    method: 'POST'
  });
  
  const result = await response.json();
  
  // 3. Sonuç sağ panelde gösterilir
  displayAgentResult({
    diagnosis: result.diagnosis,
    root_cause: result.root_cause,
    prediction: result.prediction,
    action: result.action
  });
}
```

---

## 7. Context Pipeline (Veri Hazırlama)

### 7.1 Dosya: `pipeline/context_builder.py`

**Görev:** HAM VERİ → ZENGİN CONTEXT'e dönüştürür.

### 7.2 Context Yapısı

```python
context = {
    # Temel bilgiler
    "machine_id": "HPR001",
    "timestamp": "2026-04-30 10:30:00",
    "operating_time": "2.5 saat",
    
    # Sensör verileri
    "sensors": {
        "oil_tank_temperature": 42.5,
        "main_pressure": 98.2,
        "horizontal_press_pressure": 85.1
    },
    
    # Limit ihlalleri
    "limit_violations": [
        "main_pressure: 98.2 bar (limit: 95 bar)"
    ],
    
    # Risk analizi
    "risk_score": 72.5,
    "severity": "critical",
    
    # Fizik kuralları
    "physics_rules_triggered": [
        "Sinsi İç Kaçak Isısı: Basınç + Sıcaklık birlikte artıyor"
    ],
    
    # Benzer geçmiş olaylar
    "similar_incidents": [
        "2026-03-15: HPR001 - Yağ filtresi tıkanması (benzerlik: 87%)"
    ],
    
    # ML tahmini
    "ml_prediction": {
        "anomaly_score": 0.82,
        "probability_failure_24h": 0.65
    }
}
```

### 7.3 Gelecek Geliştirmeler (TODO)

Context Builder'a EKLENMESİ PLANLANANLAR:

```python
# 1. Makine Profili
context["machine_profile"] = {
    "model": "HPR Dikey Pres",
    "age_years": 2.5,
    "total_hours": 18500,
    "known_issues": ["valf aşınması"],
    "sensors_available": ["oil_temp", "main_pressure", ...]
}

# 2. Bakım Geçmişi
context["maintenance_history"] = {
    "last_date": "2026-04-15",
    "days_since": 15,
    "overdue_tasks": ["filtre değişimi"],
    "recent_records": [
        {"date": "2026-04-15", "type": "valf kontrol", "result": "normal"}
    ]
}

# 3. Envanter Durumu
context["inventory_status"] = {
    "low_stock_alerts": ["yağ filtresi (2 adet kaldı)"],
    "critical_parts": ["valf contası (YOK!)"]
}

# 4. Filo Karşılaştırması
context["fleet_comparison"] = {
    "HPR001": {"temp": 42.5, "pressure": 98.2, "status": "critical"},
    "HPR002": {"temp": 35.1, "pressure": 82.0, "status": "normal"},
    "HPR003": {"temp": 38.7, "pressure": 88.5, "status": "warning"},
    # ... HPR004, HPR005, HPR006
}

# 5. Operatör Feedback
context["feedback_stats"] = {
    "avg_rating": 4.2,
    "accuracy_rate": 0.87,
    "total_feedbacks": 23
}
```

**Bu eklendiğinde ajanlar çok daha zengin analiz yapacak!**

---

## 8. Gerçek Hayat Senaryosu

### 8.1 Örnek: HPR001 Kritik Durum

**08:00 - Sistem başlıyor**

```
1. Kafka'dan veri geliyor:
   HPR001 → oil_temp: 42.5°C, main_pressure: 98.2 bar

2. Context Builder çalışıyor:
   - Limit ihlali: main_pressure 98.2 > 95
   - Fizik kuralı: Basınç + Sıcaklık birlikte artıyor
   - Risk skoru: 72.5/100

3. Agent Coordinator diyor:
   "Risk CRITICAL! Tüm ekibi çağır!"

4. Paralel analiz başlıyor (5 uzman aynı anda):
   🔍 Teşhis: "Hidrolik iç kaçak" (5 saniye)
   🎯 Kök Neden: "Valf aşınması" (5 saniye)
   📈 Tahmin: "3 saatte limite ulaşır" (5 saniye)
   🛠️ Aksiyon: "Valfi değiştir" (5 saniye)

5. Raporcu bekliyor (4 uzman bitene kadar)

6. 4 uzman bitince Raporcu çalışıyor:
   📝 Rapor: "Kritik: HPR001'de iç kaçak..." (3 saniye)

7. Web Dashboard'a gönderiliyor:
   Toplam süre: 8 saniye

8. Teknisyen ekranda görüyor:
   🔴 HPR001 - KRİTİK
   "Ana basınç valfi aşınması nedeniyle iç kaçak.
    3 saat içinde basınç limite ulaşacak.
    Makineyi durdur, valfi kontrol et."
```

**08:05 - Otomatik tekrar analiz**

```
- Cache kontrol: "HPR001_critical" → YOK (ilk kez)
- API çağrısı yapılıyor
- Sonuç cache'e yazılıyor (10 dk geçerli)
```

**08:08 - Manuel analiz isteği**

```
- Cache kontrol: "HPR001_critical" → VAR! (3 dk önce)
- API'ye gitme! Cache'den döndür ✅
- API kotası korunmuş! 🎯
```

**08:20 - Throttle devrede**

```
- Son analiz: 08:05 (15 dk önce)
- Throttle: 5 dk beklenmeli
- Durum: OK, analiz yapılır ✅
```

**08:21 - Erken istek**

```
- Son analiz: 08:20 (1 dk önce)
- Throttle: 5 dk beklenmeli
- Durum: ÇOK ERKEN, 4 dakika daha bekle ❌
```

---

## 9. Performans ve Optimizasyon

### 9.1 Eski vs Yeni Karşılaştırma

| Metrik | Eski Sistem | Yeni Sistem | İyileşme |
|--------|-------------|-------------|----------|
| Analiz Süresi | 25 saniye | 8 saniye | **%68 daha hızlı** ⚡ |
| API Kullanımı | Her seferinde | Cache + Throttle | **%80 tasarruf** 💰 |
| Günlük Kapasite | 20 analiz | 750 analiz | **37x daha fazla** 🚀 |
| Hata Toleransı | Tek API | 2 API (Gemini+Groq) | **%100 artırım** 🛡️ |
| Analiz Derinliği | Yüzeysel | 5 uzman detaylı | **5x daha detaylı** 🔬 |

### 9.2 API Kota Hesabı

```
# GÜNLÜK KAPASİTE:

Gemini API:
10 keys × 20 istek = 200 istek/gün

Groq API:
11 keys × 50 istek = 550 istek/gün

TOPLAM: 750 istek/gün

# GERÇEK KULLANIM:
Cache hit rate: ~60% (10 dk içinde tekrar sorma)
Throttle: 5 dk aralık
Gerçek API kullanımı: ~300 istek/gün

MARJ: 750 - 300 = 450 istek YEDEK ✅
```

---

## 10. Sorun Giderme

### 10.1 "API kotası doldu" Hatası

**Sebep:** Tüm Gemini key'leri dolmuş.

**Çözüm:** 
- Sistem otomatik Groq'a geçmeli ✅
- Log kontrol: `pm2 logs codlean-mes | grep "Groq fallback"`
- Eğer Groq'a geçmiyorsa → kod hatası var

### 10.2 "Analiz çok yavaş" Şikayeti

**Sebep:** 
- Cache devre dışı
- 5 ajan sıralı çalışıyor (paralel değil)
- API yanıt süresi uzun

**Çözüm:**
- `pm2 logs codlean-mes | grep "CACHE HIT"` → Cache çalışıyor mu?
- `pm2 logs codlean-mes | grep "asyncio.gather"` → Paralel mi?
- Groq kullan → Gemini'den hızlı

### 10.3 "Teşhis çok kısa" Şikayeti

**Sebep:** 
- Model kısa yanıt veriyor
- Prompt yeterli değil

**Çözüm:**
- `diagnosis_agent.py` → `_build_diagnosis_prompt()` 
- Prompt'a ekle: "HER BÖLÜM EN AZ 5 CÜMLE"
- Groq model: `llama-3.3-70b-versatile` (daha detaylı)

### 10.4 "Bazı ajanlar çalışmıyor"

**Sebep:**
- Import hatası
- API yanıtı parse edilemiyor

**Çözüm:**
```bash
pm2 logs codlean-mes --lines 50 | grep "ERROR"
pm2 logs codlean-mes --lines 50 | grep "Exception"
```

---

## 11. Gelecek Geliştirmeler (Roadmap)

### 11.1 Kısa Vadeli (1-2 hafta)

- [ ] Context Builder'a 5 yeni modül ekle (bakım, envanter, profil, filo, feedback)
- [ ] Teşhis prompt'unu optimize et (10-15 cümle zorunlu)
- [ ] Root Cause + Action ajanlarını zenginleştir
- [ ] End-to-end test senaryoları

### 11.2 Orta Vadeli (1 ay)

- [ ] `hpr_monitor.py` → coordinator.analyze() kullan (eski _usta.analyze_async() yerine)
- [ ] Feedback sistemi write entegrasyonu (operatör puanlama)
- [ ] Operator notes collection UI
- [ ] Fleet comparison dashboard

### 11.3 Uzun Vadeli (3 ay)

- [ ] Docker containerization
- [ ] Model sürümlendirme
- [ ] Monitoring + alerting (sistemin kendi sağlığı)
- [ ] Log rotation

---

## 12. Sık Sorulan Sorular (SSS)

### Neden 5 ayrı ajan yaptık? Tek büyük prompt yazamaz mıydık?

**Evet yazabilirdik AMA:**
1. **Paralel çalışma:** 5 küçük prompt paralel çalışabilir, 1 büyük prompt sıralı
2. **Bakım kolaylığı:** Teşhis prompt'unu değiştirince Kök Neden etkilenmez
3. **API verimliliği:** Her ajan sadece ihtiyacı olan context'i alır
4. **Hata izolasyonu:** Teşhis ajanı çökse bile Tahmin ajanı çalışmaya devam eder

### Groq mu daha iyi, Gemini mi?

**Karşılaştırma:**
- **Gemini 2.5 Flash:** Türkçe mükemmel, mantık çok iyi, ama yavaş ve limit düşük
- **Groq Llama 3.3 70B:** Çok hızlı, limit yüksek, Türkçe çok iyi (ama Gemini kadar mükemmel değil)

**Karar:** Kritik teşhislerde Gemini, yüksek volumede Groq. İkisi birlikte = en iyi sonuç!

### Cache 10 dakika, neden 1 saat değil?

**Sebep:** Makine durumu hızla değişebilir! 10 dakika önce "normal" olan makine, şimdi "critical" olabilir. 10 dakika optimal denge: API kotasını korur ama stale data vermez.

### Neden ThreadPoolExecutor max_workers=3?

**Sebep:** 3 thread yeterli. 5 ajan var ama 4'ü paralel async çalışıyor (asyncio.gather). ThreadPool sadece senkron I/O işlemleri için (örneğin Groq API çağrıları).

---

## 13. Özet

### Bu Sistem Neden Özel?

1. **Akıllı Kaynak Yönetimi:** Risk bazlı ajan seçimi + cache + throttle = minimum API kullanımı
2. **Yüksek Erişilebilirlik:** 2 farklı AI provider (Gemini + Groq), 21 API key, otomatik fallback
3. **Paralel İşleme:** Bağımsız uzmanlar aynı anda çalışır → %68 daha hızlı
4. **Derin Analiz:** 5 uzman, her biri kendi alanında detaylı
5. **Gerçek Zamanlı:** Kafka → Context → AI → Dashboard = 8 saniye
6. **Ölçeklenebilir:** Yeni ajan eklemek kolay (sadece coordinator'a ekle)

### Bir Cümlede:

> **Eski sistem:** Tek usta, sırayla yapıyor, yavaş ve yüzeysel  
> **Yeni sistem:** 5 uzmanlı ekip, paralel çalışıyor, hızlı ve derinlemesine, API kotasını akıllıca yönetiyor

---

**Doküman Sonu** 📚

Bu dokümanı okuyan herkes:
- ✅ Sistemin nasıl çalıştığını
- ✅ Neden böyle tasarlandığını
- ✅ Hangi dosyanın ne yaptığını
- ✅ Sorun nasıl giderileceğini
- ✅ Gelecekte ne yapılacağını

...çok iyi anlamış olmalı! 🎯
