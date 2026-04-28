#!/bin/bash
# Codlean MES - Otomatik Backup Script
# Kullanım: ./backup.sh veya cron ile günlük çalıştır

set -e

# Değişkenler
BACKUP_DIR="/Volumes/Workspace_Ahsen/Projeler/kafka/backups"
PROJECT_DIR="/Volumes/Workspace_Ahsen/Projeler/kafka"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
DATE_TODAY=$(date +"%Y-%m-%d")

# Backup klasörü oluştur
mkdir -p "$BACKUP_DIR/$DATE_TODAY"

echo "🔄 Codlean MES Backup başlatılıyor..."
echo "📅 Tarih: $(date)"
echo "📁 Backup dizini: $BACKUP_DIR/$DATE_TODAY"

# 1. state.json backup
if [ -f "$PROJECT_DIR/state.json" ]; then
    cp "$PROJECT_DIR/state.json" "$BACKUP_DIR/$DATE_TODAY/state_$TIMESTAMP.json"
    echo "✅ state.json backup edildi"
else
    echo "⚠️  state.json bulunamadı"
fi

# 2. live_windows.json backup
if [ -f "$PROJECT_DIR/live_windows.json" ]; then
    cp "$PROJECT_DIR/live_windows.json" "$BACKUP_DIR/$DATE_TODAY/live_windows_$TIMESTAMP.json"
    echo "✅ live_windows.json backup edildi"
else
    echo "⚠️  live_windows.json bulunamadı"
fi

# 3. rich_context_windows.jsonl backup
if [ -f "$PROJECT_DIR/rich_context_windows.jsonl" ]; then
    cp "$PROJECT_DIR/rich_context_windows.jsonl" "$BACKUP_DIR/$DATE_TODAY/rich_context_$TIMESTAMP.jsonl"
    echo "✅ rich_context_windows.jsonl backup edildi"
fi

# 4. data/ klasörü backup (sadece önemli dosyalar)
if [ -d "$PROJECT_DIR/data" ]; then
    tar -czf "$BACKUP_DIR/$DATE_TODAY/data_$TIMESTAMP.tar.gz" \
        --exclude='daily' \
        -C "$PROJECT_DIR" data/
    echo "✅ data/ klasörü backup edildi"
fi

# 5. config/ klasörü backup
if [ -d "$PROJECT_DIR/config" ]; then
    cp -r "$PROJECT_DIR/config" "$BACKUP_DIR/$DATE_TODAY/config_$TIMESTAMP"
    echo "✅ config/ klasörü backup edildi"
fi

# 6. docs/ klasörü backup
if [ -d "$PROJECT_DIR/docs" ]; then
    cp -r "$PROJECT_DIR/docs" "$BACKUP_DIR/$DATE_TODAY/docs_$TIMESTAMP"
    echo "✅ docs/ klasörü backup edildi"
fi

# 30 günden eski backup'ları sil
echo ""
echo "🗑️  Eski backup'lar temizleniyor (30+ gün)..."
find "$BACKUP_DIR" -type d -mtime +30 -exec rm -rf {} + 2>/dev/null || true
echo "✅ Eski backup'lar temizlendi"

# Backup özeti
echo ""
echo "📊 Backup Özeti:"
echo "   Tarih: $DATE_TODAY"
echo "   Dosyalar: $(ls -1 "$BACKUP_DIR/$DATE_TODAY" | wc -l | tr -d ' ')"
echo "   Boyut: $(du -sh "$BACKUP_DIR/$DATE_TODAY" | cut -f1)"
echo ""
echo "✅ Backup tamamlandı!"
