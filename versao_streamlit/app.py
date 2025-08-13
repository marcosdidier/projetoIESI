import json
from datetime import datetime
from typing import Any, Dict, Optional

import requests
import streamlit as st

# =========================
# Configs padrão (edite se quiser defaults)
# =========================
DEFAULT_ELAB_URL = "https://SEU_ELN/api/v2"
DEFAULT_API_KEY = "SUA_CHAVE_API_AQUI"
DEFAULT_VERIFY_TLS = True

TIMEOUT = 30  # seg por requisição

ITEM_TYPE_TITLE = "Paciente"
TEMPLATE_TITLE  = "Análise Clínica Padrão"

TEMPLATE_BODY_HTML = """
<h2>Dados da Amostra</h2>
<ul>
  <li>ID Agendamento: {{agendamento_id}}</li>
  <li>ID Paciente (Item): {{item_paciente_id}}</li>
  <li>Data/Hora da Coleta: {{data_coleta}}</li>
  <li>Tipo de Amostra: {{tipo_amostra}}</li>
</ul>
<h2>Resultados Bioquímica</h2>
<table>
<thead><tr><th>Analito</th><th>Resultado</th><th>Unidade</th><th>Ref.</th><th>Obs.</th></tr></thead>
<tbody>
<tr><td>Glicose</td><td></td><td>mg/dL</td><td>70–99</td><td></td></tr>
<tr><td>Ureia</td><td></td><td>mg/dL</td><td>10–50</td><td></td></tr>
<tr><td>Creatinina</td><td></td><td>mg/dL</td><td>0.7–1.3</td><td></td></tr>
</tbody>
</table>
<h2>Resultados Hematologia</h2>
<table>
<thead><tr><th>Parâmetro</th><th>Resultado</th><th>Unidade</th><th>Ref.</th><th>Obs.</th></tr></thead>
<tbody>
<tr><td>Hemoglobina</td><td></td><td>g/dL</td><td>13.0–17.0</td><td></td></tr>
<tr><td>Hematócrito</td><td></td><td>%</td><td>40–52</td><td></td></tr>
<tr><td>Plaquetas</td><td></td><td>x10^3/µL</td><td>150–450</td><td></td></tr>
</tbody>
</table>
<h2>Observações Técnicas</h2><p></p>
<h2>Conclusão</h2><p></p>
<h2>Anexos</h2><p>Faça upload do PDF do laudo no experimento (Uploads).</p>
""".strip()

# =========================
# Estado em memória
# =========================
if "patients" not in st.session_state:
    st.session_state.patients: Dict[str, int] = {}  # nome -> item_id
if "pdf_bytes" not in st.session_state:
    st.session_state.pdf_bytes: Optional[bytes] = None
if "pdf_name" not in st.session_state:
    st.session_state.pdf_name: Optional[str] = None

# =========================
# Helpers HTTP
# =========================
def _url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"

