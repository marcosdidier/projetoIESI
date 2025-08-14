# frontend/app.py (CORRIGIDO)
import streamlit as st
import requests
from typing import Dict, Optional, List, Any
import os
from dotenv import load_dotenv
from streamlit_autorefresh import st_autorefresh

# =========================
# Configs
# =========================
load_dotenv()
DEFAULT_ELAB_URL = os.getenv("ELAB_URL", "")
DEFAULT_API_KEY = os.getenv("API_KEY", "")
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

# =========================
# Estado da Sessão
# =========================
if "researchers_session" not in st.session_state:
    st.session_state.researchers_session: Dict[str, int] = {} # Pesquisadores cadastrados nesta sessão
if "agendamentos" not in st.session_state:
    st.session_state.agendamentos: Dict[str, int] = {} # Agendamentos criados {ag_id -> exp_id}
if "pdf_info" not in st.session_state:
    st.session_state.pdf_info: Dict[str, Any] = {"bytes": None, "name": None} # Guarda o último PDF gerado
if "last_consulted_id" not in st.session_state:
    st.session_state.last_consulted_id: Optional[str] = None # Guarda o último ID consultado

# =========================
# Funções de Comunicação com o Backend
# =========================
def handle_api_error(e: requests.exceptions.RequestException, context: str):
    """Formata e exibe uma mensagem de erro padronizada para falhas de API."""
    error_message = str(e)
    if e.response is not None:
        try:
            error_detail = e.response.json().get("detail", e.response.text)
            error_message = f"Erro {e.response.status_code}: {error_detail}"
        except (ValueError, AttributeError):
            error_message = f"Erro {e.response.status_code}: {e.response.text}"
    st.error(f"Falha em '{context}': {error_message}")

# =========================
# Interface Principal
# =========================
st.set_page_config(page_title="Plataforma de Pesquisa • LIACLI", page_icon="🔬", layout="centered")
st.title("🔬 Plataforma de Integração LIACLI")
st.caption("Interface para gestão de análises e experimentos no eLabFTW.")

