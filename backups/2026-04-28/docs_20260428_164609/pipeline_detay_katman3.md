# Katman 3 — Alert Engine

> **Modül:** `src/alerts/alert_engine.py`
> **Son güncelleme:** 2026-03-24

---

## Ne Yapar?

Risk Scorer'dan gelen `RiskEvent` nesnesini alır ve teknisyenin terminaline anlamlı, renkli, aksiyona dönüştürülebilir bir uyarı olarak basar. Aynı zamanda alarm yorgunluğunu önlemek için throttle (kısıtlama) uygular.

---

## Throttle — Alarm Yorgunluğu Önleme

Bir sensör saatlerce limit üzerinde kalabilir. Her 10 saniyede bir alarm üretmek teknisyeni bunaltır ve önemli uyarıların gözden kaçmasına neden olur (alert fatigue).

```python
THROTTLE_NORMAL_MIN   = 30   # Normal alarmlar arası minimum dakika
THROTTLE_CRITICAL_MIN = 15   # Kritik alarmlar arası minimum dakika
```

`should_alert(machine_id, severity)` fonksiyonu son alarm zamanını `_last_alert` dict'inde tutar. Yeterli süre geçmediyse `False` döner ve alarm bastırılır.

---

## İki Çalışma Modu

### 1. Risk Event Modu (Ana Mod)

`risk_scorer.py`'den gelen `RiskEvent` nesnesi doğrudan `process_alert()` fonksiyonuna gelir.

```python
def process_alert(event: RiskEvent, min_score: float = 20.0) -> bool:
```

- Skor `min_score` altındaysa sessizce atlanır
- Throttle geçilmediyse atlanır
- Geçildiyse renkli panel terminale basılır

### 2. Hybrid Alert Modu

`generate_hybrid_alert()` ile iki katmanlı alarm üretilir:

```
Katman 1 → detect_faults_direct()      → FAULT (kesin, %100 güven)
Katman 2 → predict_pre_fault_direct()  → PRE_FAULT_WARNING (olasılıksal)
```

Aynı anda hem FAULT hem PRE_FAULT_WARNING oluşursa öncelik sırasına göre sadece en kritik gösterilir:

```python
FAULT (3) > PRE_FAULT_WARNING (2) > SOFT_LIMIT_WARNING (1)
```

---

## Alarm Tipleri

| Tip | Tetikleyici | Güven | Renk |
|-----|------------|-------|------|
| `FAULT` | Limit aşıldı (IK eşiği) | %100 | 🔴 Kırmızı |
| `PRE_FAULT_WARNING` | ML anomali tahmini | %50-100 | 🟡 Sarı |
| `SOFT_LIMIT_WARNING` | Limite %85 yaklaştı | %80 | ⚠️ Mavi |

---

## Terminal Çıktısı

`rich` kütüphanesi kuruluysa renkli panel, değilse düz metin.

### FAULT Alarm Örneği

```
╭─────────────────────────────── HPR001 — FAULT ───────────────────────────────╮
│ 🔴 FAULT ALERT                                                                │
│ ──────────────────────────────────────────────────────────────────────────── │
│ Makine: HPR001                                                                │
│ Tip:    KESİN (confidence: %100)                                              │
│ Saat:   14:32:07                                                              │
│ ──────────────────────────────────────────────────────────────────────────── │
│ Sebep:                                                                        │
│   • main_pressure: 117.3 bar (max: 110 bar) → %6.6 aşım                      │
│   • oil_tank_temperature: 46.2°C (max: 45°C) → %2.7 aşım                    │
│   • ⚠️  MULTI-SENSOR FAULT: 2 sensör limit dışı!                             │
│ ──────────────────────────────────────────────────────────────────────────── │
│ Öneri: ACİL: Makineyi durdur, basınç sistemini kontrol et                    │
╰──────────────────────────────────────────────────────────────────────────────╯
```

### PRE_FAULT_WARNING Örneği

