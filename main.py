import pprint
import facebook_client
import video_analyzer
import database

def main():
    """
    Fonction principale du script.
    """
    # S'assurer que la base de données est prête
    database.init_db()
    
    print("Récupération et filtrage des publicités 'gagnantes' depuis l'API Facebook...")
    winning_ads = facebook_client.get_winning_ads()
    
    if not winning_ads:
        print("\nℹ️ Aucune nouvelle publicité 'gagnante' à analyser.")
        return

    print(f"\n✅ {len(winning_ads)} publicité(s) gagnante(s) trouvée(s). Début de l'analyse...")
    print("-" * 30)

    for ad in winning_ads:
        print(f"\nTraitement de la publicité : {ad.name} ({ad.id})")

        # 1. Vérifier si l'analyse est récente
        if database.is_recently_analyzed(ad.id):
            print(f"↪️ Analyse récente déjà trouvée dans la base de données. On passe.")
            continue

        if not ad.video_id:
            print("⚠️ Cette publicité n'a pas de vidéo associée. On passe.")
            continue

        # 2. Récupérer l'URL de la vidéo
        print("Récupération de l'URL de la vidéo...")
        video_url = facebook_client.get_video_download_url(ad.video_id)
        if not video_url:
            print("❌ Impossible de récupérer l'URL de la vidéo. On passe.")
            continue
        
        # 3. Téléverser la vidéo sur GCS
        print("Téléversement de la vidéo sur Google Cloud Storage...")
        gcs_uri = video_analyzer.upload_video_to_gcs(video_url, ad.id)
        if not gcs_uri:
            print("❌ Échec du téléversement sur GCS. On passe à la suivante.")
            continue

        # 4. Sauvegarder les métriques et l'URI GCS dans la BDD
        print("Sauvegarde des résultats dans la base de données...")
        database.save_analysis(ad, gcs_uri)
        print(f"✅ Analyse de la publicité {ad.id} terminée et sauvegardée.")

    print("\n🎉 Toutes les publicités ont été traitées.")

if __name__ == "__main__":
    main() 