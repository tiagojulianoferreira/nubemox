from proxmoxer import ProxmoxAPI, ResourceException
from flask import current_app
import logging
import re
from proxmoxer import ResourceException # Importar para tratar erros do serviço

class ProxmoxService:
    """
    Serviço para integração com API do Proxmox VE.
    Prioriza autenticação via API Token (token_name e token_value).
    """
    
    def __init__(self, host=None, user=None, password=None, verify_ssl=None, default_node=None, token_name=None, token_value=None):
        self.config = current_app.config
        self.host = host or self.config['PROXMOX_HOST']
        
        # O User ID completo (e.g., user@realm) é obrigatório, mesmo com token
        self.user = user or self.config['PROXMOX_USER']
        self.password = password or self.config['PROXMOX_PASSWORD'] # Usado como fallback e para tickets VNC
        
        # Credenciais API Token
        self.token_name = token_name or self.config.get('PROXMOX_API_TOKEN_NAME')
        self.token_value = token_value or self.config.get('PROXMOX_API_TOKEN_VALUE')
        
        # Renomeado no config para PROXMOX_DEFAULT_NODE (usando fallback para 'PROXMOX_NODE')
        default_node_config = self.config.get('PROXMOX_DEFAULT_NODE') or self.config.get('PROXMOX_NODE')
        self._default_node = default_node or default_node_config
        
        # Converter string 'false'/'true' para booleano
        config_ssl = self.config['PROXMOX_VERIFY_SSL']
        if isinstance(config_ssl, str):
            config_ssl = config_ssl.lower() == 'true'
            
        self.verify_ssl = verify_ssl if verify_ssl is not None else config_ssl
        self._connection = None
        self._cached_first_node_id = None
        
        self.logger = logging.getLogger(__name__)

    @property
    def connection(self):
        """Lazy connection - Prioriza a autenticação via API Token."""
        if self._connection is None:
            try:
                # Argumentos base para a conexão
                connect_kwargs = {
                    'host': self.host,
                    'user': self.user, 
                    'verify_ssl': self.verify_ssl,
                    'timeout': 30
                }
                
                # Prioriza API Token se ambos estiverem configurados
                if self.token_name and self.token_value:
                    connect_kwargs['token_name'] = self.token_name
                    connect_kwargs['token_value'] = self.token_value
                    log_message = f"API Token: {self.token_name} for user {self.user}"
                else:
                    # Fallback para User/Pass
                    connect_kwargs['password'] = self.password
                    log_message = f"User/Pass: {self.user}"
                
                self._connection = ProxmoxAPI(**connect_kwargs)
                self.logger.info(f"Conectado ao Proxmox: {self.host} via {log_message}")
            except Exception as e:
                self.logger.error(f"Erro ao conectar ao Proxmox: {str(e)}")
                # Levanta um erro específico para ser capturado pela rota/controller
                raise ConnectionError(f"Falha ao conectar ao Proxmox: {str(e)}")
        return self._connection

    def _resolve_node_id(self, node_id=None):
        """
        Retorna o ID do node padrão ou o ID do primeiro node se o padrão não estiver definido.
        """
        if node_id:
            return node_id
        
        if self._default_node:
            return self._default_node
        
        # Fallback: tentar obter o primeiro node se o padrão não estiver definido
        if self._cached_first_node_id:
            return self._cached_first_node_id
        
        try:
            nodes = self.connection.nodes.get()
            if nodes:
                first_node = nodes[0]['node']
                self._cached_first_node_id = first_node
                return first_node
        except Exception as e:
            self.logger.warning(f"Não foi possível resolver o Node Padrão: {str(e)}. Verifique PROXMOX_DEFAULT_NODE.")
            raise ResourceException("Não foi possível resolver o Node Padrão.")

    def test_connection(self):
        """Testa se a conexão com a API está ativa."""
        try:
            # Tenta acessar um endpoint simples, como a lista de nodes
            self.connection.nodes.get()
            return {'success': True, 'message': 'Conexão com Proxmox estabelecida com sucesso.'}
        except Exception as e:
            self.logger.error(f"Erro no teste de conexão: {str(e)}")
            return {'success': False, 'error': str(e)}

    # ---------------------------------
    # --- Métodos de Listagem (Node) ---
    # ---------------------------------

    def get_nodes(self):
        """Lista todos os nodes no cluster."""
        try:
            nodes = self.connection.nodes.get()
            return {'success': True, 'data': nodes, 'count': len(nodes)}
        except ResourceException as e:
            self.logger.error(f"Erro ao listar nodes: {str(e)}")
            return {'success': False, 'error': str(e)}

    def get_node_status(self, node_id=None):
        """Obtém o status e informações de um node (padrão se não especificado)."""
        try:
            node_id = self._resolve_node_id(node_id)
            status = self.connection.nodes(node_id).status.get()
            return {'success': True, 'data': status}
        except ResourceException as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao obter status do node {node_ref}: {str(e)}")
            return {'success': False, 'error': str(e)}

    # ------------------------------------
    # --- Métodos de Resource Pool (API) ---
    # ------------------------------------

    def get_pools(self):
        """Lista todos os Resource Pools."""
        try:
            pools = self.connection.pools.get()
            return {
                'success': True,
                'data': pools,
                'count': len(pools)
            }
        except ResourceException as e:
            self.logger.error(f"Erro ao listar pools: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def create_pool(self, poolid, comment=None):
        """Cria um novo Resource Pool."""
        try:
            params = {'poolid': poolid}
            if comment:
                params['comment'] = comment
                
            result = self.connection.pools.post(**params)
            
            return {
                'success': True,
                'data': result,
                'message': f'Pool {poolid} criado com sucesso.'
            }
        except ResourceException as e:
            self.logger.error(f"Erro ao criar pool {poolid}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
            
    def delete_pool(self, poolid):
        """Exclui um Resource Pool."""
        try:
            result = self.connection.pools(poolid).delete()
            return {
                'success': True,
                'data': result,
                'message': f'Pool {poolid} excluído com sucesso.'
            }
        except ResourceException as e:
            self.logger.error(f"Erro ao excluir pool {poolid}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    # ---------------------------
    # --- Métodos de VM (QEMU) ---
    # ---------------------------

    def get_vms(self, node_id=None):
        """Lista todas as VMs (qemu) do node padrão ou do node especificado."""
        try:
            node_id = self._resolve_node_id(node_id)
            vms = self.connection.nodes(node_id).qemu.get()
            return {'success': True, 'data': vms, 'count': len(vms)}
        except ResourceException as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao listar VMs no node {node_ref}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def get_vm_status(self, vmid):
        """Obtém o status de uma VM específica no node padrão."""
        try:
            node_id = self._resolve_node_id()
            status = self.connection.nodes(node_id).qemu(vmid).status.current.get()
            return {'success': True, 'data': status}
        except ResourceException as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao obter status da VM {vmid} no {node_ref}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def create_vm(self, config: dict):
        """Cria uma nova VM no node padrão."""
        try:
            node_id = self._resolve_node_id()
            
            # Ajuste de Mapeamento: 'poolid' da nossa API para 'pool' do PVE
            create_config = {
                'vmid': config.get('vmid'),
                'name': config['name'],
                'cores': config.get('cores', 2),
                'memory': config.get('memory', 2048),
                'net0': config.get('net0', 'virtio,bridge=vmbr0'),
                'scsihw': config.get('scsihw', 'virtio-scsi-pci'),
                'scsi0': config.get('scsi0', f"{config.get('storage', 'local-lvm')}:{config.get('disk_size', 20)}"),
                'pool': config.get('poolid') # <-- Associa a VM ao Resource Pool
            }
            
            # Remove chaves com valor None antes de enviar
            create_config = {k: v for k, v in create_config.items() if v is not None}
            
            result = self.connection.nodes(node_id).qemu.create(**create_config)
            vmid = config.get('vmid') or result.get('vmid')
            
            return {
                'success': True,
                'vmid': vmid,
                'node': node_id,
                'message': f'VM {vmid} criada com sucesso.'
            }
            
        except Exception as e:
            self.logger.error(f"Erro ao criar VM: {str(e)}")
            return {'success': False, 'error': str(e)}

    def start_vm(self, vmid):
        """Inicia uma VM no node padrão."""
        try:
            node_id = self._resolve_node_id()
            result = self.connection.nodes(node_id).qemu(vmid).status.start.post()
            return {'success': True, 'data': result, 'message': f'VM {vmid} iniciada'}
        except ResourceException as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao iniciar VM {vmid} no {node_ref}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def stop_vm(self, vmid):
        """Para uma VM no node padrão."""
        try:
            node_id = self._resolve_node_id()
            result = self.connection.nodes(node_id).qemu(vmid).status.stop.post()
            return {'success': True, 'data': result, 'message': f'VM {vmid} parada'}
        except ResourceException as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao parar VM {vmid} no {node_ref}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def delete_vm(self, vmid):
        """Exclui permanentemente uma VM no node padrão."""
        try:
            node_id = self._resolve_node_id()
            result = self.connection.nodes(node_id).qemu(vmid).delete()
            return {'success': True, 'data': result, 'message': f'VM {vmid} excluída'}
        except ResourceException as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao excluir VM {vmid} no {node_ref}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def update_vm_resources(self, vmid, updates: dict):
        """
        Atualiza recursos de uma VM (QEMU), como memória, cores, etc.
        """
        try:
            node_id = self._resolve_node_id()
            
            # Filtro de parâmetros que podem ser atualizados via PUT /config
            VALID_QEMU_CONFIG_KEYS = ['memory', 'cores', 'sockets', 'cpu', 'name']
            pve_params = {k: v for k, v in updates.items() if k in VALID_QEMU_CONFIG_KEYS}

            if not pve_params:
                self.logger.warning(f"Tentativa de atualizar VM {vmid} sem parâmetros válidos.")
                return {'success': False, 'error': 'Nenhum parâmetro de recurso válido fornecido.'}

            # A atualização é feita com o método PUT no endpoint de configuração
            result = self.connection.nodes(node_id).qemu(vmid).config.put(**pve_params)
            
            return {
                'success': True,
                'data': result,
                'message': f'Atualização de recursos da VM {vmid} iniciada com sucesso.'
            }
        except ResourceException as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao atualizar VM {vmid} no {node_ref}: {str(e)}")
            return {'success': False, 'error': str(e)}


    def get_vnc_console(self, vmid):
        """Obtém informações para console VNC da VM no node padrão."""
        try:
            node_id = self._resolve_node_id()
            
            # NOTA CRÍTICA: O endpoint de ticket VNC **requer** um usuário e senha (User/Pass),
            # mesmo que a conexão principal use um token API.
            ticket_data = self.connection.access.ticket.post(
                username=self.user,
                password=self.password
            )
            
            return {
                'success': True,
                'data': {
                    'host': self.host,
                    'port': 8006, # Porta correta para o console web (websocket)
                    'path': f'/api2/json/nodes/{node_id}/qemu/{vmid}/vncwebsocket',
                    'ticket': ticket_data['ticket'],
                    'vncticket': ticket_data['ticket']
                }
            }
        except Exception as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao obter console VNC da VM {vmid} do {node_ref}: {str(e)}")
            return {'success': False, 'error': str(e)}
        
    # ---------------------------
    # --- Métodos de CTs (LXC) ---
    # ---------------------------

    def get_containers(self, node_id=None):
        """Lista todos os contêineres (LXC) do node padrão ou do node especificado."""
        try:
            node_id = self._resolve_node_id(node_id)
            containers = self.connection.nodes(node_id).lxc.get()
            return {'success': True, 'data': containers, 'count': len(containers)}
        except ResourceException as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao listar CTs no {node_ref}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def get_container_status(self, ctid):
        """Obtém o status de um Contêiner (CT) específico."""
        try:
            node_id = self._resolve_node_id()
            status = self.connection.nodes(node_id).lxc(ctid).status.current.get()
            return {'success': True, 'data': status}
        except ResourceException as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao obter status do CT {ctid} no {node_ref}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def get_container_config(self, ctid):
        """Obtém a configuração completa de um Contêiner LXC no node padrão."""
        try:
            node_id = self._resolve_node_id()
            config = self.connection.nodes(node_id).lxc(ctid).config.get()
            return {'success': True, 'data': config}
        except ResourceException as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao obter config do CT {ctid} no {node_ref}: {str(e)}")
            return {'success': False, 'error': str(e)}


    def create_container(self, config: dict):
        """Cria um novo Contêiner LXC no node padrão."""
        try:
            node_id = self._resolve_node_id()
            
            # Parâmetros mínimos e essenciais para a criação
            create_config = {
                'vmid': config.get('vmid'),
                'ostemplate': config['template'],  # Nome do template LXC
                'hostname': config['name'],
                'memory': config.get('memory', 512),
                'cores': config.get('cores', 1),
                'storage': config.get('storage', 'local-lvm'), # Storage para o disco raiz
                'rootfs': f"{config.get('storage', 'local-lvm')}:{config.get('disk_size', 8)}",
                'net0': config.get('net0', 'name=eth0,bridge=vmbr0,ip=dhcp'),
                'pool': config.get('poolid') # <-- Associa o CT ao Resource Pool
            }
            
            # Remove chaves com valor None antes de enviar
            create_config = {k: v for k, v in create_config.items() if v is not None}

            result = self.connection.nodes(node_id).lxc.post(**create_config)
            ctid = config.get('vmid') or result.get('vmid')
            
            return {
                'success': True,
                'ctid': ctid,
                'node': node_id,
                'message': f'Contêiner {ctid} criado com sucesso.'
            }
            
        except Exception as e:
            self.logger.error(f"Erro ao criar Contêiner: {str(e)}")
            return {'success': False, 'error': str(e)}

    def start_container(self, ctid):
        """Inicia um Contêiner (CT)."""
        try:
            node_id = self._resolve_node_id()
            result = self.connection.nodes(node_id).lxc(ctid).status.start.post()
            return {'success': True, 'data': result, 'message': f'CT {ctid} iniciado'}
        except ResourceException as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao iniciar CT {ctid} no {node_ref}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def stop_container(self, ctid):
        """Para um Contêiner (CT)."""
        try:
            node_id = self._resolve_node_id()
            result = self.connection.nodes(node_id).lxc(ctid).status.stop.post()
            return {'success': True, 'data': result, 'message': f'CT {ctid} parado'}
        except ResourceException as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao parar CT {ctid} no {node_ref}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def delete_container(self, ctid):
        """Exclui um Contêiner (CT)."""
        try:
            node_id = self._resolve_node_id()
            result = self.connection.nodes(node_id).lxc(ctid).delete()
            return {'success': True, 'data': result, 'message': f'CT {ctid} excluído'}
        except ResourceException as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao excluir CT {ctid} no {node_ref}: {str(e)}")
            return {'success': False, 'error': str(e)}
        
    def update_container_resources(self, ctid, updates: dict):
        """
        Atualiza recursos de um Contêiner (CT), como memória, cores e disco.
        """
        try:
            node_id = self._resolve_node_id()
            
            # Filtro simplificado de parâmetros válidos para o endpoint de PUT config
            VALID_LXC_CONFIG_KEYS = ['memory', 'cores', 'rootfs', 'swap', 'net0', 'hostname']
            pve_params = {k: v for k, v in updates.items() if k in VALID_LXC_CONFIG_KEYS}

            if not pve_params:
                self.logger.warning(f"Tentativa de atualizar CT {ctid} sem parâmetros válidos.")
                return {'success': False, 'error': 'Nenhum parâmetro de recurso válido fornecido.'}

            # A atualização é feita com o método PUT no endpoint de configuração
            result = self.connection.nodes(node_id).lxc(ctid).config.put(**pve_params)
            
            return {
                'success': True,
                'data': result,
                'message': f'Atualização de recursos do CT {ctid} iniciada com sucesso.'
            }
        except ResourceException as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao atualizar CT {ctid} no {node_ref}: {str(e)}")
            return {'success': False, 'error': str(e)}
        
    # ---------------------------
    # --- Métodos de Storage ---
    # ---------------------------

    def get_storages(self, node_id=None):
        """Lista todos os storages do cluster ou do node padrão/especificado."""
        try:
            # Lista todos os storages do cluster (endpoint /storage)
            storages = self.connection.storage.get()
            return {'success': True, 'data': storages, 'count': len(storages)}
        except ResourceException as e:
            self.logger.error(f"Erro ao listar storages: {str(e)}")
            return {'success': False, 'error': str(e)}

    def get_storage_status(self, storage_id, node_id=None):
        """Obtém status de um storage específico no node padrão/especificado."""
        try:
            node_id = self._resolve_node_id(node_id)
            # Retorna o status de um storage em um node
            status = self.connection.nodes(node_id).storage(storage_id).status.get()
            return {'success': True, 'data': status}
        except ResourceException as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao obter status do storage {storage_id} no {node_ref}: {str(e)}")
            return {'success': False, 'error': str(e)}
        
    def get_storage_content(self, storage_id, node_id=None):
        """Lista o conteúdo de um storage (templates, imagens, etc.) no node padrão/especificado."""
        try:
            node_id = self._resolve_node_id(node_id)
            # O endpoint /content lista o conteúdo
            content = self.connection.nodes(node_id).storage(storage_id).content.get()
            return {'success': True, 'data': content, 'count': len(content)}
        except ResourceException as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao listar conteúdo do storage {storage_id} no {node_ref}: {str(e)}")
            return {'success': False, 'error': str(e)}