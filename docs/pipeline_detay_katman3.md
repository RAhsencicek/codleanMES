# 🏭 Katman 3 — İletişim & Alert Engine

> **Son güncelleme:** 2026-03-13  
> **Durum:** ✅ Güncel  
> **Sorumlu Modül:** `src/alerts/alert_engine.py`

---

Bu katman **iletişim katmanıdır**. Risk skoru eşiği geçtiyse insana anlamlı, eyleme dönüştürülebilir bir uyarı üretir.

### 1. Alert Throttling — Alarm Yorgunluğu Önleme
Bir sensör saatlerce limit üzerinde kalabilir. Bu durumda her 10 saniyede bir alert üretmek teknisyeni bunaltır (alarm fatigue) ve önemli uyarıların gözden kaçmasına neden olur.
**Kural:** Aynı makine için 30 dakikada en fazla 1 alert.
**İstisnai durum:** Severity KRİTİK ise throttle yarıya indirilir (15 dk). Çünkü limiti %10'dan fazla geçen bir değer bekletilemez.

### 2. Actionable AI (Eyleme Dönüştürülebilir Çıktı)
Açıklama üretimi şablon ve NLG (Doğal Dil Üretimi) tabanlıdır. Her alert için "Neden? Ne? Ne yapmalıyım?" sorularını yanıtlar.
Örn. Katman 2.5'ten bir ML Risk uyarısı geldiyse şablonun ötesinde XAI çevirileri kullanılarak uyarı mesajı üretilir.

### 3. Teknisyen Terminal Çıktısı
Göz yormayan renkli ve modüler bir terminal çıktısıyla teknisyenin önüne düşer.

### Örnek Alert Çıktısı
```markdown
⚠️ HPR005 — ERKEN UYARI
Risk Skoru: 100/100 | Güven: %100
📈 Tespit: Penceredeki Toplam Hata Veren Sensör Sayısı artış trendinde

🔍 AI Usta Başı Analizi (Neden Riskli?):
  • Aynı Anda Aktif Olan Sensör Sayısı arıza riskini ciddi ölçüde ARTIRIYOR (+0.155 katkı).
  • Ana Basınç (% Aşım Oranı) arıza riskini ciddi ölçüde ARTIRIYOR (+0.046 katkı).

💡 ÖNERİLEN AKSİYON: HEMEN MÜDAHALE EDİN: Makineyi rölantiye alın veya durdurun. Fiziksel bir arıza başlamak üzere.
⏱️ ETA: Eğer müdahale edilmezse 30-45 dakika içinde donanımsal arıza beklenmektedir.
```

### 4. Alert Log Tablosu (PostgreSQL)
Her alert veritabanına kaydedilir. Bu tablo hem debugging hem de sonradan teknisyen feedback'leri ile ML eğitim döngüsüne veri sağlamak için *`alert_log`* şeması ile saklanır. Gelecekte model optimizasyonu için en değerli kaynaktır.
