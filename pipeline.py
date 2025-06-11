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
GEMINI_INPUT_PRICE_PER_MILLION_TOKENS = float(os.getenv("GEMINI_INPUT_PRICE_PER_MILLION_TOKENS", "2.50"))
GEMINI_OUTPUT_PRICE_PER_MILLION_TOKENS = float(os.getenv("GEMINI_OUTPUT_PRICE_PER_MILLION_TOKENS", "7.50"))
IMAGEN_PRICE_PER_IMAGE = float(os.getenv("IMAGEN_PRICE_PER_IMAGE", "0.03"))

# Le nom du fichier de cache d'analyse (doit être spécifique au client à l'avenir)
CACHE_FILE = "analysis_cache.json"

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_cache(cache_data):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, indent=4)

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

def run_analysis_for_client(client_id, report_id, media_type: str):
    """
    Exécute le pipeline d'analyse pour la MEILLEURE annonce d'un client pour un type de média donné.
    Met à jour un enregistrement de rapport existant.
    """
    # Initialisation des coûts
    cost_analysis = 0.0
    cost_generation = 0.0
    total_cost = 0.0

    try:
        # 1. Récupérer les infos du client
        conn = database.get_db_connection()
        client = conn.execute('SELECT * FROM clients WHERE id = ?', (client_id,)).fetchone()
        conn.close()
        if not client:
            raise Exception(f"Client {client_id} non trouvé.")

        print(f"--- DÉBUT PIPELINE pour le client : {client['name']} (Rapport ID: {report_id}) ---")
        
        # Mettre à jour le statut du rapport à RUNNING
        conn = database.get_db_connection()
        conn.execute('UPDATE reports SET status = ? WHERE id = ?', ('RUNNING', report_id))
        conn.commit()
        conn.close()
        print(f"LOG: Statut du rapport {report_id} mis à jour à RUNNING.")

        # 2. Récupérer l'annonce la plus performante pour le type de média spécifié
        print(f"Récupération de l'annonce la plus performante de type '{media_type}'...")
        facebook_client.init_facebook_api()
        best_ad = facebook_client.get_specific_winning_ad(
            media_type=media_type,
            spend_threshold=client['spend_threshold'],
            cpa_threshold=client['cpa_threshold']
        )
        if not best_ad:
            raise Exception(f"Aucune annonce gagnante trouvée pour le type '{media_type}'.")
        
        print(f"Meilleure annonce trouvée : {best_ad.name} (ID: {best_ad.id}) avec un CPA de {best_ad.insights.cpa:.2f}")

        # 3. Mettre à jour l'enregistrement du rapport avec l'ID de l'annonce
        conn = database.get_db_connection()
        conn.execute('UPDATE reports SET ad_id = ? WHERE id = ?', (best_ad.id, report_id))
        conn.commit()
        conn.close()

        # 4. Logique d'analyse complète (extraite de main.py) pour cette seule annonce
        cache = load_cache()
        if best_ad.id in cache and all(os.path.exists(p) for p in cache[best_ad.id].get('generated_image_paths', [])):
             print("Annonce déjà dans le cache complet, on utilise le cache.")
             analyzed_ad_data = cache[best_ad.id]
             cost_analysis = analyzed_ad_data.get('cost_analysis', 0.0) # Récupérer le coût du cache
             cost_generation = analyzed_ad_data.get('cost_generation', 0.0)

             # CORRECTIF: On doit retélécharger le média car le chemin dans le cache est temporaire et peut ne plus exister.
             print("Le chemin du média dans le cache est obsolète, re-téléchargement...")
             downloader = MediaDownloader()
             local_media_path, _ = (None, None)
             if best_ad.video_id:
                 local_media_path = downloader.download_video_locally(best_ad.video_id, best_ad.id)
             elif best_ad.image_url:
                 local_media_path = downloader.download_image_locally(best_ad.image_url, best_ad.id)
             
             if not local_media_path:
                 raise Exception("Échec du re-téléchargement du média depuis le cache.")
                 
             # On met à jour le chemin dans les données que nous allons utiliser
             analyzed_ad_data['media_path'] = local_media_path
        else:
            print("Analyse de l'annonce requise...")
            downloader = MediaDownloader()
            local_media_path, media_type = (None, None)
            
            if best_ad.video_id:
                media_type = 'video'
                local_media_path = downloader.download_video_locally(best_ad.video_id, best_ad.id)
            elif best_ad.image_url:
                media_type = 'image'
                local_media_path = downloader.download_image_locally(best_ad.image_url, best_ad.id)

            if not local_media_path:
                raise Exception("Échec du téléchargement du média.")

            full_response_text, usage_metadata = "", {}
            if media_type == 'video':
                full_response_text, usage_metadata = gemini_analyzer.analyze_video(local_media_path, best_ad)
            else:
                full_response_text, usage_metadata = gemini_analyzer.analyze_image(local_media_path, best_ad)

            # >>>>>>>>>>>> LOGGING TEMPORAIRE AJOUTÉ <<<<<<<<<<<<
            print("\\n" + "="*80)
            print("RAW RESPONSE FROM GEMINI (START):")
            print(full_response_text)
            print("RAW RESPONSE FROM GEMINI (END):")
            print("="*80 + "\\n")
            # >>>>>>>>>>>> FIN DU LOGGING TEMPORAIRE <<<<<<<<<<<<

            # Calcul du coût de l'analyse
            cost_analysis = calculate_analysis_cost(usage_metadata)
            print(f"💰 Usage metadata from Gemini: {usage_metadata}")
            if hasattr(usage_metadata, 'prompt_token_count'):
                print(f"💰 Détail des tokens: Input={usage_metadata.prompt_token_count}, Output={usage_metadata.candidates_token_count}")
            print(f"💰 Coût de l'analyse Gemini estimé : ${cost_analysis:.4f}")
            
            analysis_part, script_part = (full_response_text.split("---", 1) + [""])[:2]
            
            print("Génération des images concepts (TEMPORAIREMENT DÉSACTIVÉE)...")
            prompts = re.findall(r"PROMPT_IMG: (.*)", full_response_text)
            generated_image_paths = []
            images_generated_count = 0
            # for i, prompt in enumerate(prompts[:3]):
            #     output_filename = f"generated_concept_{best_ad.id}_{i+1}.png"
            #     generated_path, count = image_generator.generate_image_from_prompt(prompt, output_filename)
            #     if generated_path:
            #         generated_image_paths.append(generated_path)
            #         images_generated_count += count
            
            # Calcul du coût de la génération d'images
            cost_generation = images_generated_count * IMAGEN_PRICE_PER_IMAGE
            print(f"💰 Coût de la génération d'images estimé : ${cost_generation:.4f}")

            analyzed_ad_data = {
                "ad": best_ad.model_dump(),
                "analysis_text": analysis_part.strip(),
                "script_text": script_part.strip(),
                "media_path": local_media_path,
                "media_type": media_type,
                "generated_image_paths": generated_image_paths,
                "cost_analysis": cost_analysis, # Sauvegarder les coûts dans le cache
                "cost_generation": cost_generation
            }
            # On ne sauvegarde pas le coût dans le cache fichier pour l'instant
            cache[best_ad.id] = analyzed_ad_data
            save_cache(cache)
        
        # 5. Déplacer le média vers le stockage permanent et générer les fragments HTML
        print("Génération des fragments de rapport et déplacement du média...")

        # Créer le dossier storage s'il n'existe pas
        storage_dir = "storage"
        os.makedirs(storage_dir, exist_ok=True)
            
        # Déplacer le fichier et obtenir son nouveau chemin permanent
        permanent_media_path = os.path.join(storage_dir, os.path.basename(analyzed_ad_data['media_path']))
        shutil.move(analyzed_ad_data['media_path'], permanent_media_path)
        print(f"Média déplacé vers : {permanent_media_path}")

        analysis_html, script_html = generate_report_fragments(analyzed_ad_data)

        # 6. Mettre à jour le rapport dans la DB avec les fragments et le statut final
        total_cost = cost_analysis + cost_generation
        conn = database.get_db_connection()
        conn.execute(
            """UPDATE reports 
               SET status = ?, report_path = ?, analysis_html = ?, script_html = ?, 
                   cost_analysis = ?, cost_generation = ?, total_cost = ? 
               WHERE id = ?""",
            ('COMPLETED', permanent_media_path, analysis_html, script_html, 
             cost_analysis, cost_generation, total_cost, report_id)
        )
        conn.commit()
        conn.close()
        print(f"LOG: Rapport {report_id} finalisé et sauvegardé dans la base de données avec un coût total de ${total_cost:.4f}")
        print(f"--- FIN PIPELINE pour le client : {client['name']} ---")

    except Exception as e:
        print(f"ERREUR dans le pipeline pour le rapport {report_id}: {e}")
        traceback.print_exc()
        if report_id:
            conn = database.get_db_connection()
            conn.execute('UPDATE reports SET status = ? WHERE id = ?', ('FAILED', report_id))
            conn.commit()
            conn.close()
            print(f"LOG: Statut du rapport {report_id} mis à jour à FAILED.")

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        run_analysis_for_client(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3])
    else:
        print("Usage: python pipeline.py <client_id> <report_id> <media_type>") 