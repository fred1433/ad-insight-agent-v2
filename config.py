import os
from pydantic_settings import BaseSettings
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel

# Charger les variables d'environnement depuis .env à la racine du projet
project_root = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(project_root, '.env'))

# --- Constantes de l'application ---
# Ces valeurs définissent la logique métier pour identifier une "winning ad"
WINNING_ADS_SPEND_THRESHOLD = 3000.0  # Dépense minimale pour être considérée
WINNING_ADS_CPA_THRESHOLD = 600.0     # Coût par acquisition maximal
CACHE_DURATION_HOURS = 24             # Durée de validité du cache en heures
FACEBOOK_CACHE_DIR = "data/facebook_cache" # Dossier pour les caches par compte

class FacebookConfig(BaseSettings):
    access_token: str
    app_secret: Optional[str] = None # Rendu optionnel pour plus de flexibilité
    ad_account_id: str

    class Config:
        env_prefix = 'FACEBOOK_'

class GoogleConfig(BaseModel):
    project_id: str = os.getenv("GOOGLE_PROJECT_ID")
    gcs_bucket_name: str = os.getenv("GCS_BUCKET_NAME")
    gvi_language_code: str = "es-MX" # Code langue pour l'analyse GVI

class ScriptConfig(BaseModel):
    """Configuration générale du script."""
    max_ads_per_run: int = 1 # Limite le nombre de pubs à traiter, -1 pour infini

class AuthConfig(BaseModel):
    app_access_code: str
    analysis_access_code: str

# Classe principale pour contenir toutes les configurations
# Pydantic-settings est assez intelligent pour router les variables
# en se basant sur les préfixes définis dans chaque sous-classe.
class AppSettings(BaseSettings):
    # Les champs ici peuvent être utilisés pour des variables sans préfixe
    # ex: DEBUG: bool = False
    
    # On compose la configuration avec nos classes spécifiques
    facebook: FacebookConfig = FacebookConfig(
        access_token=os.getenv("FACEBOOK_ACCESS_TOKEN"),
        app_secret=os.getenv("FACEBOOK_APP_SECRET"),
        ad_account_id=os.getenv("FACEBOOK_AD_ACCOUNT_ID"),
    )
    google: GoogleConfig = GoogleConfig()
    script: ScriptConfig = ScriptConfig()
    auth: AuthConfig = AuthConfig(
        app_access_code=os.getenv("APP_ACCESS_CODE"),
        analysis_access_code=os.getenv("ANALYSIS_ACCESS_CODE"),
    )

# Instance globale unique de la configuration
config = AppSettings() 