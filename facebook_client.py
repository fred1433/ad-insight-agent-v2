from __future__ import annotations
import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from pydantic import BaseModel
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.user import User
from facebook_business.adobjects.ad import Ad as FBAd
from facebook_business.exceptions import FacebookRequestError
import requests
from facebook_business.adobjects.adcreative import AdCreative
import traceback

from config import config, WINNING_ADS_SPEND_THRESHOLD, WINNING_ADS_CPA_THRESHOLD, CACHE_DURATION_HOURS, FACEBOOK_CACHE_DIR

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

# La gestion du cache est maintenant dynamique dans get_winning_ads.
# Cette constante globale n'est plus utilisée.
# CACHE_FILE = "facebook_cache.json"


def init_facebook_api(access_token: Optional[str] = None, ad_account_id: Optional[str] = None):
    """
    Initialise l'API Facebook.
    Privilégie les identifiants fournis en paramètres, sinon utilise la configuration globale.
    Force l'utilisation de la v19.0 de l'API pour éviter les erreurs de dépréciation.
    """
    final_access_token = access_token or config.facebook.access_token
    
    if not final_access_token:
        raise ValueError("Le token d'accès Facebook est manquant.")

    # On force la version de l'API à "v19.0" pour toutes les requêtes
    FacebookAdsApi.init(
        access_token=final_access_token,
        api_version="v19.0"
    )


def _fetch_insights_batch(account: AdAccount, ad_ids: List[str], 
                           date_start: str = None, date_end: str = None) -> Dict[str, Dict]:
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
            'time_range': {
                'since': date_start or (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'),
                'until': date_end or datetime.now().strftime('%Y-%m-%d')
            },
            'limit': 500
        }
        print(f"Exécution de la requête d'insights pour {len(chunk)} publicités...")
        insights_cursor = account.get_insights(params=params)
        for insight in insights_cursor:
            insights_map[insight['ad_id']] = insight
    
    return insights_map


