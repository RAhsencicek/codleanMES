"""
test_kafka_connection.py — Kafka Bağlantı Testi
═══════════════════════════════════════════════
VPN bağlantısını ve Kafka erişimini test eder.
"""

from confluent_kafka import Consumer, KafkaError
import yaml

# Config yükle
with open("limits_config.yaml") as f:
    CONFIG = yaml.safe_load(f)

KAFKA_CFG = CONFIG["kafka"]

print("\n" + "="*55)
print("KAFKA BAĞLANTI TESTİ")
print("="*55)

print(f"\n📡 Kafka Ayarları:")
print(f"   Bootstrap Servers: {KAFKA_CFG['bootstrap_servers']}")
print(f"   Topic: {KAFKA_CFG['topic']}")
print(f"   Group ID: {KAFKA_CFG['group_id']}")

# Consumer config
consumer_config = {
    'bootstrap.servers': KAFKA_CFG['bootstrap_servers'],
    'group.id': KAFKA_CFG['group_id'],
    'session.timeout.ms': KAFKA_CFG.get('session_timeout_ms', 10000),
    'fetch.wait.max.ms': KAFKA_CFG.get('fetch_wait_max_ms', 500),
    'auto.offset.reset': 'latest'
}

print(f"\n🔌 Bağlanıyor...")

try:
    consumer = Consumer(consumer_config)
    print("✅ Kafka'ya bağlanıldı!")
    
    # Topic subscribe et
    print(f"\n📋 Topic '{KAFKA_CFG['topic']}' subscribe ediliyor...")
    consumer.subscribe([KAFKA_CFG['topic']])
    
    print("✅ Topic subscribe edildi!")
    
    # 5 saniye mesaj dinle
    print(f"\n📨 5 saniye mesaj dinleniyor...\n")
    
    msg_count = 0
    import time
    start_time = time.time()
    
    while time.time() - start_time < 5:
        msg = consumer.poll(1.0)
        
        if msg is None:
            continue
        
        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                continue
            else:
                print(f"❌ Kafka error: {msg.error()}")
                break
        
        msg_count += 1
        
        # İlk 3 mesajı göster
        if msg_count <= 3:
            try:
                import json
                value = json.loads(msg.value().decode('utf-8'))
                machine_id = value.get('machine_id', 'N/A')
                print(f"   Mesaj {msg_count}:")
                print(f"      Machine: {machine_id}")
                print(f"      Timestamp: {value.get('timestamp', 'N/A')}")
                print(f"      Sensor count: {len(value.get('items', []))}")
            except Exception as e:
                print(f"      Message parse error: {e}")
    
    print(f"\n📊 Test Sonucu:")
    print(f"   ✅ 5 saniyede {msg_count} mesaj alındı")
    print(f"   ✅ Kafka bağlantisi ÇALIŞIYOR!")
    
    consumer.close()
    print("\n✅ Consumer kapatıldı.")
    
except Exception as e:
    print(f"\n❌ HATA: {e}")
    print("\n💡 OLASI SORUNLAR:")
    print("   1. VPN bağlı değil → VPN'i aç")
    print("   2. Kafka broker erişilebilir değil → Network kontrol et")
    print("   3. Topic yok → Topic adını kontrol et")
    print("   4. Firewall engelleme → IT ile görüş")

print("\n" + "="*55)
print("TEST TAMAMLANDI")
print("="*55 + "\n")
