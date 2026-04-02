#!/usr/bin/env python3
"""
Local Backfill Analysis — Diskteki Günlük Verilerden Hata Analizi

Kullanım:
    python3 scripts/data_tools/local_backfill_analysis.py --days 3 --output data/backfill_faults_3days.json
"""

import argparse
import sys
import json
import time
from pathlib import Path

# Add project root to path so we can import modules if needed, though fault_pattern_miner is in same dir
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from scripts.data_tools.fault_pattern_miner import FaultPatternMiner

def main():
    parser = argparse.ArgumentParser(description="Local JSONL Backfill Analysis")
    parser.add_argument('--days', type=int, default=3, help="Kaç gün geriye gidilecek (Sondaki klasörlerden)")
    parser.add_argument('--max-messages', type=int, default=None, help="Maksimum mesaj sayısı (Test için)")
    parser.add_argument('--output', type=str, default='data/backfill_faults.json', help="Çıktı dosyası yolu")
    args = parser.parse_args()

    miner = FaultPatternMiner()
    
    # Hedef klasör "data/daily"
    # Proje kökü "BASE_DIR" bulalım
    base_dir = Path(__file__).resolve().parent.parent.parent / "data" / "daily"
    if not base_dir.exists():
        print(f"❌ {base_dir} klasörü bulunamadı!")
        return

    # Tüm alt klasörleri tarihe göre sırala (Örn: 2026-03-29, 2026-03-30...)
    folders = sorted([d for d in base_dir.iterdir() if d.is_dir() and len(d.name) == 10])
    
    if not folders:
        print("❌ data/daily içerisinde hiç klasör yok.")
        return
        
    target_folders = folders[-args.days:]
    print("=" * 70)
    print("🚀 LOKAL BACKFILL ANALİZİ BAŞLIYOR")
    print(f"Hedef: Son {len(target_folders)} gün okunacak.")
    for f in target_folders:
        print(f"  - {f.name}")
    print("=" * 70)

    total_read = 0
    start_time = time.time()

    for folder in target_folders:
        file_path = folder / "raw_messages.jsonl"
        if not file_path.exists():
            print(f"⚠️ {file_path} bulunamadı, atlanıyor...")
            continue
            
        print(f"⏳ Okunuyor: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): 
                    continue
                try:
                    data = json.loads(line)
                    miner.process_message(data)
                except Exception as e:
                    pass
                    
                total_read += 1
                if total_read % 100000 == 0:
                    print(f"  ... 📊 İlerleme: {total_read} mesaj işlendi")
                    
                if args.max_messages and total_read >= args.max_messages:
                    print("🛑 Maksimum mesaj sınırına ulaşıldı.")
                    break
                    
        if args.max_messages and total_read >= args.max_messages:
            break

    miner.save_results(args.output)
    
    print("\n" + "=" * 70)
    print("✅ ANALİZ RAPORU")
    print("=" * 70)
    print(f"⏱️ Geçen Süre: {time.time()-start_time:.1f} saniye")
    print(f"📊 Toplam Mesaj: {total_read}")
    print(f"🚨 Kurallara Takılan Fault Süresi: {len(miner.fault_windows)}")
    
    from collections import Counter
    machine_counts = Counter([fw['machine_id'] for fw in miner.fault_windows])
    print("\n🏭 Makine Başına Fault Dağılımı:")
    for m, c in machine_counts.most_common():
        print(f"  - {m}: {c} uyarı")

if __name__ == '__main__':
    main()
