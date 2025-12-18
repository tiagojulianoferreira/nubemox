import logging
import urllib3
from flask import current_app
from proxmoxer import ProxmoxAPI, ResourceException

# Silenciar avisos de SSL inseguro (comum em ambientes Proxmox de laboratório)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class ProxmoxClient:
    def __init__(self):
        """
        Construtor vazio. 
        NÃO faz conexões aqui para evitar erros fora do contexto da aplicação.
        """
        self._connection = None
        self.config = None
        self.logger = logging.getLogger(__name__)

    def init_app(self, app):
        """
        Inicializa a extensão com a aplicação Flask.
        Chamado no app/__init__.py.
        """
        self.config = app.config
        # Opcional: Validar se as variáveis necessárias existem
        required_keys = ['PROXMOX_HOST', 'PROXMOX_USER']
        for key in required_keys:
            if key not in self.config:
                self.logger.warning(f"Configuração {key} não encontrada no Flask config.")

    @property
    def connection(self):
        """
        Retorna a conexão ativa (Singleton).
        Se não existir, cria uma nova.
        """
        # Se a conexão já existe, retorna ela (Reaproveitamento)
        if self._connection:
            return self._connection

        # Se self.config não foi preenchido pelo init_app, tenta pegar do current_app (Fallback)
        if not self.config:
            if current_app:
                self.config = current_app.config
            else:
                raise RuntimeError("ProxmoxClient não inicializado. Chame init_app(app) primeiro.")

        # Lógica de Conexão
        host = self.config.get('PROXMOX_HOST')
        user = self.config.get('PROXMOX_USER')
        password = self.config.get('PROXMOX_PASSWORD')
        token_name = self.config.get('PROXMOX_TOKEN_NAME')
        token_value = self.config.get('PROXMOX_TOKEN_VALUE')
        verify_ssl = self.config.get('PROXMOX_VERIFY_SSL', 'false').lower() == 'true'

        try:
            # Opção 1: Autenticação por Token (Recomendado para API)
            if token_name and token_value:
                self._connection = ProxmoxAPI(
                    host,
                    user=user,
                    token_name=token_name,
                    token_value=token_value,
                    verify_ssl=verify_ssl
                )
            # Opção 2: Autenticação por Senha
            else:
                self._connection = ProxmoxAPI(
                    host,
                    user=user,
                    password=password,
                    verify_ssl=verify_ssl
                )
            
            self.logger.info(f"Conexão com Proxmox ({host}) estabelecida com sucesso.")
            return self._connection

        except Exception as e:
            self.logger.error(f"Falha ao conectar no Proxmox: {str(e)}")
            raise e

    # --- MÉTODOS UTILITÁRIOS (SERVICE LAYER) ---
    
    def get_node(self):
        """Retorna o primeiro nó ativo do cluster."""
        nodes = self.connection.nodes.get()
        for node in nodes:
            if node['status'] == 'online':
                return node['node']
        raise Exception("Nenhum nó Proxmox online encontrado.")

    def get_next_vmid(self):
        """Busca o próximo ID livre no cluster."""
        cluster_resources = self.connection.cluster.resources.get(type='vm')
        ids = [int(vm['vmid']) for vm in cluster_resources]
        next_id = max(ids) + 1 if ids else 100
        return next_id

    def ensure_user_pool(self, username):
        """Garante que existe um Pool de recursos para o usuário."""
        pool_id = f"vps-{username}"
        try:
            self.connection.pools.get(pool_id)
        except ResourceException:
            self.logger.info(f"Criando pool {pool_id}")
            self.connection.pools.post(poolid=pool_id, comment=f"Pool do usuário {username}")
        return pool_id

    def ensure_pve_user(self, username, realm='pve'):
        """
        Cria o usuário no Proxmox se não existir (opcional, dependendo da sua estratégia).
        Geralmente retornamos o formato user@realm.
        """
        # Implementação simplificada
        return f"{username}@{realm}"

    def set_pool_permission(self, pool_id, user_pve_id, role='PVEVMUser'):
        """Define permissão no Pool."""
        try:
            self.connection.access.acl.put(
                path=f"/pool/{pool_id}",
                roles=role,
                users=user_pve_id
            )
        except Exception as e:
            self.logger.warning(f"Erro ao setar permissão: {e}")

          
    # Validar se é necessário na nova arquitetura
    # def clone_container(self, source_vmid, new_vmid, name, poolid, full_clone=True):
    #     """Clona um Container LXC."""
    #     node = self.get_node()
        
    #     self.logger.info(f"Clonando CT {source_vmid} -> {new_vmid} ({name}) no node {node}")
        
    #     task_id = self.connection.nodes(node).lxc(source_vmid).clone.post(
    #         newid=new_vmid,
    #         hostname=name,
    #         pool=poolid,
    #         full=1 if full_clone else 0
    #     )
    #     return task_id

    # Adicione methods para QEMU/VM aqui se necessário
    # def clone_vm(self, ...): ...