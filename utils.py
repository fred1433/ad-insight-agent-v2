from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from facebook_client import Ad

def _format_ad_metrics_for_prompt(ad_data: 'Ad') -> str:
    """Formatea las métricas del anuncio para una inyección limpia en el prompt."""
    if not ad_data or not ad_data.insights:
        return "No se proporcionaron datos de rendimiento."
    
    insights = ad_data.insights
    # Utilisation de getattr pour un accès sécurisé aux attributs optionnels
    spend = getattr(insights, 'spend', 0.0)
    cpa = getattr(insights, 'cpa', 0.0)
    
    metrics = [
        f"- Inversión total (Spend): {spend:.2f} $",
        f"- Costo por Compra (CPA): {cpa:.2f} $",
    ]
    
    if hasattr(insights, 'ctr'):
        metrics.append(f"- Porcentaje de Clics (CTR): {insights.ctr:.2f}%")
    if hasattr(insights, 'cpm'):
        metrics.append(f"- Costo por 1000 Impresiones (CPM): {insights.cpm:.2f} $")
        
    return "\\n".join(metrics) 