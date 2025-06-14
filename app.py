from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, make_response, Response, jsonify, session
from datetime import datetime, timezone
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
import json

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

# Appel pour s'assurer que la base de données est initialisée au démarrage
database.init_db()

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
        source = request.args.get('source')
        response = make_response("")
        
        if source == 'pending_page':
            # On est sur la page d'attente, on la rafraîchit complètement
            # pour afficher le rapport final (ou une erreur).
            response.headers['HX-Refresh'] = 'true'
        else:
            # On est sur la page principale, on recharge juste la liste
            # des clients pour mettre à jour le statut.
            response.headers['HX-Trigger'] = 'loadClientList'
            
        return response

@app.route('/add_client', methods=['POST'])
def add_client():
    """Traite la soumission du formulaire pour ajouter un nouveau client."""
    name = request.form['name']
    token = request.form['facebook_token']
    ad_account_id = request.form.get('ad_account_id')
    spend = request.form['spend_threshold']
    cpa = request.form['cpa_threshold']
    
    # --- VALIDATION CÔTÉ SERVEUR ---
    # S'assure qu'un compte publicitaire a bien été sélectionné depuis le menu déroulant.
    if not ad_account_id or not ad_account_id.startswith('act_'):
        flash("Por favor, verifica el token y selecciona una cuenta publicitaria válida antes de añadir el cliente.", "warning")
        # On force un rechargement complet pour que l'utilisateur puisse recommencer le processus.
        response = make_response()
        response.headers['HX-Refresh'] = 'true'
        return response

    database.add_client(name, token, ad_account_id, spend, cpa)
    
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

@app.route('/flash-messages')
def flash_messages():
    """Route pour rafraîchir uniquement les messages flash."""
    return render_template('_flash_messages.html')

@app.route('/validate-token', methods=['POST'])
def validate_token():
    """Valide un token Facebook et renvoie un sélecteur de cuenta publicitaria si valide."""
    token = request.form.get('facebook_token')
    if not token:
        return '<div id="token-validation-result" class="validation-message"></div>'

    is_valid, message, ad_accounts = facebook_client.check_token_validity(token)
    
    # Construction del mensaje de estado
    css_class = "text-success" if is_valid and ad_accounts else "text-danger"
    icon = "✅" if is_valid and ad_accounts else "❌"
    status_message_html = f'<small class="{css_class}">{icon} {message}</small>'

    # Construction del selector de cuenta si el token es valido y tiene cuentas
    ad_account_selector_html = ""
    if is_valid and ad_accounts:
        ad_account_selector_html = f'''
            <div class="form-group" style="margin-top: 15px;">
                <label for="ad_account_id">Cuenta Publicitaria a Analizar</label>
                <select name="ad_account_id" id="ad_account_id" class="form-control" required
                        hx-post="{url_for('unlock_submit')}"
                        hx-target="#submit-button-container"
                        hx-swap="innerHTML">
                    <option value="" disabled selected>Selecciona una cuenta</option>
        '''
        for account in ad_accounts:
            # On utiliza 'id' para el valor (ex: act_123) y 'account_id' para el display
            ad_account_selector_html += f'<option value="{account.get("id")}">{account.get("name")} ({account.get("account_id")})</option>'
        
        ad_account_selector_html += '''
                </select>
            </div>
        '''

    # On combina las dos partes y las envuelve en la div objetivo
    return f'''
        <div id="token-validation-result" class="validation-message">
            {status_message_html}
            {ad_account_selector_html}
        </div>
    '''

@app.route('/lock-submit', methods=['GET', 'POST'])
def lock_submit():
    """Renvoie el botón de envío en estado desactivado."""
    return '<button type="submit" id="add-client-btn" class="btn btn-primary" disabled>Añadir Cliente</button>'

@app.route('/unlock-submit', methods=['GET', 'POST'])
def unlock_submit():
    """Renvoie el botón de envío en estado activado."""
    return '<button type="submit" id="add-client-btn" class="btn btn-primary">Añadir Cliente</button>'

