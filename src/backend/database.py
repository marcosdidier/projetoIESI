import os
from typing import List
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker, Session
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from .models import Base, Researcher, Experiment
from dotenv import load_dotenv

load_dotenv(override=True)

DB_HOST = os.getenv("DB_HOST", "localhost").strip()
DB_PORT = os.getenv("DB_PORT", "5432").strip()
DB_USER = os.getenv("DB_USER", "postgres").strip()
DB_PASSWORD = os.getenv("DB_PASSWORD", "").strip()
DB_NAME = os.getenv("DB_NAME", "iesi_projeto").strip()
DB_SSLMODE = os.getenv("DB_SSLMODE", "disable" if DB_HOST in ("localhost", "127.0.0.1") else "require")

DATABASE_URL = URL.create(
    drivername="postgresql+psycopg2",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=int(DB_PORT) if DB_PORT else None,
    database=DB_NAME,
)

# # Debug: mostrar configurações (sem senha)
# if os.getenv("DEBUG", "false").lower() == "true":
#     print(f"🔧 Configurações carregadas:")
#     print(f"  • Host: {DB_HOST}")
#     print(f"  • Port: {DB_PORT}")
#     print(f"  • User: {DB_USER}")
#     print(f"  • Database: {DB_NAME}")

ENGINE = create_engine(
        DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=1800,
        connect_args={"sslmode": DB_SSLMODE},
    )

SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=ENGINE
)

# ===== Helpers de conexão =====
def get_engine():
    """Retorna engine do SQLAlchemy com configurações do .env"""
    return ENGINE

def get_session_local():
    """Retorna SessionLocal"""
    return SessionLocal

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ===== Bootstrap do banco =====
def create_database_if_not_exists() -> bool:
    """Cria o banco de dados se não existir"""
    try:
        # Em provedores gerenciados (ex.: Supabase) não é permitido criar databases
        if ".supabase.co" in (DB_HOST or ""):
            print(f"ℹ️ Host gerenciado detectado ('{DB_HOST}'). Pulando criação/verificação de database.")
            return True

        print(f"🔧 Conectando em postgres para criar banco '{DB_NAME}'...")
        # Conectar usando parâmetros para evitar problemas de parsing do DSN com caracteres especiais
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            dbname="postgres",
            sslmode=DB_SSLMODE,
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        
        # Verificar se banco existe
        cur.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s", (DB_NAME,))
        exists = cur.fetchone()
        
        if not exists:
            cur.execute(f'CREATE DATABASE "{DB_NAME}"')
            print(f"✅ Banco de dados '{DB_NAME}' criado com sucesso!")
        else:
            print(f"ℹ️ Banco de dados '{DB_NAME}' já existe.")
            
        cur.close()
        conn.close()
        return True
    except psycopg2.Error as e:
        print(f"❌ Erro PostgreSQL ao criar banco: {e}")
        return False
    except Exception as e:
        print(f"❌ Erro inesperado ao criar banco: {e}")
        return False

def init_database() -> bool:
    """Cria as tabelas"""
    try:
        print(f"🔧 Criando tabelas no banco '{DB_NAME}'...")
        Base.metadata.create_all(bind=ENGINE)
        print("✅ Tabelas criadas/validadas com sucesso!")
        return True
    except Exception as e:
        print(f"❌ Erro ao inicializar tabelas: {e}")
        return False

def test_connection() -> bool:
    """Testa a conexão com o banco"""
    try:
        print(f"🔧 Testando conexão com '{DB_NAME}'...")
        with ENGINE.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ Conexão com PostgreSQL bem-sucedida!")
        return True
    except Exception as e:
        print(f"❌ Erro na conexão: {e}")
        print(f"  • Verifique se PostgreSQL está rodando")
        print(f"  • Verifique as credenciais no .env")
        return False

# ===== Operações =====
def get_researcher_experiments(db: Session, researcher: int) -> List[dict]:
    """Retorna experimentos de um pesquisador"""
    try:
        experiments = db.query(Experiment).filter(Experiment.researcher_id == researcher).all()
        return [{"id": e.id, "researcher": e.researcher, "created_at": e.created_at} for e in experiments]
    except Exception as e:
        print(f"❌ Erro ao buscar experimentos: {e}")
        return []

def register_researcher(db: Session, name: str, password: str) -> bool:
    """Registra um novo pesquisador"""
    try:
        # Verificar se já existe
        if db.query(Researcher).filter(Researcher.name == name).first():
            print(f"ℹ️ Pesquisador '{name}' já existe")
            return True
                
        db.add(Researcher(name=name, password=password))
        db.commit()
        print(f"✅ Pesquisador '{name}' criado")
        return True
    except Exception as e:
        print(f"❌ Erro ao registrar Pesquisador: {e}")
        return False

