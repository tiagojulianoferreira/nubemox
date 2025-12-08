# tests/test_firewall.py
from app.services.proxmox_service import ProxmoxService
def test_enable_firewall_adds_flag_if_missing(app_context, mock_proxmox_connection):
    """Testa se adiciona firewall=1 na net0 quando não existe."""
    service = ProxmoxService()
    
    # Mock da configuração atual (sem firewall)
    mock_lxc = mock_proxmox_connection.nodes.return_value.lxc.return_value
    mock_lxc.config.get.return_value = {
        'net0': 'name=eth0,bridge=vmbr0,ip=dhcp'
    }
    
    service.enable_container_firewall(200)
    
    # Verifica se habilitou nas options globais
    mock_lxc.firewall.options.put.assert_called_with(enable=1)
    
    # Verifica se atualizou a net0 adicionando a flag
    mock_lxc.config.put.assert_called_with(
        net0='name=eth0,bridge=vmbr0,ip=dhcp,firewall=1'
    )

def test_enable_firewall_skips_if_present(app_context, mock_proxmox_connection):
    """Testa se NÃO altera a net0 se firewall=1 já estiver lá."""
    service = ProxmoxService()
    
    # Configuração atual JÁ TEM firewall=1
    mock_lxc = mock_proxmox_connection.nodes.return_value.lxc.return_value
    mock_lxc.config.get.return_value = {
        'net0': 'name=eth0,bridge=vmbr0,ip=dhcp,firewall=1'
    }
    
    service.enable_container_firewall(200)
    
    # Deve habilitar globalmente sempre
    mock_lxc.firewall.options.put.assert_called_with(enable=1)
    
    # MAS NÃO deve chamar config.put para net0 (economia de restart)
    mock_lxc.config.put.assert_not_called()