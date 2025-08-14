# Plataforma de Integração com eLabFTW

Este projeto é uma aplicação que integra uma interface de usuário construída com **Streamlit** e um backend em **FastAPI** para interagir com a API do eLabFTW. Ele permite gerenciar pacientes, criar experimentos e gerar relatórios em PDF.

## Estrutura do Projeto

```
.
├── .gitignore
├── readme.md
├── requirements.txt
├── src/
│   ├── backend/
│   │   ├── elab_service.py
│   │   ├── main.py
│   └── frontend/
│       └── app.py
```

### Principais Componentes

- **Frontend**: Interface de usuário construída com Streamlit (`src/frontend/app.py`).
- **Backend**: API construída com FastAPI para interagir com o eLabFTW (`src/backend/main.py`).
- **Serviço de Negócio**: Lógica de integração com a API do eLabFTW (`src/backend/elab_service.py`).

## Requisitos

- Python 3.10 ou superior
- Dependências listadas no arquivo `requirements.txt`

## Instalação

1. Clone o repositório:
   ```bash
   git clone https://github.com/marcosdidier/projetoIESI
   cd projetoIESI
   ```

2. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

## Uso

### Executar o Backend

1. Inicie o backend com FastAPI:
   ```bash
   uvicorn src.backend.main:app --host 127.0.0.1 --port 8000
   ```

2. Acesse a documentação interativa da API em: [http://localhost:8000/docs](http://localhost:8000/docs).
3. 
### Executar o Frontend

1. Inicie o frontend com Streamlit:
   ```bash
   cd src/frontend
   streamlit run app.py
   ```

2. Acesse a interface no navegador em: [http://localhost:8501](http://localhost:8501).

## Funcionalidades

### Frontend (Streamlit)

- **Configuração da API**: Permite configurar a URL e a chave de API do eLabFTW.
- **Cadastro de Pacientes**: Cria itens no eLabFTW representando pacientes.
- **Criação de Experimentos**: Gera experimentos vinculados a pacientes e preenche templates automaticamente.
- **Consulta de Status**: Verifica o status de experimentos criados.
- **Download de PDFs**: Exporta relatórios de experimentos em formato PDF.

### Backend (FastAPI)

- **Testar Conexão**: Verifica a conectividade com a API do eLabFTW.
- **Inicializar Ambiente**: Garante que o tipo de item e o template padrão existam no eLabFTW.
- **Gerenciar Pacientes**: Registra pacientes no eLabFTW.
- **Gerenciar Experimentos**: Cria e vincula experimentos a pacientes.
- **Exportar PDFs**: Gera relatórios de experimentos em formato PDF.

## Configuração

### Variáveis de Configuração

- **.env**: Criar um arquivo .env com a URL do elab e a chave de API.
   - **ELAB_URL**: URL base da API do eLabFTW.
   - **ELAB_API_KEY**: Chave de API gerada no perfil do usuário no eLabFTW.

## Contribuição

1. Faça um fork do repositório.
2. Crie uma branch para sua feature:
   ```bash
   git checkout -b minha-feature
   ```
3. Faça commit das suas alterações:
   ```bash
   git commit -m "Minha nova feature"
   ```
4. Envie para o repositório remoto:
   ```bash
   git push origin minha-feature
   ```
5. Abra um Pull Request.

## Licença

Este projeto está licenciado sob a [MIT License](LICENSE).


