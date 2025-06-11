from __future__ import annotations
import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pydantic import BaseModel
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.ad import Ad as FBAd

from config import config

# --- Définition des schémas de données (anciennement dans schemas.py) ---
class AdInsights(BaseModel):
    # Métriques existantes
    spend: float
    cpa: float
    
    # Nouvelles métriques de Pablo
    website_purchases: Optional[int] = 0
    website_purchases_value: Optional[float] = 0.0
    roas: Optional[float] = 0.0
    cpm: Optional[float] = 0.0
    unique_ctr: Optional[float] = 0.0
    frequency: Optional[float] = 0.0
    
    # Métriques calculées
    hook_rate: Optional[float] = 0.0 # (3s views / impressions)
    hold_rate: Optional[float] = 0.0 # (thru_plays / 3s views)

class Ad(BaseModel):
    id: str
    name: str
    creative_id: Optional[str] = None
    video_id: Optional[str] = None
    image_url: Optional[str] = None
    insights: Optional[AdInsights] = None

# --- Configuration du Cache ---
CACHE_FILE = "facebook_cache.json"
CACHE_DURATION_HOURS = 24
# -----------------------------

# Constantes pour les règles métier
WINNING_ADS_SPEND_THRESHOLD = 3000.0
WINNING_ADS_CPA_THRESHOLD = 600.0


def init_facebook_api():
    """Initialise l'API Facebook avec les identifiants de configuration."""
    init_params = {
        'access_token': config.facebook.access_token,
    }
    if config.facebook.app_secret:
        init_params['app_secret'] = config.facebook.app_secret
    FacebookAdsApi.init(**init_params)


def _fetch_creatives_batch(ad_ids: List[str]) -> Dict[str, Dict[str, str]]:
    """
    Récupère creative_id, video_id et image_url pour une liste d'ad_ids
    en utilisant un appel API groupé efficace.
    """
    results_map = {}
    api = FacebookAdsApi.get_default_api()
    
    # Découpe la liste d'IDs en morceaux de 50 pour le traitement par lots
    for i in range(0, len(ad_ids), 50):
        chunk = ad_ids[i:i+50]
        
        # Récupération en une seule fois
        ads = AdAccount(config.facebook.ad_account_id).get_ads(
            fields=[
                'id', 
                'creative{id,name,image_url,video_id}'
            ], 
            params={'ad_id__in': chunk}
        )

        for ad in ads:
            if 'creative' in ad:
                creative = ad['creative']
                results_map[ad['id']] = {
                    'creative_id': creative.get('id'),
                    'video_id': creative.get('video_id'),
                    'image_url': creative.get('image_url')
                }
        
    return results_map


