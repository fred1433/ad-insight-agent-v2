import os
import base64
import facebook_client
from video_downloader import VideoDownloader
from config import config
import gemini_analyzer

def generate_html_report(ad, analysis_text, video_path):
    """Génère un rapport HTML autonome pour une seule publicité."""
    
    # Encoder la vidéo en base64 pour l'intégrer directement dans le HTML
    try:
        with open(video_path, "rb") as video_file:
            video_b64 = base64.b64encode(video_file.read()).decode('utf-8')
        video_html = f'<video controls width="100%"><source src="data:video/mp4;base64,{video_b64}" type="video/mp4">Your browser does not support the video tag.</video>'
    except Exception as e:
        print(f"Warning: Could not embed video. {e}")
        video_html = "<p><i>Erreur lors de l'intégration de la vidéo.</i></p>"

    # CSS pour un style professionnel
    css_style = """
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 40px; background-color: #f8f9fa; color: #212529; }
        .container { max-width: 900px; margin: auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
        h1, h2, h3 { color: #0056b3; border-bottom: 2px solid #dee2e6; padding-bottom: 10px; }
        h1 { font-size: 2.5em; }
        h2 { font-size: 2em; }
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

    # Structure du tableau des KPIs
    insights = ad.insights
    kpi_table = f"""
    <table>
        <tr><th>Métrique</th><th class="kpi-value">Valeur</th></tr>
        <tr><td>Dépense (Spend)</td><td class="kpi-value">{insights.spend:,.2f} €</td></tr>
        <tr><td>Coût par Achat (CPA)</td><td class="kpi-value">{insights.cpa:,.2f} €</td></tr>
        <tr><td>Nombre d'achats</td><td class="kpi-value">{insights.website_purchases}</td></tr>
        <tr><td>Valeur des achats</td><td class="kpi-value">{insights.website_purchases_value:,.2f} €</td></tr>
        <tr><td>ROAS</td><td class="kpi-value">{insights.roas:.2f}x</td></tr>
        <tr><td>CPM</td><td class="kpi-value">{insights.cpm:,.2f} €</td></tr>
        <tr><td>CTR (unique)</td><td class="kpi-value">{insights.unique_ctr:.2f} %</td></tr>
        <tr><td>Fréquence</td><td class="kpi-value">{insights.frequency:.2f}</td></tr>
        <tr><td><b>Taux d'accroche (Hook Rate)</b></td><td class="kpi-value"><b>{insights.hook_rate:.2f} %</b></td></tr>
        <tr><td><b>Taux de rétention (Hold Rate)</b></td><td class="kpi-value"><b>{insights.hold_rate:.2f} %</b></td></tr>
    </table>
    """

    # Assemblage final du HTML
    html_content = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Rapport d'analyse de publicité</title>
        {css_style}
    </head>
    <body>
        <div class="container">
            <h1>Rapport d'Analyse de Performance</h1>
            <h2>{ad.name} (ID: {ad.id})</h2>

            <div class="grid-container">
                <div>
                    <h3>Vidéo Publicitaire</h3>
                    {video_html}
                </div>
                <div>
                    <h3>Indicateurs Clés (KPIs)</h3>
                    {kpi_table}
                </div>
            </div>

            <div>
                <h3>Analyse Qualitative de l'Expert IA</h3>
                <div class="analysis">{analysis_text}</div>
            </div>
        </div>
    </body>
    </html>
    """
    
    report_path = "report.html"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    return report_path


def main():
    """
    Point d'entrée principal du script.
    Orchestre le processus de récupération, analyse et génération de rapport.
    """
    print("🚀 Démarrage du pipeline d'analyse des publicités...")

    # 1. Récupérer les publicités depuis Facebook
    print("\n--- Étape 1: Récupération des publicités ---")
    winning_ads = facebook_client.get_winning_ads()
    if not winning_ads:
        print("✅ Aucune publicité trouvée. Le script se termine.")
        return
    
    video_ads = [ad for ad in winning_ads if ad.video_id]
    if not video_ads:
        print("✅ Aucune publicité vidéo trouvée. Le script se termine.")
        return

    # Limiter le nombre de vidéos à traiter pour le test
    ad_to_process = video_ads[0]
    print(f"\n🔬 Traitement de la première publicité gagnante : {ad_to_process.name}")

    downloader = VideoDownloader()
    local_video_path = None
    
    try:
        # 2. Télécharger la vidéo en local
        local_video_path = downloader.download_video_locally(
            video_id=ad_to_process.video_id, ad_id=ad_to_process.id
        )
        if not local_video_path:
            raise Exception("Échec du téléchargement de la vidéo.")

        # 3. Analyser la vidéo avec Gemini
        analysis_report_text = gemini_analyzer.analyze_video(
            video_path=local_video_path,
            ad_data=ad_to_process
        )
        
        # 4. Générer le rapport HTML
        report_file = generate_html_report(ad_to_process, analysis_report_text, local_video_path)
        print(f"\n🎉 Rapport HTML généré avec succès : '{os.path.abspath(report_file)}'")

    except Exception as e:
        print(f"❌ Une erreur est survenue dans le pipeline principal : {e}")
    
    finally:
        # 5. Nettoyer le fichier vidéo local
        if local_video_path and os.path.exists(local_video_path):
            print(f"  🗑️ Nettoyage du fichier local '{local_video_path}'...")
            os.remove(local_video_path)
            print("  ✅ Fichier local supprimé.")

if __name__ == '__main__':
    main() 