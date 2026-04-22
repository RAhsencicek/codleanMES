# Codlean MES — Proje Durumu ve Yapılacaklar

> **Son güncelleme:** 2026-03-24
> **Durum:** 🟡 Faz 5 devam ediyor — F5-4 bekliyor (bakım mühendisi görüşmesi)
> **Kural:** Bir şey değiştirdin mi? İlgili maddeyi güncelle. Yeni sorun buldun mu? Buraya ekle.

---

## Projeye Yeni Başlıyorsan

1. Bu dosyayı baştan sona oku (15 dakika)
2. `BÖLÜM 0`'ı oku — sistemin gerçek durumunu gör
3. `BÖLÜM 1`'den başla — öncelik sırasına göre ilerle
4. Her değişiklik sonrası ilgili maddeyi ✅ yap ve tarihi yaz

---

## BÖLÜM 0 — Sistemin Gerçek Durumu

### Çalışanlar ✅

| Bileşen | Açıklama |
|---------|----------|
| Kafka bağlantısı | `mqtt-topic-v2` @ `10.71.120.10:7001`, 10 partition, canlı mesaj akışı var |
| Veri doğrulama | Spike filtresi (2026-03-25 düzeltildi), stale kontrol, startup maskesi, parse hata logları |
| State store | RAM ring buffer (720 örnek = ~2 saat), EWMA, disk checkpoint (5 dk) |
| Threshold alarmları | IK veritabanından alınan limitlerle anlık eşik kontrolü |
| Trend tespiti + ETA | Lineer regresyon, R²≥0.70 filtresi, limite kalan dakika tahmini |
| Risk scorer | Threshold + Trend + ML ensemble, 0-100 skor |
| Physics kuralları | `docs/causal_rules.json` — termal stres, hidrolik zorlanma, soğuk makine |
| ML modeli | XGBoost/RF yüklü, SHAP+DLIME+NLG entegre (zayıf ama çalışıyor) |
| Dashboard | 2×3 grid, 6 HPR makinesi, renk kodlu paneller |
| AI Usta Başı | Gemini API — alert sonrası bağlam analizi (GEMINI_API_KEY gerekli) |
| Veri toplama | `window_collector` + `context_collector` aktif, JSON'lara yazılıyor |
| Alert throttling | Normal: 30 dk, Kritik: 15 dk |

### Eksikler / Sorunlar ❌

| Bileşen | Sorun | Öncelik |
|---------|-------|---------|
| Fabrika arıza kuralları | `causal_rules.json` genel fizik kuralı içeriyor, fabrikaya özgü değil | **F5-4** |
| sync script HPR ayrımı | `sync_limits_from_db.py` HPR002/HPR006'yı Yatay Pres yerine Dikey Pres sayıyor | F5-3b |
| ML feature leakage | `total_faults_window` + `active_sensors` = %54 importance, gerçek pre-fault değil | Bölüm 4 |
| Geçmiş olay hafızası | `similar_past_events` hep boş, Gemini geçmişe bakamıyor | Bölüm 4 |
| State store thread lock | Yüksek mesaj hızında teorik race condition | P2-2 |

### Mimari Akışı (Kısaca)

```
Kafka → [Katman 0: Temizle] → [Katman 1: Hafızala] → [Katman 2: Analiz Et]
      → [Katman 2.5: Bağlam Kur] → [Katman 3: Alarm Ver] → Teknisyen
```

Detay için: `docs/pipeline_mimarisi.md`

---

## BÖLÜM 1 — Yapılacaklar (Öncelik Sırasıyla)

### ✅ Tamamlananlar

