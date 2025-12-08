from proxmoxer import ProxmoxAPI, ResourceException
from flask import current_app
import logging
import time

class ProxmoxTaskFailedError(Exception):
    pass

class ProxmoxClient:
    """
    Cliente base: Gerencia conexão, autenticação e helpers de baixo nível.
    """
    def __init__(self):
        self.config = current_app.config
        self.host = self.config.get('PROXMOX_HOST')
        self.user = self.config.get('PROXMOX_USER')
        self.password = self.config.get('PROXMOX_PASSWORD')
        self.token_name = self.config.get('PROXMOX_API_TOKEN_NAME')
        self.token_value = self.config.get('PROXMOX_API_TOKEN_VALUE')
        
        self._default_node = self.config.get('PROXMOX_DEFAULT_NODE')
        
        # SSL Config
        verify_ssl = self.config.get('PROXMOX_VERIFY_SSL', False)
        if isinstance(verify_ssl, str):
            verify_ssl = verify_ssl.lower() == 'true'
        self.verify_ssl = verify_ssl

        self._connection = None
        self._cached_first_node_id = None
        self.logger = logging.getLogger(__name__)

    @property
    def connection(self):
        if self._connection is None:
            connect_kwargs = {
                'host': self.host, 'user': self.user, 
                'verify_ssl': self.verify_ssl, 'timeout': 30
            }
            if self.token_name and self.token_value:
                connect_kwargs['token_name'] = self.token_name
                connect_kwargs['token_value'] = self.token_value
            else:
                connect_kwargs['password'] = self.password
            
            self._connection = ProxmoxAPI(**connect_kwargs)
        return self._connection

    def _resolve_node_id(self, node_id=None):
        if node_id: return node_id
        if self._default_node: return self._default_node
        if self._cached_first_node_id: return self._cached_first_node_id
        
        nodes = self.connection.nodes.get()
        if nodes:
            self._cached_first_node_id = nodes[0]['node']
            return self._cached_first_node_id
        raise ResourceException("Nenhum node encontrado no cluster.")

    def _wait_for_task_completion(self, task_upid, node_id):
        if not task_upid or not str(task_upid).startswith('UPID:'): return
        
        start_time = time.time()
        timeout = self.config.get('PROXMOX_TASK_TIMEOUT', 300)
        
        while (time.time() - start_time) < timeout:
            task = self.connection.nodes(node_id).tasks(task_upid).status.get()
            if task.get('status') == 'stopped':
                if task.get('exitstatus') == 'OK': return
                raise ProxmoxTaskFailedError(f"Falha na tarefa: {task.get('exitstatus')}")
            time.sleep(1)
        raise TimeoutError("Timeout aguardando Proxmox.")

    def get_next_vmid(self):
        """Retorna o próximo ID livre do Cluster."""
        return self.connection.cluster.nextid.get()
    
    def get_nodes(self):
        nodes = self.connection.nodes.get()
        return {'data': nodes, 'count': len(nodes)}