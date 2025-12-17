from proxmoxer import ProxmoxAPI, ResourceException
from flask import current_app
import logging
import time
import urllib3

# Silencia avisos de certificado auto-assinado (comum em Proxmox)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class ProxmoxTaskFailedError(Exception):
    pass

class ProxmoxClient:
    """
    Cliente Base do Proxmox.
    Responsável apenas pela Conexão e Helpers de baixo nível.
    Todas as funcionalidades específicas (LXC, QEMU, etc) virão via herança (Mixins).
    """
    
    def __init__(self):
        # Inicializa vazio para suportar o padrão de Factory do Flask
        self.config = None
        self._connection = None
        self._cached_first_node_id = None
        self.logger = logging.getLogger(__name__)

    def init_app(self, app):
        """
        Carrega as configurações do Flask. 
        Chamado em app/__init__.py.
        """
        self.config = app.config
        
        # Validação básica
        if not self.config.get('PROXMOX_HOST'):
            self.logger.warning("PROXMOX_HOST não definido na configuração.")

    @property
    def connection(self):
        """
        Retorna a conexão ativa com o Proxmox (Singleton).
        """
        if self._connection:
            return self._connection

        if not self.config and current_app:
            self.config = current_app.config

        if not self.config:
            raise RuntimeError("ProxmoxClient não inicializado. Chame init_app(app) primeiro.")

        host = self.config.get('PROXMOX_HOST')
        user = self.config.get('PROXMOX_USER')
        password = self.config.get('PROXMOX_PASSWORD')
        token_name = self.config.get('PROXMOX_API_TOKEN_NAME')
        token_value = self.config.get('PROXMOX_API_TOKEN_VALUE')
        
        # --- CORREÇÃO AQUI ---
        # Converte para string antes de chamar .lower() para evitar erro se já for booleano
        ssl_val = self.config.get('PROXMOX_VERIFY_SSL', False)
        verify_ssl = str(ssl_val).lower() == 'true'

        try:
            if token_name and token_value:
                self._connection = ProxmoxAPI(
                    host,
                    user=user,
                    token_name=token_name,
                    token_value=token_value,
                    verify_ssl=verify_ssl
                )
            else:
                self._connection = ProxmoxAPI(
                    host,
                    user=user,
                    password=password,
                    verify_ssl=verify_ssl
                )
            
            return self._connection

        except Exception as e:
            self.logger.error(f"Falha ao conectar no Proxmox ({host}): {str(e)}")
            raise e
    def _resolve_node_id(self, node_id=None):
        """
        Helper fundamental para os Mixins.
        Descobre em qual Node do cluster operar.
        """
        if node_id:
            return node_id
        
        # Se tivermos um cache simples em memória, usa (evita chamada de API a cada request)
        if self._cached_first_node_id:
            return self._cached_first_node_id

        try:
            nodes = self.connection.nodes.get()
            for node in nodes:
                if node.get('status') == 'online':
                    self._cached_first_node_id = node['node']
                    return self._cached_first_node_id
            raise ResourceException("Nenhum nó online encontrado no cluster.")
        except Exception as e:
            # Se der erro de conexão, limpa o cache para tentar de novo na próxima
            self._connection = None 
            raise e

    def _wait_for_task_completion(self, task_upid, node_id, timeout=300):
        """
        Bloqueia a execução até a tarefa do Proxmox terminar.
        Essencial para criar recursos sequencialmente.
        """
        if not task_upid or not str(task_upid).startswith('UPID:'):
            return # Não é uma tarefa válida, ignora
        
        start_time = time.time()
        
        # Tenta ler timeout da config ou usa padrão
        if self.config:
            timeout = self.config.get('PROXMOX_TASK_TIMEOUT', 300)
        
        while (time.time() - start_time) < timeout:
            try:
                task = self.connection.nodes(node_id).tasks(task_upid).status.get()
                
                # Status: running, stopped
                if task.get('status') == 'stopped':
                    exit_status = task.get('exitstatus')
                    if exit_status == 'OK':
                        return True
                    else:
                        raise ProxmoxTaskFailedError(f"Tarefa Proxmox falhou: {exit_status}")
            
            except ProxmoxTaskFailedError:
                raise
            except Exception:
                # Ignora erros de rede momentâneos durante o polling
                pass
            
            time.sleep(1) # Aguarda 1 segundo antes de perguntar de novo
            
        raise TimeoutError(f"Timeout ({timeout}s) aguardando tarefa {task_upid}.")

    def get_next_vmid(self):
        """Helper global para obter próximo ID livre."""
        cluster_next = self.connection.cluster.nextid.get()
        return int(cluster_next)