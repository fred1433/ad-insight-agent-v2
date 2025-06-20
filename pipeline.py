import os
import base64
import re
import json
import threading
import traceback
from datetime import datetime
import pytz
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import shutil
from typing import Tuple

import facebook_client
from media_downloader import MediaDownloader
import gemini_analyzer
import image_generator
import markdown
import database

# On charge les variables d'environnement (comme les clés API et les prix)
load_dotenv()

# --- CONFIGURATION DES COÛTS (chargée depuis les variables d'environnement) ---
# Tarifs basés sur Gemini 1.5 Pro et Imagen 3 (vérifier les tarifs officiels)
# Prix par MILLION de tokens
# On nettoie la valeur des guillemets potentiels avant de la convertir en float
GEMINI_INPUT_PRICE_PER_MILLION_TOKENS = float(os.getenv("GEMINI_INPUT_PRICE_PER_MILLION_TOKENS", "2.50").strip('\'"'))
GEMINI_OUTPUT_PRICE_PER_MILLION_TOKENS = float(os.getenv("GEMINI_OUTPUT_PRICE_PER_MILLION_TOKENS", "7.50").strip('\'"'))
IMAGEN_PRICE_PER_IMAGE = float(os.getenv("IMAGEN_PRICE_PER_IMAGE", "0.03").strip('\'"'))

# Le nom du fichier de cache d'analyse est maintenant dynamique et géré dans le pipeline.
# CACHE_FILE = "analysis_cache.json" # Ancienne constante globale supprimée

ANALYSIS_CACHE_DIR = "data/analysis_cache"

def load_cache(cache_path: str):
    """Charge les données depuis un fichier de cache JSON."""
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)  # <-- Indentation ici
        except (json.JSONDecodeError, IOError):
            return {}  # Retourne un cache vide en cas d'erreur
    return {}

def save_cache(cache_path: str, cache_data):
    """Sauvegarde les données dans un fichier de cache JSON."""
    try:
        # S'assure que le répertoire de cache existe
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=4)  # <-- Indentation ici
    except IOError as e:
        print(f"Erreur lors de la sauvegarde du cache sur {cache_path}: {e}")

def calculate_analysis_cost(usage_metadata: dict) -> float:
    """Calcule le coût d'un appel à l'API Gemini à partir de ses métadonnées d'utilisation."""
    if not usage_metadata or not isinstance(usage_metadata, dict):
         # L'API peut retourner un objet, pas un dict, on convertit si besoin
        try:
            usage_metadata = {
                'prompt_token_count': usage_metadata.prompt_token_count,
                'candidates_token_count': usage_metadata.candidates_token_count
            }
        except AttributeError:
            return 0.0

    input_tokens = usage_metadata.get('prompt_token_count', 0)
    output_tokens = usage_metadata.get('candidates_token_count', 0)

    input_cost = (input_tokens / 1_000_000) * GEMINI_INPUT_PRICE_PER_MILLION_TOKENS
    output_cost = (output_tokens / 1_000_000) * GEMINI_OUTPUT_PRICE_PER_MILLION_TOKENS

    return input_cost + output_cost

