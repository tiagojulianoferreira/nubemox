# tests/test_service_errors.py
import pytest
from proxmoxer import ResourceException
from app.services.proxmox_service import ProxmoxService

def test_create_vm_failure_proxmox_error(app_context, mock_proxmox_connection):
    """Testa se o serviço repassa a exceção quando o Proxmox falha na criação."""
    service = ProxmoxService()
    
    # --- CORREÇÃO AQUI ---
    # ResourceException requer: (message, status_code, content)
    # Passamos valores fictícios para satisfazer o construtor
    error_exception = ResourceException("Pool not found", 500, "Error content")
    
    # Configura o mock para lançar essa exceção específica
    mock_proxmox_connection.nodes.return_value.qemu.create.side_effect = error_exception
    # ---------------------
    
    config = {'name': 'vm-fail', 'poolid': 'invalid-pool'}
    
    # Verifica se a exceção sobe
    with pytest.raises(ResourceException) as excinfo:
        service.create_vm(config)
    
    assert "Pool not found" in str(excinfo.value)