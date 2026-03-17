# 🏭 Katman 0 — Veri Girişi ve Doğrulama

> **Son güncelleme:** 2026-03-13  
> **Durum:** ✅ Güncel  
> **Sorumlu Modül:** `src/core/data_validator.py`

---

Bu katman **güvenlik görevlisi** gibi davranır. Ham Kafka verisini inceler, sorunlu olanları reddeder ya da işaretler. Kabul edilen veri temiz ve tip-güvenlidir. Bu katmanı `src/core/data_validator.py` yönetir.

**Neden bu katman kritik?**
Kafka'dan gelen `result` alanları *her zaman string*. `"52.1"` ile `52.1` arasındaki fark matematiksel olarak kritik. Üstelik `"UNAVAILABLE"` değerini `float()`'a verirseniz program çöker. Bu katman olmadan sonraki katmanlar her ölçümde hatayla karşılaşır.

### 1. Schema Doğrulama
Her Kafka mesajında bulunması *zorunlu* alanları kontrol eder. Eksikse mesaj atlanır.
Gerekli yollar: `header.sender`, `header.creationTime` ve `streams[].componentStream[].componentId`.

### 2. UNAVAILABLE → None Dönüşümü + Ondalık Virgül Düzeltmesi
> **⚠️ Saha Bulgusu:** Kafka verilerinde tüm sayısal değerler **Türkçe locale** ile geliyor. Ondalık ayracı nokta değil **virgül** (`"37,022568"`). `float()` virgülle çalışmaz — bu katman bunu düzelterek eksik veriyi işleme sokmadan yoksayar:

```python
def safe_numeric(value) -> float | None:
    if value is None or str(value).strip().upper() in ("UNAVAILABLE", ""):
        return None
    try:
        normalized = str(value).strip().replace(",", ".")  # TR locale fix
        return float(normalized)
    except (ValueError, TypeError):
        return None
```

### 3. Timestamp Gecikme Kontrolü (Stale Data)
Kafka consumer geride kalırsa (örn. ağ sorunu) eski mesajlar sırayla işlenir. 5 dakikadan eski veriler (`> 300` saniye) trend hesabını bozmasın diye **TrendDetector'a iletilmez**. Ancak anlık eşik (Threshold) hesabına dahil edilir.

### 4. Spike Filtresi
Sensör arızası veya geçici elektrik gürültüsü nedeniyle değer aniden anlamsız yerlere sıçrayabilir.
**Mantık (5σ Kuralı):** Yeni değer, mevcut EWMA ortalamasından 5 standart sapma uzaktaysa spike sayılır ve reddedilir. Bu olasılık 3 milyonda 1'dir.

### 5. Startup Mask
Hidrolik presler soğuk başlar. İlk 60 dakika sıcaklık hızla yükselir — bu bir arıza trendi değil, ısınmadır. Sistem `IDLE` → `RUNNING` durumunu yakalar ve sonraki 60 dakikada gelen veriler için trend tabanlı erken uyarıları (TrendDetector) **maskeler (kapatır)**. Üst limit aşımı (Threshold) devam eder.
