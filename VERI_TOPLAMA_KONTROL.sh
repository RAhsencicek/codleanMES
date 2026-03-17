#!/bin/bash
# ═══════════════════════════════════════════════════════════
#  CODLEAN MES - VERİ TOPLAMA KONTROL SCRİPTİ
# ═══════════════════════════════════════════════════════════

echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║     🤖 CODLEAN MES - VERİ TOPLAMA KONTROL PANELİ         ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

# 1. Sistem Çalışma Durumu
echo "📊 1. SİSTEM DURUMU"
echo "─────────────────────────────────────────────────────────────"
HPR_PID=$(pgrep -f "hpr_monitor.py" | head -1)
if [ -n "$HPR_PID" ]; then
    echo "✅ Sistem ÇALIŞIYOR (PID: $HPR_PID)"
    ps -o etime= -p $HPR_PID 2>/dev/null && echo "   Süre: $(ps -o etime= -p $HPR_PID)"
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
    MODIFIED=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M" live_windows.json 2>/dev/null || stat -c "%y" live_windows.json | cut -d'.' -f1)
    echo "✅ live_windows.json"
    echo "   Boyut: $SIZE | Satır: $LINES | Son güncelleme: $MODIFIED"
else
    echo "❌ live_windows.json bulunamadı"
fi

if [ -f "state.json" ]; then
    SIZE=$(ls -lh state.json | awk '{print $5}')
    echo "✅ state.json (Boyut: $SIZE)"
else
    echo "❌ state.json bulunamadı"
fi
echo ""

# 3. Son Veriler
echo "📝 3. SON KAYITLAR (live_windows.json)"
echo "─────────────────────────────────────────────────────────────"
if [ -f "live_windows.json" ]; then
    # Son timestamp'i bul
    LAST_TS=$(grep -o '"ts": "[^"]*"' live_windows.json | tail -1 | cut -d'"' -f4)
    if [ -n "$LAST_TS" ]; then
        echo "🕐 Son kayıt: $LAST_TS"
    fi
    
    # Makine sayısı
    MACHINES=$(grep -o '"HPR[0-9]*"' live_windows.json | sort -u | wc -l)
    echo "�� Toplam makine: $MACHINES"
    
    # Normal ve fault pencere sayısı
    NORMAL=$(grep -c '"readings"' live_windows.json 2>/dev/null || echo "0")
    echo "📊 Tahmini pencere sayısı: ~$NORMAL"
else
    echo "Veri dosyası yok"
fi
echo ""

# 4. VPN Durumu
echo "🔒 4. VPN BAĞLANTISI"
echo "─────────────────────────────────────────────────────────────"
if ifconfig | grep -q "utun"; then
    VPN_IP=$(ifconfig | grep -A 2 "utun" | grep "inet " | awk '{print $2}' | head -1)
    echo "✅ VPN AKTİF (IP: $VPN_IP)"
else
    echo "⚠️  VPN kontrol edilemedi veya kapalı"
fi
echo ""

# 5. Kafka Bağlantısı
echo "📡 5. KAFKA BAĞLANTISI"
echo "─────────────────────────────────────────────────────────────"
nc -z -G 3 10.71.120.10 7001 2>/dev/null && echo "✅ Kafka broker erişilebilir" || echo "❌ Kafka broker erişilemez"
echo ""

echo "═════════════════════════════════════════════════════════════"
echo ""
