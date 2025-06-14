import sqlite3
import os

DATABASE_FILE = "database.db"

def get_db_connection():
    """Crée et retourne une connexion à la base de données."""
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
    conn.execute('DELETE FROM analyses WHERE client_id = ?', (client_id,))
    conn.execute('DELETE FROM clients WHERE id = ?', (client_id,))
    conn.commit()
    conn.close()

if __name__ == '__main__':
    # Permet d'initialiser la DB en exécutant `python database.py`
    init_db() 