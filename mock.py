# mock.py — Servidor REST (FastAPI) que simula a API do eLabFTW
from fastapi import FastAPI, Request, HTTPException, Response, status
from fastapi.responses import JSONResponse
from datetime import date
from itertools import count

app = FastAPI(title="Mock eLabFTW API", version="0.1.0")

# "Banco" em memória
experiments: dict[int, dict] = {}
_id_gen = count(1)

API_PREFIX = "/api/v2"
REQUIRED_AUTH_PREFIX = "3-"  # A chave deve começar com "3-"

def require_auth(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth or not auth.startswith(REQUIRED_AUTH_PREFIX):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")

@app.get(f"{API_PREFIX}/users/me")
def users_me(request: Request):
    require_auth(request)
    return {
        "id": 1,
        "username": "mockuser",
        "fullname": "Mock API User",
        "email": "mock@example.com",
        "team": {"id": 1, "name": "MockLab"},
    }

@app.post(f"{API_PREFIX}/experiments", status_code=status.HTTP_201_CREATED)
def create_experiment(request: Request):
    require_auth(request)
    exp_id = next(_id_gen)
    experiments[exp_id] = {
        "id": exp_id,
        "title": f"Experiment {exp_id}",
        "date": str(date.today()),
        "body": "",
        "locked": False,
        "status": {"id": 1, "label": "Draft"},
    }
    # Location header com a URL do recurso criado
    host = request.headers.get("host", "127.0.0.1:8000")
    location = f"http://{host}{API_PREFIX}/experiments/{exp_id}"
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=None, headers={"Location": location})

@app.patch(f"{API_PREFIX}/experiments/{{exp_id}}", status_code=status.HTTP_204_NO_CONTENT)
def patch_experiment(exp_id: int, request: Request, payload: dict):
    require_auth(request)
    exp = experiments.get(exp_id)
    if not exp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    for k in ("title", "date", "body"):
        if k in payload:
            exp[k] = payload[k]
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.get(f"{API_PREFIX}/experiments/{{exp_id}}")
def get_experiment(exp_id: int, request: Request):
    require_auth(request)
    exp = experiments.get(exp_id)
    if not exp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    return exp

@app.get(f"{API_PREFIX}/experiments")
def list_all_experiments(request: Request):
    require_auth(request)
    return list(experiments.values())

if __name__ == "__main__":
    import uvicorn
    # Roda em http://127.0.0.1:8000/api/v2
    uvicorn.run(app, host="127.0.0.1", port=8000)
