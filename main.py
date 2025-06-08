import os
import facebook_client
import gvi_analyzer
import pprint
from video_downloader import VideoDownloader
from config import config
from google.cloud import storage

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

    # Filtrer pour ne garder que les publicités avec une vidéo
    video_ads = [ad for ad in winning_ads if ad.video_id]
    if not video_ads:
        print("✅ Aucune publicité vidéo parmi les gagnantes. Le script se termine.")
        return
        
    for ad in winning_ads:
        print(f"  - Ad ID: {ad.id}, Name: {ad.name}, Video ID: {ad.video_id}")

    # Limiter le nombre de vidéos à traiter pour les tests
    ads_to_process = video_ads
    if config.script.max_ads_per_run > 0:
        print(f"\n🔬 Mode test : Traitement limité à {config.script.max_ads_per_run} vidéo(s).")
        ads_to_process = video_ads[:config.script.max_ads_per_run]

    # Initialiser les clients nécessaires
    downloader = VideoDownloader()
    gcs_client = storage.Client()
    bucket = gcs_client.bucket(config.google.gcs_bucket_name)

    # 2. Traiter chaque publicité gagnante
    print("\n--- Étape 2: Traitement de chaque publicité ---")
    for ad in ads_to_process:
        print(f"\n{'*' * 40}")
        print(f"✨ Traitement de la publicité : {ad.id} ({ad.name})")
        print(f"  - 📺 URL Facebook : https://www.facebook.com/watch/?v={ad.video_id}")
        print(f"{'*' * 40}")

        gcs_object_name = f"{ad.id}.mp4"
        gcs_uri = f"gs://{config.google.gcs_bucket_name}/{gcs_object_name}"
        blob = bucket.blob(gcs_object_name)

        # 2a. Vérifier si la vidéo est déjà sur GCS, sinon la télécharger
        if blob.exists():
            print(f"  ✅ Vidéo déjà présente sur GCS : {gcs_uri}. Saut de l'étape de téléchargement.")
            video_gcs_uri = gcs_uri
        else:
            print(f"  📥 Téléchargement de la vidéo (ID: {ad.video_id})...")
            video_gcs_uri = downloader.download_and_upload_video(video_id=ad.video_id, ad_id=ad.id)
        
        if not video_gcs_uri:
            print(f"❌ Échec de la récupération de la vidéo pour la publicité {ad.id}. Passage à la suivante.")
            continue
        
        # 2b. Analyser la vidéo avec les services Google Cloud
        print("\n  🧠 Lancement de l'analyse visuelle avec GVI...")
        try:
            analysis_results = gvi_analyzer.extract_annotations(
                gcs_uri=video_gcs_uri
            )
            print("  ✅ Analyse visuelle GVI terminée.")
            print("  Résultats de l'analyse visuelle :")
            pprint.pprint(analysis_results)
        except Exception as e:
            print(f"❌ Erreur lors de l'analyse visuelle de la vidéo {video_gcs_uri}: {e}")

    print("\n🎉 Pipeline terminé.")

if __name__ == '__main__':
    main() 