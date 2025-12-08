import pytest
from proxmoxer import ResourceException

def test_create_vm_failure_proxmox_error(service, mock_pve_connection):
    # 1. Configurar Mock para falhar
    error_exception = ResourceException("Pool not found", 500, "Error content")
    mock_pve_connection.nodes.return_value.qemu.create.side_effect = error_exception
    
    config = {'name': 'vm-fail', 'poolid': 'invalid-pool'}
    
    # 2. Verificar exceção
    with pytest.raises(ResourceException) as excinfo:
        service.create_vm(config)
    
    assert "Pool not found" in str(excinfo.value)