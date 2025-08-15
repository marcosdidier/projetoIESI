# backend/main.py
"""
Ponto de Entrada da API Backend (FastAPI).

Esta aplicação serve como um gateway entre o frontend (Streamlit) e o serviço
externo eLabFTW, além de interagir com um banco de dados local para
armazenamento de metadados.
"""

from fastapi import FastAPI, Depends, HTTPException, Header, Body
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
from typing import List
from datetime import datetime
from bs4 import BeautifulSoup
import re

# Importações locais da aplicação
from src.backend.database import (
    get_db, init_database, test_connection, register_experiment,
    register_researcher, get_all_researchers, get_all_experiments
)
from src.backend.models import Researcher, Experiment
from src.backend.schemas import (
    ResearcherRequest, ElabCredentials, ExperimentRequest,
    ResearcherResponse, ExperimentResponse
)
import src.backend.elab_service as elab_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gerenciador de ciclo de vida da aplicação FastAPI.
    Executa ações na inicialização e no encerramento.
    """
    print("🚀 Iniciando aplicação e configurando banco de dados...")
    # Garante que o banco e as tabelas existam ao iniciar.
    init_database()
    test_connection()
    yield
    print("🔌 Encerrando aplicação...")

# --- Configuração da Aplicação FastAPI ---
app = FastAPI(
    title="LIACLI Backend API",
    description="API que serve como gateway para o eLabFTW, simplificando operações comuns.",
    version="1.3.0",
    lifespan=lifespan,
)

# --- Dependências (FastAPI) ---

def get_elab_credentials(
    elab_url: str = Header(..., alias="elab-url", description="URL da instância do eLabFTW."),
    elab_api_key: str = Header(..., alias="elab-api-key", description="Chave da API do eLabFTW.")
) -> ElabCredentials:
    """
    Extrai as credenciais do eLab dos cabeçalhos da requisição.
    O FastAPI injeta o resultado desta função nos endpoints que a declaram.
    """
    if not elab_url or not elab_api_key:
        raise HTTPException(
            status_code=400,
            detail="Os cabeçalhos 'elab-url' e 'elab-api-key' são obrigatórios."
        )
    return ElabCredentials(url=elab_url, api_key=elab_api_key)


# --- Endpoints da API ---

@app.post("/test-connection", summary="Testa a Conexão com a API do eLabFTW")
def test_elab_connection(creds: ElabCredentials = Depends(get_elab_credentials)):
    """Verifica se as credenciais fornecidas são válidas para conectar ao eLabFTW."""
    try:
        # Executa uma chamada leve, como listar tipos de item, para validar a conexão.
        elab_service.GET(creds.url, creds.api_key, True, "items_types")
        return {"status": "ok", "message": "Conexão com a API do eLabFTW bem-sucedida."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Falha na conexão com o eLab: {e}")

@app.post("/initialize", summary="Garante Estruturas Essenciais no eLabFTW")
def initialize_elab(creds: ElabCredentials = Depends(get_elab_credentials)):
    """
    Verifica e, se necessário, cria o "Tipo de Item" para "Pesquisador" no eLabFTW.
    Endpoint útil para a configuração inicial do ambiente.
    """
    try:
        item_type_id = elab_service.ensure_item_type_researcher(creds.url, creds.api_key, True)
        return {
            "item_type_id": item_type_id,
            "message": "O Tipo de Item 'Pesquisador' foi verificado/criado com sucesso."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao inicializar estruturas no eLab: {e}")

@app.get("/pesquisadores", response_model=List[ResearcherResponse], summary="Lista todos os Pesquisadores")
def list_researchers(db: Session = Depends(get_db)):
    """Retorna uma lista de todos os pesquisadores do banco de dados local."""
    return get_all_researchers(db)

@app.get("/experimentos", response_model=List[ExperimentResponse], summary="Lista todas as Solicitações")
def list_experiments(db: Session = Depends(get_db)):
    """Retorna uma lista de todos os experimentos (solicitações) do banco local."""
    return get_all_experiments(db)

@app.post("/pesquisadores", response_model=ResearcherResponse, status_code=201, summary="Cadastra um Novo Pesquisador")
def create_researcher(
  request: ResearcherRequest,
  creds: ElabCredentials = Depends(get_elab_credentials),
  db: Session = Depends(get_db)
):
    """
    Cadastra um pesquisador. O processo envolve duas etapas:
    1. Cria um "item" correspondente no eLabFTW para obter um ID.
    2. Salva o pesquisador no banco de dados local com a referência ao ID do eLab.
    """
    try:
        # Verifica se já existe um pesquisador com o mesmo nome (username).
        existing = db.query(Researcher).filter(Researcher.name == request.name).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Nome de usuário '{request.name}' já existe.")

        # Etapa 1: Cria o item no eLab.
        elab_item_id = elab_service.register_researcher_item(creds.url, creds.api_key, True, request.name)
        
        # Etapa 2: Salva no banco de dados local, associando o ID do eLab.
        local_researcher = register_researcher(db, name=request.name, password=request.password, elab_item_id=elab_item_id, role=request.role)
        if not local_researcher:
            raise HTTPException(status_code=500, detail="Não foi possível salvar o pesquisador no banco de dados local.")

        return local_researcher
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/experimentos", status_code=201, summary="Cria um Novo Experimento")
def create_new_experiment(
    request: ExperimentRequest,
    creds: ElabCredentials = Depends(get_elab_credentials),
    db: Session = Depends(get_db),
    researcher_header: int = Header(..., alias="researcher-id")
):
    """
    Cria uma nova solicitação (experimento), vinculando-a a um pesquisador.
    Requer o header 'researcher-id' e só permite pesquisadores com role 'pesquisador'.
    """
    try:
        # Verifica identidade e permissão do solicitante
        requester = db.query(Researcher).filter(Researcher.id == researcher_header).first()
        if not requester:
            raise HTTPException(status_code=401, detail="Pesquisador solicitante não encontrado.")
        if requester.role != "pesquisador":
            raise HTTPException(status_code=403, detail="Apenas usuários com role 'pesquisador' podem criar solicitações.")
        # Confere que o header corresponde ao researcher_id no corpo
        if requester.id != request.researcher_id:
            raise HTTPException(status_code=403, detail="O cabeçalho 'researcher-id' deve corresponder ao researcher_id no corpo da requisição.")

        researcher_obj = db.query(Researcher).filter(Researcher.id == request.researcher_id).first()
        if not researcher_obj:
            raise HTTPException(status_code=404, detail=f"Pesquisador com ID local {request.researcher_id} não encontrado.")

        elab_item_id = researcher_obj.elab_item_id
        # Se o pesquisador local não tiver um ID do eLab associado (caso de dados legados),
        # cria o item no eLab agora e atualiza o registro local.
        if not elab_item_id:
            print(f"INFO: Pesquisador '{researcher_obj.name}' sem ID do eLab. Criando agora.")
            elab_item_id = elab_service.register_researcher_item(creds.url, creds.api_key, True, researcher_obj.name)
            researcher_obj.elab_item_id = elab_item_id
            db.commit()

        # Monta o título e as variáveis para o template do eLab.
        title = f"[AG:{request.agendamento_id}] Análises {request.display_name} - {datetime.now().date().isoformat()}"
        vars_dict = {
            "agendamento_id": request.agendamento_id,
            "data_coleta": datetime.now().isoformat(timespec="minutes"),
            "tipo_amostra": request.tipo_amostra,
        }
        
        # Cria o experimento no eLab e o vincula ao item do pesquisador.
        exp_id = elab_service.create_experiment(creds.url, creds.api_key, True, title, vars_dict)
        elab_service.link_experiment_to_item(creds.url, creds.api_key, True, exp_id, elab_item_id)
        
        # Obtém o status inicial.
        status = elab_service.get_status(creds.url, creds.api_key, True, exp_id)
        
        # Registra o novo experimento no banco de dados local.
        register_experiment(
            db, agendamento_id=request.agendamento_id,
            elab_experiment_id=exp_id, researcher_local_id=request.researcher_id
        )
        
        return {"agendamento_id": request.agendamento_id, "experiment_id": exp_id, "status": status}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/experimentos/{experiment_id}/status", summary="Consulta o Status de um Experimento")
def get_experiment_status(experiment_id: int, creds: ElabCredentials = Depends(get_elab_credentials), db: Session = Depends(get_db), researcher_header: int = Header(..., alias="researcher-id")):
    """Busca e retorna o status atual de um experimento específico no eLabFTW.
    Requer o header 'researcher-id'. Pesquisadores só podem consultar seus próprios experimentos; admins podem consultar qualquer um."""
    try:
        requester = db.query(Researcher).filter(Researcher.id == researcher_header).first()
        if not requester:
            raise HTTPException(status_code=401, detail="Pesquisador solicitante não encontrado.")

        # Se não é admin, verifica propriedade do experimento
        if requester.role != "admin":
            exp = db.query(Experiment).filter(Experiment.elab_experiment_id == experiment_id).first()
            if not exp:
                raise HTTPException(status_code=404, detail=f"Experimento com ID {experiment_id} não encontrado localmente.")
            if exp.researcher_id != requester.id:
                raise HTTPException(status_code=403, detail="Acesso negado: experimento não pertence ao pesquisador autenticado.")

        status = elab_service.get_status(creds.url, creds.api_key, True, experiment_id)
        return {"status": status}
    except HTTPException:
        raise
    except Exception as e:
        if "404" in str(e):
             raise HTTPException(status_code=404, detail=f"Experimento com ID {experiment_id} não encontrado no eLabFTW.")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/experimentos/{experiment_id}/pdf", summary="Exporta um Experimento como PDF")
def get_experiment_pdf(experiment_id: int, include_changelog: bool = False, creds: ElabCredentials = Depends(get_elab_credentials), db: Session = Depends(get_db), researcher_header: int = Header(..., alias="researcher-id")):
    """Gera e retorna o laudo de um experimento em formato PDF.
    Requer o header 'researcher-id'. Pesquisadores só podem exportar seus próprios experimentos; admins podem exportar qualquer um."""
    try:
        requester = db.query(Researcher).filter(Researcher.id == researcher_header).first()
        if not requester:
            raise HTTPException(status_code=401, detail="Pesquisador solicitante não encontrado.")

        if requester.role != "admin":
            exp = db.query(Experiment).filter(Experiment.elab_experiment_id == experiment_id).first()
            if not exp:
                raise HTTPException(status_code=404, detail=f"Experimento com ID {experiment_id} não encontrado localmente.")
            if exp.researcher_id != requester.id:
                raise HTTPException(status_code=403, detail="Acesso negado: experimento não pertence ao pesquisador autenticado.")

        pdf_bytes = elab_service.export_pdf(creds.url, creds.api_key, True, experiment_id, include_changelog=include_changelog)
        from fastapi.responses import Response
        # Retorna a resposta com os bytes do PDF e o `media_type` correto.
        return Response(content=pdf_bytes, media_type="application/pdf")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/login", summary="Autentica um pesquisador pelo nome e senha")
def login_researcher(
    db: Session = Depends(get_db),
    payload: dict = Body(...)
):
    """
    Autentica um pesquisador pelo nome e senha.
    Retorna os dados do pesquisador se autenticado, ou erro 401.
    """
    try:
        print(f"[DEBUG] /login payload: {payload}")
        name = payload.get("name")
        password = payload.get("password")
        if not name or not password:
            raise HTTPException(status_code=400, detail="Nome e senha são obrigatórios.")
        researcher = db.query(Researcher).filter(Researcher.name == name).first()
        if not researcher or researcher.password != password:
            raise HTTPException(status_code=401, detail="Nome ou senha inválidos.")
        # Retorna apenas dados não sensíveis
        return {
            "id": researcher.id,
            "name": researcher.name,
            "elab_item_id": researcher.elab_item_id,
            "created_at": researcher.created_at,
            "role": researcher.role
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] /login exception: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.patch("/experimentos/{experiment_id}/update-results", summary="Atualiza resultados de um experimento (máquinas)")
def update_experiment_results(
    experiment_id: int,
    payload: dict = Body(...),
    creds: ElabCredentials = Depends(get_elab_credentials),
    db: Session = Depends(get_db),
    researcher_header: int = Header(..., alias="researcher-id")
):
    """Permite que máquinas (role 'maquina') atualizem os resultados de um experimento.

    Agora tenta preservar o corpo HTML original: se o experimento contiver uma
    tabela, atualiza as células 'Resultado' correspondentes e grava o HTML
    atualizado no eLab. Caso contrário, mantém o fallback textual anterior.
    """
    try:
        # Valida o solicitante
        requester = db.query(Researcher).filter(Researcher.id == researcher_header).first()
        if not requester:
            raise HTTPException(status_code=401, detail="Solicitante (máquina) não encontrado.")
        if requester.role != "maquina":
            raise HTTPException(status_code=403, detail="Apenas usuários com role 'maquina' podem atualizar resultados.")

        results = payload.get("results") if isinstance(payload, dict) else None
        if not results or not isinstance(results, dict):
            raise HTTPException(status_code=400, detail="Payload inválido. Campo 'results' (dict) é obrigatório.")

        # Busca o corpo atual do experimento no eLab
        exp = elab_service.GET(creds.url, creds.api_key, True, f"experiments/{experiment_id}")
        body = exp.get("body", "") if isinstance(exp, dict) else ""

        updated_body = None
        try:
            if body and "<table" in body.lower():
                from bs4 import BeautifulSoup

                soup = BeautifulSoup(body, "html.parser")
                table = soup.find("table")
                if table:
                    # Build lookup maps: normalized label -> provided value
                    def _norm(s: str) -> str:
                        return re.sub(r"[^a-z0-9]+", "_", (s or "").strip().lower()).strip("_")

                    provided_by_norm = { _norm(k): v for k, v in results.items() }
                    provided_by_label = { k.strip(): v for k, v in results.items() }

                    # Iterate rows and try to update the second <td> (Resultado)
                    for tr in table.find_all("tr"):
                        tds = tr.find_all("td")
                        if not tds or len(tds) < 2:
                            continue
                        raw_param = tds[0].get_text(separator=' ', strip=True)
                        param_norm = _norm(raw_param)

                        new_value = None
                        if raw_param in provided_by_label:
                            new_value = provided_by_label[raw_param]
                        elif param_norm in provided_by_norm:
                            new_value = provided_by_norm[param_norm]
                        else:
                            # try case-insensitive match on keys
                            for k, v in results.items():
                                if k.strip().lower() == raw_param.strip().lower():
                                    new_value = v
                                    break

                        if new_value is not None:
                            # Replace contents of the result cell with new text
                            # Clear children and set new string
                            tds[1].clear()
                            tds[1].append(str(new_value))

                    # After modifications, serialize the entire body preserving other content
                    updated_body = str(soup)
        except Exception as e:
            print(f"Aviso: falha ao tentar atualizar tabela HTML: {e}")

        if not updated_body:
            # Fallback: montar corpo simples em texto 'Chave: valor' por linha
            lines = []
            for k, v in results.items():
                lines.append(f"{k}: {v}")
            updated_body = "\n".join(lines)

        # Grava o corpo atualizado no eLabFTW
        elab_service.PATCH(creds.url, creds.api_key, True, f"experiments/{experiment_id}", {"body": updated_body})

        return {"status": "ok", "message": f"Resultados atualizados para experimento {experiment_id}."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/experimentos/{experiment_id}/set-status", summary="Altera o status de um experimento (máquinas/admin)")
def set_experiment_status(
    experiment_id: int,
    payload: dict = Body(...),
    creds: ElabCredentials = Depends(get_elab_credentials),
    db: Session = Depends(get_db),
    researcher_header: int = Header(..., alias="researcher-id")
):
    """Permite que contas com role 'maquina' ou 'admin' alterem o status de um experimento.

    O payload deve conter o campo 'status' (pode ser string ou número), que será enviado
    diretamente ao eLabFTW via PATCH no recurso do experimento. Não faz validação semântica
    do valor de status (depende da configuração do eLab).
    """
    try:
        requester = db.query(Researcher).filter(Researcher.id == researcher_header).first()
        if not requester:
            raise HTTPException(status_code=401, detail="Solicitante não encontrado.")
        if requester.role not in ("maquina", "admin"):
            raise HTTPException(status_code=403, detail="Apenas contas com role 'maquina' ou 'admin' podem alterar status.")

        status_val = payload.get("status") if isinstance(payload, dict) else None
        if status_val is None:
            raise HTTPException(status_code=400, detail="Campo 'status' é obrigatório no payload.")

        # Envia PATCH simples para o eLabFTW. Dependendo da API do eLab, 'status' pode ser um código
        # numérico ou uma string; o backend encaminha o valor fornecido sem transformação.
        elab_service.PATCH(creds.url, creds.api_key, True, f"experiments/{experiment_id}", {"status": status_val})

        return {"status": "ok", "message": f"Status do experimento {experiment_id} alterado para {status_val}."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/templates", summary="Retorna template e campos para um tipo de amostra")
def get_template_for_tipo(tipo_amostra: str = None, creds: ElabCredentials = Depends(get_elab_credentials)):
    """Busca um template no eLabFTW e retorna sua estrutura de campos.

    Se o template contiver uma tabela HTML no formato de 'Resultado Análise',
    o endpoint tentará extrair as linhas da tabela e devolver uma lista de
    campos estruturados com: key, label, unit, reference, observation, value.
    """
    try:
        tipo_norm = (tipo_amostra or "").strip().lower()
        if tipo_norm == "sangue":
            template_title = "Análise Clínica teste"
        else:
            template_title = elab_service.TEMPLATE_TITLE_TO_FIND

        template_obj = elab_service.get_template_object_by_title(creds.url, creds.api_key, True, template_title)
        body = template_obj.get("body", "") or ""

        # Tentativa 1: detectar tabela HTML e extrair colunas
        fields = []
        if "<table" in body.lower():
            try:
                soup = BeautifulSoup(body, "html.parser")
                table = soup.find("table")
                if table:
                    for tr in table.find_all("tr"):
                        # coleta apenas <td> (pula linhas header com <th>)
                        tds = tr.find_all("td")
                        if not tds or len(tds) < 3:
                            continue

                        # Extraction and sanitization
                        def _clean_text(node_text: str) -> str:
                            if not node_text:
                                return ""
                            # Remove HTML tags if any remained and trim
                            cleaned = re.sub(r"<[^>]+>", "", node_text).strip()
                            # If it still looks like HTML or contains style attributes, return empty
                            if '<' in cleaned or '>' in cleaned or 'style=' in node_text.lower():
                                return ""
                            return cleaned

                        param_raw = tds[0].get_text(separator=' ', strip=True)
                        param = _clean_text(param_raw)
                        result_raw = tds[1].get_text(separator=' ', strip=True) if len(tds) > 1 else ""
                        result = _clean_text(result_raw)
                        unit_raw = tds[2].get_text(separator=' ', strip=True) if len(tds) > 2 else ""
                        unit = _clean_text(unit_raw)
                        reference_raw = tds[3].get_text(separator=' ', strip=True) if len(tds) > 3 else ""
                        reference = _clean_text(reference_raw)
                        observation_raw = tds[4].get_text(separator=' ', strip=True) if len(tds) > 4 else ""
                        observation = _clean_text(observation_raw)

                        # Ignore rows that after cleaning have empty parameter or are header-like
                        low_param = (param or "").strip().lower()
                        if not param or low_param in ("parâmetro", "resultado", "hemograma", "série branca"):
                            continue

                        # Normaliza chave
                        key = re.sub(r"[^a-z0-9]+", "_", param.strip().lower())
                        key = key.strip("_")

                        # Only append if we have a valid key
                        if key:
                            fields.append({
                                "key": key,
                                "label": param,
                                "unit": unit,
                                "reference": reference,
                                "observation": observation,
                                "value": result
                            })
            except Exception as e:
                print(f"Aviso: falha ao parsear tabela HTML do template: {e}")

        # Se não encontrou campos via tabela, tenta extrair placeholders do body ({{campo}})
        if not fields:
            placeholders = re.findall(r"\{\{\s*([^\}]+?)\s*\}\}", body)
            for ph in placeholders:
                key = re.sub(r"[^a-z0-9]+", "_", ph.strip().lower())
                key = key.strip("_")
                fields.append({"key": key, "label": ph.strip(), "unit": "", "reference": "", "observation": "", "value": ""})

        return {"title": template_obj.get("title"), "fields": fields, "body": body}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/experimentos/{experiment_id}/body", summary="Retorna o corpo (body) de um experimento do eLabFTW")
def get_experiment_body(experiment_id: int, creds: ElabCredentials = Depends(get_elab_credentials), db: Session = Depends(get_db), researcher_header: int = Header(..., alias="researcher-id")):
    """Retorna o campo 'body' do experimento no eLabFTW e tenta extrair uma lista
    estruturada de campos a partir de uma tabela HTML presente no corpo.

    Permite que contas com role 'maquina' ou 'admin' leiam o conteúdo do experimento
    para renderizar campos no frontend. Requer cabeçalho 'researcher-id'.
    """
    try:
        requester = db.query(Researcher).filter(Researcher.id == researcher_header).first()
        if not requester:
            raise HTTPException(status_code=401, detail="Solicitante não encontrado.")
        # Permitimos somente máquinas e administradores a carregar o corpo do experimento
        if requester.role not in ("maquina", "admin"):
            raise HTTPException(status_code=403, detail="Apenas contas com role 'maquina' ou 'admin' podem carregar o corpo do experimento.")

        exp = elab_service.GET(creds.url, creds.api_key, True, f"experiments/{experiment_id}")
        body = exp.get("body", "") if isinstance(exp, dict) else ""

        # Tenta parsear tabela HTML no corpo do experimento em campos estruturados
        fields = []
        try:
            if body and "<table" in (body or "").lower():
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(body, "html.parser")
                table = soup.find("table")
                if table:
                    for tr in table.find_all("tr"):
                        tds = tr.find_all("td")
                        if not tds or len(tds) < 2:
                            continue
                        param = tds[0].get_text(strip=True)
                        result = tds[1].get_text(strip=True) if len(tds) > 1 else ""
                        unit = tds[2].get_text(strip=True) if len(tds) > 2 else ""
                        reference = tds[3].get_text(strip=True) if len(tds) > 3 else ""
                        observation = tds[4].get_text(strip=True) if len(tds) > 4 else ""
                        # Extraction and sanitization
                        def _clean_text(node_text: str) -> str:
                            if not node_text:
                                return ""
                            # Remove HTML tags if any remained and trim
                            cleaned = re.sub(r"<[^>]+>", "", node_text).strip()
                            # If it still looks like HTML or contains style attributes, return empty
                            if '<' in cleaned or '>' in cleaned or 'style=' in node_text.lower():
                                return ""
                            return cleaned

                        param_raw = tds[0].get_text(separator=' ', strip=True)
                        param = _clean_text(param_raw)
                        result_raw = tds[1].get_text(separator=' ', strip=True) if len(tds) > 1 else ""
                        result = _clean_text(result_raw)
                        unit_raw = tds[2].get_text(separator=' ', strip=True) if len(tds) > 2 else ""
                        unit = _clean_text(unit_raw)
                        reference_raw = tds[3].get_text(separator=' ', strip=True) if len(tds) > 3 else ""
                        reference = _clean_text(reference_raw)
                        observation_raw = tds[4].get_text(separator=' ', strip=True) if len(tds) > 4 else ""
                        observation = _clean_text(observation_raw)

                        # Ignore rows that after cleaning have empty parameter or are header-like
                        low_param = (param or "").strip().lower()
                        if not param or low_param in ("parâmetro", "resultado", "hemograma", "série branca"):
                            continue

                        # Normaliza chave
                        key = re.sub(r"[^a-z0-9]+", "_", param.strip().lower())
                        key = key.strip("_")

                        fields.append({
                            "key": key,
                            "label": param,
                            "unit": unit,
                            "reference": reference,
                            "observation": observation,
                            "value": result
                        })
        except Exception as e:
            print(f"Aviso: falha ao parsear tabela HTML do corpo do experimento: {e}")

        return {"body": body, "fields": fields}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
