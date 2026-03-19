from flask import Flask, request, jsonify, send_from_directory
import json
import os
import requests
import base64
from functools import wraps
from datetime import datetime, date

app = Flask(__name__, static_folder='.', template_folder='.')

# =======================================================
# CONFIGURAÇÃO DE SEGURANÇA E TOKENS
# =======================================================

# Token para acesso interno ao painel
VALID_TOKEN = "KLORD-TESTE-1234567890ABCDEF" 

# Token usado para autenticar nas APIs externas de consulta
ADM_TOKEN_EXTERNAL = "admkl0rd" 

# Token secreto para acessar as rotas de gerenciamento de usuários
ADMIN_MANAGER_TOKEN = "Kl0rd777" 
ADMIN_ROUTE = f"/adm/{ADMIN_MANAGER_TOKEN}"

# =======================================================
# CONFIGURAÇÃO DO GITHUB (NOVO)
# =======================================================
GITHUB_TOKEN = "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"
GITHUB_REPO = "klordTV/klTV"
GITHUB_FILE_PATH = "database.json"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"

# =======================================================
# FUNÇÕES GITHUB API (NOVAS)
# =======================================================

def get_github_file():
    """Busca o database.json do GitHub."""
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    try:
        response = requests.get(GITHUB_API_URL, headers=headers, timeout=30)

        if response.status_code == 404:
            return {"logins": []}, None, None

        if response.status_code == 200:
            data = response.json()
            content_base64 = data.get("content", "")
            sha = data.get("sha")

            content_decoded = base64.b64decode(content_base64).decode('utf-8')
            content_json = json.loads(content_decoded)

            return content_json, sha, None
        else:
            return None, None, f"Erro GitHub API: {response.status_code}"

    except Exception as e:
        return None, None, f"Erro: {str(e)}"


def update_github_file(content_dict, sha, commit_message="Atualização"):
    """Atualiza o database.json no GitHub."""
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    content_json = json.dumps(content_dict, indent=4, ensure_ascii=False)
    content_base64 = base64.b64encode(content_json.encode('utf-8')).decode('utf-8')

    payload = {
        "message": commit_message,
        "content": content_base64,
        "sha": sha
    }

    if sha is None:
        del payload["sha"]

    try:
        response = requests.put(GITHUB_API_URL, headers=headers, json=payload, timeout=30)
        return response.status_code in [200, 201], None
    except Exception as e:
        return False, str(e)


def carregar_logins():
    """Carrega os logins do GitHub."""
    content, sha, error = get_github_file()

    if error:
        # Fallback: tenta arquivo local
        if os.path.exists("database.json"):
            try:
                with open("database.json", "r") as f:
                    return json.load(f).get("logins", [])
            except:
                return []
        return []

    return content.get("logins", [])


def salvar_logins(logins_list):
    """Salva no GitHub."""
    content, sha, error = get_github_file()

    new_content = {"logins": logins_list}

    success, error = update_github_file(
        new_content, 
        sha, 
        f"Update users - {datetime.now().strftime('%d/%m %H:%M')}"
    )

    if success:
        # Backup local
        try:
            with open("database.json", "w") as f:
                json.dump(new_content, f, indent=4)
        except:
            pass
        return True
    return False


def check_expiration(user_data):
    """Verifica expiração da conta."""
    expiracao_str = user_data.get("expiracao")
    if not expiracao_str:
        return "ATIVO"

    try:
        expiracao_date = datetime.strptime(expiracao_str, '%Y-%m-%d').date()
        today = date.today()

        if expiracao_date < today:
            return "EXPIRADO"
        else:
            return "ATIVO"
    except ValueError:
        return "ERRO"


# =======================================================
# DECORATOR E PROXY
# =======================================================

def token_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function


