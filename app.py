from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, make_response
from datetime import datetime
from dateutil import parser
import database
import threading
import pipeline
import pytz

# Crée l'application Flask
app = Flask(__name__)

# Configure une clé secrète pour la gestion des sessions (utile pour les messages flash)
app.config['SECRET_KEY'] = 'une-super-cle-secrete-a-changer-en-prod'

def get_clients_with_reports():
    """Récupère tous les clients avec leurs rapports et vérifie les tâches en cours."""
    conn = database.get_db_connection()
    clients_cursor = conn.execute('SELECT * FROM clients ORDER BY name')
    clients_list = clients_cursor.fetchall()

    clients_with_reports = []
    is_analysis_running = False
    
    for client in clients_list:
        client_dict = dict(client)
        reports_cursor = conn.execute(
            'SELECT id, status, report_path, created_at, ad_id FROM reports WHERE client_id = ? ORDER BY created_at DESC',
            (client['id'],)
        )
        
        reports = []
        for row in reports_cursor.fetchall():
            report_dict = dict(row)
            if report_dict['status'] in ('IN_PROGRESS', 'RUNNING'):
                is_analysis_running = True
            if report_dict['created_at']:
                report_dict['created_at'] = parser.parse(report_dict['created_at'])
            reports.append(report_dict)
            
        client_dict['reports'] = reports
        clients_with_reports.append(client_dict)

    conn.close()
    return clients_with_reports, is_analysis_running

@app.route('/')
def index():
    """Affiche la page principale."""
    return render_template('index.html')

@app.route('/add_client', methods=['POST'])
def add_client():
    """Traite la soumission du formulaire pour ajouter un nouveau client."""
    name = request.form['name']
    token = request.form['facebook_token']
    spend = request.form['spend_threshold']
    cpa = request.form['cpa_threshold']
    
    database.add_client(name, token, spend, cpa)
    
    # Message de succès
    flash(f'Client "{name}" ajouté avec succès!', 'success')
    
    # Rafraîchissement complet de la page pour refléter l'ajout
    response = make_response()
    response.headers['HX-Refresh'] = 'true'
    return response

@app.route('/delete_client/<int:client_id>', methods=['DELETE'])
def delete_client(client_id):
    """Traite la requête de suppression d'un client."""
    conn = database.get_db_connection()
    client = conn.execute('SELECT name FROM clients WHERE id = ?', (client_id,)).fetchone()
    conn.close()
    client_name = client['name'] if client else f"ID {client_id}"

    database.delete_client(client_id)
    flash(f'Client "{client_name}" supprimé avec succès!', 'danger')

    # Réponse vide pour que HTMX supprime la ligne du tableau (le <tr>)
    # On déclenche un événement pour recharger les messages flash à part
    response = make_response("")
    response.headers['HX-Trigger'] = 'loadFlash'
    return response

@app.route('/run_analysis/<int:client_id>', methods=['POST'])
def run_analysis(client_id):
    """Lance le pipeline, crée un rapport IN_PROGRESS, et déclenche un rechargement de la liste."""
    
    conn = database.get_db_connection()
    client = conn.execute('SELECT name FROM clients WHERE id = ?', (client_id,)).fetchone()
    client_name = client['name'] if client else f"ID {client_id}"
    print(f"LOG: Requête reçue pour lancer l'analyse du client: {client_name}")

    # Étape 1: Créer l'enregistrement du rapport avec le statut 'IN_PROGRESS'
    utc_now = pytz.utc.localize(datetime.utcnow())
    mexico_tz = pytz.timezone("America/Mexico_City")
    mexico_now = utc_now.astimezone(mexico_tz)
    
    cursor = conn.execute('INSERT INTO reports (client_id, status, created_at) VALUES (?, ?, ?)', 
                          (client_id, 'IN_PROGRESS', mexico_now))
    report_id = cursor.lastrowid
    conn.commit()
    conn.close()
    print(f"LOG: Tâche pré-enregistrée dans la DB. Rapport ID: {report_id} avec statut IN_PROGRESS")
    
    # Étape 2: Lancer l'analyse en arrière-plan en lui passant le report_id
    analysis_thread = threading.Thread(target=pipeline.run_analysis_for_client, args=(client_id, report_id))
    analysis_thread.start()
    
    flash(f"L'analyse pour '{client_name}' a été lancée. La liste va se mettre à jour.", "info")
    
    # Étape 3: Renvoyer la réponse qui met à jour les messages flash et déclenche le rechargement de la liste.
    # Le bouton cliqué a pour target #flash-messages. La réponse met à jour cette cible.
    response = make_response(render_template('_flash_messages.html'))
    # On ajoute un header qui déclenche un événement personnalisé pour que la liste se recharge.
    response.headers['HX-Trigger'] = 'loadClientList'
    print("LOG: /run_analysis a renvoyé une réponse pour mettre à jour les messages et déclencher 'loadClientList'.")
    return response

@app.route('/clients')
def get_clients_list():
    """Route pour rafraîchir la liste des clients, utilisée pour le polling en chaîne."""
    print("LOG: /clients a été appelé pour rafraîchir la liste.")
    clients, is_analysis_running = get_clients_with_reports()
    
    if is_analysis_running:
        response = make_response(render_template('_client_list.html', clients=clients))
        # Si une analyse est en cours, on déclenche le prochain poll en renvoyant un header.
        response.headers['HX-Trigger-After-Settle'] = '{"loadClientList": {"delay": "5s"}}'
        print("LOG: Analyse en cours détectée. Déclenchement du prochain poll dans 5s.")
        return response
    else:
        print("LOG: Aucune analyse en cours. Arrêt du polling. Envoi de la liste finale et nettoyage des messages flash.")
        # On prépare une réponse en deux parties : la liste finale et un bloc de messages vide.
        client_list_html = render_template('_client_list.html', clients=clients)
        flash_messages_html = render_template('_flash_messages.html') # Sera vide car les messages ont déjà été consommés

        # On utilise un OOB (Out-of-Band) Swap pour mettre à jour la liste ET les messages en une seule fois.
        response_html = f"""
        {client_list_html}
        <div id="flash-messages" hx-swap-oob="true">
            {flash_messages_html}
        </div>
        """
        return make_response(response_html)

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