| Madde | Ne Yapıldı | Tarih |
|-------|-----------|-------|
| P0-1 | `context_collector.py` `hpr_monitor.py`'e entegre edildi | önceden |
| P0-2 | `CAUSAL_RULES_PATH` `config/` → `docs/` düzeltildi | 2026-03-23 |
| P0-3 | `context_builder.py` causal_rules.json şema uyumu (dict→dict) | 2026-03-23 |
| P1-1 | `safe_numeric()` parse hataları: bilinen metinler DEBUG, rakam içerenler WARNING | 2026-03-23 |
| P1-2 | `llm_engine.py` — 10s timeout + `ThreadPoolExecutor(max_workers=3)` | 2026-03-23 |
| P1-3 | `refresh_dashboard()` — `operating_minutes` güncelleniyor | 2026-03-23 |
| P1-4 | `_ai_analysis` — timestamp eklendi, 30dk+ eskiler soluk gösteriliyor | 2026-03-23 |
| P1-5 | `scripts/kafka_env.py` + `.env.example` — IP artık env var'dan okunuyor | 2026-03-23 |
| P1-6 | `horitzonal` typo — Kafka mesajı kontrol edildi, PLC de aynı yazımı gönderiyor | 2026-03-24 |
| P2-1 | `hpr_monitor_fixed.py`, backup dosyalar, `data_collector_service.py` silindi | 2026-03-23 |
| F5-1 | `context_builder.py` — `enriched_sensors` eklendi, hydraulic_strain + cold_startup_mask artık tetikleniyor | 2026-03-24 |
| F5-2 | `limits_config.yaml` boolean_rules — IK veritabanından `true_label`/`false_label`/`description` eklendi | 2026-03-24 |
| F5-3 | `scripts/data_tools/sync_limits_from_db.py` oluşturuldu | 2026-03-24 |
| P2-2 | `state_store.py` thread lock (`RLock`) teyit edildi | 2026-04-20 |
| P2-3 | `context_collector.py` JSONL Append-only I/O optimizasyonu eklendi | 2026-04-20 |
| F5-3b| `sync_limits_from_db.py` Yatay/Dikey pres `--hpr-yatay` ayrımı kodlandı | 2026-04-20 |
| ML   | Sızdırmaz özellik mühendisliği bitti, joblib modeli üretildi | 2026-04-20 |

---

### ✅ F5-3b — Sync Script HPR Yatay/Dikey Ayrımı

**Durum:** ✅ Tamamlandı (2026-04-20)
**Süre:** ~20 dakika
**Dosya:** `scripts/data_tools/sync_limits_from_db.py`

**Problem:**
Script şu an tüm HPR makinelerini "Dikey Pres" olarak işliyor.
HPR002 ve HPR006 "Yatay Pres" — sadece 2 sensörleri var (`horizontal_press_pressure`, `horitzonal_infeed_speed`).
Script çalıştırılırsa bu iki makineye yanlışlıkla 4 fazla sensör ekler.

**Geçici çözüm (şimdilik):**
```bash
# HPR002 ve HPR006'yı hariç tut, elle kontrol et
python3 scripts/data_tools/sync_limits_from_db.py \
  --typefile machinetypedataitems.csv \
  --machines HPR001,HPR003,HPR004,HPR005 \
  --dry-run
```

**Kalıcı çözüm:**
`--hpr-yatay HPR002,HPR006` parametresi ekle. Script bu makinelere "Yatay Pres" tipi uygulasın.

---

### ⬜ F5-4 — Gerçek Fabrika Arıza Kuralları (EN KRİTİK)

**Durum:** ⬜ Yapılmadı — Bakım mühendisi görüşmesi gerekiyor
**Süre:** Görüşme 30-45 dk, kod 1-2 saat
**Dosya:** `docs/causal_rules.json`

**Problem:**
`causal_rules.json` içindeki 3 kural (termal stres, hidrolik zorlanma, soğuk makine) genel hidrolik pres fiziğine dayalı. Bu fabrikanın HPR makinelerinde gerçekten yaşanan arıza kalıplarını yansıtmıyor.

Gemini bir alarm ürettiğinde bağlam paketine bu kuralları ekliyor. Kurallar fabrikaya özgü olmazsa Gemini'nin analizi yüzeysel kalır.

**Bakım mühendisinden alınması gereken bilgiler:**
1. Bu preslerde en sık hangi arıza yaşanıyor?
2. Arızadan önce sensörler nasıl davranıyor? (hangi sensör, ne yönde, ne hızda)
3. Hangi kombinasyonu görünce "bu makineyi durdur" diyorsunuz?
4. Hangi kombinasyon normal görünüyor ama aslında sorun işareti?

**Eklenecek kural formatı (`docs/causal_rules.json`):**
```json
"filtre_tikanma_basınç_yükselişi": {
  "condition": {
    "main_pressure_ratio": "> 0.85",
    "pressure_line_filter_dirty_minutes": "> 60"
  },
  "risk_multiplier": 25.0,
  "explanation_tr": "Kirli filtre hidrolik direnci artırıyor, pompa yüksek basınçla çalışıyor.",
  "action_tr": "Filtreyi değiştirin. 15 dakika içinde basınç düşmezse pompayı kontrol edin."
}
```

**Not:** `context_builder.py` bu kuralları otomatik değerlendirir ve Gemini'ye gönderir.
Boolean sensör süresi için `enriched_sensors`'a `{sensör_adı}_minutes` şeklinde ekleme yapılması gerekebilir.

---

