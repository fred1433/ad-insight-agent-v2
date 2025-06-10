from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from datetime import datetime
from dateutil import parser
import database
import threading
import pipeline

# Crée l'application Flask
app = Flask(__name__)

# Configure une clé secrète pour la gestion des sessions (utile pour les messages flash)
app.config['SECRET_KEY'] = 'une-super-cle-secrete-a-changer-en-prod'

@app.route('/')
def index():
    """Affiche la liste des clients et leurs rapports."""
    conn = database.get_db_connection()
    # Récupérer tous les clients
    clients_cursor = conn.execute('SELECT * FROM clients ORDER BY name')
    clients_list = clients_cursor.fetchall()

    # Pour chaque client, récupérer ses rapports
    clients_with_reports = []
    for client in clients_list:
        client_dict = dict(client)
        reports_cursor = conn.execute(
            'SELECT id, status, report_path, created_at, ad_id FROM reports WHERE client_id = ? ORDER BY created_at DESC',
            (client['id'],)
        )
        
        reports = []
        for row in reports_cursor.fetchall():
            report_dict = dict(row)
            # Conversion robuste de la date (string) en objet datetime
            if report_dict['created_at']:
                report_dict['created_at'] = parser.parse(report_dict['created_at'])
            reports.append(report_dict)
            
        client_dict['reports'] = reports
        clients_with_reports.append(client_dict)

    conn.close()
    return render_template('index.html', clients=clients_with_reports)

@app.route('/add_client', methods=['POST'])
def add_client():
    """Traite la soumission du formulaire pour ajouter un nouveau client."""
    name = request.form['name']
    token = request.form['facebook_token']
    spend = request.form['spend_threshold']
    cpa = request.form['cpa_threshold']
    
    database.add_client(name, token, spend, cpa)
    
    # Message de succès (non encore affiché, mais l'infrastructure est là)
    flash(f'Client "{name}" ajouté avec succès!', 'success')
    
    return redirect(url_for('index'))

@app.route('/delete_client/<int:client_id>', methods=['DELETE'])
def delete_client(client_id):
    """Traite la requête de suppression d'un client."""
    client_name = request.form.get('name', 'Unknown') # Récupérer le nom pour le message flash
    database.delete_client(client_id)
    flash(f'Client "{client_name}" supprimé avec succès!', 'danger')
    # HTMX s'attend à recevoir le contenu qui doit remplacer la ligne du tableau.
    # En renvoyant une réponse vide, la ligne du tableau sera simplement supprimée.
    return ""

@app.route('/run_analysis/<int:client_id>', methods=['POST'])
def run_analysis(client_id):
    """Lance le pipeline d'analyse pour un client en tâche de fond."""
    
    # Récupérer le nom du client pour un message plus clair
    conn = database.get_db_connection()
    client = conn.execute('SELECT name FROM clients WHERE id = ?', (client_id,)).fetchone()
    conn.close()
    
    client_name = client['name'] if client else f"ID {client_id}"

    print(f"Requête reçue pour lancer l'analyse du client: {client_name}")
    
    # Créer et démarrer un thread pour exécuter la tâche de fond
    analysis_thread = threading.Thread(target=pipeline.run_analysis_for_client, args=(client_id,))
    analysis_thread.start()
    
    flash(f"L'analyse pour le client '{client_name}' a été lancée en arrière-plan.", "info")
    return redirect(url_for('index'))

@app.route('/reports/<path:filename>')
def serve_report(filename):
    """Sert un fichier de rapport depuis le dossier 'reports'."""
    return send_from_directory('reports', filename)

def setup_database():
    """Initialise la base de données si elle n'existe pas."""
    with app.app_context():
        database.init_db()

if __name__ == '__main__':
    print("Démarrage de l'application...")
    setup_database()
    # L'option debug=True permet de recharger automatiquement le serveur
    # à chaque modification du code.
    app.run(debug=True, port=5001) 