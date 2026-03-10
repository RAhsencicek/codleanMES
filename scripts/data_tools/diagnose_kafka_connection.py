"""
diagnose_kafka_connection.py — Detaylı Kafka Bağlantı Teşhisi
══════════════════════════════════════════════════════════════
VPN, network, broker durumunu adım adım kontrol et.
"""

import socket
import subprocess
import sys
from datetime import datetime

print("\n" + "="*70)
print(" " * 20 + "KAFKA CONNECTION DIAGNOSTICS")
print("="*70)
print(f"\n📅 Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# ──────────────────────────────────────────────────────────────
# TEST 1: VPN BAĞLANTISI
# ──────────────────────────────────────────────────────────────
print("\n" + "-"*70)
print("TEST 1: VPN BAĞLANTISI KONTROLÜ")
print("-"*70)

try:
    # OpenVPN process check
    result = subprocess.run(['pgrep', '-f', 'openvpn'], capture_output=True, text=True)
    if result.returncode == 0:
        print("✅ OpenVPN process çalışıyor")
        print(f"   PID: {result.stdout.strip()}")
    else:
        print("❌ OpenVPN process çalışmıyor!")
        print("   → Önce VPN'i açın (OpenVPN Connect)")
except Exception as e:
    print(f"⚠️  Process check hatası: {e}")

# ──────────────────────────────────────────────────────────────
# TEST 2: NETWORK INTERFACE
# ──────────────────────────────────────────────────────────────
print("\n" + "-"*70)
print("TEST 2: NETWORK INTERFACE")
print("-"*70)

try:
    result = subprocess.run(['ifconfig', 'utun3'], capture_output=True, text=True)
    if result.returncode == 0:
        print("✅ VPN interface (utun3) mevcut")
        # IP adresini bul
        for line in result.stdout.split('\n'):
            if 'inet ' in line:
                print(f"   VPN IP: {line.split()[1]}")
    else:
        print("❌ VPN interface (utun3) yok")
        print("   → VPN bağlı değil veya farklı interface kullanıyor")
except Exception as e:
    print(f"⚠️  Interface check hatası: {e}")

# ──────────────────────────────────────────────────────────────
# TEST 3: KAFKA BROKER PING (ICMP)
# ──────────────────────────────────────────────────────────────
print("\n" + "-"*70)
print("TEST 3: KAFKA BROKER ERİŞİLEBİLİRLİK (PING)")
print("-"*70)

broker_host = "10.71.120.10"
print(f"Hedef: {broker_host}")

try:
    result = subprocess.run(['ping', '-c', '3', '-W', '2', broker_host], 
                          capture_output=True, text=True, timeout=10)
    if result.returncode == 0:
        print(f"✅ Broker PING başarılı!")
        # RTT çıkar
        for line in result.stdout.split('\n'):
            if 'rtt' in line.lower() or 'round-trip' in line.lower():
                print(f"   {line}")
    else:
        print(f"❌ Broker PING başarısız!")
        print(f"   → Broker kapalı VEYA firewall engelliyor")
        print(f"   → Network route yok")
except subprocess.TimeoutExpired:
    print("❌ Ping timeout (10 sn)")
    print("   → Broker unreachable")
except Exception as e:
    print(f"❌ Ping hatası: {e}")

# ──────────────────────────────────────────────────────────────
# TEST 4: KAFKA PORT SCAN (TCP)
# ──────────────────────────────────────────────────────────────
print("\n" + "-"*70)
print("TEST 4: KAFKA PORT TARAMA (7001)")
print("-"*70)

broker_host = "10.71.120.10"
broker_port = 7001

print(f"Hedef: {broker_host}:{broker_port}")

try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    result = sock.connect_ex((broker_host, broker_port))
    
    if result == 0:
        print(f"✅ Port {broker_port} AÇIK!")
        print(f"   → Kafka broker erişilebilir")
    else:
        print(f"❌ Port {broker_port} KAPALI veya ERİŞİLEMİYOR")
        print(f"   → Socket error code: {result}")
        print(f"   → Broker kapalı VEYA firewall engelliyor")
    
    sock.close()
except Exception as e:
    print(f"❌ Port scan hatası: {e}")

# ──────────────────────────────────────────────────────────────
# TEST 5: DNS RESOLUTION
# ──────────────────────────────────────────────────────────────
print("\n" + "-"*70)
print("TEST 5: DNS RESOLUTION")
print("-"*70)

try:
    ip_addr = socket.gethostbyname(broker_host)
    print(f"✅ DNS Resolution başarılı")
    print(f"   {broker_host} → {ip_addr}")
except Exception as e:
    print(f"❌ DNS Resolution başarısız: {e}")

# ──────────────────────────────────────────────────────────────
# TEST 6: ROUTE TABLE
# ──────────────────────────────────────────────────────────────
print("\n" + "-"*70)
print("TEST 6: NETWORK ROUTE TABLE")
print("-"*70)

try:
    result = subprocess.run(['netstat', '-rn'], capture_output=True, text=True)
    print("Routing table (ilk 20 satır):")
    lines = result.stdout.split('\n')[:20]
    for line in lines:
        if '10.71' in line or 'Destination' in line or 'default' in line:
            print(f"   {line}")
except Exception as e:
    print(f"⚠️  Route table check hatası: {e}")

# ──────────────────────────────────────────────────────────────
# TEST 7: KAFKA CONSUMER (ACTUAL CONNECTION)
# ──────────────────────────────────────────────────────────────
print("\n" + "-"*70)
print("TEST 7: KAFKA CONSUMER CONNECTION")
print("-"*70)

from confluent_kafka import Consumer, KafkaException

KAFKA_CONFIG = {
    'bootstrap.servers': '10.71.120.10:7001',
    'group.id': 'ariza-tahmin-pipeline',
    'client.id': 'diagnostic-test',
    'socket.timeout.ms': 5000,
    'session.timeout.ms': 6000,
}

print(f"Bootstrap: {KAFKA_CONFIG['bootstrap.servers']}")
print(f"Topic: mqtt-topic-v2")
print(f"Timeout: 10 saniye\n")

try:
    consumer = Consumer(KAFKA_CONFIG)
    print("✅ Consumer oluşturuldu")
    
    # Metadata al (broker info)
    metadata = consumer.list_topics(timeout=10)
    print(f"✅ Cluster metadata alındı!")
    
    # Topic listesi
    topics = list(metadata.topics.keys())
    print(f"   Topics: {len(topics)} adet")
    if 'mqtt-topic-v2' in topics:
        print(f"   ✅ 'mqtt-topic-v2' topic bulundu!")
    else:
        print(f"   ❌ 'mqtt-topic-v2' topic YOK!")
        print(f"   → Topic adı yanlış olabilir")
    
    # Subscribe deney
    try:
        consumer.subscribe(['mqtt-topic-v2'])
        print(f"✅ Topic subscribe edildi!")
        
        # Mesaj dinle (5 saniye)
        print(f"\n   5 saniye mesaj dinleniyor...\n")
        messages_count = 0
        
        for i in range(50):  # Max 50 poll
            msg = consumer.poll(0.1)
            if msg is None:
                continue
            if msg.error():
                print(f"   ⚠️  Kafka error: {msg.error()}")
                continue
            
            messages_count += 1
            if messages_count <= 3:
                ts = msg.timestamp()[1] / 1000
                value = msg.value().decode('utf-8')[:50]
                print(f"   ✅ Mesaj #{messages_count}: {value}...")
        
        if messages_count > 0:
            print(f"\n   🎉 CANLI MESAJ AKIŞI VAR! ({messages_count} mesaj)")
        else:
            print(f"\n   ⚠️  Mesaj gelmedi (production yok veya topic boş)")
        
        consumer.close()
        
    except Exception as e:
        print(f"❌ Subscribe hatası: {e}")
        consumer.close()
        
except KafkaException as e:
    print(f"❌ Kafka Exception: {e}")
    if "Connection refused" in str(e):
        print(f"   → Broker kapalı veya unreachable")
    elif "timed out" in str(e):
        print(f"   → Connection timeout (firewall?)")
except Exception as e:
    print(f"❌ General exception: {e}")

# ──────────────────────────────────────────────────────────────
# SONUÇ VE ÖNERİLER
# ──────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("SONUÇ VE ÖNERİLER")
print("="*70)

print("""
┌─────────────────────────────────────────────────────────────────┐
│ MUHTEMEL SORUNLAR                                                │
├─────────────────────────────────────────────────────────────────┤
│ 1. VPN TAM-TUNNEL DEĞİL                                          │
│    → Sadece bazı IP'ler VPN üzerinden                           │
│    → 10.71.120.10 VPN'den geçmiyor                              │
│    → ÇÖZÜM: Tam-tunnel VPN config gerekli                       │
│                                                                 │
│ 2. KAFKA BROKER KAPALI                                           │
│    → Hafta sonu/akşam bakım                                     │
│    → Production şu an yok                                       │
│    → ÇÖZÜM: Yarın iş saatinde dene                              │
│                                                                 │
│ 3. FIREWALL ENGELLEME                                            │
│    → VPN içinden bile port block                                │
│    → IT politikası                                              │
│    → ÇÖZÜM: IT ile iletişime geç                                │
│                                                                 │
│ 4. TOPIC ADI YANLIŞ                                              │
│    → mqtt-topic-v2 yerine farklı isim                           │
│    → ÇÖZÜM: Kafka admin'e sor                                   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ SONRAKİ ADIMLAR                                                  │
├─────────────────────────────────────────────────────────────────┤
│ 1. IT/Kafka Admin'e Ulaş:                                        │
│    → "Kafka broker 10.71.120.10:7001 çalışan mı?"               │
│    → "mqtt-topic-v2 topic adı doğru mu?"                        │
│    → "VPN'den erişim var mı?"                                   │
│                                                                 │
│ 2. Tam-Tunnel VPN Kontrol Et:                                    │
│    → OpenVPN Connect ayarları                                   │
│    → "route all" veya benzeri full tunnel option                │
│                                                                 │
│ 3. İş Saatinde Tekrar Dene:                                      │
│    → Pazartesi 09:00                                            │
│    → Production aktif olacak                                    │
│                                                                 │
│ 4. Alternatif: Mock Data ile Devam                               │
│    → Sistem zaten production-ready                              │
│    → Technician feedback al                                     │
│    → Akşam/ofiste tekrar dene                                   │
└─────────────────────────────────────────────────────────────────┘
""")

print("\n" + "="*70)
print("DIAGNOSTICS TAMAMLANDI")
print("="*70 + "\n")
