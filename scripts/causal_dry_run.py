#!/usr/bin/env python3
"""
Codlean MES — Causal Rules v2 Dry-Run Simülatörü
10 altın kuralı sanal sensör verileriyle test eder.
Her kural için beklenen tetiklenme/tetiklenmeme sonuçlarını raporlar.

Kullanım:
    PYTHONPATH=. python3 scripts/causal_dry_run.py
"""

import json
import logging
import os
import sys
import yaml
from datetime import datetime
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | DRY-RUN | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("dry_run")

# ─── Kural JSON Yükle ────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_PATH = os.path.join(ROOT, "docs", "causal_rules_v2.json")

with open(RULES_PATH) as f:
    rules_data = json.load(f)

RULES = rules_data["rules"]
TYPE_MAP = rules_data["hpr_type_filter"]
DIKEY = TYPE_MAP["dikey_pres"]   # HPR001, HPR003, HPR005
YATAY = TYPE_MAP["yatay_pres"]   # HPR002, HPR004, HPR006

# ─── Config Limitleri ─────────────────────────────────────────────────────────
CFG_PATH = os.path.join(ROOT, "config", "limits_config.yaml")
with open(CFG_PATH) as f:
    cfg = yaml.safe_load(f)

def get_limits(machine_id: str) -> dict:
    return cfg.get("machine_limits", {}).get(machine_id, {})

# ─── Koşul Değerlendirici ────────────────────────────────────────────────────
def evaluate_condition(
    condition: dict,
    sensor_values: dict,
    machine_limits: dict,
    operating_minutes: float = 120.0,
) -> tuple[bool, list[str]]:
    """
    Bir kuralın koşullarını sensör verileriyle karşılaştırır.
    Dönüş: (tetiklendi_mi, [detay açıklamalar])
    """
    details = []
    all_met = True

    for cond_key, cond_expr in condition.items():
        op = ">" if ">" in cond_expr else "<"
        threshold = float(cond_expr.replace(">", "").replace("<", "").strip())

        # Ratio bazlı koşullar
        if cond_key.endswith("_ratio"):
            base_sensor = cond_key.replace("_ratio", "")
            val = sensor_values.get(base_sensor)
            limit_max = machine_limits.get(base_sensor, {}).get("max")
            if val is None or limit_max is None or limit_max == 0:
                details.append(f"  ⬜ {cond_key}: veri yok (sensör/limit eksik)")
                all_met = False
                continue
            # Hız sensörleri negatif olabilir → abs() kullan
            ratio = abs(val) / abs(limit_max)
            actual = ratio
            label = f"{base_sensor} ratio"
        elif cond_key == "operating_minutes":
            actual = operating_minutes
            label = "operating_minutes"
        elif cond_key == "pressure_line_filter_dirty_minutes":
            actual = sensor_values.get("_filter_dirty_minutes", 0)
            label = "filter_dirty_minutes"
        else:
            actual = sensor_values.get(cond_key)
            label = cond_key
            if actual is None:
                details.append(f"  ⬜ {cond_key}: veri yok")
                all_met = False
                continue

        if op == ">":
            met = actual > threshold
        else:
            met = actual < threshold

        icon = "✅" if met else "❌"
        details.append(f"  {icon} {label} = {actual:.2f} {op} {threshold} → {'MET' if met else 'NOT MET'}")
        if not met:
            all_met = False

    return all_met, details


def check_hpr_type(rule: dict, machine_id: str) -> bool:
    """Kuralın HPR tipine uygun olup olmadığını kontrol eder."""
    allowed_types = rule.get("hpr_types", ["all"])
    if "all" in allowed_types:
        return True

    machine_type = None
    if machine_id in DIKEY:
        machine_type = "dikey_pres"
    elif machine_id in YATAY:
        machine_type = "yatay_pres"

    return machine_type in allowed_types


