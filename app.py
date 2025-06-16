from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, make_response, Response, jsonify, session, abort
from datetime import datetime, timezone
from dateutil import parser
import database
from database import get_report_by_id, get_ad_script, update_ad_script
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
class SuppressReportStatusFilter(logging.Filter):
    def filter(self, record):
        return '/report_status/' not in record.getMessage()

log = logging.getLogger('werkzeug')
log.addFilter(SuppressReportStatusFilter())
# --- FIN DU FILTRE ---

app = Flask(__name__)
database.init_db()
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'une-super-cle-secrete-a-changer-en-prod')

# --- FILTRES DE TEMPLATE ---
@app.template_filter('format_datetime')
def format_datetime_filter(s):
    """Filtre pour formater une date pour l'affichage."""
    if not s:
        return "N/A"
    try:
        # On suppose que la date de la DB est un string ISO-like
        dt_utc = parser.parse(s)
        # On la convertit en fuseau horaire local si nécessaire (exemple: Europe/Paris)
        # ou on la garde en UTC si on préfère. Pour l'instant, on affiche simplement.
        return dt_utc.strftime('%d/%m/%Y à %H:%M')
    except (parser.ParserError, TypeError):
        return s # Retourne la chaîne originale si le parsing échoue

@app.template_filter('format_error')
def format_error_filter(s):
    """Filtre pour rendre les messages d'erreur plus lisibles pour l'utilisateur."""
    if not isinstance(s, str):
        s = str(s)

    if "TimeoutException" in s:
        return "La carga de la página del anuncio expiró (Timeout). El anuncio puede ser inaccesible o estar protegido."
    if "500 An internal error" in s or "InternalServerError" in s:
        return "La API de análisis (Google Gemini) devolvió un error interno. Por favor, reintenta más tarde."
    if "Échec du téléchargement du média" in s:
        return "No se pudo descargar el video o la imagen del anuncio."
    if "Réponse invalide ou vide de l'API Gemini" in s:
        return "La API de análisis (Google Gemini) devolvió una respuesta vacía o inválida."
    
    # Par défaut, on retourne une version courte et nettoyée
    return s.split('\\n')[0][:150] + "..." if len(s) > 150 else s.split('\\n')[0]

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

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/report_status/<int:report_id>')
def get_report_status(report_id):
    conn = database.get_db_connection()
    report = conn.execute('SELECT status FROM analyses WHERE id = ?', (report_id,)).fetchone()
    conn.close()

    if report and report['status'] in ('IN_PROGRESS', 'RUNNING'):
        return "", 204
    else:
        source = request.args.get('source')
        response = make_response("")
        if source == 'pending_page':
            response.headers['HX-Refresh'] = 'true'
        else:
            response.headers['HX-Trigger'] = 'loadClientList'
        return response

@app.route('/add_client', methods=['POST'])
@login_required
def add_client():
    name = request.form['name']
    token = request.form['facebook_token']
    ad_account_id = request.form.get('ad_account_id')

    if not ad_account_id or not ad_account_id.startswith('act_'):
        flash("Por favor, verifica el token y selecciona una cuenta publicitaria válida.", "warning")
        response = make_response()
        response.headers['HX-Refresh'] = 'true'
        return response

    database.add_client(name, token, ad_account_id)
    flash(f'Cliente "{name}" añadido con éxito.', 'success')
    response = make_response()
    response.headers['HX-Refresh'] = 'true'
    return response

@app.route('/delete_client/<int:client_id>', methods=['DELETE'])
@login_required
def delete_client(client_id):
    conn = database.get_db_connection()
    client = conn.execute('SELECT name FROM clients WHERE id = ?', (client_id,)).fetchone()
    conn.close()
    client_name = client['name'] if client else f"ID {client_id}"

    database.delete_client(client_id)
    flash(f'Cliente "{client_name}" eliminado con éxito.', 'danger')

    response = make_response("")
    response.headers['HX-Trigger'] = 'loadFlash'
    return response

@app.route('/delete_report/<int:report_id>', methods=['DELETE'])
@login_required
def delete_report(report_id):
    """Supprime un rapport d'analyse de la base de données."""
    try:
        conn = database.get_db_connection()
        # On vérifie d'abord si le rapport existe pour pouvoir flasher un message pertinent
        report = conn.execute('SELECT id FROM analyses WHERE id = ?', (report_id,)).fetchone()
        
        if report:
            conn.execute('DELETE FROM analyses WHERE id = ?', (report_id,))
            conn.commit()
            flash(f"El informe ID {report_id} ha sido eliminado.", "success")
        else:
            flash(f"No se encontró el informe ID {report_id}.", "warning")
        
        conn.close()
    except Exception as e:
        # Log de l'erreur
        print(f"Error al eliminar el informe {report_id}: {e}")
        flash("Ocurrió un error al intentar eliminar el informe.", "danger")

    # On déclenche un événement pour que le conteneur de flash messages se recharge
    response = make_response("")
    response.headers['HX-Trigger'] = 'loadFlash'
    return response

@app.route('/flash-messages')
def flash_messages():
    return render_template('_flash_messages.html')

