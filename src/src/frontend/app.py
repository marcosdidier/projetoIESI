# frontend/app.py (VERSÃO FINAL COM INTERFACE ATUALIZADA)
import streamlit as st
import requests
from typing import Dict, Optional, Any, List
import os
from dotenv import load_dotenv
from streamlit_autorefresh import st_autorefresh
import numpy as np
import json

# ==============================================================================
# APLICAÇÃO FRONTEND COM STREAMLIT
# ------------------------------------------------------------------------------
# Este arquivo constrói a interface gráfica com a qual o usuário interage.
# Ele se conecta automaticamente ao backend, carrega os dados do banco
# e adota uma interface moderna sem a necessidade de configuração manual.
# ==============================================================================


# =========================
# Helpers de UI e Configuração
# =========================

def gradient_bar(height: int = 6, width: int = 1200):
    """Barra de separação em degradê renderizada como imagem."""
    left = np.array([252, 76, 76], dtype=np.float32)
    right = np.array([255, 255, 124], dtype=np.float32)
    x = np.linspace(0.0, 1.0, width, dtype=np.float32).reshape(1, width, 1)
    grad = (left * (1 - x) + right * x).astype(np.uint8)
    bar = np.repeat(grad, height, axis=0)
    st.image(bar, use_container_width=True, clamp=True)

# Carrega variáveis de ambiente de um arquivo .env
load_dotenv()

# Busca as configurações da API do .env ou usa valores padrão.
ELAB_URL = os.getenv("ELAB_URL", "")
API_KEY = os.getenv("API_KEY", "")
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

# Cabeçalhos da API usados em todas as chamadas
api_headers = {"elab-url": ELAB_URL, "elab-api-key": API_KEY}


# =========================
# Estado da Sessão (Session State)
# =========================
# Guarda os pesquisadores carregados do banco (Chave: nome, Valor: dict com dados do pesquisador)
if "researchers_session" not in st.session_state:
    st.session_state.researchers_session: Dict[str, Dict[str, Any]] = {}

# Guarda os experimentos criados (Chave: ID de Agendamento, Valor: ID do Experimento no eLab)
if "agendamentos" not in st.session_state:
    st.session_state.agendamentos: Dict[str, int] = {}

# Armazena temporariamente o último PDF gerado para o botão de download.
if "pdf_info" not in st.session_state:
    st.session_state.pdf_info: Dict[str, Any] = {"bytes": None, "name": None}

# Mantém o controle do último ID consultado para evitar recargas indesejadas.
if "last_consulted_id" not in st.session_state:
    st.session_state.last_consulted_id: Optional[str] = None

# Flag para controlar o carregamento inicial de dados
if "data_loaded" not in st.session_state:
    st.session_state.data_loaded = False

# Usuário logado (contexto de usuário)
if "user" not in st.session_state:
    st.session_state.user: Optional[Dict[str, Any]] = None


# =========================
# Funções de Comunicação com o Backend
# =========================

def handle_api_error(e: requests.exceptions.RequestException, context: str):
    """Exibe uma mensagem de erro amigável para o usuário em caso de falha na API."""
    error_message = str(e)
    if e.response is not None:
        try:
            error_detail = e.response.json().get("detail", e.response.text)
            error_message = f"Erro {e.response.status_code}: {error_detail}"
        except (ValueError, AttributeError):
            error_message = f"Erro {e.response.status_code}: {e.response.text}"
    st.error(f"Falha em '{context}': {error_message}")

def api_test_connection(headers: Dict) -> None:
    response = requests.post(f"{BACKEND_URL}/test-connection", headers=headers)
    response.raise_for_status()
    st.success(response.json()["message"])

def api_get_researchers(headers: Dict) -> List[Dict]:
    response = requests.get(f"{BACKEND_URL}/pesquisadores", headers=headers)
    response.raise_for_status()
    return response.json()

def api_get_experiments(headers: Dict) -> List[Dict]:
    response = requests.get(f"{BACKEND_URL}/experimentos", headers=headers)
    response.raise_for_status()
    return response.json()

