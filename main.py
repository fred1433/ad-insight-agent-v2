import os
import base64
import facebook_client
from media_downloader import MediaDownloader
from config import config
import gemini_analyzer
import markdown

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
        
        media_html = ""
        try:
            with open(media_path, "rb") as media_file:
                media_b64 = base64.b64encode(media_file.read()).decode('utf-8')
            
            if media_type == 'video':
                media_html = f'<video controls width="100%"><source src="data:video/mp4;base64,{media_b64}" type="video/mp4">Tu navegador no soporta la etiqueta de video.</video>'
            elif media_type == 'image':
                # Détecter le format de l'image pour le data URI
                ext = os.path.splitext(media_path)[1].lower().replace('.', '')
                media_html = f'<img src="data:image/{ext};base64,{media_b64}" alt="Anuncio" style="width:100%; height:auto; border-radius: 4px;">'

        except Exception as e:
            print(f"Advertencia: No se pudo incrustar el medio para {ad.id}. {e}")
            media_html = "<p><i>Error al incrustar el medio.</i></p>"

        insights = ad.insights
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
            <tr><td><b>Tasa de Enganche (Hook Rate)</b></td><td class="kpi-value"><b>{insights.hook_rate:.2f} %</b></td></tr>
            <tr><td><b>Tasa de Retención (Hold Rate)</b></td><td class="kpi-value"><b>{insights.hold_rate:.2f} %</b></td></tr>
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
                <h3>Propuestas de Nuevos Guiones</h3>
                <div class="analysis">{script_html}</div>
            </div>
        </div>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Informe de Análisis de Anuncios</title>
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

    print("\\n--- Paso 1: Recuperando Anuncios ---")
    winning_ads = facebook_client.get_winning_ads()
    if not winning_ads:
        print("✅ No se encontraron anuncios ganadores. El script finaliza.")
        return
    
    # On filtre les publicités qui ont une créative (image ou vidéo) et on prend la première
    ads_with_media = [ad for ad in winning_ads if ad.video_id or ad.image_url]
    ads_to_process = ads_with_media[:1]

    print(f"\\n🔬 Se procesarán {len(ads_to_process)} anuncios ganadores (imágenes o videos).")

    downloader = MediaDownloader()
    analyzed_ads_data = []
    
    for ad in ads_to_process:
        local_media_path = None
        analysis_report_text = None
        media_type = None

        try:
            print(f"\\n--- Procesando anuncio: {ad.name} ({ad.id}) ---")
            
            if ad.video_id:
                media_type = 'video'
                print(f"  ▶️ Es un anuncio de video (ID: {ad.video_id}).")
                local_media_path = downloader.download_video_locally(
                    video_id=ad.video_id, ad_id=ad.id
                )
            elif ad.image_url:
                media_type = 'image'
                print(f"  ▶️ Es un anuncio de imagen (URL: {ad.image_url[:60]}...).")
                local_media_path = downloader.download_image_locally(
                    image_url=ad.image_url, ad_id=ad.id
                )
            else:
                print("  ⚠️ La publicidad no contiene ni video_id ni image_url. Omitiendo.")
                continue

            if not local_media_path:
                raise Exception("Fallo en la descarga del medio.")

            # La réponse du LLM contient maintenant l'analyse ET les scripts
            full_response = ""
            if media_type == 'video':
                full_response = gemini_analyzer.analyze_video(
                    video_path=local_media_path, ad_data=ad
                )
            elif media_type == 'image':
                 full_response = gemini_analyzer.analyze_image(
                    image_path=local_media_path, ad_data=ad
                )
            
            # On sépare l'analyse et les scripts
            analysis_part = ""
            script_part = ""
            if "---" in full_response:
                parts = full_response.split("---", 1)
                analysis_part = parts[0].strip()
                script_part = parts[1].strip()
            else:
                analysis_part = full_response # Fallback

            analyzed_ads_data.append({
                "ad": ad,
                "analysis_text": analysis_part,
                "script_text": script_part,
                "media_path": local_media_path,
                "media_type": media_type
            })

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
    finally:
        print("\\n--- Limpieza de archivos de medios temporales ---")
        for item in analyzed_ads_data:
            path_to_clean = item.get('media_path')
            if path_to_clean and os.path.exists(path_to_clean):
                print(f"  🗑️ Eliminando '{path_to_clean}'...")
                os.remove(path_to_clean)
        print("✅ Limpieza completada.")


if __name__ == '__main__':
    main() 

    