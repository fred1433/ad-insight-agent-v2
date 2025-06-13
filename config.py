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
    access_token: Optional[str] = None # Rendu optionnel car fourni via l'UI
    app_secret: Optional[str] = None
    ad_account_id: Optional[str] = None # Rendu optionnel car fourni via l'UI

    class Config:
        env_prefix = 'FACEBOOK_'

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
    facebook: FacebookConfig = FacebookConfig()
    script: ScriptConfig = ScriptConfig()
    auth: AuthConfig = AuthConfig(
        app_access_code=os.getenv("APP_ACCESS_CODE", "").strip('\'"'),
        analysis_access_code=os.getenv("ANALYSIS_ACCESS_CODE", "").strip('\'"'),
    )

# Instance globale unique de la configuration
config = AppSettings() 