def api_create_researcher(headers: Dict, name: str, password: str, role: str = "pesquisador") -> Dict:
    response = requests.post(f"{BACKEND_URL}/pesquisadores", headers=headers, json={"name": name, "password": password, "role": role})
    response.raise_for_status()
    return response.json()

def api_create_experiment(headers: Dict, body: Dict, researcher_id: int) -> Dict:
    headers_with_researcher = dict(headers)
    headers_with_researcher.update({"researcher-id": str(researcher_id)})
    response = requests.post(f"{BACKEND_URL}/experimentos", headers=headers_with_researcher, json=body)
    response.raise_for_status()
    return response.json()

def api_get_status(headers: Dict, exp_id: int, researcher_id: int) -> str:
    headers_with_researcher = dict(headers)
    headers_with_researcher.update({"researcher-id": str(researcher_id)})
    response = requests.get(f"{BACKEND_URL}/experimentos/{exp_id}/status", headers=headers_with_researcher)
    response.raise_for_status()
    return response.json().get('status', 'desconhecido')
# Adicione esta função em frontend/app.py

def api_set_status(headers: Dict, exp_id: int, researcher_id: int, status_code: Any) -> None:
    """Envia uma requisição para alterar o status de um experimento."""
    headers_with_researcher = dict(headers)
    headers_with_researcher.update({"researcher-id": str(researcher_id)})
    
    json_body = {"status": status_code}
    
    response = requests.post(f"{BACKEND_URL}/experimentos/{exp_id}/set-status", headers=headers_with_researcher, json=json_body)
    response.raise_for_status()

def api_get_pdf(headers: Dict, exp_id: int, include_changelog: bool, researcher_id: int) -> bytes:
    params = {"include_changelog": include_changelog}
    headers_with_researcher = dict(headers)
    headers_with_researcher.update({"researcher-id": str(researcher_id)})
    response = requests.get(f"{BACKEND_URL}/experimentos/{exp_id}/pdf", headers=headers_with_researcher, params=params)
    response.raise_for_status()
    return response.content

def api_initialize(headers: Dict) -> None:
    response = requests.post(f"{BACKEND_URL}/initialize", headers=headers)
    response.raise_for_status()
    st.success("Estruturas essenciais verificadas com sucesso no eLabFTW!")


# =========================
# Interface Principal (UI)
# =========================

st.set_page_config(page_title="Plataforma de Pesquisa • LIACLI", page_icon="🔬", layout="centered")
st.title("Portal de Integração | LIACLI")
st.caption("Fluxo Integrado de Solicitações e Gestão Laboratorial via eLabFTW")
gradient_bar()

# --- CARREGAMENTO AUTOMÁTICO DE DADOS ---
if not st.session_state.data_loaded:
    if not all([ELAB_URL, API_KEY]):
        st.warning("Configure as variáveis ELAB_URL e API_KEY no seu arquivo .env para iniciar.")
        st.stop()
    else:
        try:
            with st.spinner("Conectando ao backend e carregando dados do banco..."):
                api_test_connection(api_headers)
                researchers_data = api_get_researchers(api_headers)
                st.session_state.researchers_session = {r["name"]: r for r in researchers_data} #
                exp_data = api_get_experiments(api_headers)
                st.session_state.researchers_session = {r["name"]: r for r in researchers_data}
                exp_data = api_get_experiments(api_headers)
                st.session_state.agendamentos = {exp["id"]: exp["elab_experiment_id"] for exp in exp_data}
                st.toast(f"{len(researchers_data)} pesquisadores e {len(exp_data)} solicitações carregadas!", icon="✅")
                st.session_state.data_loaded = True
        except requests.exceptions.RequestException as e:
            handle_api_error(e, "Falha na conexão inicial e carregamento de dados")
            st.stop()

# --- ABAS PARA ORGANIZAR O FLUXO ---
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    " Nova Solicitação de Análise ",
    " Acompanhamento e Laudos ",
    " Administração ",
    " Usuários ",
    " Editar Experimento "
])



