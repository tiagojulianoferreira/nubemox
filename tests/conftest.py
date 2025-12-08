# tests/conftest.py
import pytest
from flask import Flask
# IMPORTAÇÃO NOVA (Modular)
from app.proxmox import ProxmoxService

@pytest.fixture
def app_context():
    """Cria um app Flask falso e ativa o contexto."""
    app = Flask(__name__)
    app.config.update({
        'PROXMOX_HOST': 'mock.pve',
        'PROXMOX_USER': 'test@pam',
        'PROXMOX_PASSWORD': 'test',
        'PROXMOX_API_TOKEN_NAME': 'token',
        'PROXMOX_API_TOKEN_VALUE': 'secret',
        'PROXMOX_DEFAULT_NODE': 'pve-node',
        'PROXMOX_TASK_TIMEOUT': 1,
        'PROXMOX_VERIFY_SSL': False
    })
    
    with app.app_context():
        yield app

@pytest.fixture
def mock_pve_connection(mocker):
    """
    Mocka a conexão lá dentro do client.py.
    """
    # Patch no caminho novo: app.proxmox.client
    mock_class = mocker.patch('app.proxmox.client.ProxmoxAPI')
    return mock_class.return_value

@pytest.fixture
def service(app_context, mock_pve_connection):
    """
    Entrega uma instância do ProxmoxService pronta para uso nos testes.
    """
    svc = ProxmoxService()
    # Injeta o mock manualmente para garantir que não conecte de verdade
    svc._connection = mock_pve_connection
    return svc