def get_winning_ads(ad_account_id: str, 
                    min_spend: float = None, 
                    target_cpa: float = None, 
                    target_roas: float = None, 
                    date_start: str = None, 
                    date_end: str = None) -> List[Ad]:
    """
    Récupère les publicités les plus performantes en se basant sur un filtre de dépense
    et un tri par ROAS.
    1. Filtre les annonces pour ne garder que celles dépassant un seuil de dépense.
    2. Trie les annonces restantes par ROAS décroissant.
    """
    CACHE_FILE = os.path.join(FACEBOOK_CACHE_DIR, f"facebook_cache_{ad_account_id}.json")
    
    # Déterminer si les filtres sont actifs pour décider de l'utilisation du cache
    filters_active = any([min_spend is not None, target_cpa is not None, target_roas is not None, date_start is not None, date_end is not None])
    
    # --- Étape 0: Vérification du cache (uniquement si aucun filtre n'est appliqué) ---
    if not filters_active and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                cached_data = json.load(f)
            cache_time = datetime.fromtimestamp(os.path.getmtime(CACHE_FILE))
            if datetime.now() - cache_time < timedelta(hours=CACHE_DURATION_HOURS):
                print("ℹ️ Données triées par ROAS chargées depuis le cache.")
                return [Ad(**ad_data) for ad_data in cached_data]
        except (json.JSONDecodeError, TypeError) as e:
            print(f"⚠️ Erreur de lecture du cache ({e}), récupération depuis l'API.")

    if filters_active:
        print("ℹ️ Des filtres avancés sont appliqués, récupération des données depuis l'API Facebook...")
    else:
        print("ℹ️ Cache non trouvé ou expiré. Récupération des données depuis l'API Facebook...")

    try:
        # --- Étape 1 & 2: Récupération des données brutes (IDs, détails, créatives) ---
        account = AdAccount(ad_account_id)
        print("Récupération des IDs de toutes les publicités actives...")
        all_ads_paginated = account.get_ads(fields=[FBAd.Field.status, FBAd.Field.id])
        
        active_ad_ids = [ad[FBAd.Field.id] for ad in all_ads_paginated if ad[FBAd.Field.status] == 'ACTIVE']
        print(f"{len(active_ad_ids)} publicités actives trouvées.")

        if not active_ad_ids:
            return []
            
        print("\\nRécupération groupée des détails et des créatives...")
        ad_data_map = {}
        creatives_map = {}
        
        for i in range(0, len(active_ad_ids), 50):
            chunk = active_ad_ids[i:i+50]
            ads_details = FBAd.get_by_ids(
                ids=chunk,
                fields=['id', 'name', 'creative{id,image_url,video_id}']
            )
            for ad in ads_details:
                ad_data_map[ad['id']] = {'name': ad['name']}
                if 'creative' in ad:
                    creative_info = ad['creative']
                    
                    # Nous ne pouvons pas demander le champ 'video' directement sur AdCreative.
                    # Nous utilisons le video_id directement de la créative.
                    final_video_id = creative_info.get('video_id')
                    
                    print(f"DEBUG: Ad ID {ad['id']}, Creative ID: {creative_info.get('id')}, Extracted Video ID: {final_video_id}")

                    creatives_map[ad['id']] = {
                        'creative_id': creative_info.get('id'),
                        'video_id': final_video_id,
                        'image_url': creative_info.get('image_url')
                    }
        
        ad_ids_with_creatives = list(creatives_map.keys())
        if not ad_ids_with_creatives:
            print("Aucune des publicités actives n'a de créative associée.")
            return []
        
        # --- Étape 3: Récupération des insights ---
        print(f"\\nRécupération groupée des métriques pour {len(ad_ids_with_creatives)} publicités...")
        insights_map = _fetch_insights_batch(account, ad_ids_with_creatives, date_start, date_end)
        print(f"{len(insights_map)} insights récupérés.")

        # --- Étape 4: Création des objets Ad et filtrage ---
        all_ads_data = []
        print("\\nConstruction des objets de publicités...")
        
        for ad_id, ad_data in ad_data_map.items():
            creative_info = creatives_map.get(ad_id)
            insight_data = insights_map.get(ad_id)

            if not creative_info or not insight_data:
                continue

            spend = float(insight_data.get('spend', 0))
            cpa = next((float(action['value']) for action in insight_data.get('cost_per_action_type', []) if action['action_type'] == 'purchase'), 0.0)
            roas = next((float(roas_item['value']) for roas_item in insight_data.get('purchase_roas', [])), 0.0)

            # On ne garde que les annonces qui ont des données de conversion significatives
            if spend > 0 and cpa > 0 and roas > 0:
                # Appliquer les filtres s'ils sont fournis
                if min_spend is not None and spend < min_spend:
                    continue
                if target_cpa is not None and cpa > target_cpa:
                    continue
                if target_roas is not None and roas < target_roas:
                    continue

                impressions = float(insight_data.get('impressions', 0))
                video_3s_views = next((int(action['value']) for action in insight_data.get('video_play_actions', []) if action['action_type'] == 'video_view'), 0)
                thru_plays = next((int(action['value']) for action in insight_data.get('video_thruplay_watched_actions', []) if action['action_type'] == 'video_view'), 0)

                ad_obj = Ad(
                    id=ad_id,
                    name=ad_data['name'],
                    creative_id=creative_info['creative_id'],
                    video_id=creative_info.get('video_id'),
                    image_url=creative_info.get('image_url'),
                    insights=AdInsights(
                        spend=spend,
                        cpa=cpa,
                        roas=roas,
                        website_purchases=next((int(action['value']) for action in insight_data.get('actions', []) if action['action_type'] == 'purchase'), 0),
                        website_purchases_value=next((float(action['value']) for action in insight_data.get('action_values', []) if action['action_type'] == 'purchase'), 0.0),
                        cpm=float(insight_data.get('cpm', 0)),
                        unique_ctr=float(insight_data.get('unique_ctr', 0)),
                        frequency=float(insight_data.get('frequency', 0)),
                        hook_rate=(video_3s_views / impressions * 100) if impressions > 0 else 0,
                        hold_rate=(thru_plays / video_3s_views * 100) if video_3s_views > 0 else 0
                    )
                )
                all_ads_data.append(ad_obj)
        
        if not all_ads_data:
            print("Aucune publicité avec des données de conversion suffisantes n'a été trouvée.")
            return []

        # --- Étape 5: Tri final ---
        # Si aucun filtre de KPI n'est appliqué, on filtre par le seuil de dépense par défaut
        # avant de trier par ROAS.
        # Sinon, le filtrage a déjà été fait plus haut.
        if not filters_active:
             print(f"\\nFiltrage des annonces avec une dépense supérieure à {WINNING_ADS_SPEND_THRESHOLD}$...")
             qualifying_ads = [ad for ad in all_ads_data if ad.insights and ad.insights.spend > WINNING_ADS_SPEND_THRESHOLD]
        else:
             print("\\nPas de filtre de dépense par défaut car des filtres avancés sont actifs.")
             qualifying_ads = all_ads_data

        print(f"{len(qualifying_ads)} annonces qualifiées trouvées. Tri par ROAS...")
        
        # Tri des publicités qualifiées par ROAS décroissant
        sorted_ads = sorted(
            qualifying_ads, 
            key=lambda ad: ad.insights.roas if ad.insights else 0, 
            reverse=True
        )

        print(f"✅ {len(sorted_ads)} publicités triées par ROAS.")

        # --- Étape 6: Sauvegarde dans le cache (uniquement si aucun filtre n'est appliqué) ---
        if not filters_active:
            print(f"Sauvegarde des données dans le cache : {CACHE_FILE}")
            # Assurer que le répertoire du cache existe
            os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
            with open(CACHE_FILE, 'w') as f:
                # Pydantic's model_dump_json est parfait pour ça
                json_data = [ad.model_dump() for ad in sorted_ads]
                json.dump(json_data, f, indent=4)
        else:
            print("CACHE: Sauvegarde ignorée car des filtres avancés ont été utilisés.")

        return sorted_ads

    except FacebookRequestError as e:
        print(f"❌ Erreur API Facebook : {e}")
        return []
    except Exception as e:
        print(f"❌ Erreur inattendue dans get_winning_ads: {e}")
        traceback.print_exc()
        return []


