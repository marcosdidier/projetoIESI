# frontend/app.py
# Este é o front-end da aplicação, construído com Streamlit.
# Ele é responsável apenas pela interface e por se comunicar com o nosso back-end FastAPI.

import streamlit as st
import requests
from typing import Dict, Optional
import os
from dotenv import load_dotenv

# =========================
# Configs
# =========================

# Carregar variáveis do arquivo .env
load_dotenv()
DEFAULT_ELAB_URL = os.getenv("ELAB_URL", "")
DEFAULT_API_KEY = os.getenv("API_KEY", "")
BACKEND_URL = "http://127.0.0.1:8000"  # Endereço da nossa API FastAPI

# =========================
# Estado em memória (para guardar dados durante a sessão do usuário) 
# =========================
# """
# !!!!!!!!!!!!!!!!!!!
# TIRAR ISSO QUANDO FIZER O BANCO DE DADOS PARA CADASTRO
# DO PESQUISADOR
# !!!!!!!!!!!!!!!!!!!
# """

if "patients" not in st.session_state:
    st.session_state.patients: Dict[str, int] = {}
if "agendamentos" not in st.session_state:
    st.session_state.agendamentos: Dict[str, int] = {}
if "pdf_bytes" not in st.session_state:
    st.session_state.pdf_bytes: Optional[bytes] = None
if "pdf_name" not in st.session_state:
    st.session_state.pdf_name: Optional[str] = None

# =========================
# Interface do Usuário (UI)
# =========================
st.set_page_config(page_title="Plataforma Externa • LIACLI", page_icon="🧪", layout="centered")
st.title("🧪 Laboratório de Análises Clínicas • LIACLI")

with st.sidebar:
    st.header("Configuração da API")
    elab_url = st.text_input("ELAB_URL", value=DEFAULT_ELAB_URL)
    api_key = st.text_input("ELAB_API_KEY", value=DEFAULT_API_KEY, type="password")

    # Cabeçalhos que serão enviados em todas as requisições para o nosso backend
    api_headers = {"elab-url": elab_url, "elab-api-key": api_key}

    if st.button("Testar conexão"):
        if not api_key or api_key == DEFAULT_API_KEY:
            st.warning("Por favor, insira uma chave de API válida.")
        else:
            try:
                with st.spinner("Testando..."):
                    response = requests.post(f"{BACKEND_URL}/test-connection", headers=api_headers)
                    if response.status_code == 200:
                        st.success(response.json()["message"])
                    else:
                        st.error(f"Erro {response.status_code}: {response.text}")
            except requests.exceptions.RequestException as e:
                st.error(f"Falha de conexão com o backend: {e}")

st.divider()

# 1) Inicializar (ItemType + Template)
st.subheader("1) Inicializar Ambiente no eLabFTW")
if st.button("Garantir ItemType e Template Padrão"):
    try:
        with st.spinner("Inicializando..."):
            response = requests.post(f"{BACKEND_URL}/initialize", headers=api_headers)
            response.raise_for_status()
            data = response.json()
            st.success(f"ItemType 'Paciente' OK (id={data['item_type_id']})")
            st.success(f"Template 'Análise Clínica Padrão' OK (id={data['template_id']})")
    except requests.exceptions.RequestException as e:
        st.error(f"Erro ao inicializar: {e}")

st.divider()

# 2) Cadastrar paciente
st.subheader("2) Cadastrar paciente")
with st.form("form_patient"):
    name = st.text_input("Nome do paciente")
    ok = st.form_submit_button("Cadastrar")
    if ok:
        if not name.strip():
            st.warning("O nome do paciente não pode ser vazio.")
        else:
            try:
                with st.spinner("Cadastrando..."):
                    json_body = {"name": name.strip()}
                    response = requests.post(f"{BACKEND_URL}/pacientes", headers=api_headers, json=json_body)
                    response.raise_for_status()
                    data = response.json()
                    item_id = data["item_id"]
                    st.session_state.patients[name.strip()] = item_id
                    st.success(f"Paciente '{name}' cadastrado → item_id={item_id}")
            except requests.exceptions.RequestException as e:
                st.error(f"Erro ao cadastrar paciente: {e}")

if st.session_state.patients:
    st.caption("Pacientes cadastrados nesta sessão:")
    st.table([{"Nome": n, "item_id": iid} for n, iid in st.session_state.patients.items()])

st.divider()

# 3) Marcar experimento
st.subheader("3) Criar nova solicitação de análise")

