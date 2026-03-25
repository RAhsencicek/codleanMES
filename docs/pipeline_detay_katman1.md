# Katman 1 — State Store (Hafıza)

> **Modül:** `src/core/state_store.py`
> **Son güncelleme:** 2026-03-24

---

## Ne Yapar?

Her makine için geçmiş ölçümleri RAM'de tutar. Tek bir anlık değer anlamsızdır — "basınç 87 bar" tehlikeli mi değil mi bilemezsin. Ama son 2 saatlik geçmişe bakınca "60'tan 87'ye sürekli çıkıyor" diyebiliyorsan durum farklıdır. Bu katman o geçmişi sağlar.

---

## Ring Buffer

Her makine, her sensör için `deque(maxlen=720)` kullanılır. 720 ölçüm × 10 saniye aralık = **2 saatlik geçmiş**.

```python
DEFAULT_WINDOW = 720
```

`deque` Python'un çift yönlü kuyruğu. `maxlen` dolunca yeni eleman eklendiğinde en eski otomatik düşer. Böylece hafıza hiçbir zaman büyümez — 6 makine × 10 sensör × 720 örnek ≈ 300 KB sabit RAM.

---

## EWMA (Gürültü Filtresi)

Ham sensör değerleri gürültülüdür. Anlık ortalama almak anlık sıçramalara duyarlıdır. EWMA (Exponentially Weighted Moving Average) geçmişe üstel ağırlık vererek gürültüyü filtreler:

```
yeni_ortalama = α × yeni_değer + (1 - α) × eski_ortalama
yeni_varyans  = α × (yeni_değer - yeni_ortalama)² + (1 - α) × eski_varyans
```

`α` (alfa) değeri sensöre göre `limits_config.yaml`'da ayarlanır:

| Sensör | Alpha | Anlam |
|--------|-------|-------|
| `oil_tank_temperature` | 0.03 | Çok yavaş — sıcaklık stabil değişir |
| `main_pressure` | 0.08 | Orta — basınç dalgalanabilir |
| `horitzonal_infeed_speed` | 0.05 | Yavaş — hız ani değişmemeli |
| `default` | 0.05 | Tanımsız sensörler için varsayılan |

Küçük alfa = geçmişe çok güven = yavaş tepki = güçlü gürültü filtresi.
Büyük alfa = yeni değere çok güven = hızlı tepki = zayıf gürültü filtresi.

---

## Güven Skoru (Confidence)

Sistem yeni başlatıldığında az veri var. Az veriyle trend hesaplamak veya alarm üretmek yanıltıcıdır. Her sensör için güven skoru hesaplanır:

```python
güven = min(toplam_ölçüm / 500, 1.0) × (geçerli_ölçüm / toplam_ölçüm)
```

- 500 ölçüme kadar kademeli artar
- `UNAVAILABLE` olan mesajlar geçerli sayılmaz
- Güven < 0.10 ise o sensör için alarm üretilmez

Bu sayede sistem her sabah yeniden başladığında ilk 1-2 saat alarm üretmez — yeterli güven oluşana kadar bekler.

---

## Boolean Sensörler

Kirli filtre, pompa durumu gibi açık/kapalı sensörler sayısal sensörlerden farklı işlenir. Soru "değer ne?" değil, "**kaç dakikadır kötü durumda?**" şeklindedir.

```python
update_boolean(state, machine_id, sensor, value, success_key)
# → kötü durumdaysa geçen dakika sayısı döner
# → iyi durumdaysa None döner
```

`success_key` `limits_config.yaml`'da tanımlı:
- `success_key: false` → FALSE değeri iyi durumu temsil eder (kirli filtre: FALSE = temiz)
- `success_key: true` → TRUE değeri iyi durumu temsil eder (pompa: TRUE = çalışıyor)

---

## Operating Minutes

Makinenin kaç dakikadır çalıştığını takip eder. Startup zamanı `state[machine_id]["startup_ts"]` olarak kaydedilir.

```python
get_operating_minutes(state, machine_id)
# → float: dakika cinsinden çalışma süresi
```

Bu değer iki yerde kullanılır:
1. `context_builder.py` → Gemini'ye "makine X saattir çalışıyor" bilgisi gönderir
2. `causal_rules.json` → `cold_startup_mask` kuralı için `operating_minutes < 60` kontrolü

---

## Disk Checkpoint (state.json)

RAM geçicidir. Elektrik kesilirse veya sistem yeniden başlatılırsa ring buffer uçar. Bunu önlemek için her 5 dakikada bir tüm state `state.json`'a yazılır.

**Atomik yazma:** Önce `.tmp` dosyasına yaz, sonra `os.replace()` ile asıl dosyanın üzerine geç. Bu sayede yarım yazılmış bozuk dosya riski yoktur.

```python
CHECKPOINT_PATH = "state.json"
```

Sistem başlarken `load_state()` bu dosyayı okur. Şema versiyonu uyuşmazsa (farklı versiyon) sıfırdan başlar.

**Maksimum kayıp:** 5 dakikalık veri. Kabul edilebilir — sistem bu süre içinde yeterli güven skoru oluşturur.

---

## API Özeti

```python
# Ring buffer'a ekle + EWMA güncelle
update_numeric(state, machine_id, sensor, value, alpha=0.08)

# Boolean: kaç dakikadır kötü durumda?
bad_minutes = update_boolean(state, machine_id, sensor, value, success_key=False)

# Ring buffer içeriğini al (trend hesabı için)
buffer = get_buffer(state, machine_id, sensor)  # → list[float]

# EWMA istatistiklerini al (spike filtresi için)
stats = get_ewma_stats(state, machine_id, sensor)
# → {"ewma_mean": float, "ewma_std": float, "count": int}

# Güven skoru
conf = get_confidence(state, machine_id, sensor)  # → 0.0 - 1.0

# Çalışma süresi
minutes = get_operating_minutes(state, machine_id)  # → float

# Diske kaydet
save_state(state)

# Diskten yükle
state = load_state()
```

---

## Bağlantılar

- Önceki katman: `docs/pipeline_detay_katman0.md`
- Sonraki katman: `docs/pipeline_detay_katman2.md`
- Kaynak kod: `src/core/state_store.py`
