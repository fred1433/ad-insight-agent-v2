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

def _generate_top5_report_html(analyzed_ads_data: list, client_name: str) -> str:
    """Génère le HTML pour un rapport consolidé de plusieurs annonces."""
    
    css_style = """
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 0; background-color: #f8f9fa; color: #212529; }
        .main-container { max-width: 900px; margin: 40px auto; padding: 0 20px; }
        .report-title { font-size: 2.8em; text-align: center; margin-bottom: 10px; border-bottom: 2px solid #dee2e6; padding-bottom: 20px; color: #0056b3;}
        .client-name { font-size: 1.5em; text-align: center; margin-bottom: 40px; color: #6c757d; }
        .ad-container { background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); margin-bottom: 40px; }
        h2, h3, h4 { color: #0056b3; }
        h2 { font-size: 2em; border-bottom: 2px solid #dee2e6; padding-bottom: 10px; }
        h3 { font-size: 1.5em; border-bottom: none; }
        h4 { font-size: 1.2em; color: #343a40; margin-top: 25px; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { border: 1px solid #dee2e6; padding: 12px; text-align: left; vertical-align: top; }
        th { background-color: #e9ecef; font-weight: 600; }
        .kpi-value { text-align: right; font-weight: bold; font-family: "SFMono-Regular", Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; }
        .analysis { margin-top: 20px; line-height: 1.6; }
        .grid-container { display: grid; grid-template-columns: 1fr 1fr; gap: 40px; align-items: start;}
        .generated-images-grid { display: flex; flex-wrap: wrap; gap: 15px; margin-top: 15px; }
        .generated-images-grid img, td img { width: 100%; max-width: 250px; height: auto; border-radius: 4px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        video, .ad-media-img { max-width: 100%; height: auto; border-radius: 8px; }
        @media (max-width: 768px) { .grid-container { grid-template-columns: 1fr; } }
    </style>
    """

    ad_sections_html = ""
    for item in analyzed_ads_data:
        ad = facebook_client.Ad(**item['ad'])
        analysis_html = markdown.markdown(item['analysis_text'], extensions=['tables'])
        script_html = markdown.markdown(item['script_text'], extensions=['tables'])
        
        final_media_path = item.get('final_media_path')
        media_type = item['media_type']
        
        media_html = ""
        if final_media_path:
            filename = os.path.basename(final_media_path)
            # Utilise un chemin relatif vers le point de service des fichiers
            media_url = f"/storage/{filename}"
            if media_type == 'video':
                media_html = f'<video controls width="100%"><source src="{media_url}" type="video/mp4">Tu navegador no soporta la etiqueta de video.</video>'
            elif media_type == 'image':
                media_html = f'<img src="{media_url}" alt="Anuncio" class="ad-media-img">'
        
        # Le script de génération des concepts (pour les rapports single-ad) peut contenir des images en base64
        # On doit les gérer ici.
        if 'script_with_images_html' in item:
             script_html = item['script_with_images_html']

        proposals_title = "Propuestas de Nuevos Guiones" if media_type == 'video' else "Propuestas de Imágenes Alternativas"
        
        video_metrics_html = ""
        if media_type == 'video' and ad.insights:
            video_metrics_html = f"""
            <tr><td><b>Tasa de Enganche (Hook Rate)</b></td><td class="kpi-value"><b>{ad.insights.hook_rate:.2f} %</b></td></tr>
            <tr><td><b>Tasa de Retención (Hold Rate)</b></td><td class="kpi-value"><b>{ad.insights.hold_rate:.2f} %</b></td></tr>
            """

        kpi_table = f"""
        <table>
            <tr><th>Métrica</th><th class="kpi-value">Valor</th></tr>
            <tr><td>Inversión (Spend)</td><td class="kpi-value">{ad.insights.spend:,.2f} $</td></tr>
            <tr><td>Costo por Compra (CPA)</td><td class="kpi-value">{ad.insights.cpa:,.2f} $</td></tr>
            <tr><td>Número de Compras</td><td class="kpi-value">{ad.insights.website_purchases}</td></tr>
            <tr><td>Valor de las Compras</td><td class="kpi-value">{ad.insights.website_purchases_value:,.2f} $</td></tr>
            <tr><td>ROAS</td><td class="kpi-value">{ad.insights.roas:.2f}x</td></tr>
            <tr><td>CPM</td><td class="kpi-value">{ad.insights.cpm:,.2f} $</td></tr>
            <tr><td>CTR (único)</td><td class="kpi-value">{ad.insights.unique_ctr:.2f} %</td></tr>
            <tr><td>Frecuencia</td><td class="kpi-value">{ad.insights.frequency:.2f}</td></tr>
            {video_metrics_html}
        </table>
        """

        ad_sections_html += f"""
        <div class="ad-container">
            <h2>{ad.name} (ID: {ad.id})</h2>
            <div class="grid-container">
                <div>
                    <h3>Creatividad del Anuncio</h3>
                    {media_html}
                </div>
                <div>
                    <h3>Indicadores Clave (KPIs)</h3>
                    {kpi_table}
                </div>
            </div>
            <div>
                <h3>Análisis Cualitativo del Experto IA</h3>
                <div class="analysis">{analysis_html}</div>
            </div>
            <div>
                <h3>{proposals_title}</h3>
                <div class="analysis">{script_html}</div>
            </div>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Informe de Análisis Top 5 - {client_name}</title>
        {css_style}
    </head>
    <body>
        <div class="main-container">
            <h1 class="report-title">Informe de Análisis de Rendimiento</h1>
            <p class="client-name">Cliente: {client_name}</p>
            {ad_sections_html}
        </div>
    </body>
    </html>
    """

