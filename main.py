import json
from datetime import datetime
import requests

# ======= EDITE AQUI =======
ELAB_URL = "https://SEU_ELN/api/v2"     # ex.: https://eln.seudominio.org/api/v2
ELAB_API_KEY = "SUA_CHAVE_API_AQUI"     # crie no seu perfil do eLabFTW
# ==========================

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

HEADERS = {
    "Authorization": ELAB_API_KEY,
    "Accept": "application/json",
    "Content-Type": "application/json",
}
TIMEOUT = 30
PATIENTS = {}  # memória: nome -> item_id

def _url(path: str) -> str:
    return f"{ELAB_URL.rstrip('/')}/{path.lstrip('/')}"

def _req(method: str, path: str, json_body=None, params=None):
    r = requests.request(
        method=method.upper(),
        url=_url(path),
        headers=HEADERS,
        json=json_body,
        params=params,
        timeout=TIMEOUT,
    )
    if r.status_code not in (200, 201, 204):
        # Mostra um erro curto e inteligível
        msg = r.text
        if len(msg) > 500:
            msg = msg[:500] + "...(truncado)"
        raise RuntimeError(f"{method.upper()} {path} -> {r.status_code}: {msg}")
    if r.content:
        try:
            return r.json()
        except Exception:
            return r.text
    return {}

def GET(path, params=None):  return _req("GET", path, params=params)
def POST(path, body=None):   return _req("POST", path, json_body=body or {})
def PATCH(path, body=None):  return _req("PATCH", path, json_body=body or {})

def ensure_item_type_patient() -> int:
    data = GET("items_types")
    entries = data.get("items", data) if isinstance(data, dict) else data
    for it in entries:
        if (it.get("title") or "").strip().lower() == ITEM_TYPE_TITLE.lower():
            return int(it["id"])
    created = POST("items_types", {"title": ITEM_TYPE_TITLE, "body": "Tipo para cadastro de Pacientes."})
    return int(created["id"])

def ensure_template() -> int:
    data = GET("experiments/templates")
    entries = data.get("items", data) if isinstance(data, dict) else data
    for tpl in entries:
        if (tpl.get("title") or "").strip().lower() == TEMPLATE_TITLE.lower():
            return int(tpl["id"])
    created = POST("experiments/templates", {"title": TEMPLATE_TITLE, "body": TEMPLATE_BODY_HTML})
    return int(created["id"])

def register_patient(name: str) -> int:
    if not name.strip():
        raise ValueError("Nome vazio.")
    items_type_id = ensure_item_type_patient()
    created = POST("items", {"title": name.strip(), "items_type_id": items_type_id})
    item_id = created.get("id") or created.get("item_id")
    if not isinstance(item_id, int):
        # fallback simples: tenta achar na listagem recente
        recent = GET("items?limit=10&order=desc")
        recent_list = recent.get("items", recent) if isinstance(recent, dict) else recent
        for it in recent_list:
            if (it.get("title") or "").strip() == name.strip():
                item_id = it.get("id")
                break
    if not isinstance(item_id, int):
        raise RuntimeError("Não consegui obter o item_id recém-criado.")
    PATIENTS[name.strip()] = int(item_id)
    return int(item_id)

def create_experiment(title: str, vars_dict: dict) -> int:
    if not title.strip():
        raise ValueError("Título vazio.")
    exp = POST("experiments", {"title": title.strip()})
    exp_id = exp.get("id")
    if not isinstance(exp_id, int):
        raise RuntimeError("Falha ao criar experimento.")
    body = TEMPLATE_BODY_HTML
    for k, v in (vars_dict or {}).items():
        body = body.replace(f"{{{{{k}}}}}", str(v))
    PATCH(f"experiments/{exp_id}", {"title": title.strip(), "body": body})
    return int(exp_id)

def link_experiment_to_item(exp_id: int, item_id: int):
    try:
        POST(f"experiments/{exp_id}/items", {"item_id": item_id})
    except Exception:
        POST(f"experiments/{exp_id}/items_links", {"item_id": item_id})

