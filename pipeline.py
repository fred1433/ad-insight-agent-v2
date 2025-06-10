import os
import base64
import re
import json
import threading
import traceback
from datetime import datetime

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
        h2 { font-size: 2em; border-bottom: 2px solid #dee2e6; padding-bottom: 10px; margin-top: 40px;}
        h3 { font-size: 1.5em; border-bottom: none; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { border: 1px solid #dee2e6; padding: 12px; text-align: left; vertical-align: top;}
        th { background-color: #e9ecef; font-weight: 600; }
        .kpi-value { text-align: right; font-weight: bold; font-family: "SFMono-Regular", Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; }
        .analysis { margin-top: 20px; line-height: 1.6; }
        .grid-container { display: grid; grid-template-columns: 1fr 1fr; gap: 40px; align-items: start;}
        .generated-images-grid img { width: 100%; max-width: 250px; height: auto; border-radius: 4px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .concept-image { max-width: 200px; width: 100%; height: auto; border-radius: 4px;}
        @media (max-width: 768px) { .grid-container { grid-template-columns: 1fr; } }
    </style>
    """

    ad = analyzed_ad_data['ad']
    analysis_html = markdown.markdown(analyzed_ad_data['analysis_text'], extensions=['tables'])
    script_text = analyzed_ad_data['script_text']
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

    # Associer chaque image générée à son script
    prompts = re.findall(r"PROMPT_IMG: (.*)", analyzed_ad_data['analysis_text'] + script_text)
    image_map = {}
    for i, prompt in enumerate(prompts):
        if i < len(generated_image_paths):
            try:
                with open(generated_image_paths[i], "rb") as img_file:
                    img_b64 = base64.b64encode(img_file.read()).decode('utf-8')
                img_ext = os.path.splitext(generated_image_paths[i])[1].lower().replace('.', '')
                image_map[prompt] = f'<img src="data:image/{img_ext};base64,{img_b64}" alt="{prompt}" class="concept-image">'
            except Exception:
                pass

    # Convertir le markdown du script en HTML et insérer les images
    script_html_table = ""
    script_lines = script_text.strip().split('\n')
    in_table = False
    for line in script_lines:
        if '----' in line and not in_table:
            in_table = True
            # Ajouter une colonne pour l'image
            script_html_table += "<thead>\n"
            header = script_lines[script_lines.index(line) - 1]
            header_cols = [f"<th>{h.strip()}</th>" for h in header.split('|')]
            header_cols.insert(2, "<th>Visualisation du Concept</th>") 
            script_html_table += f"<tr>{''.join(header_cols)}</tr>\n</thead>\n<tbody>\n"
        elif in_table and '|' in line and '----' not in line:
            row_cells = [f"<td>{cell.strip()}</td>" for cell in line.split('|')]
            # Trouver le bon prompt dans la ligne pour faire correspondre l'image
            prompt_in_row = next((p for p in prompts if p in line), None)
            image_html = image_map.get(prompt_in_row, "<td></td>")
            if "<td>" not in image_html:
                image_html = f"<td>{image_html}</td>"
            row_cells.insert(2, image_html)
            script_html_table += f"<tr>{''.join(row_cells)}</tr>\n"
        elif not in_table:
            script_html_table += markdown.markdown(line)
        
    if in_table:
        script_html_table = f"<table>{script_html_table}</tbody></table>"
    else: # Fallback si pas de table détectée
        script_html_table = markdown.markdown(script_text, extensions=['tables'])

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
        <div><h3>{proposals_title}</h3><div class="analysis">{script_html_table}</div></div>
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


def run_analysis_for_client(client_id):
    """
    Exécute le pipeline d'analyse pour la MEILLEURE annonce d'un client.
    """
    report_id = None
    try:
        # 1. Récupérer les infos du client
        conn = database.get_db_connection()
        client = conn.execute('SELECT * FROM clients WHERE id = ?', (client_id,)).fetchone()
        conn.close()
        if not client:
            raise Exception(f"Client {client_id} non trouvé.")

        print(f"--- DÉBUT PIPELINE pour le client : {client['name']} ---")

        # 2. Récupérer l'annonce la plus performante
        print("Récupération de l'annonce la plus performante...")
        facebook_client.init_facebook_api()
        winning_ads = facebook_client.get_winning_ads(
            spend_threshold=client['spend_threshold'],
            cpa_threshold=client['cpa_threshold']
        )
        if not winning_ads:
            raise Exception("Aucune annonce gagnante trouvée pour ce client.")
        
        best_ad = winning_ads[0]
        print(f"Meilleure annonce trouvée : {best_ad.name} (ID: {best_ad.id}) avec un CPA de {best_ad.insights.cpa:.2f}")

        # 3. Créer l'enregistrement du rapport MAINTENANT qu'on a l'ad_id
        conn = database.get_db_connection()
        cursor = conn.execute('INSERT INTO reports (client_id, ad_id, status) VALUES (?, ?, ?)', 
                              (client_id, best_ad.id, 'RUNNING'))
        report_id = cursor.lastrowid
        conn.commit()
        conn.close()
        print(f"Tâche enregistrée dans la DB. Rapport ID: {report_id}")

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

        # 6. Mettre à jour le statut du rapport dans la DB
        conn = database.get_db_connection()
        conn.execute('UPDATE reports SET status = ?, report_path = ? WHERE id = ?', ('COMPLETED', report_path, report_id))
        conn.commit()
        conn.close()
        print(f"--- FIN PIPELINE pour le client : {client['name']} ---")

    except Exception as e:
        print(f"!!! ERREUR PIPELINE pour le client ID {client_id}: {e}")
        traceback.print_exc()
        if report_id:
            conn = database.get_db_connection()
            conn.execute('UPDATE reports SET status = ? WHERE id = ?', ('FAILED', report_id))
            conn.commit()
            conn.close()

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        run_analysis_for_client(int(sys.argv[1]))
    else:
        print("Usage: python pipeline.py <client_id>") 