def get_specific_winning_ad(ad_account_id: str, media_type: str, spend_threshold: float, cpa_threshold: float) -> Optional[Ad]:
    """
    Trouve la publicité la plus performante pour un client donné.
    """
    print(f"Recherche de la meilleure annonce de type '{media_type}'...")
    all_ads = get_winning_ads(ad_account_id)
    
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

def get_ad_by_id(ad_id: str, ad_account_id: str) -> Optional[Ad]:
    """
    Récupère une publicité spécifique par son ID en utilisant le cache des "winning ads".
    Nécessite le ad_account_id pour localiser le bon fichier de cache.
    """
    # On réutilise get_winning_ads qui contient la logique de cache.
    # On met des seuils très bas pour s'assurer de récupérer toutes les pubs
    # possibles du cache, car on ne connaît pas les seuils du rapport original.
    all_cached_ads = get_winning_ads(ad_account_id)
    
    # On cherche l'annonce spécifique dans la liste chargée.
    for ad in all_cached_ads:
        if ad.id == ad_id:
            return ad
            
    # Si non trouvée dans le cache, on tente un appel direct à l'API (fallback)
    print(f"⚠️ Annonce {ad_id} non trouvée dans le cache, tentative de récupération directe via l'API...")
    try:
        ad_object = FBAd(ad_id).api_get(fields=['id', 'name', 'creative{id,image_url,video_id}'])
        return Ad(
            id=ad_object['id'],
            name=ad_object['name'],
            creative_id=ad_object.get('creative', {}).get('id'),
            video_id=ad_object.get('creative', {}).get('video_id'),
            image_url=ad_object.get('creative', {}).get('image_url'),
        )
    except FacebookRequestError:
        print(f"❌ Échec de la récupération directe de l'annonce {ad_id}.")
    return None

def check_token_validity(token: str) -> Tuple[bool, str, Optional[List[AdAccount]]]:
    """
    Vérifie si un token d'accès Facebook est valide et peut accéder à des comptes publicitaires.
    Retourne un tuple: (est_valide, message, liste_comptes_pub)
    """
    try:
        # Initialise l'API temporairement avec le token fourni
        api = FacebookAdsApi.init(access_token=token)
        
        # Tente de récupérer les comptes publicitaires de l'utilisateur associé au token
        me = User(fbid='me', api=api)
        # On demande le nom, l'id et le statut du compte pour l'affichage et le filtrage
        ad_accounts = list(me.get_ad_accounts(fields=[
            AdAccount.Field.id,
            AdAccount.Field.name, 
            AdAccount.Field.account_id,
            AdAccount.Field.account_status
        ]))
        
        if ad_accounts:
            # On ne garde que les comptes actifs (statut 1)
            active_accounts = [acc for acc in ad_accounts if acc[AdAccount.Field.account_status] == 1]
            if active_accounts:
                return True, "Token válido y con acceso a cuentas publicitarias.", active_accounts
            else:
                return False, "Token válido, pero sin acceso a ninguna cuenta publicitaria activa.", []
        else:
            return False, "Token válido, pero sin acceso a ninguna cuenta publicitaria.", []
            
    except FacebookRequestError as e:
        # L'API a renvoyé une erreur (ex: token invalide, expiré, etc.)
        error_message = e.api_error_message()
        return False, f"Token inválido: {error_message}", None
    except Exception as e:
        # Autre erreur inattendue
        print(f"Error inesperado al validar el token: {e}")
        return False, f"Error inesperado al validar el token: {e}", None

# --- Test local (optionnel) ---
if __name__ == '__main__':
    pass 