# =========================
# ABA 1: NOVA SOLICITAÇÃO
# =========================
with tab1:
    st.header("Registrar Nova Solicitação de Análise")

    # Access control: only users with role 'pesquisador' can create experiments
    if not st.session_state.user:
        st.warning("Você precisa estar logado para criar uma solicitação.")
        st.info("Acesse a aba 'Usuários' para fazer login.")
    elif st.session_state.user.get('role') != 'pesquisador':
        st.error("Acesso negado: apenas usuários com role 'pesquisador' podem criar solicitações.")
        st.info("Se você for administrador, use a aba 'Administração' para operações de gestão.")
    else:
        st.subheader("Preencher Dados da Solicitação")
        with st.form("form_experiment"):
            c1, c2 = st.columns(2)
            with c1:
                agendamento_id = st.text_input("Nome da Solicitação", help="Nome único para referência externa. Ex: 'PROJ-X-001'", placeholder="PROJ-X-001")
            with c2:
                # Categoria de amostras (pode ser estendida no futuro)
                tipo_options = ["Sangue"]
                tipo_amostra = st.selectbox("Tipo de Amostra", options=tipo_options, index=0,
                                            help="Selecione a categoria da amostra.")

            if st.form_submit_button("Criar Solicitação no eLabFTW", type="primary", use_container_width=True):
                user_name = st.session_state.user.get("name")
                researcher_info = st.session_state.researchers_session.get(user_name)
                if not researcher_info:
                    st.error("Usuário logado não encontrado entre os pesquisadores cadastrados.")
                elif not agendamento_id.strip():
                    st.error("O nome da solicitação é obrigatório.")
                elif agendamento_id.strip() in st.session_state.agendamentos:
                    st.error("Este nome de solicitação já foi usado. Crie um novo.")
                else:
                    try:
                        local_id = researcher_info["id"]
                        elab_item_id = researcher_info.get("elab_item_id")

                        with st.spinner("Criando solicitação no eLabFTW..."):
                            json_body = {
                                "agendamento_id": agendamento_id.strip(),
                                "researcher_id": local_id,
                                "item_pesquisador_id": elab_item_id or 0,
                                "display_name": user_name.strip(),
                                "tipo_amostra": (tipo_amostra or "").strip() or "Não informado",
                                "user": {
                                    "id": st.session_state.user.get("id"),
                                    "name": st.session_state.user.get("name"),
                                    "email": st.session_state.user.get("email")
                                }
                            }
                            data = api_create_experiment(api_headers, json_body, researcher_id=local_id)

                            # 1. Atualiza a lista geral de agendamentos (como já fazia antes)
                            st.session_state.agendamentos[agendamento_id.strip()] = data["experiment_id"]

                            # 2. Prepara os dados do novo experimento no formato que o frontend espera
                            new_experiment_data = {
                                "id": agendamento_id.strip(),
                                "elab_experiment_id": data["experiment_id"]
                            }

                            # 3. Adiciona o novo experimento à lista de experimentos do pesquisador na sessão
                            st.session_state.researchers_session[user_name]['experiments'].append(new_experiment_data)

                            st.success(f"Solicitação criada! ID do Experimento: {data['experiment_id']} | Status: {data['status']}")
                            st.info("Acompanhe o status na aba 'Acompanhamento e Laudos'.")
                    except requests.exceptions.RequestException as e:
                        handle_api_error(e, "Criar Solicitação")