@app.route('/run_analysis/<int:client_id>/<string:media_type>', methods=['POST'])
@login_required
def run_analysis(client_id, media_type):
    """Lance el pipeline y crea un informe."""
    
    analysis_code = request.form.get('analysis_code')
    if not analysis_code or analysis_code != config.auth.analysis_access_code:
        flash("Código de análisis inválido o faltante.", "danger")
        # On renvoie juste un rechargement des messages flash
        return render_template('_flash_messages.html')

    if media_type not in ['video', 'image']:
        flash("Tipo de medio no válido.", "warning")
        return render_template('_flash_messages.html')

    conn = database.get_db_connection()
    client = conn.execute('SELECT name FROM clients WHERE id = ?', (client_id,)).fetchone()
    client_name = client['name'] if client else f"ID {client_id}"
    print(f"LOG: Requête reçue pour lancer l'analyse del cliente: {client_name}")

    # Étape 1: Crear el registro del informe con el estado 'IN_PROGRESS'
    utc_now = datetime.now(timezone.utc)
    mexico_tz = pytz.timezone("America/Mexico_City")
    mexico_now = utc_now.astimezone(mexico_tz)
    
    cursor = conn.execute('INSERT INTO reports (client_id, status, created_at, media_type) VALUES (?, ?, ?, ?)', 
                          (client_id, 'IN_PROGRESS', mexico_now.isoformat(), media_type))
    report_id = cursor.lastrowid
    conn.commit()
    conn.close()
    print(f"LOG: Tarea pre-registrada en la DB. Informe ID: {report_id} con estado IN_PROGRESS")
    
    # Étape 2: Lanzar la analítica en segundo plano. No se necesita cola.
    analysis_thread = threading.Thread(
        target=pipeline.run_analysis_for_client, 
        args=(client_id, report_id, media_type)
    )
    analysis_thread.start()
    
    flash(f"El análisis de tipo '{media_type}' para '{client_name}' ha comenzado.", "info")
    
    # Étape 3: Renvoyer la respuesta que actualiza los mensajes flash y recarga la lista (para ver el estado PENDING).
    response = make_response(render_template('_flash_messages.html'))
    response.headers['HX-Trigger'] = 'loadClientList'
    return response

@app.route('/run_top5_analysis/<int:client_id>', methods=['POST'])
@login_required
def run_top5_analysis(client_id):
    """Lance el pipeline para el Top 5 y crea un informe consolidado."""
    
    analysis_code = request.form.get('analysis_code')
    if not analysis_code or analysis_code != config.auth.analysis_access_code:
        flash("Código de análisis inválido o faltante.", "danger")
        return render_template('_flash_messages.html')

    conn = database.get_db_connection()
    client = conn.execute('SELECT name FROM clients WHERE id = ?', (client_id,)).fetchone()
    client_name = client['name'] if client else f"ID {client_id}"
    print(f"LOG: Requête reçue pour lancer l'analyse del Top 5 para el cliente: {client_name}")

    # Étape 1: Crear el registro del informe con el estado 'IN_PROGRESS' y el tipo 'top5'
    utc_now = datetime.now(timezone.utc)
    mexico_tz = pytz.timezone("America/Mexico_City")
    mexico_now = utc_now.astimezone(mexico_tz)
    
    cursor = conn.execute('INSERT INTO reports (client_id, status, created_at, media_type) VALUES (?, ?, ?, ?)', 
                          (client_id, 'IN_PROGRESS', mexico_now.isoformat(), 'top5'))
    report_id = cursor.lastrowid
    conn.commit()
    conn.close()
    print(f"LOG: Tarea pre-registrada en la DB. Informe ID: {report_id} con estado IN_PROGRESS para análisis Top 5")
    
    # Étape 2: Lanzar la analítica en segundo plano.
    analysis_thread = threading.Thread(
        target=pipeline.run_top5_analysis_for_client, 
        args=(client_id, report_id)
    )
    analysis_thread.start()
    
    flash(f"El análisis Top 5 para '{client_name}' ha comenzado.", "info")
    
    # Étape 3: Renvoyer la respuesta que actualiza los mensajes flash y recarga la lista.
    response = make_response(render_template('_flash_messages.html'))
    response.headers['HX-Trigger'] = 'loadClientList'
    return response

