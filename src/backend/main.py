# backend/main.py
from fastapi import FastAPI, HTTPException, Header, Body
from typing import Dict, Any
import elab_service  # Importa o nosso módulo de serviço
from schemas import PatientRequest, ExperimentRequest

app = FastAPI(
    title="LIACLI Backend API",
    description="API que serve como gateway para o eLabFTW.",
    version="1.0.0"
)

# Endpoint para testar a conexão (usado no sidebar do front)
@app.post("/test-connection")
def test_connection(
    elab_url: str = Header(...),
    elab_api_key: str = Header(...)
):
    try:
        elab_service.GET(elab_url, elab_api_key, True, "items_types")
        return {"status": "ok", "message": "Conexão com a API do eLabFTW bem-sucedida."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Endpoint para criar o ItemType e o Template
@app.post("/initialize")
def initialize_elab(
    elab_url: str = Header(...),
    elab_api_key: str = Header(...)
):
    try:
        item_type_id = elab_service.ensure_item_type_patient(elab_url, elab_api_key, True)
        template_id = elab_service.ensure_template(elab_url, elab_api_key, True)
        return {
            "item_type_id": item_type_id,
            "template_id": template_id
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Endpoint para cadastrar paciente
@app.post("/pacientes")
def create_patient(
    request: PatientRequest,
    elab_url: str = Header(...),
    elab_api_key: str = Header(...)
):
    try:
        item_id = elab_service.register_patient(elab_url, elab_api_key, True, request.name)
        return {"name": request.name, "item_id": item_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Endpoint para criar experimento
@app.post("/experimentos")
def create_new_experiment(
    request: ExperimentRequest,
    elab_url: str = Header(...),
    elab_api_key: str = Header(...)
):
    try:
        # Lógica para criar o título e o dicionário de variáveis
        from datetime import datetime
        title = f"[AG:{request.agendamento_id}] Análises {request.display_name} - {datetime.now().date().isoformat()}"
        vars_dict = {
            "agendamento_id": request.agendamento_id,
            "item_paciente_id": request.item_paciente_id,
            "data_coleta": datetime.now().isoformat(timespec="minutes"),
            "tipo_amostra": request.tipo_amostra,
        }
        
        # Cria o experimento e o linka ao item do paciente
        exp_id = elab_service.create_experiment(elab_url, elab_api_key, True, title, vars_dict)
        elab_service.link_experiment_to_item(elab_url, elab_api_key, True, exp_id, request.item_paciente_id)
        
        status = elab_service.get_status(elab_url, elab_api_key, True, exp_id)
        return {"agendamento_id": request.agendamento_id, "experiment_id": exp_id, "status": status}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Endpoint para checar status
@app.get("/experimentos/{experiment_id}/status")
def get_experiment_status(
    experiment_id: int,
    elab_url: str = Header(...),
    elab_api_key: str = Header(...)
):
    try:
        status = elab_service.get_status(elab_url, elab_api_key, True, experiment_id)
        return {"experiment_id": experiment_id, "status": status}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Endpoint para baixar PDF
@app.get("/experimentos/{experiment_id}/pdf")
def get_experiment_pdf(
    experiment_id: int,
    include_changelog: bool = False,
    elab_url: str = Header(...),
    elab_api_key: str = Header(...)
):
    try:
        pdf_bytes = elab_service.export_pdf(elab_url, elab_api_key, True, experiment_id, include_changelog=include_changelog)
        from fastapi.responses import Response
        return Response(content=pdf_bytes, media_type="application/pdf")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))