def get_status(exp_id: int) -> str:
    exp = GET(f"experiments/{exp_id}")
    return str(exp.get("status_name") or exp.get("status_label") or exp.get("status", "desconhecido"))

def export_pdf(exp_id: int, out_path: str):
    r = requests.get(_url(f"experiments/{exp_id}/export"), headers=HEADERS, params={"format": "pdf"}, timeout=120)
    if r.status_code != 200:
        msg = r.text
        if len(msg) > 500:
            msg = msg[:500] + "...(truncado)"
        raise RuntimeError(f"Export falhou: {r.status_code}: {msg}")
    with open(out_path, "wb") as f:
        f.write(r.content)

def menu():
    print("\n=== Plataforma Externa (CLI simples) ===")
    print("1) Inicializar (ItemType + Template)")
    print("2) Cadastrar paciente (cria Item)")
    print("3) Marcar experimento (cria + linka)")
    print("4) Ver status do experimento")
    print("5) Baixar PDF do experimento")
    print("6) Listar pacientes (memória)")
    print("7) Sair")
    return input("> Escolha: ").strip()

def main():
    # checagem simples das credenciais (falha rápido se inválidas)
    try:
        # tenta algo leve; se falhar, vai apontar credencial/URL
        GET("items_types")
    except Exception as e:
        print(f"[ERRO ao acessar API] Verifique ELAB_URL/ELAB_API_KEY. Detalhes: {e}")
        return

    while True:
        op = menu()

        try:
            if op == "1":
                it_id = ensure_item_type_patient()
                tpl_id = ensure_template()
                print(f"[OK] ItemType '{ITEM_TYPE_TITLE}' id={it_id}")
                print(f"[OK] Template  '{TEMPLATE_TITLE}' id={tpl_id}")

            elif op == "2":
                name = input("Nome do paciente: ").strip()
                item_id = register_patient(name)
                print(f"[OK] Paciente '{name}' → item_id={item_id}")

            elif op == "3":
                modo = input("Você tem o item_id do paciente? (s/n): ").strip().lower()
                if modo == "s":
                    item_id = int(input("item_id: ").strip())
                    nome = input("Nome (só para título): ").strip() or f"Paciente {item_id}"
                else:
                    nome = input("Nome do paciente (cadastrado nesta sessão): ").strip()
                    if nome not in PATIENTS:
                        print("Não achei na memória. Cadastre pelo passo 2 ou informe item_id.")
                        continue
                    item_id = PATIENTS[nome]

                agendamento = input("ID do agendamento: ").strip()
                amostra = input("Tipo de amostra (ex.: Sangue): ").strip() or "Sangue"

                ensure_template()
                titulo = f"Análises {nome} - {datetime.now().date().isoformat()}"
                exp_id = create_experiment(titulo, {
                    "agendamento_id": agendamento,
                    "item_paciente_id": item_id,
                    "data_coleta": datetime.now().isoformat(timespec="minutes"),
                    "tipo_amostra": amostra,
                })
                link_experiment_to_item(exp_id, item_id)
                status = get_status(exp_id)
                print(f"[OK] Experimento {exp_id} criado e linkado. Status: {status}")

            elif op == "4":
                exp_id = int(input("ID do experimento: ").strip())
                print(f"[OK] Status: {get_status(exp_id)}")

            elif op == "5":
                exp_id = int(input("ID do experimento: ").strip())
                saida = input("Arquivo de saída (ex.: laudo.pdf): ").strip() or f"experiment_{exp_id}.pdf"
                export_pdf(exp_id, saida)
                print(f"[OK] PDF salvo em: {saida}")

            elif op == "6":
                if not PATIENTS:
                    print("(vazio)")
                else:
                    for n, iid in PATIENTS.items():
                        print(f" - {n}: item_id={iid}")

            elif op == "7":
                print("Saindo.")
                break

            else:
                print("Opção inválida.")

        except Exception as e:
            print(f"[ERRO] {e}")

if __name__ == "__main__":
    main()

