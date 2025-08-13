import os
from datetime import datetime
from typing import List
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, text
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Carregar variáveis de ambiente
from dotenv import load_dotenv
load_dotenv()

# ===== Configurações do PostgreSQL (do .env) =====
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "iesi_projeto")

# Construir URLs de conexão
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
ADMIN_DSN = f"host={DB_HOST} port={DB_PORT} user={DB_USER} password={DB_PASSWORD} dbname=postgres"

# Debug: mostrar configurações (sem senha)
if os.getenv("DEBUG", "false").lower() == "true":
    print(f"🔧 Configurações carregadas:")
    print(f"  • Host: {DB_HOST}")
    print(f"  • Port: {DB_PORT}")
    print(f"  • User: {DB_USER}")
    print(f"  • Database: {DB_NAME}")

# ===== Base SQLAlchemy =====
Base = declarative_base()

# ===== Modelos =====
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    experiments = relationship("Experiment", back_populates="user", cascade="all, delete-orphan")

class Experiment(Base):
    __tablename__ = "experiments"
    id = Column(String, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="experiments")

# ===== Helpers de conexão =====
def get_engine():
    """Retorna engine do SQLAlchemy com configurações do .env"""
    return create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)

def get_session_local():
    """Retorna SessionLocal"""
    engine = get_engine()
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ===== Bootstrap do banco =====
def create_database_if_not_exists() -> bool:
    """Cria o banco de dados se não existir"""
    try:
        print(f"🔧 Conectando em postgres para criar banco '{DB_NAME}'...")
        conn = psycopg2.connect(ADMIN_DSN)
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
        engine = get_engine()
        Base.metadata.create_all(bind=engine)
        print("✅ Tabelas criadas/validadas com sucesso!")
        return True
    except Exception as e:
        print(f"❌ Erro ao inicializar tabelas: {e}")
        return False

def test_connection() -> bool:
    """Testa a conexão com o banco"""
    try:
        print(f"🔧 Testando conexão com '{DB_NAME}'...")
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ Conexão com PostgreSQL bem-sucedida!")
        return True
    except Exception as e:
        print(f"❌ Erro na conexão: {e}")
        print(f"  • Verifique se PostgreSQL está rodando")
        print(f"  • Verifique as credenciais no .env")
        return False

# ===== Operações =====
def get_user_experiments(user_id: int) -> List[dict]:
    """Retorna experimentos de um usuário"""
    try:
        SessionLocal = get_session_local()
        with SessionLocal() as db:
            experiments = db.query(Experiment).filter(Experiment.user_id == user_id).all()
            return [{"id": e.id, "user_id": e.user_id, "created_at": e.created_at} for e in experiments]
    except Exception as e:
        print(f"❌ Erro ao buscar experimentos: {e}")
        return []

def register_user(name: str, password: str) -> bool:
    """Registra um novo usuário"""
    try:
        SessionLocal = get_session_local()
        with SessionLocal() as db:
            # Verificar se já existe
            if db.query(User).filter(User.name == name).first():
                print(f"ℹ️ Usuário '{name}' já existe")
                return True
                
            user = User(name=name, password=password)
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"✅ Usuário '{name}' criado (ID: {user.id})")
            return True
    except Exception as e:
        print(f"❌ Erro ao registrar usuário: {e}")
        return False

def register_experiment(experiment_id: str, user_id: int) -> bool:
    """Registra um novo experimento"""
    try:
        SessionLocal = get_session_local()
        with SessionLocal() as db:
            # Verificar se experimento já existe
            if db.query(Experiment).filter(Experiment.id == experiment_id).first():
                print(f"ℹ️ Experimento '{experiment_id}' já existe")
                return True
                
            # Verificar se usuário existe
            if not db.query(User).filter(User.id == user_id).first():
                print(f"❌ Usuário com ID {user_id} não encontrado")
                return False
                
            experiment = Experiment(id=experiment_id, user_id=user_id)
            db.add(experiment)
            db.commit()
            print(f"✅ Experimento '{experiment_id}' criado para usuário {user_id}")
            return True
    except Exception as e:
        print(f"❌ Erro ao registrar experimento: {e}")
        return False

def create_sample_data():
    """Cria dados de exemplo para teste"""
    print("🔧 Criando dados de exemplo...")
    
    # Criar usuários
    register_user("João Silva", "123456")
    register_user("Maria Santos", "abcdef")
    register_user("Pedro Costa", "qwerty")
    
    # Criar experimentos
    register_experiment("EXP001", 1)
    register_experiment("EXP002", 1)
    register_experiment("EXP003", 2)
    register_experiment("EXP004", 3)
    
    print("✅ Dados de exemplo criados!")

def show_data():
    """Mostra os dados no banco"""
    try:
        SessionLocal = get_session_local()
        with SessionLocal() as db:
            print("\n📊 Dados no banco:")
            print("=" * 50)
            
            # Usuários
            users = db.query(User).all()
            print(f"\n👥 Usuários ({len(users)}):")
            for user in users:
                print(f"  • ID: {user.id} | Nome: {user.name} | Criado: {user.created_at}")
            
            # Experimentos
            experiments = db.query(Experiment).all()
            print(f"\n🧪 Experimentos ({len(experiments)}):")
            for exp in experiments:
                owner = db.query(User).get(exp.user_id)
                owner_name = owner.name if owner else "Usuário não encontrado"
                print(f"  • ID: {exp.id} | Usuário: {owner_name} | Criado: {exp.created_at}")
            
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
    print(f"  • Usuário: {DB_USER}")
    print("\n🔧 Para conectar no Beekeeper Studio:")
    print(f"  • Host: {DB_HOST}")
    print(f"  • Port: {DB_PORT}")
    print(f"  • Database: {DB_NAME}")
    print(f"  • Username: {DB_USER}")
    print(f"  • Password: [sua senha do .env]")