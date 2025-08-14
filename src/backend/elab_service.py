# backend/elab_service.py (REFATORADO E COMENTADO)

import re
from datetime import datetime
from typing import Any, Dict, Optional
import json

import requests

# ==============================================================================
# MÓDULO DE SERVIÇO ELAB
# ------------------------------------------------------------------------------
# Este arquivo é o "motor" da aplicação. Ele contém toda a lógica para se
# comunicar com a API do eLabFTW. O resto da aplicação (main.py, app.py)
# utiliza as funções definidas aqui, sem precisar saber os detalhes da API.
# ==============================================================================


# =========================
# Constantes de Negócio
# =========================
TIMEOUT = 30  # Tempo máximo de espera para cada requisição, em segundos

# Define o nome do "Tipo de Item" que será usado para agrupar os pesquisadores.
ITEM_TYPE_TITLE = "Pesquisador"

# Nome do template que o sistema irá procurar no eLabFTW para usar como base.
# IMPORTANTE: Este nome deve corresponder exatamente ao título do template no eLabFTW.
TEMPLATE_TITLE_TO_FIND = "Análise Clínica teste"

# ID de um template padrão que será usado caso o template principal não seja encontrado.
# É uma medida de segurança para evitar que a aplicação pare completamente.
FALLBACK_TEMPLATE_ID = 1


# =========================
# Funções Auxiliares (Helpers)
# =========================

def _url(base: str, path: str) -> str:
    """Monta a URL completa para um endpoint da API."""
    return f"{base.rstrip('/')}/{path.lstrip('/')}"

def _req(base: str, api_key: str, verify_tls: bool, method: str, path: str,
         json_body: Optional[Dict] = None, params: Optional[Dict] = None) -> requests.Response:
    """Função central que executa qualquer requisição HTTP para a API."""
    headers = {
        "Authorization": api_key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    response = requests.request(
        method=method.upper(),
        url=_url(base, path),
        headers=headers,
        json=json_body,
        params=params,
        timeout=TIMEOUT,
        verify=verify_tls,
    )
    # Validação da resposta: se não for um código de sucesso, lança um erro claro.
    if response.status_code not in (200, 201, 204):
        msg = response.text if response.text else f"status={response.status_code}"
        if len(msg) > 600: msg = msg[:600] + "... (truncado)"
        raise RuntimeError(f"{method.upper()} {path} -> {response.status_code}: {msg}")
    return response

# Wrappers para os métodos HTTP mais comuns, que retornam o conteúdo JSON da resposta.
def GET(base, key, verify, path, params=None): return _req(base, key, verify, "GET", path, params=params).json()
def POST(base, key, verify, path, body=None): return _req(base, key, verify, "POST", path, json_body=body or {})
def PATCH(base, key, verify, path, body=None): _req(base, key, verify, "PATCH", path, json_body=body or {}) # PATCH não precisa retornar corpo

def _to_list(data: Any) -> list:
    """Converte a resposta da API (que pode ser um objeto) em uma lista, se possível."""
    if isinstance(data, dict):
        for k in ("items", "data", "results"):
            if isinstance(data.get(k), list): return data[k]
        return []
    return data if isinstance(data, list) else []

def _find_id_from_response(response: requests.Response, base_url: str, api_key: str, verify_tls: bool, title_to_search: str) -> int:
    """
    Função auxiliar para extrair o ID de um recurso recém-criado.
    A API do eLabFTW pode retornar o ID de 3 formas diferentes. Esta função tenta todas.
    """
    # Abordagem 1: O ID está no corpo da resposta JSON.
    if response.content:
        try:
            data = response.json()
            if isinstance(data, dict) and isinstance(data.get("id"), int):
                return data["id"]
        except Exception:
            pass  # Se não for JSON ou não tiver 'id', tenta a próxima abordagem.

    # Abordagem 2: O ID está no cabeçalho 'Location'.
    loc = response.headers.get("Location") or response.headers.get("location")
    if loc:
        # Extrai o número do final da URL (ex: /api/v2/experiments/123)
        m = re.search(r"/(\d+)$", loc)
        if m:
            return int(m.group(1))

    # Abordagem 3 (Último recurso): Buscar nos itens recentes pelo título.
    # Isso é útil caso a API retorne 201 Created sem corpo e sem header 'Location'.
    endpoint = "experiments" # Assumindo que estamos procurando por experimentos
    recent_items = GET(base_url, api_key, verify_tls, endpoint, params={"limit": 5, "order": "desc"})
    for item in _to_list(recent_items):
        if (item.get("title") or "").strip() == title_to_search.strip():
            return int(item["id"])

    # Se nenhuma abordagem funcionou, lança um erro.
    raise RuntimeError("Não foi possível obter o ID do recurso recém-criado a partir da resposta da API.")


# =========================
# Funções de Lógica de Negócio
# =========================

def get_template_object_by_title(base: str, key: str, verify: bool, title: str) -> Dict[str, Any]:
    """
    Busca um template mestre pelo título. Se não encontrar, busca um template de fallback pelo ID.
    Retorna o objeto completo do template (dicionário).
    """
    try:
        # Busca na fonte correta de templates mestres.
        all_templates_data = GET(base, key, verify, "experiments_templates")
        all_templates = _to_list(all_templates_data)

        found_template = None
        fallback_template = None

        for template in all_templates:
            # Procura pelo template principal
            if (template.get("title") or "").strip().lower() == title.strip().lower():
                found_template = template
            # Procura pelo template de fallback (converte para string para garantir a comparação)
            if str(template.get("id")) == str(FALLBACK_TEMPLATE_ID):
                fallback_template = template

        if found_template:
            return found_template
        
        if fallback_template:
            # Imprime um aviso no console do backend se o fallback for usado.
            print(f"AVISO: Template '{title}' não encontrado. Usando fallback com ID {FALLBACK_TEMPLATE_ID}.")
            return fallback_template

        raise RuntimeError(f"Crítico: Nem o template principal ('{title}') nem o de fallback (ID: {FALLBACK_TEMPLATE_ID}) foram encontrados.")
    except Exception as e:
        raise RuntimeError(f"Falha ao buscar a lista de templates da API: {e}")

def ensure_item_type_researcher(base: str, key: str, verify: bool) -> int:
    """Verifica se o tipo de item 'Pesquisador' existe. Se não, cria e retorna o ID."""
    all_types = GET(base, key, verify, "items_types")
    for item_type in _to_list(all_types):
        if (item_type.get("title") or "").strip().lower() == ITEM_TYPE_TITLE.lower():
            return int(item_type["id"])
    
    # Se não encontrou, cria um novo.
    created = POST(base, key, verify, "items_types", {"title": ITEM_TYPE_TITLE, "body": "Tipo para cadastro de Pesquisadores."})
    return _find_id_from_response(created, base, key, verify, ITEM_TYPE_TITLE)

def register_researcher(base: str, key: str, verify: bool, name: str) -> int:
    """Cria um novo item (pesquisador) e retorna seu ID."""
    if not name.strip():
        raise ValueError("O nome do pesquisador não pode ser vazio.")
    
    items_type_id = ensure_item_type_researcher(base, key, verify)
    response = POST(base, key, verify, "items", {"title": name.strip(), "items_type_id": items_type_id})
    return _find_id_from_response(response, base, key, verify, name)

def create_experiment(base: str, key: str, verify: bool, title: str, vars_dict: Dict[str, Any]) -> int:
    """
    Cria um novo experimento. Etapas:
    1. Encontra o template (principal ou fallback).
    2. Cria um experimento vazio com um título.
    3. Pega o ID do novo experimento.
    4. Preenche o corpo do template com as variáveis.
    5. Atualiza o experimento com o corpo preenchido.
    """
    if not title.strip():
        raise ValueError("O título do experimento não pode ser vazio.")

    # Etapa 1: Encontrar o template
    template_object = get_template_object_by_title(base, key, verify, TEMPLATE_TITLE_TO_FIND)
    template_body = template_object.get("body")
    if not template_body:
        raise RuntimeError(f"O template '{template_object.get('title')}' foi encontrado, mas seu corpo está vazio.")

    # Etapa 2: Criar o experimento vazio
    response_obj = _req(base, key, verify, "POST", "experiments", json_body={"title": title.strip()})
    
    # Etapa 3: Pegar o ID
    exp_id = _find_id_from_response(response_obj, base, key, verify, title)

    # Etapa 4: Preencher o corpo
    body = template_body
    for k, v in (vars_dict or {}).items():
        body = body.replace(f"{{{{{k}}}}}", str(v))
    
    # Etapa 5: Atualizar o experimento
    PATCH(base, key, verify, f"experiments/{exp_id}", {"title": title.strip(), "body": body})
    return exp_id

def link_experiment_to_item(base: str, key: str, verify: bool, exp_id: int, item_id: int):
    """Vincula um experimento a um item (pesquisador)."""
    # Tenta o método de link mais comum primeiro.
    try:
        POST(base, key, verify, f"experiments/{exp_id}/items_links/{item_id}", {})
    except Exception:
        # Se falhar, tenta um método alternativo.
        POST(base, key, verify, f"experiments/{exp_id}/items_links", {"id": item_id})

def get_status(base: str, key: str, verify: bool, exp_id: int) -> str:
    """Busca o status de um experimento pelo seu ID."""
    exp = GET(base, key, verify, f"experiments/{exp_id}")
    return str(exp.get("status_name") or exp.get("status_label") or exp.get("status", "desconhecido"))

def export_pdf(base: str, key: str, verify: bool, exp_id: int, *, include_changelog: bool = False) -> bytes:
    """Exporta um experimento como PDF, retornando os bytes do arquivo."""
    response_obj = _req(base, key, verify, "GET", f"experiments/{exp_id}", params={"format": "pdf", "changelog": "true" if include_changelog else "false"})
    return response_obj.content
