#!/usr/bin/env bash
set -e

echo "Checking system dependencies..."
MISSING=()
command -v ffmpeg  >/dev/null 2>&1 || MISSING+=("ffmpeg")
command -v gs      >/dev/null 2>&1 || MISSING+=("ghostscript")

if [ ${#MISSING[@]} -ne 0 ]; then
    echo "Missing system packages: ${MISSING[*]}"
    echo "Install with:  sudo apt-get install -y ${MISSING[*]}"
    exit 1
fi
echo "All system dependencies found."

# Create a virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "Installing Python dependencies..."
pip install -q -r requirements.txt

echo ""
echo "========================================="
echo "  Starting OmniTool on localhost:5000"
echo "========================================="
echo ""

python3 app.py
