import os
import time
from typing import Dict
import google.generativeai as genai
from dotenv import load_dotenv

# Import pour le typage, géré de manière souple
try:
    from facebook_client import Ad
except ImportError:
    Ad = Dict

# Charger les variables d'environnement
load_dotenv()

def _format_ad_metrics_for_prompt(ad_data: Ad) -> str:
    """Met en forme les métriques de la publicité pour une injection propre dans le prompt."""
    if not ad_data or not ad_data.insights:
        return "Pas de données de performance fournies."
    
    insights = ad_data.insights
    metrics = [
        f"- Dépense totale (Spend): {getattr(insights, 'spend', 'N/A'):.2f} €",
        f"- Coût par Achat (CPA): {getattr(insights, 'cpa', 'N/A'):.2f} €",
    ]
    # Ajoutons les métriques supplémentaires si elles existent, sans causer d'erreur
    if hasattr(insights, 'ctr'):
        metrics.append(f"- Taux de Clic (CTR): {insights.ctr:.2f}%")
    if hasattr(insights, 'cpm'):
        metrics.append(f"- Coût pour 1000 Impressions (CPM): {insights.cpm:.2f} €")
        
    return "\\n".join(metrics)


def analyze_video(video_path: str, ad_data: Ad) -> str:
    """
    Analyse une vidéo et ses métriques pour fournir une explication textuelle de sa performance.

    Args:
        video_path: Le chemin local vers le fichier vidéo.
        ad_data: L'objet contenant les données de la publicité (nom, insights, etc.).

    Returns:
        Une chaîne de caractères contenant l'analyse marketing, ou un message d'erreur.
    """
    print(f"  🧠 Lancement de l'analyse marketing pour la publicité '{ad_data.name}'...")
    video_file = None

    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("La clé d'API GEMINI_API_KEY n'est pas trouvée.")

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL_NAME"))

        print(f"    ▶️ Upload de la vidéo '{os.path.basename(video_path)}'...")
        video_file = genai.upload_file(path=video_path, display_name=f"Ad: {ad_data.id}")
        
        while video_file.state.name == "PROCESSING":
            time.sleep(5)
            video_file = genai.get_file(video_file.name)
        
        if video_file.state.name == "FAILED":
             raise ValueError(f"Le traitement de la vidéo {video_file.name} a échoué.")

        # --- Construction du Prompt Simplifié ---
        metrics_text = _format_ad_metrics_for_prompt(ad_data)
        
        prompt = f"""
        **Contexte:** Tu es un expert en stratégie marketing digital, spécialisé dans l'analyse de publicités vidéo sur les réseaux sociaux. On te présente une publicité vidéo qui est considérée comme "gagnante" ainsi que ses métriques de performance clés.

        **Métrique de la Publicité Gagnante:**
        {metrics_text}

        **Ta Mission:**
        Analyse la vidéo fournie à la lumière de ses performances. Rédige une analyse concise et percutante expliquant **POURQUOI** cette publicité a fonctionné. Ta réponse doit être directement exploitable par un professionnel du marketing.

        **Points à couvrir dans ton analyse (sans forcément suivre cette structure) :**
        - **Le Hook (Accroche) :** Comment les 3 premières secondes captent-elles l'attention ?
        - **La Narration :** Quelle histoire est racontée ? Est-elle claire et convaincante ?
        - **Les Éléments Visuels et le Rythme :** Le style visuel et le montage servent-ils le message ?
        - **La Proposition de Valeur :** Le bénéfice pour le client est-il évident ?
        - **L'Appel à l'Action (CTA) :** Le CTA est-il clair et incitatif ?
        - **Corrélation :** Fais le lien entre des éléments spécifiques de la vidéo et les bonnes métriques (ex: "Le hook percutant explique probablement le bon CTR", "La clarté de l'offre justifie le CPA bas").

        **Format de Réponse Attendu:**
        Un texte fluide, rédigé et professionnel. Pas de JSON. Commence directement par ton analyse.
        """

        print("    ▶️ Envoi du prompt simplifié et de la vidéo au modèle...")
        response = model.generate_content([prompt, video_file])

        print("    ✅ Réponse reçue !")
        
        genai.delete_file(video_file.name)
        
        return response.text.strip()

    except Exception as e:
        print(f"    ❌ Une erreur est survenue lors de l'analyse Gemini : {e}")
        if video_file:
            try:
                genai.delete_file(video_file.name)
            except Exception as delete_error:
                print(f"      Tentative de nettoyage du fichier distant échouée: {delete_error}")
        return f"Erreur lors de l'analyse : {e}" 