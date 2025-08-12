# main.py — Cliente CLI para criar, listar, ver, atualizar e "travar" (lock) experimentos
import argparse
import json
from datetime import date
from pathlib import Path
import requests

ELAB_BASE = "http://127.0.0.1:8000/api/v2"  # Mock FastAPI por padrão
ELAB_API_KEY = "3-mock-key-abc"

HEADERS_JSON = {
    "Authorization": ELAB_API_KEY,
    "Accept": "application/json",
    "Content-Type": "application/json",
}

def die(msg, resp=None):
    print(f"❌ {msg}")
    if resp is not None:
        try:
            print("→ Detalhes:", resp.status_code, resp.text[:800])
        except Exception:
            pass
    raise SystemExit(1)

def test_key_or_exit():
    try:
        r = requests.get(f"{ELAB_BASE}/users/me", headers=HEADERS_JSON, timeout=10)
    except requests.RequestException as e:
        die(f"Falha de conexão: {e}")
    if r.status_code != 200:
        die("Chave API inválida ou sem permissão.", r)
    me = r.json()
    print(f"✅ Conectado como: {me.get('fullname') or me.get('username')}")
    return me

def list_experiments():
    r = requests.get(f"{ELAB_BASE}/experiments", headers=HEADERS_JSON, timeout=10)
    if r.status_code != 200:
        die("Erro ao listar experimentos.", r)
    exps = r.json()
    if not exps:
        print("📭 Nenhum experimento encontrado.")
        return
    print("\n=== Experimentos ===")
    for e in exps:
        status_label = e.get("status", {}).get("label", "-")
        print(f"[{e['id']}] {e['title']} — Status: {status_label} — Data: {e['date']} — Locked: {e.get('locked')}")
    print("=== Fim da lista ===\n")

def view_experiment(exp_id: int):
    r = requests.get(f"{ELAB_BASE}/experiments/{exp_id}", headers=HEADERS_JSON, timeout=10)
    if r.status_code != 200:
        die(f"Erro ao buscar experimento {exp_id}.", r)
    e = r.json()
    print(json.dumps(e, indent=2, ensure_ascii=False))

def post_new_experiment() -> int:
    r = requests.post(f"{ELAB_BASE}/experiments", headers=HEADERS_JSON, timeout=10)
    if r.status_code not in (201, 202):
        die("Não foi possível criar o experimento.", r)
    location = r.headers.get("Location") or r.headers.get("location")
    if not location or "/experiments/" not in location:
        die("Resposta sem header 'Location' com ID do experimento.", r)
    return int(location.rstrip("/").split("/")[-1])

def patch_experiment(exp_id: int, payload: dict):
    r = requests.patch(f"{ELAB_BASE}/experiments/{exp_id}", headers=HEADERS_JSON, json=payload, timeout=10)
    if r.status_code not in (200, 204):
        die("Falha ao atualizar experimento.", r)

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

# --------- Subcomandos ---------

def cmd_create(args):
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
    body_md = build_markdown_form(dados)
    title = f"[Agendamento] Análise — {origem_amostras} — {solicitante_nome} — {str(date.today())}"

    exp_id = post_new_experiment()
    patch_experiment(exp_id, {"title": title, "body": body_md, "date": str(date.today())})
    print(f"✅ Experimento criado. ID: {exp_id}")
    print(f"URL (aprox.): {ELAB_BASE.replace('/api/v2','')}/experiments/{exp_id}")

def cmd_list(args):
    test_key_or_exit()
    list_experiments()

def cmd_view(args):
    test_key_or_exit()
    view_experiment(args.id)

def cmd_update(args):
    test_key_or_exit()
    payload = {}
    if args.title:
        payload["title"] = args.title
    if args.date:
        payload["date"] = args.date
    if args.status:
        payload["status"] = {"label": args.status}
    if args.body:
        payload["body"] = args.body
    if args.body_file:
        p = Path(args.body_file)
        if not p.exists():
            die(f"Arquivo não encontrado: {p}")
        payload["body"] = p.read_text(encoding="utf-8")
    if not payload:
        die("Nenhum campo para atualizar. Informe --title/--date/--status/--body/--body-file.")
    patch_experiment(args.id, payload)
    print("✅ Atualizado.")

def cmd_lock(args):
    test_key_or_exit()
    patch_experiment(args.id, {"locked": True})
    print("✅ Registro marcado como locked=True.")

def build_parser():
    p = argparse.ArgumentParser(description="CLI de integração com API estilo eLabFTW (mock ou real).")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("create", help="Criar experimento (interativo).")
    sp.set_defaults(func=cmd_create)

    sp = sub.add_parser("list", help="Listar experimentos.")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("view", help="Ver detalhes de um experimento.")
    sp.add_argument("--id", type=int, required=True, help="ID do experimento.")
    sp.set_defaults(func=cmd_view)

    sp = sub.add_parser("update", help="Atualizar campos do experimento.")
    sp.add_argument("--id", type=int, required=True)
    sp.add_argument("--title")
    sp.add_argument("--date", help="YYYY-MM-DD")
    sp.add_argument("--status", help="Rótulo do status, ex.: Draft/Completed.")
    sp.add_argument("--body", help="Texto do corpo (Markdown).")
    sp.add_argument("--body-file", help="Arquivo com o corpo (Markdown).")
    sp.set_defaults(func=cmd_update)

    sp = sub.add_parser("lock", help="Marcar experimento como locked=True.")
    sp.add_argument("--id", type=int, required=True)
    sp.set_defaults(func=cmd_lock)

    return p

def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
