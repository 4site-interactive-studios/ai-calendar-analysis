#!/usr/bin/env bash
set -e

# 4Site Calendar Analytics - Setup & Run Script
# Detects your Python, installs everything, and launches the tool.

echo ""
echo "  4Site Calendar Analytics - Setup"
echo "  ================================"
echo ""

# Find Python 3
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" --version 2>&1)
        if echo "$version" | grep -q "Python 3"; then
            PYTHON="$cmd"
            echo "  Found: $version ($cmd)"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "  ERROR: Python 3 not found."
    echo ""
    echo "  Install Python 3:"
    echo "    macOS:   brew install python3"
    echo "    Ubuntu:  sudo apt install python3 python3-venv python3-pip"
    echo "    Windows: https://www.python.org/downloads/"
    exit 1
fi

# Get script directory (works even if called from elsewhere)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Create virtual environment if needed
if [ ! -d "venv" ]; then
    echo "  Creating virtual environment..."
    "$PYTHON" -m venv venv
fi

# Activate
source venv/bin/activate
echo "  Virtual environment activated."

# Install/update dependencies
echo "  Installing dependencies..."
if command -v uv &>/dev/null; then
    uv pip install -r requirements.txt --quiet
else
    pip install -r requirements.txt --quiet
fi
echo "  Dependencies installed."

# Copy config if needed
if [ ! -f "config.yaml" ]; then
    cp config.example.yaml config.yaml
    echo "  Created config.yaml from example (edit to add your client domains)."
fi

echo ""
echo "  Setup complete!"
echo ""

# Determine what to run
MODE="${1:-menu}"

if [ "$MODE" = "cli" ]; then
    shift
    echo "  Running CLI..."
    echo ""
    python analyze.py "$@"

elif [ "$MODE" = "web" ]; then
    PORT="${2:-5000}"
    echo "  Starting web dashboard at http://127.0.0.1:$PORT"
    echo "  Press Ctrl+C to stop."
    echo ""
    python web_server.py --port "$PORT"

elif [ "$MODE" = "demo" ]; then
    echo "  Running demo with sample data..."
    echo ""
    python analyze.py --ical-file sample_calendar.ics --start 2025-01-01 --end 2025-12-31

else
    echo "  Usage:"
    echo ""
    echo "    ./run.sh demo                          # Run with sample data"
    echo "    ./run.sh web                            # Start web dashboard"
    echo "    ./run.sh cli --ical-file calendar.ics   # Analyze an .ics file"
    echo "    ./run.sh cli --ical-url \"https://...\"   # Analyze an iCal URL"
    echo ""
    echo "  Quick test:"
    echo "    ./run.sh demo"
    echo ""
fi
