# tests/test_service.py
from app.services.proxmox_service import ProxmoxService

def test_create_vm_success(app_context, mock_proxmox_connection):
    """Testa se create_vm chama a API do Proxmox com os dados certos."""
    service = ProxmoxService()
    
    mock_proxmox_connection.nodes.return_value.qemu.create.return_value = "UPID:test"
    mock_proxmox_connection.nodes.return_value.tasks.return_value.status.get.return_value = {
        'status': 'stopped', 'exitstatus': 'OK'
    }
    mock_proxmox_connection.cluster.nextid.get.return_value = 100
    
    config = {'name': 'vm-teste', 'poolid': 'vps-user', 'cores': 2}
    result = service.create_vm(config)
    
    mock_proxmox_connection.nodes.return_value.qemu.create.assert_called_once()
    assert result['vmid'] == 100