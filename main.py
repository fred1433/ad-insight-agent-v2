import os
import base64
import facebook_client
from video_downloader import VideoDownloader
from config import config
import gemini_analyzer

def generate_html_report(analyzed_ads):
    """Génère un rapport HTML autonome pour une liste de publicités analysées."""
    
    # CSS pour un style professionnel
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
        .analysis { margin-top: 20px; line-height: 1.6; white-space: pre-wrap; }
        .grid-container { display: grid; grid-template-columns: 1fr 1fr; gap: 40px; align-items: start;}
        @media (max-width: 768px) { .grid-container { grid-template-columns: 1fr; } }
    </style>
    """

    ad_sections_html = ""
    for item in analyzed_ads:
        ad = item['ad']
        analysis_text = item['analysis_text']
        video_path = item['video_path']
        
        try:
            with open(video_path, "rb") as video_file:
                video_b64 = base64.b64encode(video_file.read()).decode('utf-8')
            video_html = f'<video controls width="100%"><source src="data:video/mp4;base64,{video_b64}" type="video/mp4">Tu navegador no soporta la etiqueta de video.</video>'
        except Exception as e:
            print(f"Advertencia: No se pudo incrustar el video para {ad.id}. {e}")
            video_html = "<p><i>Error al incrustar el video.</i></p>"

        insights = ad.insights
        kpi_table = f"""
        <table>
            <tr><th>Métrica</th><th class="kpi-value">Valor</th></tr>
            <tr><td>Inversión (Spend)</td><td class="kpi-value">{insights.spend:,.2f} €</td></tr>
            <tr><td>Costo por Compra (CPA)</td><td class="kpi-value">{insights.cpa:,.2f} €</td></tr>
            <tr><td>Número de Compras</td><td class="kpi-value">{insights.website_purchases}</td></tr>
            <tr><td>Valor de las Compras</td><td class="kpi-value">{insights.website_purchases_value:,.2f} €</td></tr>
            <tr><td>ROAS</td><td class="kpi-value">{insights.roas:.2f}x</td></tr>
            <tr><td>CPM</td><td class="kpi-value">{insights.cpm:,.2f} €</td></tr>
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
                    <h3>Video del Anuncio</h3>
                    {video_html}
                </div>
                <div>
                    <h3>Indicadores Clave (KPIs)</h3>
                    {kpi_table}
                </div>
            </div>
            <div>
                <h3>Análisis Cualitativo del Experto IA</h3>
                <div class="analysis">{analysis_text}</div>
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
    Point d'entrée principal du script.
    Orchestre le processus de récupération, analyse et génération de rapport.
    """
    print("🚀 Iniciando el pipeline de análisis de anuncios...")

    print("\\n--- Paso 1: Recuperando Anuncios ---")
    winning_ads = facebook_client.get_winning_ads()
    if not winning_ads:
        print("✅ No se encontraron anuncios. El script finaliza.")
        return
    
    video_ads = [ad for ad in winning_ads if ad.video_id]
    if not video_ads:
        print("✅ No se encontraron anuncios de video. El script finaliza.")
        return

    ads_to_process = video_ads[:5]
    print(f"\\n🔬 Se procesarán {len(ads_to_process)} anuncios ganadores.")

    downloader = VideoDownloader()
    analyzed_ads_data = []
    
    for ad in ads_to_process:
        local_video_path = None
        try:
            print(f"\\n--- Procesando anuncio: {ad.name} ({ad.id}) ---")
            local_video_path = downloader.download_video_locally(
                video_id=ad.video_id, ad_id=ad.id
            )
            if not local_video_path:
                raise Exception("Fallo en la descarga del video.")

            analysis_report_text = gemini_analyzer.analyze_video(
                video_path=local_video_path,
                ad_data=ad
            )
            
            analyzed_ads_data.append({
                "ad": ad,
                "analysis_text": analysis_report_text,
                "video_path": local_video_path
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
        print("\\n--- Limpieza de archivos de video temporales ---")
        for item in analyzed_ads_data:
            path_to_clean = item.get('video_path')
            if path_to_clean and os.path.exists(path_to_clean):
                print(f"  🗑️ Eliminando '{path_to_clean}'...")
                os.remove(path_to_clean)
        print("✅ Limpieza completada.")


if __name__ == '__main__':
    main() 