import json
from datetime import datetime

import requests

# ==============================
# CONFIGURAÇÕES (edite aqui)
# ==============================
ELAB_URL = "https://SEU_ELN/api/v2"   # ex.: https://eln.exemplo.org/api/v2
ELAB_API_KEY = "SUA_CHAVE_API_AQUI"  # gere no seu usuário do eLabFTW

ITEM_TYPE_TITLE = "Paciente"
TEMPLATE_TITLE  = "Análise Clínica Padrão"

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
# Estado em memória (sem DB)
# ==============================
# Guardamos pares (nome -> item_id) enquanto o programa estiver aberto.
PATIENTS = {}  # {"Naruto Uzumaki": 123}

# ==============================
# Cliente HTTP
# ==============================
def _url(path: str) -> str:
    return f"{ELAB_URL.rstrip('/')}/{path.lstrip('/')}"

HEADERS = {
    "Authorization": ELAB_API_KEY,
    "Accept": "application/json",
    "Content-Type": "application/json",
}

def GET(path, params=None):
    r = requests.get(_url(path), headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json() if r.content else {}

def POST(path, payload=None):
    r = requests.post(_url(path), headers=HEADERS, data=json.dumps(payload or {}), timeout=60)
    if r.status_code not in (200, 201):
        try:
            detail = r.json()
        except Exception:
            detail = r.text
        raise RuntimeError(f"POST {path} falhou: {r.status_code} - {detail}")
    return r.json() if r.content else {}

def PATCH(path, payload=None):
    r = requests.patch(_url(path), headers=HEADERS, data=json.dumps(payload or {}), timeout=60)
    r.raise_for_status()
    return r.json() if r.content else {}

# ==============================
# Passo 2: garantir ItemType + Template
# ==============================
def ensure_item_type_patient() -> int:
    data = GET("items_types")
    entries = data.get("items", data)
    for it in entries:
        if (it.get("title") or "").strip().lower() == ITEM_TYPE_TITLE.lower():
            return it["id"]
    created = POST("items_types", {
        "title": ITEM_TYPE_TITLE,
        "body": "Tipo para cadastro de Pacientes/Pesquisadores."
    })
    return created["id"]

def ensure_template() -> int:
    data = GET("experiments/templates")
    entries = data.get("items", data)
    for tpl in entries:
        if (tpl.get("title") or "").strip().lower() == TEMPLATE_TITLE.lower():
            return tpl["id"]
    created = POST("experiments/templates", {"title": TEMPLATE_TITLE, "body": TEMPLATE_BODY_HTML})
    return created["id"]

# ==============================
# Operações principais
# ==============================
def register_patient(name: str) -> int:
    items_type_id = ensure_item_type_patient()
    created = POST("items", {"title": name, "items_type_id": items_type_id})
    item_id = created.get("id") or created.get("item_id")
    if not item_id:
        # fallback: tenta achar por listagem recente
        items = GET("items?limit=5&order=desc")
        for it in items.get("items", items):
            if (it.get("title") or "").strip() == name:
                item_id = it["id"]
                break
    if not item_id:
        raise RuntimeError("Não foi possível obter o id do Item recém-criado.")
    PATIENTS[name] = int(item_id)
    return int(item_id)

def create_experiment_from_template(title: str, body_vars: dict) -> int:
    exp = POST("experiments", {"title": title})
    exp_id = exp.get("id")
    if not exp_id:
        raise RuntimeError("Falha ao criar experimento.")

    body = TEMPLATE_BODY_HTML
    for k, v in (body_vars or {}).items():
        body = body.replace(f"{{{{{k}}}}}", str(v))
    PATCH(f"experiments/{exp_id}", {"title": title, "body": body})
    return int(exp_id)

def link_experiment_to_item(experiment_id: int, item_id: int):
    try:
        POST(f"experiments/{experiment_id}/items", {"item_id": item_id})
    except Exception:
        # fallback para instâncias com endpoint alternativo
        POST(f"experiments/{experiment_id}/items_links", {"item_id": item_id})

def get_experiment_status(experiment_id: int) -> str:
    exp = GET(f"experiments/{experiment_id}")
    return exp.get("status_name") or exp.get("status_label") or str(exp.get("status", "desconhecido"))

def export_experiment_pdf(experiment_id: int, out_path: str):
    url = _url(f"experiments/{experiment_id}/export")
    r = requests.get(url, headers=HEADERS, params={"format": "pdf"}, timeout=120)
    r.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(r.content)

# ==============================
# UI simples (terminal)
# ==============================
def menu():
    print("\n=== Plataforma Externa (CLI sem DB) ===")
    print("1) Inicializar Passo 2 (ItemType + Template)")
    print("2) Cadastrar paciente (cria Item)")
    print("3) Marcar experimento (cria e linka)")
    print("4) Ver status do experimento")
    print("5) Baixar PDF do experimento")
    print("6) Listar pacientes (memória)")
    print("7) Sair")
    return input("> Escolha: ").strip()

def main():
    while True:
        op = menu()

        if op == "1":
            try:
                it_id = ensure_item_type_patient()
                tpl_id = ensure_template()
                print(f"[OK] Item Type '{ITEM_TYPE_TITLE}' id={it_id}")
                print(f"[OK] Template '{TEMPLATE_TITLE}' id={tpl_id}")
            except Exception as e:
                print(f"[ERRO] {e}")

        elif op == "2":
            name = input("Nome do paciente: ").strip()
            if not name:
                print("Nome inválido."); continue
            try:
                item_id = register_patient(name)
                print(f"[OK] Paciente '{name}' → item_id={item_id}")
            except Exception as e:
                print(f"[ERRO] {e}")

        elif op == "3":
            # Sem DB: você pode escolher por nome (se já cadastrou nesta sessão) ou digitar item_id manualmente.
            mode = input("Você tem o item_id do paciente? (s/n): ").strip().lower()
            if mode == "s":
                try:
                    item_id = int(input("item_id do paciente: ").strip())
                except ValueError:
                    print("item_id inválido."); continue
                nome = input("Nome (apenas para título): ").strip() or f"Paciente {item_id}"
            else:
                nome = input("Nome do paciente (precisa ter sido cadastrado nesta sessão): ").strip()
                if nome not in PATIENTS:
                    print("Paciente não consta na memória. Cadastre ou informe item_id.")
                    continue
                item_id = PATIENTS[nome]

            agendamento_id = input("ID do agendamento: ").strip()
            tipo_amostra   = input("Tipo de amostra (ex.: Sangue): ").strip() or "Sangue"

            if not agendamento_id:
                print("ID do agendamento inválido."); continue

            try:
                ensure_template()
                title = f"Análises {nome} - {datetime.now().date().isoformat()}"
                body_vars = {
                    "agendamento_id": agendamento_id,
                    "item_paciente_id": item_id,
                    "data_coleta": datetime.now().isoformat(timespec="minutes"),
                    "tipo_amostra": tipo_amostra,
                }
                exp_id = create_experiment_from_template(title, body_vars)
                link_experiment_to_item(exp_id, item_id)
                status = get_experiment_status(exp_id)
                print(f"[OK] Experimento criado (id={exp_id}) e linkado ao item_id={item_id}. Status inicial: {status}")
            except Exception as e:
                print(f"[ERRO] {e}")

        elif op == "4":
            exp_str = input("ID do experimento: ").strip()
            if not exp_str.isdigit():
                print("ID inválido."); continue
            try:
                status = get_experiment_status(int(exp_str))
                print(f"[OK] Status: {status}")
            except Exception as e:
                print(f"[ERRO] {e}")

        elif op == "5":
            exp_str = input("ID do experimento: ").strip()
            out     = input("Arquivo de saída (ex.: laudo.pdf): ").strip() or f"experiment_{exp_str}.pdf"
            if not exp_str.isdigit():
                print("ID inválido."); continue
            try:
                export_experiment_pdf(int(exp_str), out)
                print(f"[OK] PDF salvo em: {out}")
            except Exception as e:
                print(f"[ERRO] {e}")

        elif op == "6":
            if not PATIENTS:
                print("(vazio) Cadastre com a opção 2.")
            else:
                print("Pacientes em memória:")
                for name, iid in PATIENTS.items():
                    print(f" - {name}: item_id={iid}")

        elif op == "7":
            print("Saindo.")
            break

        else:
            print("Opção inválida.")

if __name__ == "__main__":
    main()
