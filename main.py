# main.py — Cliente interativo que chama a API (mock ou real)
import sys
import json
from datetime import date
import requests

# Configuração — altere conforme necessário
ELAB_BASE = "http://127.0.0.1:5000/api/v2"  # Ex.: "https://servidor-eln/api/v2" ou mock local
ELAB_API_KEY = "3-mock-key-abc"             # Ex.: "3-xxxxxxxxxxxxxxxx"

HEADERS_JSON = {
    "Authorization": ELAB_API_KEY,
    "Accept": "application/json",
    "Content-Type": "application/json",
}

def die(msg: str, resp: requests.Response | None = None):
    print(f"❌ {msg}")
    if resp is not None:
        try:
            print("→ Detalhes:", resp.status_code, resp.text[:800])
        except Exception:
            pass
    sys.exit(1)

def test_key_or_exit():
    try:
        r = requests.get(f"{ELAB_BASE}/users/me", headers=HEADERS_JSON, timeout=10)
    except requests.RequestException as e:
        die(f"Falha de conexão com '{ELAB_BASE}': {e}")
    if r.status_code != 200:
        die("Chave API inválida ou sem permissão para /users/me.", r)
    me = r.json()
    print("✅ Conectado. Usuário:", me.get("fullname") or me.get("username") or "desconhecido")
    return me

def post_new_experiment() -> int:
    try:
        r = requests.post(f"{ELAB_BASE}/experiments", headers=HEADERS_JSON, timeout=10)
    except requests.RequestException as e:
        die(f"Erro ao criar experimento (POST /experiments): {e}")
    if r.status_code not in (201, 202):
        die("Não foi possível criar o experimento.", r)
    location = r.headers.get("Location") or r.headers.get("location")
    if not location or "/experiments/" not in location:
        die("Resposta sem header 'Location' com ID do experimento.", r)
    exp_id = int(location.rstrip("/").split("/")[-1])
    return exp_id

def patch_experiment(exp_id: int, title: str, body: str, iso_date: str):
    payload = {"title": title, "body": body, "date": iso_date}
    try:
        r = requests.patch(f"{ELAB_BASE}/experiments/{exp_id}", headers=HEADERS_JSON, json=payload, timeout=10)
    except requests.RequestException as e:
        die(f"Erro ao preencher experimento (PATCH /experiments/{exp_id}): {e}")
    if r.status_code not in (200, 204):
        die("Falha ao atualizar título/data/corpo do experimento.", r)

def get_experiment(exp_id: int) -> dict:
    r = requests.get(f"{ELAB_BASE}/experiments/{exp_id}", headers=HEADERS_JSON, timeout=10)
    if r.status_code != 200:
        die("Falha ao ler o experimento recém-criado.", r)
    return r.json()

def ask(prompt: str, required: bool = True, default: str | None = None) -> str:
    while True:
        val = input(f"{prompt.strip()} " + (f"[{default}] " if default else "")).strip()
        if not val and default is not None:
            return default
        if val or not required:
            return val
        print("  Campo obrigatório.")

def ask_int(prompt: str, min_value: int = 0, max_value: int | None = None, default: int | None = None) -> int:
    while True:
        raw = ask(prompt, required=(default is None), default=str(default) if default is not None else None)
        try:
            x = int(raw)
            if x < min_value:
                print(f"  Valor mínimo: {min_value}."); continue
            if max_value is not None and x > max_value:
                print(f"  Valor máximo: {max_value}."); continue
            return x
        except ValueError:
            print("  Digite um número inteiro válido.")

def build_markdown_form(data: dict) -> str:
    lines = []
    lines.append("# Solicitação de Análise — Amostras\n")
    lines.append("## Solicitante")
    lines.append(f"- **Nome:** {data['solicitante_nome']}")
    if data.get("solicitante_email"):
        lines.append(f"- **E-mail:** {data['solicitante_email']}")
    if data.get("grupo"):
        lines.append(f"- **Grupo/Unidade:** {data['grupo']}")
    lines.append("\n## Detalhes da Solicitação")
    lines.append(f"- **Motivo/Objetivo:** {data['motivo']}")
    lines.append(f"- **Origem das amostras:** {data['origem_amostras']}")
    lines.append(f"- **Urgência:** {data['urgencia']}")
    lines.append(f"- **Consentimento Ético/Termos:** {data['etica']}")
    if data.get("responsavel_tecnico"):
        lines.append(f"- **Responsável técnico indicado:** {data['responsavel_tecnico']}")
    lines.append("\n## Amostras")
    if data["amostras"]:
        lines.append("| # | Identificação | Volume | Data de Coleta | Observações |")
        lines.append("|---|---------------|--------|----------------|-------------|")
        for idx, s in enumerate(data["amostras"], 1):
            lines.append(f"| {idx} | {s['id']} | {s['volume']} | {s['data_coleta']} | {s['obs']} |")
    else:
        lines.append("_Nenhuma amostra informada_")
    lines.append("\n## Observações adicionais")
    lines.append(data.get("observacoes") or "_—_")
    lines.append("\n> Criado automaticamente via API.")
    return "\n".join(lines)

def main():
    print("=== Agendamento de Análise ===")
    print(f"ELAB_BASE = {ELAB_BASE}")
    test_key_or_exit()

    solicitante_nome = ask("Nome do solicitante:")
    solicitante_email = ask("E-mail do solicitante (opcional):", required=False)
    grupo = ask("Grupo/Unidade/Projeto (opcional):", required=False)
    motivo = ask("Motivo/objetivo da análise:")
    origem_amostras = ask("Origem das amostras:")
    n = ask_int("Quantas amostras? ", min_value=0, max_value=200, default=1)

    amostras = []
    for i in range(1, n + 1):
        print(f" - Amostra {i}:")
        s_id = ask("   Identificação/código da amostra:")
        s_vol = ask("   Volume (ex.: 2 mL):", required=False, default="—")
        s_data = ask("   Data de coleta (YYYY-MM-DD):", required=False, default=str(date.today()))
        s_obs = ask("   Observações (opcional):", required=False, default="—")
        amostras.append({"id": s_id, "volume": s_vol, "data_coleta": s_data, "obs": s_obs})

    urgencia = ask("Urgência (Normal/Urgente):", required=False, default="Normal")
    etica = ask("Consentimento/ética aprovado? (Sim/Não/Em análise):", required=False, default="Em análise")
    responsavel_tecnico = ask("Responsável técnico (opcional):", required=False)
    observacoes = ask("Observações adicionais (opcional):", required=False)

    dados = {
        "solicitante_nome": solicitante_nome,
        "solicitante_email": solicitante_email,
        "grupo": grupo,
        "motivo": motivo,
        "origem_amostras": origem_amostras,
        "amostras": amostras,
        "urgencia": urgencia,
        "etica": etica,
        "responsavel_tecnico": responsavel_tecnico,
        "observacoes": observacoes,
    }

    corpo_md = build_markdown_form(dados)
    hoje = str(date.today())
    title = f"[Agendamento] Análise — {origem_amostras} — {solicitante_nome} — {hoje}"

    print("\nCriando experimento...")
    exp_id = post_new_experiment()
    patch_experiment(exp_id, title=title, body=corpo_md, iso_date=hoje)
    exp = get_experiment(exp_id)

    print("\n✅ Experimento criado!")
    print("ID:", exp_id)
    base_web = ELAB_BASE.replace("/api/v2", "")
    print("URL (aprox.):", f"{base_web}/experiments/{exp_id}")
    print("\nResumo do servidor:")
    print(json.dumps({k: exp.get(k) for k in ("id", "title", "date", "locked", "status")}, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