# =========================
# ABA 4: USUÁRIOS (REGISTRO E LOGIN)
# =========================
with tab4:
    st.header("Gerenciamento de Pesquisadores")

    # --- Login de usuário: apenas pelo nome do pesquisador já cadastrado ---
    if st.session_state.user:
        st.success(f"Usuário logado: {st.session_state.user.get('name', '')}")
        if st.button("Sair", use_container_width=True):
            st.session_state.user = None
            st.rerun()
    else:
        st.subheader("Login de Pesquisador")
        researchers_names = sorted(st.session_state.researchers_session.keys())
        with st.form("form_login_researcher"):
            login_name = st.selectbox(
                "Selecione seu nome (pesquisador já cadastrado)",
                options=researchers_names,
                index=None,
                placeholder="Escolha seu nome..."
            )
            login_password = st.text_input("Senha", type="password", placeholder="Digite sua senha")
            if st.form_submit_button("Entrar", use_container_width=True):
                if not login_name:
                    st.warning("Selecione seu nome para autenticação.")
                elif not login_password:
                    st.warning("Digite sua senha.")
                else:
                    try:
                        resp = requests.post(
                            f"{BACKEND_URL}/login",
                            headers=api_headers,
                            json={"name": login_name, "password": login_password}
                        )
                        if resp.status_code == 200:
                            user_data = resp.json()
                            st.session_state.user = {
                                "id": user_data.get("id"),
                                "name": user_data.get("name"),
                                "elab_item_id": user_data.get("elab_item_id"),
                                "role": user_data.get("role")
                            }
                            st.success(f"Bem-vindo, {login_name}!")
                            st.rerun()
                        else:
                            st.error("Nome ou senha inválidos.")
                    except Exception as e:
                        st.error(f"Erro ao autenticar: {e}")

    st.divider()
    st.subheader("Cadastrar Novo Pesquisador na Plataforma")
    with st.form("form_researcher"):
        name = st.text_input("Nome completo do pesquisador", placeholder="Ex.: Profa. Maria Silva")
        password = st.text_input("Senha", type="password", placeholder="Digite uma senha")
        password2 = st.text_input("Confirme a Senha", type="password", placeholder="Repita a senha")
        role_option = st.selectbox("Papel (role)", options=["pesquisador", "admin", "maquina"], index=0, help="Selecione o papel do usuário no sistema.")
        if st.form_submit_button("Cadastrar Pesquisador", use_container_width=True):
            if not name.strip():
                st.warning("O nome do pesquisador não pode ser vazio.")
            elif not password or not password2:
                st.warning("A senha é obrigatória e deve ser confirmada.")
            elif password != password2:
                st.warning("As senhas não coincidem.")
            elif len(password) < 4:
                st.warning("A senha deve ter pelo menos 4 caracteres.")
            else:
                try:
                    with st.spinner(f"Cadastrando '{name.strip()}'..."):
                        data = api_create_researcher(api_headers, name.strip(), password, role_option)
                        # Garante que a chave 'experiments' exista
                        if 'experiments' not in data:
                            data['experiments'] = []
                        st.session_state.researchers_session[data["name"]] = data
                        st.success(f"Pesquisador '{data['name']}' cadastrado! (ID Local: {data['id']}, ID eLab: {data['elab_item_id']})")
                        # Faz login automático do pesquisador cadastrado
                        st.session_state.user = {
                            "id": data.get("id"),
                            "name": data.get("name"),
                            "elab_item_id": data.get("elab_item_id"),
                            "role": data.get("role")
                        }
                        st.success(f"Logado como {data.get('name')}")
                        st.rerun()
                except requests.exceptions.RequestException as e:
                    handle_api_error(e, "Cadastrar Pesquisador")

