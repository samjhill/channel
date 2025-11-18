#!/bin/bash
set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Configuration
DOCKER_IMAGE="tvchannel"
DOCKER_CONTAINER="tvchannel"
DOCKER_PORT="8080"
API_PORT="8000"
ADMIN_UI_PORT="5174"
TEST_CLIENT_PORT="8081"

# Media directory (default: /Volumes/media/tv)
# This is the HOST path that will be mounted to /media/tvchannel inside the container
# Override with MEDIA_DIR environment variable or --media-dir flag
MEDIA_DIR="${MEDIA_DIR:-/Volumes/media/tv}"

# PID file for tracking background processes
PID_FILE="$SCRIPT_DIR/.start_pids"

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}Shutting down services...${NC}"
    
    if [ -f "$PID_FILE" ]; then
        while read -r pid; do
            if kill -0 "$pid" 2>/dev/null; then
                echo "Stopping process $pid"
                kill "$pid" 2>/dev/null || true
            fi
        done < "$PID_FILE"
        rm -f "$PID_FILE"
    fi
    
    echo -e "${GREEN}All services stopped.${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check if a port is in use
port_in_use() {
    lsof -i ":$1" >/dev/null 2>&1
}

# Function to start Docker container
start_docker() {
    echo -e "${BLUE}Starting Docker container...${NC}"
    
    if ! command_exists docker; then
        echo -e "${RED}Error: Docker is not installed or not in PATH${NC}"
        return 1
    fi
    
    # Check if container already exists
    if docker ps -a --format '{{.Names}}' | grep -q "^${DOCKER_CONTAINER}$"; then
        if docker ps --format '{{.Names}}' | grep -q "^${DOCKER_CONTAINER}$"; then
            echo -e "${YELLOW}Container ${DOCKER_CONTAINER} is already running${NC}"
            echo -e "${YELLOW}Note: If you need to change volume mounts, stop and remove the container first${NC}"
        else
            echo -e "${BLUE}Starting existing container ${DOCKER_CONTAINER}...${NC}"
            docker start "$DOCKER_CONTAINER"
        fi
    else
        # Check if image exists
        if ! docker images --format '{{.Repository}}' | grep -q "^${DOCKER_IMAGE}$"; then
            echo -e "${BLUE}Building Docker image...${NC}"
            docker build -t "$DOCKER_IMAGE" -f server/Dockerfile .
        fi
        
        # Verify and create required directories
        if [ ! -d "$MEDIA_DIR" ]; then
            echo -e "${YELLOW}Warning: Media directory does not exist: ${MEDIA_DIR}${NC}"
            echo -e "${YELLOW}Creating directory...${NC}"
            mkdir -p "$MEDIA_DIR" || {
                echo -e "${RED}Error: Could not create media directory${NC}"
                return 1
            }
        fi
        
        # Ensure HLS directory exists (needed for playhead/playlist state)
        mkdir -p "$(pwd)/server/hls" || {
            echo -e "${RED}Error: Could not create HLS directory${NC}"
            return 1
        }
        
        # Ensure assets directory exists
        if [ ! -d "$(pwd)/assets" ]; then
            echo -e "${YELLOW}Warning: Assets directory does not exist, creating...${NC}"
            mkdir -p "$(pwd)/assets" || {
                echo -e "${RED}Error: Could not create assets directory${NC}"
                return 1
            }
        fi
        
        # Ensure config directory exists
        if [ ! -d "$(pwd)/server/config" ]; then
            echo -e "${YELLOW}Warning: Config directory does not exist, creating...${NC}"
            mkdir -p "$(pwd)/server/config" || {
                echo -e "${RED}Error: Could not create config directory${NC}"
                return 1
            }
        fi
        
        echo -e "${BLUE}Creating and starting container...${NC}"
        echo -e "${BLUE}  Media directory: ${MEDIA_DIR} -> /media/tvchannel${NC}"
        echo -e "${BLUE}  Assets: $(pwd)/assets -> /app/assets${NC}"
        echo -e "${BLUE}  Config: $(pwd)/server/config -> /app/config${NC}"
        echo -e "${BLUE}  HLS: $(pwd)/server/hls -> /app/hls${NC}"
        
        docker run -d \
            -p "${DOCKER_PORT}:8080" \
            -v "${MEDIA_DIR}:/media/tvchannel" \
            -v "$(pwd)/assets:/app/assets" \
            -v "$(pwd)/server/config:/app/config" \
            -v "$(pwd)/server/hls:/app/hls" \
            --name "$DOCKER_CONTAINER" \
            "$DOCKER_IMAGE"
    fi
    
    echo -e "${GREEN}Docker container started on port ${DOCKER_PORT}${NC}"
    echo -e "  Stream: http://localhost:${DOCKER_PORT}/channel/stream.m3u8"
}

