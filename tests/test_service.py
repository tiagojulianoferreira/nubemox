def test_create_vm_success(service, mock_pve_connection):
    # 1. Configurar Mock
    mock_pve_connection.nodes.return_value.qemu.create.return_value = "UPID:test"
    mock_pve_connection.nodes.return_value.tasks.return_value.status.get.return_value = {
        'status': 'stopped', 'exitstatus': 'OK'
    }
    mock_pve_connection.cluster.nextid.get.return_value = 100
    
    # 2. Executar
    config = {'name': 'vm-teste', 'poolid': 'vps-user', 'cores': 2}
    result = service.create_vm(config)
    
    # 3. Validar
    mock_pve_connection.nodes.return_value.qemu.create.assert_called_once()
    assert result['vmid'] == 100