# =========================
# ABA 2: ACOMPANHAMENTO E LAUDOS
# =========================
with tab2:
    st.header("Acompanhamento e Laudo da Análise")

    # Access control: only 'pesquisador' role can view personal acompanhamento
    if not st.session_state.user:
        st.warning("Você precisa estar logado para acessar o acompanhamento e laudos.")
        st.info("Acesse a aba 'Usuários' para fazer login.")
    elif st.session_state.user.get('role') != 'pesquisador':
        st.error("Acesso negado: a aba de Acompanhamento é apenas para usuários com role 'pesquisador'.")
    else:
        # Mostra somente as solicitações do usuário logado
        user_name = st.session_state.user.get("name")
        researcher_data = st.session_state.researchers_session.get(user_name, {})
        user_experiments = researcher_data.get("experiments", [])
        ag_options = [exp["id"] for exp in user_experiments]

        if not ag_options:
            st.info("Você não tem solicitações registradas. Crie uma nova na aba 'Nova Solicitação de Análise'.")

        ag_key_selecionado = st.selectbox(
            "Selecione o Nome da Solicitação (apenas as suas)",
            options=sorted(ag_options, reverse=True),
            index=None,
            placeholder="Escolha uma solicitação para consultar..."
        )

        if st.button("Consultar Status", use_container_width=True, disabled=not ag_key_selecionado):
            st.session_state.last_consulted_id = ag_key_selecionado
            st.session_state.pdf_info = {"bytes": None, "name": None}

        if st.session_state.last_consulted_id:
            ag_key = st.session_state.last_consulted_id
            if ag_key not in st.session_state.agendamentos:
                st.error(f"Nome da solicitação '{ag_key}' não encontrado. Verifique se os dados foram carregados.")
            else:
                exp_id = st.session_state.agendamentos[ag_key] #
                st.info(f"Consultando Solicitação: **{ag_key}** (Experimento eLab: **{exp_id}**)")
                try:
                    # Envia o header com o ID do pesquisador para verificação no backend
                    researcher_id = st.session_state.user.get("id")
                    status = api_get_status(api_headers, exp_id, researcher_id)
                    status_messages = {
                        'None': ("Pendente", "🔄"), '1': ("Em Andamento", "⏳"), '2': ("Concluída", "✅"),
                        '3': ("Requer Reavaliação", "⚠️"), '4': ("Falhou", "❌"),
                    }
                    status_label, status_icon = status_messages.get(status, (status, "❓"))
                    st.metric(label="Status da Análise", value=status_label, delta=status_icon)

                    if status == '2':
                        st.divider()
                        st.subheader("Gerar Laudo em PDF")
                        include_changelog = st.checkbox("Incluir histórico de alterações no PDF")
                        if st.button("Gerar PDF", type="primary", use_container_width=True):
                            with st.spinner("Gerando PDF..."):
                                try:
                                    researcher_id = st.session_state.user.get("id")
                                    pdf_bytes = api_get_pdf(api_headers, exp_id, include_changelog, researcher_id)
                                    st.session_state.pdf_info["bytes"] = pdf_bytes
                                    st.session_state.pdf_info["name"] = f"laudo_{ag_key}.pdf"
                                except requests.exceptions.RequestException as e:
                                    handle_api_error(e, "Gerar PDF")
                    else:
                        st.info("A página será atualizada automaticamente a cada 30 segundos para verificar o status.")
                        st_autorefresh(interval=30 * 1000, key="status_refresh")
                except requests.exceptions.RequestException as e:
                    handle_api_error(e, f"Consultar Status (ID: {ag_key})")
        
        if st.session_state.pdf_info.get("bytes"):
            st.download_button(label="⬇️ Baixar Laudo Gerado", data=st.session_state.pdf_info["bytes"],
                               file_name=st.session_state.pdf_info["name"], mime="application/pdf", use_container_width=True)

