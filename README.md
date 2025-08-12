# 1) (opcional) criar e ativar venv
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\Activate.ps1

# 2) instalar dependências
pip install -r requirements.txt

# 3) iniciar o mock FastAPI (deixe rodando)
python mock.py
# ou:
# uvicorn mock:app --host 127.0.0.1 --port 8000 --reload

# 4) em outro terminal, consultar
python main.py
