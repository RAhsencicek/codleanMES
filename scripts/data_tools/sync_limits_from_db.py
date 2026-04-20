"""
sync_limits_from_db.py — IK Veritabanından Limit Senkronizasyonu
═══════════════════════════════════════════════════════════════════
IK'nın veritabanından export ettiği CSV dosyalarını okuyup
config/limits_config.yaml'ı otomatik olarak günceller.

Kullanım:
    # Sadece değişiklikleri göster, yazma:
    PYTHONPATH=. python3 scripts/data_tools/sync_limits_from_db.py \\
        --typefile /path/to/machinetypedataitems.csv \\
        --machinefile /path/to/machinedataitems.csv \\
        --dry-run

    # Gerçekten yaz:
    PYTHONPATH=. python3 scripts/data_tools/sync_limits_from_db.py \\
        --typefile /path/to/machinetypedataitems.csv \\
        --machinefile /path/to/machinedataitems.csv \\
        --output config/limits_config.yaml

Merge Mantığı:
    1. machinetypedataitems.csv → Tip bazlı limitler (tüm HPR için ortak)
    2. machinedataitems.csv     → Makine bazlı override (varsa tip limitini ezer)
    3. is_violation_enabled=true olan sensörler alınır, diğerleri atlanır

Hangi Makine ID'leri Oluşturulur:
    Script, Kafka topic'inden hangi fiziksel makinelerin geldiğini bilmez.
    Bu nedenle --machines parametresiyle makine listesi verilmeli.
    Verilmezse sadece tip bazlı template çıkar, makine ID eklenmez.

Örnek:
    python3 scripts/data_tools/sync_limits_from_db.py \\
        --typefile downloads/machinetypedataitems.csv \\
        --machinefile downloads/machinedataitems.csv \\
        --machines HPR001,HPR002,HPR003,HPR004,HPR005,HPR006 \\
        --hpr-yatay HPR002,HPR006 \\
        --tst-machines TST001,TST002,TST003,TST004 \\
        --output config/limits_config.yaml \\
        --dry-run
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict
from typing import Optional

import yaml

# ─── Makine tipi → makine kodu prefix eşleştirmesi ──────────────────────────
# Veritabanındaki machinetypename → Kafka'daki makine ID prefix
TYPENAME_TO_PREFIX = {
    "Dikey Pres": "HPR",  # Type 003 — HPR001, HPR003, HPR004, HPR005
    "Yatay Pres": "HPR",  # Type 004 — HPR002, HPR006
    "Testere": "TST",  # Type 001 — TST001, TST002, TST003, TST004
    "Indüksiyon": "IND",  # Type 005 — IND001, IND002...
    "AbbRobot": "RBT",  # Type 002
    "Fanuc CNC": "CNC",  # Type 007
    "Kumlama": "KUM",  # Type 006
    "Döner Tabla": "DT",  # Type 008
    "Press 500 Ton": "P500",  # Type 009
}

# Boolean sensörlerin Türkçe etiketleri — veritabanındaki true_label/false_label
# Bu eşleştirme CSV'deki sütunlardan otomatik alınır
BOOLEAN_ALERT_MINUTES = {
    # Kirli filtreler: 30-60 dakika tolerans
    "pilot_pump_filter_1_dirty": 30,
    "pilot_pump_filter_2_dirty": 30,
    "pressure_line_filter_1_dirty": 60,
    "pressure_line_filter_2_dirty": 60,
    "pressure_line_filter_3_dirty": 60,
    "pressure_line_filter_4_dirty": 60,
    "pressure_line_filter_5_dirty": 60,
    "return_line_filter_1_dirty": 60,
    "return_line_filter_2_dirty": 60,
    # Seviye
    "oil_tank_level_low": 10,
    # Valf ve pompa
    "pump_1_suction_valve_ok": 5,
    "pump_2_suction_valve_ok": 5,
    "pump_3_suction_valve_ok": 5,
    "pump_4_suction_valve_ok": 5,
    "pump_5_suction_valve_ok": 5,
    "pilot_pump_active": 15,
}


def _safe_float(val: str) -> Optional[float]:
    """Boş veya None string'i güvenle float'a çevirir."""
    if not val or not val.strip():
        return None
    try:
        return float(val.strip())
    except (ValueError, TypeError):
        return None


def load_type_limits(filepath: str) -> dict:
    """
    machinetypedataitems.csv'yi okur.

    Dönüş:
        {
          "Dikey Pres": {
            "oil_tank_temperature": {
              "data_type": "number",
              "min_value": 0.0, "max_value": 45.0,
              "unit": "°C",
              "success_key": None,
              "true_label": None, "false_label": None,
              "description": "Yağ Tankı Sıcaklığı",
              "is_violation_enabled": True
            },
            ...
          }
        }
    """
    result: dict = defaultdict(dict)

    with open(filepath, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            typename = (row.get("machinetypename") or "").strip()
            dataitem = (row.get("dataitemid") or "").strip()
            enabled = (row.get("is_violation_enabled") or "").strip().lower() == "true"

            if not typename or not dataitem:
                continue

            result[typename][dataitem] = {
                "data_type": (row.get("data_type") or "").strip(),
                "min_value": _safe_float(row.get("min_value", "")),
                "max_value": _safe_float(row.get("max_value", "")),
                "unit": (row.get("unit") or "").strip(),
                "success_key": (row.get("success_key") or "").strip().upper() or None,
                "true_label": (row.get("true_label") or "").strip() or None,
                "false_label": (row.get("false_label") or "").strip() or None,
                "description": (row.get("description") or "").strip() or None,
                "is_violation_enabled": enabled,
            }

    print(
        f"  [DB] machinetypedataitems: {len(result)} tip, toplam "
        f"{sum(len(v) for v in result.values())} sensör okundu."
    )
    return dict(result)


def load_machine_overrides(filepath: str) -> dict:
    """
    machinedataitems.csv'yi okur.
    Makineye özel override değerleri (min/max).

    Dönüş:
        {
          "TST001": {
            "total_cut_count": {"min_value": 0.0, "max_value": 100.0, ...}
          }
        }
    """
    result: dict = defaultdict(dict)

    with open(filepath, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            machinecode = (row.get("machinecode") or "").strip()
            dataitem = (row.get("dataitemid") or "").strip()
            enabled = (row.get("is_violation_enabled") or "").strip().lower() == "true"

            if not machinecode or not dataitem:
                continue

            result[machinecode][dataitem] = {
                "data_type": (row.get("data_type") or "").strip(),
                "min_value": _safe_float(row.get("min_value", "")),
                "max_value": _safe_float(row.get("max_value", "")),
                "unit": (row.get("unit") or "").strip(),
                "success_key": (row.get("success_key") or "").strip().upper() or None,
                "true_label": (row.get("true_label") or "").strip() or None,
                "false_label": (row.get("false_label") or "").strip() or None,
                "description": (row.get("description") or "").strip() or None,
                "is_violation_enabled": enabled,
            }

    if result:
        print(f"  [DB] machinedataitems: {len(result)} makine bazlı override okundu.")
        for mc, sensors in result.items():
            print(f"       {mc}: {list(sensors.keys())}")
    else:
        print(
            "  [DB] machinedataitems: Override yok — tüm makineler tip limitlerini kullanıyor."
        )

    return dict(result)


def build_machine_limits(
    type_limits: dict,
    machine_overrides: dict,
    machine_map: dict,  # {"HPR001": "Dikey Pres", "HPR002": "Yatay Pres", ...}
) -> dict:
    """
    Tip limitleri + makine override'larını birleştirip
    limits_config.yaml'ın `machine_limits` bölümünü üretir.

    Merge mantığı:
        1. Makine tipine göre type_limits'ten başla
        2. Makine bazlı override varsa o sensör için onu uygula
        3. is_violation_enabled=False olanları çıkar
        4. data_type=number olanları machine_limits'e yaz
        5. data_type=boolean olanları boolean_rules'a yaz (ayrı döndürülür)
    """
    machine_limits: dict = {}
    boolean_rules: dict = {}

    for machine_id, typename in machine_map.items():
        type_sensors = type_limits.get(typename, {})
        machine_overrides_for_id = machine_overrides.get(machine_id, {})

        numeric_limits = {}
        bool_rules_local = {}

        for dataitem, base_info in type_sensors.items():
            # Makine bazlı override varsa onu uygula
            info = dict(base_info)
            if dataitem in machine_overrides_for_id:
                override = machine_overrides_for_id[dataitem]
                # Override'dan gelen alanlar base_info'yu ezer
                for key in (
                    "min_value",
                    "max_value",
                    "unit",
                    "success_key",
                    "true_label",
                    "false_label",
                    "description",
                    "is_violation_enabled",
                ):
                    if override.get(key) is not None:
                        info[key] = override[key]

            if not info.get("is_violation_enabled"):
                continue  # Violation kapalı → atla

            data_type = info.get("data_type", "")

            if data_type == "number":
                entry = {}
                if info.get("min_value") is not None:
                    entry["min"] = info["min_value"]
                if info.get("max_value") is not None:
                    entry["max"] = info["max_value"]
                if info.get("unit"):
                    entry["unit"] = info["unit"]
                if entry:
                    numeric_limits[dataitem] = entry

            elif data_type == "boolean":
                sk = info.get("success_key", "TRUE")
                entry = {
                    "success_key": sk == "TRUE" if sk else True,
                    "alert_after_minutes": BOOLEAN_ALERT_MINUTES.get(dataitem, 60),
                }
                if info.get("true_label"):
                    entry["true_label"] = info["true_label"]
                if info.get("false_label"):
                    entry["false_label"] = info["false_label"]
                if info.get("description"):
                    entry["description"] = info["description"]
                bool_rules_local[dataitem] = entry

        if numeric_limits:
            machine_limits[machine_id] = numeric_limits

        # Boolean rules makine bazlı değil, tip bazlı olduğu için
        # boolean_rules'a bir kez eklenir (aynı sensör birden fazla makinede tekrar etmez)
        for sensor, rule in bool_rules_local.items():
            if sensor not in boolean_rules:
                boolean_rules[sensor] = rule

    return machine_limits, boolean_rules


def load_current_config(config_path: str) -> dict:
    """Mevcut limits_config.yaml'ı okur."""
    if not os.path.exists(config_path):
        print(f"  [WARN] {config_path} bulunamadı — sıfırdan oluşturulacak.")
        return {}
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def show_diff(current: dict, new_val: dict, path: str = "") -> list[str]:
    """
    İki dict arasındaki farkları insan okunabilir formatta listeler.
    Dönüş: Değişiklik açıklamaları listesi.
    """
    diffs = []

    all_keys = set(current.keys()) | set(new_val.keys())
    for key in sorted(all_keys):
        full_path = f"{path}.{key}" if path else str(key)
        if key not in current:
            diffs.append(f"  [EKLENECEK] {full_path}: {new_val[key]}")
        elif key not in new_val:
            diffs.append(f"  [KALDIRILACAK] {full_path}: {current[key]}")
        elif isinstance(current[key], dict) and isinstance(new_val[key], dict):
            diffs.extend(show_diff(current[key], new_val[key], full_path))
        elif current[key] != new_val[key]:
            diffs.append(
                f"  [DEĞİŞECEK] {full_path}: {current[key]!r} → {new_val[key]!r}"
            )

    return diffs


