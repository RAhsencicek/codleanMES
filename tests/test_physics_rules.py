"""
Faz 2.0 Physics-Informed Kurallar — Doğrulama Test Betiği
═══════════════════════════════════════════════════════════
Bu betik, CausalEvaluator'ın v2.0 kurallarını doğru şekilde
değerlendirdiğini test eder.

Çalıştır: PYTHONPATH=. python3 -m pytest tests/test_physics_rules.py -v
"""
import time
import sys
import os

from src.core import state_store as store
from src.analysis.causal_evaluator import CausalEvaluator
from src.analysis.risk_scorer import CAUSAL_RULES


RULES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs", "causal_rules.json"
)
evaluator = CausalEvaluator(RULES_PATH)


def test_operating_minutes():
    """TEST 1: Operating Minutes (Çalışma Süresi)"""
    print("\n" + "=" * 55)
    print("TEST 1: Operating Minutes (Çalışma Süresi)")
    print("=" * 55)

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

    print("  🎉 Operating Minutes testi BAŞARILI!")


def test_causal_evaluator_scenario_a():
    """TEST 2A: Ana basınç regülatör zorlanması (kural eşleşmesi)"""
    print("\n" + "=" * 55)
    print("TEST 2A: CausalEvaluator — Ana Basınç Regülatör Zorlanması")
    print("=" * 55)

    # main_pressure_slope > 0.05 → trend_info içinde main_pressure = 0.10
    strain_data = {
        "sensors": {"main_pressure": 105.0},
        "trend_info": {"main_pressure": 0.10},
    }
    name, explanation = evaluator.evaluate(strain_data)
    print(f"  Senaryo A (Basınç slope yüksek): kural='{name}'")
    assert name == "Ana Basinc Regulator Zorlanmasi", f"Beklenen 'Ana Basinc Regulator Zorlanmasi', got '{name}'"
    assert "basınç" in explanation.lower() or "regülatör" in explanation.lower()
    print("  ✅ Ana basınç regülatör zorlanması algılandı!")


def test_causal_evaluator_scenario_b():
    """TEST 2B: Kısmi koşul — eşleşmemeli"""
    print("\n" + "=" * 55)
    print("TEST 2B: CausalEvaluator — Kısmi Koşul (Eşleşmemeli)")
    print("=" * 55)

    # Sinsi iç kaçak ısısı: slope > 0.003 AMA sıcaklık < 39.0 → Eşleşmemeli
    partial_data = {
        "sensors": {"oil_tank_temperature": 35.0},
        "trend_info": {"oil_tank_temperature": 0.005},
    }
    name, _ = evaluator.evaluate(partial_data)
    print(f"  Senaryo B (Düşük sıcaklık + yüksek slope): kural='{name}'")
    assert name == "", f"Kısmi eşleşme kural tetiklememeli, got '{name}'"
    print("  ✅ Kısmi koşul eşleşmedi (doğru davranış)!")


def test_causal_evaluator_scenario_c():
    """TEST 2C: Normal çalışma — hiçbir kural tetiklenmemeli"""
    print("\n" + "=" * 55)
    print("TEST 2C: CausalEvaluator — Normal Çalışma")
    print("=" * 55)

    normal_data = {
        "sensors": {"main_pressure": 50.0, "oil_tank_temperature": 30.0},
        "trend_info": {"main_pressure": 0.01, "oil_tank_temperature": 0.001},
    }
    name, _ = evaluator.evaluate(normal_data)
    print(f"  Senaryo C (Normal çalışma): kural='{name}'")
    assert name == "", f"Normal durumda kural tetiklenmemeli, got '{name}'"
    print("  ✅ Normal çalışmada kural tetiklenmedi!")


def test_causal_rules_json_loading():
    """TEST 3: Causal Rules JSON Yükleme"""
    print("\n" + "=" * 55)
    print("TEST 3: Causal Rules JSON Yükleme")
    print("=" * 55)

    print(f"  Yüklenen kurallar: {list(CAUSAL_RULES.keys())}")
    assert "ana_basinc_regulator_zorlanmasi" in CAUSAL_RULES, "ana_basinc_regulator_zorlanmasi kuralı eksik!"
    assert "sinsi_ic_kacak_isisi" in CAUSAL_RULES, "sinsi_ic_kacak_isisi kuralı eksik!"
    assert "testere_bicak_korelmesi" in CAUSAL_RULES, "testere_bicak_korelmesi kuralı eksik!"
    assert "infeed_mekanik_sikisma" in CAUSAL_RULES, "infeed_mekanik_sikisma kuralı eksik!"
    print("  ✅ Tüm Causal Rules başarıyla yüklendi!")


if __name__ == "__main__":
    print("\n" + "╔" + "═" * 53 + "╗")
    print("║" + " " * 12 + "PHYSICS RULES TESTİ (v2.0)" + " " * 15 + "║")
    print("╚" + "═" * 53 + "╝")

    tests = [
        ("Operating Minutes", test_operating_minutes),
        ("CausalEvaluator A", test_causal_evaluator_scenario_a),
        ("CausalEvaluator B", test_causal_evaluator_scenario_b),
        ("CausalEvaluator C", test_causal_evaluator_scenario_c),
        ("Causal Rules JSON", test_causal_rules_json_loading),
    ]

    results = []
    for name, test_fn in tests:
        try:
            test_fn()
            results.append((name, True))
        except AssertionError as e:
            results.append((name, False))
            print(f"\n❌ {name} BAŞARISIZ: {e}")

    print("\n" + "=" * 55)
    print("TEST ÖZETİ")
    print("=" * 55)
    for name, passed in results:
        status = "✅ GEÇTİ" if passed else "❌ BAŞARISIZ"
        print(f"  {status} | {name}")

    all_passed = all(passed for _, passed in results)

    print("\n" + "=" * 55)
    if all_passed:
        print("🎉 TÜM FAZ 2.0 TESTLERİ BAŞARILI!")
    else:
        print("⚠️  BAZI TESTLER BAŞARISIZ")
    print("=" * 55 + "\n")
