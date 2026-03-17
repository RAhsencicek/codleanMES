"""
Faz 1.5 Physics-Informed Kurallar — Doğrulama Test Betiği
═══════════════════════════════════════════════════════════
Bu betik, Hydraulic Strain ve Cold Startup Mask kurallarının
risk_scorer ve state_store ile doğru çalıştığını test eder.

Çalıştır: PYTHONPATH=. python3 test_physics_rules.py
"""
import time, sys

# ─── 1) State Store: Operating Minutes Testi ─────────────────────────────────
print("=" * 60)
print("TEST 1: Operating Minutes (Çalışma Süresi)")
print("=" * 60)

from src.core import state_store as store

test_state = {}
store.ensure_machine(test_state, "HPR_TEST")
op_min = store.get_operating_minutes(test_state, "HPR_TEST")
print(f"  ✅ Makine kaydedildi. Çalışma süresi: {op_min:.1f} dakika")
assert op_min >= 0.0, "Operating minutes negatif olamaz!"

# Startup_ts'yi 90 dakika önceye set et (sıcak makine simülasyonu)
test_state["HPR_TEST"]["startup_ts"] = time.time() - (90 * 60)
op_min_warm = store.get_operating_minutes(test_state, "HPR_TEST")
print(f"  ✅ 90 dakika simülasyonu: {op_min_warm:.1f} dakika")
assert 89.5 <= op_min_warm <= 91.0, f"Beklenen ~90, got {op_min_warm}"

# Startup_ts'yi 30 dakika önceye set et (soğuk makine simülasyonu)
test_state["HPR_TEST"]["startup_ts"] = time.time() - (30 * 60)
op_min_cold = store.get_operating_minutes(test_state, "HPR_TEST")
print(f"  ✅ 30 dakika simülasyonu: {op_min_cold:.1f} dakika")
assert 29.5 <= op_min_cold <= 31.0, f"Beklenen ~30, got {op_min_cold}"

print("  🎉 Operating Minutes testi BAŞARILI!\n")


# ─── 2) Risk Scorer: Hydraulic Strain Testi ──────────────────────────────────
print("=" * 60)
print("TEST 2: Hydraulic Strain (Hidrolik Zorlanma)")
print("=" * 60)

from src.analysis.risk_scorer import _apply_physics_rules

# HPR001 limitleri (limits_config.yaml'dan)
hpr001_limits = {
    "main_pressure":         {"min": 0.0, "max": 110.0, "unit": "bar"},
    "horitzonal_infeed_speed": {"min": -300.0, "max": 300.0, "unit": "mm/sn"},
    "vertical_infeed_speed":   {"min": -300.0, "max": 300.0, "unit": "mm/sn"},
}

# SENARYO A: Basınç yüksek + Hız sıfır = Hidrolik Zorlanma!
strain_values = {
    "main_pressure": 100.0,        # 100/110 = %91 → > %80 ✓
    "horitzonal_infeed_speed": 5.0, # 5/300 = %1.7 → < %20 ✓
    "vertical_infeed_speed": 2.0,   # 2/300 = %0.7 → < %20 ✓
}

# Sıcak makine (90 dk) → Cold Startup dampen YOK
warm_state = {}
store.ensure_machine(warm_state, "HPR_TEST")
warm_state["HPR_TEST"]["startup_ts"] = time.time() - (90 * 60)

bonus, reasons = _apply_physics_rules("HPR_TEST", strain_values, hpr001_limits, warm_state)
print(f"  Senaryo A (Sıcak + Zorlanma): bonus={bonus:.1f}, nedenler={len(reasons)}")
for r in reasons:
    print(f"    → {r}")
assert bonus >= 25.0, f"Beklenen >= 25 puan, got {bonus}"
print("  ✅ Hidrolik Zorlanma algılandı!\n")

# SENARYO B: Aynı zorlanma AMA soğuk makine → Dampen edilmeli
cold_state = {}
store.ensure_machine(cold_state, "HPR_TEST")
cold_state["HPR_TEST"]["startup_ts"] = time.time() - (15 * 60)  # 15 dakika

bonus_cold, reasons_cold = _apply_physics_rules("HPR_TEST", strain_values, hpr001_limits, cold_state)
print(f"  Senaryo B (Soğuk + Zorlanma): bonus={bonus_cold:.1f}, nedenler={len(reasons_cold)}")
for r in reasons_cold:
    print(f"    → {r}")
assert bonus_cold < bonus, f"Soğuk makine bonusu ({bonus_cold}) sıcak makineden ({bonus}) düşük olmalı!"
print("  ✅ Soğuk makine toleransı uygulandı!\n")

# SENARYO C: Normal çalışma (basınç düşük) → Zorlanma YOK
normal_values = {
    "main_pressure": 50.0,           # 50/110 = %45 → < %80 ✗
    "horitzonal_infeed_speed": 200.0, # Normal hız
    "vertical_infeed_speed": 150.0,   # Normal hız
}
bonus_normal, reasons_normal = _apply_physics_rules("HPR_TEST", normal_values, hpr001_limits, warm_state)
print(f"  Senaryo C (Normal çalışma): bonus={bonus_normal:.1f}")
assert bonus_normal == 0.0, f"Normal durumda bonus 0 olmalı, got {bonus_normal}"
print("  ✅ Normal çalışmada fizik kuralları tetiklenmedi!\n")


# ─── 3) Causal Rules JSON Yükleme Testi ──────────────────────────────────────
print("=" * 60)
print("TEST 3: Causal Rules JSON Yükleme")
print("=" * 60)

from src.analysis.risk_scorer import CAUSAL_RULES
print(f"  Yüklenen kurallar: {list(CAUSAL_RULES.keys())}")
assert "hydraulic_strain" in CAUSAL_RULES, "hydraulic_strain kuralı eksik!"
assert "cold_startup_mask" in CAUSAL_RULES, "cold_startup_mask kuralı eksik!"
assert "thermal_stress" in CAUSAL_RULES, "thermal_stress kuralı eksik!"
print("  ✅ Tüm Causal Rules başarıyla yüklendi!\n")


# ─── SONUÇ ───────────────────────────────────────────────────────────────────
print("=" * 60)
print("🎉 TÜM FAZ 1.5 TESTLERİ BAŞARILI!")
print("=" * 60)
print("""
📊 Özet:
   ✅ Operating Minutes: Hesaplanabiliyor (startup_ts tabanlı)
   ✅ Hydraulic Strain: Yüksek basınç + düşük hız = Zorlanma algılanıyor
   ✅ Cold Startup Mask: Soğuk makine toleransı uygulanıyor
   ✅ Causal Rules JSON: 3 kural başarıyla yüklendi
   ✅ Normal durumda false positive üretilmiyor
""")
