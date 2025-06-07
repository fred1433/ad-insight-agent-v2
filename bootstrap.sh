python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

pip install black ruff isort pydantic python-dotenv facebook-business google-cloud-videointelligence google-cloud-storage google-generativeai 