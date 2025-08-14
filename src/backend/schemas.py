from pydantic import BaseModel

class ExperimentRequest(BaseModel):
    agendamento_id: str
    item_paciente_id: int
    display_name: str
    tipo_amostra: str

class PatientRequest(BaseModel):
    name: str