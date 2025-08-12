# main.py — Consulta de análises no mock (ou servidor real) via requests
import sys
import requests
import json

# Configuração
ELAB_BASE = "http://127.0.0.1:8000/api/v2"  # FastAPI mock por padrão
ELAB_API_KEY = "3-mock-key-abc"

HEADERS_JSON = {
    "Authorization": ELAB_API_KEY,
    "Accept": "application/json",
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
        print(f"[{e['id']}] {e['title']} — Status: {status_label} — Data: {e['date']}")
    print("=== Fim da lista ===\n")

def view_experiment(exp_id: int):
    r = requests.get(f"{ELAB_BASE}/experiments/{exp_id}", headers=HEADERS_JSON, timeout=10)
    if r.status_code != 200:
        die(f"Erro ao buscar experimento {exp_id}.", r)
    e = r.json()
    print(json.dumps(e, indent=2, ensure_ascii=False))

def main():
    test_key_or_exit()
    list_experiments()
    escolha = input("Digite o ID de um experimento para ver detalhes (ou Enter para sair): ").strip()
    if escolha:
        try:
            view_experiment(int(escolha))
        except ValueError:
            print("ID inválido.")

if __name__ == "__main__":
    main()