# Function to start FastAPI backend
start_api() {
    echo -e "${BLUE}Starting FastAPI backend...${NC}"
    
    if port_in_use "$API_PORT"; then
        echo -e "${YELLOW}Port ${API_PORT} is already in use. Skipping API server.${NC}"
        return 0
    fi
    
    # Check for virtual environment
    if [ ! -d ".venv" ]; then
        echo -e "${BLUE}Creating Python virtual environment...${NC}"
        python3 -m venv .venv
    fi
    
    # Use venv's Python directly
    VENV_PYTHON=".venv/bin/python"
    VENV_PIP=".venv/bin/pip"
    
    # Install dependencies if needed
    if ! "$VENV_PYTHON" -c "import fastapi" 2>/dev/null; then
        echo -e "${BLUE}Installing Python dependencies...${NC}"
        "$VENV_PIP" install -q fastapi uvicorn[standard]
    fi
    
    # Start API server in background using venv's uvicorn
    echo -e "${BLUE}Starting API server on port ${API_PORT}...${NC}"
    "$VENV_PYTHON" -m uvicorn server.api.app:app --host 0.0.0.0 --port "$API_PORT" --reload > /tmp/tvchannel_api.log 2>&1 &
    API_PID=$!
    echo "$API_PID" >> "$PID_FILE"
    
    echo -e "${GREEN}FastAPI backend started on port ${API_PORT}${NC}"
    echo -e "  API: http://localhost:${API_PORT}"
    echo -e "  Docs: http://localhost:${API_PORT}/docs"
}

# Function to start React admin UI
start_admin_ui() {
    echo -e "${BLUE}Starting React admin UI...${NC}"
    
    if port_in_use "$ADMIN_UI_PORT"; then
        echo -e "${YELLOW}Port ${ADMIN_UI_PORT} is already in use. Skipping admin UI.${NC}"
        return 0
    fi
    
    cd ui/channel-admin
    
    # Check if node_modules exists
    if [ ! -d "node_modules" ]; then
        echo -e "${BLUE}Installing npm dependencies...${NC}"
        npm install
    fi
    
    # Start Vite dev server in background
    echo -e "${BLUE}Starting admin UI on port ${ADMIN_UI_PORT}...${NC}"
    VITE_API_BASE="http://localhost:${API_PORT}" npm run dev > /tmp/tvchannel_admin_ui.log 2>&1 &
    ADMIN_UI_PID=$!
    echo "$ADMIN_UI_PID" >> "$PID_FILE"
    
    cd "$SCRIPT_DIR"
    
    echo -e "${GREEN}Admin UI started on port ${ADMIN_UI_PORT}${NC}"
    echo -e "  Admin: http://localhost:${ADMIN_UI_PORT}"
}

# Function to start web test client
start_test_client() {
    echo -e "${BLUE}Starting web test client...${NC}"
    
    if port_in_use "$TEST_CLIENT_PORT"; then
        echo -e "${YELLOW}Port ${TEST_CLIENT_PORT} is already in use. Skipping test client.${NC}"
        return 0
    fi
    
    cd client/web_test
    
    # Start HTTP server in background
    echo -e "${BLUE}Starting test client on port ${TEST_CLIENT_PORT}...${NC}"
    python3 -m http.server "$TEST_CLIENT_PORT" > /tmp/tvchannel_test_client.log 2>&1 &
    TEST_CLIENT_PID=$!
    echo "$TEST_CLIENT_PID" >> "$PID_FILE"
    
    cd "$SCRIPT_DIR"
    
    echo -e "${GREEN}Test client started on port ${TEST_CLIENT_PORT}${NC}"
    echo -e "  Test Client: http://localhost:${TEST_CLIENT_PORT}"
}

# Main execution
main() {
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  TV Channel Startup Script${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    
    # Initialize PID file
    > "$PID_FILE"
    
    # Parse command line arguments
    START_DOCKER=true
    START_API=true
    START_ADMIN_UI=true
    START_TEST_CLIENT=true
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --no-docker)
                START_DOCKER=false
                shift
                ;;
            --no-api)
                START_API=false
                shift
                ;;
            --no-admin-ui)
                START_ADMIN_UI=false
                shift
                ;;
            --test-client)
                START_TEST_CLIENT=true
                shift
                ;;
            --media-dir)
                MEDIA_DIR="$2"
                shift 2
                ;;
            --help)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --no-docker       Skip starting Docker container"
                echo "  --no-api          Skip starting FastAPI backend"
                echo "  --no-admin-ui     Skip starting React admin UI"
                echo "  --test-client     Also start web test client"
                echo "  --media-dir DIR   Set media directory (default: /Volumes/media/tv)"
                echo "  --help            Show this help message"
                echo ""
                echo "Environment variables:"
                echo "  MEDIA_DIR         Media directory path (default: /Volumes/media/tv)"
                exit 0
                ;;
            *)
                echo -e "${RED}Unknown option: $1${NC}"
                echo "Use --help for usage information"
                exit 1
                ;;
        esac
    done
    
    # Start services
    if [ "$START_DOCKER" = true ]; then
        start_docker
        echo ""
    fi
    
    if [ "$START_API" = true ]; then
        start_api
        echo ""
    fi
    
    if [ "$START_ADMIN_UI" = true ]; then
        start_admin_ui
        echo ""
    fi
    
    if [ "$START_TEST_CLIENT" = true ]; then
        start_test_client
        echo ""
    fi
    
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  All services started!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "Press ${YELLOW}Ctrl+C${NC} to stop all services"
    echo ""
    
    # Wait for all background processes
    wait
}

# Run main function
main "$@"

