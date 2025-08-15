# src/backend/database.py
"""
Módulo de Gerenciamento do Banco de Dados.

Responsável por toda a interação com o banco de dados PostgreSQL, incluindo:
- Configuração e criação da engine de conexão do SQLAlchemy.
- Gerenciamento de sessões do banco de dados.
- Funções para inicialização (criação de tabelas) e testes de conexão.
- Funções de CRUD (Create, Read, Update, Delete) para os modelos da aplicação.
"""

import os
from typing import List, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker, Session, joinedload
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from .models import Base, Researcher, Experiment
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do arquivo .env.
# `override=True` permite que as variáveis no .env sobrescrevam as do sistema.
load_dotenv(override=True)

# --- Configuração da Conexão a partir de Variáveis de Ambiente ---
DB_HOST = os.getenv("DB_HOST", "localhost").strip()
DB_PORT = os.getenv("DB_PORT", "5432").strip()
DB_USER = os.getenv("DB_USER", "postgres").strip()
DB_PASSWORD = os.getenv("DB_PASSWORD", "").strip()
DB_NAME = os.getenv("DB_NAME", "iesi_projeto").strip()
# Define `sslmode` como 'require' por padrão, exceto para conexões locais.
DB_SSLMODE = os.getenv("DB_SSLMODE", "disable" if DB_HOST in ("localhost", "127.0.0.1") else "require")

# Monta a URL de conexão para o SQLAlchemy.
DATABASE_URL = os.getenv("DATABASE_URL")

# Cria a "engine" do SQLAlchemy, o ponto central de comunicação com o banco.
# Configurações de pool otimizam o reuso de conexões.
ENGINE = create_engine(
    DATABASE_URL,
    echo=False,          # Se True, imprime todos os SQLs executados.
    pool_pre_ping=True,  # Testa a validade das conexões antes de usá-las.
    pool_size=5,         # Número de conexões mantidas no pool.
    max_overflow=10,     # Conexões extras permitidas em picos de uso.
    pool_recycle=1800,   # Recicla conexões após 30 minutos (1800s).
    connect_args={"sslmode": DB_SSLMODE}, # Passa argumentos específicos do driver.
)

# Cria uma fábrica de sessões (SessionLocal) que será usada para criar
# sessões individuais do banco de dados para cada requisição.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=ENGINE)


# --- Funções Auxiliares de Conexão (Injeção de Dependência) ---