### ✅ P2-2 — State Store Thread Lock

**Durum:** ✅ Tamamlandı (Hali hazırda `RLock` ile korunuyor)
**Dosya:** `src/core/state_store.py`

**Problem:**
Ana thread `state` dict'ini sürekli güncellerken checkpoint thread her 5 dakikada `save_state()` çağırıyor. `for mid, ms in state.items()` dönerken aynı dict'e eleman eklenirse `RuntimeError` olabilir. Python GIL bunu büyük ölçüde önler ama garanti değil.

**Çözüm:**
```python
import threading
_STATE_LOCK = threading.RLock()

def update_numeric(state, ...):
    with _STATE_LOCK:
        # mevcut kod

def save_state(state, ...):
    with _STATE_LOCK:
        # mevcut kod
```

---

### ✅ P2-3 — context_collector.py Büyük Dosya I/O

**Durum:** ✅ Tamamlandı (2026-04-20 - JSONL formatına geçildi)

**Problem:**
`rich_context_windows.json` her 5 dakikada tamamen yeniden yazılıyor. Dosya büyüdükçe bu disk I/O yükü olur.

**Çözüm:**
JSON Lines formatına geç (append-only):
```python
with open("rich_context_windows.jsonl", "a") as f:
    f.write(json.dumps(context_entry) + "\n")
```

---

## BÖLÜM 2 — ML Yeniden Eğitim Yol Haritası

> Veri kampanyası devam ederken bu bölüm değişmez. 17 Nisan'dan sonra uygulanır.

### Mevcut ML Modeli Neden Zayıf?

Model `total_faults_window` (%28.7) ve `active_sensors` (%25.6) özelliklerine %54 oranında dayanıyor. Bu özellikler zaten limit aşıldığında 1 olur — yani model gerçek bir öngörü yapmıyor, sadece threshold checker'ı taklit ediyor. Test F1=0.48.

Hedef: Arızadan 30-60 dakika önce, sensörler henüz limitte değilken uyarı verebilen model. F1 ≥ 0.65.

---

### Faz A — Veri Toplama (18 Mart → 17 Nisan 2026)

**Sistem şu an veri topluyor.** `rich_context_windows.json` her fault anında ±30 dakikalık sensör geçmişini kaydediyor. Hedef: 1500+ valid fault context.

**1 Nisan ara kontrol:**
```bash
python3 -c "
import json
d = json.load(open('rich_context_windows.json'))
print('Valid faults:', d['summary']['total_valid_faults'], '/ 1500 hedef')
"
```

Eğer 300'den az fault varsa: Kafka bağlantısını kontrol et, HPR makineleri gerçekten çalışıyor mu?

---

### Faz B — Feature Engineering (17-22 Nisan)

`total_faults_window` ve `active_sensors` özelliklerini **kaldır**.

Yerine `rich_context_windows.json`'dan şu özellikler türet:

```python
f"{sensor}__pre_fault_slope"       # Son 30 dk artış hızı
f"{sensor}__pre_fault_max_pct"     # Limitin maksimum yüzdesi
f"{sensor}__pre_fault_volatility"  # Standart sapma / ortalama
"operating_minutes_at_fault"       # Fault anında çalışma süresi
"recent_faults_24h"                # Son 24 saatteki fault sayısı
"pressure_temp_correlation"        # Basınç × sıcaklık ilişkisi
```

---

### Faz C — Model Eğitimi (22-27 Nisan)

```bash
PYTHONPATH=. python3 scripts/ml_tools/train_model.py
PYTHONPATH=. python3 scripts/ml_tools/shap_analyzer.py
```

**Başarı kriterleri:**
- Recall ≥ 0.85 (arızaların %85+ yakalanıyor)
- Precision ≥ 0.55 (alarmların %55+ gerçek)
- F1 ≥ 0.65

Tutmazsa: Faz A'ya dön, daha fazla veri topla.

---

### Faz D — Production Hazırlığı (27 Nisan+)

```
[ ] Docker — Dockerfile + secrets (.env)
[ ] Model versioning — her eğitimde model_v{tarih}.pkl
[ ] Monitoring — alert oranı, Kafka lag, thread sayısı
[ ] Boolean sensör özellikleri ML'e eklenmeli
```

---

## BÖLÜM 3 — Hızlı Başvuru

### Sistemi Başlatmak

```bash
source venv/bin/activate
PYTHONPATH=. python3 src/app/hpr_monitor.py
```

### Önemli Dosyalar

