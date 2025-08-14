# frontend/app.py (VERSÃO FINAL COM INTERFACE ATUALIZADA)
import streamlit as st
import requests
from typing import Dict, Optional, Any, List
import os
from dotenv import load_dotenv
from streamlit_autorefresh import st_autorefresh
import numpy as np

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

def api_create_researcher(headers: Dict, name: str) -> Dict:
    response = requests.post(f"{BACKEND_URL}/pesquisadores", headers=headers, json={"name": name})
    response.raise_for_status()
    return response.json()

def api_create_experiment(headers: Dict, body: Dict) -> Dict:
    response = requests.post(f"{BACKEND_URL}/experimentos", headers=headers, json=body)
    response.raise_for_status()
    return response.json()

def api_get_status(headers: Dict, exp_id: int) -> str:
    response = requests.get(f"{BACKEND_URL}/experimentos/{exp_id}/status", headers=headers)
    response.raise_for_status()
    return response.json().get('status', 'desconhecido')

def api_get_pdf(headers: Dict, exp_id: int, include_changelog: bool) -> bytes:
    params = {"include_changelog": include_changelog}
    response = requests.get(f"{BACKEND_URL}/experimentos/{exp_id}/pdf", headers=headers, params=params)
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
tab1, tab2, tab3 = st.tabs([
    " Nova Solicitação de Análise ",
    " Acompanhamento e Laudos ",
    " Administração "
])

# =========================
# ABA 1: NOVA SOLICITAÇÃO
# =========================
with tab1:
    st.header("Registrar Nova Solicitação de Análise")

    with st.expander("Cadastrar Novo Pesquisador (se necessário)"):
        with st.form("form_researcher"):
            name = st.text_input("Nome completo do pesquisador", placeholder="Ex.: Profa. Maria Silva")
            if st.form_submit_button("Cadastrar Pesquisador", use_container_width=True):
                if not name.strip():
                    st.warning("O nome do pesquisador não pode ser vazio.")
                else:
                    try:
                        with st.spinner(f"Cadastrando '{name.strip()}'..."):
                            data = api_create_researcher(api_headers, name.strip())
                            
                            # --- INÍCIO DA CORREÇÃO PARA O KEYERROR ---
                            # Garante que a chave 'experiments' exista no dicionário do pesquisador,
                            # mesmo que ele seja novo e a API não retorne a lista vazia.
                            if 'experiments' not in data:
                                data['experiments'] = []
                            # --- FIM DA CORREÇÃO ---
                            
                            st.session_state.researchers_session[data["name"]] = data
                            st.success(f"Pesquisador '{data['name']}' cadastrado! (ID Local: {data['id']}, ID eLab: {data['elab_item_id']})")
                    
                    except requests.exceptions.RequestException as e:
                        handle_api_error(e, "Cadastrar Pesquisador")

    st.divider()
    
    st.subheader("Preencher Dados da Solicitação")
    with st.form("form_experiment"):
        researchers_in_session = list(st.session_state.researchers_session.keys()) #
        nome_pesquisador_selecionado = st.selectbox(
            "Pesquisador (carregados do banco)",
            options=sorted(researchers_in_session),
            index=None,
            placeholder="Escolha um pesquisador..."
        )
        
        c1, c2 = st.columns(2)
        with c1:
            agendamento_id = st.text_input("ID de Referência (Agendamento)", help="Código único para referência externa. Ex: 'PROJ-X-001'", placeholder="PROJ-X-001")
        with c2:
            tipo_amostra = st.text_input("Tipo de Amostra", value="Sangue Total", help="Ex.: Sangue Total, Soro, Plasma, etc.")

        if st.form_submit_button("Criar Solicitação no eLabFTW", type="primary", use_container_width=True):
            if not nome_pesquisador_selecionado:
                st.error("Selecione um pesquisador da lista.")
            elif not agendamento_id.strip():
                st.error("O ID de Referência (Agendamento) é obrigatório.")
            elif agendamento_id.strip() in st.session_state.agendamentos: #
                st.error("Este ID de Referência já foi usado. Crie um novo.")
            else:
                try:
                    researcher_info = st.session_state.researchers_session[nome_pesquisador_selecionado] #
                    local_id = researcher_info["id"] #
                    elab_item_id = researcher_info.get("elab_item_id") #

                    with st.spinner("Criando solicitação no eLabFTW..."):
                        json_body = {
                            "agendamento_id": agendamento_id.strip(),
                            "researcher_id": local_id, #
                            "item_pesquisador_id": elab_item_id or 0,
                            "display_name": nome_pesquisador_selecionado.strip(),
                            "tipo_amostra": tipo_amostra.strip() or "Não informado",
                        }
                        data = api_create_experiment(api_headers, json_body)
                        
                        # 1. Atualiza a lista geral de agendamentos (como já fazia antes)
                        st.session_state.agendamentos[agendamento_id.strip()] = data["experiment_id"]

                        # 2. Prepara os dados do novo experimento no formato que o frontend espera
                        new_experiment_data = {
                            "id": agendamento_id.strip(),
                            "elab_experiment_id": data["experiment_id"]
                        }

                        # 3. Adiciona o novo experimento à lista de experimentos do pesquisador na sessão
                        st.session_state.researchers_session[nome_pesquisador_selecionado]['experiments'].append(new_experiment_data)
                        
                        st.success(f"Solicitação criada! ID do Experimento: {data['experiment_id']} | Status: {data['status']}")
                        st.info("Acompanhe o status na aba 'Acompanhamento e Laudos'.")
                except requests.exceptions.RequestException as e:
                    handle_api_error(e, "Criar Solicitação")

# =========================
# ABA 2: ACOMPANHAMENTO E LAUDOS
# =========================
with tab2:
    st.header("Acompanhamento e Laudo da Análise")

    agendamentos_existentes = list(st.session_state.agendamentos.keys()) #
    ag_key_selecionado = st.selectbox(
        "Selecione o ID de Referência da solicitação",
        options=sorted(agendamentos_existentes, reverse=True),
        index=None,
        placeholder="Escolha uma solicitação para consultar..."
    )

    if st.button("Consultar Status", use_container_width=True, disabled=not ag_key_selecionado):
        st.session_state.last_consulted_id = ag_key_selecionado
        st.session_state.pdf_info = {"bytes": None, "name": None}

    if st.session_state.last_consulted_id:
        ag_key = st.session_state.last_consulted_id
        if ag_key not in st.session_state.agendamentos:
            st.error(f"ID de Referência '{ag_key}' não encontrado. Verifique se os dados foram carregados.")
        else:
            exp_id = st.session_state.agendamentos[ag_key] #
            st.info(f"Consultando Referência: **{ag_key}** (Experimento eLab: **{exp_id}**)")
            try:
                status = api_get_status(api_headers, exp_id)
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
                                pdf_bytes = api_get_pdf(api_headers, exp_id, include_changelog)
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
# Rodapé
# =========================
gradient_bar()
st.caption("LIACLI | UFPE — Ambiente de demonstração. Para suporte, contate o responsável pelo laboratório.")