with st.container(border=True):
    with st.form("form_experiment"):
        st.write("Primeiro, selecione o paciente para a análise:")
        
        # --- Lógica de Seleção do Paciente ---
        src = st.radio(
            "Origem do paciente",
            ["Escolher da lista (cadastrados nesta sessão)", "Informar item_id manualmente"],
            horizontal=True,
            label_visibility="collapsed"
        )

        selected_item_id = None
        display_name = ""

        if src == "Escolher da lista (cadastrados nesta sessão)":
            options = list(st.session_state.patients.keys())
            if not options:
                st.info("Nenhum paciente na sessão. Por favor, cadastre um paciente no passo 2.")
            else:
                nome_sel = st.selectbox("Paciente", options, index=None, placeholder="Selecione um paciente...")
                if nome_sel:
                    selected_item_id = st.session_state.patients[nome_sel]
                    display_name = nome_sel
        else: # "Informar item_id manualmente"
            manual_id_str = st.text_input("item_id do paciente")
            if manual_id_str.strip().isdigit():
                selected_item_id = int(manual_id_str.strip())
                # Para o título, usamos o ID, mas o usuário pode sobrescrever se quiser
                display_name = st.text_input("Nome (para o título da solicitação)", value=f"Paciente {selected_item_id}")
            elif manual_id_str: # Se o usuário digitou algo que não é um número
                st.warning("O item_id deve ser um número inteiro.")

        st.divider()
        st.write("Agora, preencha os dados da solicitação:")
        
        agendamento_id = st.text_input("ID do Agendamento (sua chave única de referência)")
        tipo_amostra   = st.text_input("Tipo de amostra", value="Sangue")
        
        submit_exp = st.form_submit_button("Criar Solicitação no eLabFTW")

        # --- Lógica de Submissão ---
        if submit_exp:
            agendamento_key = agendamento_id.strip()
            
            # 1. Validação robusta de todos os campos
            errors = []
            if not selected_item_id or not isinstance(selected_item_id, int):
                errors.append("Um paciente válido precisa ser selecionado ou informado.")
            if not agendamento_key:
                errors.append("O ID do Agendamento é obrigatório.")
            if agendamento_key in st.session_state.agendamentos:
                errors.append("Este ID de Agendamento já foi usado. Por favor, use um novo.")
            if not display_name.strip():
                errors.append("O nome para o título da solicitação não pode ser vazio.")

            # 2. Se não houver erros, prosseguir com a chamada de API
            if errors:
                for error in errors:
                    st.error(error)
            else:
                try:
                    with st.spinner("Criando solicitação no eLabFTW..."):
                        json_body = {
                            "agendamento_id": agendamento_key,
                            "item_paciente_id": selected_item_id,
                            "display_name": display_name.strip(),
                            "tipo_amostra": tipo_amostra.strip() or "Não informado",
                        }
                        response = requests.post(f"{BACKEND_URL}/experimentos", headers=api_headers, json=json_body)
                        response.raise_for_status() # Lança um erro para status HTTP 4xx ou 5xx
                        
                        data = response.json()
                        st.session_state.agendamentos[agendamento_key] = data["experiment_id"]
                        st.success(f"Solicitação criada! ID do Experimento={data['experiment_id']} | Status: {data['status']}")
                
                except requests.exceptions.RequestException as e:
                    # Tratamento de erro aprimorado para mostrar a mensagem do backend
                    error_message = str(e)
                    if e.response is not None:
                        try:
                            # Tenta pegar o detalhe do erro do JSON retornado pelo FastAPI
                            error_detail = e.response.json().get("detail", e.response.text)
                            error_message = f"Erro {e.response.status_code}: {error_detail}"
                        except:
                            # Se a resposta não for JSON, mostra o texto puro
                            error_message = f"Erro {e.response.status_code}: {e.response.text}"
                    st.error(f"Falha ao criar experimento: {error_message}")

# Usa um "expander" para não poluir a tela se a lista for grande
if st.session_state.agendamentos:
    with st.expander("Ver solicitações criadas nesta sessão", expanded=True):
        st.table([{"ID do Agendamento": k, "ID do Experimento (eLab)": v} for k, v in st.session_state.agendamentos.items()])

st.divider()