# --- BARRA LATERAL DE CONFIGURAÇÃO ---
with st.sidebar:
    st.header("⚙️ Configuração da API")
    elab_url = st.text_input("URL do eLabFTW", value=DEFAULT_ELAB_URL, help="Ex: https://elab.seu-dominio.com")
    api_key = st.text_input("Chave da API (Read/Write)", value=DEFAULT_API_KEY, type="password")

    api_headers = {"elab-url": elab_url, "elab-api-key": api_key}

    if st.button("Testar Conexão", use_container_width=True):
        if not all([elab_url, api_key]):
            st.warning("Preencha a URL e a Chave da API.")
        else:
            try:
                with st.spinner("Testando..."):
                    response = requests.post(f"{BACKEND_URL}/test-connection", headers=api_headers)
                    response.raise_for_status()
                    st.success(response.json()["message"])
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
    st.markdown("Cadastre um pesquisador (se necessário) e crie uma nova solicitação de análise no eLabFTW.")

    # --- Seção de Cadastro de Pesquisador ---
    with st.expander("Cadastrar Novo Pesquisador (se ainda não existir)"):
        with st.form("form_researcher"):
            name = st.text_input("Nome completo do pesquisador")
            if st.form_submit_button("Cadastrar Pesquisador"):
                if not name.strip():
                    st.warning("O nome do pesquisador não pode ser vazio.")
                else:
                    try:
                        with st.spinner(f"Cadastrando '{name.strip()}'..."):
                            json_body = {"name": name.strip()}
                            # CORREÇÃO: Endpoint atualizado para /pesquisadores
                            response = requests.post(f"{BACKEND_URL}/pesquisadores", headers=api_headers, json=json_body)
                            response.raise_for_status()
                            data = response.json()
                            item_id = data["item_id"]
                            st.session_state.researchers_session[name.strip()] = item_id
                            st.success(f"Pesquisador '{name.strip()}' cadastrado com sucesso! (ID do Item: {item_id})")
                    except requests.exceptions.RequestException as e:
                        handle_api_error(e, "Cadastrar Pesquisador")

    # --- Seção de Criação de Experimento ---
    st.subheader("Preencher Dados da Solicitação")
    with st.form("form_experiment"):
        # Seleção do Pesquisador
        st.markdown("**Selecione o Pesquisador**")
        researchers_in_session = list(st.session_state.researchers_session.keys())
        if not researchers_in_session:
            st.info("Nenhum pesquisador cadastrado nesta sessão. Use o formulário acima para adicionar um.")
            nome_pesquisador_selecionado = None
        else:
            nome_pesquisador_selecionado = st.selectbox(
                "Pesquisador",
                options=researchers_in_session,
                index=None,
                placeholder="Escolha um pesquisador cadastrado na sessão..."
            )

        item_id_manual = st.text_input("Ou informe o ID do Item do pesquisador manualmente",
                                       help="Preencha se o pesquisador não estiver na lista acima.")

        # Dados da Solicitação
        st.markdown("**Detalhes da Análise**")
        agendamento_id = st.text_input("ID de Referência (Agendamento)",
                                       help="Um código único para sua referência externa. Ex: 'PROJ-X-001'")
        tipo_amostra = st.text_input("Tipo de Amostra", value="Sangue Total")

        # Submissão do Formulário
        if st.form_submit_button("Criar Solicitação no eLabFTW", type="primary", use_container_width=True):
            final_item_id = None
            display_name = ""
            if nome_pesquisador_selecionado:
                final_item_id = st.session_state.researchers_session[nome_pesquisador_selecionado]
                display_name = nome_pesquisador_selecionado
            elif item_id_manual.isdigit():
                final_item_id = int(item_id_manual)
                display_name = f"Pesquisador {final_item_id}"
            else:
                st.error("Selecione um pesquisador da lista ou informe um ID de item numérico válido.")

            if not agendamento_id.strip():
                st.error("O ID de Referência (Agendamento) é obrigatório.")
            elif agendamento_id.strip() in st.session_state.agendamentos:
                st.error("Este ID de Referência já foi utilizado nesta sessão. Use um novo.")
            elif final_item_id:
                try:
                    with st.spinner("Criando solicitação no eLabFTW..."):
                        json_body = {
                            "agendamento_id": agendamento_id.strip(),
                            # CORREÇÃO: Chave do body alinhada com o backend
                            "item_pesquisador_id": final_item_id,
                            "display_name": display_name.strip(),
                            "tipo_amostra": tipo_amostra.strip() or "Não informado",
                        }
                        response = requests.post(f"{BACKEND_URL}/experimentos", headers=api_headers, json=json_body)
                        response.raise_for_status()
                        data = response.json()
                        st.session_state.agendamentos[agendamento_id.strip()] = data["experiment_id"]
                        st.success(f"Solicitação criada! ID do Experimento: {data['experiment_id']} | Status Inicial: {data['status']}")
                        st.info("Acompanhe o status na aba 'Acompanhamento e Laudos'.")
                except requests.exceptions.RequestException as e:
                    handle_api_error(e, "Criar Solicitação")

