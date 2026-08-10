#!/bin/bash
cd "$(dirname "$0")"

echo "🤖 Installazione del Motore Robot (Playwright) in corso su disco esterno..."
echo "Questa operazione richiede qualche minuto la prima volta."

if [ ! -d "robot_env" ]; then
    python3 -m venv robot_env
fi

source robot_env/bin/activate
pip install --upgrade pip
pip install playwright
# Use a specific path for the playwright browsers so they go to the external drive too
export PLAYWRIGHT_BROWSERS_PATH="$(pwd)/pw-browsers"
playwright install chromium

echo ""
echo "✅ Installazione completata! Avvio del Robot..."
python3 send_to_stitch.py --headed --debug --animate-in-stitch
echo ""
echo "Finito! Premi Invio per chiudere."
read
