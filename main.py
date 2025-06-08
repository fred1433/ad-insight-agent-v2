import os
import pprint
import json

import facebook_client
from video_downloader import VideoDownloader
from config import config
import gemini_analyzer

def main():
    """
    Point d'entrée principal du script.
    Orchestre le processus de récupération des publicités, de téléchargement et d'analyse.
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

    # Limiter le nombre de vidéos à traiter pour les tests
    ads_to_process = video_ads
    if config.script.max_ads_per_run > 0:
        print(f"\n🔬 Mode test : Traitement limité à {config.script.max_ads_per_run} vidéo(s).")
        ads_to_process = video_ads[:config.script.max_ads_per_run]

    downloader = VideoDownloader()
    os.makedirs("reports", exist_ok=True)

    # 2. Traiter chaque publicité
    print("\n--- ÉTAPE 2 : TEST DE COLLECTE DE DONNÉES UNIQUEMENT ---")
    if ads_to_process:
        print("Affichage des métriques pour la première publicité trouvée...")
        first_ad = ads_to_process[0]
        print(f"  - Ad ID: {first_ad.id}")
        print(f"  - Ad Name: {first_ad.name}")
        
        print("\n--- Données collectées ---")
        if first_ad.insights:
            # Utilise pprint pour un affichage lisible du dictionnaire des insights
            pprint.pprint(first_ad.insights.model_dump())
        else:
            print("Aucun insight trouvé pour cette publicité.")

    # --- L'ancien traitement est mis en commentaire pour le test ---
    # for ad in ads_to_process:
    #     print(f"\n{'*' * 20} Traitement de la publicité {ad.id} {'*' * 20}")

    #     # 2a. Télécharger la vidéo en local
    #     local_video_path = downloader.download_video_locally(video_id=ad.video_id, ad_id=ad.id)
        
    #     if not local_video_path:
    #         print(f"❌ Échec du téléchargement pour la publicité {ad.id}. Passage à la suivante.")
    #         continue
        
    #     # 2b. Analyser la vidéo avec Gemini
    #     try:
    #         analysis_report_text = gemini_analyzer.analyze_video(
    #             video_path=local_video_path,
    #             ad_data=ad
    #         )
            
    #         # Sauvegarder le rapport texte dans un fichier markdown
    #         report_path = f"reports/{ad.id}.md"
    #         with open(report_path, "w", encoding="utf-8") as f:
    #             f.write(f"# Analyse Marketing de la Publicité: {ad.name} (ID: {ad.id})\\n\\n")
    #             f.write(analysis_report_text)
            
    #         print(f"  ✅ Analyse terminée et sauvegardée dans '{report_path}'.")
    #         print("\n--- DÉBUT DU RAPPORT ---")
    #         print(analysis_report_text)
    #         print("--- FIN DU RAPPORT ---\\n")

    #     except Exception as e:
    #         print(f"❌ Erreur lors de l'analyse Gemini pour la vidéo {local_video_path}: {e}")
        
    #     finally:
    #         # 2c. Nettoyer le fichier vidéo local
    #         print(f"  🗑️ Nettoyage du fichier local '{local_video_path}'...")
    #         os.remove(local_video_path)
    #         print("  ✅ Fichier local supprimé.")

    print("\n🎉 Pipeline terminé.")

if __name__ == '__main__':
    main() 