```
╭──────────────────────────── HPR003 — PRE_FAULT_WARNING ──────────────────────╮
│ 🟡 PRE_FAULT_WARNING                                                          │
│ Makine: HPR003                                                                │
│ Tip:    OLASI (confidence: %73)                                               │
│ Zaman:  Önümüzdeki 30-60 dakika                                               │
│ Sebep:                                                                        │
│   • main_pressure: yükseliş trendi (+4.2 bar/saat, R²=0.89, ETA: 28 dk)     │
│   • Tetikleyenler: main_pressure__over_ratio, active_sensors                  │
│ Öneri: 24 saat içinde bakım planla                                            │
╰──────────────────────────────────────────────────────────────────────────────╯
```

---

## Risk Event Format (Eski Mod)

```
  ───────────────────────────────────────────────────────
  🚨 HPR001 — KRİTİK  [14:32:07]
  Risk: ████████████████░░░░ 82/100  | Güven: %87
  ───────────────────────────────────────────────────────
  • main_pressure: +4.2 bar/saat trend → 28 dk içinde limit 110 bar aşılır (R²=0.89)
  • oil_tank_temperature: 43.8°C — limite %97 yakın
  • 🔧 Termal stres tespit edildi (basınç × sıcaklık kombinasyonu)
  
  ⏱  Kritik eşiğe tahmini süre: 0sa 28dk
  
  🧠 ML Analizi:
    Anomali Olasılığı : %78  |  ML Skoru: 74/100
    [SHAP] Ana Basınç (% Aşım Oranı) arıza riskini ciddi ölçüde ARTIRIYOR
  
  Anlık değerler:
    main_pressure: 103.70
    oil_tank_temperature: 43.82
  ───────────────────────────────────────────────────────
```

---

## `detect_faults_direct()` — Kural Tabanlı Tespit

```python
def detect_faults_direct(
    machine_id: str,
    sensor_values: dict,
    limits_config: dict,
    soft_limit_ratio: float = 0.85,
) -> list[dict]:
```

Her sensör için:
1. `max` limitini al
2. `değer > max × 1.10` → KRİTİK
3. `değer > max` → YÜKSEK
4. `değer > max × 0.85` → DÜŞÜK (soft limit uyarısı)
5. `değer < min` → YÜKSEK (alt limit ihlali)

Multi-sensor kontrol: 2+ sensörde eş zamanlı ihlal varsa ekstra uyarı mesajı eklenir.

---

## `predict_pre_fault_direct()` — ML Tabanlı Erken Uyarı

```python
def predict_pre_fault_direct(
    machine_id: str,
    window_features: dict,    # state_store'dan ring buffer + EWMA
    ml_predictor,
    threshold: float = 0.50,
) -> dict | None:
```

- ML modeli mevcut değilse `None` döner
- `confidence < threshold` ise `None` döner (0.50 threshold — precision odaklı)
- Geçilirse: probability, confidence_level, trends, top_features, explanation döner

---

## Fonksiyon Özeti

| Fonksiyon | Ne Yapar? |
|-----------|----------|
| `should_alert(machine_id, severity)` | Throttle kontrolü |
| `detect_faults_direct(...)` | Kural tabanlı limit aşımı tespiti |
| `predict_pre_fault_direct(...)` | ML tabanlı pre-fault tahmini |
| `generate_hybrid_alert(...)` | İki katmanlı alarm üretimi |
| `process_hybrid_alert(alert)` | Hybrid alarm formatla + terminale bas |
| `process_alert(event)` | Risk event alarm formatla + terminale bas |
| `format_hybrid_alert_plain(alert)` | Düz metin format |
| `format_hybrid_alert_rich(alert)` | Renkli `rich` panel format |
| `_format_plain(event)` | Risk event düz metin format |
| `_format_rich(event)` | Risk event renkli format |

---

## Bağlantılar

- Önceki katman: `docs/pipeline_detay_katman2.md`
- Kaynak kod: `src/alerts/alert_engine.py`
