from confluent_kafka import Consumer, TopicPartition
import json
import sys
import time

def check_kafka_history():
    c = Consumer({
        'bootstrap.servers': '10.71.120.10:7001',
        'group.id': 'check-history-group-fast-2',
        'enable.auto.commit': False,
        'fetch.min.bytes': 1000000,
        'receive.message.max.bytes': 100000000
    })

    topic = 'mqtt-topic-v2'
    
    try:
        metadata = c.list_topics(topic, timeout=10)
        partitions = metadata.topics[topic].partitions
    except Exception as e:
        print(f"Failed to get metadata: {e}")
        return

    last_hpr_time = None
    last_hpr_machine = None
    total_scanned = 0
    found_hpr = 0

    # Assign and seek to end - N
    n_messages = 50000  # Scan last 50k messages per partition
    tps = []
    
    for p in partitions:
        try:
            low, high = c.get_watermark_offsets(TopicPartition(topic, p), timeout=5)
            # If there are fewer messages than n_messages, start from low
            start_offset = max(low, high - n_messages)
            if start_offset < high:
                tps.append(TopicPartition(topic, p, start_offset))
                print(f"Partition {p}: Scanning from {start_offset} to {high} (Total: {high - start_offset})")
        except Exception as e:
            print(f"Error getting offsets for partition {p}: {e}")

    if not tps:
        return

    c.assign(tps)

    print(f"Dinleniyor... (Timeout 3 saniye)")
    start_time = time.time()
    
    empty_polls = 0
    while True:
        msg = c.poll(1.0)
        if msg is None:
            empty_polls += 1
            if empty_polls > 3:
                break
            continue
            
        empty_polls = 0
        if msg.error():
            continue
            
        total_scanned += 1
        
        if total_scanned % 10000 == 0:
            sys.stdout.write(f"\rScanned {total_scanned} messages... Found HPR: {found_hpr}")
            sys.stdout.flush()
            
        val = msg.value().decode('utf-8', errors='ignore')
        
        if "HPR" in val:
            found_hpr += 1
            try:
                data = json.loads(val)
                ts = data.get("header", {}).get("creationTime")
                
                # find which machine it is
                streams = data.get("streams", [])
                machine_id = "Unknown"
                for s in streams:
                    for comp in s.get("componentStream", []):
                        cid = comp.get("componentId", "")
                        if "HPR" in cid:
                            machine_id = cid
                            break
                            
                if ts:
                    if not last_hpr_time or ts > last_hpr_time:
                        last_hpr_time = ts
                        last_hpr_machine = machine_id
            except:
                pass

    print(f"\nCompleted in {time.time() - start_time:.1f} seconds.")
    print("\n" + "="*50)
    print("📝 ANALİZ SONUCU")
    print("="*50)
    print(f"Taranan Toplam Mesaj Sayısı : {total_scanned}")
    print(f"Bulunan HPR Mesaj Sayısı    : {found_hpr}")
    
    if last_hpr_time:
        print(f"🛑 SON HPR VERİSİ GÖRÜLME ZAMANI : {last_hpr_time} UTC")
        print(f"Endüstriyel Makine              : {last_hpr_machine}")
    else:
        print("⚠️ Taranan aralıkta HPR makinelerinden HİÇ veri bulunamadı. Makine çok uzun süredir kapalı olabilir veya tamamen başka bir topic kullanıyor olabilir.")

if __name__ == "__main__":
    check_kafka_history()