@app.route('/validate-token', methods=['POST'])
@login_required
def validate_token():
    token = request.form.get('facebook_token')
    if not token:
        return '<div id="token-validation-result" class="validation-message"></div>'

    is_valid, message, ad_accounts = facebook_client.check_token_validity(token)
    
    css_class = "text-success" if is_valid and ad_accounts else "text-danger"
    icon = "✅" if is_valid and ad_accounts else "❌"
    status_message_html = f'<small class="{css_class}">{icon} {message}</small>'

    ad_account_selector_html = ""
    if is_valid and ad_accounts:
        ad_account_selector_html = f'''
            <div class="form-group" style="margin-top: 15px;">
                <label for="ad_account_id">Cuenta Publicitaria a Analizar</label>
                <select name="ad_account_id" id="ad_account_id" class="form-control" required
                        hx-post="{url_for('unlock_submit')}" hx-target="#submit-button-container" hx-swap="innerHTML">
                    <option value="" disabled selected>Selecciona una cuenta</option>
        '''
        for account in ad_accounts:
            ad_account_selector_html += f'<option value="{account.get("id")}">{account.get("name")} ({account.get("account_id")})</option>'
        ad_account_selector_html += '</select></div>'

    return f'<div id="token-validation-result" class="validation-message">{status_message_html}{ad_account_selector_html}</div>'

@app.route('/lock-submit', methods=['GET', 'POST'])
def lock_submit():
    return '<button type="submit" id="add-client-btn" class="btn btn-primary" disabled>Añadir Cliente</button>'

@app.route('/unlock-submit', methods=['GET', 'POST'])
def unlock_submit():
    return '<button type="submit" id="add-client-btn" class="btn btn-primary">Añadir Cliente</button>'

@app.route('/run_top_n_analysis/<int:client_id>', methods=['POST'])
@login_required
def run_top_n_analysis(client_id):
    analysis_code = request.form.get('analysis_code')
    if not analysis_code or analysis_code != config.auth.analysis_access_code:
        flash("Código de análisis inválido o faltante.", "danger")
        return render_template('_flash_messages.html')

    conn = database.get_db_connection()
    client = conn.execute('SELECT name FROM clients WHERE id = ?', (client_id,)).fetchone()
    conn.close()
    
    if not client:
        flash(f"Cliente con ID {client_id} no encontrado.", "danger")
        return redirect(url_for('index'))

    client_name = client['name']
    top_n = request.form.get('top_n_to_analyze', 5, type=int)

    print(f"LOG: Requête reçue pour lancer l'analyse del Top {top_n} para el cliente: {client_name}")

    created_at_local = datetime.now(pytz.timezone("America/Mexico_City"))
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO analyses (client_id, status, media_type, created_at) VALUES (?, ?, ?, ?)",
        (client_id, 'IN_PROGRESS', f'Top {top_n}', created_at_local.strftime('%Y-%m-%d %H:%M:%S'))
    )
    report_id = cursor.lastrowid
    conn.commit()
    conn.close()

    thread = threading.Thread(target=pipeline.run_top_n_analysis_for_client, args=(client_id, report_id, top_n))
    thread.start()

    flash(f"Análisis Top {top_n} para '{client_name}' ha comenzado. El informe aparecerá aquí en breve.", 'info')

    response = make_response("")
    response.headers['HX-Trigger'] = json.dumps({
        "loadClientList": None,
        "loadFlash": None,
        "closeModal": None
    })
    return response

@app.route('/clients')
def get_clients_list():
    conn = database.get_db_connection()
    clients_list = conn.execute('SELECT id, name, ad_account_id FROM clients ORDER BY name').fetchall()
    
    clients_with_analyses = []
    for client in clients_list:
        client_dict = dict(client)
        analyses_cursor = conn.execute(
            'SELECT * FROM analyses WHERE client_id = ? ORDER BY created_at DESC', (client['id'],)
        )
        
        analyses_list = []
        for row in analyses_cursor.fetchall():
            analysis_dict = dict(row)
            if analysis_dict.get('created_at') and isinstance(analysis_dict['created_at'], str):
                try:
                    analysis_dict['created_at'] = parser.parse(analysis_dict['created_at'])
                except parser.ParserError:
                    analysis_dict['created_at'] = None
            
            # Récupérer les erreurs associées à ce rapport
            analysis_dict['errors'] = database.get_errors_for_report(analysis_dict['id'])
            
            analyses_list.append(analysis_dict)

        client_dict['analyses'] = analyses_list
        clients_with_analyses.append(client_dict)
    conn.close()
    
    return render_template('_client_list.html', clients=clients_with_analyses)

@app.route('/get_analysis_modal/<int:client_id>')
def get_analysis_modal(client_id):
    """Renvoie le contenu HTML du formulaire de la modale pour un client donné."""
    return render_template('_analysis_modal_form.html', client_id=client_id)

@app.route('/report/<int:report_id>')
@login_required
def view_report(report_id):
    report = get_report_by_id(report_id)
    if not report:
        abort(404)
    
    analyzed_ads_data = json.loads(report.analyzed_ads_data) if report.analyzed_ads_data else []
    scripts_data = {script.ad_id: script for script in report.scripts}

    return render_template('analysis_report.html',
                           report=report,
                           analyzed_ads_data=analyzed_ads_data,
                           scripts_data=scripts_data,
                           num_analyzed=report.num_analyzed)

@app.route('/report/<int:report_id>/ad/<string:ad_id>/update_script', methods=['POST'])
@login_required
def update_ad_script(report_id, ad_id):
    data = request.get_json()
    updated_html = data.get('script_html')
    if not updated_html:
        return jsonify(status='error', message='Contenido vacío.'), 400
    
    conn = database.get_db_connection()
    conn.execute(
        "UPDATE ad_scripts SET edited_script_html = ? WHERE report_id = ? AND ad_id = ?",
        (updated_html, report_id, ad_id)
    )
    conn.commit()
    conn.close()
    return jsonify(status='success', message='Script actualizado.')

@app.route('/storage/<path:filename>')
def serve_storage_file(filename):
    return send_from_directory(os.path.join(app.root_path, 'data', 'storage'), filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000, debug=True)