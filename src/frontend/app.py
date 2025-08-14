# frontend/app.py (REFATORADO E COMENTADO)
import streamlit as st
import requests
from typing import Dict, Optional, Any
import os
from dotenv import load_dotenv
from streamlit_autorefresh import st_autorefresh

# ==============================================================================
# APLICAÇÃO FRONTEND COM STREAMLIT
# ------------------------------------------------------------------------------
# Este arquivo constrói a interface gráfica com a qual o usuário interage.
# Ele não contém lógica de negócio; apenas monta os botões e campos,
# e chama o nosso backend (main.py) para realizar as ações.
# ==============================================================================


# =========================
# Configuração Inicial
# =========================
load_dotenv() # Carrega variáveis de ambiente de um arquivo .env

# Busca as configurações da API ou usa valores padrão.
DEFAULT_ELAB_URL = os.getenv("ELAB_URL", "")
DEFAULT_API_KEY = os.getenv("API_KEY", "")
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")


# =========================
# Estado da Sessão (Session State)
# =========================
# O session_state do Streamlit é um "dicionário mágico" que persiste
# os dados enquanto o usuário mantém a aba do navegador aberta.

# Guarda os pesquisadores cadastrados durante a sessão para fácil acesso.
if "researchers_session" not in st.session_state:
    st.session_state.researchers_session: Dict[str, int] = {}

# Guarda os experimentos criados na sessão (ID de Referência -> ID do Experimento).
if "agendamentos" not in st.session_state:
    st.session_state.agendamentos: Dict[str, int] = {}

# Armazena temporariamente o último PDF gerado para o botão de download.
if "pdf_info" not in st.session_state:
    st.session_state.pdf_info: Dict[str, Any] = {"bytes": None, "name": None}

# Mantém o controle do último ID consultado para evitar recargas indesejadas.
if "last_consulted_id" not in st.session_state:
    st.session_state.last_consulted_id: Optional[str] = None


# =========================
# Funções de Comunicação com o Backend
# =========================

def handle_api_error(e: requests.exceptions.RequestException, context: str):
    """Exibe uma mensagem de erro amigável para o usuário em caso de falha na API."""
    error_message = str(e)
    # Tenta extrair a mensagem de erro específica do backend.
    if e.response is not None:
        try:
            error_detail = e.response.json().get("detail", e.response.text)
            error_message = f"Erro {e.response.status_code}: {error_detail}"
        except (ValueError, AttributeError):
            error_message = f"Erro {e.response.status_code}: {e.response.text}"
    st.error(f"Falha em '{context}': {error_message}")

# As funções abaixo encapsulam as chamadas de API, limpando o código da UI.
def api_test_connection(headers: Dict) -> None:
    response = requests.post(f"{BACKEND_URL}/test-connection", headers=headers)
    response.raise_for_status()
    st.success(response.json()["message"])

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
st.title("🔬 Plataforma de Integração LIACLI")
st.caption("Interface para gestão de análises e experimentos no eLabFTW.")

# --- BARRA LATERAL DE CONFIGURAÇÃO ---
with st.sidebar:
    st.header("⚙️ Configuração da API")
    elab_url = st.text_input("URL do eLabFTW", value=DEFAULT_ELAB_URL)
    api_key = st.text_input("Chave da API (Read/Write)", value=DEFAULT_API_KEY, type="password")

    # Os cabeçalhos são montados uma vez e reutilizados em todas as chamadas.
    api_headers = {"elab-url": elab_url, "elab-api-key": api_key}

    if st.button("Testar Conexão", use_container_width=True):
        if not all([elab_url, api_key]):
            st.warning("Preencha a URL e a Chave da API.")
        else:
            try:
                with st.spinner("Testando..."):
                    api_test_connection(api_headers)
            except requests.exceptions.RequestException as e:
                handle_api_error(e, "Testar Conexão")

# --- ABAS PARA ORGANIZAR O FLUXO ---
tab1, tab2, tab3 = st.tabs([
    " Nova Solicitação de Análise ",
    " Acompanhamento e Laudos ",
    " ⚙️ Administração "
])

