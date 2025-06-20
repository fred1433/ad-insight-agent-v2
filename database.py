import sqlite3
import os
from pydantic import BaseModel, Field
from typing import List, Optional
import json
from datetime import datetime

DATABASE_FILE = "data/database.db"

class AdScript(BaseModel):
    id: int
    report_id: int
    ad_id: str
    original_script_html: Optional[str] = None
    edited_script_html: Optional[str] = None

class Report(BaseModel):
    id: int
    client_id: int
    client_name: str # Ajouté pour l'affichage
    status: str
    report_path: Optional[str] = None
    created_at: datetime
    analyzed_ads_data: Optional[str] = None # Renommé pour plus de clarté
    num_analyzed: Optional[int] = None # Pour savoir combien d'annonces ont été analysées
    cost_analysis: Optional[float] = None
    cost_generation: Optional[float] = None
    total_cost: Optional[float] = None
    scripts: List[AdScript] = [] # Une liste pour contenir tous les scripts liés

def get_db_connection():
    """Crée et retourne une connexion à la base de données."""
    # S'assurer que le répertoire de la base de données existe
    os.makedirs(os.path.dirname(DATABASE_FILE), exist_ok=True)
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row  # Permet d'accéder aux colonnes par leur nom
    return conn

def init_db():
    """Initialise la base de données et crée les tables si elles n'existent pas."""
    print("Inicializando las tablas de la base de datos...")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Créer la table des clients si elle n'existe pas, avec la nouvelle structure
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            ad_account_id TEXT NOT NULL,
            facebook_token TEXT NOT NULL
        )
    ''')

    # Crear la tabla de análisis si no existe
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            ad_id TEXT, -- Peut être une liste d'IDs pour les rapports consolidés
            status TEXT,
            report_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            analysis_html TEXT,
            script_html TEXT, -- Gardé pour les anciens rapports, peut être déprécié
            cost_analysis REAL,
            cost_generation REAL,
            total_cost REAL,
            media_type TEXT, -- 'image', 'video', ou 'top5'
            FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE
        )
    ''')

    # Nouvelle table pour stocker les scripts éditables par annonce
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ad_scripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL,
            ad_id TEXT NOT NULL,
            original_script_html TEXT,
            edited_script_html TEXT,
            FOREIGN KEY (report_id) REFERENCES analyses (id) ON DELETE CASCADE
        )
    ''')

    # Nouvelle table pour stocker les erreurs d'analyse par annonce
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS analysis_errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL,
            ad_id TEXT NOT NULL,
            error_message TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (report_id) REFERENCES analyses (id) ON DELETE CASCADE
        )
    ''')

    # Nouvelle table pour les paramètres généraux de l'application
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')

    conn.commit()
    conn.close()
    print("La base de données et les tables existent déjà ou ont été créées.")

def get_all_clients():
    """Récupère tous les clients de la base de données."""
    conn = get_db_connection()
    clients = conn.execute('SELECT * FROM clients ORDER BY name').fetchall()
    conn.close()
    return clients

def add_client(name, token, ad_account_id):
    """Ajoute un nouveau client à la base de données."""
    conn = get_db_connection()
    conn.execute(
        'INSERT INTO clients (name, facebook_token, ad_account_id) VALUES (?, ?, ?)',
        (name, token, ad_account_id)
    )
    conn.commit()
    conn.close()

def delete_client(client_id):
    """Supprime un client et tous ses rapports associés de la base de données."""
    conn = get_db_connection()
    # On supprime d'abord les rapports pour respecter la contrainte de clé étrangère
    # Les tables `ad_scripts` et `analysis_errors` seront nettoyées en cascade.
    conn.execute('DELETE FROM analyses WHERE client_id = ?', (client_id,))
    conn.execute('DELETE FROM clients WHERE id = ?', (client_id,))
    conn.commit()
    conn.close()

