#!/usr/bin/env bash
# ============================================================
# Model Router — setup script
# Works on macOS and Linux natively. On Windows, run this via
# Git Bash or WSL (both ship with a real bash + python).
#
# After this finishes, the next step is simply:
#   python main.py
# ============================================================
set -e

echo "=== Model Router setup ==="

# --- 1. Find a python3 interpreter ---------------------------
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo "ERROR: Python was not found on this system."
    echo "Install Python 3.9+ from https://www.python.org/downloads/ and re-run this script."
    exit 1
fi
echo "Using interpreter: $($PYTHON --version)"

# --- 2. Create a virtual environment --------------------------
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment (.venv)..."
    $PYTHON -m venv .venv
else
    echo "Virtual environment already exists, reusing it."
fi

# Activate venv (works for bash on macOS/Linux and Git Bash on Windows)
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
elif [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate
else
    echo "ERROR: Could not find the venv activation script."
    exit 1
fi

# --- 3. Install dependencies -----------------------------------
echo "Installing dependencies from requirements.txt..."
pip install --upgrade pip > /dev/null
pip install -r requirements.txt

# --- 4. Check for Ollama and pull the tiebreak model -------------
if command -v ollama &> /dev/null; then
    echo "Ollama found. Pulling the tiebreak model (phi4-mini)..."
    ollama pull phi4-mini || echo "WARNING: could not pull phi4-mini automatically — pull it manually with 'ollama pull phi4-mini'."
else
    echo "WARNING: Ollama was not found on PATH."
    echo "The router will still work, but ambiguous-case tiebreaking will silently"
    echo "fall back to the default tier until Ollama is installed and running."
    echo "Install it from https://ollama.com/download"
fi

# --- 5. Prepare the log file -------------------------------------
touch routing_log.jsonl

echo ""
echo "=== Setup complete ==="
echo "Virtual environment: .venv"
echo "Next step:"
echo "  1) Activate the environment (this script already did it for this session):"
echo "       source .venv/bin/activate      (macOS/Linux/Git Bash)"
echo "       .venv\\Scripts\\activate         (Windows cmd/PowerShell)"
echo "  2) Run:"
echo "       python main.py"
echo ""
echo "Try it now with the bundled example:"
echo "       python main.py --prompt examples/sample_prompt.md --docs examples/docs"
