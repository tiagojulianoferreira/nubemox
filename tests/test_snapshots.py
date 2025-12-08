def test_create_snapshot_success(service, mock_pve_connection):
    # 1. Mock
    mock_resource = mock_pve_connection.nodes.return_value.qemu.return_value
    mock_resource.snapshot.post.return_value = "UPID:pve:snapshot:task"
    
    mock_pve_connection.nodes.return_value.tasks.return_value.status.get.return_value = {
        'status': 'stopped', 'exitstatus': 'OK'
    }
    
    # 2. Ação
    service.create_snapshot(100, "snap-01", "Backup antes do deploy", vmstate=True)
    
    # 3. Asserts
    mock_resource.snapshot.post.assert_called_with(
        snapname="snap-01", description="Backup antes do deploy", vmstate=1
    )