# =========================
# ABA 3: ADMINISTRAÇÃO
# =========================
with tab3:
    st.header("Administração do Ambiente")
    # Admin-only area
    if not st.session_state.user:
        st.warning("Você precisa estar logado como administrador para acessar esta área.")
        st.info("Acesse a aba 'Usuários' para fazer login.")
    elif st.session_state.user.get('role') != 'admin':
        st.error("Acesso negado: apenas administradores podem acessar esta área.")
    else:
        st.markdown("Visão geral da sessão e do estado da integração.")
        st.divider()

        # --- NOVO BLOCO: STATUS DA INTEGRAÇÃO (COMO EM APP_NEW.PY) ---
        st.subheader("Status da Integração")
        col1, col2, col3 = st.columns(3)

        with col1:
            st.caption("Backend")
            # Usamos o flag 'data_loaded' para saber se a comunicação inicial funcionou
            if st.session_state.get("data_loaded"):
                st.write("✅ Disponível")
            else:
                st.write("❌ Indisponível")

        with col2:
            st.caption("eLabFTW")
            # Se os dados foram carregados, a conexão com o eLabFTW foi bem-sucedida
            if st.session_state.get("data_loaded"):
                st.write("✅ Conectado")
            else:
                st.write("❌ Não Conectado")

        with col3:
            st.caption("Credenciais (.env)")
            # Verifica se as variáveis de ambiente foram carregadas
            if bool(ELAB_URL and API_KEY):
                st.write("✅ Presentes")
            else:
                st.write("❌ Ausentes")

        st.divider()
        # --- FIM DO NOVO BLOCO ---


        st.subheader("Verificação Manual de Estruturas no eLabFTW")
        st.markdown("Esta ação verifica se o **Tipo de Item 'Pesquisador'** existe no seu eLabFTW. Se não existir, ele será criado.")
        if st.button("Verificar Estruturas", use_container_width=True):
            try:
                with st.spinner("Verificando..."):
                    api_initialize(api_headers)
            except requests.exceptions.RequestException as e:
                handle_api_error(e, "Inicializar Ambiente")

        st.divider()

        st.subheader("Dados da Sessão Atual (Carregados do Banco)")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Pesquisadores**")
            st.json(st.session_state.researchers_session, expanded=False)
        with col2:
            st.markdown("**Solicitações (Agendamento -> ID eLab)**")
            st.json(st.session_state.agendamentos, expanded=False)

        st.divider()
        
        st.header("🔗 Visualizar Experimentos por Pesquisador")
        researcher_names = list(st.session_state.researchers_session.keys())
        
        if not researcher_names:
            st.info("Nenhum pesquisador carregado. Verifique a conexão e o banco de dados.")
        else:
            selected_name = st.selectbox(
                "Selecione um pesquisador para ver suas solicitações",
                options=sorted(researcher_names),
                index=None,
                placeholder="Escolha um pesquisador..."
            )

            if selected_name:
                researcher_data = st.session_state.researchers_session[selected_name]
                experiments_list = researcher_data.get('experiments', [])
                
                st.subheader(f"Solicitações de: {selected_name}")

                if not experiments_list:
                    st.write("Nenhuma solicitação encontrada para este pesquisador.")
                else:
                    for exp in experiments_list:
                        st.info(f"**ID da Referência (Agendamento):** `{exp['id']}`\n\n**ID do Experimento no eLab:** `{exp['elab_experiment_id']}`")

