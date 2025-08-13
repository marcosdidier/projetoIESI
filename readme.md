# 1) instalar deps
pip install -r requirements.txt

# 2) (opcional) criar DB no MySQL (vide SQL acima) e ajuste MYSQL_CFG no código se precisar
-- rode no seu MySQL uma vez (ajuste o nome se quiser)
CREATE DATABASE IF NOT EXISTS platform_ext
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

# 3) edite ELAB_URL e ELAB_API_KEY no topo do main.py

# 4) rodar
python main.py
