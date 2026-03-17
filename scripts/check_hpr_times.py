import time
from confluent_kafka import Consumer, TopicPartition
import json
from datetime import datetime, timezone, timedelta

def check_hpr_at_time(c, topic, target_time_ms):
    try:
        metadata = c.list_topics(topic, timeout=10)
        partitions = metadata.topics[topic].partitions
    except Exception as e:
        print(f"Error getting partitions: {e}")
        return False
        
    tps = [TopicPartition(topic, p, target_time_ms) for p in partitions]
    
    try:
        offsets = c.offsets_for_times(tps, timeout=10)
    except Exception as e:
        print(f"Error getting offsets for times: {e}")
        return False
        
    valid_tps = [tp for tp in offsets if tp.offset > 0]
    if not valid_tps:
        return False
        
    c.assign(valid_tps)
    
    found_hpr = False
    start_time = time.time()
    messages_checked = 0
    try:
        while True:
            msg = c.poll(0.5)
            if msg is None:
                continue
            if msg.error():
                continue
            messages_checked += 1
            if "HPR" in msg.value().decode('utf-8', errors='ignore'):
                found_hpr = True
                break
            if messages_checked >= 1000 or time.time() - start_time > 5:
                # Check up to 1000 messages or 5 seconds max
                break
    except Exception as e:
        print(f"Error polling: {e}")
        
    return found_hpr

if __name__ == "__main__":
    c = Consumer({
        'bootstrap.servers': '10.71.120.10:7001',
        'group.id': 'check-history-time-based-v1',
        'enable.auto.commit': False
    })

    topic = 'mqtt-topic-v2'
    now_ms = int(time.time() * 1000)

    print("Zaman bazlı HPR verisi kontrol ediliyor...\n")
    # 0, 10 dk, 30 dk, 1 saat, 3 saat, 6 saat, 12 saat, 24 saat, 48 saat
    check_points_minutes = [0, 10, 30, 60, 180, 360, 720, 1440, 2880]
    
    for mins_ago in check_points_minutes:
        target_ms = now_ms - (mins_ago * 60 * 1000)
        dt_str = datetime.fromtimestamp(target_ms/1000).strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{dt_str}] ({mins_ago} dakika önce) kontrol ediliyor...")
        
        has_hpr = check_hpr_at_time(c, topic, target_ms)
        status = "✅ AKTİF (Veri Var)" if has_hpr else "❌ YOK (Veri Bulunamadı)"
        print(f"  -> {status}\n")
