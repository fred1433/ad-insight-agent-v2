#!/bin/bash
# Script pour initialiser l'environnement de développement

echo "--- Création de l'environnement virtuel ---"
python3 -m venv .venv

echo "--- Activation de l'environnement ---"
source .venv/bin/activate

echo "--- Mise à jour de pip ---"
pip install --upgrade pip

echo "--- Installation des dépendances depuis requirements.txt ---"
pip install -r requirements.txt

echo "--- ✅ Environnement prêt ! ---" 