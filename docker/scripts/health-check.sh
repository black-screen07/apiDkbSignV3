#!/bin/bash
# ==============================================================================
# DkbSign V3 - Health Check Script
# Monitor application health and send alerts
# ==============================================================================

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[!]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

check_container() {
    local container=$1
    local status=$(docker inspect -f '{{.State.Status}}' "$container" 2>/dev/null || echo "not found")
    
    if [ "$status" = "running" ]; then
        log_info "Container $container: running"
        return 0
    else
        log_error "Container $container: $status"
        return 1
    fi
}

check_health() {
    local container=$1
    local health=$(docker inspect -f '{{.State.Health.Status}}' "$container" 2>/dev/null || echo "no healthcheck")
    
    if [ "$health" = "healthy" ]; then
        log_info "Health check $container: healthy"
        return 0
    else
        log_warn "Health check $container: $health"
        return 1
    fi
}

check_endpoint() {
    local url=$1
    local response=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")
    
    if [ "$response" = "200" ]; then
        log_info "Endpoint $url: OK ($response)"
        return 0
    else
        log_error "Endpoint $url: FAILED ($response)"
        return 1
    fi
}

check_disk_space() {
    local usage=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
    
    if [ "$usage" -lt 80 ]; then
        log_info "Disk space: ${usage}% used"
        return 0
    elif [ "$usage" -lt 90 ]; then
        log_warn "Disk space: ${usage}% used (warning)"
        return 0
    else
        log_error "Disk space: ${usage}% used (critical)"
        return 1
    fi
}

check_memory() {
    local usage=$(free | awk 'NR==2 {printf "%.0f", $3/$2 * 100}')
    
    if [ "$usage" -lt 80 ]; then
        log_info "Memory usage: ${usage}%"
        return 0
    elif [ "$usage" -lt 90 ]; then
        log_warn "Memory usage: ${usage}% (warning)"
        return 0
    else
        log_error "Memory usage: ${usage}% (critical)"
        return 1
    fi
}

# Main health check
echo "================================"
echo "DkbSign V3 - Health Check"
echo "$(date)"
echo "================================"
echo ""

ERRORS=0

# Check containers
echo "Checking containers..."
check_container "dkbsign_db" || ((ERRORS++))
check_container "dkbsign_redis" || ((ERRORS++))
check_container "dkbsign_app" || ((ERRORS++))
check_container "dkbsign_nginx" || ((ERRORS++))
echo ""

# Check health
echo "Checking health status..."
check_health "dkbsign_db" || ((ERRORS++))
check_health "dkbsign_app" || ((ERRORS++))
check_health "dkbsign_nginx" || ((ERRORS++))
echo ""

# Check endpoints
echo "Checking endpoints..."
check_endpoint "http://localhost/health" || ((ERRORS++))
check_endpoint "http://localhost:5000/health" || ((ERRORS++))
echo ""

# Check resources
echo "Checking system resources..."
check_disk_space || ((ERRORS++))
check_memory || ((ERRORS++))
echo ""

# Summary
echo "================================"
if [ $ERRORS -eq 0 ]; then
    log_info "All checks passed!"
    exit 0
else
    log_error "$ERRORS check(s) failed"
    exit 1
fi
