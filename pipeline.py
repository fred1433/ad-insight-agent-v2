import os
import base64
import re
import json
import threading
import traceback
from datetime import datetime
import pytz
from bs4 import BeautifulSoup

import facebook_client
from media_downloader import MediaDownloader
import gemini_analyzer
import image_generator
import markdown
import database

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

def generate_html_report(analyzed_ad_data, client_name):
    """Génère un rapport HTML autonome pour un seul annonce analysée."""
    
    css_style = """
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 0; background-color: #f8f9fa; color: #212529; }
        .main-container { max-width: 1200px; margin: 40px auto; }
        .ad-container { background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); margin-bottom: 40px; }
        h1, h2, h3 { color: #0056b3; }
        h1 { font-size: 2.8em; text-align: center; margin-bottom: 20px; }
        h1 small { font-size: 0.5em; color: #6c757d; display: block; margin-top: 10px;}
        h2 { font-size: 2em; border-bottom: 2px solid #dee2e6; padding-bottom: 10px; margin-top: 40px; }
        h3 { font-size: 1.5em; border-bottom: none; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { border: 1px solid #dee2e6; padding: 12px; text-align: left; }
        th { background-color: #e9ecef; font-weight: 600; }
        .kpi-value { text-align: right; font-weight: bold; font-family: "SFMono-Regular", Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; }
        .analysis { margin-top: 20px; line-height: 1.6; }
        .grid-container { display: grid; grid-template-columns: 1fr 1fr; gap: 40px; align-items: start;}
        .generated-images-grid { display: flex; flex-wrap: wrap; gap: 15px; margin-top: 15px; justify-content: center; }
        .generated-images-grid img { width: 100%; max-width: 250px; height: auto; border-radius: 4px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        td img { max-width: 250px; height: auto; border-radius: 4px; }
        @media (max-width: 768px) { .grid-container { grid-template-columns: 1fr; } }
    </style>
    """

    ad = analyzed_ad_data['ad']
    analysis_html = markdown.markdown(analyzed_ad_data['analysis_text'], extensions=['tables'])
    script_html = markdown.markdown(analyzed_ad_data['script_text'], extensions=['tables'])
    media_path = analyzed_ad_data['media_path']
    media_type = analyzed_ad_data['media_type']
    generated_image_paths = analyzed_ad_data.get('generated_image_paths', [])

    proposals_title = "Propuestas de Nuevos Guiones" if media_type == 'video' else "Propuestas de Imágenes Alternativas"
    
    media_html = ""
    try:
        with open(media_path, "rb") as media_file:
            media_b64 = base64.b64encode(media_file.read()).decode('utf-8')
        if media_type == 'video':
            media_html = f'<video controls width="100%"><source src="data:video/mp4;base64,{media_b64}" type="video/mp4"></video>'
        elif media_type == 'image':
            ext = os.path.splitext(media_path)[1].lower().replace('.', '')
            media_html = f'<img src="data:image/{ext};base64,{media_b64}" alt="Anuncio" style="width:100%; height:auto; border-radius: 4px;">'
    except Exception as e:
        media_html = f"<p><i>Error al incrustar el medio: {e}</i></p>"

    # Logique conditionnelle pour l'affichage des propositions
    proposals_html_content = ""
    if media_type == 'image' and generated_image_paths:
        # Pour les images, on fusionne les propositions et les images dans un seul tableau
        soup = BeautifulSoup(script_html, 'html.parser')
        
        table = soup.find('table')
        if table:
            # 1. Ajouter l'en-tête de la nouvelle colonne
            header = table.find('thead').find('tr')
            if header:
                new_th = soup.new_tag('th')
                new_th.string = 'Visualización (IA)'
                header.append(new_th)
            
            # 2. Ajouter les cellules pour les images
            rows = table.find('tbody').find_all('tr')
            image_iterator = iter(generated_image_paths)
            
            for row in rows:
                new_td = soup.new_tag('td')
                try:
                    img_path = next(image_iterator)
                    with open(img_path, "rb") as img_file:
                        img_b64 = base64.b64encode(img_file.read()).decode('utf-8')
                    img_ext = os.path.splitext(img_path)[1].lower().replace('.', '')
                    img_tag = soup.new_tag('img', src=f"data:image/{img_ext};base64,{img_b64}", alt="Concepto generado por IA")
                    new_td.append(img_tag)
                except (StopIteration, FileNotFoundError):
                    pass
                row.append(new_td)
                
            proposals_html_content = f"""
            <h3>{proposals_title}</h3>
            <div class="analysis">{str(soup)}</div>
            """
        else: # Fallback si le script n'est pas un tableau
            proposals_html_content = f"""
            <h3>{proposals_title}</h3>
            <div class="analysis">{script_html}</div>
            {create_image_grid_html(generated_image_paths)}
            """
    elif media_type == 'video' and generated_image_paths:
        # Pour les vidéos, on utilise colspan et rowspan pour placer l'image dans l'espace vide sous le hook
        soup = BeautifulSoup(script_html, 'html.parser')
        table = soup.find('table')
        if table:
            rows = table.find('tbody').find_all('tr')
            image_iterator = iter(generated_image_paths)
            
            i = 0
            while i < len(rows):
                row = rows[i]
                tds = row.find_all('td', recursive=False)
                # Heuristique : une ligne de "hook" a du contenu dans les deux premières cellules
                is_hook_row = len(tds) > 1 and tds[0].get_text(strip=True) and tds[1].get_text(strip=True)

                if is_hook_row:
                    scene_rows = []
                    for j in range(i + 1, len(rows)):
                        next_row = rows[j]
                        next_tds = next_row.find_all('td', recursive=False)
                        # Arrêter si on trouve le prochain hook
                        if len(next_tds) > 1 and next_tds[0].get_text(strip=True) and next_tds[1].get_text(strip=True):
                            break
                        scene_rows.append(next_row)
                    
                    rowspan_count = len(scene_rows)
                    if rowspan_count > 0:
                        try:
                            img_path = next(image_iterator)
                            
                            # Créer la cellule qui s'étendra sur 2 colonnes et N lignes
                            img_td = soup.new_tag('td', colspan="2", rowspan=rowspan_count)
                            img_td.attrs['style'] = "vertical-align: top; text-align: center;"
                            with open(img_path, "rb") as img_file:
                                img_b64 = base64.b64encode(img_file.read()).decode('utf-8')
                            img_ext = os.path.splitext(img_path)[1].lower().replace('.', '')
                            img_tag = soup.new_tag('img', src=f"data:image/{img_ext};base64,{img_b64}", alt="Concepto generado por IA")
                            img_td.append(img_tag)
                            
                            # Dans la 1ère ligne de scène, supprimer les 2 premières cellules et insérer la nouvelle
                            first_scene_row_tds = scene_rows[0].find_all('td', recursive=False)
                            if len(first_scene_row_tds) >= 2:
                                first_scene_row_tds[0].decompose()
                                first_scene_row_tds[1].decompose()
                            scene_rows[0].insert(0, img_td)

                            # Dans les lignes de scène suivantes, supprimer les 2 premières cellules
                            for j in range(1, len(scene_rows)):
                                subsequent_scene_row_tds = scene_rows[j].find_all('td', recursive=False)
                                if len(subsequent_scene_row_tds) >= 2:
                                    subsequent_scene_row_tds[0].decompose()
                                    subsequent_scene_row_tds[1].decompose()
                        except (StopIteration, FileNotFoundError):
                            pass
                    i += 1 + rowspan_count
                else:
                    i += 1
            
            proposals_html_content = f"""
            <h3>{proposals_title}</h3>
            <div class="analysis">{str(soup)}</div>
            """
        else: # Fallback
            proposals_html_content = f"""
            <h3>{proposals_title}</h3>
            <div class="analysis">{script_html}</div>
            {create_image_grid_html(generated_image_paths)}
            """
    else: 
        # S'il n'y a pas d'images générées, on affiche juste le script
        proposals_html_content = f"""
        <h3>{proposals_title}</h3>
        <div class="analysis">
            {script_html}
        </div>
        """

    insights = facebook_client.AdInsights(**ad['insights'])
    video_metrics_html = ""
    if media_type == 'video':
        video_metrics_html = f"""
        <tr><td><b>Tasa de Enganche (Hook Rate)</b></td><td class="kpi-value"><b>{insights.hook_rate:.2f} %</b></td></tr>
        <tr><td><b>Tasa de Retención (Hold Rate)</b></td><td class="kpi-value"><b>{insights.hold_rate:.2f} %</b></td></tr>
        """

    kpi_table = f"""
    <table>
        <tr><th>Métrica</th><th class="kpi-value">Valor</th></tr>
        <tr><td>Inversión (Spend)</td><td class="kpi-value">{insights.spend:,.2f} $</td></tr>
        <tr><td>Costo por Compra (CPA)</td><td class="kpi-value">{insights.cpa:,.2f} $</td></tr>
        <tr><td>Número de Compras</td><td class="kpi-value">{insights.website_purchases}</td></tr>
        <tr><td>Valor de las Compras</td><td class="kpi-value">{insights.website_purchases_value:,.2f} $</td></tr>
        <tr><td>ROAS</td><td class="kpi-value">{insights.roas:.2f}x</td></tr>
        <tr><td>CPM</td><td class="kpi-value">{insights.cpm:,.2f} $</td></tr>
        <tr><td>CTR (único)</td><td class="kpi-value">{insights.unique_ctr:.2f} %</td></tr>
        <tr><td>Frecuencia</td><td class="kpi-value">{insights.frequency:.2f}</td></tr>
        {video_metrics_html}
    </table>
    """

    ad_section_html = f"""
    <div class="ad-container">
        <h2>{ad['name']} (ID: {ad['id']})</h2>
        <div class="grid-container">
            <div><h3>Creatividad del Anuncio</h3>{media_html}</div>
            <div><h3>Indicadores Clave (KPIs)</h3>{kpi_table}</div>
        </div>
        <div><h3>Análisis Cualitativo del Experto IA</h3><div class="analysis">{analysis_html}</div></div>
        <div>{proposals_html_content}</div>
    </div>
    """

    html_content = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Informe de Análisis para {client_name}</title>
        {css_style}
    </head>
    <body>
        <div class="main-container">
            <h1>Informe de Análisis de Rendimiento<small>Cliente: {client_name}</small></h1>
            {ad_section_html}
        </div>
    </body>
    </html>
    """
    
    os.makedirs("reports", exist_ok=True)
    report_filename = f"informe_{client_name.replace(' ', '_')}_{ad['id']}_{datetime.now().strftime('%Y%m%d')}.html"
    report_path = os.path.join("reports", report_filename)
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"Rapport HTML généré : {report_path}")
    return report_path

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

            full_response = ""
            if media_type == 'video':
                full_response = gemini_analyzer.analyze_video(local_media_path, best_ad)
            else:
                full_response = gemini_analyzer.analyze_image(local_media_path, best_ad)
            
            analysis_part, script_part = (full_response.split("---", 1) + [""])[:2]
            
            print("Génération des images concepts...")
            prompts = re.findall(r"PROMPT_IMG: (.*)", full_response)
            generated_image_paths = []
            for i, prompt in enumerate(prompts[:3]):
                output_filename = f"generated_concept_{best_ad.id}_{i+1}.png"
                generated_path = image_generator.generate_image_from_prompt(prompt, output_filename)
                if generated_path:
                    generated_image_paths.append(generated_path)
            
            analyzed_ad_data = {
                "ad": best_ad.model_dump(),
                "analysis_text": analysis_part.strip(),
                "script_text": script_part.strip(),
                "media_path": local_media_path,
                "media_type": media_type,
                "generated_image_paths": generated_image_paths
            }
            cache[best_ad.id] = analyzed_ad_data
            save_cache(cache)
        
        # 5. Générer le rapport HTML
        print("Génération du rapport HTML...")
        report_path = generate_html_report(analyzed_ad_data, client['name'])

        # 6. Mettre à jour le statut du rapport dans la DB à COMPLETED
        conn = database.get_db_connection()
        conn.execute('UPDATE reports SET status = ?, report_path = ? WHERE id = ?', ('COMPLETED', report_path, report_id))
        conn.commit()
        conn.close()
        print(f"LOG: Statut du rapport {report_id} mis à jour à COMPLETED.")
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