# =========================
# ABA 1: NOVA SOLICITAÇÃO
# =========================
with tab1:
    st.header("Registrar Nova Solicitação de Análise")

    # --- Seção de Cadastro de Pesquisador ---
    with st.expander("Cadastrar Novo Pesquisador (se necessário)"):
        with st.form("form_researcher"):
            name = st.text_input("Nome completo do pesquisador")
            if st.form_submit_button("Cadastrar Pesquisador"):
                if not name.strip():
                    st.warning("O nome do pesquisador não pode ser vazio.")
                else:
                    try:
                        with st.spinner(f"Cadastrando '{name.strip()}'..."):
                            data = api_create_researcher(api_headers, name.strip())
                            item_id = data["item_id"]
                            st.session_state.researchers_session[name.strip()] = item_id
                            st.success(f"Pesquisador '{name.strip()}' cadastrado! (ID do Item: {item_id})")
                    except requests.exceptions.RequestException as e:
                        handle_api_error(e, "Cadastrar Pesquisador")

    st.divider()

    # --- Seção de Criação de Experimento ---
    st.subheader("Preencher Dados da Solicitação")
    with st.form("form_experiment"):
        st.markdown("**1. Selecione o Pesquisador**")
        researchers_in_session = list(st.session_state.researchers_session.keys())
        nome_pesquisador_selecionado = st.selectbox(
            "Pesquisador cadastrado na sessão",
            options=researchers_in_session,
            index=None,
            placeholder="Escolha um pesquisador..."
        )
        item_id_manual = st.text_input("Ou informe o ID do Item do pesquisador manualmente")

        st.markdown("**2. Detalhes da Análise**")
        agendamento_id = st.text_input("ID de Referência (Agendamento)", help="Um código único para sua referência externa. Ex: 'PROJ-X-001'")
        tipo_amostra = st.text_input("Tipo de Amostra", value="Sangue Total")

        if st.form_submit_button("Criar Solicitação no eLabFTW", type="primary", use_container_width=True):
            final_item_id, display_name = (None, "")
            if nome_pesquisador_selecionado:
                final_item_id = st.session_state.researchers_session[nome_pesquisador_selecionado]
                display_name = nome_pesquisador_selecionado
            elif item_id_manual.isdigit():
                final_item_id = int(item_id_manual)
                display_name = f"Pesquisador ID {final_item_id}"
            else:
                st.error("Selecione um pesquisador da lista ou informe um ID de item numérico válido.")

            if not agendamento_id.strip():
                st.error("O ID de Referência (Agendamento) é obrigatório.")
            elif agendamento_id.strip() in st.session_state.agendamentos:
                st.error("Este ID de Referência já foi usado. Crie um novo.")
            elif final_item_id:
                try:
                    with st.spinner("Criando solicitação no eLabFTW..."):
                        json_body = {
                            "agendamento_id": agendamento_id.strip(),
                            "item_pesquisador_id": final_item_id,
                            "display_name": display_name.strip(),
                            "tipo_amostra": tipo_amostra.strip() or "Não informado",
                        }
                        data = api_create_experiment(api_headers, json_body)
                        st.session_state.agendamentos[agendamento_id.strip()] = data["experiment_id"]
                        st.success(f"Solicitação criada! ID do Experimento: {data['experiment_id']} | Status: {data['status']}")
                        st.info("Acompanhe o status na aba 'Acompanhamento e Laudos'.")
                except requests.exceptions.RequestException as e:
                    handle_api_error(e, "Criar Solicitação")

# =========================
# ABA 2: ACOMPANHAMENTO E LAUDOS
# =========================
with tab2:
    st.header("Acompanhamento e Laudo da Análise")
    ag_key_input = st.text_input("Informe o ID de Referência (Agendamento) da solicitação")

    if st.button("Consultar Status", use_container_width=True):
        st.session_state.last_consulted_id = ag_key_input.strip()
        st.session_state.pdf_info = {"bytes": None, "name": None} # Limpa PDF anterior

    if st.session_state.last_consulted_id:
        ag_key = st.session_state.last_consulted_id
        if not ag_key:
            st.warning("Informe um ID de Referência para consultar.")
        elif ag_key not in st.session_state.agendamentos:
            st.error(f"ID de Referência '{ag_key}' não encontrado nesta sessão.")
        else:
            exp_id = st.session_state.agendamentos[ag_key]
            st.info(f"Consultando Referência: **{ag_key}** (Experimento eLab: **{exp_id}**)")
            try:
                status = api_get_status(api_headers, exp_id)
                status_messages = {
                    'None': ("Pendendo", "🔄"), '1': ("Em Andamento", "⏳"), '2': ("Concluída", "✅"),
                    '3': ("Requer Reavaliação", "⚠️"), '4': ("Falhou", "❌"),
                }
                status_label, status_icon = status_messages.get(status, ("Desconhecido", "❓"))
                st.metric(label="Status da Análise", value=status_label, delta=status_icon)

                if status == '2': # Se concluída, oferece o download do PDF
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
                else: # Se não concluída, ativa o auto-refresh
                    st.info("A página será atualizada automaticamente a cada 30 segundos.")
                    st_autorefresh(interval=30 * 1000, key="status_refresh")
            except requests.exceptions.RequestException as e:
                handle_api_error(e, f"Consultar Status (ID: {ag_key})")
    
    # Botão de download só aparece se um PDF foi gerado com sucesso.
    if st.session_state.pdf_info.get("bytes"):
        st.download_button(label="⬇️ Baixar Laudo Gerado", data=st.session_state.pdf_info["bytes"],
                           file_name=st.session_state.pdf_info["name"], mime="application/pdf", use_container_width=True)

# =========================
# ABA 3: ADMINISTRAÇÃO
# =========================
with tab3:
    st.header("Administração do Ambiente")
    st.markdown("Use estas ferramentas para configurar e verificar o ambiente no eLabFTW.")

    st.subheader("Inicializar Estruturas Essenciais")
    st.markdown("Esta ação verifica se o **Tipo de Item 'Pesquisador'** existe no seu eLabFTW. Se não existir, ele será criado automaticamente.")
    if st.button("Verificar Estruturas", use_container_width=True):
        try:
            with st.spinner("Verificando..."):
                api_initialize(api_headers)
        except requests.exceptions.RequestException as e:
            handle_api_error(e, "Inicializar Ambiente")

    st.divider()
    st.subheader("Dados da Sessão Atual")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Pesquisadores Cadastrados**")
        st.json(st.session_state.researchers_session, expanded=False)
    with col2:
        st.markdown("**Solicitações Criadas**")
        st.json(st.session_state.agendamentos, expanded=False)
