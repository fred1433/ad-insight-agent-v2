from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.ad import Ad as FBAd
from facebook_business.adobjects.advideo import AdVideo
from typing import List, Optional

from config import config
from schemas import Ad, AdInsights

# Constantes pour les règles métier
WINNING_ADS_SPEND_THRESHOLD = 3000.0
WINNING_ADS_CPA_THRESHOLD = 600.0

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

def get_video_download_url(video_id: str) -> Optional[str]:
    """Récupère l'URL de téléchargement direct pour une vidéo donnée."""
    try:
        # On utilise api_get() pour demander directement le champ 'source' de l'objet vidéo.
        # C'est une approche plus directe et robuste que get_previews().
        video = AdVideo(video_id).api_get(fields=['source'])
        return video.get('source')
    except Exception as e:
        print(f"Erreur lors de la récupération de l'URL de la vidéo {video_id}: {e}")
        # On log l'erreur pour voir si c'est encore un problème de permission
        # ou autre chose.
        return None

def get_winning_ads() -> List[Ad]:
    """
    Récupère les publicités, leurs métriques, les filtre pour ne garder
    que les "gagnantes" et retourne une liste complète.
    """
    try:
        init_facebook_api()
        ad_account = AdAccount(config.facebook.ad_account_id)
        
        # 1. Récupérer les publicités de base
        base_ads = ad_account.get_ads(
            fields=['id', 'name', 'creative{video_id}'],
            params={'effective_status': ['ACTIVE']}
        )
        
        winning_ads = []
        for ad_data in base_ads:
            ad_id = ad_data['id']
            fb_ad = FBAd(ad_id)

            # 2. Pour chaque pub, récupérer ses métriques (insights)
            insights_data = fb_ad.get_insights(
                fields=[
                    'spend',
                    'cpm',
                    'unique_ctr',
                    'frequency',
                    'purchase_roas',
                    'cost_per_action_type',
                    'actions',
                    'action_values',
                    'video_play_actions', # Pour le Hold Rate
                    'video_p100_watched_actions', # Pour le Hold Rate
                    'video_thruplay_watched_actions', # Base alternative pour le Hook Rate
                    'impressions' # Pour le Hook Rate
                ]
            )

            if not insights_data:
                continue # Passer si pas de métriques

            insights = insights_data[0] # Les insights sont une liste

            # Extraire le coût par achat et la valeur des achats
            cpa = 0.0
            for item in insights.get('cost_per_action_type', []):
                if item['action_type'] == 'purchase':
                    cpa = float(item['value'])
                    break
            
            purchases = 0
            for item in insights.get('actions', []):
                if item['action_type'] == 'purchase':
                    purchases = int(item['value'])
                    break

            purchases_value = 0.0
            for item in insights.get('action_values', []):
                if item['action_type'] == 'purchase':
                    purchases_value = float(item['value'])
                    break
            
            # Calculer les métriques personnalisées
            impressions = float(insights.get('impressions', 0))
            video_plays = 0
            for item in insights.get('video_play_actions', []):
                if item['action_type'] == 'video_view':
                    video_plays = float(item['value'])
                    break
            
            video_p100 = 0
            for item in insights.get('video_p100_watched_actions', []):
                if item['action_type'] == 'video_view':
                    video_p100 = float(item['value'])
                    break

            video_thruplay = 0
            for item in insights.get('video_thruplay_watched_actions', []):
                if item['action_type'] == 'video_view':
                    video_thruplay = float(item['value'])
                    break
            
            hook_rate = (video_thruplay / impressions) if impressions > 0 else 0.0
            hold_rate = (video_p100 / video_plays) if video_plays > 0 else 0.0

            # 3. Appliquer le filtre "gagnante"
            spend = float(insights.get('spend', 0.0))
            if spend >= WINNING_ADS_SPEND_THRESHOLD and cpa <= WINNING_ADS_CPA_THRESHOLD:
                
                creative = ad_data.get('creative')
                ad_pydantic = Ad(
                    id=ad_data['id'],
                    name=ad_data['name'],
                    creative_id=creative.get('id') if creative else None,
                    video_id=creative.get('video_id') if creative else None,
                    insights=AdInsights(
                        spend=spend,
                        cpa=cpa,
                        website_purchases=purchases,
                        website_purchases_value=purchases_value,
                        roas=float(insights.get('purchase_roas', [{}])[0].get('value', 0.0)),
                        cpm=float(insights.get('cpm', 0.0)),
                        unique_ctr=float(insights.get('unique_ctr', 0.0)),
                        frequency=float(insights.get('frequency', 0.0)),
                        hook_rate=hook_rate,
                        hold_rate=hold_rate
                    )
                )
                winning_ads.append(ad_pydantic)
                
        return winning_ads

    except Exception as e:
        print(f"Erreur lors de la récupération des publicités Facebook : {e}")
        return [] 