def write_config(config: dict, output_path: str) -> None:
    """
    Güncellenmiş config'i YAML dosyasına yazar.
    Orijinal dosyanın Kafka/pipeline bölümlerini korur.
    """
    # Başlık yorumu
    header = """# =============================================================================
# Codlean MES — Arıza Tahmin Pipeline Konfigürasyonu
# =============================================================================
# Bu dosya IK veritabanından (machinetypedataitems + machinedataitems)
# otomatik olarak üretilebilir:
#
#   python3 scripts/data_tools/sync_limits_from_db.py \\
#       --typefile /path/to/machinetypedataitems.csv \\
#       --machinefile /path/to/machinedataitems.csv \\
#       --dry-run
#
# Machine_limits ve boolean_rules bölümleri DB'den gelir.
# kafka, pipeline, ewma_alpha bölümleri bu script tarafından değiştirilmez.
# =============================================================================

"""
    # Atomik yazma: önce temp dosya, sonra rename
    import tempfile

    tmp_dir = os.path.dirname(os.path.abspath(output_path)) or "."
    with tempfile.NamedTemporaryFile(
        "w", dir=tmp_dir, delete=False, suffix=".tmp", encoding="utf-8"
    ) as f:
        f.write(header)
        yaml.dump(
            config,
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            indent=2,
        )
        tmp_path = f.name

    os.replace(tmp_path, output_path)
    print(f"\n  ✅ {output_path} başarıyla güncellendi.")