def proxy_consulta(api_url, dado, requires_token_external=False, token_key='token'):
    TIMEOUT_SECONDS = 60 
    url = f"{api_url}{dado}"

    if requires_token_external:
        sep = '&' if '?' in url else '?'
        url += f"{sep}{token_key}={ADM_TOKEN_EXTERNAL}"

    try:
        response = requests.get(url, timeout=TIMEOUT_SECONDS)

        if response.ok:
            try:
                return response.json()
            except:
                return {"erro": "Resposta não-JSON", "detalhes": response.text}
        else:
            try:
                return {"erro": f"HTTP {response.status_code}", "detalhes": response.json()}
            except:
                return {"erro": f"HTTP {response.status_code}", "detalhes": response.text}

    except requests.exceptions.Timeout:
        return {"erro": "Timeout"}
    except Exception as e:
        return {"erro": f"Erro: {str(e)}"}


# =======================================================
# ROTAS PRINCIPAIS
# =======================================================

@app.route('/')
def home():
    return send_from_directory('.', 'login.html') 

@app.route('/painel')
def painel():
    return send_from_directory('.', 'index.html')

@app.route('/consulta')
def consulta():
    return send_from_directory('.', 'consulta.html')


# =======================================================
# ROTA DE LOGIN
# =======================================================

@app.route('/api/login', methods=['POST'])
def api_login():
    dados = request.get_json()
    usuario = dados.get("usuario")
    senha = dados.get("senha")
    logins = carregar_logins()

    for login in logins:
        if login.get("usuario") == usuario and login.get("senha") == senha:
            status = check_expiration(login)

            if status == "EXPIRADO":
                 return jsonify({"ok": False, "erro": "Conta expirada"}), 403
            if status == "ERRO":
                 return jsonify({"ok": False, "erro": "Erro data expiração"}), 500

            return jsonify({"ok": True, "mensagem": "Login OK"})

    return jsonify({"ok": False, "erro": "Usuário ou senha inválidos"}), 401


# =======================================================
# ROTA DE ADMINISTRAÇÃO
# =======================================================

