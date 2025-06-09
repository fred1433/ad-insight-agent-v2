import os
from google import genai
from google.api_core import exceptions

# --- CONFIGURATION ---
# Ces valeurs sont chargées depuis les variables d'environnement ou les configurations gcloud.
# Assurez-vous que votre environnement est configuré.
PROJECT_ID = "nouveau-voxanet"
LOCATION = "us-central1"
MODEL_NAME = "imagen-3.0-generate-002"
# --- FIN CONFIGURATION ---

def generate_image_from_prompt(prompt: str, output_filename: str) -> str | None:
    """
    Génère une seule image à partir d'un prompt en utilisant Imagen sur Vertex AI.

    Args:
        prompt: Le texte descriptif pour l'image à générer.
        output_filename: Le nom du fichier de sortie (sans chemin).

    Returns:
        Le chemin complet vers l'image générée si succès, sinon None.
    """
    # On enrichit le prompt pour de meilleurs résultats et pour éviter le texte
    enhanced_prompt = f"Photographie hyper-réaliste et détaillée de : '{prompt}'. Style cinématique. IMPORTANT : L'image ne doit contenir absolument aucun texte, mot, lettre ou logo."
    
    print(f"🎨 Lancement de la génération d'une image pour le prompt : '{enhanced_prompt[:70]}...'")

    try:
        # Assure que le répertoire de sortie existe
        output_dir = "tmp"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        full_output_path = os.path.join(output_dir, output_filename)

        client = genai.Client(project=PROJECT_ID, location=LOCATION)

        config = genai.types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio="1:1"
        )

        response = client.models.generate_images(
            model=MODEL_NAME,
            prompt=enhanced_prompt,
            config=config
        )

        if response.generated_images:
            response.generated_images[0].image.save(full_output_path)
            print(f"✅ Image sauvegardée avec succès : {full_output_path}")
            return full_output_path
        else:
            print("⚠️ La génération d'image n'a retourné aucun résultat.")
            return None

    except Exception as e:
        print(f"❌ Une erreur est survenue lors de la génération de l'image : {e}")
        return None 