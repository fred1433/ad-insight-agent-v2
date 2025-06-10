import os
import base64
import re
import json # Importer json pour le cache
import facebook_client
from media_downloader import MediaDownloader
from config import config
import gemini_analyzer
import image_generator
import markdown

CACHE_FILE = "analysis_cache.json"

def load_cache():
    """Charge le cache depuis le fichier s'il existe."""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_cache(cache_data):
    """Sauvegarde les données dans le fichier cache."""
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, indent=4)


def generate_html_report(analyzed_ads):
    """Genera un informe HTML autónomo para una lista de anuncios analizados."""
    
    # CSS para un estilo profesional
    css_style = """
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 0; background-color: #f8f9fa; color: #212529; }
        .main-container { max-width: 900px; margin: 40px auto; }
        .ad-container { background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); margin-bottom: 40px; }
        h1, h2, h3 { color: #0056b3; }
        h1 { font-size: 2.8em; text-align: center; margin-bottom: 20px; border-bottom: 2px solid #dee2e6; padding-bottom: 20px; }
        h2 { font-size: 2em; border-bottom: 2px solid #dee2e6; padding-bottom: 10px; }
        h3 { font-size: 1.5em; border-bottom: none; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { border: 1px solid #dee2e6; padding: 12px; text-align: left; }
        th { background-color: #e9ecef; font-weight: 600; }
        .kpi-value { text-align: right; font-weight: bold; font-family: "SFMono-Regular", Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; }
        .analysis { margin-top: 20px; line-height: 1.6; }
        .grid-container { display: grid; grid-template-columns: 1fr 1fr; gap: 40px; align-items: start;}
        .generated-images-grid { display: flex; flex-wrap: wrap; gap: 15px; margin-top: 15px; }
        .generated-images-grid img { width: 100%; max-width: 250px; height: auto; border-radius: 4px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        @media (max-width: 768px) { .grid-container { grid-template-columns: 1fr; } }
    </style>
    """

    ad_sections_html = ""
    for item in analyzed_ads:
        ad = item['ad']
        analysis_html = markdown.markdown(item['analysis_text'], extensions=['tables'])
        script_html = markdown.markdown(item['script_text'], extensions=['tables'])
        media_path = item['media_path']
        media_type = item['media_type']
        generated_image_paths = item.get('generated_image_paths', []) # C'est maintenant une liste

        proposals_title = "Propuestas de Nuevos Guiones" if media_type == 'video' else "Propuestas de Imágenes Alternativas"
        
        media_html = ""
        try:
            with open(media_path, "rb") as media_file:
                media_b64 = base64.b64encode(media_file.read()).decode('utf-8')
            
            if media_type == 'video':
                media_html = f'<video controls width="100%"><source src="data:video/mp4;base64,{media_b64}" type="video/mp4">Tu navegador no soporta la etiqueta de video.</video>'
            elif media_type == 'image':
                ext = os.path.splitext(media_path)[1].lower().replace('.', '')
                media_html = f'<img src="data:image/{ext};base64,{media_b64}" alt="Anuncio" style="width:100%; height:auto; border-radius: 4px;">'

        except Exception as e:
            print(f"Advertencia: No se pudo incrustar el medio para {ad['id']}. {e}")
            media_html = "<p><i>Error al incrustar el medio.</i></p>"

        generated_images_html = ""
        if generated_image_paths:
            generated_images_html += "<h4>Visualización de Conceptos (IA Generativa)</h4><div class='generated-images-grid'>"
            for img_path in generated_image_paths:
                try:
                    with open(img_path, "rb") as img_file:
                        img_b64 = base64.b64encode(img_file.read()).decode('utf-8')
                    img_ext = os.path.splitext(img_path)[1].lower().replace('.', '')
                    generated_images_html += f'<img src="data:image/{img_ext};base64,{img_b64}" alt="Concepto generado por IA">'
                except Exception as e:
                    print(f"Advertencia: No se pudo incrustar la imagen generada {img_path}. {e}")
            generated_images_html += "</div>"
        
        # On ne traite l'objet `ad` que s'il n'est pas déjà un dictionnaire (provenant du cache)
        ad_id = ad['id'] if isinstance(ad, dict) else ad.id
        ad_name = ad['name'] if isinstance(ad, dict) else ad.name
        insights = ad['insights'] if isinstance(ad, dict) else ad.insights
        
        # Pour le cache, insights est un dictionnaire, pas un objet pydantic
        insights_obj = facebook_client.AdInsights(**insights) if isinstance(insights, dict) else insights

        video_metrics_html = ""
        if media_type == 'video':
            video_metrics_html = f"""
            <tr><td><b>Tasa de Enganche (Hook Rate)</b></td><td class="kpi-value"><b>{insights_obj.hook_rate:.2f} %</b></td></tr>
            <tr><td><b>Tasa de Retención (Hold Rate)</b></td><td class="kpi-value"><b>{insights_obj.hold_rate:.2f} %</b></td></tr>
            """

        kpi_table = f"""
        <table>
            <tr><th>Métrica</th><th class="kpi-value">Valor</th></tr>
            <tr><td>Inversión (Spend)</td><td class="kpi-value">{insights_obj.spend:,.2f} $</td></tr>
            <tr><td>Costo por Compra (CPA)</td><td class="kpi-value">{insights_obj.cpa:,.2f} $</td></tr>
            <tr><td>Número de Compras</td><td class="kpi-value">{insights_obj.website_purchases}</td></tr>
            <tr><td>Valor de las Compras</td><td class="kpi-value">{insights_obj.website_purchases_value:,.2f} $</td></tr>
            <tr><td>ROAS</td><td class="kpi-value">{insights_obj.roas:.2f}x</td></tr>
            <tr><td>CPM</td><td class="kpi-value">{insights_obj.cpm:,.2f} $</td></tr>
            <tr><td>CTR (único)</td><td class="kpi-value">{insights_obj.unique_ctr:.2f} %</td></tr>
            <tr><td>Frecuencia</td><td class="kpi-value">{insights_obj.frequency:.2f}</td></tr>
            {video_metrics_html}
        </table>
        """

        ad_sections_html += f"""
        <div class="ad-container">
            <h2>{ad_name} (ID: {ad_id})</h2>
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
                {generated_images_html}
            </div>
        </div>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Informe de Análisis de Rendimiento de Anuncios</title>
        {css_style}
    </head>
    <body>
        <div class="main-container">
            <h1>Informe de Análisis de Rendimiento de Anuncios</h1>
            {ad_sections_html}
        </div>
    </body>
    </html>
    """
    
    report_path = "informe_anuncios.html"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    return report_path

