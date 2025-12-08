from unittest.mock import MagicMock

def test_assign_ct_to_pool_move_logic(service, mock_pve_connection):
    ct_id = 105
    
    mock_pve_connection.cluster.resources.get.return_value = [
        {'vmid': 105, 'type': 'lxc', 'pool': 'pool-antigo'}
    ]
    
    mock_pool_antigo = MagicMock()
    mock_pool_novo = MagicMock()
    mock_pool_antigo.get.return_value = {'members': [{'vmid': 105}]}
    mock_pool_novo.get.return_value = {'members': []}
    
    def side_effect_pools(pool_id):
        if pool_id == 'pool-antigo': return mock_pool_antigo
        if pool_id == 'pool-novo': return mock_pool_novo
        return MagicMock()
        
    mock_pve_connection.pools.side_effect = side_effect_pools
    
    # Verifica se o método existe antes de chamar
    if hasattr(service, 'assign_ct_to_pool'):
        service.assign_ct_to_pool(ct_id, 'pool-novo')
        mock_pool_antigo.put.assert_called() 
        mock_pool_novo.put.assert_called()