import requests
from google.cloud import storage
from google.api_core.exceptions import GoogleAPICallError
from typing import Optional

from config import config

def upload_video_to_gcs(video_url: str, ad_id: str) -> Optional[str]:
    """
    Télécharge une vidéo depuis une URL et la téléverse sur Google Cloud Storage.
    Retourne l'URI GCS de la vidéo.
    """
    try:
        # Initialiser le client GCS
        storage_client = storage.Client()
        bucket = storage_client.bucket(config.google.gcs_bucket_name)
        
        # Télécharger le contenu de la vidéo en streaming
        response = requests.get(video_url, stream=True)
        response.raise_for_status() # Lève une exception si le statut est une erreur

        # Définir le nom du fichier sur GCS
        destination_blob_name = f"{ad_id}.mp4"
        blob = bucket.blob(destination_blob_name)
        
        # Téléverser le contenu
        blob.upload_from_string(
            response.content,
            content_type='video/mp4'
        )

        gcs_uri = f"gs://{config.google.gcs_bucket_name}/{destination_blob_name}"
        print(f"Vidéo téléversée avec succès sur GCS : {gcs_uri}")
        return gcs_uri

    except requests.exceptions.RequestException as e:
        print(f"Erreur lors du téléchargement de la vidéo depuis l'URL : {e}")
        return None
    except GoogleAPICallError as e:
        print(f"Erreur lors du téléversement sur Google Cloud Storage : {e}")
        print("Veuillez vous assurer que vos identifiants GOOGLE_APPLICATION_CREDENTIALS sont corrects et valides.")
        return None
    except Exception as e:
        print(f"Une erreur inattendue est survenue lors du processus de téléversement : {e}")
        return None 