import json
import sys
import logging
from datetime import datetime

import requests
import mysql.connector
from mysql.connector import errorcode

# ==============================
# CONFIGURAÇÕES (edite aqui diretamente)
# ==============================
# eLabFTW
ELAB_URL = "https://SEU_ELN/api/v2"      # ex.: https://eln.exemplo.org/api/v2
ELAB_API_KEY = "SUA_CHAVE_API_AQUI"      # gere no seu usuário do eLabFTW

# MySQL
MYSQL_CFG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "root",
    "database": "platform_ext",
}

# Configura o sistema de logs para exibir informações úteis no terminal.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)

# Constantes do projeto
ITEM_TYPE_TITLE = "Paciente"
TEMPLATE_TITLE = "Análise Clínica Padrão"
TEMPLATE_BODY_HTML = """
<h2>Dados da Amostra</h2>
<ul>
    <li>ID Agendamento: {{agendamento_id}}</li>
    <li>ID Paciente (Item): {{item_paciente_id}}</li>
    <li>Data/Hora da Coleta: {{data_coleta}}</li>
    <li>Tipo de Amostra: {{tipo_amostra}}</li>
</ul>
<h2>Resultados Bioquímica</h2>
<table>
<thead><tr><th>Analito</th><th>Resultado</th><th>Unidade</th><th>Ref.</th><th>Obs.</th></tr></thead>
<tbody>
<tr><td>Glicose</td><td></td><td>mg/dL</td><td>70–99</td><td></td></tr>
<tr><td>Ureia</td><td></td><td>mg/dL</td><td>10–50</td><td></td></tr>
</tbody>
</table>
<h2>Observações Técnicas</h2><p></p>
""".strip()

# ==============================
# CLASSES PARA SEPARAR RESPONSABILIDADES
# ==============================

class ElabClient:
    """Uma classe dedicada a todas as interações com a API do eLabFTW."""
    def __init__(self, base_url: str, api_key: str, timeout=30):
        if not base_url or not api_key or "SUA_CHAVE" in api_key:
            raise ValueError("ELAB_URL e ELAB_API_KEY devem ser configurados no início do script.")
        self.base = base_url.rstrip("/")
        self.h = {"Authorization": api_key, "Accept": "application/json", "Content-Type": "application/json"}
        self.timeout = timeout

    def _request(self, method, path, **kwargs):
        url = f"{self.base}/{path.lstrip('/')}"
        try:
            response = requests.request(method, url, headers=self.h, timeout=self.timeout, **kwargs)
            response.raise_for_status()  # Lança uma exceção para erros HTTP (4xx ou 5xx)
            return response.json() if response.content else {}
        except requests.exceptions.HTTPError as e:
            logging.error(f"Erro HTTP na API do eLabFTW: {e.response.status_code} - {e.response.text}")
            raise
        except requests.exceptions.RequestException as e:
            logging.error(f"Erro de conexão com a API do eLabFTW: {e}")
            raise

    def get(self, path, params=None):
        return self._request("get", path, params=params)

    def post(self, path, payload=None):
        return self._request("post", path, json=payload or {})

    def patch(self, path, payload=None):
        return self._request("patch", path, json=payload or {})


