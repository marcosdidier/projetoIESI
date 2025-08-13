# backend/elab_service.py
# Este módulo contém toda a lógica de negócio para interagir com a API do eLabFTW.

import re
from datetime import datetime
from typing import Any, Dict, Optional

import requests

# =========================
# Constantes de Negócio
# =========================
TIMEOUT = 30  # seg por requisição

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
  <thead>
    <tr>
      <th>Analito</th>
      <th>Resultado</th>
      <th>Unidade</th>
      <th>Ref. (Exemplo Ratos de Lab.)</th>
      <th>Obs.</th>
    </tr>
  </thead>
  <tbody>
    <tr><td>Ureia (BUN)</td><td></td><td>mg/dL</td><td>15 – 21</td><td></td></tr>
    <tr><td>Creatinina</td><td></td><td>mg/dL</td><td>0.2 – 0.8</td><td></td></tr>
    <tr><td>TGO (AST)</td><td></td><td>U/L</td><td>59 – 247</td><td></td></tr>
    <tr><td>TGP (ALT)</td><td></td><td>U/L</td><td>17 – 77</td><td></td></tr>
    <tr><td>TAP (PT)</td><td></td><td>Segundos</td><td>10 – 16</td><td></td></tr>
    <tr><td>TTPA (aPTT)</td><td></td><td>Segundos</td><td>15 – 25</td><td></td></tr>
  </tbody>
</table>

<h2>Resultados Hematologia (Hemograma Completo)</h2>
<table>
  <thead>
    <tr>
      <th>Parâmetro</th>
      <th>Resultado</th>
      <th>Unidade</th>
      <th>Ref. (Exemplo Ratos de Lab.)</th>
      <th>Obs.</th>
    </tr>
  </thead>
  <tbody>
    <tr><td colspan="5" style="background-color:#f2f2f2;"><strong><em>Série Vermelha</em></strong></td></tr>
    <tr><td>Hemácias</td><td></td><td>x10⁶/mm³</td><td>7.0 – 10.0</td><td></td></tr>
    <tr><td>Hemoglobina</td><td></td><td>g/dL</td><td>11.5 – 16.0</td><td></td></tr>
    <tr><td>Hematócrito</td><td></td><td>%</td><td>36 – 48</td><td></td></tr>
    <tr><td>VCM</td><td></td><td>fL</td><td>50 – 65</td><td></td></tr>
    <tr><td>HCM</td><td></td><td>pg</td><td>16 – 21</td><td></td></tr>
    <tr><td>CHCM</td><td></td><td>g/dL</td><td>31 – 35</td><td></td></tr>
    <tr><td colspan="5" style="background-color:#f2f2f2;"><strong><em>Série Branca</em></strong></td></tr>
    <tr><td>Leucócitos</td><td></td><td>/mm³</td><td>3.000 – 12.000</td><td></td></tr>
    <tr><td>Neutrófilos</td><td></td><td>%</td><td>9 – 35</td><td></td></tr>
    <tr><td>Eosinófilos</td><td></td><td>%</td><td>0 – 6</td><td></td></tr>
    <tr><td>Basófilos</td><td></td><td>%</td><td>0 – 1</td><td></td></tr>
    <tr><td>Linfócitos</td><td></td><td>%</td><td>65 – 90</td><td></td></tr>
    <tr><td>Monócitos</td><td></td><td>%</td><td>0 – 7</td><td></td></tr>
    <tr><td colspan="5" style="background-color:#f2f2f2;"><strong><em>Plaquetas</em></strong></td></tr>
    <tr><td>Plaquetas</td><td></td><td>x10³/mm³</td><td>500.000 – 1.300.000</td><td></td></tr>
  </tbody>
</table>

