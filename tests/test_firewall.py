def test_enable_firewall_adds_flag_if_missing(service, mock_pve_connection):
    # 1. Mock (sem firewall)
    mock_lxc = mock_pve_connection.nodes.return_value.lxc.return_value
    mock_lxc.config.get.return_value = {
        'net0': 'name=eth0,bridge=vmbr0,ip=dhcp'
    }
    
    # 2. Ação
    service.enable_container_firewall(200)
    
    # 3. Validação
    mock_lxc.firewall.options.put.assert_called_with(enable=1)
    mock_lxc.config.put.assert_called_with(
        net0='name=eth0,bridge=vmbr0,ip=dhcp,firewall=1'
    )

def test_enable_firewall_skips_if_present(service, mock_pve_connection):
    # 1. Mock (já tem firewall)
    mock_lxc = mock_pve_connection.nodes.return_value.lxc.return_value
    mock_lxc.config.get.return_value = {
        'net0': 'name=eth0,bridge=vmbr0,ip=dhcp,firewall=1'
    }
    
    # 2. Ação
    service.enable_container_firewall(200)
    
    # 3. Validação (não chama config.put)
    mock_lxc.firewall.options.put.assert_called_with(enable=1)
    mock_lxc.config.put.assert_not_called()