# =========================
# ABA 5: EDITAR EXPERIMENTO (MÁQUINA)
# =========================
with tab5:
    st.header("Editar Informações do Experimento (Máquina)")

    # Only machines can use this tab
    if not st.session_state.user:
        st.warning("Você precisa estar logado como máquina para editar experimentos.")
        st.info("Acesse a aba 'Usuários' para fazer login com uma conta de máquina.")
    elif st.session_state.user.get('role') != 'maquina':
        st.error("Acesso negado: apenas contas com role 'maquina' podem editar experimentos.")
    else:
        with st.form("form_edit_experiment"):
            exp_id_input = st.text_input("ID do Experimento (eLab)", placeholder="ex: 12345")
            if st.form_submit_button("Carregar Campos do Experimento", type="secondary"):
                st.session_state._edit_exp_loaded = False
                if not exp_id_input.strip():
                    st.error("ID do experimento é obrigatório para carregar campos.")
                else:
                    try:
                        exp_id = int(exp_id_input.strip())
                    except ValueError:
                        st.error("ID do experimento deve ser um número inteiro.")
                        exp_id = None

                    if exp_id:
                        try:
                            headers_with_researcher = dict(api_headers)
                            headers_with_researcher.update({"researcher-id": str(st.session_state.user.get("id"))})
                            resp = requests.get(f"{BACKEND_URL}/experimentos/{exp_id}/body", headers=headers_with_researcher)
                            resp.raise_for_status()
                            data = resp.json()
                            # Backend now returns a structured 'fields' list when possible
                            fields = data.get("fields") or []
                            body_text = data.get("body", "")

                            if fields:
                                # store fields list (preserves order and metadata)
                                st.session_state._edit_fields_list = fields
                                st.session_state._edit_exp_loaded = True
                                st.session_state._edit_exp_id = exp_id
                                st.success(f"Corpo do experimento {exp_id} carregado. {len(fields)} campos detectados.")
                            else:
                                # fallback: keep raw body for manual editing
                                st.session_state._edit_fields_list = []
                                st.session_state._edit_exp_loaded = True
                                st.session_state._edit_exp_id = exp_id
                                st.session_state._edit_body_raw = body_text
                                st.success(f"Corpo do experimento {exp_id} carregado. Nenhum campo estruturado detectado.")
                        except requests.exceptions.RequestException as e:
                            handle_api_error(e, "Carregar Corpo do Experimento")

        # Se campos foram carregados, renderiza inputs separados por campo
        if st.session_state.get("_edit_exp_loaded"):
            exp_id = st.session_state.get("_edit_exp_id")
            fields_list = st.session_state.get("_edit_fields_list", []) or []

            st.markdown("### Campos detectados no corpo do experimento")
            updated_values = {}

            if fields_list:
                for f in fields_list:
                    label = f.get("label") or f.get("key")
                    value = f.get("value", "")
                    unit = f.get("unit", "")
                    reference = f.get("reference", "")
                    key = f"edit_field_{exp_id}_{f.get('key', label)}"

                    col1, col2 = st.columns([2,1])
                    with col1:
                        updated_values[label] = st.text_input(f"{label}", value=value, key=key)
                    with col2:
                        # show unit and reference compactly
                        st.caption(f"{unit or ''}\n{reference or ''}")

            else:
                # No structured fields: show raw body for manual edit
                raw = st.session_state.get("_edit_body_raw", "")
                updated_raw = st.text_area("Corpo bruto do experimento", value=raw, height=300, key=f"edit_body_raw_{exp_id}")
                # If user edited raw, we won't parse fields; submit will send raw lines
                # Map lines like 'Key: value' into results dict on submit

            if st.button("Enviar Atualização do Experimento", type="primary"):
                # Build results payload
                results_payload = None
                if fields_list:
                    results_payload = {k: v for k, v in updated_values.items()}
                else:
                    # parse updated_raw into dict
                    updated_raw = st.session_state.get(f"edit_body_raw_{exp_id}", "")
                    parsed = {}
                    for line in (updated_raw or "").splitlines():
                        if ':' in line:
                            k, v = line.split(':', 1)
                            parsed[k.strip()] = v.strip()
                    results_payload = parsed

                if not results_payload:
                    st.error("Nenhum campo disponível para enviar.")
                else:
                    # frontend/app.py (ABA 5)
                    try:
                        researcher_id = st.session_state.user.get("id")
                        headers_with_researcher = dict(api_headers)
                        headers_with_researcher.update({"researcher-id": str(researcher_id)})

                        # Etapa 1: Atualizar os resultados
                        with st.spinner(f"Enviando atualização para o experimento {exp_id}..."):
                            resp = requests.patch(
                                f"{BACKEND_URL}/experimentos/{exp_id}/update-results", 
                                headers=headers_with_researcher, 
                                json={"results": results_payload}
                            )
                            resp.raise_for_status()
                        st.toast("Resultados atualizados!", icon="📝")

                        # Etapa 2: Mudar o status para 2 (Concluído)
                        with st.spinner(f"Marcando experimento {exp_id} como 'Concluído'..."):
                            api_set_status(api_headers, exp_id, researcher_id, status_code=2)
                        
                        st.success(f"Experimento {exp_id} atualizado e marcado como 'Concluído' com sucesso!")

                    except requests.exceptions.RequestException as e:
                        handle_api_error(e, "Enviar Atualização do Experimento")
# =========================
# Rodapé
# =========================
gradient_bar()
st.caption("LIACLI | UFPE — Ambiente de demonstração. Para suporte, contate o responsável pelo laboratório.")