def generate_report_fragments(analyzed_ad_data) -> Tuple[str, str]:
    """Génère les fragments HTML pour l'analyse et les concepts."""
    
    analysis_html = markdown.markdown(analyzed_ad_data['analysis_text'], extensions=['tables'])
    script_html_raw = markdown.markdown(analyzed_ad_data['script_text'], extensions=['tables'])
    media_type = analyzed_ad_data['media_type']
    generated_image_paths = analyzed_ad_data.get('generated_image_paths', [])

    # La logique complexe d'injection des images générées dans le HTML du script est conservée
    soup = BeautifulSoup(script_html_raw, 'html.parser')
    table = soup.find('table')
    if table and generated_image_paths:
        # Simplification: on ajoute une colonne pour les images générées
        # Note: la logique plus complexe pour les vidéos avec rowspan est omise pour la clarté de cette refonte
        header = table.find('tr')
        if header:
            new_th = soup.new_tag('th')
            new_th.string = 'Visualisation Concept'
            header.insert(1, new_th) # Insérer après le "Hook"

        rows = table.find_all('tr')
        for i, row in enumerate(rows[1:]): # Ignorer l'en-tête
            if i < len(generated_image_paths):
                new_td = soup.new_tag('td')
                try:
                    img_path = generated_image_paths[i]
                    with open(img_path, "rb") as img_file:
                        img_b64 = base64.b64encode(img_file.read()).decode('utf-8')
                    img_ext = os.path.splitext(img_path)[1].lower().replace('.', '')
                    img_tag = soup.new_tag('img', src=f"data:image/{img_ext};base64,{img_b64}", alt="Concept IA", style="max-width:200px;")
                    new_td.append(img_tag)
                except (IOError, IndexError):
                    pass # Laisser la cellule vide en cas d'erreur
                
                # Insérer la nouvelle cellule
                data_cells = row.find_all('td')
                if data_cells:
                    data_cells[0].insert_after(new_td)

    script_html_final = str(soup)
    
    return analysis_html, script_html_final

def create_image_grid_html(image_paths):
    """Crée le HTML pour une grille d'images."""
    if not image_paths:
        return ""
    
    grid_html = "<h4>Visualización de Conceptos (IA Generativa)</h4><div class='generated-images-grid'>"
    for img_path in image_paths:
        try:
            with open(img_path, "rb") as img_file:
                img_b64 = base64.b64encode(img_file.read()).decode('utf-8')
            img_ext = os.path.splitext(img_path)[1].lower().replace('.', '')
            grid_html += f'<img src="data:image/{img_ext};base64,{img_b64}" alt="Concepto generado por IA">'
        except Exception:
            pass
    grid_html += "</div>"
    return grid_html

