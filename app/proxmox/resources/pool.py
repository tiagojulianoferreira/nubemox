from proxmoxer import ResourceException

class PoolManager:
    """Mixin para gerenciamento de Resource Pools."""

    def get_pools(self):
        pools = self.connection.pools.get()
        return {'data': pools, 'count': len(pools)}

    def create_pool(self, poolid, comment=None):
        params = {'poolid': poolid}
        if comment: params['comment'] = comment
        
        try:
            self.connection.pools.post(**params)
            return {'success': True, 'message': f'Pool {poolid} criado.'}
        except ResourceException as e:
            # Se o erro for "já existe", não é um problema grave
            if 'already exists' in str(e):
                return {'success': True, 'message': f'Pool {poolid} já existe.', 'existing': True}
            raise e

    def delete_pool(self, poolid):
        self.connection.pools(poolid).delete()
        return {'message': f'Pool {poolid} excluído.'}

    def ensure_user_pool(self, username):
        """
        Helper de Negócio: Garante que o pool do usuário exista.
        Retorna o ID do pool (ex: 'vps-tiago').
        """
        # Sanitização simples (remove espaços, lowercase)
        safe_name = username.lower().replace(' ', '-')
        poolid = f"vps-{safe_name}"
        
        self.create_pool(poolid, comment=f"Pool dedicado ao usuário: {username}")
        return poolid