def get_db():
    """
    Gerador de sessão do banco de dados para injeção de dependência no FastAPI.
    Garante que a sessão seja sempre fechada após o uso.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Funções de Inicialização e Manutenção do Banco ---

def create_database_if_not_exists() -> bool:
    """
    Verifica se o banco de dados principal existe e o cria se necessário.
    Conecta-se ao banco 'postgres' padrão para realizar a operação.
    """
    # Em provedores de nuvem como Supabase, a criação de bancos é restrita.
    if ".supabase.co" in (DB_HOST or ""):
        print(f"ℹ️ Host gerenciado detectado. Pulando criação de banco '{DB_NAME}'.")
        return True

    conn = None
    try:
        print(f"🔧 Conectando ao 'postgres' para verificar a existência do banco '{DB_NAME}'...")
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, user=DB_USER,
            password=DB_PASSWORD, dbname="postgres", sslmode=DB_SSLMODE
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        
        cur.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s", (DB_NAME,))
        exists = cur.fetchone()
        
        if not exists:
            cur.execute(f'CREATE DATABASE "{DB_NAME}"')
            print(f"✅ Banco de dados '{DB_NAME}' criado com sucesso!")
        else:
            print(f"ℹ️ Banco de dados '{DB_NAME}' já existe.")
            
        cur.close()
        return True
    except psycopg2.Error as e:
        print(f"❌ Erro de PostgreSQL ao criar/verificar banco: {e}")
        return False
    except Exception as e:
        print(f"❌ Erro inesperado ao criar banco: {e}")
        return False
    finally:
        if conn:
            conn.close()

def init_database() -> bool:
    """Cria todas as tabelas definidas nos modelos do SQLAlchemy, se não existirem."""
    try:
        print(f"🔧 Validando/criando tabelas no banco '{DB_NAME}'...")
        Base.metadata.create_all(bind=ENGINE)
        print("✅ Tabelas validadas com sucesso!")
        return True
    except Exception as e:
        print(f"❌ Erro ao inicializar tabelas: {e}")
        return False

def test_connection() -> bool:
    """Testa a conexão com o banco de dados executando uma consulta simples."""
    try:
        print(f"🔧 Testando conexão com '{DB_NAME}'...")
        with ENGINE.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ Conexão com o PostgreSQL bem-sucedida!")
        return True
    except Exception as e:
        print(f"❌ Falha na conexão: {e}")
        print("  • Verifique se o PostgreSQL está em execução.")
        print("  • Verifique as credenciais no arquivo .env.")
        return False


# --- Funções de Operações no Banco (CRUD) ---

def get_all_researchers(db: Session) -> List[Researcher]:
    """Retorna todos os pesquisadores, com seus experimentos já carregados (eager loading)."""
    try:
        return db.query(Researcher).options(joinedload(Researcher.experiments)).order_by(Researcher.name).all()
    except Exception as e:
        print(f"❌ Erro ao buscar todos os pesquisadores: {e}")
        return []

def get_all_experiments(db: Session) -> List[Experiment]:
    """Retorna todos os experimentos registrados no banco de dados local."""
    try:
        return db.query(Experiment).all()
    except Exception as e:
        print(f"❌ Erro ao buscar todos os experimentos: {e}")
        return []

def register_researcher(db: Session, name: str, password: str, elab_item_id: Optional[int] = None, role: Optional[str] = None) -> Optional[Researcher]:
    """
    Registra um novo pesquisador ou atualiza um existente.

    Se um pesquisador com o mesmo nome já existe, atualiza seu `elab_item_id`,
    `password` e `role` se fornecidos. Caso contrário, cria um novo registro.

    Returns:
        O objeto Researcher criado ou encontrado, com seus experimentos carregados.
    """
    try:
        # Normaliza e valida o role se fornecido.
        allowed_roles = {"pesquisador", "admin", "maquina"}
        if role:
            role = role.strip().lower()
            if role not in allowed_roles:
                print(f"⚠️ Role inválido '{role}' fornecido. Usando 'pesquisador' por padrão.")
                role = "pesquisador"
        else:
            role = "pesquisador"

        existing_researcher = db.query(Researcher).filter(Researcher.name == name).first()
        
        if existing_researcher:
            # Se o pesquisador já existe, atualiza o ID do eLab se estiver faltando
            # e atualiza a senha/role se uma nova for fornecida (ou se estiver vazia localmente).
            updated = False
            if elab_item_id and not existing_researcher.elab_item_id:
                existing_researcher.elab_item_id = elab_item_id
                updated = True

            if password and existing_researcher.password != password:
                existing_researcher.password = password
                updated = True

            if role and existing_researcher.role != role:
                existing_researcher.role = role
                updated = True

            if updated:
                db.commit()

            # Recarrega o pesquisador forçando o carregamento dos experimentos.
            complete_researcher = db.query(Researcher).options(
                joinedload(Researcher.experiments)
            ).filter(Researcher.id == existing_researcher.id).first()
            return complete_researcher

        # Se não existe, cria um novo pesquisador.
        new_researcher = Researcher(name=name, password=password, elab_item_id=elab_item_id, role=role)
        db.add(new_researcher)
        db.commit()
        db.refresh(new_researcher) # Atualiza o objeto com os dados do banco (como o ID gerado).
        print(f"✅ Pesquisador '{name}' criado com ID local {new_researcher.id} e role '{new_researcher.role}'")
        return new_researcher
        
    except Exception as e:
        db.rollback() # Desfaz a transação em caso de erro.
        print(f"❌ Erro ao registrar pesquisador: {e}")
        return None

def register_experiment(db: Session, agendamento_id: str, elab_experiment_id: int, researcher_local_id: int) -> bool:
    """Registra um novo experimento no banco de dados local."""
    try:
        # Verifica se o experimento já foi registrado para evitar duplicatas.
        if db.query(Experiment).filter(Experiment.id == agendamento_id).first():
            print(f"ℹ️ Experimento '{agendamento_id}' já registrado.")
            return True
        # Garante que o pesquisador associado existe.
        if not db.query(Researcher).filter(Researcher.id == researcher_local_id).first():
            print(f"❌ Falha ao registrar experimento: Pesquisador com ID local {researcher_local_id} não encontrado.")
            return False
            
        new_experiment = Experiment(id=agendamento_id, elab_experiment_id=elab_experiment_id, researcher_id=researcher_local_id)
        db.add(new_experiment)
        db.commit()
        print(f"✅ Experimento '{agendamento_id}' (eLab ID: {elab_experiment_id}) registrado localmente.")
        return True
    except Exception as e:
        db.rollback()
        print(f"❌ Erro ao registrar experimento localmente: {e}")
        return False

# --- Bloco de Execução Principal (para setup e teste) ---
if __name__ == "__main__":
    print("🚀 Iniciando script de setup do banco de dados...")
    
    # 1. Criar o banco de dados se não existir.
    if not create_database_if_not_exists():
        raise SystemExit("Falha crítica: não foi possível criar ou verificar o banco de dados.")

    # 2. Criar as tabelas.
    if not init_database():
        raise SystemExit("Falha crítica: não foi possível inicializar as tabelas.")

    # 3. Testar a conexão.
    if not test_connection():
        raise SystemExit("Falha crítica: não foi possível conectar ao banco de dados.")

    print("\n✅ Setup do banco de dados concluído com sucesso!")
    print(f"  • Host: {DB_HOST}:{DB_PORT}")
    print(f"  • Banco: {DB_NAME}")