def _perform_single_ad_analysis(ad: facebook_client.Ad, cache: dict) -> dict:
    """
    Exécute le pipeline d'analyse complet (téléchargement, analyse, génération) pour une seule publicité.
    Utilise et met à jour un dictionnaire de cache fourni.
    Retourne un dictionnaire contenant toutes les données et les coûts de l'analyse.
    """
    print(f"--- Début de l'analyse pour l'annonce : {ad.name} ({ad.id}) ---")
    
    cost_analysis = 0.0
    cost_generation = 0.0
    
    if ad.id in cache and all(os.path.exists(p) for p in cache[ad.id].get('generated_image_paths', [])):
         print(f"Annonce trouvée dans le cache, on utilise les données.")
         analyzed_ad_data = cache[ad.id]
         cost_analysis = analyzed_ad_data.get('cost_analysis', 0.0)
         cost_generation = analyzed_ad_data.get('cost_generation', 0.0)

         print("Re-téléchargement du média au cas où le chemin temporaire serait invalide...")
         downloader = MediaDownloader()
         local_media_path = None
         if ad.video_id:
             local_media_path = downloader.download_video_locally(ad.video_id, ad.id)
         elif ad.image_url:
             local_media_path = downloader.download_image_locally(ad.image_url, ad.id)
         
         if not local_media_path:
             raise Exception("Échec du re-téléchargement du média.")
             
         analyzed_ad_data['media_path'] = local_media_path
    else:
        print("Analyse complète de l'annonce requise...")
        downloader = MediaDownloader()
        local_media_path, media_type = (None, None)
        
        if ad.video_id:
            media_type = 'video'
            local_media_path = downloader.download_video_locally(ad.video_id, ad.id)
        elif ad.image_url:
            media_type = 'image'
            local_media_path = downloader.download_image_locally(ad.image_url, ad.id)

        if not local_media_path:
            raise Exception("Échec du téléchargement du média.")

        full_response_text, usage_metadata = "", {}
        model_used, is_fallback = None, False
        if media_type == 'video':
            video_analysis_result = gemini_analyzer.analyze_video(local_media_path, ad)
            full_response_text = video_analysis_result.get("analysis_text", "")
            usage_metadata = video_analysis_result.get("usage_metadata", {})
            model_used = video_analysis_result.get("model_used", "N/A")
            is_fallback = video_analysis_result.get("is_fallback", False)
        else: # image
            full_response_text, usage_metadata = gemini_analyzer.analyze_image(local_media_path, ad)
            model_used = gemini_analyzer.GEMINI_MODEL_NAME
            is_fallback = False

        cost_analysis = calculate_analysis_cost(usage_metadata)
        print(f"💰 Coût de l'analyse Gemini estimé : ${cost_analysis:.4f}")
        
        analysis_part, script_part = (full_response_text.split("---", 1) + [""])[:2]
        
        print("Génération des images concepts... (Désactivée)")
        generated_image_paths = []
        images_generated_count = 0
        
        cost_generation = images_generated_count * IMAGEN_PRICE_PER_IMAGE
        print(f"💰 Coût de la génération d'images estimé : ${cost_generation:.4f}")

        analyzed_ad_data = {
            "ad": ad.model_dump(),
            "media_type": media_type,
            "media_path": local_media_path,
            "analysis_text": analysis_part.strip(),
            "script_text": script_part.strip(),
            "generated_image_paths": generated_image_paths,
            "cost_analysis": cost_analysis,
            "cost_generation": cost_generation,
            "model_used": model_used,
            "is_fallback": is_fallback
        }
        cache[ad.id] = analyzed_ad_data
    
    destination_folder = os.path.join('data', 'storage')
    os.makedirs(destination_folder, exist_ok=True)
    
    final_media_path = None
    if analyzed_ad_data.get('media_path') and os.path.exists(analyzed_ad_data['media_path']):
        filename = os.path.basename(analyzed_ad_data['media_path'])
        final_media_path = os.path.join(destination_folder, filename)
        shutil.move(analyzed_ad_data['media_path'], final_media_path)
        analyzed_ad_data['final_media_path'] = final_media_path
        print(f"Média principal déplacé vers : {final_media_path}")
    
    final_generated_image_paths = []
    if analyzed_ad_data.get('generated_image_paths'):
        for temp_path in analyzed_ad_data['generated_image_paths']:
            if os.path.exists(temp_path):
                filename = os.path.basename(temp_path)
                final_path = os.path.join(destination_folder, filename)
                shutil.move(temp_path, final_path)
                final_generated_image_paths.append(final_path)
    analyzed_ad_data['final_generated_image_paths'] = final_generated_image_paths

    return analyzed_ad_data

