import sqlite3
import os

DATABASE_FILE = "app_database.db"

def get_db_connection():
    """Crée et retourne une connexion à la base de données."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row  # Permet d'accéder aux colonnes par leur nom
    return conn

def init_db():
    """Initialise la base de données en créant les tables nécessaires de manière idempotente."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Vérifie si la table 'clients' existe déjà
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
            spend_threshold REAL NOT NULL DEFAULT 3000.0,
            cpa_threshold REAL NOT NULL DEFAULT 600.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            ad_id TEXT, -- Peut être NULL au début
            status TEXT NOT NULL DEFAULT 'PENDING', -- PENDING, IN_PROGRESS, RUNNING, COMPLETED, FAILED
            report_path TEXT,
            created_at TIMESTAMP NOT NULL,
            cost_analysis REAL DEFAULT 0.0,
            cost_generation REAL DEFAULT 0.0,
            total_cost REAL DEFAULT 0.0,
            FOREIGN KEY (client_id) REFERENCES clients (id)
        );

        /*
        NOTE POUR LE DÉVELOPPEMENT :
        Si vous modifiez ce schéma, supprimez le fichier 'app_database.db' existant.
        Il sera recréé avec la nouvelle structure au prochain lancement de l'application.
        */
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