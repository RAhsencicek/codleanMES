"""
Quick Kafka Connection Check
"""
import socket
from confluent_kafka import Consumer, KafkaException

print("\n" + "="*60)
print("KAFKA BAĞLANTI TESTİ")
print("="*60)

# Konfigürasyon
broker = "10.71.120.10:7001"
topic = "mqtt-topic-v2"

print(f"\n📍 Broker: {broker}")
print(f"📝 Topic: {topic}")

# 1. Port kontrolü
print("\n" + "-"*60)
print("1️⃣  PORT KONTROLÜ (7001)")
print("-"*60)

try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    result = sock.connect_ex(("10.71.120.10", 7001))
    
    if result == 0:
        print(f"✅ Port 7001 AÇIK")
    else:
        print(f"❌ Port 7001 KAPALI (Error: {result})")
        print("   → VPN bağlantısını kontrol et!")
    
    sock.close()
except Exception as e:
    print(f"❌ Hata: {e}")

# 2. PING testi
print("\n" + "-"*60)
print("2️⃣  PING TESTİ")
print("-"*60)

import subprocess
try:
    result = subprocess.run(['ping', '-c', '2', '-W', '2', '10.71.120.10'], 
                          capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        print(f"✅ PING başarılı")
    else:
        print(f"❌ PING başarısız - Broker unreachable")
except Exception as e:
    print(f"❌ Ping hatası: {e}")

# 3. Kafka Consumer
print("\n" + "-"*60)
print("3️⃣  KAFKA CONSUMER TESTİ")
print("-"*60)

KAFKA_CONFIG = {
    'bootstrap.servers': '10.71.120.10:7001',
    'group.id': 'ariza-tahmin-pipeline',
    'client.id': 'quick-test',
    'socket.timeout.ms': 5000,
    'session.timeout.ms': 6000,
}

try:
    print("Consumer oluşturuluyor...")
    consumer = Consumer(KAFKA_CONFIG)
    print("✅ Consumer OK")
    
    # Metadata al
    print("\nMetadata alınacak (timeout: 5 sn)...")
    metadata = consumer.list_topics(timeout=5)
    print("✅ Metadata alındı!")
    
    topics = list(metadata.topics.keys())
    print(f"\n📋 Toplam topic sayısı: {len(topics)}")
    
    if topic in topics:
        print(f"✅ '{topic}' topic bulundu!")
    else:
        print(f"❌ '{topic}' topic YOK!")
        print("\nMevcut topicler:")
        for t in sorted(topics)[:10]:  # İlk 10
            print(f"   - {t}")
    
    # Subscribe
    print(f"\nTopic'e subscribe ediliyor...")
    consumer.subscribe([topic])
    print("✅ Subscribe OK")
    
    # Mesaj dinle (3 saniye)
    print("\n3 saniye mesaj dinleniyor...")
    messages_count = 0
    
    for i in range(30):
        msg = consumer.poll(0.1)
        if msg is None:
            continue
        if msg.error():
            print(f"⚠️  Error: {msg.error()}")
            continue
        
        messages_count += 1
        if messages_count <= 2:
            ts = msg.timestamp()[1] / 1000
            value = msg.value().decode('utf-8')[:80]
            print(f"✅ Mesaj #{messages_count}: {value}...")
    
    if messages_count > 0:
        print(f"\n🎉 CANLI AKIŞ VAR! ({messages_count} mesaj)")
    else:
        print(f"\n⚠️  Mesaj gelmedi (production yok)")
    
    consumer.close()
    print("\n✅ Consumer kapatıldı")
    
except KafkaException as e:
    print(f"\n❌ Kafka Exception: {e}")
    if "Connection refused" in str(e):
        print("   → Broker kapalı veya unreachable")
    elif "timed out" in str(e):
        print("   → Connection timeout - VPN'i kontrol et!")
except Exception as e:
    print(f"\n❌ Hata: {e}")

print("\n" + "="*60)
print("TEST TAMAMLANDI")
print("="*60 + "\n")
