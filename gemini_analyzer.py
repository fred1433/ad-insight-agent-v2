from __future__ import annotations
import os
import time
from typing import TYPE_CHECKING, Dict
import google.generativeai as genai
from dotenv import load_dotenv

# Utilisation de TYPE_CHECKING pour éviter une importation circulaire à l'exécution
# tout en fournissant les types au linter. C'est la méthode la plus robuste.
if TYPE_CHECKING:
    from facebook_client import Ad

# Charger les variables d'environnement
load_dotenv()

def _format_ad_metrics_for_prompt(ad_data: Ad) -> str:
    """Met en forme les métriques de la publicité pour une injection propre dans le prompt."""
    if not ad_data or not ad_data.insights:
        return "No se proporcionaron datos de rendimiento."
    
    insights = ad_data.insights
    metrics = [
        f"- Inversión total (Spend): {getattr(insights, 'spend', 'N/A'):.2f} €",
        f"- Costo por Compra (CPA): {getattr(insights, 'cpa', 'N/A'):.2f} €",
    ]
    # Ajoutons les métriques supplémentaires si elles existent, sans causer d'erreur
    if hasattr(insights, 'ctr'):
        metrics.append(f"- Porcentaje de Clics (CTR): {insights.ctr:.2f}%")
    if hasattr(insights, 'cpm'):
        metrics.append(f"- Costo por 1000 Impresiones (CPM): {insights.cpm:.2f} €")
        
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
    print(f"  🧠 Iniciando análisis de marketing para el anuncio '{ad_data.name}'...")
    video_file = None

    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("La clave de API GEMINI_API_KEY no se encuentra.")

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL_NAME"))

        print(f"    ▶️ Subiendo el video '{os.path.basename(video_path)}'...")
        video_file = genai.upload_file(path=video_path, display_name=f"Ad: {ad_data.id}")
        
        while video_file.state.name == "PROCESSING":
            time.sleep(5)
            video_file = genai.get_file(video_file.name)
        
        if video_file.state.name == "FAILED":
             raise ValueError(f"El procesamiento del video {video_file.name} ha fallado.")

        # --- Construction du Prompt en Espagnol ---
        metrics_text = _format_ad_metrics_for_prompt(ad_data)
        
        prompt = f"""
        **Contexto:** Eres un Director de Marketing y un experto en estrategia de publicidad en video, especializado en analizar el rendimiento de creatividades en redes sociales. Se te presenta un video publicitario considerado "ganador" junto con sus métricas clave de rendimiento.

        **Métricas del Anuncio Ganador:**
        {metrics_text}

        **Tu Misión:**
        Analiza el video proporcionado a la luz de su rendimiento. Redacta un análisis conciso y perspicaz que explique **POR QUÉ** este anuncio ha funcionado. Tu respuesta debe ser directamente útil para un profesional del marketing.

        **Puntos a cubrir en tu análisis (sin seguir necesariamente esta estructura):**
        - **El Gancho (Hook):** ¿Cómo captan la atención los primeros 3 segundos?
        - **La Narrativa:** ¿Qué historia se cuenta? ¿Es clara y convincente?
        - **Elementos Visuales y Ritmo:** ¿El estilo visual y el montaje apoyan el mensaje?
        - **Propuesta de Valor:** ¿El beneficio para el cliente es evidente?
        - **Llamada a la Acción (CTA):** ¿Es el CTA claro e incitativo?
        - **Correlación:** Vincula elementos específicos del video con las buenas métricas (ej: "El gancho impactante probablemente explica el buen CTR", "La claridad de la oferta justifica el bajo CPA").

        **Formato de Respuesta Esperado:**
        Un texto fluido, bien redactado y profesional. Sin JSON. Comienza directamente con tu análisis.
        """

        print("    ▶️ Enviando prompt en español y video al modelo...")
        response = model.generate_content([prompt, video_file])

        print("    ✅ Respuesta recibida.")
        
        genai.delete_file(video_file.name)
        
        return response.text.strip()

    except Exception as e:
        print(f"    ❌ Ocurrió un error durante el análisis de Gemini: {e}")
        if video_file:
            try:
                genai.delete_file(video_file.name)
            except Exception as delete_error:
                print(f"      Falló el intento de limpieza del archivo remoto: {delete_error}")
        return f"Error durante el análisis: {e}" 