# backend/elab_service.py (VERSÃO COM O ENDPOINT CORRETO)

import re
from datetime import datetime
from typing import Any, Dict, Optional
import json

import requests

# =========================
# Constantes de Negócio
# =========================
TIMEOUT = 30  # seg por requisição

ITEM_TYPE_TITLE = "Pesquisador"
# [CORREÇÃO] Voltando para o nome correto do template que você quer usar
TEMPLATE_TITLE_TO_FIND = "Análise Clíndsd teste" 
# [CORREÇÃO] Voltando para o ID de fallback correto
FALLBACK_TEMPLATE_ID = 1

# =========================
# Helpers HTTP (Sem alterações)
# =========================
def _url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"

def _req(base: str, api_key: str, verify_tls: bool, method: str, path: str,
         json_body: Optional[Dict]=None, params: Optional[Dict]=None) -> Any:
    headers = {"Authorization": api_key, "Accept": "application/json", "Content-Type": "application/json"}
    r = requests.request(method=method.upper(), url=_url(base, path), headers=headers, json=json_body, params=params, timeout=TIMEOUT, verify=verify_tls)
    if r.status_code not in (200, 201, 204):
        msg = r.text if r.text else f"status={r.status_code}"
        if len(msg) > 600: msg = msg[:600] + "... (truncado)"
        raise RuntimeError(f"{method.upper()} {path} -> {r.status_code}: {msg}")
    if r.content:
        try: return r.json()
        except Exception: return r.content
    return {}

def GET(base, key, verify, path, params=None):  return _req(base, key, verify, "GET", path, params=params)
def POST(base, key, verify, path, body=None):   return _req(base, key, verify, "POST", path, json_body=body or {})
def PATCH(base, key, verify, path, body=None):  return _req(base, key, verify, "PATCH", path, json_body=body or {})

def _to_list(data: Any) -> list:
    if isinstance(data, dict):
        for k in ("items", "data", "results"):
            if isinstance(data.get(k), list): return data[k]
        return []
    return data if isinstance(data, list) else []

# =========================
# Operações de Negócio
# =========================
def get_template_object_by_title(base: str, key: str, verify: bool, title: str) -> Dict[str, Any]:
    try:
        # [CORREÇÃO CRÍTICA] Usando o endpoint correto para listar os templates MESTRES.
        all_templates_data = GET(base, key, verify, "experiments_templates")
        all_templates = _to_list(all_templates_data)

        found_template = None
        fallback_template = None

        for template in all_templates:
            if (template.get("title") or "").strip().lower() == title.strip().lower():
                found_template = template
            
            if str(template.get("id")) == str(FALLBACK_TEMPLATE_ID):
                fallback_template = template

        if found_template:
            return found_template
        
        if fallback_template:
            print(f"AVISO: Template '{title}' não encontrado. Usando fallback com ID {FALLBACK_TEMPLATE_ID}.")
            return fallback_template

        raise RuntimeError(f"Nem o template principal ('{title}') nem o de fallback (ID: {FALLBACK_TEMPLATE_ID}) foram encontrados na lista de templates mestres.")

    except Exception as e:
        raise RuntimeError(f"Falha crítica ao buscar a lista de templates da API: {e}")

def ensure_item_type_researcher(base: str, key: str, verify: bool) -> int:
    data = GET(base, key, verify, "items_types")
    entries = _to_list(data)
    for it in entries:
        if (it.get("title") or "").strip().lower() == ITEM_TYPE_TITLE.lower(): return int(it["id"])
    created = POST(base, key, verify, "items_types", {"title": ITEM_TYPE_TITLE, "body": "Tipo para cadastro de Pesquisadores."})
    return int(created["id"])
