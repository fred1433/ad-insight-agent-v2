# Étape 1: Utiliser une image Python officielle et légère
FROM python:3.11-slim

# Étape 2: Définir le répertoire de travail dans le conteneur
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Install system dependencies for Chromium (for Selenium on ARM/M1)
RUN apt-get update && apt-get install -y chromium chromium-driver sqlite3 --no-install-recommends

# Étape 3: Copier le fichier des dépendances et les installer
# Copier uniquement ce fichier d'abord permet de profiter du cache de Docker
# si les dépendances ne changent pas entre les builds.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Étape 4: Copier tout le reste du code de l'application
COPY . .

# Variables d'environnement pour s'assurer que Python affiche les logs immédiatement
ENV PYTHONUNBUFFERED=1

# Exposition du port (sera surchargé par Gunicorn ou Flask)
EXPOSE 10000

# Commande par défaut pour la production (utilisée par Render)
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "app:app"] 