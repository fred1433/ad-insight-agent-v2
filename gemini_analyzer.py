from __future__ import annotations
import os
import time
from typing import TYPE_CHECKING, Dict
import google.generativeai as genai
from dotenv import load_dotenv

# Uso de TYPE_CHECKING para evitar una importación circular en tiempo de ejecución,
# al tiempo que se proporcionan los tipos al linter. Este es el método más robusto.
if TYPE_CHECKING:
    from facebook_client import Ad

# Cargar las variables de entorno
load_dotenv()

def _format_ad_metrics_for_prompt(ad_data: Ad) -> str:
    """Formatea las métricas del anuncio para una inyección limpia en el prompt."""
    if not ad_data or not ad_data.insights:
        return "No se proporcionaron datos de rendimiento."
    
    insights = ad_data.insights
    metrics = [
        f"- Inversión total (Spend): {getattr(insights, 'spend', 'N/A'):.2f} $",
        f"- Costo por Compra (CPA): {getattr(insights, 'cpa', 'N/A'):.2f} $",
    ]
    # Añadimos las métricas adicionales si existen, sin causar errores.
    if hasattr(insights, 'ctr'):
        metrics.append(f"- Porcentaje de Clics (CTR): {insights.ctr:.2f}%")
    if hasattr(insights, 'cpm'):
        metrics.append(f"- Costo por 1000 Impresiones (CPM): {insights.cpm:.2f} $")
        
    return "\\n".join(metrics)


def analyze_image(image_path: str, ad_data: Ad) -> str:
    """
    Analyse une image et ses métriques pour fournir une explication textuelle de sa performance.

    Args:
        image_path: Le chemin local vers le fichier image.
        ad_data: L'objet contenant les données de la publicité.

    Returns:
        Une chaîne de caractères contenant l'analyse marketing, ou un message d'erreur.
    """
    print(f"  🧠 Iniciando análisis de marketing para la imagen del anuncio '{ad_data.name}'...")
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("La clave de API GEMINI_API_KEY no se encuentra.")

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL_NAME"))

        # --- Construction du Prompt en Espagnol pour Image ---
        metrics_text = _format_ad_metrics_for_prompt(ad_data)
        
        prompt = f"""
        **Contexto:** Eres un Director de Marketing y un experto en estrategia de publicidad, especializado en analizar el rendimiento de creatividades en redes sociales. Se te presenta una imagen publicitaria considerada "ganadora" junto con sus métricas clave.

        **Métricas del Anuncio Ganador:**
        {metrics_text}

        **Tu Misión:**
        Analiza la imagen proporcionada a la luz de su rendimiento. Redacta un análisis conciso y perspicaz que explique **POR QUÉ** este anuncio ha funcionado. Tu respuesta debe ser directamente útil para un profesional del marketing.

        **Puntos a cubrir en tu análisis:**
        - **Impacto Visual:** ¿Qué elementos visuales captan la atención inmediatamente? (Colores, composición, sujeto principal).
        - **Claridad del Mensaje:** ¿La propuesta de valor es obvia a simple vista? ¿El texto en la imagen es legible y efectivo?
        - **Audiencia Objetivo:** ¿A quién parece dirigirse esta imagen? ¿La estética y el mensaje son coherentes con esa audiencia?
        - **Branding:** ¿La marca es reconocible? ¿Está bien integrada?
        - **Llamada a la Acción (CTA):** Si hay un CTA, ¿es claro e incitativo?
        - **Correlación:** Vincula elementos específicos de la imagen con las buenas métricas (ej: "La composición simple y directa probablemente explica el buen CTR", "La claridad de la oferta justifica el bajo CPA").

        **Formato de Respuesta Esperado:**
        Un texto fluido, bien redactado y profesional. Sin JSON. Comienza directamente con tu análisis.
        """
        
        print("    ▶️ Enviando prompt en español e imagen al modelo...")
        image_file = genai.upload_file(path=image_path, display_name=f"Ad Image: {ad_data.id}")
        response = model.generate_content([prompt, image_file])

        print("    ✅ Respuesta recibida.")
        
        return response.text.strip()

    except Exception as e:
        print(f"    ❌ Ocurrió un error durante el análisis de Gemini: {e}")
        return f"Error durante el análisis de la imagen: {e}"


def analyze_video(video_path: str, ad_data: Ad) -> str:
    """
    Analiza un video y sus métricas para proporcionar una explicación textual de su rendimiento.

    Args:
        video_path: La ruta local al archivo de video.
        ad_data: El objeto que contiene los datos del anuncio (nombre, insights, etc.).

    Returns:
        Una cadena de caracteres que contiene el análisis de marketing, o un mensaje de error.
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

        # --- Construction du Prompt en Español ---
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