def run_top_n_analysis_for_client(client_id: int, report_id: int, num_ads: int, 
                                  min_spend: float = None, target_cpa: float = None, 
                                  target_roas: float = None, date_start: str = None, 
                                  date_end: str = None):
    """
    Exécute le pipeline d'analyse pour les N MEILLEURES annonces d'un client,
    génère un rapport HTML consolidé et met à jour un enregistrement de rapport existant.
    """
    print(f"--- DÉBUT PIPELINE TOP {num_ads} pour le client ID: {client_id} (Rapport ID: {report_id}) ---")
    cache_path = os.path.join(ANALYSIS_CACHE_DIR, f"analysis_{client_id}_{report_id}_top{num_ads}.json")
    
    total_cost_analysis = 0.0
    total_cost_generation = 0.0

    try:
        conn = database.get_db_connection()
        client = conn.execute('SELECT * FROM clients WHERE id = ?', (client_id,)).fetchone()
        conn.close()
        if not client:
            raise Exception(f"Client {client_id} non trouvé.")

        ad_account_id = client['ad_account_id']
        if not ad_account_id or not ad_account_id.startswith('act_'):
            raise ValueError(f"ID de compte publicitaire manquant ou invalide pour le client {client['name']}.")

        conn = database.get_db_connection()
        conn.execute('UPDATE analyses SET status = ? WHERE id = ?', ('RUNNING', report_id))
        conn.commit()
        conn.close()

        print(f"Récupération des {num_ads} annonces les plus performantes...")
        facebook_client.init_facebook_api(client['facebook_token'], ad_account_id)
        
        all_winning_ads = facebook_client.get_winning_ads(
            ad_account_id=ad_account_id,
            min_spend=min_spend,
            target_cpa=target_cpa,
            target_roas=target_roas,
            date_start=date_start,
            date_end=date_end
        )
        
        top_ads = all_winning_ads[:num_ads]

        if not top_ads:
            raise Exception("Aucune annonce performante trouvée pour ce client.")

        print(f"{len(top_ads)} annonces performantes trouvées. Lancement des analyses...")
        
        ad_ids = [ad.id for ad in top_ads]
        conn = database.get_db_connection()
        conn.execute('UPDATE analyses SET ad_id = ? WHERE id = ?', (','.join(ad_ids), report_id))
        conn.commit()
        conn.close()

        analyzed_ads_data = []
        cache = load_cache(cache_path)
        
        # On va aussi stocker l'HTML de l'analyse principale pour le rapport final
        final_analysis_html_parts = []

        for ad in top_ads:
            try:
                analysis_result = _perform_single_ad_analysis(ad, cache)
                analyzed_ads_data.append(analysis_result)
                total_cost_analysis += analysis_result.get('cost_analysis', 0.0)
                total_cost_generation += analysis_result.get('cost_generation', 0.0)
                save_cache(cache_path, cache)

                # Étape clé : Sauvegarder le script de cette annonce dans la nouvelle table
                conn = database.get_db_connection()
                script_html = markdown.markdown(analysis_result.get('script_text', ''), extensions=['tables'])
                conn.execute(
                    "INSERT INTO ad_scripts (report_id, ad_id, original_script_html) VALUES (?, ?, ?)",
                    (report_id, ad.id, script_html)
                )
                conn.commit()
                conn.close()
                print(f"Script pour l'annonce {ad.id} sauvegardé dans la base de données.")

                # On prépare l'HTML de l'analyse pour le rapport final
                # (sans les scripts, qui seront chargés dynamiquement dans le template)
                analysis_html = markdown.markdown(analysis_result.get('analysis_text', ''), extensions=['tables'])
                final_analysis_html_parts.append({
                    "ad": ad.model_dump(),
                    "analysis_html": analysis_html,
                    "media_type": analysis_result.get('media_type'),
                    "final_media_path": analysis_result.get('final_media_path'),
                    "model_used": analysis_result.get('model_used'),
                    "is_fallback": analysis_result.get('is_fallback', False),
                })
            except Exception as ad_error:
                error_message = f"Échec de l'analyse pour l'annonce ID {ad.id} ({ad.name}): {ad_error}"
                print(f"\n[ERREUR] {error_message}\n")
                traceback.print_exc()
                # Enregistrer l'erreur dans la base de données et continuer
                database.add_analysis_error(report_id, ad.id, str(ad_error))
                continue

        print("Toutes les analyses sont terminées. Assemblage du rapport principal...")
        
        # La génération de l'HTML est maintenant simplifiée, car les scripts sont dans leur propre table.
        # Nous allons juste stocker un JSON ou une structure de base dans 'analysis_html'
        # que le template pourra utiliser.
        final_report_structure = json.dumps(final_analysis_html_parts)
        
        total_cost = total_cost_analysis + total_cost_generation
        conn = database.get_db_connection()
        conn.execute(
            """
            UPDATE analyses 
            SET status = ?, analysis_html = ?, cost_analysis = ?, cost_generation = ?, total_cost = ?
            WHERE id = ?
            """,
            ('COMPLETED', final_report_structure, total_cost_analysis, total_cost_generation, total_cost, report_id)
        )
        conn.commit()
        conn.close()
        
        print(f"--- FIN PIPELINE TOP {num_ads} pour le client : {client['name']}. Coût total: ${total_cost:.4f} ---")

    except Exception as e:
        print(f"ERREUR dans le pipeline TOP {num_ads} pour le rapport {report_id}: {e}")
        traceback.print_exc()
        conn = database.get_db_connection()
        conn.execute('UPDATE analyses SET status = ? WHERE id = ?', ('FAILED', report_id))
        conn.commit()
        conn.close()