def _perform_single_ad_analysis(ad: facebook_client.Ad, cache: dict) -> dict:
    """
    Exécute le pipeline d'analyse complet (téléchargement, analyse, génération) pour une seule publicité.
    Utilise et met à jour un dictionnaire de cache fourni.
    Retourne un dictionnaire contenant toutes les données et les coûts de l'analyse.
    """
    print(f"--- Début de l'analyse pour l'annonce : {ad.name} ({ad.id}) ---")
    
    cost_analysis = 0.0
    cost_generation = 0.0
    
    # Vérification du cache pour cette annonce spécifique
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
        if media_type == 'video':
            full_response_text, usage_metadata = gemini_analyzer.analyze_video(local_media_path, ad)
        else:
            full_response_text, usage_metadata = gemini_analyzer.analyze_image(local_media_path, ad)

        cost_analysis = calculate_analysis_cost(usage_metadata)
        print(f"💰 Coût de l'analyse Gemini estimé : ${cost_analysis:.4f}")
        
        analysis_part, script_part = (full_response_text.split("---", 1) + [""])[:2]
        
        print("Génération des images concepts... (Désactivée)")
        # prompts = re.findall(r"PROMPT_IMG: (.*)", full_response_text)
        generated_image_paths = []
        images_generated_count = 0
        # for i, prompt in enumerate(prompts[:3]):
        #     output_filename = f"generated_concept_{ad.id}_{i+1}.png"
        #     # La fonction de génération d'image a été modifiée pour renvoyer le chemin et le nombre d'images
        #     generated_path, count = image_generator.generate_image_from_prompt(prompt, output_filename)
        #     if generated_path:
        #         generated_image_paths.append(generated_path)
        #         images_generated_count += count
        
        cost_generation = images_generated_count * IMAGEN_PRICE_PER_IMAGE
        print(f"💰 Coût de la génération d'images estimé : ${cost_generation:.4f}")

        analyzed_ad_data = {
            "ad": ad.model_dump(), # Sauvegarde l'objet Ad complet au format dict
            "media_type": media_type,
            "media_path": local_media_path,
            "analysis_text": analysis_part.strip(),
            "script_text": script_part.strip(),
            "generated_image_paths": generated_image_paths,
            "cost_analysis": cost_analysis,
            "cost_generation": cost_generation
        }
        # Met à jour le cache externe (passé par référence)
        cache[ad.id] = analyzed_ad_data
    
    # Déplacer les médias (principal et générés) vers le stockage final
    # et retourner les chemins finaux pour la génération du rapport.
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