# ─── TEST SENARYOLARI ─────────────────────────────────────────────────────────
# Her senaryo bir HPR makinesi + sensör kombinasyonu tanımlar
TEST_SCENARIOS = [
    # 1. Termal Stres ve Sızıntı Riski
    {
        "name": "Termal Stres — HPR001 yağ 42°C + basınç 100 bar",
        "machine_id": "HPR001",
        "sensors": {
            "oil_tank_temperature": 42.0,
            "main_pressure": 100.0,
            "horizontal_press_pressure": 30.0,
            "lower_ejector_pressure": 20.0,
            "horitzonal_infeed_speed": -50.0,
            "vertical_infeed_speed": 40.0,
        },
        "operating_minutes": 120,
        "expected_rules": ["termal_stres_ve_sizinti_riski"],
    },
    # 2. Pompa Kavitasyonu
    {
        "name": "Kavitasyon — HPR003 basınç 105 bar + yağ 44°C",
        "machine_id": "HPR003",
        "sensors": {
            "oil_tank_temperature": 44.0,
            "main_pressure": 105.0,
            "horizontal_press_pressure": 60.0,
            "lower_ejector_pressure": 50.0,
            "horitzonal_infeed_speed": -30.0,
            "vertical_infeed_speed": 20.0,
        },
        "operating_minutes": 180,
        "expected_rules": ["termal_stres_ve_sizinti_riski", "pompa_kavitasyon_ve_hava_emme", "sogutma_sistemi_verimsizligi"],
    },
    # 3. İç Kaçak
    {
        "name": "İç Kaçak — HPR005 basınç düşük 55 bar + yağ 39°C",
        "machine_id": "HPR005",
        "sensors": {
            "oil_tank_temperature": 39.0,
            "main_pressure": 55.0,
            "horizontal_press_pressure": 20.0,
            "lower_ejector_pressure": 15.0,
            "horitzonal_infeed_speed": -10.0,
            "vertical_infeed_speed": 5.0,
        },
        "operating_minutes": 200,
        "expected_rules": ["ic_kacak_belirtisi_dusuk_basinc_yuksek_isi"],
    },
    # 4. Filtre Tıkanıklığı
    {
        "name": "Filtre Tıkanık — HPR001 basınç %85 + filtre 45dk kirli",
        "machine_id": "HPR001",
        "sensors": {
            "oil_tank_temperature": 37.0,
            "main_pressure": 95.0,
            "horizontal_press_pressure": 30.0,
            "lower_ejector_pressure": 20.0,
            "horitzonal_infeed_speed": -50.0,
            "vertical_infeed_speed": 40.0,
            "_filter_dirty_minutes": 45.0,
        },
        "operating_minutes": 300,
        "expected_rules": ["filtre_tikanikligi_ve_yuksek_direnc"],
    },
    # 5. Yatay Pres Hareket Düzensizliği
    {
        "name": "Yatay Hareket Düzensizliği — HPR002 yatay hız max + basınç 115",
        "machine_id": "HPR002",
        "sensors": {
            "horizontal_press_pressure": 115.0,
            "horitzonal_infeed_speed": -280.0,
        },
        "operating_minutes": 100,
        "expected_rules": ["yatay_pres_hareket_duzensizligi"],
    },
    # 6. Soğuk Başlangıç Aşırı Basınç (Dikey + Yatay)
    {
        "name": "Soğuk Başlangıç — HPR004 yeni açılmış + basınç 102",
        "machine_id": "HPR004",
        "sensors": {
            "horizontal_press_pressure": 50.0,
            "horitzonal_infeed_speed": -20.0,
            "main_pressure": 102.0,
        },
        "operating_minutes": 8,
        "expected_rules": ["soguk_baslangic_asiri_basinc"],
    },
    # 7. Dikey Pres Aşırı Yüklenme
    {
        "name": "Aşırı Yüklenme — HPR001 dikey hız max + basınç 108",
        "machine_id": "HPR001",
        "sensors": {
            "oil_tank_temperature": 36.0,
            "main_pressure": 108.0,
            "horizontal_press_pressure": 40.0,
            "lower_ejector_pressure": 30.0,
            "horitzonal_infeed_speed": -20.0,
            "vertical_infeed_speed": 260.0,
        },
        "operating_minutes": 90,
        "expected_rules": ["dikey_pres_asiri_yuklenme"],
    },
    # 8. Alt Ejektör Sıkışması
    {
        "name": "Ejektör Sıkışması — HPR003 ejektör 105 bar + dikey hız 3",
        "machine_id": "HPR003",
        "sensors": {
            "oil_tank_temperature": 35.0,
            "main_pressure": 60.0,
            "horizontal_press_pressure": 25.0,
            "lower_ejector_pressure": 105.0,
            "horitzonal_infeed_speed": -5.0,
            "vertical_infeed_speed": 3.0,
        },
        "operating_minutes": 150,
        "expected_rules": ["alt_ejektor_sikismasi"],
    },
    # 9. Yatay Pres Hidrolik Kayma (Drift)
    {
        "name": "Hidrolik Kayma — HPR006 yatay basınç 118 + hız 2",
        "machine_id": "HPR006",
        "sensors": {
            "horizontal_press_pressure": 118.0,
            "horitzonal_infeed_speed": 2.0,
        },
        "operating_minutes": 60,
        "expected_rules": ["yatay_pres_hidrolik_kayma_drift"],
    },
    # 10. Normal Durum — HIÇBIR KURAL TETİKLENMEMELİ
    {
        "name": "Normal Durum — HPR001 hepsi normal aralıkta",
        "machine_id": "HPR001",
        "sensors": {
            "oil_tank_temperature": 32.0,
            "main_pressure": 50.0,
            "horizontal_press_pressure": 30.0,
            "lower_ejector_pressure": 20.0,
            "horitzonal_infeed_speed": -80.0,
            "vertical_infeed_speed": 60.0,
        },
        "operating_minutes": 200,
        "expected_rules": [],
    },
]


