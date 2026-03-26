# Katman 0 — Veri Doğrulama

> **Modül:** `src/core/data_validator.py`
> **Son güncelleme:** 2026-03-24

---

## Ne Yapar?

Kafka'dan gelen ham JSON mesajını alır, güvenilirliğini kontrol eder ve temiz bir Python dict olarak sonraki katmana iletir. Bu katmandan geçmeyen veri sisteme girmez.

Neden gerekli? Fabrikadaki PLC cihazları farklı üreticilerden, farklı yazılım versiyonlarından. Biri sayıyı `"37,02"` yazar, diğeri `"37.02"`. Biri sensör okuyamazsa `"UNAVAILABLE"` gönderir. Ağ gecikmesiyle 8 dakika geç gelen mesajlar trend hesabını bozar. Bu katman bunların tamamını ele alır.

---

## Kontroller (Sırasıyla)

### 1. Schema Doğrulama
`header.sender`, `header.creationTime` ve `streams` alanları zorunlu. Bunlardan biri yoksa mesaj tamamen reddedilir, sonraki adımlara geçilmez.

### 2. Sayısal Dönüşüm — `safe_numeric()`

```python
safe_numeric("37,02")       → 37.02   (Türkçe locale virgül → nokta)
safe_numeric("UNAVAILABLE") → None
safe_numeric("")            → None
safe_numeric("52.1")        → 52.1
```

Bilinen metin değerleri (`"RUNNING"`, `"AUTO"`, `"FALSE"` vb.) DEBUG seviyesinde loglanır — bunlar format hatası değil, beklenen durum metinleridir. Rakam içeren ama parse edilemeyen değerler (`"37.5 bar"` gibi) WARNING verir çünkü o sensörün formatı değişmiş olabilir.

### 3. Boolean Dönüşüm — `safe_bool()`

```python
safe_bool("TRUE")        → True
safe_bool("FALSE")       → False
safe_bool("0")           → False
safe_bool("1")           → True
safe_bool("UNAVAILABLE") → None
```

### 4. Stale (Bayat) Veri Kontrolü

Mesajın `creationTime` alanı şu andan 5 dakikadan eskiyse `is_stale=True` olarak işaretlenir. Bu mesaj sisteme kabul edilir ama trend hesabı dışında tutulur. Neden tamamen reddedilmiyor? Çünkü EWMA güncelleme ve sayaç artırma için yine de bilgi taşır.

```python
STALE_SECONDS = 300  # 5 dakika
```

### 5. Spike Filtresi

İlk 15 ölçüm beklenir (ısınma için). Sonrasında her yeni değer için Z-skoru hesaplanır:

```
Z = |değer - EWMA_ortalama| / EWMA_std
```

Z > 5.0 ise spike sayılır ve sessizce atılır. Elektrik sıçraması, sensör arızası gibi anlık fiziksel anomaliler gerçek arıza olarak yorumlanmamalıdır.

```python
SPIKE_SIGMA          = 5.0
MIN_SAMPLES_FOR_SPIKE = 15
```

> **Not (2026-03-25 düzeltildi):** Bu filtre daha önce `ewma_state[machine_id][sensor]` yolunu arıyordu ama `state_store` yapısı `state[machine_id]["ewma_mean"][sensor]` şeklinde nested'dir. Bu uyumsuzluk nedeniyle spike filtresi hiç çalışmıyordu. `data_validator.py:319` doğru yapıya göre güncellendi.

### 6. Startup Maskesi

Makine `IDLE/STOPPED → RUNNING` geçişi yaptığında ilk 60 dakika `is_startup=True` işaretlenir. Bu sürede trend hesabı yapılmaz. Neden? Soğuk başlatma sırasında yağ sıcaklığı, basınç, hız değerleri hızla değişir — bu normaldir, alarm üretmemeli.

```python
STARTUP_MINUTES = 60
```

---

## Çıktı Formatı

Her makine için şu dict döner:

```python
{
    "machine_id":   "HPR001",
    "machine_type": "HPR",
    "timestamp":    "2026-03-24T14:22:11Z",
    "is_stale":     False,   # True ise trend hesabına katılmaz
    "is_startup":   False,   # True ise trend hesabına katılmaz
    "numeric":      {"main_pressure": 87.3, "oil_tank_temperature": 38.4, ...},
    "boolean":      {"pressure_line_filter_1_dirty": False, ...},
    "text":         {"execution": "RUNNING", "mode": "AUTO"},
}
```

Bir mesajda birden fazla makine olabilir. Fonksiyon liste döner.

---

## Önemli Not: `horitzonal_infeed_speed`

Kodda `horitzonal_infeed_speed` yazılı (z harfi fazla). Bu bir yazım hatası değil — PLC cihazının kendisi bu ismi kullanıyor. Kafka mesajlarında da bu şekilde geliyor. **Değiştirme.**

---

## Bağlantılar

- Sonraki katman: `docs/pipeline_detay_katman1.md`
- Kaynak kod: `src/core/data_validator.py`
