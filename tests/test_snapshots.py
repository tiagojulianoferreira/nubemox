# tests/test_snapshots.py]
from app.services.proxmox_service import ProxmoxService

def test_create_snapshot_success(app_context, mock_proxmox_connection):
    """Testa o fluxo completo de criação de snapshot (POST + Polling)."""
    service = ProxmoxService()
    
    # 1. Mock do retorno do POST (UPID)
    mock_resource = mock_proxmox_connection.nodes.return_value.qemu.return_value
    mock_resource.snapshot.post.return_value = "UPID:pve:snapshot:task"
    
    # 2. Mock do Polling (Sucesso)
    mock_proxmox_connection.nodes.return_value.tasks.return_value.status.get.return_value = {
        'status': 'stopped', 'exitstatus': 'OK'
    }
    
    # 3. Ação
    result = service.create_snapshot(100, "snap-01", "Backup antes do deploy", vmstate=True)
    
    # 4. Asserts
    # Verifica se chamou o endpoint de snapshot da VM 100
    mock_proxmox_connection.nodes.assert_called() # node resolvido
    mock_resource.snapshot.post.assert_called_with(
        snapname="snap-01", description="Backup antes do deploy", vmstate=1
    )
    
    # Verifica se fez o polling da tarefa correta
    mock_proxmox_connection.nodes.return_value.tasks.assert_called_with("UPID:pve:snapshot:task")
    assert "criado" in result['message']