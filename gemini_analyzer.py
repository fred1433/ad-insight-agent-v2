import os
import time
import json
import google.generativeai as genai
from dotenv import load_dotenv

# Charger les variables d'environnement pour que le module puisse être utilisé seul
load_dotenv()

def analyze_video(video_path: str) -> dict:
    """
    Analyse une vidéo locale en utilisant l'API Google AI (avec clé API).
    Cette fonction uploade la vidéo, envoie un prompt détaillé pour une analyse
    publicitaire, et retourne le résultat structuré sous forme de dictionnaire.

    Args:
        video_path: Le chemin local vers le fichier vidéo.

    Returns:
        Un dictionnaire contenant l'analyse structurée, ou un dictionnaire d'erreur.
    """
    print("  🧠 Lancement de l'analyse vidéo avec Gemini...")
    video_file = None # Initialiser au cas où l'upload échoue

    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("La clé d'API GEMINI_API_KEY n'a pas été trouvée dans le fichier .env")

        model_name = os.getenv("GEMINI_MODEL_NAME")
        if not model_name:
            raise ValueError("Le nom du modèle GEMINI_MODEL_NAME n'a pas été trouvé dans le fichier .env")

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)

        print(f"    ▶️ Upload de la vidéo '{os.path.basename(video_path)}'...")
        video_file = genai.upload_file(path=video_path, display_name="Analyse publicitaire")
        
        # Attendre que la vidéo soit prête pour l'analyse
        while video_file.state.name == "PROCESSING":
            time.sleep(5)
            video_file = genai.get_file(video_file.name)
        
        if video_file.state.name == "FAILED":
             raise ValueError(f"Le traitement de la vidéo {video_file.name} a échoué.")

        prompt = """
        Analyse la publicité vidéo fournie et retourne un rapport détaillé au format JSON.
        Le JSON doit avoir la structure suivante :
        {
          "transcription": "La transcription intégrale et textuelle de toute parole. Si vide, retourne une chaîne vide.",
          "hook_analysis": {
            "description": "Une description de ce qui se passe dans les 3 premières secondes (visuels et sonores) pour capter l'attention.",
            "effectiveness_score": "Une note de 1 à 10 sur l'efficacité perçue du hook."
          },
          "shot_changes": [
            { "timestamp": "00:02", "description": "Description de la scène au moment du changement de plan." },
            { "timestamp": "00:05", "description": "Description de la nouvelle scène." }
          ],
          "on_screen_text": [
            { "text": "50% de réduction", "timestamp": "00:07" }
          ],
          "visual_elements": {
            "main_characters": "Description des personnages principaux ou acteurs.",
            "setting": "Description du lieu et de l'environnement.",
            "key_objects": ["Liste", "des", "objets", "importants", "montrés"],
            "logo_mentions": "Description des moments où le logo de la marque apparaît."
          },
          "audio_elements": {
            "music_style": "Description du style de musique de fond (épique, joyeuse, etc.).",
            "sound_effects": ["Liste", "des", "effets", "sonores", "marquants"]
          },
          "narrative_summary": "Un résumé concis de l'histoire racontée par la publicité.",
          "call_to_action": "Description de l'appel à l'action final (ex: 'Visitez notre site', 'Téléchargez l'application').",
          "target_audience": "Description du public cible probable de cette publicité.",
          "overall_feeling": "Le sentiment général ou l'émotion que la publicité cherche à provoquer (confiance, urgence, joie, etc.)."
        }
        Ne retourne rien d'autre que le JSON lui-même.
        """

        print("    ▶️ Envoi du prompt et de la vidéo au modèle...")
        response = model.generate_content([prompt, video_file])

        print("    ✅ Réponse reçue !")
        
        # Nettoyage du fichier uploadé sur les serveurs de Google
        genai.delete_file(video_file.name)
        video_file = None # Le fichier distant n'existe plus

        # Extraire et parser le JSON
        json_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(json_text)

    except Exception as e:
        print(f"    ❌ Une erreur est survenue lors de l'analyse Gemini : {e}")
        # En cas d'erreur, tenter de supprimer le fichier s'il a été uploadé
        if video_file:
            try:
                genai.delete_file(video_file.name)
            except Exception as delete_error:
                print(f"      Tentative de nettoyage du fichier distant échouée: {delete_error}")
        return {"error": str(e)} 