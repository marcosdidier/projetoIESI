# src/backend/models.py
"""
Define os modelos de dados (tabelas) da aplicação usando SQLAlchemy ORM.

Estes modelos são a representação em Python do esquema do banco de dados local,
que armazena informações sobre pesquisadores e experimentos para evitar
consultas desnecessárias à API do eLabFTW e para manter um registro local.
"""
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from datetime import datetime

# Base declarativa que será usada por todos os modelos ORM.
Base = declarative_base()


class Researcher(Base):
    """
    Representa a tabela 'researchers'.

    Armazena os dados dos pesquisadores cadastrados no sistema.
    """
    __tablename__ = "researchers"

    # ID primário no nosso banco de dados local.
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True, comment="Nome completo e único do pesquisador.")
    password = Column(String, nullable=False, comment="Hash da senha para futura implementação de login.")
    
    # ID correspondente ao "item" do tipo "Pesquisador" no eLabFTW.
    # Essencial para vincular o registro local ao registro no eLab.
    elab_item_id = Column(Integer, nullable=True, unique=True)
    
    created_at = Column(DateTime, default=datetime.now)

    # Define a relação "um-para-muitos": um pesquisador pode ter múltiplos experimentos.
    # O cascade garante que, ao deletar um pesquisador, seus experimentos também sejam removidos.
    experiments = relationship("Experiment", back_populates="researcher", cascade="all, delete-orphan")


class Experiment(Base):
    """
    Representa a tabela 'experiments'.

    Armazena um registro local para cada experimento (solicitação) criado.
    """
    __tablename__ = "experiments"

    # Chave primária baseada no ID de agendamento/referência externa.
    # É um `String` para suportar códigos como 'PROJ-X-001'.
    id = Column(String, primary_key=True, index=True)
    
    # O ID real do experimento no banco de dados do eLabFTW.
    elab_experiment_id = Column(Integer, nullable=False, unique=True)
    
    # Chave estrangeira que liga o experimento ao seu pesquisador na tabela 'researchers'.
    researcher_id = Column(Integer, ForeignKey("researchers.id", ondelete="CASCADE"), nullable=False)
    
    created_at = Column(DateTime, default=datetime.now())

    # Define a relação "muitos-para-um", ligando de volta ao pesquisador.
    researcher = relationship("Researcher", back_populates="experiments")
