from pydantic import BaseModel

class ResearcherRequest(BaseModel):
    """Corpo da requisição para cadastrar um novo pesquisador."""
    name: str

class ExperimentRequest(BaseModel):
    """Corpo da requisição para criar um novo experimento."""
    agendamento_id: str
    item_pesquisador_id: int
    display_name: str
    tipo_amostra: str

class ElabCredentials(BaseModel):
    """Estrutura para agrupar as credenciais da API."""
    url: str
    api_key: str