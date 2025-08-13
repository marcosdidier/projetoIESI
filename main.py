#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import sys
from datetime import datetime

import requests
import mysql.connector

# ==============================
# CONFIGURAÇÕES (edite aqui)
# ==============================
# eLabFTW
ELAB_URL = "https://SEU_ELN/api/v2"     # ex.: https://eln.exemplo.org/api/v2
ELAB_API_KEY = "SUA_CHAVE_API_AQUI"     # gere no seu usuário do eLabFTW

# MySQL
MYSQL_CFG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "root",
    "database": "platform_ext",
}

# Títulos usados no passo 2
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
<tr><td>Creatinina</td><td></td><td>mg/dL</td><td>0.7–1.3</td><td></td></tr>
</tbody>
</table>
<h2>Resultados Hematologia</h2>
<table>
<thead><tr><th>Parâmetro</th><th>Resultado</th><th>Unidade</th><th>Ref.</th><th>Obs.</th></tr></thead>
<tbody>
<tr><td>Hemoglobina</td><td></td><td>g/dL</td><td>13.0–17.0</td><td></td></tr>
<tr><td>Hematócrito</td><td></td><td>%</td><td>40–52</td><td></td></tr>
<tr><td>Plaquetas</td><td></td><td>x10^3/µL</td><td>150–450</td><td></td></tr>
</tbody>
</table>
<h2>Observações Técnicas</h2><p></p>
<h2>Conclusão</h2><p></p>
<h2>Anexos</h2><p>Faça upload do PDF do laudo no experimento (Uploads).</p>
""".strip()


# ==============================
# HTTP client eLabFTW
# ==============================
class ELab:
    def __init__(self, base_url: str, api_key: str, timeout=30):
        self.base = base_url.rstrip("/")
        self.h = {
            "Authorization": api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self.timeout = timeout

    def _url(self, path: str) -> str:
        return f"{self.base}/{path.lstrip('/')}"

    def get(self, path, params=None):
        r = requests.get(self._url(path), headers=self.h, params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json() if r.content else {}

    def post(self, path, payload=None):
        data = json.dumps(payload or {})
        r = requests.post(self._url(path), headers=self.h, data=data, timeout=max(self.timeout, 60))
        if r.status_code not in (200, 201):
            try:
                detail = r.json()
            except Exception:
                detail = r.text
            raise RuntimeError(f"POST {path} falhou: {r.status_code} - {detail}")
        return r.json() if r.content else {}

    def patch(self, path, payload=None):
        data = json.dumps(payload or {})
        r = requests.patch(self._url(path), headers=self.h, data=data, timeout=max(self.timeout, 60))
        r.raise_for_status()
        return r.json() if r.content else {}


# ==============================
# MySQL helpers
# ==============================
def db():
    return mysql.connector.connect(**MYSQL_CFG)

def db_init():
    con = db()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            item_id INT NOT NULL,
            created_at DATETIME NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            patient_id INT NOT NULL,
            experiment_id INT NOT NULL,
            status VARCHAR(255) NOT NULL,
            created_at DATETIME NOT NULL,
            last_checked DATETIME NULL,
            FOREIGN KEY (patient_id) REFERENCES patients(id)
                ON UPDATE CASCADE ON DELETE RESTRICT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)
    con.commit()
    cur.close()
    con.close()

def db_add_patient(name: str, item_id: int) -> int:
    con = db(); cur = con.cursor()
    cur.execute(
        "INSERT INTO patients(name, item_id, created_at) VALUES (%s, %s, %s)",
        (name, item_id, datetime.utcnow())
    )
    con.commit()
    pid = cur.lastrowid
    cur.close(); con.close()
    return pid

def db_get_patient(pid: int):
    con = db(); cur = con.cursor(dictionary=True)
    cur.execute("SELECT * FROM patients WHERE id=%s", (pid,))
    row = cur.fetchone()
    cur.close(); con.close()
    return row

def db_add_appointment(patient_id: int, experiment_id: int, status: str) -> int:
    con = db(); cur = con.cursor()
    cur.execute(
        "INSERT INTO appointments(patient_id, experiment_id, status, created_at) VALUES (%s,%s,%s,%s)",
        (patient_id, experiment_id, status, datetime.utcnow())
    )
    con.commit()
    appt_id = cur.lastrowid
    cur.close(); con.close()
    return appt_id

def db_update_status(experiment_id: int, status: str):
    con = db(); cur = con.cursor()
    cur.execute(
        "UPDATE appointments SET status=%s, last_checked=%s WHERE experiment_id=%s",
        (status, datetime.utcnow(), experiment_id)
    )
    con.commit()
    cur.close(); con.close()


# ==============================
# Passo 2: garantir ItemType + Template
# ==============================
def ensure_item_type_patient(api: ELab) -> int:
    data = api.get("items_types")
    entries = data.get("items", data)
    for it in entries:
        if (it.get("title") or "").strip().lower() == ITEM_TYPE_TITLE.lower():
            return it["id"]
    created = api.post("items_types", {
        "title": ITEM_TYPE_TITLE,
        "body": "Tipo para cadastro de Pacientes/Pesquisadores."
    })
    return created["id"]

def ensure_template(api: ELab) -> int:
    data = api.get("experiments/templates")
    entries = data.get("items", data)
    for tpl in entries:
        if (tpl.get("title") or "").strip().lower() == TEMPLATE_TITLE.lower():
            return tpl["id"]
    created = api.post("experiments/templates", {"title": TEMPLATE_TITLE, "body": TEMPLATE_BODY_HTML})
    return created["id"]


# ==============================
# Operações de fluxo
# ==============================
def create_patient_item(api: ELab, items_type_id: int, name: str) -> int:
    created = api.post("items", {"title": name, "items_type_id": items_type_id})
    item_id = created.get("id") or created.get("item_id")
    if not item_id:
        # fallback: tenta pegar por listagem recente
        items = api.get("items?limit=5&order=desc")
        for it in items.get("items", items):
            if (it.get("title") or "").strip() == name:
                item_id = it["id"]
                break
    if not item_id:
        raise RuntimeError("Não consegui obter o id do Item recém-criado.")
    return int(item_id)

def create_experiment_from_template(api: ELab, title: str, body_vars: dict) -> int:
    exp = api.post("experiments", {"title": title})
    exp_id = exp.get("id")
    if not exp_id:
        raise RuntimeError("Falha ao criar experimento.")

    body = TEMPLATE_BODY_HTML
    for k, v in (body_vars or {}).items():
        body = body.replace(f"{{{{{k}}}}}", str(v))
    api.patch(f"experiments/{exp_id}", {"title": title, "body": body})
    return int(exp_id)

def link_experiment_to_item(api: ELab, experiment_id: int, item_id: int):
    try:
        api.post(f"experiments/{experiment_id}/items", {"item_id": item_id})
    except Exception:
        # fallback para instâncias com endpoint alternativo
        api.post(f"experiments/{experiment_id}/items_links", {"item_id": item_id})

def get_experiment_status(api: ELab, experiment_id: int) -> str:
    exp = api.get(f"experiments/{experiment_id}")
    return exp.get("status_name") or exp.get("status_label") or str(exp.get("status", "desconhecido"))


# ==============================
# Menu simples (terminal)
# ==============================
def menu():
    print("\n=== Plataforma Externa (CLI) ===")
    print("1) Inicializar Passo 2 (ItemType + Template)")
    print("2) Cadastrar paciente")
    print("3) Marcar experimento (agendar)")
    print("4) Ver status do experimento")
    print("5) Sair")
    return input("> Escolha: ").strip()

def main():
    # init
    api = ELab(ELAB_URL, ELAB_API_KEY)
    db_init()

    while True:
        op = menu()

        if op == "1":
            try:
                it_id = ensure_item_type_patient(api)
                tpl_id = ensure_template(api)
                print(f"[OK] Item Type '{ITEM_TYPE_TITLE}' id={it_id}")
                print(f"[OK] Template '{TEMPLATE_TITLE}' id={tpl_id}")
            except Exception as e:
                print(f"[ERRO] {e}")

        elif op == "2":
            name = input("Nome do paciente: ").strip()
            if not name:
                print("Nome inválido."); continue
            try:
                it_id = ensure_item_type_patient(api)
                item_id = create_patient_item(api, it_id, name)
                pid = db_add_patient(name, item_id)
                print(f"[OK] Paciente cadastrado (local_id={pid}) → item_id={item_id}")
            except Exception as e:
                print(f"[ERRO] {e}")

        elif op == "3":
            pid_str = input("ID local do paciente: ").strip()
            agendamento_id = input("ID do agendamento: ").strip()
            tipo_amostra = input("Tipo de amostra (ex.: Sangue): ").strip() or "Sangue"
            if not pid_str.isdigit() or not agendamento_id:
                print("Dados inválidos."); continue

            pid = int(pid_str)
            row = db_get_patient(pid)
            if not row:
                print("Paciente não encontrado."); continue

            try:
                _ = ensure_template(api)  # garante existência
                title = f"Análises Paciente {pid} - {datetime.now().date().isoformat()}"
                body_vars = {
                    "agendamento_id": agendamento_id,
                    "item_paciente_id": row["item_id"],
                    "data_coleta": datetime.now().isoformat(timespec="minutes"),
                    "tipo_amostra": tipo_amostra,
                }
                exp_id = create_experiment_from_template(api, title, body_vars)
                link_experiment_to_item(api, exp_id, row["item_id"])
                status = get_experiment_status(api, exp_id)
                appt_id = db_add_appointment(pid, exp_id, status)
                print(f"[OK] Experimento criado (id={exp_id}) e linkado ao paciente (item_id={row['item_id']}).")
                print(f"[OK] Agendamento salvo (id={appt_id}) com status='{status}'.")
            except Exception as e:
                print(f"[ERRO] {e}")

        elif op == "4":
            exp_str = input("ID do experimento: ").strip()
            if not exp_str.isdigit():
                print("ID inválido."); continue
            exp_id = int(exp_str)
            try:
                status = get_experiment_status(api, exp_id)
                db_update_status(exp_id, status)
                print(f"[OK] Status atual: {status}")
            except Exception as e:
                print(f"[ERRO] {e}")

        elif op == "5":
            print("Saindo.")
            sys.exit(0)

        else:
            print("Opção inválida.")


if __name__ == "__main__":
    main()
