"""
generate_technician_report.py — Technician Feedback Raporu
═══════════════════════════════════════════════════════════
Mock alert'leri technician feedback için hazırla.
"""

from datetime import datetime

print("\n" + "="*70)
print(" " * 20 + "TECHNICIAN FEEDBACK RAPORU")
print("="*70)

print(f"\n📅 Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(f"🎯 Konu: Hybrid Fault Prediction System - Alert Validation")
print(f"👤 Hazırlayan: R. Ahsen Çiçek")

# ──────────────────────────────────────────────────────────────
# SİSTEM ÖZETİ
# ──────────────────────────────────────────────────────────────
print("\n" + "-"*70)
print("SİSTEM ÖZETİ")
print("-"*70)

print("""
🔹 Hybrid Alert Engine: Rule-Based + ML Pre-Fault Prediction

   KATMAN 1: Rule-Based Fault Detection (KESİN)
   → Sensör limit aşımı tespit eder
   → Min/max limit kontrolü
   → Severity: DÜŞÜK, ORTA, YÜKSEK, KRİTİK
   
   KATMAN 2: ML Pre-Fault Prediction (OLASI)
   → 30-60 dakika önce bozulma öngörür
   → RandomForest model (CV F1: 0.686 ± 0.019)
   → Recall: 1.00 (tüm arızalar yakalandı!)

🔹 Alert Türleri:

   1. FAULT (KESİN ARIZA)
      → Sensör limit aşıldı
      → Action: ACİL bakım veya durdurma
      
   2. PRE_FAULT_WARNING (OLASI ARIZA)
      → ML bozulma öngörüyor
      → Action: İzleme ve planlama
      
   3. SOFT_LIMIT_WARNING (YAKLAŞIYOR)
      → Sensör %85+ threshold'ta
      → Action: Dikkatli izleme

🔹 Alert Önceliklendirme:
   
   FAULT > PRE_FAULT_WARNING > SOFT_LIMIT_WARNING
   → Sadece en önemli alert gösterilir (alert spam önleme)
""")

# ──────────────────────────────────────────────────────────────
# ALERT ÖRNEKLERİ
# ──────────────────────────────────────────────────────────────
print("\n" + "-"*70)
print("ALERT ÖRNEKLERİ VE FEEDBACK SORULARI")
print("-"*70)

# Örnek 1
print("""
┌─────────────────────────────────────────────────────────────────┐
│ ÖRNEK 1: NORMAL OPERASYON                                       │
├─────────────────────────────────────────────────────────────────┤
│ Senaryo: Makine full speed çalışıyor                           │
│                                                                  │
│ Sensör Değerleri:                                               │
│   • main_pressure: 95.0 bar (max: 110) → %86                   │
│   • horizontal_press: 100.0 bar (max: 120) → %83               │
│   • oil_temperature: 38.0°C (max: 45) → %84                    │
│                                                                  │
│ Sistem Kararı: ✅ ALERT YOK                                     │
│                                                                  │
│ Soru: Bu karar doğru mu?                                        │
│ ☐ Evet, normal operasyon                                        │
│ ☐ Hayır, uyarı verilmeliydi                                     │
└─────────────────────────────────────────────────────────────────┘
""")

# Örnek 2
print("""
┌─────────────────────────────────────────────────────────────────┐
│ ÖRNEK 2: SOFT LIMIT WARNING (%85 THRESHOLD)                     │
├─────────────────────────────────────────────────────────────────┤
│ Senaryo: Sensörler limite yaklaşıyor                            │
│                                                                  │
│ Sensör Değerleri:                                               │
│   • main_pressure: 105.0 bar (max: 110) → %95 ⚠️               │
│   • horizontal_press: 115.0 bar (max: 120) → %96 ⚠️            │
│   • oil_temperature: 42.0°C (max: 45) → %93 ⚠️                 │
│                                                                  │
│ Sistem Kararı: ⚠️  SOFT_LIMIT_WARNING                           │
│   Severity: DÜŞÜK                                               │
│   Recommendation: "Dikkat: Sensör değerlerini izlemeye devam et"│
│                                                                  │
│ Sorular:                                                        │
│ 1. Bu uyarı faydalı mı?                                         │
│    ☐ Evet, erken uyarı sistemi olarak çalışıyor                │
│    ☐ Hayır, gereksiz alert fatigue yaratıyor                   │
│                                                                  │
│ 2. Severity "DÜŞÜK" doğru mu?                                   │
│    ☐ Evet, uygun                                                │
│    ☐ Hayır, daha yüksek olmalı                                 │
│                                                                  │
│ 3. Threshold %85 doğru mu?                                      │
│    ☐ Evet                                                       │
│    ☐ Hayır, ___% olmalı                                        │
└─────────────────────────────────────────────────────────────────┘
""")

# Örnek 3
print("""
┌─────────────────────────────────────────────────────────────────┐
│ ÖRNEK 3: HARD FAULT - SINGLE SENSOR                             │
├─────────────────────────────────────────────────────────────────┤
│ Senaryo: Ana basınç limit aştı                                  │
│                                                                  │
│ Sensör Değerleri:                                               │
│   • main_pressure: 118.0 bar (max: 110) → %107.3 🔴            │
│   • horizontal_press: 100.0 bar (max: 120) → %83 ✓             │
│   • oil_temperature: 38.0°C (max: 45) → %84 ✓                  │
│                                                                  │
│ Sistem Kararı: 🔴 FAULT                                         │
│   Severity: YÜKSEK                                              │
│   Recommendation: "İlk fırsatta bakım planla"                   │
│                                                                  │
│ Sorular:                                                        │
│ 1. Bu fault doğru tespit edildi mi?                             │
│    ☐ Evet                                                       │
│    ☐ Hayır, false positive                                     │
│                                                                  │
│ 2. Severity "YÜKSEK" doğru mu?                                  │
│    ☐ Evet                                                       │
│    ☐ Hayır, ___ olmalı                                         │
│                                                                  │
│ 3. Recommendation actionable mı?                                │
│    ☐ Evet, ne yapılacağı açık                                  │
│    ☐ Hayır, daha spesifik olmalı                               │
└─────────────────────────────────────────────────────────────────┘
""")

# Örnek 4
print("""
┌─────────────────────────────────────────────────────────────────┐
│ ÖRNEK 4: MULTI-SENSOR KRİTİK FAULT                              │
├─────────────────────────────────────────────────────────────────┤
│ Senaryo: 3 sensör birden limit dışı + %10+ aşım                 │
│                                                                  │
│ Sensör Değerleri:                                               │
│   • main_pressure: 125.0 bar (max: 110) → %113.6 🔴            │
│   • horizontal_press: 135.0 bar (max: 120) → %112.5 🔴         │
│   • lower_ejector: 122.0 bar (max: 110) → %110.9 🔴            │
│   • oil_temperature: 48.0°C (max: 45) → %106.7 🔴              │
│                                                                  │
│ Sistem Kararı: 🔴 FAULT (KRİTİK)                                │
│   Multi-Sensor: EVET (4 sensör!)                                │
│   Recommendation: "ACİL: Makineyi durdur, basınç sistemini      │
│                    kontrol et"                                  │
│                                                                  │
│ Sorular:                                                        │
│ 1. Kritik severity doğru mu?                                    │
│    ☐ Evet, acil durum                                           │
│    ☐ Hayır, abartılı                                           │
│                                                                  │
│ 2. Recommendation uygun mu?                                     │
│    ☐ Evet, acil durdurma gerekli                                │
│    ☐ Hayır, farklı olmalı                                      │
└─────────────────────────────────────────────────────────────────┘
""")

# ──────────────────────────────────────────────────────────────
# GENEL DEĞERLENDİRME
# ──────────────────────────────────────────────────────────────
print("\n" + "-"*70)
print("GENEL DEĞERLENDİRME")
print("-"*70)

print("""
Aşağıdaki soruları lütfen cevaplayın:

1. Hangi alert türleri faydalı?
   ☐ FAULT (Kesin arıza tespiti)
   ☐ PRE_FAULT_WARNING (ML ile erken uyarı)
   ☐ SOFT_LIMIT_WARNING (Limite yaklaşma uyarısı)
   ☐ Hiçbiri faydalı değil
   ☐ Diğer: ____________________

2. Hangi alert'ler gereksiz / alert fatigue yaratıyor?
   ☐ FAULT alert'leri
   ☐ PRE_FAULT_WARNING alert'leri
   ☐ SOFT_LIMIT_WARNING alert'leri
   ☐ Hiçbiri, hepsi faydalı
   ☐ Diğer: ____________________

3. Severity seviyeleri doğru mu?
   ☐ Evet, tüm severity'ler uygun
   ☐ Hayır, bazıları yanlış:
      Açıklama: ____________________

4. Recommendations (öneriler) actionable mı?
   ☐ Evet, ne yapılacağı açık
   ☐ Hayır, daha spesifik olmalı
   Örnek: ____________________

5. Threshold ayarı (0.50) hakkında düşünceniz? (Yeni: Precision-focused)
   ☐ Çok düşük, çok fazla false positive verir
   ☐ Uygun
   ☐ Çok yüksek, bazı arızaları kaçırır
   Öneri: _____ olmalı

6. Soft limit warning (%85 threshold) faydalı mı?
   ☐ Evet, erken uyarı olarak kullanışlı
   ☐ Hayır, gereksiz alert
   Öneri: _____% olmalı

7. Multi-sensor fault detection hakkında?
   ☐ Çok önemli, kritik durumları gösteriyor
   ☐ Gereksiz, tek sensor faults yeterli
   Görüş: ____________________

8. ML pre-fault prediction (30-60 dk erken uyarı) hakkında?
   ☐ Çok faydalı, proaktif bakım sağlar
   ☐ Şüpheli, güvenilir değil
   ☐ Gereksiz, rule-based yeterli
   Görüş: ____________________

9. Alert önceliklendirme (FAULT > PRE_FAULT > SOFT_LIMIT) doğru mu?
   ☐ Evet, en önemli alert gösteriliyor
   ☐ Hayır, tüm alert'ler gösterilmeli
   Görüş: ____________________

10. Genel sistem güvenirliliği hakkında?
    ☐ Tamamen güvenilir, production'da kullanılabilir
    ☐ Güvenilir ama küçük ayarlar gerekli
    ☐ Şüpheli, daha fazla test gerekli
    ☐ Güvenilir değil, yeniden geliştirme gerekli
    
    Açıklama: ____________________
""")

# ──────────────────────────────────────────────────────────────
# EK NOTLAR
# ──────────────────────────────────────────────────────────────
print("\n" + "-"*70)
print("EK NOTLAR VE ÖNERİLER")
print("-"*70)

print("""
Teknisyen Notları:
_____________________________________________________________________
_____________________________________________________________________
_____________________________________________________________________
_____________________________________________________________________

Önerilen Değişiklikler:
_____________________________________________________________________
_____________________________________________________________________
_____________________________________________________________________

Bir Sonraki Adımlar:
☐ Threshold tuning (feedback'e göre)
☐ Limit config güncelleme
☐ Alert recommendation iyileştirme
☐ Additional testing required
☐ Production deployment ready

""")

print("\n" + "="*70)
print("FEEDBACK FORMU TAMAMLANDI")
print("="*70)
print("\n💡 Talimatlar:")
print("   1. Bu formu yazdır veya PDF olarak kaydet")
print("   2. Technisyenlere dağıt")
print("   3. Cevapları topla")
print("   4. Feedback'e göre sistemi optimize et")
print("\n")