def main():
    parser = argparse.ArgumentParser(
        description="IK veritabanı CSV'sinden limits_config.yaml güncelle"
    )
    parser.add_argument(
        "--typefile",
        required=True,
        help="machinetypedataitems.csv dosya yolu",
    )
    parser.add_argument(
        "--machinefile",
        default=None,
        help="machinedataitems.csv dosya yolu (opsiyonel — yoksa tip limitleri kullanılır)",
    )
    parser.add_argument(
        "--output",
        default="config/limits_config.yaml",
        help="Güncellenecek YAML dosyası (varsayılan: config/limits_config.yaml)",
    )
    parser.add_argument(
        "--machines",
        default="HPR001,HPR002,HPR003,HPR004,HPR005,HPR006",
        help="Fiziksel HPR makine ID'leri virgülle ayrılmış (varsayılan: HPR001-HPR006)",
    )
    parser.add_argument(
        "--hpr-yatay",
        default="HPR002,HPR006",
        help="Yatay Pres olan HPR ID'leri (virgülle ayrılmış). (varsayılan: HPR002,HPR006)",
    )
    parser.add_argument(
        "--tst-machines",
        default="TST001,TST002,TST003,TST004",
        help="Testere makine ID'leri (varsayılan: TST001-TST004)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Değişiklikleri göster ama dosyaya yazma",
    )
    args = parser.parse_args()

    print()
    print("═" * 60)
    print("  IK VERİTABANI → limits_config.yaml SENKRONIZASYONU")
    print("═" * 60)
    print()

    # ── 1. CSV'leri oku ──────────────────────────────────────────────────────
    print("1. Veritabanı dosyaları okunuyor...")
    type_limits = load_type_limits(args.typefile)

    machine_overrides = {}
    if args.machinefile and os.path.exists(args.machinefile):
        machine_overrides = load_machine_overrides(args.machinefile)
    else:
        print(
            "  [INFO] machinefile verilmedi/bulunamadı — sadece tip limitleri kullanılacak."
        )

    # ── 2. Makine → tip eşleştirmesi ────────────────────────────────────────
    print("\n2. Makine → Tip eşleştirmesi...")
    machine_map = {}

    # HPR makineleri: tip'i belirlemek için HP sayısal sensörlerine bak
    # Yatay Pres sadece horizontal_press_pressure + horitzonal_infeed_speed'e sahip
    # Dikey Pres bunlara ek olarak oil_tank_temperature, main_pressure, lower_ejector_pressure var
    dikey_pres_sensors = type_limits.get("Dikey Pres", {})
    yatay_pres_sensors = type_limits.get("Yatay Pres", {})

    # Yatay Presleri ayır
    yatay_pres_ids = [m.strip() for m in args.hpr_yatay.split(",") if m.strip()]

    for mid in args.machines.split(","):
        mid = mid.strip()
        if not mid:
            continue
            
        if mid in yatay_pres_ids:
            machine_map[mid] = "Yatay Pres"
            print(f"    {mid} → Yatay Pres")
        else:
            machine_map[mid] = "Dikey Pres"
            print(f"    {mid} → Dikey Pres")

    for mid in args.tst_machines.split(","):
        mid = mid.strip()
        if not mid:
            continue
        machine_map[mid] = "Testere"
        print(f"    {mid} → Testere")

    # ── 3. Limit matrisini oluştur ───────────────────────────────────────────
    print("\n3. Limit matrisi oluşturuluyor...")
    new_machine_limits, new_boolean_rules = build_machine_limits(
        type_limits, machine_overrides, machine_map
    )

    print(f"    {len(new_machine_limits)} makine için sayısal limit üretildi.")
    print(f"    {len(new_boolean_rules)} boolean sensör kuralı üretildi.")

    # ── 4. Mevcut config'i oku ───────────────────────────────────────────────
    print(f"\n4. Mevcut config okunuyor: {args.output}")
    current_config = load_current_config(args.output)

    # ── 5. Diff göster ──────────────────────────────────────────────────────
    print("\n5. Değişiklik analizi...")
    current_ml = current_config.get("machine_limits", {})
    current_br = current_config.get("boolean_rules", {})

    ml_diffs = show_diff(current_ml, new_machine_limits, "machine_limits")
    br_diffs = show_diff(current_br, new_boolean_rules, "boolean_rules")

    all_diffs = ml_diffs + br_diffs

    if not all_diffs:
        print("  ✅ Değişiklik yok — limits_config.yaml zaten güncel!")
        return

    print(f"\n  Toplam {len(all_diffs)} değişiklik tespit edildi:")
    for d in all_diffs[:50]:  # Çok uzun olmasın
        print(d)
    if len(all_diffs) > 50:
        print(f"  ... ve {len(all_diffs) - 50} değişiklik daha.")

    if args.dry_run:
        print("\n  ℹ️  DRY-RUN modu — dosyaya yazılmadı.")
        print("  Gerçekten güncellemek için --dry-run parametresini kaldırın.")
        return

    # ── 6. Konfirmason ───────────────────────────────────────────────────────
    print("\n  Bu değişiklikleri uygulamak istiyor musunuz? [e/H]: ", end="")
    try:
        answer = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = ""

    if answer != "e":
        print("  İptal edildi.")
        return

    # ── 7. Config'i güncelle ─────────────────────────────────────────────────
    print("\n6. Config güncelleniyor...")
    # Kafka, pipeline, ewma_alpha bölümlerini koru — sadece limitler değişecek
    new_config = dict(current_config)
    new_config["machine_limits"] = new_machine_limits
    new_config["boolean_rules"] = new_boolean_rules

    write_config(new_config, args.output)

    print()
    print("═" * 60)
    print("  SENKRONIZASYON TAMAMLANDI")
    print("═" * 60)
    print(f"  Güncellenen: {args.output}")
    print(f"  Makine sayısı: {len(new_machine_limits)}")
    print(f"  Boolean kural sayısı: {len(new_boolean_rules)}")
    print()
    print("  ⚠️  Sistemi yeniden başlatmayı unutmayın:")
    print("  PYTHONPATH=. python3 src/app/hpr_monitor.py")
    print()


if __name__ == "__main__":
    main()
