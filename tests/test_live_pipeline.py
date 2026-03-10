"""
test_live_pipeline.py — Live Pipeline Kısa Test
═══════════════════════════════════════════════
HPR monitor'u 30 saniye çalıştırıp Kafka'dan veri alıyoruz.
"""

import sys
import time
from datetime import datetime
from confluent_kafka import Consumer, KafkaException
import yaml

print("\n" + "╔" + "═"*53 + "╗")
print("║" + " "*15 + "LIVE PIPELINE TEST" + " "*17 + "║")
print("╚" + "═"*53 + "╝")

# Config yükle
with open("limits_config.yaml") as f:
    CONFIG = yaml.safe_load(f)

KAFKA_CONFIG = CONFIG.get("kafka", {})

print(f"\n📡 Kafka Ayarları:")
print(f"   Bootstrap: {KAFKA_CONFIG.get('bootstrap_servers')}")
print(f"   Topic: {KAFKA_CONFIG.get('topic')}")
print(f"   Group ID: {KAFKA_CONFIG.get('group_id')}")

# Consumer config
consumer_config = {
    'bootstrap.servers': KAFKA_CONFIG['bootstrap_servers'],
    'group.id': KAFKA_CONFIG['group_id'],
    'auto.offset.reset': 'latest',  # En yeni mesajlar
    'enable.auto.commit': True,
    'session.timeout.ms': 6000,
}

print(f"\n⏳ 30 saniye mesaj dinleniyor...\n")

try:
    consumer = Consumer(consumer_config)
    consumer.subscribe([KAFKA_CONFIG['topic']])
    
    messages_received = []
    start_time = time.time()
    timeout_seconds = 30
    
    print(f"   Başlangıç: {datetime.now().strftime('%H:%M:%S')}")
    print(f"   Bekleme süresi: {timeout_seconds} saniye\n")
    
    while time.time() - start_time < timeout_seconds:
        msg = consumer.poll(1.0)  # 1 saniye timeout
        
        if msg is None:
            continue
        
        if msg.error():
            print(f"   ⚠️  Kafka error: {msg.error()}")
            continue
        
        try:
            value = msg.value().decode('utf-8')
            timestamp = datetime.fromtimestamp(msg.timestamp()[1] / 1000)
            
            messages_received.append({
                'timestamp': timestamp,
                'value': value[:100]  # İlk 100 karakter
            })
            
            if len(messages_received) <= 5 or len(messages_received) % 10 == 0:
                print(f"   ✅ Mesaj #{len(messages_received)} @ {timestamp.strftime('%H:%M:%S')}")
        
        except Exception as e:
            print(f"   ⚠️  Decode error: {e}")
    
    # Özet
    elapsed = time.time() - start_time
    
    print(f"\n\n📊 TEST SONUÇLARI:")
    print(f"   Süre: {elapsed:.1f} saniye")
    print(f"   Alınan mesaj: {len(messages_received):,}")
    print(f"   Mesaj/sn: {len(messages_received)/elapsed:.1f}")
    
    if messages_received:
        print(f"\n   İlk mesaj: {messages_received[0]['timestamp'].strftime('%H:%M:%S')}")
        print(f"   Son mesaj: {messages_received[-1]['timestamp'].strftime('%H:%M:%S')}")
        
        print(f"\n✅ KAFKA ÇALIŞIYOR! MESAJ AKIŞI VAR!")
        print(f"   → hpr_monitor.py çalıştırılabilir")
        print(f"   → Alert üretimi test edilebilir")
    else:
        print(f"\n⚠️  MESAJ GELMEDİ")
        print(f"   → Şu an üretim yok olabilir")
        print(f"   → VEYA farklı topic'ten geliyor olabilir")
        print(f"   → Yine de hpr_monitor.py deneyebiliriz")
    
    consumer.close()
    
except KeyboardInterrupt:
    print("\n\n⚠️  Kullanıcı tarafından durduruldu")
    consumer.close()
except Exception as e:
    print(f"\n❌ HATA: {e}")
    print(f"\n💡 Olası çözümler:")
    print(f"   1. VPN bağlantısını kontrol et")
    print(f"   2. Kafka broker çalışan mı?")
    print(f"   3. Topic adı doğru mu?")
    sys.exit(1)

print("\n" + "="*55 + "\n")