def register_researcher(base: str, key: str, verify: bool, name: str) -> int:
    if not name.strip(): raise ValueError("Nome do pesquisador vazio.")
    items_type_id = ensure_item_type_researcher(base, key, verify)
    created = POST(base, key, verify, "items", {"title": name.strip(), "items_type_id": items_type_id})
    item_id = created.get("id") or created.get("item_id")
    if not isinstance(item_id, int):
        recent = GET(base, key, verify, "items", params={"limit": 10, "order": "desc"})
        for it in _to_list(recent):
            if (it.get("title") or "").strip() == name.strip(): item_id = it.get("id"); break
    if not isinstance(item_id, int): raise RuntimeError("Não consegui obter o item_id recém-criado.")
    return int(item_id)
def create_experiment(base: str, key: str, verify: bool, title: str, vars_dict: Dict[str, Any]) -> int:
    if not title.strip(): raise ValueError("Título do experimento vazio.")
    template_object = get_template_object_by_title(base, key, verify, TEMPLATE_TITLE_TO_FIND)
    template_body = template_object.get("body")
    if not template_body:
        template_info = f"'{template_object.get('title')}' (ID: {template_object.get('id')})"
        raise RuntimeError(f"O template {template_info} foi encontrado, mas seu corpo está vazio.")
    headers = { "Authorization": key, "Accept": "application/json", "Content-Type": "application/json" }
    resp = requests.post( _url(base, "experiments"), headers=headers, json={"title": title.strip()}, timeout=TIMEOUT, verify=verify )
    if resp.status_code not in (200, 201):
        msg = resp.text if resp.text else f"status={resp.status_code}"; raise RuntimeError(f"POST /experiments -> {resp.status_code}: {msg}")
    exp_id: Optional[int] = None
    if resp.content:
        try:
            data = resp.json()
            if isinstance(data, dict) and isinstance(data.get("id"), int): exp_id = data["id"]
        except Exception: pass
    if exp_id is None:
        loc = resp.headers.get("Location") or resp.headers.get("location");
        if loc:
            m = re.search(r"/experiments/(\d+)", loc)
            if m: exp_id = int(m.group(1))
    if exp_id is None:
        recent = GET(base, key, verify, "experiments", params={"limit": 10, "order": "desc"})
        for e in _to_list(recent):
            if (e.get("title") or "").strip() == title.strip() and isinstance(e.get("id"), int):
                exp_id = int(e["id"]); break
    if exp_id is None: raise RuntimeError("Não consegui obter o id do experimento recém-criado a partir da resposta POST.")
    body = template_body
    for k, v in (vars_dict or {}).items(): body = body.replace(f"{{{{{k}}}}}", str(v))
    PATCH(base, key, verify, f"experiments/{exp_id}", {"title": title.strip(), "body": body})
    return exp_id
def link_experiment_to_item(base: str, key: str, verify: bool, exp_id: int, item_id: int):
    GET(base, key, verify, f"experiments/{exp_id}"); GET(base, key, verify, f"items/{item_id}")
    try: POST(base, key, verify, f"experiments/{exp_id}/items_links/{item_id}", {}); return
    except Exception as e1:
        try: POST(base, key, verify, f"experiments/{exp_id}/items_links", {"id": item_id}); return
        except Exception as e2: raise RuntimeError
def get_status(base: str, key: str, verify: bool, exp_id: int) -> str:
    exp = GET(base, key, verify, f"experiments/{exp_id}")
    return str(exp.get("status_name") or exp.get("status_label") or exp.get("status", "desconhecido"))
def export_pdf(base: str, key: str, verify: bool, exp_id: int, *, include_changelog: bool = False) -> bytes:
    url = _url(base, f"experiments/{exp_id}")
    headers = { "Authorization": key, "Accept": "application/pdf, application/octet-stream" }
    params = { "format": "pdf", "changelog": "true" if include_changelog else "false" }
    r = requests.get(url, headers=headers, params=params, timeout=max(60, TIMEOUT), verify=verify)
    if r.status_code != 200:
        body = r.text if r.text else f"status={r.status_code}"; raise RuntimeError(f"GET experiments/{exp_id}?format=pdf -> {r.status_code}: {body}")
    return r.content
