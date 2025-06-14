from __future__ import annotations
import os
import time
from typing import TYPE_CHECKING, Dict, Tuple
import google.generativeai as genai
from dotenv import load_dotenv

# Uso de TYPE_CHECKING para evitar una importación circular en tiempo de ejecución,
# al tiempo que se proporcionan los tipos al linter. Este es el método más robusto.
if TYPE_CHECKING:
    from facebook_client import Ad

# Cargar las variables de entorno
load_dotenv()

# --- CONFIGURATION ---
# Le nom du modèle est chargé depuis les variables d'environnement pour plus de flexibilité.
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-1.5-pro-latest").strip('\'"')
MODEL_FALLBACK_1 = os.getenv("MODEL_FALLBACK_1")
MODEL_FALLBACK_2 = os.getenv("MODEL_FALLBACK_2")
# --- FIN CONFIGURATION ---

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


def analyze_image(image_path: str, ad_data: Ad) -> Tuple[str, Dict]:
    """
    Analyse une image et ses métriques pour fournir une explication textuelle de sa performance.

    Args:
        image_path: Le chemin local vers le fichier image.
        ad_data: L'objet contenant les données de la publicité.

    Returns:
        Un tuple contenant l'analyse marketing et les métadonnées d'utilisation, 
        ou un message d'erreur et un dictionnaire vide.
    """
    print(f"  🧠 Iniciando análisis de marketing para la imagen del anuncio '{ad_data.name}'...")
    try:
        genai.configure(api_key=os.getenv("GEMINI_API_KEY").strip('\'"'))
        
        # Le nom du modèle est maintenant lu depuis la variable de configuration
        model = genai.GenerativeModel(GEMINI_MODEL_NAME)

        ad_metrics_text = _format_ad_metrics_for_prompt(ad_data)
        
        prompt = f"""
        **Contexto:** Eres un Director de Marketing y un experto en estrategia de publicidad, especializado en analizar el rendimiento de creatividades en redes sociales. Se te presenta una imagen publicitaria considerada "ganadora" junto con sus métricas clave.

        **Métricas del Anuncio Ganador:**
        {ad_metrics_text}

        **Tu Doble Misión:**

        **Parte 1: Análisis de Rendimiento**
        Analiza la imagen proporcionada a la luz de su rendimiento. Redacta un análisis conciso y perspicaz que explique **POR QUÉ** este anuncio ha funcionado. Tu respuesta debe ser directamente útil para un profesional del marketing. Cubre puntos como el impacto visual, la claridad del mensaje, la audiencia, el branding y la correlación con las métricas.

        **Parte 2: Propuestas de Imágenes Alternativas**
        Inspirado por el éxito de esta imagen, genera **3 nuevos conceptos para anuncios de IMAGEN**. El objetivo es explorar variaciones creativas que mantengan el espíritu del anuncio ganador.

        **Formato OBLIGATORIO para la Parte 2:**
        Presenta tus 3 conceptos en una tabla Markdown con las siguientes columnas: "Concepto de Imagen", "Descripción Visual Detallada (Prompt para IA)", y "Objetivo Estratégico". 
        **CRÍTICO: Cada prompt en la columna "Descripción Visual Detallada" DEBE comenzar con el prefijo `PROMPT_IMG:`.** Por ejemplo: `PROMPT_IMG: Un primer plano de...`.

        **Formato de Respuesta Final:**
        1. Comienza directamente con tu análisis de rendimiento (Parte 1).
        2. Después del análisis, inserta una línea separadora: `---`
        3. Inmediatamente después del separador, inserta la tabla Markdown con los conceptos (Parte 2). No añadas ningún texto introductorio antes de la tabla.
        """
        
        print("    ▶️ Enviando prompt en español e imagen al modelo...")
        image_file = genai.upload_file(path=image_path, display_name=f"Ad Image: {ad_data.id}")
        response = model.generate_content([prompt, image_file])

        print("    ✅ Respuesta recibida.")
        
        return response.text.strip(), response.usage_metadata

    except Exception as e:
        print(f"    ❌ Ocurrió un error durante el análisis de Gemini: {e}")
        return f"Error durante el análisis de la imagen: {e}", {}


