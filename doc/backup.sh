
BACKUP_DATE=$(date +%Y%m%d_%H%M%S)

BACKUP_DIR="/opt/backups"
mkdir -p $BACKUP_DIR

cd /opt/chatbot
tar -czf $BACKUP_DIR/code_$BACKUP_DATE.tar.gz .

docker run --rm -v chatbot_logs:/logs -v $BACKUP_DIR:/backup alpine tar -czf /backup/logs_$BACKUP_DATE.tar.gz /logs

echo "バックアップが完了しました: $BACKUP_DIR/code_$BACKUP_DATE.tar.gz"
