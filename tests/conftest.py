# tests/conftest.py
import pytest
from unittest.mock import MagicMock
from flask import Flask

@pytest.fixture
def app_context():
    """Cria um app Flask falso e ativa o contexto para os testes."""
    app = Flask(__name__)
    app.config.update({
        'PROXMOX_HOST': 'mock.pve',
        'PROXMOX_USER': 'test@pam',
        'PROXMOX_PASSWORD': 'test',
        'PROXMOX_API_TOKEN_NAME': 'token',
        'PROXMOX_API_TOKEN_VALUE': 'secret',
        'PROXMOX_DEFAULT_NODE': 'pve-node',
        'PROXMOX_TASK_TIMEOUT': 1,
        'PROXMOX_TASK_POLL_INTERVAL': 0.1
    })
    
    with app.app_context():
        yield

@pytest.fixture
def mock_proxmox_connection(mocker):
    """Mocka a classe ProxmoxAPI globalmente."""
    mock_api = mocker.patch('app.services.proxmox_service.ProxmoxAPI')
    return mock_api.return_value