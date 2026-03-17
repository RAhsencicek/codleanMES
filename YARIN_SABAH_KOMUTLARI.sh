#!/bin/bash
# YARIN SABAH ÇALIŞTIRILACAK KOMUTLAR
# Tarih: 2026-03-17

echo "═══════════════════════════════════════════════════════════"
echo "  CODLEAN MES - SABAH KONTROL RAPORU"
echo "═══════════════════════════════════════════════════════════"
echo ""

# 1. Sistem Durumu Kontrol
echo "📊 1. SİSTEM DURUMU KONTROLÜ"
echo "───────────────────────────────────────────────────────────"
ps aux | grep "hpr_monitor" | grep -v grep
echo ""

# 2. Veri Boyutları
echo "📁 2. VERİ BOYUTLARI"
echo "───────────────────────────────────────────────────────────"
echo "live_windows.json:"
ls -lh /Users/mac/kafka/live_windows.json
echo ""
echo "state.json:"
ls -lh /Users/mac/kafka/state.json
echo ""

# 3. Yeni Veri Sayısı
echo "📈 3. TOPLAM VERİ SAYISI"
echo "───────────────────────────────────────────────────────────"
echo "live_windows.json satır sayısı:"
wc -l /Users/mac/kafka/live_windows.json
echo ""
echo "violation_log.json satır sayısı:"
wc -l /Users/mac/kafka/data/violation_log.json
echo ""

# 4. Son Verileri Gör
echo "📝 4. SON VERİLER (son 20 satır)"
echo "───────────────────────────────────────────────────────────"
tail -20 /Users/mac/kafka/live_windows.json
echo ""

# 5. Eski Logları Kontrol Et
echo "📜 5. ESKİ LOGLAR"
echo "───────────────────────────────────────────────────────────"
echo "Mevcut log dosyaları:"
ls -lh /Users/mac/kafka/logs/*.log 2>/dev/null | head -10
echo ""

# 6. Sistem Performansı
echo "⏱️  6. SİSTEM ÇALIŞMA SÜRESİ"
echo "───────────────────────────────────────────────────────────"
ps -o etime= -p $(pgrep -f "hpr_monitor.py" | head -1) 2>/dev/null || echo "Sistem durumu kontrol edilemedi"
echo ""

echo "═══════════════════════════════════════════════════════════"
echo "  KONTROL TAMAMLANDI"
echo "═══════════════════════════════════════════════════════════"