def run_top5_analysis_for_client(client_id: int, report_id: int):
    """
    Exécute le pipeline d'analyse pour les 5 MEILLEURES annonces d'un client,
    génère un rapport HTML consolidé et met à jour un enregistrement de rapport existant.
    """
    print(f"--- DÉBUT PIPELINE TOP 5 pour le client ID: {client_id} (Rapport ID: {report_id}) ---")
    cache_path = os.path.join(ANALYSIS_CACHE_DIR, f"analysis_{client_id}_{report_id}_top5.json")
    
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
        conn.execute('UPDATE reports SET status = ? WHERE id = ?', ('RUNNING', report_id))
        conn.commit()
        conn.close()

        print("Récupération des 5 annonces les plus performantes...")
        facebook_client.init_facebook_api(client['facebook_token'], ad_account_id)
        
        top_ads = facebook_client.get_winning_ads(
            ad_account_id=ad_account_id,
            spend_threshold=client['spend_threshold'],
            cpa_threshold=client['cpa_threshold']
        )[:2] # On prend les 2 premiers pour un test rapide

        if not top_ads:
            raise Exception("Aucune annonce performante trouvée pour ce client.")

        print(f"{len(top_ads)} annonces performantes trouvées. Lancement des analyses...")
        
        ad_ids = [ad.id for ad in top_ads]
        conn = database.get_db_connection()
        conn.execute('UPDATE reports SET ad_id = ? WHERE id = ?', (','.join(ad_ids), report_id))
        conn.commit()
        conn.close()

        analyzed_ads_data = []
        cache = load_cache(cache_path)
        
        for ad in top_ads:
            analysis_result = _perform_single_ad_analysis(ad, cache)
            analyzed_ads_data.append(analysis_result)
            total_cost_analysis += analysis_result.get('cost_analysis', 0.0)
            total_cost_generation += analysis_result.get('cost_generation', 0.0)
            save_cache(cache_path, cache) # Sauvegarde après chaque analyse
        
        print("Toutes les analyses sont terminées. Génération du rapport consolidé...")
        final_html_report = _generate_top5_report_html(analyzed_ads_data, client['name'])
        
        total_cost = total_cost_analysis + total_cost_generation
        conn = database.get_db_connection()
        conn.execute(
            """
            UPDATE reports 
            SET status = ?, analysis_html = ?, cost_analysis = ?, cost_generation = ?, total_cost = ?
            WHERE id = ?
            """,
            ('COMPLETED', final_html_report, total_cost_analysis, total_cost_generation, total_cost, report_id)
        )
        conn.commit()
        conn.close()
        
        print(f"--- FIN PIPELINE TOP 5 pour le client : {client['name']}. Coût total: ${total_cost:.4f} ---")

    except Exception as e:
        print(f"ERREUR dans le pipeline TOP 5 pour le rapport {report_id}: {e}")
        traceback.print_exc()
        conn = database.get_db_connection()
        conn.execute('UPDATE reports SET status = ? WHERE id = ?', ('FAILED', report_id))
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
        conn.execute('UPDATE reports SET status = ? WHERE id = ?', ('RUNNING', report_id))
        conn.commit()
        conn.close()

        print(f"Récupération de l'annonce la plus performante de type '{media_type}'...")
        facebook_client.init_facebook_api(client['facebook_token'], ad_account_id)
        
        best_ad = facebook_client.get_specific_winning_ad(
            ad_account_id=ad_account_id,
            media_type=media_type,
            spend_threshold=client['spend_threshold'],
            cpa_threshold=client['cpa_threshold']
        )
        if not best_ad:
            raise Exception(f"Aucune annonce gagnante trouvée pour le type '{media_type}'.")
        
        print(f"Meilleure annonce trouvée : {best_ad.name} (ID: {best_ad.id})")

        conn = database.get_db_connection()
        conn.execute('UPDATE reports SET ad_id = ? WHERE id = ?', (best_ad.id, report_id))
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
            UPDATE reports 
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
        conn.execute('UPDATE reports SET status = ?, media_type = ? WHERE id = ?', ('FAILED', media_type, report_id))
        conn.commit()
        conn.close()
        print(f"LOG: Statut du rapport {report_id} mis à jour à FAILED.")

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        run_analysis_for_client(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3])
    else:
        print("Usage: python pipeline.py <client_id> <report_id> <media_type>") 