import os
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from config import config

def init_facebook_api():
    """Initialise l'API Facebook avec les identifiants de configuration."""
    FacebookAdsApi.init(
        access_token=config.facebook.access_token,
        app_secret=config.facebook.app_secret,
        api_version='v19.0'
    )

def find_first_ad_with_image_efficiently():
    """
    Récupère un lot de publicités et leurs créatives en un seul appel API
    pour trouver la première publicité avec une image.
    """
    try:
        init_facebook_api()
        account = AdAccount(config.facebook.ad_account_id)
        
        print("Récupération efficace d'un lot de publicités avec leurs créatives...")
        
        # Un seul appel API qui récupère les pubs et les champs de la créative associée
        ads = account.get_ads(
            fields=[
                'id', 
                'name', 
                'creative{id,name,image_url,video_id}' # Demande imbriquée
            ], 
            params={'ad_state': 'ACTIVE', 'limit': 25} # Limite à 25 pour être prudent
        )

        print("Analyse du lot pour trouver une publicité avec image...")
        for ad in ads:
            if 'creative' in ad:
                creative = ad['creative']
                # On cherche une créative qui a une image_url mais PAS de video_id
                if creative.get('image_url') and not creative.get('video_id'):
                    print(f"\\n🎉 Annonce avec image trouvée (méthode efficace)!")
                    print(f"  - ID de l'annonce: {ad['id']}")
                    print(f"  - Nom de l'annonce: {ad['name']}")
                    print(f"  - ID de la créative: {creative['id']}")
                    print(f"  - URL de l'image: {creative['image_url']}")
                    return

        print("\\n❌ Aucune publicité avec seulement une image n'a été trouvée dans le lot testé.")

    except Exception as e:
        print(f"Une erreur est survenue : {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    find_first_ad_with_image_efficiently() 