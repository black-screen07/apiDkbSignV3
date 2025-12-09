#!/bin/bash
# ==============================================================================
# DkbSign V3 - Log Viewer Script
# Easy access to container logs
# ==============================================================================

# Default values
SERVICE="app"
LINES=100
FOLLOW=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -s|--service)
            SERVICE="$2"
            shift 2
            ;;
        -n|--lines)
            LINES="$2"
            shift 2
            ;;
        -f|--follow)
            FOLLOW=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -s, --service SERVICE   Service name (app, db, redis, nginx)"
            echo "  -n, --lines NUMBER      Number of lines to show (default: 100)"
            echo "  -f, --follow            Follow log output"
            echo "  -h, --help              Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 -s app -n 50         # Show last 50 lines from app"
            echo "  $0 -s nginx -f          # Follow nginx logs"
            echo "  $0 --service db         # Show last 100 lines from db"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use -h or --help for usage information"
            exit 1
            ;;
    esac
done

# Build docker-compose command
CMD="docker-compose logs --tail=$LINES"

if [ "$FOLLOW" = true ]; then
    CMD="$CMD -f"
fi

CMD="$CMD $SERVICE"

# Execute
echo "Showing logs for: $SERVICE"
echo "================================"
eval $CMD