@app.route(ADMIN_ROUTE, methods=['GET', 'POST'])
def admin_manager():

    if request.method == 'POST':
        try:
            dados = request.get_json()
        except:
            return jsonify({"ok": False, "erro": "JSON inválido"}), 400

        acao = dados.get('acao')
        usuario = dados.get('usuario')
        logins = carregar_logins()

        if not usuario:
            return jsonify({"ok": False, "erro": "Usuário obrigatório"}), 400

        if acao == 'cadastrar':
            senha = dados.get('senha')
            expiracao = dados.get('expiracao') or None
            nome_completo = dados.get('nome_completo') or None
            email = dados.get('email') or None
            tipo = dados.get('tipo') or 'user'

            if not senha:
                 return jsonify({"ok": False, "erro": "Senha obrigatória"}), 400

            if any(login.get("usuario") == usuario for login in logins):
                 return jsonify({"ok": False, "erro": f"Usuário '{usuario}' já existe"}), 409

            novo_login = {
                "usuario": usuario, 
                "senha": senha,
                "expiracao": expiracao,
                "nome_completo": nome_completo,
                "email": email,
                "tipo": tipo
            }
            logins.append(novo_login)

            if salvar_logins(logins):
                return jsonify({"ok": True, "mensagem": f"Usuário '{usuario}' salvo no GitHub!"})
            else:
                return jsonify({"ok": False, "erro": "Falha ao salvar no GitHub"}), 500

        elif acao == 'deletar':
            logins_filtrados = [login for login in logins if login.get("usuario") != usuario]

            if len(logins) == len(logins_filtrados):
                return jsonify({"ok": False, "erro": f"Usuário '{usuario}' não encontrado"}), 404

            if salvar_logins(logins_filtrados):
                return jsonify({"ok": True, "mensagem": f"Usuário '{usuario}' deletado!"})
            else:
                return jsonify({"ok": False, "erro": "Falha ao deletar no GitHub"}), 500

        else:
            return jsonify({"ok": False, "erro": "Ação inválida"}), 400

    elif request.args.get('data') == 'json':
        logins = carregar_logins()

        users_with_status = []
        for user in logins:
            status = check_expiration(user)
            user_data = user.copy()
            user_data["status"] = status
            user_data["expiracao"] = user_data.get("expiracao") or 'NUNCA'
            user_data.pop("senha", None)
            users_with_status.append(user_data)

        return jsonify(users_with_status)

    else:
        # HTML do painel admin
        html_content = f"""
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Admin - Klord Buscas</title>
            <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
            <style>
                :root {{
                    --cor-fundo: #0c0c14; 
                    --cor-card-fundo: #1a1a2e; 
                    --cor-borda: #3a3a5e; 
                    --cor-primaria: #7f00ff; 
                    --cor-secundaria-acao: #a259ff; 
                    --cor-gradiente-btn: linear-gradient(135deg, #7f00ff 0%, #a259ff 100%);
                    --cor-texto-principal: #e0e0e0;
                    --cor-texto-secundaria: #9e9e9e;
                    --cor-sucesso: #4caf50;
                    --cor-erro: #f44336;
                    --radius-borda: 16px;
                    --shadow: 0 8px 20px rgba(0, 0, 0, 0.5);
                }}
                body {{ font-family: 'Inter', sans-serif; background-color: var(--cor-fundo); color: var(--cor-texto-principal); margin: 0; padding: 30px; min-height: 100vh; }}
                .container {{ max-width: 1200px; margin: 0 auto; }}
                .back-link {{ color: #a259ff; text-decoration: none; margin-bottom: 25px; display: inline-block; font-size: 1rem; font-weight: 600; }}
                .user-management-card {{ background: var(--cor-card-fundo); padding: 30px; border-radius: var(--radius-borda); box-shadow: var(--shadow); border: 1px solid var(--cor-borda); }}
                .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; }}
                .card-header h2 {{ font-size: 1.5rem; font-weight: 600; margin: 0; }}
                .btn-new-user {{ padding: 12px 20px; background: var(--cor-gradiente-btn); color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 1rem; font-weight: 600; transition: opacity 0.2s; box-shadow: 0 4px 10px rgba(127, 0, 255, 0.4); }}
                .btn-new-user:hover {{ opacity: 0.9; }}
                .user-table {{ width: 100%; border-collapse: collapse; text-align: left; }}
                .user-table th {{ font-size: 0.85rem; font-weight: 600; color: var(--cor-texto-secundaria); padding: 15px 10px; border-bottom: 1px solid var(--cor-borda); text-transform: uppercase; }}
                .user-table td {{ font-size: 0.95rem; padding: 15px 10px; border-bottom: 1px solid #1f1f3a; color: var(--cor-texto-principal); }}
                .user-table tbody tr:hover {{ background-color: #151525; }}
                .tag {{ padding: 4px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; text-transform: capitalize; }}
                .tag-owner {{ background-color: #8800ff; color: white; }}
                .tag-user {{ background-color: #007bff; color: white; }}
                .tag-admin {{ background-color: #ff9800; color: #333; }}
                .tag-ativo {{ background-color: var(--cor-sucesso); color: white; }}
                .tag-expirado {{ background-color: var(--cor-erro); color: white; }}
                .btn-delete {{ background-color: var(--cor-erro); color: white; padding: 8px 15px; border: none; border-radius: 6px; cursor: pointer; font-size: 0.9rem; }}
                .modal {{ display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; overflow: auto; background-color: rgba(0,0,0,0.7); }}
                .modal-content {{ background: var(--cor-card-fundo); margin: 10% auto; padding: 30px; border-radius: var(--radius-borda); width: 90%; max-width: 500px; box-shadow: var(--shadow); border: 1px solid var(--cor-borda); position: relative; }}
                .modal-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; border-bottom: 1px solid var(--cor-borda); padding-bottom: 15px; }}
                .modal-header h3 {{ font-size: 1.5rem; margin: 0; color: var(--cor-secundaria-acao); }}
                .modal-close {{ color: var(--cor-texto-secundaria); font-size: 1.5rem; font-weight: bold; cursor: pointer; }}
                .modal-form-group {{ margin-bottom: 18px; }}
                .modal-form-group label {{ display: block; font-weight: 600; margin-bottom: 5px; color: var(--cor-texto-principal); font-size: 0.95rem; }}
                .modal-form-group input, .modal-form-group select {{ width: 100%; padding: 12px; background-color: #111122; color: var(--cor-texto-principal); border: 1px solid var(--cor-borda); border-radius: 8px; font-size: 1rem; box-sizing: border-box; }}
                .modal-form-group input:focus, .modal-form-group select:focus {{ outline: none; border-color: var(--cor-secundaria-acao); }}
                .modal-footer {{ display: flex; justify-content: flex-end; gap: 15px; margin-top: 25px; padding-top: 15px; border-top: 1px solid var(--cor-borda); }}
                .btn-salvar {{ background: var(--cor-gradiente-btn); color: white; padding: 10px 20px; border-radius: 8px; border: none; font-weight: 600; cursor: pointer; }}
                .btn-cancelar {{ background: transparent; color: var(--cor-texto-secundaria); padding: 10px 20px; border-radius: 8px; border: 1px solid var(--cor-borda); font-weight: 600; cursor: pointer; }}
                .github-status {{ display: inline-block; padding: 5px 10px; border-radius: 4px; font-size: 0.8rem; margin-left: 10px; }}
                .github-online {{ background-color: var(--cor-sucesso); color: white; }}
                .github-offline {{ background-color: var(--cor-erro); color: white; }}
            </style>
        </head>
        <body onload="fetchUsersAndRenderTable()">
            <div class="container">
                <a href="/" class="back-link">&lt; Voltar para Login</a>

                <div class="user-management-card">
                    <div class="card-header">
                        <div>
                            <h2>Gerenciamento de Usuários</h2>
                            <span id="githubStatus" class="github-status github-offline">GitHub: Conectando...</span>
                        </div>
                        <button class="btn-new-user" onclick="openModal()"><i class="fas fa-plus"></i> Novo Usuário</button>
                    </div>

                    <div style="overflow-x: auto;">
                        <table class="user-table">
                            <thead>
                                <tr>
                                    <th>Usuário</th>
                                    <th>Nome Completo</th>
                                    <th>Email</th>
                                    <th>Tipo</th>
                                    <th>Status</th>
                                    <th>Expiração</th>
                                    <th>Ações</th>
                                </tr>
                            </thead>
                            <tbody id="userTableBody">
                            </tbody>
                        </table>
                        <p id="loadingMsg" style="text-align: center; margin-top: 20px; color: var(--cor-texto-secundaria);">Carregando usuários...</p>
                    </div>
                </div>
            </div>

            <div id="userModal" class="modal">
                <div class="modal-content">
                    <div class="modal-header">
                        <h3>Novo Usuário</h3>
                        <span class="modal-close" onclick="closeModal()">&times;</span>
                    </div>
                    <form id="newUserForm">
                        <div class="modal-form-group">
                            <label for="username">Nome de Usuário *</label>
                            <input type="text" id="username" placeholder="Digite o nome de usuário" required>
                        </div>
                        <div class="modal-form-group">
                            <label for="password">Senha *</label>
                            <input type="password" id="password" placeholder="Digite a senha" required>
                        </div>
                        <div class="modal-form-group">
                            <label for="expiry">Data de Expiração (YYYY-MM-DD)</label>
                            <input type="date" id="expiry">
                            <p style="font-size: 0.8rem; color: var(--cor-texto-secundaria); margin: 5px 0 0 0;">Deixe em branco para acesso sem expiração</p>
                        </div>
                        <div class="modal-form-group">
                            <label for="fullname">Nome Completo</label>
                            <input type="text" id="fullname" placeholder="Digite o nome completo">
                        </div>
                        <div class="modal-form-group">
                            <label for="email">Email</label>
                            <input type="email" id="email" placeholder="Digite o email">
                        </div>
                        <div class="modal-form-group">
                            <label for="userType">Tipo de Usuário</label>
                            <select id="userType">
                                <option value="user">Usuário</option>
                                <option value="owner">Owner</option>
                                <option value="admin">Administrador</option>
                            </select>
                        </div>

                        <div class="modal-footer">
                            <button type="button" class="btn-cancelar" onclick="closeModal()">Cancelar</button>
                            <button type="submit" class="btn-salvar">Salvar no GitHub</button>
                        </div>
                    </form>
                    <p id="modalMsg" style="margin-top: 15px; text-align: center; font-weight: 600;"></p>
                </div>
            </div>

            <script>
                const ADMIN_API_URL = '{ADMIN_ROUTE}';
                const tableBody = document.getElementById('userTableBody');
                const loadingMsg = document.getElementById('loadingMsg');
                const githubStatus = document.getElementById('githubStatus');

                function setMsg(elementId, text, isSuccess) {{
                    const msg = document.getElementById(elementId);
                    msg.textContent = text;
                    msg.style.color = isSuccess ? 'var(--cor-sucesso)' : 'var(--cor-erro)';
                }}

                async function fetchUsersAndRenderTable() {{
                    loadingMsg.style.display = 'block';
                    tableBody.innerHTML = '';

                    try {{
                        const response = await fetch(ADMIN_API_URL + '?data=json', {{ method: 'GET' }});
                        const users = await response.json();

                        if (!Array.isArray(users)) {{
                            throw new Error("Resposta inválida");
                        }}

                        githubStatus.textContent = 'GitHub: Online';
                        githubStatus.className = 'github-status github-online';

                        if (users.length === 0) {{
                            tableBody.innerHTML = '<tr><td colspan="7" style="text-align: center;">Nenhum usuário cadastrado.</td></tr>';
                        }} else {{
                            users.forEach(user => {{
                                const statusClass = user.status === 'ATIVO' ? 'tag-ativo' : 
                                                    user.status === 'EXPIRADO' ? 'tag-expirado' : 'tag-erro';
                                const typeClass = user.tipo === 'owner' ? 'tag-owner' : user.tipo === 'admin' ? 'tag-admin' : 'tag-user';
                                const expiryDisplay = user.expiracao === "" || user.expiracao === null || user.expiracao === 'NUNCA' ? 'NUNCA' : user.expiracao;

                                const row = `
                                    <tr>
                                        <td>${{user.usuario}}</td>
                                        <td>${{user.nome_completo || 'N/A'}}</td>
                                        <td>${{user.email || 'N/A'}}</td>
                                        <td><span class="tag ${{typeClass}}">${{user.tipo}}</span></td>
                                        <td><span class="tag ${{statusClass}}">${{user.status}}</span></td>
                                        <td>${{expiryDisplay}}</td>
                                        <td>
                                            <button class="btn-delete" onclick="deletar('${{user.usuario}}')">
                                                <i class="fas fa-trash"></i> Deletar
                                            </button>
                                        </td>
                                    </tr>
                                `;
                                tableBody.innerHTML += row;
                            }});
                        }}
                    }} catch (error) {{
                        console.error('Erro:', error);
                        githubStatus.textContent = 'GitHub: Offline';
                        githubStatus.className = 'github-status github-offline';
                        tableBody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--cor-erro);">Erro ao carregar dados.</td></tr>';
                    }} finally {{
                        loadingMsg.style.display = 'none';
                    }}
                }}

                document.getElementById('newUserForm').addEventListener('submit', async function(event) {{
                    event.preventDefault();
                    const form = event.target;
                    setMsg('modalMsg', 'Salvando no GitHub...', false);

                    if(form.password.value.trim() === "") {{
                        setMsg('modalMsg', 'A senha é obrigatória.', false);
                        return;
                    }}

                    const userData = {{
                        acao: 'cadastrar',
                        usuario: form.username.value,
                        senha: form.password.value,
                        expiracao: form.expiry.value || null,
                        nome_completo: form.fullname.value || null,
                        email: form.email.value || null,
                        tipo: form.userType.value
                    }};

                    try {{
                        const response = await fetch(ADMIN_API_URL, {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/json' }},
                            body: JSON.stringify(userData)
                        }});

                        const data = await response.json();

                        if (response.ok && data.ok) {{
                            setMsg('modalMsg', data.mensagem, true);
                            form.reset();
                            setTimeout(() => {{
                                closeModal();
                                fetchUsersAndRenderTable(); 
                            }}, 1500); 
                        }} else {{
                            setMsg('modalMsg', data.erro || 'Erro ao cadastrar.', false);
                        }}

                    }} catch (error) {{
                        setMsg('modalMsg', 'Erro de rede.', false);
                    }}
                }});

                async function deletar(usuario) {{
                    if (!confirm(`DELETAR ${{usuario}}?`)) return;

                    try {{
                        const response = await fetch(ADMIN_API_URL, {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/json' }},
                            body: JSON.stringify({{ acao: 'deletar', usuario: usuario }})
                        }});

                        const data = await response.json();

                        if (response.ok && data.ok) {{
                            fetchUsersAndRenderTable();
                        }} else {{
                            alert(data.erro || 'Erro ao deletar');
                        }}
                    }} catch (error) {{
                        alert('Erro de rede');
                    }}
                }}

                function openModal() {{
                    document.getElementById('userModal').style.display = 'block';
                    document.getElementById('newUserForm').reset();
                    document.getElementById('modalMsg').textContent = '';
                }}

                function closeModal() {{
                    document.getElementById('userModal').style.display = 'none';
                }}

                window.onclick = function(event) {{
                    if (event.target == document.getElementById('userModal')) closeModal();
                }}
            </script>
        </body>
        </html>
        """
        return html_content