<h2>Observações Técnicas</h2>
<p></p>
<h2>Conclusão</h2>
<p></p>
<h2>Anexos</h2>
<p>Faça upload do PDF do laudo finalizado na aba "Uploads" deste experimento.</p>
""".strip()

# =========================
# Helpers HTTP
# =========================
def _url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"

def _req(base: str, api_key: str, verify_tls: bool, method: str, path: str,
         json_body: Optional[Dict]=None, params: Optional[Dict]=None) -> Any:
    headers = {
        "Authorization": api_key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    r = requests.request(
        method=method.upper(),
        url=_url(base, path),
        headers=headers,
        json=json_body,
        params=params,
        timeout=TIMEOUT,
        verify=verify_tls,
    )
    if r.status_code not in (200, 201, 204):
        msg = r.text if r.text else f"status={r.status_code}"
        if len(msg) > 600:
            msg = msg[:600] + "... (truncado)"
        raise RuntimeError(f"{method.upper()} {path} -> {r.status_code}: {msg}")
    if r.content:
        try:
            return r.json()
        except Exception:
            return r.content
    return {}

def GET(base, key, verify, path, params=None):  return _req(base, key, verify, "GET", path, params=params)
def POST(base, key, verify, path, body=None):   return _req(base, key, verify, "POST", path, json_body=body or {})
def PATCH(base, key, verify, path, body=None):  return _req(base, key, verify, "PATCH", path, json_body=body or {})

def _to_list(data: Any) -> list:
    if isinstance(data, dict):
        for k in ("items", "data", "results"):
            if isinstance(data.get(k), list):
                return data[k]
        return []
    return data if isinstance(data, list) else []

# =========================
# Operações de Negócio
# =========================
def ensure_item_type_patient(base: str, key: str, verify: bool) -> int:
    data = GET(base, key, verify, "items_types")
    entries = _to_list(data)
    for it in entries:
        if (it.get("title") or "").strip().lower() == ITEM_TYPE_TITLE.lower():
            return int(it["id"])
    created = POST(base, key, verify, "items_types",
                   {"title": ITEM_TYPE_TITLE, "body": "Tipo para cadastro de Pacientes/Pesquisadores."})
    return int(created["id"])

def ensure_template(base: str, key: str, verify: bool) -> int:
    data = GET(base, key, verify, "experiments/templates")
    entries = _to_list(data)
    for tpl in entries:
        if (tpl.get("title") or "").strip().lower() == TEMPLATE_TITLE.lower():
            return int(tpl["id"])
    created = POST(base, key, verify, "experiments/templates",
                   {"title": TEMPLATE_TITLE, "body": TEMPLATE_BODY_HTML})
    return int(created["id"])

def register_patient(base: str, key: str, verify: bool, name: str) -> int:
    if not name.strip():
        raise ValueError("Nome do paciente vazio.")
    items_type_id = ensure_item_type_patient(base, key, verify)
    created = POST(base, key, verify, "items", {"title": name.strip(), "items_type_id": items_type_id})
    item_id = created.get("id") or created.get("item_id")
    if not isinstance(item_id, int):
        recent = GET(base, key, verify, "items", params={"limit": 10, "order": "desc"})
        for it in _to_list(recent):
            if (it.get("title") or "").strip() == name.strip():
                item_id = it.get("id")
                break
    if not isinstance(item_id, int):
        raise RuntimeError("Não consegui obter o item_id recém-criado.")
    return int(item_id)

def create_experiment(base: str, key: str, verify: bool, title: str, vars_dict: Dict[str, Any]) -> int:
    if not title.strip():
        raise ValueError("Título do experimento vazio.")

    headers = {
        "Authorization": key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    resp = requests.post(
        _url(base, "experiments"),
        headers=headers,
        json={"title": title.strip()},
        timeout=TIMEOUT,
        verify=verify,
    )
    if resp.status_code not in (200, 201):
        msg = resp.text if resp.text else f"status={resp.status_code}"
        if len(msg) > 600:
            msg = msg[:600] + "... (truncado)"
        raise RuntimeError(f"POST /experiments -> {resp.status_code}: {msg}")

    exp_id: Optional[int] = None
    if resp.content:
        try:
            data = resp.json()
            if isinstance(data, dict) and isinstance(data.get("id"), int):
                exp_id = data["id"]
        except Exception:
            pass
    if exp_id is None:
        loc = resp.headers.get("Location") or resp.headers.get("location")
        if loc:
            m = re.search(r"/experiments/(\d+)", loc)
            if m:
                exp_id = int(m.group(1))
    if exp_id is None:
        recent = GET(base, key, verify, "experiments", params={"limit": 10, "order": "desc"})
        for e in _to_list(recent):
            if (e.get("title") or "").strip() == title.strip() and isinstance(e.get("id"), int):
                exp_id = int(e["id"])
                break
    if exp_id is None:
        short_body = resp.text[:200] if resp.text else ""
        raise RuntimeError(
            f"Não consegui obter o id do experimento recém-criado."
            f"HTTP={resp.status_code}, Location={resp.headers.get('Location')!r}, Body='{short_body}'"
        )

    body = TEMPLATE_BODY_HTML
    for k, v in (vars_dict or {}).items():
        body = body.replace(f"{{{{{k}}}}}", str(v))
    PATCH(base, key, verify, f"experiments/{exp_id}", {"title": title.strip(), "body": body})
    return exp_id

def link_experiment_to_item(base: str, key: str, verify: bool, exp_id: int, item_id: int):
    GET(base, key, verify, f"experiments/{exp_id}")
    GET(base, key, verify, f"items/{item_id}")
    try:
        POST(base, key, verify, f"experiments/{exp_id}/items_links/{item_id}", {})
        return
    except Exception as e1:
        try:
            POST(base, key, verify, f"experiments/{exp_id}/items_links", {"id": item_id})
            return
        except Exception as e2:
            raise RuntimeError
        
def get_status(base: str, key: str, verify: bool, exp_id: int) -> str:
    """Busca um experimento pelo ID e retorna seu status atual."""
    exp = GET(base, key, verify, f"experiments/{exp_id}")
    # Retorna o primeiro campo de status que encontrar, com um fallback
    return str(exp.get("status_name") or exp.get("status_label") or exp.get("status", "desconhecido"))

def export_pdf(base: str, key: str, verify: bool, exp_id: int, *, include_changelog: bool = False) -> bytes:
    """
    Exporta o experimento em PDF pelo endpoint correto, enviando explicitamente
    o parâmetro changelog como 'true' ou 'false'.
    """
    url = _url(base, f"experiments/{exp_id}")
    headers = {
        "Authorization": key,
        "Accept": "application/pdf, application/octet-stream",
    }
    
    params = {
        "format": "pdf",
        "changelog": "true" if include_changelog else "false"
    }

    r = requests.get(url, headers=headers, params=params, timeout=max(60, TIMEOUT), verify=verify)
    
    if r.status_code != 200:
        body = r.text if r.text else f"status={r.status_code}"
        raise RuntimeError(f"GET experiments/{exp_id}?format=pdf -> {r.status_code}: {body}")
    
    return r.content