# 4) Ver status
st.subheader("4) Consultar status da solicitação")
with st.container(border=True):
    with st.form("form_status"):
        ag_key = st.text_input("Chave do agendamento")
        go_status = st.form_submit_button("Consultar")
        if go_status:
            ag_key = ag_key.strip()
            
            # Validação inicial dos dados
            if not ag_key:
                st.error("Informe a chave do agendamento.")
            elif ag_key not in st.session_state.agendamentos:
                st.error("Chave não encontrada nesta sessão. Verifique se digitou corretamente.")
            else:
                try:
                    with st.spinner("Buscando status..."):
                        exp_id = st.session_state.agendamentos[ag_key]
                        response = requests.get(f"{BACKEND_URL}/experimentos/{exp_id}/status", headers=api_headers)
                        response.raise_for_status() # Lança erro se a resposta for 4xx ou 5xx
                        data = response.json()
                        
                        # Exibe o status
                        if data['status'] == 'None':
                            st.info(f"🔄 Solicitação pendente. Aguardando processamento.")
                        
                        # Verifica se o status indica que a análise está em progresso
                        elif data['status'] == '1':
                            st.info(f"⏳ Solicitação em Andamento.")

                        # Verifica se o status indica que a análise foi concluída
                        elif data['status'] == '2':
                            st.success(f"✅ Solicitação Concluída!")
                            st.balloons()
                        
                        # Verifica se o status indica que a solicitação precisa ser refeita
                        elif data['status'] == '3':
                            st.warning(f"⚠️ Solicitação Requer Reavaliação.")
                        
                        # Caso o status seja outro, exibe um aviso
                        elif data['status'] == '4':
                            st.error(f"❌ Solicitação Falhou.")
                        
                        else:
                            st.warning(f"⚠️ Status desconhecido: '{data['status']}'.")

                except requests.exceptions.RequestException as e:
                    # Tratamento de erro aprimorado
                    error_message = str(e)
                    if e.response is not None:
                        try:
                            error_detail = e.response.json().get("detail", e.response.text)
                            error_message = f"Erro {e.response.status_code}: {error_detail}"
                        except:
                            error_message = f"Erro {e.response.status_code}: {e.response.text}"
                    st.error(f"Erro ao consultar status: {error_message}")

st.divider()

# 5) Baixar PDF
st.subheader("5) Baixar laudo em PDF")
with st.container(border=True):
    with st.form("form_pdf"):
        ag_key_pdf = st.text_input("Chave do agendamento")
        include_changelog = st.checkbox("Incluir changelog no PDF", value=False)
        go_pdf = st.form_submit_button("Gerar e Baixar Laudo")

        if go_pdf:
            ag_key_pdf = ag_key_pdf.strip()
            # Limpa qualquer PDF de uma tentativa anterior
            st.session_state.pdf_bytes = None
            st.session_state.pdf_name = None

            if not ag_key_pdf:
                st.error("Informe a chave do agendamento.")
            elif ag_key_pdf not in st.session_state.agendamentos:
                st.error("Chave não encontrada nesta sessão.")
            else:
                try:
                    exp_id = st.session_state.agendamentos[ag_key_pdf]

                    # 1. PRIMEIRO, VERIFICA O STATUS
                    with st.spinner("Verificando status da análise..."):
                        status_response = requests.get(f"{BACKEND_URL}/experimentos/{exp_id}/status", headers=api_headers)
                        status_response.raise_for_status()
                        status_data = status_response.json()
                        status_code = status_data.get("status")

                    # 2. SÓ GERA O PDF SE O STATUS FOR DE CONCLUSÃO (2)
                    if status_code == "2":
                        with st.spinner(f"Análise concluída! Gerando PDF..."):
                            params = {"include_changelog": include_changelog}
                            pdf_response = requests.get(f"{BACKEND_URL}/experimentos/{exp_id}/pdf", headers=api_headers, params=params)
                            pdf_response.raise_for_status()

                            st.session_state.pdf_bytes = pdf_response.content
                            st.session_state.pdf_name = f"laudo_ag_{ag_key_pdf}.pdf"
                            st.success("PDF pronto para download!")
                    else:
                        # Se não estiver concluído, informa o usuário e não tenta baixar o PDF
                        st.warning(f"⚠️ A análise ainda não foi concluída (Status: '{status_code}'). O laudo só pode ser gerado ao final do processo.")

                except requests.exceptions.RequestException as e:
                    error_message = str(e)
                    if e.response is not None:
                        try:
                            error_detail = e.response.json().get("detail", e.response.text)
                            error_message = f"Erro {e.response.status_code}: {error_detail}"
                        except:
                            error_message = f"Erro {e.response.status_code}: {e.response.text}"
                    st.error(f"Erro ao comunicar com o servidor: {error_message}")

# O botão de download só aparece se os bytes do PDF existirem na sessão
if st.session_state.pdf_bytes and st.session_state.pdf_name:
    st.download_button(
        label="⬇️ Baixar Laudo",
        data=st.session_state.pdf_bytes,
        file_name=st.session_state.pdf_name,
        mime="application/pdf"
    )

st.divider()