class DatabaseManager:
    """Gerencia todas as operações do banco de dados da plataforma externa."""
    def __init__(self, config):
        self.config = config
        self._check_and_create_tables()

    def _get_connection(self):
        try:
            conn = mysql.connector.connect(**self.config)
            return conn
        except mysql.connector.Error as err:
            if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
                logging.error("Acesso negado. Verifique usuário/senha do MySQL.")
            elif err.errno == errorcode.ER_BAD_DB_ERROR:
                logging.error(f"Banco de dados '{self.config['database']}' não existe.")
            else:
                logging.error(f"Erro de conexão com o MySQL: {err}")
            raise

    def _check_and_create_tables(self):
        try:
            con = self._get_connection()
            cur = con.cursor()
            logging.info("Verificando se as tabelas 'patients' e 'appointments' existem...")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS patients (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    item_id INT NOT NULL UNIQUE,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS appointments (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    patient_id INT NOT NULL,
                    experiment_id INT NOT NULL UNIQUE,
                    status VARCHAR(255) NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_checked DATETIME NULL,
                    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE RESTRICT
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            con.commit()
            cur.close()
            con.close()
        except mysql.connector.Error as err:
            logging.error(f"Falha ao inicializar tabelas do banco de dados: {err}")
            sys.exit(1)

    def execute_query(self, query, params=None, fetch=None):
        try:
            con = self._get_connection()
            cur = con.cursor(dictionary=True)
            cur.execute(query, params or ())
            if fetch == 'one':
                result = cur.fetchone()
            elif fetch == 'all':
                result = cur.fetchall()
            else:
                con.commit()
                result = cur.lastrowid
            cur.close()
            con.close()
            return result
        except mysql.connector.Error as err:
            logging.error(f"Erro ao executar query no DB: {err}")
            raise


class PlatformService:
    """Orquestra as operações entre a API do eLabFTW e o banco de dados local."""
    def __init__(self, elab: ElabClient, db: DatabaseManager):
        self.elab = elab
        self.db = db
        self.patient_item_type_id = None
        self.analysis_template_id = None

    def initialize_elab_configs(self):
        logging.info("Inicializando configurações no eLabFTW (Item Type e Template)...")
        items_types = self.elab.get("items_types")
        for it in items_types:
            if it.get("title", "").strip().lower() == ITEM_TYPE_TITLE.lower():
                self.patient_item_type_id = it["id"]
                break
        if not self.patient_item_type_id:
            created = self.elab.post("items_types", {"title": ITEM_TYPE_TITLE})
            self.patient_item_type_id = created["id"]
        logging.info(f"ID do Item Type '{ITEM_TYPE_TITLE}': {self.patient_item_type_id}")

        templates = self.elab.get("experiments/templates")
        for tpl in templates:
            if tpl.get("title", "").strip().lower() == TEMPLATE_TITLE.lower():
                self.analysis_template_id = tpl["id"]
                break
        if not self.analysis_template_id:
            created = self.elab.post("experiments/templates", {"title": TEMPLATE_TITLE, "body": TEMPLATE_BODY_HTML})
            self.analysis_template_id = created["id"]
        logging.info(f"ID do Template '{TEMPLATE_TITLE}': {self.analysis_template_id}")

    def register_patient(self, name: str):
        if not self.patient_item_type_id:
            raise RuntimeError("Configurações do eLabFTW não inicializadas. Execute a inicialização primeiro.")

        logging.info(f"Criando item no eLabFTW para o paciente '{name}'...")
        created_item = self.elab.post("items", {"title": name, "items_type_id": self.patient_item_type_id})
        item_id = created_item.get("id")
        if not item_id:
             raise RuntimeError("Não foi possível obter o ID do item criado no eLabFTW.")

        logging.info(f"Salvando paciente no banco de dados local (item_id={item_id})...")
        patient_id = self.db.execute_query(
            "INSERT INTO patients(name, item_id) VALUES (%s, %s)",
            (name, item_id)
        )
        return {"local_id": patient_id, "elab_item_id": item_id}

    def schedule_analysis(self, local_patient_id: int, appointment_details: dict):
        patient = self.db.execute_query("SELECT * FROM patients WHERE id=%s", (local_patient_id,), fetch='one')
        if not patient:
            raise ValueError("Paciente com ID local não encontrado.")

        logging.info(f"Criando experimento no eLabFTW para o paciente ID {local_patient_id}...")
        title = f"Análises Paciente {patient['name']} - {datetime.now().date().isoformat()}"
        body_vars = {
            "agendamento_id": appointment_details.get("id", "N/A"),
            "item_paciente_id": patient["item_id"],
            "data_coleta": datetime.now().isoformat(timespec="minutes"),
            "tipo_amostra": appointment_details.get("sample_type", "Não especificado"),
        }
        
        body = TEMPLATE_BODY_HTML
        for k, v in body_vars.items():
            body = body.replace(f"{{{{{k}}}}}", str(v))
        
        created_exp = self.elab.post("experiments", {"title": title, "body": body})
        exp_id = created_exp.get("id")
        if not exp_id:
            raise RuntimeError("Não foi possível obter o ID do experimento criado no eLabFTW.")

        self.elab.post(f"experiments/{exp_id}/items", {"item_id": patient["item_id"]})
        logging.info(f"Experimento {exp_id} vinculado ao item {patient['item_id']}.")

        status = created_exp.get("status_name", "Em andamento")
        appointment_id = self.db.execute_query(
            "INSERT INTO appointments(patient_id, experiment_id, status) VALUES (%s, %s, %s)",
            (local_patient_id, exp_id, status)
        )
        return {"local_appointment_id": appointment_id, "elab_experiment_id": exp_id, "status": status}
    
    def check_experiment_status(self, experiment_id: int):
        logging.info(f"Verificando status do experimento {experiment_id}...")
        exp = self.elab.get(f"experiments/{experiment_id}")
        status = exp.get("status_name", "desconhecido")
        self.db.execute_query(
            "UPDATE appointments SET status=%s, last_checked=%s WHERE experiment_id=%s",
            (status, datetime.now(), experiment_id)
        )
        return status

    def process_webhook_notification(self, webhook_payload: dict):
        logging.info(f"Processando notificação de webhook recebida: {webhook_payload}")
        event = webhook_payload.get("event")
        data = webhook_payload.get("data")

        if event == "EXPERIMENT_UPDATED" and data:
            experiment_id = data.get("id")
            status = data.get("status_name")
            if experiment_id and status:
                logging.info(f"Webhook: Experimento {experiment_id} atualizado para status '{status}'.")
                self.db.execute_query(
                    "UPDATE appointments SET status=%s, last_checked=%s WHERE experiment_id=%s",
                    (status, datetime.now(), experiment_id)
                )
                logging.info("Status do agendamento atualizado no banco de dados local.")
            else:
                logging.warning("Webhook de experimento atualizado, mas sem dados suficientes.")
        else:
            logging.info("Webhook recebido, mas não é um evento de interesse.")


def main():
    try:
        elab_client = ElabClient(ELAB_URL, ELAB_API_KEY)
        db_manager = DatabaseManager(MYSQL_CFG)
        service = PlatformService(elab_client, db_manager)
    except (ValueError, mysql.connector.Error) as e:
        logging.error(f"Falha na inicialização. Verifique as configurações no início do script. Erro: {e}")
        sys.exit(1)

    while True:
        print("\n=== Plataforma Externa (PoC Refatorado) ===")
        print("1) Inicializar Configurações no eLabFTW")
        print("2) Cadastrar novo paciente")
        print("3) Agendar análise para paciente")
        print("4) Verificar status de uma análise (Polling)")
        print("5) Simular recebimento de Webhook (Análise Concluída)")
        print("6) Sair")
        op = input("> Escolha: ").strip()

        try:
            if op == "1":
                service.initialize_elab_configs()
            elif op == "2":
                name = input("Nome do paciente: ").strip()
                if name:
                    result = service.register_patient(name)
                    logging.info(f"Paciente cadastrado com sucesso! ID Local: {result['local_id']}, ID eLabFTW: {result['elab_item_id']}")
                else:
                    logging.warning("Nome inválido.")
            elif op == "3":
                pid_str = input("ID local do paciente: ").strip()
                if pid_str.isdigit():
                    details = {"sample_type": input("Tipo de amostra (ex: Sangue): ").strip()}
                    result = service.schedule_analysis(int(pid_str), details)
                    logging.info(f"Análise agendada! ID Agendamento: {result['local_appointment_id']}, ID Experimento: {result['elab_experiment_id']}, Status: '{result['status']}'")
                else:
                    logging.warning("ID do paciente inválido.")
            elif op == "4":
                exp_id_str = input("ID do experimento no eLabFTW: ").strip()
                if exp_id_str.isdigit():
                    status = service.check_experiment_status(int(exp_id_str))
                    logging.info(f"Status atual do experimento {exp_id_str}: '{status}'")
                else:
                    logging.warning("ID do experimento inválido.")
            elif op == "5":
                exp_id_str = input("ID do experimento que foi 'concluído': ").strip()
                if exp_id_str.isdigit():
                    mock_webhook_payload = {
                        "event": "EXPERIMENT_UPDATED",
                        "data": { "id": int(exp_id_str), "status_name": "Concluído" }
                    }
                    service.process_webhook_notification(mock_webhook_payload)
                else:
                    logging.warning("ID do experimento inválido.")
            elif op == "6":
                logging.info("Saindo.")
                break
            else:
                logging.warning("Opção inválida.")
        except (RuntimeError, ValueError, requests.exceptions.RequestException, mysql.connector.Error) as e:
            logging.error(f"Ocorreu um erro durante a operação: {e}")

if __name__ == "__main__":
    main()
