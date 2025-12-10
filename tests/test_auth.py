import pytest
from unittest.mock import patch, MagicMock
from app.models import User

# Dados simulados que o LDAP retornaria
MOCK_LDAP_USER = {
    'username': 'tiago.teste',
    'email': 'tiago.teste@nubemox.local',
    'fullname': 'Tiago Teste'
}

def test_login_success_creates_shadow_user(client, app_context):
    """
    Testa se um login válido no LDAP:
    1. Cria o usuário no banco local (Shadow User).
    2. Retorna o Token JWT.
    3. Retorna os dados do usuário.
    """
    
    # 1. Mock do LDAPService
    # Interceptamos a classe LDAPService e o método authenticate
    with patch('app.api.auth.routes.LDAPService') as MockService:
        # Configura o mock para retornar sucesso
        mock_instance = MockService.return_value
        mock_instance.authenticate.return_value = MOCK_LDAP_USER
        
        # 2. Faz a requisição de Login
        payload = {
            "username": "tiago.teste",
            "password": "senha-correta"
        }
        response = client.post('/api/auth/login', json=payload)
        
        # 3. Validações da Resposta HTTP
        assert response.status_code == 200
        data = response.get_json()
        
        assert "access_token" in data
        assert data["user"]["username"] == "tiago.teste"
        assert data["user"]["email"] == "tiago.teste@nubemox.local"
        
        # 4. Validação do Banco de Dados (Efeito Colateral)
        # Verifica se o usuário foi realmente criado no banco
        user_db = User.query.filter_by(username="tiago.teste").first()
        assert user_db is not None
        assert user_db.email == "tiago.teste@nubemox.local"
        # Verifica se a cota padrão foi criada
        assert user_db.quota is not None

def test_login_failure_invalid_credentials(client):
    """
    Testa se o sistema retorna 401 quando o LDAP rejeita as credenciais.
    """
    with patch('app.api.auth.routes.LDAPService') as MockService:
        # Configura o mock para retornar None (falha no login)
        mock_instance = MockService.return_value
        mock_instance.authenticate.return_value = None
        
        payload = {
            "username": "hacker",
            "password": "senha-errada"
        }
        response = client.post('/api/auth/login', json=payload)
        
        assert response.status_code == 401
        assert "Credenciais inválidas" in response.get_json()["msg"]

def test_login_missing_fields(client):
    """
    Testa validação de campos obrigatórios.
    """
    response = client.post('/api/auth/login', json={"username": "so-usuario"})
    assert response.status_code == 400