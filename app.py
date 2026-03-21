from flask import Flask, request, jsonify, send_from_directory, render_template_string
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

VALID_TOKEN = "KLORD-TESTE-1234567890ABCDEF" 
ADM_TOKEN_EXTERNAL = "admkl0rd"
ADM_TOKEN_V2 = "Kl0rd777"
ADMIN_MANAGER_TOKEN = "Kl0rd777" 
ADMIN_ROUTE = f"/adm/{ADMIN_MANAGER_TOKEN}"

# =======================================================
# CONFIGURAÇÃO DO GITHUB
# =======================================================
GITHUB_TOKEN = "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"
GITHUB_REPO = "klordTV/klTV"
GITHUB_FILE_PATH = "database.json"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"

# =======================================================
# FUNÇÕES GITHUB API
# =======================================================

def get_github_file():
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
    content, sha, error = get_github_file()
    if error:
        if os.path.exists("database.json"):
            try:
                with open("database.json", "r") as f:
                    return json.load(f).get("logins", [])
            except:
                return []
        return []
    return content.get("logins", [])

def salvar_logins(logins_list):
    content, sha, error = get_github_file()
    new_content = {"logins": logins_list}
    success, error = update_github_file(
        new_content, 
        sha, 
        f"Update users - {datetime.now().strftime('%d/%m %H:%M')}"
    )
    if success:
        try:
            with open("database.json", "w") as f:
                json.dump(new_content, f, indent=4)
        except:
            pass
        return True
    return False

def check_expiration(user_data):
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

def proxy_consulta(api_url, dado, requires_token_external=False, token_value=None, token_key='token'):
    TIMEOUT_SECONDS = 60 
    url = f"{api_url}{dado}"
    if requires_token_external:
        sep = '&' if '?' in url else '?'
        token = token_value or ADM_TOKEN_EXTERNAL
        url += f"{sep}{token_key}={token}"
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

@app.route('/admin/dashboard')
def admin_dashboard():
    return send_from_directory('.', 'admin_dashboard.html')

@app.route('/admin/users')
def admin_users():
    return send_from_directory('.', 'admin_users.html')

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
            return jsonify({"ok": True, "mensagem": "Login OK", "tipo": login.get("tipo", "user")})

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

        elif acao == 'editar':
            senha = dados.get('senha')
            expiracao = dados.get('expiracao') or None
            nome_completo = dados.get('nome_completo') or None
            email = dados.get('email') or None
            tipo = dados.get('tipo') or 'user'

            user_found = False
            for login in logins:
                if login.get("usuario") == usuario:
                    if senha:
                        login["senha"] = senha
                    if expiracao is not None:
                        login["expiracao"] = expiracao
                    if nome_completo:
                        login["nome_completo"] = nome_completo
                    if email:
                        login["email"] = email
                    if tipo:
                        login["tipo"] = tipo
                    user_found = True
                    break

            if not user_found:
                return jsonify({"ok": False, "erro": f"Usuário '{usuario}' não encontrado"}), 404

            if salvar_logins(logins):
                return jsonify({"ok": True, "mensagem": f"Usuário '{usuario}' atualizado!"})
            else:
                return jsonify({"ok": False, "erro": "Falha ao atualizar no GitHub"}), 500

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
        return send_from_directory('.', 'admin.html')

# =======================================================
# ROTAS DE CONSULTA - V1 (klordapiv1.onrender.com)
# =======================================================

BASE_URL_V1 = "https://klordapiv1.onrender.com"

@app.route('/api/consulta-cnpj')
def api_consulta_cnpj():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado CNPJ não fornecido"}), 400
    url_base = f"{BASE_URL_V1}/cnpj/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True, token_value=ADM_TOKEN_EXTERNAL)
    return jsonify(resultado)

@app.route('/api/consulta-cpf')
def api_consulta_cpf():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado CPF não fornecido"}), 400
    url_base = f"{BASE_URL_V1}/cpf/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True, token_value=ADM_TOKEN_EXTERNAL)
    return jsonify(resultado)

@app.route('/api/consulta-rg')
def api_consulta_rg():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado RG não fornecido"}), 400
    url_base = f"{BASE_URL_V1}/rg/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True, token_value=ADM_TOKEN_EXTERNAL)
    return jsonify(resultado)

@app.route('/api/consulta-nome')
def api_consulta_nome():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado NOME não fornecido"}), 400
    url_base = f"{BASE_URL_V1}/nome/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True, token_value=ADM_TOKEN_EXTERNAL)
    return jsonify(resultado)

@app.route('/api/consulta-telefone')
def api_consulta_telefone():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado TELEFONE não fornecido"}), 400
    url_base = f"{BASE_URL_V1}/telefone/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True, token_value=ADM_TOKEN_EXTERNAL)
    return jsonify(resultado)

@app.route('/api/consulta-placa')
def api_consulta_placa():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado PLACA não fornecido"}), 400
    url_base = f"{BASE_URL_V1}/placa/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True, token_value=ADM_TOKEN_EXTERNAL)
    return jsonify(resultado)

@app.route('/api/consulta-renavam')
def api_consulta_renavam():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado RENAVAM não fornecido"}), 400
    url_base = f"{BASE_URL_V1}/renavam/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True, token_value=ADM_TOKEN_EXTERNAL)
    return jsonify(resultado)

@app.route('/api/consulta-foto-sp')
def api_consulta_foto_sp():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado não fornecido"}), 400
    url_base = f"{BASE_URL_V1}/fotosp/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True, token_value=ADM_TOKEN_EXTERNAL)
    return jsonify(resultado)

@app.route('/api/consulta-foto-rj')
def api_consulta_foto_rj():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado não fornecido"}), 400
    url_base = f"{BASE_URL_V1}/fotorj/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True, token_value=ADM_TOKEN_EXTERNAL)
    return jsonify(resultado)

