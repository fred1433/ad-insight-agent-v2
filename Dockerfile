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

# Étape 5: Commande pour lancer l'application avec Gunicorn
# Render définit automatiquement la variable d'environnement $PORT.
# Nous lions Gunicorn à l'adresse 0.0.0.0 pour qu'il soit accessible de l'extérieur du conteneur.
# Le format 'app:app' signifie "dans le fichier app.py, utilise l'objet app (Flask)".
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--timeout", "90", "app:app"] 