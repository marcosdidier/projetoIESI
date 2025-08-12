import requests

BASE = "localhost..."
API_KEY = "3-xxxxxxxxxxxxxxxxxxxxxxxxxx"

def testar_api():
    url = f"{BASE}/users/me"
    headers = {
        "Authorization": API_KEY,
        "Accept": "application/json"
    }
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        print("Chave API funcionando!")
        print("Dados retornados:", r.json())
    else:
        print(f"Erro {r.status_code}: {r.text}")

testar_api()