# =========================
# ABA 2: ACOMPANHAMENTO E LAUDOS
# =========================
with tab2:
    st.header("Acompanhamento e Laudo da Análise")
    st.markdown("Consulte o andamento de uma solicitação e baixe o laudo em PDF quando estiver concluída.")

    ag_key_input = st.text_input(
        "Informe o ID de Referência (Agendamento) da solicitação",
        key="ag_key_status",
        help="Use o mesmo ID de referência que você informou na criação da solicitação."
    )

    if st.button("Consultar Status", use_container_width=True):
        st.session_state.last_consulted_id = ag_key_input.strip()
        st.session_state.pdf_info = {"bytes": None, "name": None} # Limpa PDF anterior

    if st.session_state.last_consulted_id:
        ag_key = st.session_state.last_consulted_id
        if not ag_key:
            st.warning("Por favor, informe um ID de Referência para consultar.")
        elif ag_key not in st.session_state.agendamentos:
            st.error(f"O ID de Referência '{ag_key}' não foi encontrado nesta sessão.")
        else:
            exp_id = st.session_state.agendamentos[ag_key]
            st.info(f"Consultando ID de Referência: **{ag_key}** (Experimento eLab: **{exp_id}**)")

            try:
                status_response = requests.get(f"{BACKEND_URL}/experimentos/{exp_id}/status", headers=api_headers)
                status_response.raise_for_status()
                status = status_response.json().get('status', 'desconhecido')

                status_messages = {
                    'None': ("Pendendo", "🔄 Solicitação aguardando processamento."),
                    '1': ("Em Andamento", "⏳ Análise em andamento no laboratório."),
                    '2': ("Concluída", "✅ Análise concluída! O laudo está pronto para ser gerado."),
                    '3': ("Requer Reavaliação", "⚠️ A análise requer atenção ou reavaliação."),
                    '4': ("Falhou", "❌ A análise falhou ou foi cancelada."),
                }
                status_label, status_message = status_messages.get(status, ("Desconhecido", f"⚠️ Status não reconhecido: '{status}'."))
                st.metric(label="Status da Análise", value=status_label)
                st.markdown(status_message)

                if status == '2':
                    st.divider()
                    st.subheader("Gerar Laudo em PDF")
                    include_changelog = st.checkbox("Incluir histórico de alterações (changelog) no PDF", value=False)
                    if st.button("Gerar e Baixar Laudo", type="primary", use_container_width=True):
                        with st.spinner("Gerando PDF..."):
                            try:
                                params = {"include_changelog": include_changelog}
                                pdf_response = requests.get(f"{BACKEND_URL}/experimentos/{exp_id}/pdf", headers=api_headers, params=params)
                                pdf_response.raise_for_status()
                                st.session_state.pdf_info["bytes"] = pdf_response.content
                                st.session_state.pdf_info["name"] = f"laudo_{ag_key}.pdf"
                            except requests.exceptions.RequestException as e:
                                handle_api_error(e, "Gerar PDF")
                else:
                    st.info("A página será atualizada automaticamente a cada 30 segundos até a conclusão.")
                    st_autorefresh(interval=30 * 1000, key="status_refresh")

            except requests.exceptions.RequestException as e:
                handle_api_error(e, f"Consultar Status (ID: {ag_key})")

    if st.session_state.pdf_info.get("bytes"):
        st.download_button(
            label="⬇️ Baixar Laudo Gerado",
            data=st.session_state.pdf_info["bytes"],
            file_name=st.session_state.pdf_info["name"],
            mime="application/pdf",
            use_container_width=True
        )

# =========================
# ABA 3: ADMINISTRAÇÃO
# =========================
with tab3:
    st.header("Administração do Ambiente eLabFTW")
    st.markdown("Ferramentas para garantir que o eLabFTW está configurado corretamente para esta aplicação.")

    st.subheader("Estruturas Essenciais no eLabFTW")
    # CORREÇÃO: Texto de ajuda atualizado para ser preciso
    st.markdown("""
    Esta ação verifica se o **Tipo de Item 'Pesquisador'** e o **Template 'Análise Clínica Padrão'**
    existem no seu eLabFTW. Se não existirem, serão criados.
    """)
    if st.button("Verificar e Criar Estruturas", use_container_width=True):
        try:
            with st.spinner("Verificando e, se necessário, criando estruturas..."):
                response = requests.post(f"{BACKEND_URL}/initialize", headers=api_headers)
                response.raise_for_status()
                data = response.json()
                st.success(f"OK! Tipo de Item 'Pesquisador' garantido (ID: {data['item_type_id']}).")
                st.success(f"OK! Template 'Análise Clínica Padrão' garantido (ID: {data['template_id']}).")
        except requests.exceptions.RequestException as e:
            handle_api_error(e, "Inicializar Ambiente")

    st.divider()

    st.subheader("Visualizar Dados da Sessão Atual")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Pesquisadores Cadastrados**")
        if st.session_state.researchers_session:
            st.table([{"Nome": n, "ID do Item": iid} for n, iid in st.session_state.researchers_session.items()])
        else:
            st.info("Nenhum pesquisador cadastrado nesta sessão.")
    with col2:
        st.markdown("**Solicitações Criadas**")
        if st.session_state.agendamentos:
            st.table([{"ID de Referência": k, "ID do Experimento": v} for k, v in st.session_state.agendamentos.items()])
        else:
            st.info("Nenhuma solicitação criada nesta sessão.")