# =======================================================
# ROTAS DE CONSULTA (MANTIDAS)
# =======================================================

@app.route('/api/consulta-cnpj')
def api_consulta_cnpj():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado CNPJ não fornecido"}), 400
    url_base = "http://klordapisBrasil.serveo.net/cnpj/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True)
    return jsonify(resultado)

@app.route('/api/consulta-cpf')
def api_consulta_cpf():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado CPF não fornecido"}), 400
    url_base = "https://klordapisbrasil.serveo.net/cpf/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True)
    return jsonify(resultado)

@app.route('/api/consulta-cpf2')
def api_consulta_cpf2():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado CPF não fornecido"}), 400
    url_base = "https://klordsearchapis.serveo.net/cpf/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True)
    return jsonify(resultado)

@app.route('/api/consulta-placa')
def api_consulta_placa():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado PLACA não fornecido"}), 400
    url_base = "http://klordapisBrasil.serveo.net/placa/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True)
    return jsonify(resultado)

@app.route('/api/consulta-placa-completa')
def api_consulta_placa_completa():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado PLACA não fornecido"}), 400
    url_base = "https://datazinapis.serveo.net/api/token=91919/consulta?tipo=placacompleta&dado="
    resultado = proxy_consulta(url_base, dado, requires_token_external=False)
    return jsonify(resultado)

