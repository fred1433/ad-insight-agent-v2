import os
from dotenv import load_dotenv
from google import genai
from google.api_core import exceptions
from typing import Tuple

# --- CONFIGURATION ---
# Ces valeurs sont chargées depuis les variables d'environnement ou les configurations gcloud.
# Si vous n'utilisez pas gcloud, assurez-vous de définir GEMINI_API_KEY dans votre .env
PROJECT_ID = "nouveau-voxanet" 
LOCATION = "us-central1"
# Le nom du modèle est maintenant chargé depuis les variables d'environnement
MODEL_NAME = os.getenv("IMAGEN_MODEL_NAME", "imagen-3.0-generate-002")
# --- FIN CONFIGURATION ---

# On charge les variables d'environnement depuis le fichier .env
load_dotenv()

def generate_image_from_prompt(prompt: str, output_filename: str) -> Tuple[str | None, int]:
    """
    Génère une seule image à partir d'un prompt en utilisant Imagen sur Vertex AI.

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

        # Initialisation du client Vertex AI
        # La configuration se fait via les variables d'environnement de gcloud
        # ou via GEMINI_API_KEY dans le .env
        client = genai.Client(project=PROJECT_ID, location=LOCATION)

        config = genai.types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio="1:1",
            # Vous pouvez ajouter d'autres paramètres ici si nécessaire
        )
        
        print(f"  🖼️  Génération d'image avec le modèle '{MODEL_NAME}' et le prompt : \"{prompt[:80]}...\"")
        
        # Génération de l'image
        response = client.models.generate_images(
            model=MODEL_NAME,
            prompt=enhanced_prompt,
            config=config
        )

        if response.generated_images:
            response.generated_images[0].image.save(full_output_path)
            print(f"✅ Image sauvegardée avec succès : {full_output_path}")
            return full_output_path, len(response.generated_images)
        else:
            print("⚠️ La génération d'image n'a retourné aucun résultat.")
            return None, 0

    except Exception as e:
        print(f"❌ Une erreur est survenue lors de la génération de l'image : {e}")
        return None, 0 