def _fetch_insights_batch(account: AdAccount, ad_ids: List[str]) -> Dict[str, Dict]:
    """
    Récupère les insights pour une liste d'ad_ids en utilisant un filtre
    sur le compte publicitaire, ce qui est une forme de batching efficace.
    """
    insights_map = {}
    insight_fields = [
        'ad_id', 
        'spend', 
        'cost_per_action_type',
        'impressions',
        'cpm',
        'unique_ctr',
        'frequency',
        'purchase_roas',
        'actions',
        'action_values',
        'video_play_actions', # Base pour le "Hook Rate" (vues de 3s)
        'video_thruplay_watched_actions' # Base pour le "Hold Rate"
    ]

    # Découpe les IDs en morceaux de 100 pour le filtre 'IN'
    for i in range(0, len(ad_ids), 100):
        chunk = ad_ids[i:i+100]
        params = {
            'level': 'ad',
            'fields': insight_fields,
            'filtering': [{'field': 'ad.id', 'operator': 'IN', 'value': chunk}],
            'time_range': {'since': (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'), 'until': datetime.now().strftime('%Y-%m-%d')},
            'limit': 500
        }
        print(f"Exécution de la requête d'insights pour {len(chunk)} publicités...")
        insights_cursor = account.get_insights(params=params)
        for insight in insights_cursor:
            insights_map[insight['ad_id']] = insight
    
    return insights_map


def get_winning_ads(spend_threshold=WINNING_ADS_SPEND_THRESHOLD, cpa_threshold=WINNING_ADS_CPA_THRESHOLD) -> List[Ad]:
    """
    Récupère les publicités gagnantes en utilisant des appels par lots pour
    une meilleure performance et un système de cache pour éviter les appels répétés.
    Les seuils peuvent être surchargés.
    """
    # --- Étape 1: Vérification du cache ---
    if os.path.exists(CACHE_FILE):
        file_mod_time = datetime.fromtimestamp(os.path.getmtime(CACHE_FILE))
        if datetime.now() - file_mod_time < timedelta(hours=CACHE_DURATION_HOURS):
            print(f"✅ Chargement des données depuis le cache récent : {CACHE_FILE}")
            with open(CACHE_FILE, 'r') as f:
                cached_data = json.load(f)
            # Reconstruit les objets Pydantic depuis le dictionnaire en cache
            return [Ad(**ad) for ad in cached_data]

    print("ℹ️ Cache non trouvé ou expiré. Récupération des données depuis l'API Facebook...")
    
    winning_ads = []
    try:
        init_facebook_api()
        account = AdAccount(config.facebook.ad_account_id)

        # --- Étape 2: Récupération des données par lots ---
        print("Récupération de toutes les publicités actives...")
        ad_fields = ['id', 'name']
        params = {'ad_state': 'ACTIVE', 'limit': 1000}
        all_ads_raw = list(account.get_ads(fields=ad_fields, params=params))
        
        if not all_ads_raw:
            print("Aucune publicité active trouvée.")
            return []
            
        ad_data_map = {ad['id']: ad for ad in all_ads_raw}
        ad_ids = list(ad_data_map.keys())
        print(f"{len(ad_ids)} publicités actives trouvées.")

        print("\nRécupération groupée des créatives (vidéo et image)...")
        creatives_map = _fetch_creatives_batch(ad_ids)
        
        ad_ids_with_creatives = list(creatives_map.keys())
        if not ad_ids_with_creatives:
            print("Aucune publicité avec une créative (vidéo ou image) trouvée.")
            return []
        print(f"{len(ad_ids_with_creatives)} publicités avec une créative trouvées.")
        
        print("\nRécupération groupée des métriques (insights)...")
        insights_map = _fetch_insights_batch(account, ad_ids_with_creatives)
        print(f"{len(insights_map)} insights récupérés.")

        # --- Étape 3: Combinaison des données et filtrage ---
        print("\nFiltrage des publicités gagnantes...")
        
        for ad_id, ad_data in ad_data_map.items():
            creative_info = creatives_map.get(ad_id)
            insight_data = insights_map.get(ad_id)

            if not creative_info or not insight_data:
                continue

            # --- Extraction des métriques de base ---
            spend = float(insight_data.get('spend', 0))
            cpm = float(insight_data.get('cpm', 0))
            unique_ctr = float(insight_data.get('unique_ctr', 0))
            frequency = float(insight_data.get('frequency', 0))
            roas = float(insight_data.get('purchase_roas', [{}])[0].get('value', 0.0))
            impressions = float(insight_data.get('impressions', 0))

            # --- Extraction des actions spécifiques ---
            cpa = 0.0
            website_purchases = 0
            website_purchases_value = 0.0
            
            if 'cost_per_action_type' in insight_data:
                for action in insight_data['cost_per_action_type']:
                    if action['action_type'] == 'purchase':
                        cpa = float(action['value'])
                        break # On a trouvé le CPA, on sort de la boucle
            
            if 'actions' in insight_data:
                for action in insight_data['actions']:
                    if action['action_type'] == 'purchase':
                        website_purchases = int(action['value'])
                        break
            
            if 'action_values' in insight_data:
                for action in insight_data['action_values']:
                    if action['action_type'] == 'purchase':
                        website_purchases_value = float(action['value'])
                        break
            
            # --- Calcul des métriques vidéo personnalisées ---
            video_3s_views = 0
            if 'video_play_actions' in insight_data:
                 for action in insight_data['video_play_actions']:
                    if action['action_type'] == 'video_view':
                        video_3s_views = int(action['value'])
                        break
            
            thru_plays = 0
            if 'video_thruplay_watched_actions' in insight_data:
                for action in insight_data['video_thruplay_watched_actions']:
                    if action['action_type'] == 'video_view':
                        thru_plays = int(action['value'])
                        break

            hook_rate = (video_3s_views / impressions * 100) if impressions > 0 else 0
            hold_rate = (thru_plays / video_3s_views * 100) if video_3s_views > 0 else 0


            # Filtrage des publicités gagnantes basé sur les KPIs définis
            if spend >= spend_threshold and cpa <= cpa_threshold and cpa > 0:
                ad_obj = Ad(
                    id=ad_id,
                    name=ad_data['name'],
                    creative_id=creative_info['creative_id'],
                    video_id=creative_info.get('video_id'),
                    image_url=creative_info.get('image_url'),
                    insights=AdInsights(
                        spend=spend, 
                        cpa=cpa,
                        website_purchases=website_purchases,
                        website_purchases_value=website_purchases_value,
                        roas=roas,
                        cpm=cpm,
                        unique_ctr=unique_ctr,
                        frequency=frequency,
                        hook_rate=hook_rate,
                        hold_rate=hold_rate
                    )
                )
                winning_ads.append(ad_obj)
        
        # Triage des publicités gagnantes pour avoir la meilleure en premier (CPA le plus bas)
        winning_ads.sort(key=lambda ad: ad.insights.cpa)
        
        print(f"✅ {len(winning_ads)} publicités gagnantes trouvées et triées par CPA.")

    except Exception as e:
        print(f"❌ Une erreur est survenue lors de la récupération des publicités : {e}")
    
    finally:
        # --- Étape 4: Sauvegarde dans le cache QUOI QU'IL ARRIVE ---
        if winning_ads:
            try:
                ads_to_cache = [ad.model_dump() for ad in winning_ads]
                with open(CACHE_FILE, 'w') as f:
                    json.dump(ads_to_cache, f, indent=4)
                print(f"💾 Données sauvegardées dans le cache : {CACHE_FILE}")
            except Exception as cache_e:
                print(f"⚠️ Erreur lors de la sauvegarde du cache : {cache_e}")

    return winning_ads 

def get_specific_winning_ad(media_type: str, spend_threshold: float, cpa_threshold: float) -> Optional[Ad]:
    """
    Récupère la meilleure annonce gagnante pour un type de média spécifique ('video' ou 'image').
    Se base sur le cache pour la rapidité.
    """
    print(f"Recherche de la meilleure annonce de type '{media_type}'...")
    all_ads = get_winning_ads(spend_threshold, cpa_threshold)
    
    if not all_ads:
        return None

    if media_type == 'video':
        # Filtre pour les annonces qui ont un video_id
        candidate_ads = [ad for ad in all_ads if ad.video_id]
    elif media_type == 'image':
        # Filtre pour les annonces qui ont une image_url
        candidate_ads = [ad for ad in all_ads if ad.image_url]
    else:
        return None
    
    if not candidate_ads:
        print(f"Aucune annonce gagnante trouvée pour le type '{media_type}'.")
        return None
    
    # La liste est déjà triée par CPA, donc le premier élément est le meilleur.
    best_ad = candidate_ads[0]
    print(f"Meilleure annonce de type '{media_type}' trouvée : {best_ad.name} (CPA: {best_ad.insights.cpa})")
    return best_ad

def get_ad_by_id(ad_id: str) -> Optional[Ad]:
    """
    Récupère une annonce spécifique par son ID en utilisant le cache.
    """
    if not ad_id:
        return None
        
    # On charge toutes les pubs depuis le cache (ou l'API si le cache est vide)
    all_ads = get_winning_ads()
    
    # On cherche l'annonce correspondante
    for ad in all_ads:
        if ad.id == ad_id:
            return ad
            
    # Si non trouvée dans les "winning ads", on pourrait avoir besoin de faire un fetch spécifique
    # mais pour l'instant, on se contente de ce qui est dans le cache.
    print(f"Avertissement: Annonce avec ID {ad_id} non trouvée dans le cache des 'winning ads'.")
    return None 