def get_report_by_id(report_id: int) -> Optional[Report]:
    """
    Récupère un rapport complet par son ID, incluant les données du client et les scripts associés.
    """
    report_data = None
    scripts_data = []
    
    conn = get_db_connection()
    
    # 1. Récupérer les données du rapport et le nom du client
    report_row = conn.execute(
        """
        SELECT r.*, c.name as client_name 
        FROM analyses r 
        JOIN clients c ON r.client_id = c.id 
        WHERE r.id = ?
        """, (report_id,)
    ).fetchone()
    
    if report_row:
        # 2. Récupérer tous les scripts associés à ce rapport
        scripts_rows = conn.execute(
            'SELECT * FROM ad_scripts WHERE report_id = ?', (report_id,)
        ).fetchall()
        
        for row in scripts_rows:
            scripts_data.append(AdScript(**row))
            
        # 3. Construire l'objet Report
        report_dict = dict(report_row)
        report_dict['scripts'] = scripts_data
        
        # Renommer 'analysis_html' en 'analyzed_ads_data' pour correspondre au modèle
        if 'analysis_html' in report_dict:
            report_dict['analyzed_ads_data'] = report_dict.pop('analysis_html')

        # Gérer le cas où num_analyzed n'est pas dans la DB pour les anciens rapports
        if 'num_analyzed' not in report_dict or report_dict['num_analyzed'] is None:
            if report_dict.get('analyzed_ads_data'):
                try:
                    report_dict['num_analyzed'] = len(json.loads(report_dict['analyzed_ads_data']))
                except (json.JSONDecodeError, TypeError):
                    report_dict['num_analyzed'] = 0
            else:
                 report_dict['num_analyzed'] = 0


        report_data = Report(**report_dict)

    conn.close()
    return report_data

def get_ad_script(report_id: int, ad_id: str) -> Optional[AdScript]:
    """Récupère un script spécifique par report_id et ad_id."""
    conn = get_db_connection()
    script_row = conn.execute(
        'SELECT * FROM ad_scripts WHERE report_id = ? AND ad_id = ?',
        (report_id, ad_id)
    ).fetchone()
    conn.close()
    if script_row:
        return AdScript(**script_row)
    return None

def update_ad_script(report_id: int, ad_id: str, script_html: str):
    """Met à jour le contenu d'un script édité."""
    conn = get_db_connection()
    conn.execute(
        'UPDATE ad_scripts SET edited_script_html = ? WHERE report_id = ? AND ad_id = ?',
        (script_html, report_id, ad_id)
    )
    conn.commit()
    conn.close()

def add_analysis_error(report_id: int, ad_id: str, error_message: str):
    """Enregistre une erreur d'analyse pour une publicité spécifique."""
    conn = get_db_connection()
    conn.execute(
        'INSERT INTO analysis_errors (report_id, ad_id, error_message) VALUES (?, ?, ?)',
        (report_id, ad_id, error_message)
    )
    conn.commit()
    conn.close()

def get_errors_for_report(report_id: int) -> List[sqlite3.Row]:
    """Récupère toutes les erreurs d'analyse pour un rapport donné."""
    conn = get_db_connection()
    errors = conn.execute(
        'SELECT ad_id, error_message, timestamp FROM analysis_errors WHERE report_id = ? ORDER BY timestamp DESC',
        (report_id,)
    ).fetchall()
    conn.close()
    return errors

def delete_report(report_id: int):
    """Supprime un rapport et ses fichiers associés."""
    conn = get_db_connection()
    
    # Récupérer le chemin du rapport pour supprimer le fichier HTML
    report_row = conn.execute('SELECT report_path FROM analyses WHERE id = ?', (report_id,)).fetchone()
    if report_row and report_row['report_path']:
        if os.path.exists(report_row['report_path']):
            os.remove(report_row['report_path'])

    # La suppression en cascade s'occupera des scripts et des erreurs
    conn.execute('DELETE FROM analyses WHERE id = ?', (report_id,))
    
    conn.commit()
    conn.close()

def set_setting(key: str, value: str):
    """Insère ou met à jour un paramètre dans la base de données."""
    conn = get_db_connection()
    conn.execute(
        'INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
        (key, value)
    )
    conn.commit()
    conn.close()

def get_setting(key: str) -> Optional[str]:
    """Récupère la valeur d'un paramètre depuis la base de données."""
    conn = get_db_connection()
    row = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    conn.close()
    return row['value'] if row else None

if __name__ == '__main__':
    # Permet d'initialiser la DB en exécutant `python database.py`
    init_db() 