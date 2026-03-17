# 🏭 Katman 1 — State Store (Bellek)

> **Son güncelleme:** 2026-03-13  
> **Durum:** ✅ Güncel  
> **Sorumlu Modül:** `src/core/state_store.py`, `src/core/data_feeder.py`
> **Veri Toplama:** `scripts/data_tools/window_collector.py`

---

Bu katman pipeline'ın **belleğidir**. Tek bir Kafka mesajı anlık değeri verir ama "bu değer artıyor mu, azalıyor mu, ne kadar süredir bu seviyede?" sorularını yanıtlamak için geçmişe ihtiyaç vardır. State store her makine için bu geçmişi RAM'de tutar.

### 📡 Veri Akışı (Katman 0 → Katman 1)

```
Kafka Consumer (data_feeder.py)
        ↓
Veri Doğrulama (validator)
        ↓
Window Collector (window_collector.py) → live_windows.json
        ↓
State Store (state_store.py) → state.json
```

**`data_feeder.py`:** Kafka'dan gelen ham veriyi okur, doğrular ve pipeline'a iletir.

**`window_collector.py`:** Analiz katmanından bağımsız olarak, ML eğitimi için canlı veri pencereleri toplar. Her HPR mesajını kaydeder:
- **Normal pencereler:** Saatte 3 adet (her makine)
- **Fault pencereleri:** Her limit aşımı anında
- **Çıktı:** `live_windows.json`

### 1. Ring Buffer (Kayan Pencere)
Her sensörün son 720 ölçümü (`maxlen=720`) tutulur. Bu 10 saniyelik sıklıkla yaklaşık 2 saate denk gelir. N dolarsa en eski değer otomatik silinir. Sıcaklık gibi yavaş değişen trendler için bu pencere kritik olmakla birlikte `limits_config.yaml` üzerinden ayarlanabilir.

### 2. EWMA (Online İstatistik)
Hareketli Ortalama hesaplamak için tüm diziyi toplamak yerine her yeni girdide "Öğrenme Hızı" (alpha) kullanılarak anlık istatistik güncellenir.
`new_mean = alpha * new_value + (1 - alpha) * old_mean`
Sıcaklıkta yavaş (`0.07`), basınçta yüksek (`0.25`) alpha gibi dinamik güncellemeler config dosyasında mevcuttur.

### 3. Confidence Score (Sistem Ne Kadar Güvenilir?)
Sensörün son N saatteki değerlerinden ne kadarı **UNAVAILABLE** oldu? Veya model eğitimindeki F1-skorları gibi makine geçmiş istatistiksel durumunu gösterir. Olası 0-1 arasında güven hesabı. `Valid_count / Sample_count` formülü ile ölçülür. %30'un altında gelen uyarılara "[DÜŞÜK GÜVEN]" eki konur.

### 4. Boolean Takibi
Boolean sensörlerin (`filter_dirty = TRUE`) anlık olarak var olması değil "ne kadar süredir bu halde olduğu" da takip edilir (örn: Son 2 saat 14 dakikadır kirli).
 
### 5. Atomik Checkpoint
RAM'deki state her 5 dakikada bir geçici bir `.tmp` dosyasına yazılır, ardından `os.replace()` ile atomik disk üzerine `state.json` şeklinde basılır. Elektrik kopmalarında bile veri kirliliği yaşanmaz.

### 6. Operating Minutes (Çalışma Süresi) - Yeni Özellik Faz 1.5
Sensör değerlerinden bağımsız olarak, makinenin son kalkış (startup) anından itibaren kaç saniye/dakika boyunca aktif (`RUNNING`) kaldığı RAM'de hesaplanır. Bu özellik XAI ve risk hesaplamasında "Soğuk Makine" kararlarını dinamik olarak vermek için kullanılır. Formül: `(time.time() - startup_time) / 60`.
