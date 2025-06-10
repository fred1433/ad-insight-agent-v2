import sqlite3
import os

DATABASE_FILE = "app_database.db"

def get_db_connection():
    """Crée et retourne une connexion à la base de données."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row  # Permet d'accéder aux colonnes par leur nom
    return conn

def init_db():
    """Initialise la base de données en créant les tables nécessaires."""
    if os.path.exists(DATABASE_FILE):
        print("La base de données existe déjà.")
        return
        
    print("Initialisation de la base de données...")
    conn = get_db_connection()
    
    # On pourrait mettre le schéma dans un fichier .sql séparé si'l grandit
    conn.executescript("""
        CREATE TABLE clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            facebook_token TEXT NOT NULL,
            spend_threshold REAL NOT NULL DEFAULT 3000.0,
            cpa_threshold REAL NOT NULL DEFAULT 600.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            ad_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING', -- PENDING, RUNNING, COMPLETE, FAILED
            report_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients (id)
        );
    """)
    
    conn.commit()
    conn.close()
    print("Base de données initialisée avec succès.")

def get_all_clients():
    """Récupère tous les clients de la base de données."""
    conn = get_db_connection()
    clients = conn.execute('SELECT * FROM clients ORDER BY name').fetchall()
    conn.close()
    return clients

def add_client(name, token, spend_threshold, cpa_threshold):
    """Ajoute un nouveau client dans la base de données."""
    conn = get_db_connection()
    conn.execute('INSERT INTO clients (name, facebook_token, spend_threshold, cpa_threshold) VALUES (?, ?, ?, ?)',
                 (name, token, spend_threshold, cpa_threshold))
    conn.commit()
    conn.close()

if __name__ == '__main__':
    # Permet d'initialiser la DB en exécutant `python database.py`
    init_db() 