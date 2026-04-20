#!/usr/bin/env python3
"""
fetch_past_week_kafka.py — Geçmiş 1 Haftalık Kafka Verisi Toplama Scripti
════════════════════════════════════════════════════════════════════════
Kafka'dan "earliest" ofsetleri veya 7 gün önceki başlangıç offsetini alıp
mesajları okur ve ML modeli eğitmek için `window_collector` ve `context_collector`
yapılarına aktarır.

ÖNEMLİ: Bu araç zamanı (time) geçmişteki Kafka timestamp'lerine mocklar.
Böylece trend hesaplamaları (slope, etc.) geçmişteyken de düzgün çalışır.
"""

import sys
import os
import json
import time
from datetime import datetime, timezone, timedelta
from confluent_kafka import Consumer, TopicPartition

# Proje dizinini yola ekle
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.kafka_env import BOOTSTRAP, TOPIC, make_config
import scripts.data_tools.window_collector as wc
import scripts.data_tools.context_collector as cc

KAFKA_CONFIG = make_config(
    group_id=f"historical-gather-{int(time.time())}",
    auto_offset_reset="earliest",
    session_timeout_ms=10000,
    **{"fetch.message.max.bytes": 10485760} # Lige payloads
)

def get_hpr_readings(msg_value):
    readings_by_machine = {}
    try:
        data = json.loads(msg_value)
        for stream in data.get("streams", []):
            for comp in stream.get("componentStream", []):
                mid = comp.get("componentId", "")
                if not mid.startswith("HPR"):
                    continue
                readings = {}
                for sample in comp.get("samples", []):
                    k = sample.get("dataItemId", "")
                    v_str = str(sample.get("result", "")).replace(',', '.')
                    if "UNAVAILABLE" in v_str.upper() or v_str == "":
                        continue
                    try:
                        readings[k] = float(v_str)
                    except ValueError:
                        pass
                if readings:
                    readings_by_machine[mid] = readings
    except Exception:
        pass
    return readings_by_machine

def run():
    print("="*70)
    print("🚀 GEÇMİŞ 7 GÜNÜN VERİLERİ (KAFKA) TOPLANIYOR")
    print("="*70)
    
    # Eskiyse silip sıfırdan başlıyoruz
    if os.path.exists("live_windows.json"):
        os.remove("live_windows.json")
        print("🧹 Eski live_windows.json temizlendi.")
    if os.path.exists("rich_context_windows.json"):
        os.remove("rich_context_windows.json")
        print("🧹 Eski rich_context_windows.json temizlendi.")

    consumer = Consumer(KAFKA_CONFIG)
    
    # Hangi topic ve partitionlar?
    metadata = consumer.list_topics(TOPIC, timeout=10.0)
    if not metadata or TOPIC not in metadata.topics:
        print(f"❌ Kafka Topic bulunamadı: {TOPIC}")
        return
        
    partitions = metadata.topics[TOPIC].partitions
    
    # 7 gün öncesi
    start_dt = datetime.now(timezone.utc) - timedelta(days=7)
    start_time_ms = int(start_dt.timestamp() * 1000)
    
    print(f"📡 {TOPIC} — Toplam {len(partitions)} partition, Başlangıç: {start_dt.strftime('%d %b %H:%M')}")
    
    tpl = [TopicPartition(TOPIC, p, start_time_ms) for p in partitions]
    target_offsets = consumer.offsets_for_times(tpl)
    
    # Fallback to earliest if data is purged or offsets_for_times is unavailable
    for tp in target_offsets:
        if tp.offset == -1:
             low, high = consumer.get_watermark_offsets(tp)
             tp.offset = low
             
    consumer.assign(target_offsets)
    
    print("\n🔄 Çekim başlatılıyor... (Lütfen iptal etmeyin)")
    
    msg_count = 0
    start_fetch = time.time()
    last_msg_time = time.time()
    
    end_dt = datetime.now(timezone.utc) - timedelta(minutes=5)
    
    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                # 15 saniyedir yeni mesaj yoksa partition sonudur
                if time.time() - last_msg_time > 15 and msg_count > 0:
                     print("\n✅ Veri akışı sona erdi (15 saniye boyunca yeni mesaj yok).")
                     break
                if time.time() - start_fetch > 15 and msg_count == 0:
                     print("\n❌ Başlangıçtan beri hiç veri gelmedi.")
                     break
                continue
            
            if msg.error():
                continue
            
            last_msg_time = time.time()
            msg_count += 1
            if msg_count % 10000 == 0:
                print(f"📊 İşlenen mesaj: {msg_count:,}...", end="\r")
            
            timestamp_ms = msg.timestamp()[1]
            if not timestamp_ms:
                continue
                
            msg_dt = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
            
            # --- ZAMAN MAKİNESİ (MOCK) ---
            # Collectorler içindeki zaman fonksiyonlarını msg_dt ile ez (overwrite)
            wc._now_iso = lambda dt=msg_dt: dt.isoformat()
            cc._now = lambda dt=msg_dt: dt
            cc._now_iso = lambda dt=msg_dt: dt.isoformat()
            
            readings_map = get_hpr_readings(msg.value().decode("utf-8"))
            for mid, reads in readings_map.items():
                wc.record(mid, reads)
                cc.record(mid, reads, None) # Startup is None
                
            # Güncel zamana ulaştıysak döngüyü kır
            if msg_dt >= end_dt:
                print(f"\n✅ Güncel zamana ulaşıldı.")
                break
                
    except KeyboardInterrupt:
        print("\n⏳ Kullanıcı tarafından durduruldu.")
    finally:
        print("\n💾 Bellekteki veriler json dosyalarına yazılıyor...")
        wc.force_save()
        cc.force_save()
        consumer.close()
        
    print(f"✅ İşlem Tamamlandı. Toplam çekilen mesaj: {msg_count:,}")
    print(wc.summary())
    print(cc.summary())

if __name__ == '__main__':
    run()