| Dosya | Ne işe yarıyor |
|-------|----------------|
| `src/app/hpr_monitor.py` | Ana uygulama — buradan başlatılır |
| `config/limits_config.yaml` | Tüm makine limitleri ve sistem ayarları |
| `docs/causal_rules.json` | Fizik tabanlı bağlam kuralları |
| `pipeline/model/model.joblib` | Eğitilmiş ML modeli (joblib formatı) |
| `pipeline/model/feature_names.json` | Eğitimdeki özellik listesi |
| `state.json` | 5 dk checkpoint — silme |
| `live_windows.json` | Basit veri penceresi (window_collector) |
| `rich_context_windows.jsonl` | Zengin bağlam penceresi (context_collector, JSONL) |
| `.env` | Gerçek API key ve IP'ler — git'e girmiyor |
| `.env.example` | .env şablonu — git'e giriyor |

### Ortam Değişkenleri

| Değişken | Varsayılan | Açıklama |
|----------|-----------|----------|
| `KAFKA_BOOTSTRAP_SERVERS` | `10.71.120.10:7001` | Kafka broker adresi |
| `KAFKA_TOPIC` | `mqtt-topic-v2` | Topic adı |
| `KAFKA_GROUP_ID` | `ariza-tahmin-pipeline` | Consumer group |
| `GEMINI_API_KEY` | — | AI Usta Başı için zorunlu |
| `CONFIG_PATH` | `config/limits_config.yaml` | Config dosyası yolu |

### IK Veritabanından Limit Güncelleme

IK yeni CSV gönderince:
```bash
python3 scripts/data_tools/sync_limits_from_db.py \
  --typefile /path/to/machinetypedataitems.csv \
  --machinefile /path/to/machinedataitems.csv \
  --machines HPR001,HPR003,HPR004,HPR005 \
  --tst-machines TST001,TST002,TST003,TST004 \
  --dry-run   # önce diff gör
```
HPR002 ve HPR006 Yatay Pres — bunları ayrıca kontrol et (F5-3b tamamlanana kadar).

### Sık Karşılaşılan Hatalar

| Hata | Neden | Çözüm |
|------|-------|-------|
| `ModuleNotFoundError: src.core` | PYTHONPATH ayarlı değil | `PYTHONPATH=. python3 ...` |
| `FileNotFoundError: limits_config.yaml` | Yanlış dizindesin | `cd kafka/` sonra çalıştır |
| `KafkaException: broker not available` | VPN bağlı değil | VPN'e bağlan, `.env`'i kontrol et |
| `GEMINI_API_KEY tanımlı değil` | Env var eksik | `.env.example`'dan `.env` oluştur, key ekle |
| `model.joblib bulunamadı` | Model eğitilmemiş | `PYTHONPATH=. python3 scripts/ml_tools/train_new_model.py` |

### Commit Mesaj Formatı

```
[F5-4] Gerçek fabrika arıza kuralları eklendi
[P2-2] State store thread lock eklendi
[ML]   Feature engineering v2 — leaky özellikler kaldırıldı
[FIX]  context_builder.py cold_startup_mask düzeltmesi
[DOC]  TODO güncellendi
```

---

## BÖLÜM 4 — Kural Kaynakları (Önemli Ayrım)

Sistemde iki farklı kural türü var. Bunları karıştırmak hatalara yol açar.

### 1. Mühendislik Limitleri (IK'dan — Güvenilir ✅)

`config/limits_config.yaml` içindeki min/max değerleri IK'nın veritabanından (`mes.machinetypedataitems`) alınmış. Bunlar mühendislik onaylı eşikler. Değiştirmek için `sync_limits_from_db.py` kullan, elle değiştirme.

### 2. Fizik Nedensellik Kuralları (Geliştirici Yazdı ⚠️)

`docs/causal_rules.json` içindeki kurallar IK'dan gelmiyor. Genel hidrolik pres fiziğine dayanıyor. Fabrika spesifik değil. Bakım mühendisinin bilgisiyle güçlendirilmesi gerekiyor (F5-4).

### 3. Mevcut Fizik Kuralları

| Kural | Koşul | Risk Etkisi |
|-------|-------|-------------|
| `thermal_stress` | Yağ sıcaklığı > 40°C **VE** basınç > 100 bar | +20 puan |
| `hydraulic_strain` | Basınç/limit > 0.8 **VE** her iki hız/limit < 0.2 | +30 puan |
| `cold_startup_mask` | Çalışma süresi < 60 dakika | Bonus ×0.5 (azalt) |

---

*Bu doküman projenin yaşayan hafızasıdır. Güncel tutmak herkesin sorumluluğu.*