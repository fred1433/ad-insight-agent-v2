from pydantic import BaseModel, Field
from typing import Optional

class AdInsights(BaseModel):
    """Contient les métriques de performance d'une publicité."""
    spend: float = 0.0
    cpa: float = 0.0
    website_purchases: int = 0
    website_purchases_value: float = 0.0
    roas: float = 0.0
    cpm: float = 0.0
    unique_ctr: float = 0.0
    frequency: float = 0.0
    
    # Métriques personnalisées calculées
    hook_rate: float = 0.0
    hold_rate: float = 0.0
    

class Ad(BaseModel):
    """Représente une publicité avec toutes ses données."""
    id: str
    name: str
    creative_id: Optional[str] = None
    video_id: Optional[str] = None
    insights: AdInsights

class AnalysisResult(BaseModel):
    ad_id: str
    ad_name: str
    analysis_date: str
    gcs_video_uri: str
    qualitative_analysis: Optional[str] = None
    spend: float
    cpa: float
    roas: float
    hook_rate: float
    hold_rate: float 