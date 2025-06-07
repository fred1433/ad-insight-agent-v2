from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from typing import List

from config import config
from schemas import Ad

def init_facebook_api():
    """Initialise l'API Facebook avec les identifiants de configuration."""
    init_params = {
        'access_token': config.facebook.access_token,
        'crash_log': False
    }
    if config.facebook.app_id:
        init_params['app_id'] = config.facebook.app_id
    if config.facebook.app_secret:
        init_params['app_secret'] = config.facebook.app_secret

    FacebookAdsApi.init(**init_params)

def get_ads() -> List[Ad]:
    """
    Récupère toutes les publicités actives d'un compte publicitaire.
    """
    try:
        init_facebook_api()
        ad_account = AdAccount(config.facebook.ad_account_id)
        
        # Définir les champs que nous voulons récupérer
        fields = [
            'id',
            'name',
            'creative{video_id}' # On re-tente la syntaxe imbriquée
        ]
        
        # Paramètres pour ne récupérer que les publicités actives
        params = {
            'effective_status': ['ACTIVE'],
        }
        
        ads = ad_account.get_ads(fields=fields, params=params)
        
        # Transformation des résultats en objets Pydantic
        ad_list = []
        for ad in ads:
            creative = ad.get('creative')
            ad_list.append(Ad(
                id=ad['id'],
                name=ad['name'],
                creative_id=creative.get('id') if creative else None,
                video_id=creative.get('video_id') if creative else None
            ))
            
        return ad_list

    except Exception as e:
        print(f"Erreur lors de la récupération des publicités Facebook : {e}")
        return [] 