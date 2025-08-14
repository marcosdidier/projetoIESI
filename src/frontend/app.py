import os
from typing import Dict, Optional, Any, Tuple

import numpy as np
import requests
import streamlit as st
from dotenv import load_dotenv
from streamlit_autorefresh import st_autorefresh

# ==============================================================================
# LIACLI | Portal de Integração com eLabFTW (Frontend Streamlit)
# ==============================================================================

load_dotenv()

st.set_page_config(
    page_title="Portal de Integração | LIACLI",
    page_icon="🔬",
    layout="centered",
)

# -------------------------
# Configurações (.env)
# -------------------------
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
ELAB_URL = os.getenv("ELAB_URL", "")
API_KEY = os.getenv("API_KEY", "")

api_headers: Dict[str, str] = {
    "elab-url": ELAB_URL,
    "elab-api-key": API_KEY,
}

# -------------------------
# Helpers de UI (sem HTML inseguro)
# -------------------------

def gradient_bar(height: int = 6, width: int = 1200):
    """Barra de separação em degradê (laranja → amarelo) renderizada como imagem."""
    left = np.array([252, 76, 76], dtype=np.float32)   # laranja
    right = np.array([255, 255, 124], dtype=np.float32)  # amarelo
    x = np.linspace(0.0, 1.0, width, dtype=np.float32).reshape(1, width, 1)
    grad = (left * (1 - x) + right * x).astype(np.uint8)
    bar = np.repeat(grad, height, axis=0)
    st.image(bar, use_container_width=True, clamp=True)


def handle_api_error(e: requests.exceptions.RequestException, context: str):
    msg = str(e)
    if e.response is not None:
        try:
            detail = e.response.json().get("detail", e.response.text)
            msg = f"Erro {e.response.status_code}: {detail}"
        except Exception:
            msg = f"Erro {e.response.status_code}: {e.response.text}"
    st.error(f"Falha em '{context}': {msg}")

# -------------------------
# Chamadas ao backend
# -------------------------

def api_test_connection(headers: Dict) -> Tuple[bool, str]:
    try:
        r = requests.post(f"{BACKEND_URL}/test-connection", headers=headers)
        r.raise_for_status()
        return True, r.json().get("message", "Conexão realizada.")
    except requests.exceptions.RequestException as e:
        return False, str(e)


def api_create_researcher(headers: Dict, name: str) -> Dict:
    r = requests.post(f"{BACKEND_URL}/pesquisadores", headers=headers, json={"name": name})
    r.raise_for_status()
    return r.json()


def api_create_experiment(headers: Dict, body: Dict) -> Dict:
    r = requests.post(f"{BACKEND_URL}/experimentos", headers=headers, json=body)
    r.raise_for_status()
    return r.json()


def api_get_status(headers: Dict, exp_id: int) -> str:
    r = requests.get(f"{BACKEND_URL}/experimentos/{exp_id}/status", headers=headers)
    r.raise_for_status()
    return r.json().get("status", "desconhecido")


def api_get_pdf(headers: Dict, exp_id: int, include_changelog: bool) -> bytes:
    r = requests.get(
        f"{BACKEND_URL}/experimentos/{exp_id}/pdf",
        headers=headers,
        params={"include_changelog": include_changelog},
    )
    r.raise_for_status()
    return r.content


def api_initialize(headers: Dict) -> None:
    r = requests.post(f"{BACKEND_URL}/initialize", headers=headers)
    r.raise_for_status()

# -------------------------
# Estado de sessão
# -------------------------
if "researchers_session" not in st.session_state:
    st.session_state.researchers_session: Dict[str, int] = {}
if "agendamentos" not in st.session_state:
    st.session_state.agendamentos: Dict[str, int] = {}
if "pdf_info" not in st.session_state:
    st.session_state.pdf_info: Dict[str, Any] = {"bytes": None, "name": None}
if "last_consulted_id" not in st.session_state:
    st.session_state.last_consulted_id: Optional[str] = None
if "initialized_elab" not in st.session_state:
    st.session_state.initialized_elab = False
if "backend_alive" not in st.session_state:
    st.session_state.backend_alive = None  # True/False/None

# -------------------------
# Inicializações automáticas
# -------------------------
backend_ok, _ = api_test_connection(api_headers)
st.session_state.backend_alive = backend_ok

if not st.session_state.initialized_elab:
    if not ELAB_URL or not API_KEY:
        st.session_state.initialized_elab = False
        st.warning("Defina ELAB_URL e API_KEY no seu .env para inicializar o ambiente.")
    else:
        try:
            api_initialize(api_headers)
            st.session_state.initialized_elab = True
            st.toast("Estruturas essenciais verificadas/criadas.", icon="✅")
        except requests.exceptions.RequestException as e:
            st.session_state.initialized_elab = False
            handle_api_error(e, "Inicializar Ambiente")

# -------------------------
# Header
# -------------------------
st.title("Portal de Integração | LIACLI")
st.caption("Gestão formal de solicitações de análise e integração com eLabFTW.")
gradient_bar()

# -------------------------
# Abas
# -------------------------

TAB_SOLICITACAO = " Nova Solicitação de Análise "
TAB_ACOMPANHAMENTO = " Acompanhamento e Laudos "
TAB_ADMIN = " Administração "

