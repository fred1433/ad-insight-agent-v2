import os
from dotenv import load_dotenv
import google.generativeai as genai
from google.api_core import exceptions
from typing import Tuple

# --- CONFIGURATION ---
# Le nom du modèle et la clé API sont maintenant chargés depuis les variables d'environnement.
MODEL_NAME = os.getenv("IMAGEN_MODEL_NAME", "imagen-3.0-generate-002")
# --- FIN CONFIGURATION ---

# On charge les variables d'environnement depuis le fichier .env
load_dotenv()

# Configuration de l'API Gemini directement avec la clé.
# Cette ligne doit être exécutée après load_dotenv()
# genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def generate_image_from_prompt(prompt: str, output_filename: str) -> Tuple[str | None, int]:
    """
    Génère UNE image à partir d'un prompt en utilisant l'API Gemini.

    Args:
        prompt: Le prompt textuel pour la génération.
        output_filename: Le nom du fichier de sortie (sans chemin).

    Returns:
         Un tuple contenant (chemin_du_fichier_sauvegardé, nombre_images_générées).
         Retourne (None, 0) si une erreur survient.
    """
    print(f"  🖼️  Génération d'image avec le modèle '{MODEL_NAME}' et le prompt : \"{prompt[:80]}...\"")
    try:
        # S'assurer que la clé API est configurée
        genai.configure(api_key=os.getenv("GEMINI_API_KEY").strip('\'"'))
        
        # Instancier le modèle 
        model = genai.GenerativeModel(model_name=MODEL_NAME)
        # La méthode correcte est generate_content, qui prend directement le prompt
        response = model.generate_content(prompt)

        # Créer le répertoire de sortie s'il n'existe pas
        output_dir = "tmp"
        os.makedirs(output_dir, exist_ok=True)
        
        # La réponse contient une liste de "parts". Pour la génération d'une seule image,
        # nous accédons à la première part et à ses données binaires.
        generated_image_part = response.parts[0]
        output_path = os.path.join(output_dir, output_filename)
        
        with open(output_path, 'wb') as f:
            f.write(generated_image_part.data)
            
        print(f"  ✅ Image sauvegardée : {output_path}")
        # On retourne le nombre de parts de type image générées
        return output_path, len(response.parts)

    except Exception as e:
        print(f"❌ Une erreur est survenue lors de la génération de l'image : {e}")
        return None, 0 