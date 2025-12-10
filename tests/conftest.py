import pytest
from unittest.mock import MagicMock
from app import create_app
from app.config import TestingConfig
from app.extensions import db

@pytest.fixture
def app():
    """
    Cria a instância do Flask configurada para TESTES.
    1. Usa 'TestingConfig' para garantir modo de teste.
    2. Usa banco SQLite em memória (rápido e isolado).
    3. Cria e destroi as tabelas a cada teste.
    """
    app = create_app(TestingConfig)
    
    # Reforça configurações críticas de Mock (caso o TestingConfig falhe)
    app.config.update({
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'JWT_SECRET_KEY': 'test-secret-key',
        
        # Mocks Proxmox
        'PROXMOX_HOST': 'mock.pve',
        'PROXMOX_USER': 'test@pam',
        'PROXMOX_PASSWORD': 'test',
        'PROXMOX_API_TOKEN_NAME': 'token',
        'PROXMOX_API_TOKEN_VALUE': 'secret',
        'PROXMOX_DEFAULT_NODE': 'pve-node',
        'PROXMOX_TASK_TIMEOUT': 1,
        'PROXMOX_VERIFY_SSL': False,
        
        # Mocks LDAP
        'LDAP_SERVER': 'ldap://mock',
        'LDAP_USER_DN_TEMPLATE': 'cn={},ou=users,dc=test'
    })
    
    # Contexto da Aplicação
    with app.app_context():
        # --- CRUCIAL: Importar Models aqui para o SQLAlchemy criar as tabelas ---
        from app.models import User, ResourceQuota, ServiceTemplate, VirtualResource
        
        db.create_all()  # Cria o schema no SQLite em memória
        
        yield app
        
        db.session.remove() # Fecha a sessão do SQLAlchemy
        db.drop_all()       # Limpa o banco para o próximo teste

@pytest.fixture
def client(app):
    """
    Client HTTP simulado para fazer requisições (POST, GET) nas rotas.
    Ex: client.post('/api/auth/login', ...)
    """
    return app.test_client()

@pytest.fixture
def app_context(app):
    """
    Fixture de compatibilidade. Alguns testes pedem apenas o contexto ativo.
    """
    with app.app_context():
        yield

@pytest.fixture
def mock_pve_connection(mocker):
    """
    Mocka a classe ProxmoxAPI globalmente.
    Impede que o sistema tente conectar na rede real.
    """
    # Ajuste o caminho conforme sua estrutura de pastas
    mock_api = mocker.patch('app.proxmox.client.ProxmoxAPI')
    return mock_api.return_value

@pytest.fixture
def mock_proxmox_connection(mock_pve_connection):
    """
    ALIAS DE COMPATIBILIDADE.
    Redireciona chamadas antigas de 'mock_proxmox_connection' para 'mock_pve_connection'.
    Isso evita quebrar seus testes anteriores.
    """
    return mock_pve_connection

@pytest.fixture
def service(app, mock_pve_connection):
    """
    Retorna uma instância do ProxmoxService pronta para uso,
    com o mock de conexão já injetado manualmente.
    """
    from app.proxmox import ProxmoxService
    
    svc = ProxmoxService()
    # Injeta o mock para garantir que não use a conexão real
    svc._connection = mock_pve_connection
    return svc