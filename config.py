import os
from pydantic_settings import BaseSettings
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel

# Charger les variables d'environnement depuis .env à la racine du projet
project_root = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(project_root, '.env'))

# Définir le chemin vers le fichier de clés et l'assigner à la variable d'environnement
credentials_path = os.path.join(project_root, 'google-cloud-credentials.json')
if os.path.exists(credentials_path):
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
else:
    print("⚠️  AVERTISSEMENT: Le fichier 'google-cloud-credentials.json' n'a pas été trouvé.")

class FacebookConfig(BaseSettings):
    access_token: str
    app_secret: Optional[str] = None # Rendu optionnel pour plus de flexibilité
    ad_account_id: str

    class Config:
        env_prefix = 'FACEBOOK_'

class GoogleConfig(BaseModel):
    project_id: str = os.getenv("GOOGLE_PROJECT_ID")
    gcs_bucket_name: str = os.getenv("GCS_BUCKET_NAME")

class ScriptConfig(BaseModel):
    """Configuration générale du script."""
    max_ads_per_run: int = 1 # Limite le nombre de pubs à traiter, -1 pour infini

# Classe principale pour contenir toutes les configurations
# Pydantic-settings est assez intelligent pour router les variables
# en se basant sur les préfixes définis dans chaque sous-classe.
class AppSettings(BaseSettings):
    # Les champs ici peuvent être utilisés pour des variables sans préfixe
    # ex: DEBUG: bool = False
    
    # On compose la configuration avec nos classes spécifiques
    facebook: FacebookConfig = FacebookConfig()
    google: GoogleConfig = GoogleConfig()
    script: ScriptConfig = ScriptConfig()

# Instance globale unique de la configuration
config = AppSettings() 