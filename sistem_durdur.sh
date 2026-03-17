#!/bin/bash
# ═══════════════════════════════════════════════════════════
#  CODLEAN MES - SİSTEM DURDURMA SCRİPTİ
# ═══════════════════════════════════════════════════════════

cd /Users/mac/kafka

echo ""
echo "🛑 CODLEAN MES Sistemi Durduruluyor..."
echo "═════════════════════════════════════════════════════════════"
echo ""

# PID kontrol
if [ -f /tmp/hpr_monitor.pid ]; then
    PID=$(cat /tmp/hpr_monitor.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "📍 Sistem bulundu (PID: $PID)"
        echo "⏳ Güvenli kapatma yapılıyor..."
        
        # SIGTERM gönder (graceful shutdown)
        kill $PID
        
        # 10 saniye bekle
        for i in {1..10}; do
            if ! ps -p $PID > /dev/null 2>&1; then
                echo "✅ Sistem başarıyla durduruldu"
                break
            fi
            echo "   Bekleniyor... ($i/10)"
            sleep 1
        done
        
        # Hala çalışıyorsa SIGKILL
        if ps -p $PID > /dev/null 2>&1; then
            echo "⚠️  Zorla kapatma yapılıyor..."
            kill -9 $PID
        fi
    else
        echo "⚠️  PID dosyası var ama process çalışmıyor"
    fi
    rm -f /tmp/hpr_monitor.pid
else
    # PID dosyası yoksa pgrep ile bul
    HPR_PID=$(pgrep -f "hpr_monitor.py" | head -1)
    if [ -n "$HPR_PID" ]; then
        echo "📍 Sistem bulundu (PID: $HPR_PID)"
        kill $HPR_PID
        sleep 3
        echo "✅ Sistem durduruldu"
    else
        echo "⚠️  Çalışan sistem bulunamadı"
    fi
fi

echo ""
echo "📊 Son Veri Durumu:"
if [ -f "live_windows.json" ]; then
    SIZE=$(ls -lh live_windows.json | awk '{print $5}')
    echo "   live_windows.json: $SIZE"
fi
if [ -f "state.json" ]; then
    SIZE=$(ls -lh state.json | awk '{print $5}')
    echo "   state.json: $SIZE"
fi

echo ""
echo "═════════════════════════════════════════════════════════════"
