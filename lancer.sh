#!/bin/bash
echo "═══════════════════════════════════════════"
echo "   NEXORE Spark V3.0 — IFT Madagascar"
echo "═══════════════════════════════════════════"
cd "$(dirname "$0")"

# Create venv if not exists
if [ ! -d "venv" ]; then
    echo "📦 Création de l'environnement virtuel..."
    python3 -m venv venv
fi

# Activate
source venv/bin/activate

# Install deps
echo "📥 Installation des dépendances..."
pip install -q -r requirements.txt

# Create uploads dir
mkdir -p static/uploads

# Launch
echo ""
echo "🚀 Démarrage sur http://localhost:5000"
echo "   Admin : direction@ift-mada.mg"
echo "   MDP   : admin2025"
echo ""
python3 app.py
