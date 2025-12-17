from app.services.health.base import HealthCheckProvider
from app.proxmox import proxmox_client 

class ProxmoxHealthCheck(HealthCheckProvider):
    @property
    def name(self):
        return "Proxmox Cluster"

    @property
    def category(self):
        return "compute"

    def check(self):
        # 1. Verifica se o objeto cliente foi importado
        if not proxmox_client:
            return {
                'status': 'unhealthy',
                'error': 'Objeto proxmox_client não encontrado.'
            }

        # 2. Tenta acessar a propriedade .connection
        # Isso aciona o Lazy Loading. Se faltar config (host/user), vai dar erro aqui.
        try:
            conn = proxmox_client.connection
            if not conn:
                return {'status': 'unhealthy', 'error': 'Falha ao criar conexão.'}
        except Exception as e:
            # Captura erro de configuração (ex: falta PROXMOX_HOST no .env)
            return {'status': 'unhealthy', 'error': str(e)}

        # 3. Teste real de API (Ping)
        # Usamos 'conn' (que é proxmox_client.connection) e não .proxmox
        try:
            version_data = conn.version.get()
        except Exception as e:
             return {'status': 'unhealthy', 'error': f'Proxmox inacessível: {str(e)}'}
        
        return {
            'status': 'healthy',
            'details': {
                'version': version_data.get('version'),
                'release': version_data.get('release'),
                'repoid': version_data.get('repoid')
            }
        }