def main():
    """
    Punto de entrada principal del script.
    Orquesta el proceso de recuperación, análisis y generación de informes.
    """
    print("🚀 Iniciando el pipeline de análisis de anuncios...")

    cache = load_cache()

    print("\\n--- Paso 1: Recuperando Anuncios ---")
    winning_ads = facebook_client.get_winning_ads()
    if not winning_ads:
        print("✅ No se encontraron anuncios ganadores. El script finaliza.")
        return
    
    video_ads = [ad for ad in winning_ads if ad.video_id][:2]
    image_ads = [ad for ad in winning_ads if ad.image_url][:2]
    ads_to_process = video_ads + image_ads

    if not ads_to_process:
        print("✅ No se encontraron anuncios ganadores con vídeo o imagen para procesar. El script finaliza.")
        return

    print(f"\\n🔬 Se procesarán {len(ads_to_process)} anuncios ganadores ({len(video_ads)} vídeos, {len(image_ads)} imágenes).")

    downloader = MediaDownloader()
    analyzed_ads_data = []
    
    for ad in ads_to_process:
        media_needs_redownload = False
        analysis_needed = True
        
        # Vérifier le cache
        if ad.id in cache:
            print(f"\\n--- Verificando cache para el anuncio {ad.id} ---")
            cached_data = cache[ad.id]
            # Vérifier si tous les fichiers nécessaires existent
            media_path_exists = os.path.exists(cached_data['media_path'])
            generated_images_exist = all(os.path.exists(p) for p in cached_data.get('generated_image_paths', []))

            if media_path_exists and generated_images_exist:
                print(f"  ✅ Cache completo y válido encontrado. Saltando análisis.")
                analyzed_ads_data.append(cached_data)
                analysis_needed = False
            else:
                print(f"  ⚠️ Cache incompleto. El medio o las imágenes generadas no existen. Se volverán a descargar.")
                media_needs_redownload = True # On force le re-téléchargement mais on garde l'analyse
                analysis_needed = False # On ne refait pas l'analyse LLM si on a déjà le texte
                
        if analysis_needed or media_needs_redownload:
            try:
                print(f"\\n--- Procesando anuncio: {ad.name} ({ad.id}) ---")
                
                # Étape 1: Assurer la présence du média principal
                if media_needs_redownload:
                    local_media_path = cached_data['media_path']
                    media_type = cached_data['media_type']
                    if not os.path.exists(local_media_path):
                        if media_type == 'video':
                             downloader.download_video_locally(ad.video_id, ad.id)
                        elif media_type == 'image':
                             downloader.download_image_locally(ad.image_url, ad.id)
                else: # Cas nominal: pas dans le cache
                    if ad.video_id:
                        media_type = 'video'
                        print(f"  ▶️ Es un anuncio de video (ID: {ad.video_id}).")
                        local_media_path = downloader.download_video_locally(ad.video_id, ad.id)
                    elif ad.image_url:
                        media_type = 'image'
                        print(f"  ▶️ Es un anuncio de imagen (URL: {ad.image_url[:60]}...).")
                        local_media_path = downloader.download_image_locally(ad.image_url, ad.id)
                    else:
                        continue # Pas de média, on passe au suivant

                if not local_media_path or not os.path.exists(local_media_path):
                    raise Exception("Fallo en la descarga del medio.")

                # Étape 2: Analyse (seulement si nécessaire)
                if analysis_needed:
                    print("\\n--- Paso 2: Analizando con IA de Gemini ---")
                    full_response = ""
                    if media_type == 'video':
                        full_response = gemini_analyzer.analyze_video(local_media_path, ad)
                    elif media_type == 'image':
                        full_response = gemini_analyzer.analyze_image(local_media_path, ad)
                    
                    analysis_part, script_part = (full_response.split("---", 1)[0].strip(), full_response.split("---", 1)[1].strip()) if "---" in full_response else (full_response, "")
                else: # Utiliser l'analyse du cache
                    analysis_part = cached_data['analysis_text']
                    script_part = cached_data['script_text']
                    full_response = analysis_part + " --- " + script_part # Reconstituer pour trouver les prompts

                # Étape 3: Génération d'images
                generated_image_paths = []
                if media_needs_redownload and not generated_images_exist:
                     print("\\n--- Regenerando visuales para los conceptos ---")
                elif analysis_needed:
                    print("\\n--- Paso 3: Buscando y generando visuales para los conceptos ---")

                if analysis_needed or (media_needs_redownload and not generated_images_exist):
                    prompts = re.findall(r"PROMPT_IMG: (.*)", full_response)
                    print(f"  ▶️ {len(prompts)} prompts encontrados.")

                    for i, prompt in enumerate(prompts[:3]): # Limite à 3 générations
                        print(f"    - Procesando prompt {i+1}...")
                        output_filename = f"generated_concept_{ad.id}_{i+1}.png"
                        generated_path = image_generator.generate_image_from_prompt(prompt, output_filename)
                        if generated_path:
                            generated_image_paths.append(generated_path)
                else: # Les images existent déjà
                    generated_image_paths = cached_data['generated_image_paths']

                ad_dict = ad.model_dump()
                current_ad_data = {
                    "ad": ad_dict,
                    "analysis_text": analysis_part,
                    "script_text": script_part,
                    "media_path": local_media_path,
                    "media_type": media_type,
                    "generated_image_paths": generated_image_paths
                }
                analyzed_ads_data.append(current_ad_data)

                # Sauvegarder dans le cache après chaque succès
                cache[ad.id] = current_ad_data
                save_cache(cache)

            except Exception as e:
                print(f"❌ Ocurrió un error al procesar el anuncio {ad.id}: {e}")
        
    if not analyzed_ads_data:
        print("\\n❌ No se pudo analizar ningún anuncio. El script finaliza.")
        return
        
    try:
        report_file = generate_html_report(analyzed_ads_data)
        print(f"\\n🎉 Informe HTML consolidado generado con éxito: '{os.path.abspath(report_file)}'")
    except Exception as e:
        print(f"❌ Ocurrió un error al generar el informe HTML: {e}")
    # finally:
    #     print("\\n--- Limpieza de archivos de medios temporales ---")
    #     all_temp_files = []
    #     for item in analyzed_ads_data:
    #         if item.get('media_path'): all_temp_files.append(item['media_path'])
    #         if item.get('generated_image_paths'): all_temp_files.extend(item['generated_image_paths'])
        
    #     for path_to_clean in set(all_temp_files): # Utiliser set pour éviter les doublons
    #         if path_to_clean and os.path.exists(path_to_clean):
    #             # print(f"  🗑️ Eliminando '{path_to_clean}'...")
    #             os.remove(path_to_clean)
    #     print("✅ Limpieza completada.")


if __name__ == '__main__':
    main() 

    