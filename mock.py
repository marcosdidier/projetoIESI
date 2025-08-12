# mock.py — Servidor REST que simula a API do eLabFTW
from flask import Flask, request, jsonify, make_response
from datetime import date
from itertools import count

app = Flask(__name__)

# "Banco" em memória
experiments = {}
_id_gen = count(1)

API_PREFIX = "/api/v2"
REQUIRED_AUTH_PREFIX = "3-"  # A chave deve começar com "3-"

def require_auth():
    auth = request.headers.get("Authorization", "")
    return bool(auth and auth.startswith(REQUIRED_AUTH_PREFIX))

@app.get(f"{API_PREFIX}/users/me")
def users_me():
    if not require_auth():
        return make_response(jsonify({"error": "unauthorized"}), 401)
    return jsonify({
        "id": 1,
        "username": "mockuser",
        "fullname": "Mock API User",
        "email": "mock@example.com",
        "team": {"id": 1, "name": "MockLab"},
    })

@app.post(f"{API_PREFIX}/experiments")
def create_experiment():
    if not require_auth():
        return make_response(jsonify({"error": "unauthorized"}), 401)
    exp_id = next(_id_gen)
    experiments[exp_id] = {
        "id": exp_id,
        "title": f"Experiment {exp_id}",
        "date": str(date.today()),
        "body": "",
        "locked": False,
        "status": {"id": 1, "label": "Draft"},
    }
    resp = make_response("", 201)
    resp.headers["Location"] = f"{request.host_url.rstrip('/')}{API_PREFIX}/experiments/{exp_id}"
    return resp

@app.patch(f"{API_PREFIX}/experiments/<int:exp_id>")
def patch_experiment(exp_id: int):
    if not require_auth():
        return make_response(jsonify({"error": "unauthorized"}), 401)
    exp = experiments.get(exp_id)
    if not exp:
        return make_response(jsonify({"error": "not found"}), 404)
    data = request.get_json(silent=True) or {}
    for k in ("title", "date", "body"):
        if k in data:
            exp[k] = data[k]
    return "", 204

@app.get(f"{API_PREFIX}/experiments/<int:exp_id>")
def get_experiment(exp_id: int):
    if not require_auth():
        return make_response(jsonify({"error": "unauthorized"}), 401)
    exp = experiments.get(exp_id)
    if not exp:
        return make_response(jsonify({"error": "not found"}), 404)
    return jsonify(exp)

if __name__ == "__main__":
    # Roda em http://127.0.0.1:5000/api/v2
    app.run(host="127.0.0.1", port=5000, debug=True)
