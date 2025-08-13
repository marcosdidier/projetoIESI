import json
from datetime import datetime
from typing import Any, Dict, Optional

import requests
import streamlit as st

# ==============================================================================
# MELHORIA: CLASSES PARA SEPARAÇÃO DE RESPONSABILIDADES
# Esta estrutura separa a lógica da API (ElabClient) da lógica de negócio
# (PlatformService), que por sua vez é separada da lógica da interface (UI).
# ==============================================================================

class ElabClient:
    """Classe responsável exclusivamente pela comunicação HTTP com a API do eLabFTW."""
    def __init__(self, base_url: str, api_key: str, verify_tls: bool, timeout: int = 30):
        if not base_url or not api_key or "SUA_CHAVE" in api_key:
            raise ValueError("URL da API ou Chave da API não foram configuradas corretamente.")
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.verify_tls = verify_tls
        self.timeout = timeout
        self.headers = {
            "Authorization": self.api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def request(self, method: str, path: str, json_body: Optional[Dict] = None, params: Optional[Dict] = None) -> Any:
        """Método genérico para fazer uma requisição."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            r = requests.request(
                method=method.upper(),
                url=url,
                headers=self.headers,
                json=json_body,
                params=params,
                timeout=self.timeout,
                verify=self.verify_tls,
            )
            r.raise_for_status()  # Lança exceção para status 4xx/5xx
            if r.content:
                # Retorna bytes se não for JSON (para o PDF)
                return r.json() if "application/json" in r.headers.get("Content-Type", "") else r.content
            return {}
        except requests.exceptions.HTTPError as e:
            # Re-lança o erro com uma mensagem mais clara
            msg = e.response.text if e.response.text else f"status={e.response.status_code}"
            raise RuntimeError(f"Erro na API ({e.response.status_code}): {msg}") from e
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Erro de conexão: {e}") from e

    @staticmethod
    def _to_list(data: Any) -> list:
        """Extrai uma lista de uma resposta da API, que pode vir em vários formatos."""
        if isinstance(data, dict):
            for k in ("items", "data", "results"):
                if isinstance(data.get(k), list):
                    return data[k]
        return data if isinstance(data, list) else []


class PlatformService:
    """
    Contém toda a LÓGICA DE NEGÓCIO. Não sabe nada sobre Streamlit (st.*).
    Ela usa um ElabClient para interagir com a API.
    """
    def __init__(self, client: ElabClient):
        self.elab = client
        # Constantes de negócio
        self.item_type_title = "Paciente"
        self.template_title = "Análise Clínica Padrão"
        self.template_body_html = TEMPLATE_BODY_HTML # Usa a constante global

    def ensure_item_type_patient(self) -> int:
        data = self.elab.request("GET", "items_types")
        for it in self.elab._to_list(data):
            if (it.get("title") or "").strip().lower() == self.item_type_title.lower():
                return int(it["id"])
        created = self.elab.request("POST", "items_types", json_body={"title": self.item_type_title})
        return int(created["id"])

    def ensure_template(self) -> int:
        data = self.elab.request("GET", "experiments/templates")
        for tpl in self.elab._to_list(data):
            if (tpl.get("title") or "").strip().lower() == self.template_title.lower():
                return int(tpl["id"])
        created = self.elab.request("POST", "experiments/templates", json_body={"title": self.template_title, "body": self.template_body_html})
        return int(created["id"])

    def register_patient(self, name: str) -> int:
        if not name.strip():
            raise ValueError("O nome do paciente não pode ser vazio.")
        item_type_id = self.ensure_item_type_patient()
        created = self.elab.request("POST", "items", json_body={"title": name.strip(), "items_type_id": item_type_id})
        item_id = created.get("id") or created.get("item_id")
        if not isinstance(item_id, int):
            raise RuntimeError("Não foi possível obter o ID do Item recém-criado.")
        return item_id

    def create_and_link_experiment(self, item_id: int, display_name: str, appointment_id: str, sample_type: str) -> Dict[str, Any]:
        self.ensure_template() # Garante que o template existe
        title = f"Análises {display_name or 'Paciente'} - {datetime.now().date().isoformat()}"
        
        # 1. Cria o experimento vazio
        exp = self.elab.request("POST", "experiments", json_body={"title": title.strip()})
        exp_id = exp.get("id")
        if not isinstance(exp_id, int):
            raise RuntimeError("Falha ao criar o esqueleto do experimento.")

        # 2. Preenche o corpo com o template
        vars_dict = {
            "agendamento_id": appointment_id, "item_paciente_id": item_id,
            "data_coleta": datetime.now().isoformat(timespec="minutes"), "tipo_amostra": sample_type
        }
        body = self.template_body_html
        for k, v in vars_dict.items():
            body = body.replace(f"{{{{{k}}}}}", str(v))
        self.elab.request("PATCH", f"experiments/{exp_id}", json_body={"body": body})

        # 3. Linka ao item do paciente
        try:
            self.elab.request("POST", f"experiments/{exp_id}/items", json_body={"item_id": item_id})
        except RuntimeError:
            self.elab.request("POST", f"experiments/{exp_id}/items_links", json_body={"item_id": item_id})

        # 4. Busca o status final
        status = self.get_experiment_status(exp_id)
        return {"id": exp_id, "status": status}

    def get_experiment_status(self, exp_id: int) -> str:
        exp = self.elab.request("GET", f"experiments/{exp_id}")
        return str(exp.get("status_name") or exp.get("status_label") or exp.get("status", "desconhecido"))

    def export_experiment_pdf(self, exp_id: int) -> bytes:
        pdf_bytes = self.elab.request("GET", f"experiments/{exp_id}/export", params={"format": "pdf"})
        if not isinstance(pdf_bytes, bytes):
            raise TypeError("A resposta da API para o PDF não era do tipo 'bytes'.")
        return pdf_bytes

# ==============================================================================
# LÓGICA DA INTERFACE (UI)
# Esta parte do código lida apenas com a apresentação e interação com o usuário.
# ==============================================================================



st.set_page_config(page_title="Plataforma Externa • eLabFTW (demo)", page_icon="🧪", layout="centered")

# Forma correta de inicializar o st.session_state
if "patients" not in st.session_state:
    st.session_state.patients = {}  # Atribuição direta, sem anotação de tipo

if "pdf_bytes" not in st.session_state:
    st.session_state.pdf_bytes = None  # Atribuição direta
    st.session_state.pdf_name = None   # Atribuição direta
    
# --- Constantes Globais de UI e Template ---
TEMPLATE_BODY_HTML = """
<h2>Dados da Amostra</h2>
<ul><li>ID Agendamento: {{agendamento_id}}</li><li>ID Paciente (Item): {{item_paciente_id}}</li><li>Data/Hora da Coleta: {{data_coleta}}</li><li>Tipo de Amostra: {{tipo_amostra}}</li></ul>
<h2>Resultados Bioquímica</h2>
<table><thead><tr><th>Analito</th><th>Resultado</th><th>Unidade</th><th>Ref.</th><th>Obs.</th></tr></thead><tbody><tr><td>Glicose</td><td></td><td>mg/dL</td><td>70–99</td><td></td></tr><tr><td>Ureia</td><td></td><td>mg/dL</td><td>10–50</td><td></td></tr></tbody></table>
<h2>Observações Técnicas</h2><p></p>
""".strip()

# --- Renderização da UI ---
st.title("🧪 Plataforma Externa • eLabFTW (demo)")

with st.sidebar:
    st.header("Configuração da API")
    elab_url = st.text_input("ELAB_URL", value="https://demo.elabftw.net/api/v2")
    api_key = st.text_input("ELAB_API_KEY", value="coloque_a_chave_da_demo_aqui", type="password")
    verify_tls = st.checkbox("Verificar certificado TLS (recomendado)", value=True)

# Instancia os serviços. A UI vai interagir com 'service'.
try:
    client = ElabClient(elab_url, api_key, verify_tls)
    service = PlatformService(client)
except ValueError as e:
    st.sidebar.error(f"Erro de configuração: {e}")
    st.stop() # Interrompe a execução se a configuração estiver errada

# Botão de Teste
if st.sidebar.button("Testar conexão"):
    with st.spinner("Testando..."):
        try:
            service.ensure_item_type_patient()
            st.sidebar.success("Conexão OK! ✅")
        except Exception as e:
            st.sidebar.error(f"Falha no acesso: {e}")

st.divider()

# 1) Inicializar
st.subheader("1) Inicializar (ItemType + Template)")
if st.button("Garantir Configurações no eLabFTW"):
    with st.spinner("Verificando e criando o que for necessário..."):
        try:
            iid = service.ensure_item_type_patient()
            st.success(f"ItemType 'Paciente' OK (id={iid})")
            tid = service.ensure_template()
            st.success(f"Template 'Análise Clínica Padrão' OK (id={tid})")
        except Exception as e:
            st.error(f"Erro: {e}")

st.divider()

# 2) Cadastrar paciente
st.subheader("2) Cadastrar paciente (cria Item)")
with st.form("form_patient"):
    name = st.text_input("Nome do paciente")
    if st.form_submit_button("Cadastrar"):
        with st.spinner(f"Cadastrando '{name}'..."):
            try:
                item_id = service.register_patient(name)
                # A UI é responsável por atualizar o estado da sessão
                st.session_state.patients[name.strip()] = item_id
                st.success(f"Paciente '{name}' cadastrado → item_id={item_id}")
            except Exception as e:
                st.error(f"Erro: {e}")

if st.session_state.patients:
    st.caption("Pacientes cadastrados nesta sessão:")
    st.table([{"Nome": n, "item_id": iid} for n, iid in st.session_state.patients.items()])

st.divider()

# 3) Marcar experimento
st.subheader("3) Marcar experimento (criar + linkar)")
with st.form("form_experiment"):
    pacientes_sessao = list(st.session_state.patients.keys())
    if pacientes_sessao:
        nome_sel = st.selectbox("Paciente (desta sessão)", pacientes_sessao)
        item_id_selecionado = st.session_state.patients[nome_sel]
        display_name = nome_sel
    else:
        st.info("Nenhum paciente na sessão. Cadastre no passo 2.")
        item_id_manual = st.text_input("Ou informe o item_id do paciente manualmente")
        item_id_selecionado = int(item_id_manual) if item_id_manual.isdigit() else None
        display_name = f"Paciente {item_id_selecionado}" if item_id_selecionado else ""

    agendamento_id = st.text_input("ID do agendamento (da sua plataforma)")
    tipo_amostra = st.text_input("Tipo de amostra", value="Sangue")

    if st.form_submit_button("Criar experimento"):
        if not item_id_selecionado or not agendamento_id.strip():
            st.warning("É necessário um paciente e um ID de agendamento.")
        else:
            with st.spinner("Criando e vinculando experimento..."):
                try:
                    result = service.create_and_link_experiment(
                        item_id_selecionado, display_name, agendamento_id, tipo_amostra
                    )
                    st.success(f"Experimento criado e linkado! ID: {result['id']} | Status: {result['status']}")
                except Exception as e:
                    st.error(f"Erro: {e}")

st.divider()

# 4) Ver status
st.subheader("4) Ver status do experimento")
exp_id_status = st.text_input("ID do experimento para consultar")
if st.button("Consultar status"):
    if exp_id_status.isdigit():
        with st.spinner("Consultando..."):
            try:
                status = service.get_experiment_status(int(exp_id_status))
                st.success(f"Status do experimento {exp_id_status}: **{status}**")
            except Exception as e:
                st.error(f"Erro: {e}")
    else:
        st.warning("Informe um ID de experimento válido.")

st.divider()

# 5) Baixar PDF
st.subheader("5) Baixar PDF do experimento")
exp_id_pdf = st.text_input("ID do experimento para gerar PDF")
if st.button("Gerar e preparar download do PDF"):
    if exp_id_pdf.isdigit():
        with st.spinner("Gerando PDF no servidor do eLabFTW..."):
            try:
                pdf_bytes = service.export_experiment_pdf(int(exp_id_pdf))
                st.session_state.pdf_bytes = pdf_bytes
                st.session_state.pdf_name = f"experimento_{exp_id_pdf}.pdf"
                st.success("PDF pronto! Use o botão de download abaixo.")
            except Exception as e:
                st.error(f"Erro ao gerar PDF: {e}")
    else:
        st.warning("Informe um ID de experimento válido.")

if st.session_state.get("pdf_bytes"):
    st.download_button(
        label="⬇️ Baixar PDF",
        data=st.session_state.pdf_bytes,
        file_name=st.session_state.pdf_name,
        mime="application/pdf"
    )

# LINHA FALTANTE ADICIONADA AQUI
st.caption("Dica: esta demo não usa banco; a lista de pacientes é somente desta sessão.")
