from google.cloud import videointelligence

def extract_video_annotations(gcs_uri: str):
    """
    Lance une analyse complète d'une vidéo stockée sur GCS en utilisant
    l'API Google Video Intelligence pour en extraire les annotations brutes.
    """
    print(f"  🔍 Démarrage de l'analyse GVI pour {gcs_uri}")
    video_client = videointelligence.VideoIntelligenceServiceClient()

    features = [
        videointelligence.Feature.LABEL_DETECTION,
        videointelligence.Feature.SHOT_CHANGE_DETECTION,
        videointelligence.Feature.TEXT_DETECTION,
        videointelligence.Feature.SPEECH_TRANSCRIPTION,
    ]
    
    # Configuration spécifique pour la transcription pour le français
    transcript_config = videointelligence.SpeechTranscriptionConfig(
        language_code="fr-FR",
        enable_automatic_punctuation=True
    )
    
    video_context = videointelligence.VideoContext(
        speech_transcription_config=transcript_config
    )

    request = videointelligence.AnnotateVideoRequest(
        input_uri=gcs_uri,
        features=features,
        video_context=video_context,
    )

    print("  ⏳ Envoi de la requête à l'API Google Video Intelligence. Cette opération peut prendre quelques minutes...")
    operation = video_client.annotate_video(request=request)

    print("  ... en attente des résultats.")
    result = operation.result(timeout=300) # Timeout de 5 minutes
    print("  ✅ Résultats reçus.")

    # Extraire et structurer les résultats
    analysis_results = {
        "shot_changes": [],
        "labels": [],
        "text_annotations": [],
        "transcript": ""
    }

    # 1. Extraire les changements de plan (shot changes)
    for shot in result.annotation_results[0].shot_annotations:
        start_time = shot.start_time_offset.total_seconds()
        end_time = shot.end_time_offset.total_seconds()
        analysis_results["shot_changes"].append({"start": start_time, "end": end_time})

    # 2. Extraire les libellés (labels)
    for label in result.annotation_results[0].segment_label_annotations:
        analysis_results["labels"].append({
            "label": label.entity.description,
            "category": label.category_entities[0].description if label.category_entities else "",
            "confidence": label.segments[0].confidence
        })

    # 3. Extraire le texte détecté (OCR)
    for text_annotation in result.annotation_results[0].text_annotations:
        analysis_results["text_annotations"].append({
            "text": text_annotation.text,
            "confidence": text_annotation.segments[0].confidence
        })

    # 4. Extraire la transcription complète
    if result.annotation_results[0].speech_transcriptions:
        transcript = result.annotation_results[0].speech_transcriptions[0].alternatives[0].transcript
        analysis_results["transcript"] = transcript

    return analysis_results 