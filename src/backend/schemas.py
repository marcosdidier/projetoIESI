# backend/schemas.py
"""
Define os esquemas de dados (Data Models) usando Pydantic.

Estes modelos são usados pelo FastAPI para:
1. Validar os dados de entrada das requisições (corpo JSON).
2. Serializar os dados de saída das respostas, garantindo um formato consistente.
3. Gerar a documentação automática da API (Swagger/OpenAPI).
"""

from pydantic import BaseModel
from typing import List, Optional

# --- Schemas para Respostas ---

class ExperimentResponse(BaseModel):
    """Schema para representar um experimento na resposta da API."""
    id: str  # ID de Agendamento/Referência
    elab_experiment_id: int
    researcher_id: int

    class Config:
        # Permite que o Pydantic leia os dados de um objeto ORM (SQLAlchemy).
        orm_mode = True

class ResearcherResponse(BaseModel):
    """Schema para representar um pesquisador na resposta da API, incluindo seus experimentos."""
    id: int
    name: str
    elab_item_id: Optional[int] = None
    role: str
    experiments: List[ExperimentResponse] = []

    class Config:
        orm_mode = True


# --- Schemas para Requisições ---

class ResearcherRequest(BaseModel):
    """Schema para o corpo da requisição ao cadastrar um novo pesquisador."""
    name: str
    password: str
    role: Optional[str] = "pesquisador"

class ExperimentRequest(BaseModel):
    """Schema para o corpo da requisição ao criar um novo experimento."""
    agendamento_id: str         # ID de referência único (ex: 'PROJ-X-001')
    item_pesquisador_id: int    # ID do item do pesquisador no eLabFTW
    researcher_id: int          # ID do pesquisador no nosso banco local
    display_name: str           # Nome do pesquisador para exibição
    tipo_amostra: str

class ElabCredentials(BaseModel):
    """Estrutura para agrupar as credenciais da API extraídas dos cabeçalhos."""
    url: str
    api_key: str
