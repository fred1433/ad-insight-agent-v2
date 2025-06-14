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
class SuppressReportStatusFilter(logging.Filter):
    def filter(self, record):
        return '/report_status/' not in record.getMessage()

log = logging.getLogger('werkzeug')
log.addFilter(SuppressReportStatusFilter())
# --- FIN DU FILTRE ---

app = Flask(__name__)
database.init_db()
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'une-super-cle-secrete-a-changer-en-prod')

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
            analyses_list.append(analysis_dict)

        client_dict['analyses'] = analyses_list
        clients_with_analyses.append(client_dict)
    conn.close()
    
    return render_template('_client_list.html', clients=clients_with_analyses)

@app.route('/report/<int:report_id>')
@login_required
def view_report(report_id):
    conn = database.get_db_connection()
    report_data = conn.execute(
        "SELECT r.*, c.name as client_name FROM analyses r JOIN clients c ON r.client_id = c.id WHERE r.id = ?", (report_id,)
    ).fetchone()
    conn.close()

    if not report_data:
        flash("Informe no encontrado.", "danger")
        return redirect(url_for('index'))

    if report_data['status'] != 'COMPLETED':
        return render_template('report_pending.html', client_name=report_data['client_name'], report_id=report_data['id'])
    
    try:
        analyzed_ads_data = json.loads(report_data['analysis_html'])
    except (json.JSONDecodeError, TypeError):
        analyzed_ads_data = []
    
    conn = database.get_db_connection()
    scripts_cursor = conn.execute('SELECT ad_id, original_script_html, edited_script_html FROM ad_scripts WHERE report_id = ?', (report_id,))
    scripts_data = {row['ad_id']: dict(row) for row in scripts_cursor.fetchall()}
    conn.close()

    return render_template('top5_report.html', 
                           report=report_data, 
                           analyzed_ads_data=analyzed_ads_data,
                           scripts_data=scripts_data,
                           num_analyzed=len(analyzed_ads_data))

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