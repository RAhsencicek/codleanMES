#!/usr/bin/env python3
"""
gecmis_veri_cek.py — Kafka'dan Geçmiş Veri Çekme
═══════════════════════════════════════════════════
Tarih aralığı: 6-16 Mart 2026 (eğer varsa)
Amaç: violation_log.json formatında kaydetme
"""

import json
import os
from datetime import datetime, timezone
from confluent_kafka import Consumer, TopicPartition

# Kafka ayarları
KAFKA_CONFIG = {
    "bootstrap.servers": "10.71.120.10:7001",
    "group.id": "historical-data-pull-" + datetime.now().strftime("%H%M%S"),
    "auto.offset.reset": "earliest",  # ⭐ BURASI ÖNEMLİ: En baştan başla
    "enable.auto.commit": False,
    "session.timeout.ms": 30000,
}

TOPIC = "mqtt-topic-v2"
OUTPUT_FILE = "data/historical_violations_mart_2026.json"

def main():
    print("=" * 60)
    print("  KAFKA'DAN GEÇMİŞ VERİ ÇEKME")
    print("=" * 60)
    print()
    
    consumer = Consumer(KAFKA_CONFIG)
    
    # Topic metadata al
    metadata = consumer.list_topics(TOPIC)
    partitions = metadata.topics[TOPIC].partitions
    
    print(f"📡 Topic: {TOPIC}")
    print(f"📊 Partition sayısı: {len(partitions)}")
    print()
    
    # Her partition için offset aralığını kontrol et
    total_messages = 0
    for partition_id in partitions.keys():
        tp = TopicPartition(TOPIC, partition_id)
        low, high = consumer.get_watermark_offsets(tp)
        count = high - low
        total_messages += count
        print(f"  Partition {partition_id}: {count:,} mesaj (offset {low} - {high})")
    
    print()
    print(f"📈 Toplam mesaj: {total_messages:,}")
    print()
    
    # Şimdi mesajları oku - 6-16 Mart arasını bul
    print("🔍 6-16 Mart 2026 arası mesajlar aranıyor...")
    print("   (Bu işlem biraz zaman alabilir)")
    print()
    
    consumer.subscribe([TOPIC])
    
    # HPR makineleri için violation kayıtları
    violations = {}
    message_count = 0
    found_in_range = 0
    
    # Hedef tarih aralığı
    start_date = datetime(2026, 3, 6, tzinfo=timezone.utc)
    end_date = datetime(2026, 3, 17, tzinfo=timezone.utc)
    
    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                # 5 saniye yeni mesaj yoksa bitir
                continue
            
            message_count += 1
            
            # Her 1000 mesajda bir rapor
            if message_count % 1000 == 0:
                print(f"   İşlenen: {message_count:,} | Bulunan: {found_in_range}", end="\r")
            
            # Timestamp kontrolü
            timestamp_ms = msg.timestamp()[1]
            if timestamp_ms:
                msg_time = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
                
                # 6-16 Mart arası mı?
                if start_date <= msg_time < end_date:
                    found_in_range += 1
                    
                    # Mesaj içeriğini parse et
                    try:
                        value = json.loads(msg.value().decode('utf-8'))
                        
                        # HPR makinelerini bul
                        for stream in value.get("streams", []):
                            for comp in stream.get("componentStream", []):
                                machine_id = comp.get("componentId", "")
                                
                                if machine_id.startswith("HPR"):
                                    # Sensör değerlerini kontrol et
                                    for sample in comp.get("samples", []):
                                        sensor_id = sample.get("dataItemId", "")
                                        val = sample.get("result", "")
                                        
                                        # Violation kontrolü (örnek)
                                        # Gerçek limit kontrolü eklenebilir
                                        if machine_id not in violations:
                                            violations[machine_id] = {}
                                        if sensor_id not in violations[machine_id]:
                                            violations[machine_id][sensor_id] = {"violations": []}
                                        
                                        violations[machine_id][sensor_id]["violations"].append({
                                            "ts": msg_time.isoformat(),
                                            "value": val,
                                            "partition": msg.partition(),
                                            "offset": msg.offset()
                                        })
                    except Exception as e:
                        pass
                
                # 17 Mart'tan sonraysa bitir
                elif msg_time >= end_date:
                    print(f"\n   17 Mart+ tarihli mesaj bulundu, arama bitiriliyor...")
                    break
            
            # Maksimum 100k mesaj oku (güvenlik için)
            if message_count >= 100000:
                print(f"\n   Maksimum mesaj limitine ulaşıldı")
                break
                
    except KeyboardInterrupt:
        print("\n   Kullanıcı tarafından durduruldu")
    
    finally:
        consumer.close()
    
    print()
    print("=" * 60)
    print("  SONUÇ")
    print("=" * 60)
    print(f"📊 Toplam işlenen mesaj: {message_count:,}")
    print(f"📅 6-16 Mart arası mesaj: {found_in_range}")
    print(f"🏭 Bulunan HPR makine sayısı: {len(violations)}")
    
    if violations:
        for machine_id, sensors in violations.items():
            total_v = sum(len(s.get("violations", [])) for s in sensors.values())
            print(f"   - {machine_id}: {total_v} kayıt")
        
        # Kaydet
        os.makedirs("data", exist_ok=True)
        output = {
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "date_range": "2026-03-06 to 2026-03-16",
                "source": "Kafka historical pull"
            },
            "violations": violations
        }
        
        with open(OUTPUT_FILE, "w") as f:
            json.dump(output, f, indent=2)
        
        print()
        print(f"✅ Kaydedildi: {OUTPUT_FILE}")
    else:
        print()
        print("❌ 6-16 Mart arası HPR verisi bulunamadı")
    
    print("=" * 60)

if __name__ == "__main__":
    main()