tab1, tab2, tab3 = st.tabs([TAB_SOLICITACAO, TAB_ACOMPANHAMENTO, TAB_ADMIN])

# ========================
# Aba 1: Nova Solicitação
# ========================
with tab1:
    st.subheader("Registrar nova solicitação")
    st.caption("Cadastre o pesquisador (se necessário) e envie uma solicitação ao eLabFTW.")
    st.divider()

    # Cadastro de pesquisador (opcional)
    with st.expander("Cadastrar novo pesquisador"):
        with st.form("form_researcher"):
            name = st.text_input("Nome completo do pesquisador", placeholder="Ex.: Profa. Maria Silva")
            submitted_r = st.form_submit_button("Cadastrar", use_container_width=True)

            if submitted_r:
                if not name.strip():
                    st.warning("O nome do pesquisador não pode ser vazio.")
                else:
                    try:
                        data = api_create_researcher(api_headers, name.strip())
                        item_id = data["item_id"]
                        st.session_state.researchers_session[name.strip()] = item_id
                        st.success(f"Pesquisador '{name.strip()}' cadastrado (Item ID: {item_id}).")
                    except requests.exceptions.RequestException as e:
                        handle_api_error(e, "Cadastrar Pesquisador")

    st.divider()

    # Criação do experimento
    st.markdown("**Dados da solicitação**")
    with st.form("form_experiment"):
        # 1) Pesquisador (apenas via select; campo manual removido)
        researchers_in_session = list(st.session_state.researchers_session.keys())
        nome_pesquisador_selecionado = st.selectbox(
            "Pesquisador (sessão)",
            options=researchers_in_session,
            index=None,
            placeholder="Escolha um pesquisador…",
            help="Selecione um pesquisador previamente cadastrado nesta sessão.",
        )

        # 2) Detalhes
        c3, c4 = st.columns(2)
        with c3:
            agendamento_id = st.text_input(
                "ID de Referência (Agendamento)",
                help="Código externo único. Ex.: PROJ-X-001",
                placeholder="PROJ-X-001",
            )
        with c4:
            tipo_amostra = st.text_input(
                "Tipo de amostra (material)",
                value="Amostra de Sangue Integral",
                help="Ex.: Amostra de Sangue Integral, Soro, Plasma, Urina, etc.",
            )

        submitted_e = st.form_submit_button(
            "Criar solicitação no eLabFTW",
            type="primary",
            use_container_width=True,
        )

        if submitted_e:
            if not nome_pesquisador_selecionado:
                st.error("Selecione um pesquisador da lista.")
            elif not agendamento_id.strip():
                st.error("O ID de Referência (Agendamento) é obrigatório.")
            elif agendamento_id.strip() in st.session_state.agendamentos:
                st.error("Este ID de Referência já foi utilizado nesta sessão.")
            else:
                try:
                    final_item_id = st.session_state.researchers_session[nome_pesquisador_selecionado]
                    payload = {
                        "agendamento_id": agendamento_id.strip(),
                        "item_pesquisador_id": final_item_id,
                        "display_name": nome_pesquisador_selecionado.strip(),
                        "tipo_amostra": tipo_amostra.strip() or "Não informado",
                    }
                    data = api_create_experiment(api_headers, payload)
                    st.session_state.agendamentos[agendamento_id.strip()] = data["experiment_id"]

                    status_label = data.get("status")
                    if status_label is None or str(status_label).lower() == "none":
                        status_label = "Pendente"

                    st.success(
                        f"Solicitação criada com êxito. Experimento: {data['experiment_id']} · Status inicial: {status_label}"
                    )
                    st.info("Acompanhe o andamento e gere o laudo na aba “Acompanhamento e Laudos”.")
                except requests.exceptions.RequestException as e:
                    handle_api_error(e, "Criar Solicitação")

# ================================
# Aba 2: Acompanhamento e Laudos
# ================================
with tab2:
    st.header("Acompanhamento e Laudo da Análise")
    ag_key_input = st.text_input("Informe o ID de Referência (Agendamento) da solicitação", placeholder="Informe o código externo cadastrado (ex.: PROJ-X-001)")

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
# Aba 3: Administração
# =========================
with tab3:
    st.subheader("Administração do ambiente")
    st.caption("Visão geral da sessão e do estado da integração.")
    st.divider()

    # Pequeno e com ícones (sem HTML):
    c1, c2, c3 = st.columns(3)
    with c1:
        st.caption("Backend")
        st.write("✅ Disponível" if st.session_state.backend_alive else "❌ Indisponível")
    with c2:
        st.caption("eLabFTW")
        st.write("✅ Inicializado" if st.session_state.initialized_elab else "❌ Não inicializado")
    with c3:
        st.caption("Credenciais (.env)")
        cred_ok = bool(ELAB_URL and API_KEY)
        st.write("✅ Presentes" if cred_ok else "❌ Ausentes")

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("Pesquisadores cadastrados (sessão)")
        st.json(st.session_state.researchers_session, expanded=False)
    with col2:
        st.markdown("Solicitações criadas (agendamento → experimento)")
        st.json(st.session_state.agendamentos, expanded=False)

# -------------------------
# Rodapé
# -------------------------
gradient_bar()
st.caption("LIACLI | UFPE — Ambiente de demonstração. Para suporte, contate o responsável pelo laboratório.")