def register_experiment(db: Session, experiment_id: str, researcher_id: int) -> bool:
    """Registra um novo experimento"""
    try:
            # Verificar se experimento já existe
            if db.query(Experiment).filter(Experiment.id == experiment_id).first():
                print(f"ℹ️ Experimento '{experiment_id}' já existe")
                return True
                
            # Verificar se Pesquisador existe
            if not db.query(Researcher).filter(Researcher.id == researcher_id).first():
                print(f"❌ Pesquisador com ID {researcher_id} não encontrado")
                return False
                
            db.add(Experiment(id=experiment_id, researcher_id=researcher_id))
            db.commit()
            print(f"✅ Experimento '{experiment_id}' criado para Pesquisador {researcher_id}")
            return True
    except Exception as e:
        print(f"❌ Erro ao registrar experimento: {e}")
        return False
    
# ===== Testes =====

def create_sample_data():
    """Cria dados de exemplo para teste"""
    print("🔧 Criando dados de exemplo...")
    SessionLocal = get_session_local()
    with SessionLocal() as db:
        # Criar Pesquisadors
        register_researcher(db, "D", "123456")
        register_researcher(db, "E", "abcdef")
        register_researcher(db, "F", "qwerty")
        
        # Criar experimentos
        register_experiment(db, "EXP005", 4)
        register_experiment(db, "EXP006", 5)
        register_experiment(db, "EXP007", 6)
        register_experiment(db, "EXP008", 4)
    
    print("✅ Dados de exemplo criados!")

def show_data():
    """Mostra os dados no banco"""
    try:
        SessionLocal = get_session_local()
        with SessionLocal() as db:
            print("\n📊 Dados no banco:")
            print("=" * 50)
            
            # Pesquisadors
            researchers = db.query(Researcher).all()
            print(f"\n👥 Pesquisadores ({len(researchers)}):")
            for researcher in researchers:
                print(f"  • ID: {researcher.id} | Nome: {researcher.name} | Criado: {researcher.created_at}")
            
            # Experimentos
            experiments = db.query(Experiment).all()
            print(f"\n🧪 Experimentos ({len(experiments)}):")
            for exp in experiments:
                owner = db.query(Researcher).get(exp.researcher_id)
                owner_name = owner.name if owner else "Pesquisador não encontrado"
                print(f"  • ID: {exp.id} | Pesquisador: {owner_name} | Criado: {exp.created_at}")
            
            print("\n" + "=" * 50)
    except Exception as e:
        print(f"❌ Erro ao mostrar dados: {e}")

def get_env_info() -> dict:
    """Retorna informações das variáveis de ambiente (para debug)"""
    return {
        "db_host": DB_HOST,
        "db_port": DB_PORT,
        "db_user": DB_USER,
        "db_name": DB_NAME,
        "has_password": bool(DB_PASSWORD),
        "app_env": os.getenv("APP_ENV", "production"),
        "debug": os.getenv("DEBUG", "false").lower() == "true"
    }

# ===== Script principal =====
if __name__ == "__main__":
    print("🚀 Iniciando setup do banco de dados...")
    print("=" * 60)
    
    # Mostrar configurações se debug estiver ativo
    if os.getenv("DEBUG", "false").lower() == "true":
        env_info = get_env_info()
        print(f"🔧 Ambiente: {env_info['app_env']}")
        print(f"🔧 Debug: {env_info['debug']}")
    
    # 1) Criar banco se não existir
    if not create_database_if_not_exists():
        print("❌ Falha ao criar/verificar banco")
        raise SystemExit(1)

    # 2) Criar tabelas
    if not init_database():
        print("❌ Falha ao criar tabelas")
        raise SystemExit(1)

    # 3) Testar conexão
    if not test_connection():
        print("❌ Falha na conexão")
        raise SystemExit(1)

    # 4) Criar dados de exemplo e mostrar
    create_sample_data()
    show_data()

    print("\n✅ Setup completo!")
    print(f"  • Host: {DB_HOST}:{DB_PORT}")
    print(f"  • Banco: {DB_NAME}")
    print(f"  • Pesquisador: {DB_USER}")
    print("\n🔧 Para conectar no Beekeeper Studio:")
    print(f"  • Host: {DB_HOST}")
    print(f"  • Port: {DB_PORT}")
    print(f"  • Database: {DB_NAME}")
    print(f"  • Username: {DB_USER}")
    print(f"  • Password: [sua senha do .env]")