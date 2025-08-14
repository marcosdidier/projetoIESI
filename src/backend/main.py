# backend/main.py 

from fastapi import FastAPI, Depends, HTTPException, Header, Body
from typing import Dict, Any
from pydantic import BaseModel
from datetime import datetime
from src.backend.database import get_db, init_database, test_connection
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
from src.backend.schemas import ResearcherRequest, ElabCredentials, ExperimentRequest
import src.backend.elab_service as elab_service # Nosso módulo que conversa com a API do eLabFTW

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Iniciando aplicação...")

    init_database()
    test_connection()

    yield

    print("Encerrando aplicação...")
      
# --- Dependências (FastAPI) ---
# Funções que o FastAPI pode injetar automaticamente nos endpoints.

def get_elab_credentials(
    elab_url: str = Header(..., description="URL da instância do eLabFTW."),
    elab_api_key: str = Header(..., description="Chave da API do eLabFTW com permissão de escrita.")
) -> ElabCredentials:
    """
    Extrai as credenciais dos cabeçalhos da requisição e as retorna em um objeto.
    Isso evita repetir 'elab_url' e 'elab_api_key' em todas as funções de endpoint.
    """
    if not elab_url or not elab_api_key:
        raise HTTPException(status_code=400, detail="Os cabeçalhos 'elab-url' e 'elab-api-key' são obrigatórios.")
    return ElabCredentials(url=elab_url, api_key=elab_api_key)


# --- Configuração da Aplicação FastAPI ---
app = FastAPI(
    title="LIACLI Backend API",
    description="API que serve como um gateway inteligente para o eLabFTW, simplificando operações comuns.",
    version="1.1.0", # Versão atualizada para refletir a refatoração
    lifespan=lifespan
)

# Endpoint para testar a conexão (usado no sidebar do front)
@app.post("/test-connection", summary="Testa a Conexão com a API do eLabFTW")
def test_elab_connection(
    creds: ElabCredentials = Depends(get_elab_credentials),
    elab_url: str = Header(...),
    elab_api_key: str = Header(...)
):
    try:
        elab_service.GET(creds.url, creds.api_key, True, "items_types")
        return {"status": "ok", "message": "Conexão com a API do eLabFTW bem-sucedida."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/initialize", summary="Garante Estruturas Essenciais no eLabFTW")
def initialize_elab(creds: ElabCredentials = Depends(get_elab_credentials)):
    """Garante que o 'Tipo de Item' para Pesquisador existe no eLabFTW."""
    try:
        item_type_id = elab_service.ensure_item_type_researcher(creds.url, creds.api_key, True)
        return {
            "item_type_id": item_type_id,
            "message": "O Tipo de Item 'Pesquisador' foi verificado com sucesso."
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/pesquisadores", summary="Cadastra um Novo Pesquisador")
def create_researcher(
  request: ResearcherRequest, 
  creds: ElabCredentials = Depends(get_elab_credentials),
  elab_url: str = Header(...),
  elab_api_key: str = Header(...),
  db: Session = Depends(get_db)
):
    try:
        item_id = elab_service.register_researcher(creds.url, creds.api_key, True, request.name)
        return {"name": request.name, "item_id": item_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/experimentos", summary="Cria um Novo Experimento")
def create_new_experiment(
    request: ExperimentRequest,
    creds: ElabCredentials = Depends(get_elab_credentials),
    elab_url: str = Header(...),
    elab_api_key: str = Header(...),
    db: Session = Depends(get_db)
):
    try:
        # Monta o título do experimento de forma padronizada
        title = f"[AG:{request.agendamento_id}] Análises {request.display_name} - {datetime.now().date().isoformat()}"
        
        # Agrupa as variáveis que serão substituídas no corpo do template
        vars_dict = {
            "agendamento_id": request.agendamento_id,
            "item_pesquisador_id": request.item_pesquisador_id,
            "data_coleta": datetime.now().isoformat(timespec="minutes"),
            "tipo_amostra": request.tipo_amostra,
        }
        
        # Orquestra as chamadas de serviço
        exp_id = elab_service.create_experiment(creds.url, creds.api_key, True, title, vars_dict)
        elab_service.link_experiment_to_item(creds.url, creds.api_key, True, exp_id, request.item_pesquisador_id)
        status = elab_service.get_status(creds.url, creds.api_key, True, exp_id)
        
        return {"agendamento_id": request.agendamento_id, "experiment_id": exp_id, "status": status}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/experimentos/{experiment_id}/status", summary="Consulta o Status de um Experimento")
def get_experiment_status(experiment_id: int, creds: ElabCredentials = Depends(get_elab_credentials)):
    """Obtém o status atual (ex: 'Em Andamento', 'Concluída') de um experimento."""
    try:
        status = elab_service.get_status(creds.url, creds.api_key, True, experiment_id)
        return {"experiment_id": experiment_id, "status": status}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/experimentos/{experiment_id}/pdf", summary="Exporta um Experimento como PDF")
def get_experiment_pdf(experiment_id: int, include_changelog: bool = False, creds: ElabCredentials = Depends(get_elab_credentials)):
    """Gera e retorna o laudo de um experimento em formato PDF."""
    try:
        pdf_bytes = elab_service.export_pdf(creds.url, creds.api_key, True, experiment_id, include_changelog=include_changelog)
        from fastapi.responses import Response
        return Response(content=pdf_bytes, media_type="application/pdf")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