@app.route('/api/consulta-nome')
def api_consulta_nome():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado NOME não fornecido"}), 400
    url_base = "https://klordsearchapis.serveo.net/nome/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True)
    return jsonify(resultado)

@app.route('/api/consulta-telefone')
def api_consulta_telefone():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado TELEFONE não fornecido"}), 400
    url_base = "https://klordapisbrasil.serveo.net/telefone/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True)
    return jsonify(resultado)

@app.route('/api/consulta-telefone2')
def api_consulta_telefone2():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado TELEFONE não fornecido"}), 400
    url_base = "http://n3.yoshinofenixbots.com:5042/AlizinHacker/telefone?token=klordmalware&telefone="
    resultado = proxy_consulta(url_base, dado, requires_token_external=False)
    return jsonify(resultado)

@app.route('/api/consulta-foto-sp')
def api_consulta_foto_sp():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado não fornecido"}), 400
    url_base = "https://klordsearchapis.serveo.net/fotos/SP/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True)
    return jsonify(resultado)

@app.route('/api/consulta-foto-rj')
def api_consulta_foto_rj():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado não fornecido"}), 400
    url_base = "http://klordsearchapis.serveo.net/fotorj/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True)
    return jsonify(resultado)

@app.route('/api/consulta-foto-es')
def api_consulta_foto_es():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado não fornecido"}), 400
    url_base = "https://klordsearchapis.serveo.net/fotos/ES/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True)
    return jsonify(resultado)

@app.route('/api/consulta-renavam')
def api_consulta_renavam():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado RENAVAM não fornecido"}), 400
    url_base = "https://klordsearchapis.serveo.net/renavam/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True)
    return jsonify(resultado)


if __name__ == '__main__':
    print("🚀 Klord Buscas iniciando...")
    print(f"📁 GitHub: {GITHUB_REPO}/{GITHUB_FILE_PATH}")
    print(f"🔑 Admin: /adm/{ADMIN_MANAGER_TOKEN}")
    app.run(host='0.0.0.0', port=5000)
