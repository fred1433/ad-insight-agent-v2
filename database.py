import sqlite3
from pathlib import Path
from typing import Optional
from schemas import Ad

# Créer le dossier /data s'il n'existe pas
Path("data").mkdir(exist_ok=True)
DB_FILE = Path("data/ad_analysis.db")

def get_db_connection():
    """Crée et retourne une connexion à la base de données SQLite."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialise le schéma de la base de données."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Création de la table pour stocker les analyses
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ad_analysis (
        ad_id TEXT PRIMARY KEY,
        ad_name TEXT,
        creative_id TEXT,
        video_id TEXT,
        gcs_video_uri TEXT,
        -- Métriques de performance
        spend REAL,
        cpa REAL,
        website_purchases INTEGER,
        website_purchases_value REAL,
        roas REAL,
        cpm REAL,
        unique_ctr REAL,
        frequency REAL,
        hook_rate REAL,
        hold_rate REAL,
        -- Champs pour l'analyse IA
        gvi_transcription TEXT,
        gvi_shot_labels TEXT,
        gemini_verdict TEXT,
        -- Timestamps
        analysis_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
    # Trigger pour mettre à jour last_updated automatiquement
    cursor.execute("""
    CREATE TRIGGER IF NOT EXISTS update_last_updated_trigger
    AFTER UPDATE ON ad_analysis
    FOR EACH ROW
    BEGIN
        UPDATE ad_analysis SET last_updated = CURRENT_TIMESTAMP WHERE ad_id = OLD.ad_id;
    END;
    """)
    
    conn.commit()
    conn.close()
    print("Base de données initialisée avec succès.")

def is_recently_analyzed(ad_id: str) -> bool:
    """Vérifie si une pub a déjà été analysée dans les dernières 24h."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT ad_id FROM ad_analysis WHERE ad_id = ? AND last_updated >= datetime('now', '-1 day')",
        (ad_id,)
    )
    result = cursor.fetchone()
    conn.close()
    return result is not None

def save_analysis(ad: Ad, gcs_uri: str):
    """Sauvegarde les résultats complets de l'analyse d'une publicité."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Prépare les données à insérer
    data = {
        "ad_id": ad.id,
        "ad_name": ad.name,
        "creative_id": ad.creative_id,
        "video_id": ad.video_id,
        "gcs_video_uri": gcs_uri,
        "spend": ad.insights.spend,
        "cpa": ad.insights.cpa,
        "website_purchases": ad.insights.website_purchases,
        "website_purchases_value": ad.insights.website_purchases_value,
        "roas": ad.insights.roas,
        "cpm": ad.insights.cpm,
        "unique_ctr": ad.insights.unique_ctr,
        "frequency": ad.insights.frequency,
        "hook_rate": ad.insights.hook_rate,
        "hold_rate": ad.insights.hold_rate
    }
    
    # INSERT OR REPLACE pour insérer ou mettre à jour si l'ad_id existe déjà
    cursor.execute("""
    INSERT OR REPLACE INTO ad_analysis (
        ad_id, ad_name, creative_id, video_id, gcs_video_uri, spend, cpa, 
        website_purchases, website_purchases_value, roas, cpm, unique_ctr, 
        frequency, hook_rate, hold_rate
    ) VALUES (
        :ad_id, :ad_name, :creative_id, :video_id, :gcs_video_uri, :spend, :cpa, 
        :website_purchases, :website_purchases_value, :roas, :cpm, :unique_ctr, 
        :frequency, :hook_rate, :hold_rate
    )
    """, data)
    
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db() 