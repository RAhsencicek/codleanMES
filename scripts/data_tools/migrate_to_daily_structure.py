"""
migrate_to_daily_structure.py — Geçmiş Verileri Günlük Yapıya Taşı
═══════════════════════════════════════════════════════════════════════
Mevcut veri dosyalarını data/daily/YYYY-MM-DD/ yapısına taşır.

Kaynak dosyalar:
  - data/violation_log.json → daily/*/violations.json
  - data/rich_context_historical_march_12_19.json → daily/*/contexts.json
  - data/hpr_full_sensor_march_12_19.json → daily/*/raw_messages.jsonl

Kullanım:
  python3 scripts/data_tools/migrate_to_daily_structure.py
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

# Import daily manager
from daily_data_manager import (
    save_raw_message,
    save_violation,
    save_context,
    _get_daily_dir,
)


def parse_timestamp(ts_str: str) -> datetime:
    """ISO timestamp'i parse et."""
    try:
        return datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
    except:
        return datetime.now(timezone.utc)


def migrate_violation_log():
    """violation_log.json'ı günlük yapıya taşı."""
    print("📦 violation_log.json taşınıyor...")
    
    log_path = Path("data/violation_log.json")
    if not log_path.exists():
        print("   ⚠️ Dosya bulunamadı")
        return
    
    with open(log_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Fault windows'dan violation'ları çıkar
    fault_windows = data.get("fault_windows", [])
    migrated = 0
    
    for window in fault_windows:
        mid = window.get("machine_id", "UNKNOWN")
        timestamp = window.get("timestamp", "")
        
        if not timestamp:
            continue
        
        dt = parse_timestamp(timestamp)
        date_str = dt.strftime("%Y-%m-%d")
        
        # Her sensör için violation kaydet
        for sensor_data in window.get("sensors", []):
            sensor = sensor_data.get("sensor", "unknown")
            max_value = sensor_data.get("max_value", 0)
            limit = sensor_data.get("limit", 0)
            
            save_violation(
                machine_id=mid,
                sensor=sensor,
                value=max_value,
                limit=limit,
                timestamp=timestamp,
                date_str=date_str
            )
            migrated += 1
    
    print(f"   ✅ {migrated} violation taşındı")


def migrate_rich_context():
    """rich_context_historical.json'ı günlük yapıya taşı."""
    print("📦 rich_context_historical_march_12_19.json taşınıyor...")
    
    ctx_path = Path("data/rich_context_historical_march_12_19.json")
    if not ctx_path.exists():
        print("   ⚠️ Dosya bulunamadı")
        return
    
    with open(ctx_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    contexts = data.get("contexts", [])
    migrated = 0
    
    for ctx in contexts:
        mid = ctx.get("machine_id", "UNKNOWN")
        timestamp = ctx.get("timestamp", "")
        
        if not timestamp:
            continue
        
        dt = parse_timestamp(timestamp)
        date_str = dt.strftime("%Y-%m-%d")
        
        save_context(mid, ctx, date_str=date_str)
        migrated += 1
    
    print(f"   ✅ {migrated} context taşındı")


def migrate_full_sensor_data():
    """hpr_full_sensor_march_12_19.json'ı günlük yapıya taşı."""
    print("📦 hpr_full_sensor_march_12_19.json taşınıyor...")
    
    sensor_path = Path("data/hpr_full_sensor_march_12_19.json")
    if not sensor_path.exists():
        print("   ⚠️ Dosya bulunamadı")
        return
    
    with open(sensor_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    messages = data.get("messages", [])
    migrated = 0
    
    for msg in messages:
        mid = msg.get("machine_id", "UNKNOWN")
        timestamp = msg.get("timestamp", "")
        
        if not timestamp:
            continue
        
        dt = parse_timestamp(timestamp)
        date_str = dt.strftime("%Y-%m-%d")
        
        save_raw_message({
            "machine_id": mid,
            "timestamp": timestamp,
            "numeric": msg.get("numeric", {}),
            "boolean": msg.get("boolean", {}),
            "is_stale": msg.get("is_stale", False),
            "is_startup": msg.get("is_startup", False)
        }, date_str=date_str)
        
        migrated += 1
        
        if migrated % 10000 == 0:
            print(f"   ... {migrated} mesaj taşındı")
    
    print(f"   ✅ {migrated} mesaj taşındı")


def generate_migration_report():
    """Taşıma sonrası rapor oluştur."""
    print("\n📊 Migration Raporu:")
    print("=" * 50)
    
    base_dir = Path("data/daily")
    if not base_dir.exists():
        print("❌ Daily dizini bulunamadı")
        return
    
    total_days = 0
    total_messages = 0
    total_violations = 0
    total_contexts = 0
    
    for day_dir in sorted(base_dir.iterdir()):
        if not day_dir.is_dir():
            continue
        
        try:
            # Tarih formatını doğrula
            datetime.strptime(day_dir.name, "%Y-%m-%d")
            total_days += 1
            
            # Dosya sayıları
            raw_msgs = day_dir / "raw_messages.jsonl"
            violations = day_dir / "violations.json"
            contexts = day_dir / "contexts.json"
            
            if raw_msgs.exists():
                with open(raw_msgs, 'r') as f:
                    total_messages += sum(1 for _ in f)
            
            if violations.exists():
                with open(violations, 'r') as f:
                    total_violations += len(json.load(f))
            
            if contexts.exists():
                with open(contexts, 'r') as f:
                    ctx_data = json.load(f)
                    for mid, mdata in ctx_data.get("machines", {}).items():
                        total_contexts += len(mdata.get("context_windows", []))
            
        except ValueError:
            continue
    
    print(f"📁 Toplam gün: {total_days}")
    print(f"💬 Toplam mesaj: {total_messages:,}")
    print(f"⚠️  Toplam violation: {total_violations:,}")
    print(f"🧠 Toplam context: {total_contexts:,}")
    print("=" * 50)


def main():
    """Ana migration fonksiyonu."""
    print("🚀 Geçiş Veri Migration'ı Başlıyor")
    print("=" * 50)
    
    # Her bir kaynağı taşı
    migrate_violation_log()
    migrate_rich_context()
    migrate_full_sensor_data()
    
    # Rapor oluştur
    generate_migration_report()
    
    print("\n✅ Migration tamamlandı!")
    print("\n📌 Not: Orijinal dosyalar korundu.")
    print("   Yeni veriler data/daily/ altında oluşturuldu.")


if __name__ == "__main__":
    main()
