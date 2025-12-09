#!/bin/bash
# ==============================================================================
# DkbSign V3 - Restore Script
# Restore database from backup
# ==============================================================================

set -e

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

# Check if backup file is provided
if [ -z "$1" ]; then
    log_error "Usage: $0 <backup_file.sql.gz>"
    log_info "Available backups:"
    ls -lh ./backups/*.sql.gz 2>/dev/null || echo "No backups found"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    log_error "Backup file not found: $BACKUP_FILE"
    exit 1
fi

# Load environment
source .env

log_warn "This will restore the database from: $BACKUP_FILE"
log_warn "Current database will be OVERWRITTEN!"
read -p "Are you sure? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    log_info "Restore cancelled"
    exit 0
fi

# Stop application
log_info "Stopping application..."
docker-compose stop app

# Restore database
log_info "Restoring database..."
gunzip < "$BACKUP_FILE" | docker-compose exec -T db mysql -u root -p"${DB_ROOT_PASSWORD}" "${DB_NAME}"

if [ $? -eq 0 ]; then
    log_info "Database restored successfully"
else
    log_error "Database restore failed"
    exit 1
fi

# Restart application
log_info "Starting application..."
docker-compose start app

# Wait for health check
sleep 10
docker-compose ps

log_info "Restore completed successfully"