@app.route('/api/consulta-foto-es')
def api_consulta_foto_es():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado não fornecido"}), 400
    url_base = f"{BASE_URL_V1}/fotoes/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True, token_value=ADM_TOKEN_EXTERNAL)
    return jsonify(resultado)

# =======================================================
# ROTAS DE CONSULTA - V2 (klordapiv2.onrender.com)
# =======================================================

BASE_URL_V2 = "https://klordapiv2.onrender.com"

@app.route('/api/consulta-cpf-v1')
def api_consulta_cpf_v1():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado CPF não fornecido"}), 400
    url_base = f"{BASE_URL_V2}/cpf/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True, token_value=ADM_TOKEN_V2)
    return jsonify(resultado)

@app.route('/api/consulta-cpf-v2')
def api_consulta_cpf_v2():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado CPF não fornecido"}), 400
    url_base = f"{BASE_URL_V2}/cpf2/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True, token_value=ADM_TOKEN_V2)
    return jsonify(resultado)

@app.route('/api/consulta-cpf-v3')
def api_consulta_cpf_v3():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado CPF não fornecido"}), 400
    url_base = f"{BASE_URL_V2}/cpf3/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True, token_value=ADM_TOKEN_V2)
    return jsonify(resultado)

@app.route('/api/consulta-cpf-v4')
def api_consulta_cpf_v4():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado CPF não fornecido"}), 400
    url_base = f"{BASE_URL_V2}/cpf4/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True, token_value=ADM_TOKEN_V2)
    return jsonify(resultado)

@app.route('/api/consulta-cpf-v5')
def api_consulta_cpf_v5():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado CPF não fornecido"}), 400
    url_base = f"{BASE_URL_V2}/cpf5/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True, token_value=ADM_TOKEN_V2)
    return jsonify(resultado)

@app.route('/api/consulta-fotope')
def api_consulta_fotope():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado NOME não fornecido"}), 400
    url_base = f"{BASE_URL_V2}/fotope/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True, token_value=ADM_TOKEN_V2)
    return jsonify(resultado)

@app.route('/api/consulta-nome-v2')
def api_consulta_nome_v2():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado NOME não fornecido"}), 400
    url_base = f"{BASE_URL_V2}/nome/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True, token_value=ADM_TOKEN_V2)
    return jsonify(resultado)

@app.route('/api/consulta-placa-v1')
def api_consulta_placa_v1():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado PLACA não fornecido"}), 400
    url_base = f"{BASE_URL_V2}/placa/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True, token_value=ADM_TOKEN_V2)
    return jsonify(resultado)

@app.route('/api/consulta-placa-v2')
def api_consulta_placa_v2():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado PLACA não fornecido"}), 400
    url_base = f"{BASE_URL_V2}/placa2/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True, token_value=ADM_TOKEN_V2)
    return jsonify(resultado)

@app.route('/api/consulta-telefone-v2')
def api_consulta_telefone_v2():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado TELEFONE não fornecido"}), 400
    url_base = f"{BASE_URL_V2}/telefone/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True, token_value=ADM_TOKEN_V2)
    return jsonify(resultado)

@app.route('/api/consulta-cep')
def api_consulta_cep():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado CEP não fornecido"}), 400
    url_base = f"{BASE_URL_V2}/cep/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True, token_value=ADM_TOKEN_V2)
    return jsonify(resultado)

@app.route('/api/consulta-cnpj-v2')
def api_consulta_cnpj_v2():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado CNPJ não fornecido"}), 400
    url_base = f"{BASE_URL_V2}/cnpj/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True, token_value=ADM_TOKEN_V2)
    return jsonify(resultado)

@app.route('/api/consulta-motor')
def api_consulta_motor():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado MOTOR não fornecido"}), 400
    url_base = f"{BASE_URL_V2}/motor/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True, token_value=ADM_TOKEN_V2)
    return jsonify(resultado)

@app.route('/api/consulta-chassi')
def api_consulta_chassi():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado CHASSI não fornecido"}), 400
    url_base = f"{BASE_URL_V2}/chassi/"
    resultado = proxy_consulta(url_base, dado, requires_token_external=True, token_value=ADM_TOKEN_V2)
    return jsonify(resultado)

# =======================================================
# ROTAS LEGADAS (mantidas para compatibilidade)
# =======================================================

@app.route('/api/consulta-cpf2')
def api_consulta_cpf2():
    return api_consulta_cpf_v2()

@app.route('/api/consulta-placa-completa')
def api_consulta_placa_completa():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado PLACA não fornecido"}), 400
    url_base = "https://klordapi-rild.onrender.com/api/token=91919/consulta?tipo=placacompleta&dado="
    resultado = proxy_consulta(url_base, dado, requires_token_external=False)
    return jsonify(resultado)

@app.route('/api/consulta-telefone2')
def api_consulta_telefone2():
    dado = request.args.get('dado')
    if not dado:
        return jsonify({"erro": "Dado TELEFONE não fornecido"}), 400
    url_base = "https://klordapi-rild.onrender.com/AlizinHacker/telefone?token=klordmalware&telefone="
    resultado = proxy_consulta(url_base, dado, requires_token_external=False)
    return jsonify(resultado)

if __name__ == '__main__':
    print("🚀 Klord Buscas V2.0 iniciando...")
    print(f"📁 GitHub: {GITHUB_REPO}/{GITHUB_FILE_PATH}")
    print(f"🔑 Admin: /adm/{ADMIN_MANAGER_TOKEN}")
    print(f"📊 Total de APIs: 25+ endpoints")
    app.run(host='0.0.0.0', port=5000, debug=True)