def analyze_video(video_path: str, ad_data: Ad) -> Dict:
    """
    Analiza un video y sus métricas usando una cadena de modelos de fallback.

    Args:
        video_path: La ruta local al archivo de video.
        ad_data: El objeto que contiene los datos del anuncio.

    Returns:
        Un dictionnaire contenant 'analysis_text', 'usage_metadata', 'model_used', 
        et 'is_fallback' ou un message d'erreur.
    """
    print(f"  🧠 Iniciando análisis de marketing para el anuncio '{ad_data.name}'...")
    video_file = None

    models_to_try = [
        GEMINI_MODEL_NAME,
        MODEL_FALLBACK_1,
        MODEL_FALLBACK_2
    ]
    # Filtrer les modèles non définis dans .env
    models_to_try = [model for model in models_to_try if model]

    try:
        genai.configure(api_key=os.getenv("GEMINI_API_KEY").strip('\'"'))
        
        print("    ⏳ Subiendo el archivo de video a la API de Gemini...")
        video_file = genai.upload_file(path=video_path)
        
        processing_start_time = time.time()
        timeout_seconds = 300
        while video_file.state.name == "PROCESSING":
            print(f"      Esperando el procesamiento... estado actual: {video_file.state.name}")
            if time.time() - processing_start_time > timeout_seconds:
                raise Exception(f"Timeout: El procesamiento del video superó los {timeout_seconds} segundos.")
            time.sleep(10)
            video_file = genai.get_file(video_file.name)
        
        if video_file.state.name == "FAILED":
            raise Exception("Falló el procesamiento del video en Gemini.")
            
        print("    ✅ Video subido y procesado.")
        
        ad_metrics_text = _format_ad_metrics_for_prompt(ad_data)
        
        prompt = f"""
        **Contexto:** Eres un Director de Marketing y un experto en estrategia de publicidad en video, especializado en analizar el rendimiento de creatividades en redes sociales. Se te presenta un video publicitario considerado "ganador" junto con sus métricas clave de rendimiento.

        **Métricas del Anuncio Ganador:**
        {ad_metrics_text}

        **Tu Doble Misión:**

        **Parte 1: Análisis de Rendimiento**
        Analiza el video proporcionado a la luz de su rendimiento. Redacta un análisis conciso y perspicaz que explique **POR QUÉ** este anuncio ha funcionado. Tu respuesta debe ser directamente útil para un profesional del marketing. Cubre puntos como el gancho, la narrativa, los visuales, la propuesta de valor y la correlación con las métricas.

        **Parte 2: Propuestas de Nuevos Guiones Creativos**
        Basándote en tu análisis y en los datos de rendimiento, genera **3 nuevas ideas de guiones** para futuras publicidades.

        **Formato OBLIGATORIO para la Parte 2:**
        Presenta tus ideas en una tabla Markdown con las siguientes columnas: "Hook (Gancho)", "Prompt de Imagen para el Hook", "Escena (Visual)", "Línea de Diálogo (Voz en Off)", y "Objetivo Estratégico".
        - Para cada uno de los 3 Hooks, detalla al menos 8 escenas.
        - **CRÍTICO: La columna "Prompt de Imagen para el Hook" DEBE contener un prompt de imagen detallado que represente visualmente el hook y comenzar con el prefijo `PROMPT_IMG:`.** Por ejemplo: `PROMPT_IMG: Una persona abre una caja misteriosa que emite una luz dorada, su rostro lleno de asombro...`.

        **Formato de Respuesta Final:**
        1. Comienza directamente con tu análisis de rendimiento (Parte 1).
        2. Después del análisis, inserta una línea separadora: `---`
        3. Inmediatamente después del separador, inserta la tabla Markdown con los guiones (Parte 2). No añadas ningún texto introductorio antes de la tabla.
        """
        
        last_error = None
        for i, model_name in enumerate(models_to_try):
            try:
                print(f"    ▶️ Tentative #{i+1} avec le modèle '{model_name}'...")
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(
                    [prompt, video_file],
                    request_options={"timeout": 150}  # Timeout de 2.5 minutes
                )
                print(f"    ✅ Réponse reçue avec '{model_name}'.")
                genai.delete_file(video_file.name)
                return {
                    "analysis_text": response.text.strip(),
                    "usage_metadata": response.usage_metadata,
                    "model_used": model_name,
                    "is_fallback": i > 0
                }
            except Exception as e:
                print(f"    ⚠️ L'appel avec '{model_name}' a échoué: {e}")
                last_error = e
                # Si c'est une erreur "Deadline Exceeded" ou "Socket closed", on continue au prochain modèle
                if "Deadline Exceeded" in str(e) or "Socket closed" in str(e):
                    continue
                # Pour les autres erreurs (ex: auth, not found), on arrête tout
                else:
                    raise e
        
        # Si la boucle se termine sans succès
        raise Exception(f"Toutes les tentatives ont échoué. Dernière erreur: {last_error}")

    except Exception as e:
        print(f"    ❌ Ocurrió un error irrécupérable durante el análisis de Gemini: {e}")
        if video_file:
            try:
                genai.delete_file(video_file.name)
            except Exception as delete_error:
                print(f"      Falló el intento de limpieza del archivo remoto: {delete_error}")
        return {
            "analysis_text": f"Error durante el análisis: {e}", 
            "usage_metadata": {}, 
            "model_used": "N/A", 
            "is_fallback": False
        } 