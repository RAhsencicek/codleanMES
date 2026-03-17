#!/bin/bash
# ═══════════════════════════════════════════════════════════
#  CODLEAN MES - GÖRÜNÜR MOD BAŞLATMA (Terminal Açık Kalır)
# ═══════════════════════════════════════════════════════════

cd /Users/mac/kafka

echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║  🤖 CODLEAN MES - GÖRÜNÜR MOD BAŞLATMA                   ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

# Önceki çalışan var mı kontrol et
HPR_PID=$(pgrep -f "hpr_monitor.py" | head -1)
if [ -n "$HPR_PID" ]; then
    echo "⚠️  Sistem zaten çalışıyor (PID: $HPR_PID)"
    echo "   Önce ./sistem_durdur.sh çalıştırın"
    exit 1
fi

# VPN kontrolü
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

# Kafka kontrolü
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

echo ""
echo "✅ Tüm kontroller tamamlandı!"
echo ""
echo "═════════════════════════════════════════════════════════════"
echo "🚀 Sistem 3 saniye içinde başlıyor..."
echo "   Terminal AÇIK kalacak - veri akışını görebilirsiniz"
echo "   Çıkmak için: Ctrl+C"
echo "═════════════════════════════════════════════════════════════"
echo ""

sleep 3

# Virtual environment aktif et
source venv/bin/activate

# Log dizini
mkdir -p logs
LOG_FILE="logs/hpr_monitor_$(date +%Y%m%d_%H%M%S).log"

echo "📄 Log dosyası: $LOG_FILE"
echo "▶️  Sistem başlıyor..."
echo ""

# Terminal açık kalacak şekilde çalıştır (tee ile hem ekrana hem dosyaya)
PYTHONPATH=. python3 src/app/hpr_monitor.py 2>&1 | tee "$LOG_FILE"

# Ctrl+C ile çıkıldığında buraya gelir
echo ""
echo "═════════════════════════════════════════════════════════════"
echo "🛑 Sistem durduruldu"
echo "📄 Log kaydedildi: $LOG_FILE"
echo "═════════════════════════════════════════════════════════════"
