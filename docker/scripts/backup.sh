#!/bin/bash
# ==============================================================================
# DkbSign V3 - Backup Script
# Automated database and file backup with retention policy
# ==============================================================================

set -e

# Configuration
BACKUP_DIR="/backups"
RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-30}
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/dkbsign_backup_$TIMESTAMP.sql.gz"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Database backup
log_info "Starting database backup..."
mysqldump -h"${MYSQL_HOST}" -u"${MYSQL_USER}" -p"${MYSQL_PASSWORD}" "${MYSQL_DATABASE}" \
    --single-transaction \
    --quick \
    --lock-tables=false \
    | gzip > "$BACKUP_FILE"

if [ -f "$BACKUP_FILE" ]; then
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    log_info "Database backup completed: $BACKUP_FILE ($BACKUP_SIZE)"
else
    log_error "Database backup failed"
    exit 1
fi

# Backup application files (optional)
if [ -d "/app/documents" ]; then
    log_info "Backing up application files..."
    tar -czf "$BACKUP_DIR/files_backup_$TIMESTAMP.tar.gz" \
        /app/documents \
        /app/certificates \
        /app/signatures \
        /app/stamps \
        2>/dev/null || log_warn "Some files could not be backed up"
fi

# Clean old backups
log_info "Cleaning backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "*.sql.gz" -type f -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.tar.gz" -type f -mtime +$RETENTION_DAYS -delete

# List recent backups
log_info "Recent backups:"
ls -lh "$BACKUP_DIR" | tail -10

log_info "Backup completed successfully"