@app.route('/clients')
def get_clients_list():
    """Route para recargar la lista de clientes, utilizada por HTMX."""
    clients = get_clients_with_reports()
    return render_template('_client_list.html', clients=clients)

@app.route('/report/<int:report_id>')
@login_required
def view_report(report_id):
    """Affiche un rapport d'analyse spécifique, qu'il soit simple ou consolidé."""
    conn = database.get_db_connection()
    report = conn.execute('SELECT * FROM reports WHERE id = ?', (report_id,)).fetchone()
    
    if not report:
        flash("Informe no encontrado.", "danger")
        return redirect(url_for('index'))

    # Pour les anciens rapports ou les analyses simples
    ad = None
    if report['media_type'] != 'top5':
        if report['ad_id']:
            try:
                # Initialisation de l'API nécessaire pour récupérer les détails de l'annonce
                client = conn.execute('SELECT facebook_token, ad_account_id FROM clients WHERE id = ?', (report['client_id'],)).fetchone()
                facebook_client.init_facebook_api(client['facebook_token'], client['ad_account_id'])
                ad = facebook_client.get_ad_details(report['ad_id'])
            except Exception as e:
                print(f"No se pudo obtener detalles del anuncio {report['ad_id']}: {e}")
                ad = None # Assure que 'ad' est None si la récupération échoue
        conn.close()
        return render_template('report.html', report=dict(report), ad=ad)
    
    # --- NOUVELLE LOGIQUE POUR LES RAPPORTS TOP 5 ---
    else:
        # L'analyse est stockée en JSON
        try:
            analyzed_ads_data = json.loads(report['analysis_html'])
        except (json.JSONDecodeError, TypeError):
            analyzed_ads_data = []

        # On récupère tous les scripts associés à ce rapport
        scripts_cursor = conn.execute('SELECT * FROM ad_scripts WHERE report_id = ?', (report_id,))
        scripts_data = {row['ad_id']: dict(row) for row in scripts_cursor.fetchall()}
        
        conn.close()
        
        # On passe la structure JSON et les données des scripts au template
        return render_template(
            'top5_report.html', 
            report=dict(report), 
            analyzed_ads_data=analyzed_ads_data,
            scripts_data=scripts_data
        )

@app.route('/report/<int:report_id>/ad/<string:ad_id>/update_script', methods=['POST'])
@login_required
def update_ad_script(report_id, ad_id):
    """Met à jour le contenu HTML d'un script spécifique pour une annonce dans un rapport."""
    data = request.get_json()
    updated_html = data.get('script_html')
    if updated_html is None:
        return jsonify({"status": "error", "message": "Contenido faltante."}), 400

    try:
        conn = database.get_db_connection()
        conn.execute(
            "UPDATE ad_scripts SET edited_script_html = ? WHERE report_id = ? AND ad_id = ?",
            (updated_html, report_id, ad_id)
        )
        conn.commit()
        conn.close()
        return jsonify({"status": "success"})
    except Exception as e:
        print(f"Error al actualizar el script: {e}")
        return jsonify({"status": "error", "message": "Error interno del servidor."}), 500

@app.route('/report/<int:report_id>/update', methods=['POST'])
@login_required
def update_report_script(report_id):
    """Met à jour le fragment HTML del script para un informe."""
    data = request.json
    script_html = data.get('script_html')

    if script_html is None:
        return jsonify({'status': 'error', 'message': 'Contenido faltante'}), 400

    try:
        conn = database.get_db_connection()
        conn.execute('UPDATE reports SET script_html = ? WHERE id = ?', (script_html, report_id))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'message': 'Informe actualizado'})
    except Exception as e:
        print(f"Error al actualizar el informe {report_id}: {e}")
        return jsonify({'status': 'error', 'message': 'Error interno del servidor'}), 500

@app.route('/storage/<path:filename>')
def serve_storage_file(filename):
    """Sert les fichiers depuis el directorio de almacenamiento (informes HTML)."""
    return send_from_directory(os.path.join('data', 'storage'), filename)

# Point d'entrée para el desarrollo local
if __name__ == '__main__':
    app.run(debug=True, port=5001, host='0.0.0.0')