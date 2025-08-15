# backend/main.py
"""
Ponto de Entrada da API Backend (FastAPI).

Esta aplicação serve como um gateway entre o frontend (Streamlit) e o serviço
externo eLabFTW, além de interagir com um banco de dados local para
armazenamento de metadados.
"""

from fastapi import FastAPI, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
from typing import List
from datetime import datetime
from pydantic import BaseModel

# Importações locais da aplicação
from src.backend.database import (
    get_db, init_database, test_connection, register_experiment,
    register_researcher, get_all_researchers, get_all_experiments
)
from src.backend.models import Researcher
from src.backend.schemas import (
    ResearcherRequest, ElabCredentials, ExperimentRequest,
    ResearcherResponse, ExperimentResponse
)
import src.backend.elab_service as elab_service

class ResultsUpdateRequest(BaseModel):
    results: Dict[str, str]

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
        # Etapa 1: Cria o item no eLab.
        elab_item_id = elab_service.register_researcher_item(creds.url, creds.api_key, True, request.name)
        
        # Etapa 2: Salva no banco de dados local, associando o ID do eLab.
        # A senha "default_password" é um placeholder para uma futura implementação de autenticação.
        local_researcher = register_researcher(db, name=request.name, password="default_password", elab_item_id=elab_item_id)
        if not local_researcher:
            raise HTTPException(status_code=500, detail="Não foi possível salvar o pesquisador no banco de dados local.")

        return local_researcher
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/experimentos", status_code=201, summary="Cria um Novo Experimento")
def create_new_experiment(
    request: ExperimentRequest,
    creds: ElabCredentials = Depends(get_elab_credentials),
    db: Session = Depends(get_db)
):
    """
    Cria uma nova solicitação (experimento), vinculando-a a um pesquisador.
    """
    try:
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
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/experimentos/{experiment_id}/status", summary="Consulta o Status de um Experimento")
def get_experiment_status(experiment_id: int, creds: ElabCredentials = Depends(get_elab_credentials)):
    """Busca e retorna o status atual de um experimento específico no eLabFTW."""
    try:
        status = elab_service.get_status(creds.url, creds.api_key, True, experiment_id)
        return {"status": status}
    except Exception as e:
        if "404" in str(e):
             raise HTTPException(status_code=404, detail=f"Experimento com ID {experiment_id} não encontrado no eLabFTW.")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/experimentos/{experiment_id}/pdf", summary="Exporta um Experimento como PDF")
def get_experiment_pdf(experiment_id: int, include_changelog: bool = False, creds: ElabCredentials = Depends(get_elab_credentials)):
    """Gera e retorna o laudo de um experimento em formato PDF."""
    try:
        pdf_bytes = elab_service.export_pdf(creds.url, creds.api_key, True, experiment_id, include_changelog=include_changelog)
        from fastapi.responses import Response
        # Retorna a resposta com os bytes do PDF e o `media_type` correto.
        return Response(content=pdf_bytes, media_type="application/pdf")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.patch("/experimentos/{experiment_id}/update-results")
def update_experiment_results(
    experiment_id: int,
    request: ResultsUpdateRequest,
    elab_url: str = Header(..., alias="elab-url"),
    elab_api_key: str = Header(..., alias="elab-api-key")
):
    try:
        response = elab_service.update_results(
            elab_url, elab_api_key, True, experiment_id, request.results
        )
        return {"status": "ok", "message": f"Resultados do experimento {experiment_id} atualizados com sucesso."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
