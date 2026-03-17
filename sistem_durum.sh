#!/bin/bash
# ═══════════════════════════════════════════════════════════
#  CODLEAN MES - SİSTEM DURUM KONTROL SCRİPTİ
# ═══════════════════════════════════════════════════════════

cd /Users/mac/kafka

echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║     🤖 CODLEAN MES - SİSTEM DURUM KONTROLÜ               ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

# 1. Sistem Çalışma Durumu
echo "📊 1. SİSTEM DURUMU"
echo "─────────────────────────────────────────────────────────────"
HPR_PID=$(pgrep -f "hpr_monitor.py" | head -1)
if [ -n "$HPR_PID" ]; then
    echo "✅ Sistem ÇALIŞIYOR"
    echo "   PID: $HPR_PID"
    # macOS için süre hesaplama
    START_TIME=$(ps -o lstart= -p $HPR_PID 2>/dev/null)
    if [ -n "$START_TIME" ]; then
        echo "   Başlangıç: $START_TIME"
    fi
    # CPU ve Memory kullanımı
    CPU_MEM=$(ps -o %cpu,%mem= -p $HPR_PID 2>/dev/null)
    if [ -n "$CPU_MEM" ]; then
        echo "   CPU/MEM: $CPU_MEM"
    fi
else
    echo "❌ Sistem DURMUŞ"
fi
echo ""

# 2. Veri Dosyaları
echo "📁 2. VERİ DOSYALARI"
echo "─────────────────────────────────────────────────────────────"
if [ -f "live_windows.json" ]; then
    SIZE=$(ls -lh live_windows.json | awk '{print $5}')
    LINES=$(wc -l < live_windows.json)
    MODIFIED=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M" live_windows.json 2>/dev/null)
    echo "✅ live_windows.json"
    echo "   Boyut: $SIZE"
    echo "   Satır: $LINES"
    echo "   Son güncelleme: $MODIFIED"
else
    echo "❌ live_windows.json bulunamadı"
fi
echo ""

if [ -f "state.json" ]; then
    SIZE=$(ls -lh state.json | awk '{print $5}')
    MODIFIED=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M" state.json 2>/dev/null)
    echo "✅ state.json"
    echo "   Boyut: $SIZE"
    echo "   Son güncelleme: $MODIFIED"
else
    echo "❌ state.json bulunamadı"
fi
echo ""

# 3. Son Veriler
echo "📝 3. SON KAYITLAR"
echo "─────────────────────────────────────────────────────────────"
if [ -f "live_windows.json" ]; then
    # Son timestamp
    LAST_TS=$(grep -o '"ts": "[^"]*"' live_windows.json | tail -1 | cut -d'"' -f4)
    if [ -n "$LAST_TS" ]; then
        echo "🕐 Son kayıt zamanı: $LAST_TS"
    fi
    
    # Makine sayısı
    MACHINES=$(grep -o '"HPR[0-9]*"' live_windows.json | sort -u | wc -l)
    echo "🏭 Makine sayısı: $MACHINES"
    
    # Her makineden kaç kayıt var
    echo "   Makine başına kayıt:"
    for machine in HPR001 HPR002 HPR003 HPR004 HPR005 HPR006; do
        COUNT=$(grep -c "$machine" live_windows.json)
        if [ $COUNT -gt 0 ]; then
            echo "     - $machine: $COUNT"
        fi
    done
else
    echo "Veri dosyası yok"
fi
echo ""

# 4. VPN ve Network
echo "🔒 4. AĞ BAĞLANTISI"
echo "─────────────────────────────────────────────────────────────"
if ifconfig | grep -q "utun"; then
    VPN_IP=$(ifconfig utun* 2>/dev/null | grep "inet " | awk '{print $2}' | head -1)
    echo "✅ VPN AKTİF"
    echo "   IP: $VPN_IP"
else
    echo "⚠️  VPN kontrol edilemedi"
fi

# Kafka bağlantısı
if nc -z -G 3 10.71.120.10 7001 2>/dev/null; then
    echo "✅ Kafka broker (10.71.120.10:7001) erişilebilir"
else
    echo "❌ Kafka broker erişilemez"
fi

# PostgreSQL bağlantısı
if nc -z -G 3 10.71.0.27 5432 2>/dev/null; then
    echo "✅ PostgreSQL (10.71.0.27:5432) erişilebilir"
else
    echo "❌ PostgreSQL erişilemez"
fi
echo ""

# 5. Son Log Kayıtları
echo "📜 5. SON LOG KAYITLARI"
echo "─────────────────────────────────────────────────────────────"
LATEST_LOG=$(ls -t logs/hpr_monitor_*.log 2>/dev/null | head -1)
if [ -n "$LATEST_LOG" ]; then
    echo "📄 $LATEST_LOG"
    echo ""
    echo "   Son 5 satır:"
    tail -5 "$LATEST_LOG" | sed 's/^/   /'
else
    echo "Log dosyası bulunamadı"
fi
echo ""

echo "═════════════════════════════════════════════════════════════"
echo ""
