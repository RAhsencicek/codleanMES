#!/bin/bash
# ═══════════════════════════════════════════════════════════
#  CODLEAN MES - SİSTEM BAŞLATMA SCRİPTİ
# ═══════════════════════════════════════════════════════════

cd /Users/mac/kafka

echo ""
echo "🚀 CODLEAN MES Sistemi Başlatılıyor..."
echo "═════════════════════════════════════════════════════════════"
echo ""

# 1. Önceki çalışan var mı kontrol et
HPR_PID=$(pgrep -f "hpr_monitor.py" | head -1)
if [ -n "$HPR_PID" ]; then
    echo "⚠️  Sistem zaten çalışıyor (PID: $HPR_PID)"
    echo "   Önce sistem_durdur.sh çalıştırın"
    exit 1
fi

# 2. VPN kontrolü
echo "🔒 VPN kontrol ediliyor..."
if ! ifconfig | grep -q "utun"; then
    echo "⚠️  UYARI: VPN aktif görünmüyor!"
    echo "   Devam etmek istiyor musunuz? (e/h)"
    read -r cevap
    if [ "$cevap" != "e" ]; then
        echo "❌ İptal edildi"
        exit 1
    fi
fi

# 3. Kafka bağlantısı kontrolü
echo "📡 Kafka bağlantısı kontrol ediliyor..."
if ! nc -z -G 3 10.71.120.10 7001 2>/dev/null; then
    echo "⚠️  UYARI: Kafka broker erişilemiyor!"
    echo "   Devam etmek istiyor musunuz? (e/h)"
    read -r cevap
    if [ "$cevap" != "e" ]; then
        echo "❌ İptal edildi"
        exit 1
    fi
fi

# 4. Virtual environment aktif et
echo "🐍 Python ortamı hazırlanıyor..."
source venv/bin/activate

# 5. Log dizini oluştur
mkdir -p logs

# 6. Sistemi başlat
echo "▶️  Sistem başlatılıyor..."
echo ""

# Tarih ile log dosyası adı
LOG_FILE="logs/hpr_monitor_$(date +%Y%m%d_%H%M%S).log"

# Arka planda çalıştır
export PYTHONPATH=. # PYTHONPATH'i nohup'tan önce ayarla
nohup python3 src/app/hpr_monitor.py > "$LOG_FILE" 2>&1 &
PID=$!

# PID kaydet
echo $PID > /tmp/hpr_monitor.pid

echo "✅ Sistem başlatıldı!"
echo "   PID: $PID"
echo "   Log: $LOG_FILE"
echo ""
echo "📋 Kullanabileceğiniz komutlar:"
echo "   ./sistem_durum.sh   → Durum kontrolü"
echo "   ./sistem_durdur.sh  → Sistemi durdur"
echo "   tail -f $LOG_FILE   → Logları izle"
echo ""
echo "═════════════════════════════════════════════════════════════"
