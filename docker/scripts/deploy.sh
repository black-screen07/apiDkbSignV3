#!/bin/bash
# ==============================================================================
# DkbSign V3 - Deployment Script
# Automated deployment with health checks and rollback capability
# ==============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="docker-compose.yml"
PROJECT_NAME="dkbsign"
BACKUP_DIR="./backups"
MAX_RETRIES=30
RETRY_INTERVAL=10

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed"
        exit 1
    fi
    
    if [ ! -f ".env" ]; then
        log_error ".env file not found. Please copy .env.example to .env and configure it."
        exit 1
    fi
    
    log_info "Prerequisites check passed"
}

create_backup() {
    log_info "Creating backup before deployment..."
    
    mkdir -p "$BACKUP_DIR"
    BACKUP_FILE="$BACKUP_DIR/backup_$(date +%Y%m%d_%H%M%S).sql"
    
    if docker-compose ps | grep -q "dkbsign_db.*Up"; then
        docker-compose exec -T db mysqldump -u root -p"${DB_ROOT_PASSWORD}" "${DB_NAME}" > "$BACKUP_FILE" 2>/dev/null || true
        
        if [ -f "$BACKUP_FILE" ]; then
            log_info "Backup created: $BACKUP_FILE"
        else
            log_warn "Backup creation failed, but continuing deployment"
        fi
    else
        log_warn "Database not running, skipping backup"
    fi
}

pull_images() {
    log_info "Pulling latest images..."
    docker-compose -f "$COMPOSE_FILE" pull
}

build_app() {
    log_info "Building application image..."
    docker-compose -f "$COMPOSE_FILE" build --no-cache app
}

stop_services() {
    log_info "Stopping services..."
    docker-compose -f "$COMPOSE_FILE" down
}

start_services() {
    log_info "Starting services..."
    docker-compose -f "$COMPOSE_FILE" up -d
}

wait_for_health() {
    log_info "Waiting for services to be healthy..."
    
    local retries=0
    while [ $retries -lt $MAX_RETRIES ]; do
        if docker-compose ps | grep -q "dkbsign_app.*Up.*healthy"; then
            log_info "Application is healthy"
            return 0
        fi
        
        retries=$((retries + 1))
        log_info "Waiting for health check... ($retries/$MAX_RETRIES)"
        sleep $RETRY_INTERVAL
    done
    
    log_error "Health check failed after $MAX_RETRIES attempts"
    return 1
}

run_migrations() {
    log_info "Running database migrations..."
    docker-compose exec -T app flask db upgrade || {
        log_error "Migration failed"
        return 1
    }
    log_info "Migrations completed successfully"
}

show_status() {
    log_info "Deployment Status:"
    docker-compose ps
    echo ""
    log_info "Application logs (last 20 lines):"
    docker-compose logs --tail=20 app
}

rollback() {
    log_error "Deployment failed. Rolling back..."
    docker-compose down
    
    # Restore from latest backup if available
    LATEST_BACKUP=$(ls -t "$BACKUP_DIR"/backup_*.sql 2>/dev/null | head -1)
    if [ -n "$LATEST_BACKUP" ]; then
        log_info "Restoring from backup: $LATEST_BACKUP"
        docker-compose up -d db
        sleep 10
        docker-compose exec -T db mysql -u root -p"${DB_ROOT_PASSWORD}" "${DB_NAME}" < "$LATEST_BACKUP"
    fi
    
    exit 1
}

# Main deployment flow
main() {
    log_info "Starting DkbSign V3 deployment..."
    
    # Load environment variables
    source .env
    
    check_prerequisites
    
    # Create backup before deployment
    create_backup
    
    # Pull and build
    pull_images
    build_app
    
    # Deploy
    stop_services
    start_services
    
    # Wait for health check
    if ! wait_for_health; then
        rollback
    fi
    
    # Run migrations
    if ! run_migrations; then
        rollback
    fi
    
    # Show status
    show_status
    
    log_info "Deployment completed successfully!"
    log_info "Application is running at: http://localhost"
    log_info "API documentation: http://localhost/v3/"
}

# Run main function
main "$@"
