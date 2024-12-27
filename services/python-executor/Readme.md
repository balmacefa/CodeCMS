# Install

pip install -r requirements.txt

# Executar en modemo desarollo 
python -m debugpy --listen 0.0.0.0:5678 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload