# backend/elab_service.py
"""
Módulo de Serviço para Interação com a API do eLabFTW.

Este arquivo centraliza toda a lógica de comunicação com a API do eLabFTW,
abstraindo os detalhes das requisições HTTP. As outras partes do backend
(como main.py) devem utilizar as funções deste módulo para realizar
operações no eLab, garantindo um ponto único de manutenção e controle.
"""

import re
from typing import Any, Dict, Optional
import requests

# --- Constantes de Configuração ---

# Tempo máximo de espera (em segundos) para as requisições à API.
TIMEOUT = 30

# Título do "Tipo de Item" no eLabFTW que será usado para categorizar os pesquisadores.
# Este tipo será criado caso não exista.
ITEM_TYPE_TITLE = "Pesquisador"

# Título do template de experimento que o sistema buscará no eLabFTW.
# É crucial que este nome corresponda exatamente ao título do template mestre no eLab.
TEMPLATE_TITLE_TO_FIND = "Análise Clínica teste"

# ID de um template de segurança (fallback). Caso o template principal não seja
# encontrado, este será utilizado para evitar a interrupção total do serviço.
FALLBACK_TEMPLATE_ID = 1


# --- Funções Auxiliares de Requisição ---

def _url(base: str, path: str) -> str:
    """Constrói a URL completa para um endpoint da API, tratando barras."""
    return f"{base.rstrip('/')}/{path.lstrip('/')}"

def _req(
    base: str, api_key: str, verify_tls: bool, method: str,
    path: str, json_body: Optional[Dict] = None, params: Optional[Dict] = None
) -> requests.Response:
    """
    Função central para executar requisições HTTP para a API do eLabFTW.

    Args:
        base: URL base da instância do eLabFTW.
        api_key: Chave de autorização da API.
        verify_tls: Booleano para verificar (ou não) o certificado TLS/SSL.
        method: Método HTTP (GET, POST, PATCH, etc.).
        path: Caminho do endpoint (ex: '/api/v2/experiments').
        json_body: Corpo da requisição em formato de dicionário.
        params: Parâmetros de query da URL.

    Returns:
        O objeto de resposta da requisição.

    Raises:
        RuntimeError: Se a resposta da API indicar um erro (status code não for 2xx).
    """
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

    # Lança uma exceção com detalhes se a requisição falhar.
    if response.status_code not in (200, 201, 204):
        error_msg = response.text or f"status={response.status_code}"
        if len(error_msg) > 600:
            error_msg = error_msg[:600] + "... (truncado)"
        raise RuntimeError(f"{method.upper()} {path} -> {response.status_code}: {error_msg}")

    return response

# Funções "wrapper" para os métodos HTTP mais comuns, simplificando as chamadas.
def GET(base, key, verify, path, params=None) -> Any:
    """Executa uma requisição GET e retorna a resposta JSON decodificada."""
    return _req(base, key, verify, "GET", path, params=params).json()

def POST(base, key, verify, path, body=None) -> requests.Response:
    """Executa uma requisição POST e retorna o objeto de resposta completo."""
    return _req(base, key, verify, "POST", path, json_body=body or {})

def PATCH(base, key, verify, path, body=None) -> None:
    """Executa uma requisição PATCH. Não retorna conteúdo."""
    _req(base, key, verify, "PATCH", path, json_body=body or {})

def _to_list(data: Any) -> list:
    """
    Normaliza a resposta da API para sempre retornar uma lista.
    APIs paginadas frequentemente retornam um dicionário com uma chave como 'items' ou 'data'.
    """
    if isinstance(data, dict):
        # Chaves comuns em APIs para listas de resultados.
        for key in ("items", "data", "results"):
            if isinstance(data.get(key), list):
                return data[key]
        return []
    return data if isinstance(data, list) else []

def _find_id_from_response(response: requests.Response, base_url: str, api_key: str, verify_tls: bool, title_to_search: str) -> int:
    """
    Extrai o ID de um recurso recém-criado a partir da resposta da API.

    A API do eLabFTW pode retornar o ID de diferentes formas. Esta função tenta, em ordem:
    1. No corpo da resposta JSON (campo 'id').
    2. No cabeçalho 'Location' da resposta.
    3. Como último recurso, buscando nos itens recém-criados pelo título.
    """
    # Tentativa 1: ID no corpo da resposta.
    if response.content:
        try:
            data = response.json()
            if isinstance(data, dict) and isinstance(data.get("id"), int):
                return data["id"]
        except requests.exceptions.JSONDecodeError:
            pass  # Se não for JSON, prossegue para a próxima tentativa.

    # Tentativa 2: ID no cabeçalho 'Location'.
    location_header = response.headers.get("Location") or response.headers.get("location")
    if location_header:
        match = re.search(r"/(\d+)$", location_header)
        if match:
            return int(match.group(1))

    # Tentativa 3: Buscar nos itens recentes pelo título (fallback).
    # Útil se a API retorna 201 Created sem corpo e sem header 'Location'.
    try:
        recent_items = GET(base_url, api_key, verify_tls, "experiments", params={"limit": 5, "order": "desc"})
        for item in _to_list(recent_items):
            if (item.get("title") or "").strip() == title_to_search.strip():
                return int(item["id"])
    except Exception as e:
        # Se a busca falhar, não impede o erro final de ser lançado.
        print(f"Alerta: Falha ao tentar buscar ID por título: {e}")

    raise RuntimeError("Não foi possível extrair o ID do recurso criado da resposta da API.")


# --- Lógica de Negócio Específica do eLabFTW ---

def get_template_object_by_title(base: str, key: str, verify: bool, title: str) -> Dict[str, Any]:
    """
    Busca um template mestre pelo título.

    Se o template principal não for encontrado, tenta carregar um template de fallback
    pelo ID definido em `FALLBACK_TEMPLATE_ID`.

    Returns:
        O objeto completo (dicionário) do template encontrado.

    Raises:
        RuntimeError: Se nem o template principal nem o de fallback forem encontrados.
    """
    try:
        all_templates_data = GET(base, key, verify, "experiments_templates")
        all_templates = _to_list(all_templates_data)

        found_template = None
        fallback_template = None

        for template in all_templates:
            # Compara o título principal (case-insensitive).
            if (template.get("title") or "").strip().lower() == title.strip().lower():
                found_template = template
            # Procura pelo template de fallback para tê-lo como garantia.
            if str(template.get("id")) == str(FALLBACK_TEMPLATE_ID):
                fallback_template = template

        if found_template:
            return found_template
        
        if fallback_template:
            print(f"AVISO: Template '{title}' não encontrado. Usando fallback ID {FALLBACK_TEMPLATE_ID}.")
            return fallback_template

        raise RuntimeError(f"Crítico: O template '{title}' e o de fallback (ID: {FALLBACK_TEMPLATE_ID}) não foram encontrados.")
    except Exception as e:
        raise RuntimeError(f"Falha ao buscar a lista de templates da API: {e}")

def ensure_item_type_researcher(base: str, key: str, verify: bool) -> int:
    """
    Garante que o tipo de item 'Pesquisador' exista no eLabFTW.

    Se não existir, cria o tipo e retorna seu ID. Caso contrário, apenas retorna o ID existente.
    Isso torna a aplicação autoconfigurável na primeira execução.
    """
    all_types = GET(base, key, verify, "items_types")
    for item_type in _to_list(all_types):
        if (item_type.get("title") or "").strip().lower() == ITEM_TYPE_TITLE.lower():
            return int(item_type["id"])
    
    # Se o loop terminar sem encontrar, cria o novo tipo.
    print(f"Criando tipo de item '{ITEM_TYPE_TITLE}' no eLabFTW...")
    response = POST(base, key, verify, "items_types", {"title": ITEM_TYPE_TITLE, "body": "Tipo para cadastro de Pesquisadores do LIACLI."})
    return _find_id_from_response(response, base, key, verify, ITEM_TYPE_TITLE)

def register_researcher_item(base: str, key: str, verify: bool, name: str) -> int:
    """
    Cria um novo 'item' do tipo 'Pesquisador' no eLabFTW.

    Args:
        name: O nome completo do pesquisador.

    Returns:
        O ID do item recém-criado no eLabFTW.
    """
    if not name.strip():
        raise ValueError("O nome do pesquisador não pode ser vazio.")
    
    # Garante que a categoria "Pesquisador" existe antes de criar o item.
    items_type_id = ensure_item_type_researcher(base, key, verify)
    
    # Cria o item no eLab.
    response = POST(base, key, verify, "items", {"title": name.strip(), "items_type_id": items_type_id})
    return _find_id_from_response(response, base, key, verify, name)

def create_experiment(base: str, key: str, verify: bool, title: str, vars_dict: Dict[str, Any]) -> int:
    """
    Cria um novo experimento no eLabFTW a partir de um template.

    O processo envolve:
    1. Encontrar o ID do template pelo título.
    2. Criar um experimento vazio para obter um ID.
    3. Preencher as variáveis do corpo do template (ex: `{{data_coleta}}`).
    4. Atualizar (PATCH) o experimento com o corpo preenchido.

    Returns:
        O ID do experimento recém-criado.
    """
    if not title.strip():
        raise ValueError("O título do experimento não pode ser vazio.")

    # Determine o template a usar com base na categoria de amostra fornecida.
    tipo_amostra = (vars_dict or {}).get("tipo_amostra", "")
    tipo_norm = (tipo_amostra or "").strip().lower()
    if tipo_norm == "sangue":
        template_to_find = "Análise Clínica teste"
    else:
        template_to_find = TEMPLATE_TITLE_TO_FIND

    # 1. Encontrar o template.
    print(f"[DEBUG] Selected template for tipo_amostra='{tipo_amostra}': '{template_to_find}'")
    template_object = get_template_object_by_title(base, key, verify, template_to_find)
    template_body = template_object.get("body")
    if not template_body:
        raise RuntimeError(f"O template '{template_object.get('title')}' está com o corpo vazio.")

    # 2. Criar o experimento vazio para reservar um ID.
    response_obj = POST(base, key, verify, "experiments", {"title": title.strip()})
    exp_id = _find_id_from_response(response_obj, base, key, verify, title)

    # 3. Substituir as variáveis no corpo do template.
    body = template_body
    for placeholder, value in (vars_dict or {}).items():
        body = body.replace(f"{{{{{placeholder}}}}}", str(value))
    
    # 4. Atualizar o experimento com o conteúdo.
    PATCH(base, key, verify, f"experiments/{exp_id}", {"body": body})
    return exp_id

def link_experiment_to_item(base: str, key: str, verify: bool, exp_id: int, item_id: int):
    """Vincula um experimento a um item (neste caso, um pesquisador)."""
    if not all([isinstance(exp_id, int), isinstance(item_id, int)]):
        raise TypeError("IDs do experimento e do item devem ser inteiros.")
    
    # A API do eLab pode ter variações no endpoint de vínculo.
    # Tenta o método mais comum primeiro.
    try:
        POST(base, key, verify, f"experiments/{exp_id}/items_links/{item_id}", {})
    except Exception as e:
        # Se falhar, tenta um método alternativo que algumas versões da API usam.
        print(f"Alerta: O link direto falhou ({e}). Tentando método alternativo.")
        POST(base, key, verify, f"experiments/{exp_id}/items_links", {"id": item_id})

def get_status(base: str, key: str, verify: bool, exp_id: int) -> str:
    """Busca o status atual de um experimento pelo seu ID."""
    exp = GET(base, key, verify, f"experiments/{exp_id}")
    # Retorna o status, tentando diferentes chaves que a API pode usar.
    return str(exp.get("status_name") or exp.get("status_label") or exp.get("status", "desconhecido"))

def export_pdf(base: str, key: str, verify: bool, exp_id: int, *, include_changelog: bool = False) -> bytes:
    """
    Exporta um experimento como um arquivo PDF.

    Args:
        exp_id: O ID do experimento a ser exportado.
        include_changelog: Se True, o histórico de alterações será incluído no PDF.

    Returns:
        Os bytes brutos do arquivo PDF gerado.
    """
    # A exportação é feita chamando o endpoint do experimento com o parâmetro 'format=pdf'.
    params = {"format": "pdf"}
    if include_changelog:
        params["changelog"] = "true"
        
    response_obj = _req(base, key, verify, "GET", f"experiments/{exp_id}", params=params)
    return response_obj.content