# ─── ÇALIŞTIR ─────────────────────────────────────────────────────────────────
def main():
    print("=" * 78)
    print("  🧪 CODLEAN MES — CAUSAL RULES v2 DRY-RUN SİMÜLASYONU")
    print(f"  📋 10 Altın Kural × {len(TEST_SCENARIOS)} Senaryo")
    print(f"  ⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 78)
    print()

    total_pass = 0
    total_fail = 0
    results = []

    for i, scenario in enumerate(TEST_SCENARIOS, 1):
        sc_name   = scenario["name"]
        mid       = scenario["machine_id"]
        sensors   = scenario["sensors"]
        op_min    = scenario["operating_minutes"]
        expected  = set(scenario["expected_rules"])
        limits    = get_limits(mid)

        triggered = set()
        all_details = {}

        print(f"─── Senaryo {i}: {sc_name} ───")
        print(f"    Makine: {mid} ({'Dikey' if mid in DIKEY else 'Yatay'} Pres)")
        print(f"    Çalışma: {op_min} dk")
        print()

        for rule_name, rule in RULES.items():
            # HPR tipi kontrolü
            if not check_hpr_type(rule, mid):
                all_details[rule_name] = ("SKIP", ["  ⏭️  HPR tipi uyumsuz"])
                continue

            met, details = evaluate_condition(
                rule["condition"], sensors, limits, op_min
            )
            if met:
                triggered.add(rule_name)
                all_details[rule_name] = ("TRIGGERED", details)
            else:
                all_details[rule_name] = ("SAFE", details)

        # Sonuçları göster
        for rule_name in RULES:
            status, details = all_details.get(rule_name, ("SKIP", []))
            is_expected = rule_name in expected

            if status == "TRIGGERED":
                if is_expected:
                    icon = "🟢"
                    verdict = "BEKLENEN TETİKLENME ✓"
                else:
                    icon = "🔴"
                    verdict = "BEKLENMEYEN TETİKLENME ✗"
            elif status == "SAFE":
                if not is_expected:
                    icon = "⚪"
                    verdict = "Beklenen: tetiklenmedi"
                else:
                    icon = "🔴"
                    verdict = "BEKLENİYORDU AMA TETİKLENMEDİ ✗"
            else:
                icon = "⏭️ "
                verdict = "HPR tipi uyumsuz — atlandı"

            risk_m = RULES[rule_name].get("risk_multiplier", "?")
            print(f"  {icon} [{rule_name}] (risk:+{risk_m}) → {verdict}")
            if status == "TRIGGERED" or (status == "SAFE" and is_expected):
                for d in details:
                    print(f"      {d}")

        # Doğrulama
        passed = (triggered == expected)
        if passed:
            total_pass += 1
            print(f"\n  ✅ SENARYO BAŞARILI — Beklenen: {len(expected)}, Tetiklenen: {len(triggered)}")
        else:
            total_fail += 1
            missing = expected - triggered
            extra = triggered - expected
            print(f"\n  ❌ SENARYO BAŞARISIZ")
            if missing:
                print(f"     Eksik tetiklenme: {missing}")
            if extra:
                print(f"     Fazla tetiklenme: {extra}")

        results.append({
            "scenario": sc_name,
            "machine": mid,
            "expected": list(expected),
            "triggered": list(triggered),
            "passed": passed,
        })
        print()

    # ─── ÖZET ─────────────────────────────────────────────────────────────────
    print("=" * 78)
    print(f"  📊 DRY-RUN SONUCU: {total_pass}/{len(TEST_SCENARIOS)} senaryo BAŞARILI")
    if total_fail > 0:
        print(f"  ⚠️  {total_fail} senaryo BAŞARISIZ — kurallar gözden geçirilmeli")
    else:
        print(f"  🎯 TÜM KURALLAR DOĞRU ÇALIŞİYOR!")
    print("=" * 78)

    # JSON rapor kaydet
    report = {
        "timestamp": datetime.now().isoformat(),
        "total_scenarios": len(TEST_SCENARIOS),
        "passed": total_pass,
        "failed": total_fail,
        "results": results,
    }
    report_path = os.path.join(ROOT, "data", "causal_dry_run_report.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n  📁 Detaylı rapor: {report_path}")


if __name__ == "__main__":
    main()
