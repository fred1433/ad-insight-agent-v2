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
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def generate_image_from_prompt(prompt: str, output_filename: str) -> Tuple[str | None, int]:
    """
    Génère une seule image à partir d'un prompt en utilisant Imagen via l'API Gemini.

    Args:
        prompt: Le texte descriptif pour générer l'image.
        output_filename: Le nom du fichier de sortie (sans chemin).

    Returns:
        Un tuple contenant le chemin de l'image et le nombre d'images générées (0 ou 1).
    """
    # On enrichit le prompt pour de meilleurs résultats et pour éviter le texte
    enhanced_prompt = f"Photographie hyper-réaliste et détaillée de : '{prompt}'. Style cinématique. IMPORTANT : L'image ne doit contenir absolument aucun texte, mot, lettre ou logo."

    try:
        # Assure que le répertoire de sortie existe
        output_dir = "tmp"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        full_output_path = os.path.join(output_dir, output_filename)

        # L'initialisation du client n'est plus nécessaire car on a utilisé genai.configure()
        
        print(f"  🖼️  Génération d'image avec le modèle '{MODEL_NAME}' et le prompt : \"{prompt[:80]}...\"")
        
        # Génération de l'image
        response = genai.generate_images(
            model=MODEL_NAME,
            prompt=enhanced_prompt,
            # Le nombre d'images est maintenant un paramètre direct
            number_of_images=1,
        )

        # La nouvelle API retourne une liste d'objets GeneratedImage
        if response.images:
            # On accède aux données binaires de l'image via ._image_bytes
            with open(full_output_path, 'wb') as f:
                f.write(response.images[0]._image_bytes)
                
            print(f"✅ Image sauvegardée avec succès : {full_output_path}")
            return full_output_path, len(response.images)
        else:
            print("⚠️ La génération d'image n'a retourné aucun résultat.")
            return None, 0

    except Exception as e:
        print(f"❌ Une erreur est survenue lors de la génération de l'image : {e}")
        return None, 0 