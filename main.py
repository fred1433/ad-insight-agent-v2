import os
import facebook_client
from video_downloader import VideoDownloader
from config import config

def main():
    """
    Point d'entrée principal du script.
    Orchestre le processus de récupération des publicités, de téléchargement des vidéos
    et d'analyse.
    """
    print("🚀 Démarrage du pipeline d'analyse des publicités...")

    # 1. Récupérer les publicités gagnantes depuis Facebook
    print("\n--- Étape 1: Récupération des publicités gagnantes ---")
    winning_ads = facebook_client.get_winning_ads()
    if not winning_ads:
        print("✅ Aucune publicité gagnante trouvée. Le script se termine.")
        return
    print(f"📊 {len(winning_ads)} publicité(s) gagnante(s) trouvée(s).")
    for ad in winning_ads:
        print(f"  - Ad ID: {ad.id}, Name: {ad.name}, Video ID: {ad.video_id}")

    # Initialiser les clients nécessaires
    downloader = VideoDownloader()
    # La logique d'analyse sera ajoutée ici plus tard
    # analyzer = google_client.VideoAnalyzer()

    # 2. Traiter chaque publicité gagnante
    print("\n--- Étape 2: Traitement de chaque publicité ---")
    for ad in winning_ads:
        print(f"\n✨ Traitement de la publicité : {ad.id} ({ad.name})")

        # Vérifier si un video_id est présent
        if not ad.video_id:
            print(f"⚠️ Pas de video_id pour la publicité {ad.id}. Passage à la suivante.")
            continue

        # 2a. Télécharger la vidéo et la téléverser sur GCS
        print(f"  📥 Téléchargement de la vidéo (ID: {ad.video_id})...")
        video_gcs_uri = downloader.download_and_upload_video(video_id=ad.video_id, ad_id=ad.id)
        
        if not video_gcs_uri:
            print(f"❌ Échec du téléchargement pour la publicité {ad.id}. Passage à la suivante.")
            continue
        print(f"  ✅ Vidéo téléversée sur GCS : {video_gcs_uri}")

        # 2b. Analyser la vidéo avec les services Google Cloud
        print("  🧠 Lancement de l'analyse vidéo avec Google AI...")
        print("     (Logique d'analyse à implémenter)")
        # try:
        #     analysis_results = analyzer.analyze_video(video_gcs_uri)
        #     print("  ✅ Analyse vidéo terminée.")
        #     # Ici, vous pourriez sauvegarder les `analysis_results`
        #     # dans une base de données ou un fichier.
        #     print("  Résultats de l'analyse :")
        #     print(analysis_results)
        # except Exception as e:
        #     print(f"❌ Erreur lors de l'analyse de la vidéo {video_gcs_uri}: {e}")

    print("\n🎉 Pipeline terminé.")

if __name__ == '__main__':
    main() 