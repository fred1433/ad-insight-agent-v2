from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, make_response, Response, jsonify, session
from datetime import datetime
from dateutil import parser
import database
import threading
import pipeline
import pytz
import logging
import os
import facebook_client
from functools import wraps
from config import config

# --- FILTRE DE LOGS ---
# Filtre pour ne pas afficher les requêtes de polling dans le terminal
class SuppressReportStatusFilter(logging.Filter):
    def filter(self, record):
        # record.getMessage() contient la ligne de log, ex: "GET /report_status/5 HTTP/1.1" 204
        return '/report_status/' not in record.getMessage()

# Appliquer le filtre au logger par défaut de Werkzeug (qui gère les requêtes HTTP)
log = logging.getLogger('werkzeug')
log.addFilter(SuppressReportStatusFilter())

# --- FIN DU FILTRE ---


# Crée l'application Flask
app = Flask(__name__)

# Configure une clé secrète pour la gestion des sessions (utile pour les messages flash)
app.config['SECRET_KEY'] = 'une-super-cle-secrete-a-changer-en-prod'

# --- GESTION DE L'AUTHENTIFICATION ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('access_code') == config.auth.app_access_code:
            session['authenticated'] = True
            return redirect(url_for('index'))
        else:
            flash("Código de acceso inválido.", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    flash("Has cerrado sesión.", "info")
    return redirect(url_for('login'))
# -----------------------------------------

def get_clients_with_reports():
    """Récupère tous les clients avec leurs rapports."""
    conn = database.get_db_connection()
    clients_cursor = conn.execute('SELECT * FROM clients ORDER BY name')
    clients_list = clients_cursor.fetchall()

    clients_with_reports = []
    
    for client in clients_list:
        client_dict = dict(client)
        reports_cursor = conn.execute(
            'SELECT id, status, report_path, created_at, ad_id, cost_analysis, cost_generation, total_cost FROM reports WHERE client_id = ? ORDER BY created_at DESC',
            (client['id'],)
        )
        
        reports = []
        for row in reports_cursor.fetchall():
            report_dict = dict(row)
            if report_dict['created_at']:
                report_dict['created_at'] = parser.parse(report_dict['created_at'])
            reports.append(report_dict)
            
        client_dict['reports'] = reports
        clients_with_reports.append(client_dict)

    conn.close()
    return clients_with_reports

@app.route('/')
@login_required
def index():
    """Affiche la page principale."""
    return render_template('index.html')

@app.route('/report_status/<int:report_id>')
def get_report_status(report_id):
    """Vérifie le statut d'un rapport. Utilisé pour le polling intelligent."""
    conn = database.get_db_connection()
    report = conn.execute('SELECT status FROM reports WHERE id = ?', (report_id,)).fetchone()
    conn.close()

    if report and report['status'] in ('IN_PROGRESS', 'RUNNING'):
        # Le rapport est toujours en cours. On renvoie 204 No Content pour que
        # HTMX ne fasse rien et continue le polling.
        return "", 204
    else:
        # Le rapport est terminé (ou a échoué).
        # On renvoie une réponse vide, mais avec un header qui déclenche le 
        # rechargement de toute la liste des clients. Le polling s'arrêtera 
        # car le badge qui le déclenchait sera remplacé.
        response = make_response("")
        response.headers['HX-Trigger'] = 'loadClientList'
        return response

@app.route('/add_client', methods=['POST'])
def add_client():
    """Traite la soumission du formulaire pour ajouter un nouveau client."""
    name = request.form['name']
    token = request.form['facebook_token']
    spend = request.form['spend_threshold']
    cpa = request.form['cpa_threshold']
    
    database.add_client(name, token, spend, cpa)
    
    # Message de succès
    flash(f'Cliente "{name}" añadido con éxito.', 'success')
    
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
    flash(f'Cliente "{client_name}" eliminado con éxito.', 'danger')

    # Réponse vide pour que HTMX supprime la ligne du tableau (le <tr>)
    # On déclenche un événement pour recharger les messages flash à part
    response = make_response("")
    response.headers['HX-Trigger'] = 'loadFlash'
    return response

@app.route('/run_analysis/<int:client_id>/<string:media_type>', methods=['POST'])
@login_required
def run_analysis(client_id, media_type):
    """Lance le pipeline et crée un rapport."""
    
    analysis_code = request.form.get('analysis_code')
    if not analysis_code or analysis_code != config.auth.analysis_access_code:
        flash("Código de análisis inválido o faltante.", "danger")
        # On renvoie juste un rechargement des messages flash
        response = make_response(render_template('_flash_messages.html'))
        return response # On renvoie 200 OK pour que HTMX fasse le swap

    if media_type not in ['video', 'image']:
        return "Type de média non valide.", 400

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
    
    # Étape 2: Lancer l'analyse en arrière-plan. Plus besoin de queue.
    analysis_thread = threading.Thread(
        target=pipeline.run_analysis_for_client, 
        args=(client_id, report_id, media_type)
    )
    analysis_thread.start()
    
    flash(f"El análisis de tipo '{media_type}' para '{client_name}' ha comenzado.", "info")
    
    # Étape 3: Renvoyer la réponse qui met à jour les messages flash et recharge la liste (pour voir le statut PENDING).
    response = make_response(render_template('_flash_messages.html'))
    response.headers['HX-Trigger'] = 'loadClientList'
    return response

@app.route('/clients')
def get_clients_list():
    """Route pour rafraîchir la liste des clients, utilisée par HTMX."""
    clients = get_clients_with_reports()
    return render_template('_client_list.html', clients=clients)

@app.route('/report/<int:report_id>')
def view_report(report_id):
    """Affiche un rapport spécifique depuis la base de données."""
    conn = database.get_db_connection()
    # On joint avec la table clients pour récupérer le nom du client
    report = conn.execute("""
        SELECT r.*, c.name as client_name 
        FROM reports r 
        JOIN clients c ON r.client_id = c.id 
        WHERE r.id = ?
    """, (report_id,)).fetchone()
    conn.close()
    
    if report is None:
        return "Rapport non trouvé", 404
    
    # On récupère l'objet Ad complet pour avoir les KPIs
    ad = facebook_client.get_ad_by_id(report['ad_id'])

    return render_template('report.html', report=report, insights=(ad.insights if ad else None))

@app.route('/report/<int:report_id>/update', methods=['POST'])
def update_report_script(report_id):
    """Met à jour le fragment HTML du script pour un rapport."""
    data = request.json
    script_html = data.get('script_html')

    if script_html is None:
        return jsonify({'status': 'error', 'message': 'Contenido faltante'}), 400

    try:
        conn = database.get_db_connection()
        conn.execute('UPDATE reports SET script_html = ? WHERE id = ?', (script_html, report_id))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'message': 'Rapport actualizado'})
    except Exception as e:
        print(f"Error al actualizar el informe {report_id}: {e}")
        return jsonify({'status': 'error', 'message': 'Error interno del servidor'}), 500

@app.route('/storage/<path:filename>')
def serve_storage_file(filename):
    """Sert les fichiers depuis le dossier de stockage."""
    return send_from_directory('storage', filename)

def setup_database():
    """Initialise la base de données si elle n'existe pas."""
    db_path = database.DATABASE_FILE
    if not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
        database.init_db()
        flash("La base de données a été initialisée.", "info")

if __name__ == '__main__':
    print("Démarrage de l'application...")
    setup_database()
    app.run(debug=True, port=5001)