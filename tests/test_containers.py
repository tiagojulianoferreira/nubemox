from unittest.mock import MagicMock # <--- Adicione isto
from app.services.proxmox_service import ProxmoxService

def test_assign_ct_to_pool_move_logic(app_context, mock_proxmox_connection):
    """
    Teste Avançado: Simula mover um CT do 'pool-antigo' para o 'pool-novo'.
    Valida a lógica de: Descobrir onde está -> Remover -> Adicionar.
    """
    service = ProxmoxService()
    ct_id = 105
    
    # 1. Mock: /cluster/resources (O serviço usa isso para saber onde o CT está)
    mock_proxmox_connection.cluster.resources.get.return_value = [
        {'vmid': 105, 'type': 'lxc', 'pool': 'pool-antigo'}
    ]
    
    # --- Mocks Diferenciados para cada Pool ---
    # Criamos objetos Mock distintos para simular os endpoints de cada pool
    mock_pool_antigo = MagicMock()
    mock_pool_novo = MagicMock()
    
    # Configuramos os retornos dos métodos .get() desses mocks
    mock_pool_antigo.get.return_value = {'members': [{'vmid': 105}, {'vmid': 106}]}
    mock_pool_novo.get.return_value = {'members': []}
    
    # Ensinamos o mock principal a retornar o mock correto dependendo do ID do pool
    def side_effect_pools(pool_id):
        if pool_id == 'pool-antigo':
            return mock_pool_antigo
        if pool_id == 'pool-novo':
            return mock_pool_novo
        return MagicMock()
        
    mock_proxmox_connection.pools.side_effect = side_effect_pools
    # ------------------------------------------
    
    # 2. Executar a movimentação
    service.assign_ct_to_pool(ct_id, 'pool-novo')
    
    # 3. Verificações
    
    # A) Verifique se removeu do antigo (chamou .put no mock_pool_antigo)
    # vms='106' significa que o 105 foi removido da lista original [105, 106]
    mock_pool_antigo.put.assert_called_with(vms='106')
    
    # B) Verifique se adicionou no novo (chamou .put no mock_pool_novo)
    mock_pool_novo.put.assert_called_with(vms='105')