def run_analysis_for_client(client_id, report_id, media_type: str):
    """
    Exécute le pipeline d'analyse pour la MEILLEURE annonce d'un client pour un type de média donné.
    Met à jour un enregistrement de rapport existant.
    """
    cache_path = os.path.join(ANALYSIS_CACHE_DIR, f"analysis_{client_id}_{report_id}.json")

    try:
        conn = database.get_db_connection()
        client = conn.execute('SELECT * FROM clients WHERE id = ?', (client_id,)).fetchone()
        conn.close()
        if not client:
            raise Exception(f"Client {client_id} non trouvé.")

        ad_account_id = client['ad_account_id']
        if not ad_account_id or not ad_account_id.startswith('act_'):
            raise ValueError(f"ID de compte publicitaire manquant ou invalide pour le client {client['name']}.")

        print(f"--- DÉBUT PIPELINE '{media_type}' pour le client : {client['name']} (Rapport ID: {report_id}) ---")
        
        conn = database.get_db_connection()
        conn.execute('UPDATE analyses SET status = ? WHERE id = ?', ('RUNNING', report_id))
        conn.commit()
        conn.close()

        print(f"Récupération de l'annonce la plus performante de type '{media_type}'...")
        facebook_client.init_facebook_api(client['facebook_token'], ad_account_id)
        
        best_ad = facebook_client.get_specific_winning_ad(
            ad_account_id=ad_account_id,
            media_type=media_type,
            spend_threshold=0, # On laisse 0 et 99999 pour l'instant
            cpa_threshold=99999
        )
        if not best_ad:
            raise Exception(f"Aucune annonce gagnante trouvée pour le type '{media_type}'.")
        
        print(f"Meilleure annonce trouvée : {best_ad.name} (ID: {best_ad.id})")

        conn = database.get_db_connection()
        conn.execute('UPDATE analyses SET ad_id = ? WHERE id = ?', (best_ad.id, report_id))
        conn.commit()
        conn.close()

        cache = load_cache(cache_path)
        analyzed_ad_data = _perform_single_ad_analysis(best_ad, cache)
        save_cache(cache_path, cache)

        print("Génération des fragments de rapport...")
        analysis_html, script_html_with_images = generate_report_fragments(analyzed_ad_data)

        final_media_path = analyzed_ad_data.get('final_media_path')
        cost_analysis = analyzed_ad_data.get('cost_analysis', 0.0)
        cost_generation = analyzed_ad_data.get('cost_generation', 0.0)
        total_cost = cost_analysis + cost_generation

        conn = database.get_db_connection()
        conn.execute(
            """
            UPDATE analyses 
            SET status = ?, report_path = ?, analysis_html = ?, script_html = ?, 
                cost_analysis = ?, cost_generation = ?, total_cost = ?, media_type = ?
            WHERE id = ?
            """,
            ('COMPLETED', final_media_path, analysis_html, script_html_with_images, 
             cost_analysis, cost_generation, total_cost, media_type, report_id)
        )
        conn.commit()
        conn.close()
        
        print(f"--- FIN PIPELINE '{media_type}' pour le client : {client['name']}. Coût: ${total_cost:.4f} ---")

    except Exception as e:
        print(f"ERREUR dans le pipeline pour le rapport {report_id}: {e}")
        traceback.print_exc()
        conn = database.get_db_connection()
        conn.execute('UPDATE analyses SET status = ?, media_type = ? WHERE id = ?', ('FAILED', media_type, report_id))
        conn.commit()
        conn.close()
        print(f"LOG: Statut du rapport {report_id} mis à jour à FAILED.")

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        run_analysis_for_client(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3])
    else:
        print("Usage: python pipeline.py <client_id> <report_id> <media_type>") 