def _req(base: str, api_key: str, verify_tls: bool, method: str, path: str,
         json_body: Optional[Dict]=None, params: Optional[Dict]=None) -> Any:
    headers = {
        "Authorization": api_key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    r = requests.request(
        method=method.upper(),
        url=_url(base, path),
        headers=headers,
        json=json_body,
        params=params,
        timeout=TIMEOUT,
        verify=verify_tls,
    )
    if r.status_code not in (200, 201, 204):
        # mensagem curta e direta
        msg = r.text if r.text else f"status={r.status_code}"
        if len(msg) > 600:  # corta logs muito longos
            msg = msg[:600] + "... (truncado)"
        raise RuntimeError(f"{method.upper()} {path} -> {r.status_code}: {msg}")
    if r.content:
        try:
            return r.json()
        except Exception:
            return r.content  # para PDF/bytes
    return {}

def GET(base, key, verify, path, params=None):  return _req(base, key, verify, "GET", path, params=params)
def POST(base, key, verify, path, body=None):   return _req(base, key, verify, "POST", path, json_body=body or {})
def PATCH(base, key, verify, path, body=None):  return _req(base, key, verify, "PATCH", path, json_body=body or {})

def _to_list(data: Any) -> list:
    if isinstance(data, dict):
        for k in ("items", "data", "results"):
            if isinstance(data.get(k), list):
                return data[k]
        return []
    return data if isinstance(data, list) else []

# =========================
# Operações de negócio
# =========================
def ensure_item_type_patient(base: str, key: str, verify: bool) -> int:
    data = GET(base, key, verify, "items_types")
    entries = _to_list(data)
    for it in entries:
        if (it.get("title") or "").strip().lower() == ITEM_TYPE_TITLE.lower():
            return int(it["id"])
    created = POST(base, key, verify, "items_types",
                   {"title": ITEM_TYPE_TITLE, "body": "Tipo para cadastro de Pacientes/Pesquisadores."})
    return int(created["id"])

def ensure_template(base: str, key: str, verify: bool) -> int:
    data = GET(base, key, verify, "experiments/templates")
    entries = _to_list(data)
    for tpl in entries:
        if (tpl.get("title") or "").strip().lower() == TEMPLATE_TITLE.lower():
            return int(tpl["id"])
    created = POST(base, key, verify, "experiments/templates",
                   {"title": TEMPLATE_TITLE, "body": TEMPLATE_BODY_HTML})
    return int(created["id"])

def register_patient(base: str, key: str, verify: bool, name: str) -> int:
    if not name.strip():
        raise ValueError("Nome do paciente vazio.")
    items_type_id = ensure_item_type_patient(base, key, verify)
    created = POST(base, key, verify, "items", {"title": name.strip(), "items_type_id": items_type_id})
    item_id = created.get("id") or created.get("item_id")
    if not isinstance(item_id, int):
        # fallback leve: busca últimos itens
        recent = GET(base, key, verify, "items", params={"limit": 10, "order": "desc"})
        for it in _to_list(recent):
            if (it.get("title") or "").strip() == name.strip():
                item_id = it.get("id")
                break
    if not isinstance(item_id, int):
        raise RuntimeError("Não consegui obter o item_id recém-criado.")
    st.session_state.patients[name.strip()] = int(item_id)
    return int(item_id)

def create_experiment(base: str, key: str, verify: bool, title: str, vars_dict: Dict[str, Any]) -> int:
    if not title.strip():
        raise ValueError("Título do experimento vazio.")
    exp = POST(base, key, verify, "experiments", {"title": title.strip()})
    exp_id = exp.get("id")
    if not isinstance(exp_id, int):
        raise RuntimeError("Falha ao criar experimento.")

    body = TEMPLATE_BODY_HTML
    for k, v in (vars_dict or {}).items():
        body = body.replace(f"{{{{{k}}}}}", str(v))
    PATCH(base, key, verify, f"experiments/{exp_id}", {"title": title.strip(), "body": body})
    return int(exp_id)

def link_experiment_to_item(base: str, key: str, verify: bool, exp_id: int, item_id: int):
    try:
        POST(base, key, verify, f"experiments/{exp_id}/items", {"item_id": item_id})
    except Exception:
        POST(base, key, verify, f"experiments/{exp_id}/items_links", {"item_id": item_id})

def get_status(base: str, key: str, verify: bool, exp_id: int) -> str:
    exp = GET(base, key, verify, f"experiments/{exp_id}")
    return str(exp.get("status_name") or exp.get("status_label") or exp.get("status", "desconhecido"))

def export_pdf(base: str, key: str, verify: bool, exp_id: int) -> bytes:
    # usa a versão "crua" do _req que retorna bytes
    return _req(base, key, verify, "GET", f"experiments/{exp_id}/export", params={"format": "pdf"})

# =========================
# UI
# =========================
st.set_page_config(page_title="Plataforma Externa • eLabFTW (demo)", page_icon="🧪", layout="centered")
st.title("🧪 Plataforma Externa • eLabFTW (demo)")

with st.sidebar:
    st.header("Configuração da API")
    elab_url = st.text_input("ELAB_URL", value=DEFAULT_ELAB_URL, help="Ex.: https://eln.seudominio.org/api/v2")
    api_key  = st.text_input("ELAB_API_KEY", value=DEFAULT_API_KEY, type="password")
    verify_tls = st.checkbox("Verificar certificado TLS (recomendado)", value=DEFAULT_VERIFY_TLS)
    if st.button("Testar conexão"):
        try:
            GET(elab_url, api_key, verify_tls, "items_types")
            st.success("Consegui acessar a API com essa chave. ✅")
        except Exception as e:
            st.error(f"Falha no acesso: {e}")

st.divider()

# 1) Inicializar (Passo 2)
st.subheader("1) Inicializar (ItemType + Template)")
col1, col2 = st.columns(2)
with col1:
    if st.button("Garantir ItemType 'Paciente'"):
        try:
            iid = ensure_item_type_patient(elab_url, api_key, verify_tls)
            st.success(f"ItemType 'Paciente' OK (id={iid})")
        except Exception as e:
            st.error(f"Erro: {e}")
with col2:
    if st.button("Garantir Template 'Análise Clínica Padrão'"):
        try:
            tid = ensure_template(elab_url, api_key, verify_tls)
            st.success(f"Template OK (id={tid})")
        except Exception as e:
            st.error(f"Erro: {e}")

st.divider()

# 2) Cadastrar paciente (Item)
st.subheader("2) Cadastrar paciente (cria Item)")
with st.form("form_patient"):
    name = st.text_input("Nome do paciente")
    ok = st.form_submit_button("Cadastrar")
    if ok:
        try:
            item_id = register_patient(elab_url, api_key, verify_tls, name)
            st.success(f"Paciente '{name}' cadastrado → item_id={item_id}")
        except Exception as e:
            st.error(f"Erro: {e}")

if st.session_state.patients:
    st.caption("Pacientes cadastrados nesta sessão:")
    st.table([{"Nome": n, "item_id": iid} for n, iid in st.session_state.patients.items()])

st.divider()

# 3) Marcar experimento (criar + linkar)
st.subheader("3) Marcar experimento (criar + linkar)")
with st.form("form_experiment"):
    src = st.radio("Selecione a origem do paciente", ["Escolher pelo nome (desta sessão)", "Informar item_id manualmente"])
    selected_item_id = None
    display_name = ""
    if src == "Escolher pelo nome (desta sessão)":
        options = list(st.session_state.patients.keys())
        if options:
            nome_sel = st.selectbox("Paciente", options)
            if nome_sel:
                selected_item_id = st.session_state.patients[nome_sel]
                display_name = nome_sel
        else:
            st.info("Nenhum paciente na sessão. Cadastre no passo 2 ou use item_id manual.")
    else:
        manual_id = st.text_input("item_id do paciente")
        if manual_id.strip().isdigit():
            selected_item_id = int(manual_id.strip())
            display_name = st.text_input("Nome (apenas para o título)", value=f"Paciente {selected_item_id}")
        else:
            display_name = st.text_input("Nome (apenas para o título)")

    agendamento_id = st.text_input("ID do agendamento")
    tipo_amostra   = st.text_input("Tipo de amostra", value="Sangue")
    submit_exp = st.form_submit_button("Criar experimento")

    if submit_exp:
        if not selected_item_id:
            st.error("Informe um paciente (por nome desta sessão ou item_id).")
        elif not agendamento_id.strip():
            st.error("Informe o ID do agendamento.")
        else:
            try:
                ensure_template(elab_url, api_key, verify_tls)
                titulo = f"Análises {display_name or 'Paciente'} - {datetime.now().date().isoformat()}"
                exp_id = create_experiment(
                    elab_url, api_key, verify_tls, titulo,
                    {
                        "agendamento_id": agendamento_id.strip(),
                        "item_paciente_id": selected_item_id,
                        "data_coleta": datetime.now().isoformat(timespec="minutes"),
                        "tipo_amostra": tipo_amostra.strip() or "Sangue",
                    }
                )
                link_experiment_to_item(elab_url, api_key, verify_tls, exp_id, selected_item_id)
                status = get_status(elab_url, api_key, verify_tls, exp_id)
                st.success(f"Experimento criado e linkado! id={exp_id} | status: {status}")
            except Exception as e:
                st.error(f"Erro: {e}")

st.divider()

# 4) Ver status
st.subheader("4) Ver status do experimento")
with st.form("form_status"):
    exp_id_status = st.text_input("ID do experimento")
    go_status = st.form_submit_button("Consultar status")
    if go_status:
        if not exp_id_status.strip().isdigit():
            st.error("ID inválido.")
        else:
            try:
                s = get_status(elab_url, api_key, verify_tls, int(exp_id_status.strip()))
                st.success(f"Status: {s}")
            except Exception as e:
                st.error(f"Erro: {e}")

st.divider()

# 5) Baixar PDF
st.subheader("5) Baixar PDF do experimento")
with st.form("form_pdf"):
    exp_id_pdf = st.text_input("ID do experimento (PDF)")
    go_pdf = st.form_submit_button("Gerar e preparar download")
    if go_pdf:
        if not exp_id_pdf.strip().isdigit():
            st.error("ID inválido.")
        else:
            try:
                pdf_bytes = export_pdf(elab_url, api_key, verify_tls, int(exp_id_pdf.strip()))
                st.session_state.pdf_bytes = pdf_bytes if isinstance(pdf_bytes, bytes) else bytes(pdf_bytes)
                st.session_state.pdf_name = f"experiment_{exp_id_pdf.strip()}.pdf"
                st.success("PDF pronto para download abaixo.")
            except Exception as e:
                st.error(f"Erro: {e}")

if st.session_state.pdf_bytes and st.session_state.pdf_name:
    st.download_button(
        label="⬇️ Baixar PDF",
        data=st.session_state.pdf_bytes,
        file_name=st.session_state.pdf_name,
        mime="application/pdf"
    )

st.caption("Dica: esta demo não usa banco; a lista de pacientes é somente desta sessão.")
