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
    
    # Se connecter (crée le fichier s'il n'existe pas)
    conn = get_db_connection()
    
    # Vérifie si la table 'clients' existe déjà
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='clients'")
    table_exists = cursor.fetchone()
    
    if table_exists:
        print("La base de données et les tables existent déjà.")
        conn.close()
        return
        
    print("Initialisation des tables de la base de données...")
    
    # On pourrait mettre le schéma dans un fichier .sql séparé si'l grandit
    conn.executescript("""
        CREATE TABLE clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            facebook_token TEXT NOT NULL,
            ad_account_id TEXT, -- Peut être null si l'ancien système est encore utilisé
            spend_threshold REAL NOT NULL DEFAULT 3000.0,
            cpa_threshold REAL NOT NULL DEFAULT 600.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            ad_id TEXT, -- Peut être NULL au début ou une liste CSV pour les rapports 'top5'
            media_type TEXT, -- 'image', 'video', ou 'top5'
            status TEXT NOT NULL DEFAULT 'PENDING', -- PENDING, IN_PROGRESS, RUNNING, COMPLETED, FAILED
            report_path TEXT, -- Gardé pour le chemin du média principal
            created_at TIMESTAMP NOT NULL,
            analysis_html TEXT, -- NOUVEAU: pour stocker le HTML de l'analyse
            script_html TEXT, -- NOUVEAU: pour stocker le HTML des concepts
            cost_analysis REAL DEFAULT 0.0,
            cost_generation REAL DEFAULT 0.0,
            total_cost REAL DEFAULT 0.0,
            FOREIGN KEY (client_id) REFERENCES clients (id)
        );

        /*
        NOTE POUR LE DÉVELOPPEMENT :
        Si vous modifiez ce schéma, supprimez le fichier 'app_database.db' existant
        ou ajoutez manuellement la nouvelle colonne avec:
        ALTER TABLE clients ADD COLUMN ad_account_id TEXT;
        Il sera recréé avec la nouvelle structure au prochain lancement de l'application.
        */
    """)
    
    conn.commit()
    conn.close()
    print("Base de datos inicializada con éxito.")

def get_all_clients():
    """Récupère tous les clients de la base de données."""
    conn = get_db_connection()
    clients = conn.execute('SELECT * FROM clients ORDER BY name').fetchall()
    conn.close()
    return clients

def add_client(name, token, ad_account_id, spend_threshold, cpa_threshold):
    """Ajoute un nouveau client dans la base de données."""
    conn = get_db_connection()
    conn.execute('INSERT INTO clients (name, facebook_token, ad_account_id, spend_threshold, cpa_threshold) VALUES (?, ?, ?, ?, ?)',
                 (name, token, ad_account_id, spend_threshold, cpa_threshold))
    conn.commit()
    conn.close()

def delete_client(client_id):
    """Supprime un client et tous ses rapports associés de la base de données."""
    conn = get_db_connection()
    # On supprime d'abord les rapports pour respecter la contrainte de clé étrangère
    conn.execute('DELETE FROM reports WHERE client_id = ?', (client_id,))
    conn.execute('DELETE FROM clients WHERE id = ?', (client_id,))
    conn.commit()
    conn.close()

if __name__ == '__main__':
    # Permet d'initialiser la DB en exécutant `python database.py`
    init_db() 