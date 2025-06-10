from flask import Flask, render_template, request, redirect, url_for, flash
import database

# Crée l'application Flask
app = Flask(__name__)

# Configure une clé secrète pour la gestion des sessions (utile pour les messages flash)
app.config['SECRET_KEY'] = 'une-super-cle-secrete-a-changer-en-prod'

@app.route('/')
def index():
    """Affiche la page principale avec la liste des clients et le formulaire d'ajout."""
    clients = database.get_all_clients()
    return render_template('index.html', clients=clients)

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