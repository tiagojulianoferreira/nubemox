from proxmoxer import ProxmoxAPI, ResourceException
from flask import current_app
import logging

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
        
        # Renomeado no config para PROXMOX_DEFAULT_NODE 
        default_node_config = self.config.get('PROXMOX_DEFAULT_NODE')
        self._default_node = default_node or default_node_config
        
        self.verify_ssl = verify_ssl if verify_ssl is not None else self.config['PROXMOX_VERIFY_SSL']
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
                raise
        return self._connection

    @property
    def default_node(self):
        """Retorna o node padrão configurado ou o primeiro node do cluster."""
        # Código para resolver o node ID omitido por brevidade, mas o método anterior é mantido.
        if self._default_node:
            return self._default_node
        
        if self._cached_first_node_id:
            return self._cached_first_node_id
            
        try:
            nodes_data = self.get_nodes()
            if nodes_data['success'] and nodes_data['count'] > 0:
                first_node_id = nodes_data['data'][0]['node']
                self._cached_first_node_id = first_node_id
                self.logger.info(f"Node padrão não definido. Usando o primeiro node do cluster: {first_node_id}")
                return first_node_id
            else:
                self.logger.error("Não foi possível determinar o Node padrão: Cluster vazio ou inacessível.")
                return None
        except Exception as e:
            self.logger.error(f"Erro fatal ao tentar determinar o node padrão: {str(e)}")
            return None

    def _resolve_node_id(self):
        """Função auxiliar para resolver o node ID, usando apenas a propriedade default_node."""
        node_id = self.default_node
        if not node_id:
            self.logger.error("Node ID é obrigatório e não pôde ser determinado automaticamente.")
            raise ValueError("Node ID é obrigatório: configure PROXMOX_DEFAULT_NODE ou adicione um node ao cluster.")
        return node_id
    
    # ... (Métodos de Listagem e Status, mantidos) ...
    
    def test_connection(self):
        """Testa a conexão com o Proxmox"""
        try:
            version = self.connection.version.get()
            return {
                'success': True,
                'version': version.get('version', 'Unknown'),
                'release': version.get('release', 'Unknown'),
                'host': self.host
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'host': self.host
            }
    
    def get_nodes(self):
        """Lista todos os nodes do cluster"""
        try:
            nodes = self.connection.nodes.get()
            return {
                'success': True,
                'data': nodes,
                'count': len(nodes)
            }
        except ResourceException as e:
            self.logger.error(f"Erro ao listar nodes: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_node_status(self):
        """Obtém status do node padrão."""
        try:
            node_id = self._resolve_node_id()
            status = self.connection.nodes(node_id).status.get()
            return {
                'success': True,
                'data': status
            }
        except Exception as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao obter status do {node_ref}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_vms(self):
        """Lista todas as VMs do node padrão."""
        try:
            node_id = self._resolve_node_id()
            vms = self.connection.nodes(node_id).qemu.get()
            return {
                'success': True,
                'data': vms,
                'count': len(vms)
            }
        except Exception as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao listar VMs do {node_ref}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_vm_status(self, vmid):
        """Obtém status de uma VM específica no node padrão."""
        try:
            node_id = self._resolve_node_id()
            status = self.connection.nodes(node_id).qemu(vmid).status.current.get()
            return {
                'success': True,
                'data': status
            }
        except ResourceException as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao obter status da VM {vmid} no {node_ref}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_containers(self):
        """Lista todos os containers LXC do node padrão."""
        try:
            node_id = self._resolve_node_id()
            containers = self.connection.nodes(node_id).lxc.get()
            return {
                'success': True,
                'data': containers,
                'count': len(containers)
            }
        except Exception as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao listar containers do {node_ref}: {str(e)}")
            return {
                'success': False,
                'error': str(e)}
    def get_container_status(self, ctid):
        """Obtém status de um Contêiner LXC específico no node padrão."""
        try:
            node_id = self._resolve_node_id()
            # LXC usa 'lxc' em vez de 'qemu' na API
            status = self.connection.nodes(node_id).lxc(ctid).status.current.get()
            return {
                'success': True,
                'data': status
            }
        except ResourceException as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao obter status do Contêiner {ctid} no {node_ref}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    def get_storage(self):
        """Lista storage disponível no node padrão."""
        try:
            node_id = self._resolve_node_id()
            storage = self.connection.nodes(node_id).storage.get()
            return {
                'success': True,
                'data': storage,
                'count': len(storage)
            }
        except Exception as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao listar storage do {node_ref}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_templates(self):
        """Lista templates disponíveis (VMs marcadas como template) no node padrão."""
        try:
            node_id = self._resolve_node_id()
            all_vms = self.connection.nodes(node_id).qemu.get()
            templates = [vm for vm in all_vms if vm.get('template') == 1]
            return {
                'success': True,
                'data': templates,
                'count': len(templates)
            }
        except Exception as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao listar templates do {node_ref}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    # --- Métodos de Criação de VM (Mantidos) ---
    
    def _clone_vm(self, node_id, config):
        """Lógica para clonar uma VM a partir de um template."""
        template_vmid = config['template']
        clone_config = {
            'newid': config.get('vmid'),
            'name': config['name'],
            'full': 1,
            'storage': config.get('storage', 'local-lvm')
        }
        result = self.connection.nodes(node_id).qemu(template_vmid).clone.create(**clone_config)
        vmid = result['newid']
        update_config = {}
        if 'cores' in config:
            update_config['cores'] = config['cores']
        if 'memory' in config:
            update_config['memory'] = config['memory']
        if update_config:
            self.connection.nodes(node_id).qemu(vmid).config.put(**update_config)
            
        return vmid


    def _create_bare_vm(self, node_id, config):
        """Lógica para criar uma VM do zero (sem template)."""
        create_config = {
            'vmid': config.get('vmid'),
            'name': config['name'],
            'cores': config.get('cores', 2),
            'memory': config.get('memory', 2048),
            'net0': 'virtio,bridge=vmbr0',
            'scsihw': 'virtio-scsi-pci',
            'scsi0': f"{config.get('storage', 'local-lvm')}:{config.get('disk_size', 20)}"
        }
        result = self.connection.nodes(node_id).qemu.create(**create_config)
        vmid = config.get('vmid') or result.get('vmid')
        return vmid

    def create_vm(self, config):
        """Cria uma nova VM no node padrão, usando clonagem ou criação do zero."""
        try:
            node_id = self._resolve_node_id()
            
            if 'template' in config:
                vmid = self._clone_vm(node_id, config)
            else:
                vmid = self._create_bare_vm(node_id, config)
            
            return {
                'success': True,
                'vmid': vmid,
                'node': node_id,
                'message': f'VM {vmid} criada com sucesso'
            }
            
        except Exception as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao criar VM no {node_ref}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
            
    # --- NOVO: Método de Criação de Container ---
    
    def create_container(self, config):
        """Cria um novo Contêiner LXC no node padrão."""
        try:
            node_id = self._resolve_node_id()
            
            # Mapeia chaves de configuração básicas (ostemplate é obrigatório)
            create_config = {
                'vmid': config.get('vmid'),
                'ostemplate': config['template'], # Na rota está 'template', no proxmoxer é 'ostemplate'
                'hostname': config.get('name'),
                'cores': config.get('cores', 1),
                'memory': config.get('memory', 512),
                'rootfs': f"{config.get('storage', 'local')}:{config.get('disk_size', 8)}",
                'net0': 'name=eth0,bridge=vmbr0,ip=dhcp',
                'password': config.get('password')
            }

            # Remove None values
            create_config = {k: v for k, v in create_config.items() if v is not None}
            
            result = self.connection.nodes(node_id).lxc.create(**create_config)
            ctid = config.get('vmid') or result.get('vmid')
            
            return {
                'success': True,
                'ctid': ctid,
                'node': node_id,
                'message': f'Contêiner {ctid} criado com sucesso'
            }
            
        except Exception as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao criar Contêiner no {node_ref}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    # --- Métodos de Ação (VMs) Mantidos ---

    def start_vm(self, vmid):
        """Inicia uma VM no node padrão."""
        try:
            node_id = self._resolve_node_id()
            result = self.connection.nodes(node_id).qemu(vmid).status.start.post()
            return {
                'success': True,
                'data': result,
                'message': f'VM {vmid} iniciada'
            }
        except ResourceException as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao iniciar VM {vmid} no {node_ref}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def stop_vm(self, vmid):
        """Para uma VM no node padrão."""
        try:
            node_id = self._resolve_node_id()
            result = self.connection.nodes(node_id).qemu(vmid).status.stop.post()
            return {
                'success': True,
                'data': result,
                'message': f'VM {vmid} parada'
            }
        except ResourceException as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao parar VM {vmid} no {node_ref}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
            
    # --- NOVO: Métodos de Ação (Containers) ---

    def start_container(self, ctid):
        """Inicia um Contêiner LXC no node padrão."""
        try:
            node_id = self._resolve_node_id()
            result = self.connection.nodes(node_id).lxc(ctid).status.start.post()
            return {
                'success': True,
                'data': result,
                'message': f'Contêiner {ctid} iniciado'
            }
        except ResourceException as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao iniciar Contêiner {ctid} no {node_ref}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def stop_container(self, ctid):
        """Para um Contêiner LXC no node padrão."""
        try:
            node_id = self._resolve_node_id()
            result = self.connection.nodes(node_id).lxc(ctid).status.stop.post()
            return {
                'success': True,
                'data': result,
                'message': f'Contêiner {ctid} parado'
            }
        except ResourceException as e:
            node_ref = node_id if node_id else "Node (não resolvido)"
            self.logger.error(f"Erro ao parar Contêiner {ctid} no {node_ref}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_vnc_console(self, vmid):
        """Obtém informações para console VNC da VM no node padrão."""
        try:
            node_id = self._resolve_node_id()
            
            # NOTA: O endpoint de ticket VNC requer um usuário e senha (não um token API).
            # Usamos o user/pass de fallback, que o usuário deve manter configurado.
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
            return {
                'success': False,
                'error': str(e)
            }
    # --- Métodos de Resource Pool ---
    
    def get_pools(self):
        """Lista todos os Resource Pools do cluster."""
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
            
    def create_pool(self, poolid, comment=""):
        """Cria um novo Resource Pool."""
        try:
            # A criação é feita via POST no endpoint /pools
            result = self.connection.pools.post(poolid=poolid, comment=comment)
            return {
                'success': True,
                'message': f"Pool '{poolid}' criado com sucesso.",
                'data': result
            }
        except ResourceException as e:
            self.logger.error(f"Erro ao criar pool '{poolid}': {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def add_pool_member(self, poolid, vmid):
        """Adiciona uma VM/CT (vmid) a um Resource Pool."""
        try:
            # A atualização de membros é feita enviando a lista completa via PUT
            
            # 1. Obter membros atuais (se o pool existir)
            pool_data = self.connection.pools(poolid).get()
            members = pool_data.get('members', [])
            
            # Formato esperado: 'type/id', ex: 'qemu/101', 'lxc/201'
            # O Proxmoxer espera que você envie o ID da VM/CT puro: 101, 201
            
            # Verificação se o membro já existe
            is_vm = True if vmid >= 100 else False # Heurística simples
            member_type = 'qemu' if is_vm else 'lxc'
            
            # Verifica se o recurso existe e adiciona ao pool se não estiver lá
            if not any(m['vmid'] == vmid for m in members):
                members.append({'vmid': vmid, 'type': member_type, 'node': self._resolve_node_id()})
            else:
                self.logger.warning(f"Membro {vmid} já está no pool {poolid}.")
                return {'success': True, 'message': f"Membro {vmid} já está no pool {poolid}."}

            # 2. Reenviar a lista completa de membros via PUT
            # O Proxmoxer requer a lista de IDs de VMS/CTs no parâmetro 'vms'
            vm_list = [str(m['vmid']) for m in members]
            
            # O endpoint PUT /pools/{poolid} espera o parâmetro 'vms' como uma string separada por vírgulas
            result = self.connection.pools(poolid).put(vms=','.join(vm_list))
            
            return {
                'success': True,
                'message': f"Membro {vmid} adicionado ao pool '{poolid}'.",
                'data': result
            }
        except ResourceException as e:
            self.logger.error(f"Erro ao adicionar membro {vmid} ao pool {poolid}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def list_pool_vms(self, poolid):
        """Lista as VMs e CTs que são membros de um Resource Pool específico."""
        try:
            # Ao buscar o pool, os membros são retornados
            pool_data = self.connection.pools(poolid).get()
            members = pool_data.get('members', [])
            
            vms_and_cts = []
            for member in members:
                vms_and_cts.append({
                    'vmid': member.get('vmid'),
                    'type': 'VM' if member.get('type') == 'qemu' else 'CT',
                    'node': member.get('node'),
                    # Informação de status básica pode ser adicionada aqui se necessário
                })
            
            return {
                'success': True,
                'data': vms_and_cts,
                'count': len(vms_and_cts)
            }
        except ResourceException as e:
            self.logger.error(f"Erro ao listar membros do pool {poolid}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }