import os
import sys
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

# Charger les variables d'environnement du fichier .env
load_dotenv()

class FacebookConfig(BaseModel):
    app_id: Optional[str] = None
    app_secret: Optional[str] = None
    access_token: str
    ad_account_id: str

class AppConfig(BaseModel):
    facebook: FacebookConfig

def load_config() -> AppConfig:
    """
    Charge la configuration depuis les variables d'environnement
    et la valide avec Pydantic.
    """
    try:
        return AppConfig(
            facebook=FacebookConfig(
                app_id=os.getenv("FACEBOOK_APP_ID"),
                app_secret=os.getenv("FACEBOOK_APP_SECRET"),
                access_token=os.getenv("FACEBOOK_ACCESS_TOKEN"),
                ad_account_id=os.getenv("FACEBOOK_AD_ACCOUNT_ID"),
            )
        )
    except ValidationError as e:
        print("Erreur de configuration : des variables d'environnement sont manquantes ou invalides.")
        print("Veuillez vérifier votre fichier .env. Variables requises : FACEBOOK_ACCESS_TOKEN, FACEBOOK_AD_ACCOUNT_ID")
        print(f"\nDétails de l'erreur Pydantic:\n{e}")
        sys.exit(1) # Quitte le script si la configuration est mauvaise

# Instance globale de la configuration
config = load_config() 