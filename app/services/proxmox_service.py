from proxmoxer import ProxmoxAPI, ResourceException
from flask import current_app
import logging
import re
import time # Necessário para o polling

# --- Nova Exceção de Tratamento de Erros Assíncronos ---
class ProxmoxTaskFailedError(Exception):
    """Exceção levantada quando uma tarefa do Proxmox retorna um status de falha."""
    pass

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

    # -------------------------------------------------------------
    # --- NOVO: Métodos Auxiliares de Gerenciamento de Tarefas  ---
    # -------------------------------------------------------------

    def _wait_for_task_completion(self, task_upid, node_id: str):
        """
        Monitora o status de uma tarefa assíncrona do Proxmox usando polling.
        Recebe o UPID (string) retornado pelas chamadas assíncronas do proxmoxer.
        """
        # Se não for uma string de UPID válida, retorna imediatamente (operação síncrona)
        if not task_upid or not isinstance(task_upid, str) or not task_upid.startswith('UPID:'):
            return

        start_time = time.time()
        timeout = self.config.get('PROXMOX_TASK_TIMEOUT', 300)
        poll_interval = self.config.get('PROXMOX_TASK_POLL_INTERVAL', 5)

        self.logger.info(f"Iniciando polling da tarefa UPID: {task_upid} (Timeout: {timeout}s)")

        while (time.time() - start_time) < timeout:
            try:
                # Endpoint PVE para verificar o status da tarefa
                task_status = self.connection.nodes(node_id).tasks(task_upid).status.get()
                
                # Se 'status' = 'stopped', a tarefa terminou
                if task_status.get('status') == 'stopped':
                    if task_status.get('exitstatus') == 'OK':
                        self.logger.info(f"Tarefa UPID: {task_upid} concluída com sucesso.")
                        return 
                    else:
                        # A tarefa falhou no PVE
                        error_message = task_status.get('exitstatus', 'Falha desconhecida na tarefa PVE.')
                        self.logger.error(f"Tarefa UPID: {task_upid} falhou: {error_message}")
                        raise ProxmoxTaskFailedError(f"A operação do Proxmox falhou: {error_message}")

            except ResourceException as e:
                self.logger.error(f"Erro ao buscar status da tarefa {task_upid}: {str(e)}")
                # Se o erro for de conexão, tentamos novamente; se for fatal, raise
                raise e 
            except Exception as e:
                self.logger.error(f"Erro inesperado durante o polling: {str(e)}")
                raise

            time.sleep(poll_interval)

        raise TimeoutError(f"A tarefa do Proxmox (UPID: {task_upid}) excedeu o tempo limite de {timeout} segundos.")

    def _resolve_node_id(self, node_id=None):
        if node_id:
            return node_id
        if self._default_node:
            return self._default_node
        if self._cached_first_node_id:
            return self._cached_first_node_id
        try:
            nodes = self.connection.nodes.get()
            if nodes:
                first_node = nodes[0]['node']
                self._cached_first_node_id = first_node
                return first_node
        except Exception as e:
            self.logger.warning(f"Não foi possível resolver o Node Padrão: {str(e)}")
            raise ResourceException("Não foi possível resolver o Node Padrão.")

    def test_connection(self):
        try:
            self.connection.nodes.get()
            return {'success': True, 'message': 'Conexão com Proxmox estabelecida com sucesso.'}
        except Exception as e:
            self.logger.error(f"Erro no teste de conexão: {str(e)}")
            return {'success': False, 'error': str(e)}

    def get_nodes(self):
        try:
            nodes = self.connection.nodes.get()
            return {'success': True, 'data': nodes, 'count': len(nodes)}
        except ResourceException as e:
            self.logger.error(f"Erro ao listar nodes: {str(e)}")
            return {'success': False, 'error': str(e)}

    def get_node_status(self, node_id=None):
        try:
            node_id = self._resolve_node_id(node_id)
            status = self.connection.nodes(node_id).status.get()
            return {'success': True, 'data': status}
        except ResourceException as e:
            self.logger.error(f"Erro ao obter status do node: {str(e)}")
            return {'success': False, 'error': str(e)}

    # ------------------------------------
    # --- Métodos de Resource Pool ---
    # ------------------------------------

    def get_pools(self):
        try:
            pools = self.connection.pools.get()
            return {'success': True, 'data': pools, 'count': len(pools)}
        except ResourceException as e:
            self.logger.error(f"Erro ao listar pools: {str(e)}")
            return {'success': False, 'error': str(e)}

    def create_pool(self, poolid, comment=None):
        try:
            params = {'poolid': poolid}
            if comment:
                params['comment'] = comment
            self.connection.pools.post(**params)
            return {'success': True, 'message': f'Pool {poolid} criado com sucesso.'}
        except ResourceException as e:
            self.logger.error(f"Erro ao criar pool {poolid}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def provision_user_pool(self, username: str):
        poolid = f"vps-{username.lower()}"
        comment = f"Pool dedicado ao usuário: {username}"
        try:
            params = {'poolid': poolid, 'comment': comment}
            self.connection.pools.post(**params)
            return {'success': True, 'poolid': poolid, 'message': f'Pool "{poolid}" criado.'}
        except ResourceException as e:
            if 'poolid already exists' in str(e):
                 return {'success': False, 'error': f'Pool "{poolid}" já existe.', 'proxmox_error': str(e)}
            self.logger.error(f"Erro ao provisionar pool {poolid}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def deprovision_user_pool(self, username: str):
        poolid = f"vps-{username.lower()}"
        try:
            self.connection.pools(poolid).delete()
            return {'success': True, 'poolid': poolid, 'message': f'Pool "{poolid}" excluído.'}
        except ResourceException as e:
            if 'not found' in str(e):
                 return {'success': False, 'error': f'Pool "{poolid}" não encontrado.'}
            if 'still has members' in str(e):
                 return {'success': False, 'error': f'Pool "{poolid}" não está vazio.'}
            self.logger.error(f"Erro ao desprovisionar pool {poolid}: {str(e)}")
            return {'success': False, 'error': str(e)}

    # ---------------------------
    # --- Métodos de VM (QEMU) ---
    # ---------------------------

    def get_vms(self, node_id=None):
        try:
            node_id = self._resolve_node_id(node_id)
            vms = self.connection.nodes(node_id).qemu.get()
            return {'success': True, 'data': vms, 'count': len(vms)}
        except ResourceException as e:
            self.logger.error(f"Erro ao listar VMs: {str(e)}")
            return {'success': False, 'error': str(e)}

    def get_vm_status(self, vmid):
        try:
            node_id = self._resolve_node_id()
            status = self.connection.nodes(node_id).qemu(vmid).status.current.get()
            return {'success': True, 'data': status}
        except ResourceException as e:
            self.logger.error(f"Erro ao obter status da VM {vmid}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def create_vm(self, config: dict):
        """Cria uma nova VM. Se 'vmid' não for informado, gera automaticamente."""
        try:
            node_id = self._resolve_node_id()
            
            # 1. Lógica de VMID Automático
            vmid = config.get('vmid')
            if not vmid:
                vmid = self._get_next_vmid()
            
            create_config = {
                'vmid': vmid,
                'name': config['name'],
                'cores': config.get('cores', 2),
                'memory': config.get('memory', 2048),
                'net0': config.get('net0', 'virtio,bridge=vmbr0'),
                'scsihw': config.get('scsihw', 'virtio-scsi-pci'),
                'scsi0': config.get('scsi0', f"{config.get('storage', 'local-lvm')}:{config.get('disk_size', 20)}"),
                'pool': config.get('poolid')
            }
            create_config = {k: v for k, v in create_config.items() if v is not None}
            
            # Chamada Assíncrona
            upid = self.connection.nodes(node_id).qemu.create(**create_config)
            
            # Polling
            self._wait_for_task_completion(upid, node_id)
            
            return {
                'success': True,
                'vmid': vmid, # Retorna o ID gerado
                'message': f'VM {vmid} criada e provisionada com sucesso.'
            }
            
        except (ResourceException, TimeoutError, ProxmoxTaskFailedError, Exception) as e:
            self.logger.error(f"Erro ao criar VM: {str(e)}")
            return {'success': False, 'error': str(e)}

    def start_vm(self, vmid):
        try:
            node_id = self._resolve_node_id()
            upid = self.connection.nodes(node_id).qemu(vmid).status.start.post()
            self._wait_for_task_completion(upid, node_id)
            return {'success': True, 'message': f'VM {vmid} iniciada'}
        except Exception as e:
            self.logger.error(f"Erro ao iniciar VM {vmid}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def stop_vm(self, vmid):
        try:
            node_id = self._resolve_node_id()
            upid = self.connection.nodes(node_id).qemu(vmid).status.stop.post()
            self._wait_for_task_completion(upid, node_id)
            return {'success': True, 'message': f'VM {vmid} parada'}
        except Exception as e:
            self.logger.error(f"Erro ao parar VM {vmid}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def delete_vm(self, vmid):
        try:
            node_id = self._resolve_node_id()
            upid = self.connection.nodes(node_id).qemu(vmid).delete()
            self._wait_for_task_completion(upid, node_id)
            return {'success': True, 'message': f'VM {vmid} excluída'}
        except Exception as e:
            self.logger.error(f"Erro ao excluir VM {vmid}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def assign_vm_to_pool(self, vmid, poolid):
        try:
            node_id = self._resolve_node_id()
            params = {'pool': poolid if poolid else ''} 
            self.connection.nodes(node_id).qemu(vmid).config.put(**params)
            msg = f"VM {vmid} atribuída ao Pool '{poolid}'." if poolid else f"VM {vmid} removida do Pool."
            return {'success': True, 'message': msg}
        except ResourceException as e:
            self.logger.error(f"Erro ao atribuir VM {vmid} ao Pool: {str(e)}")
            return {'success': False, 'error': str(e)}

    def get_vnc_console(self, vmid):
        try:
            node_id = self._resolve_node_id()
            ticket_data = self.connection.access.ticket.post(username=self.user, password=self.password)
            return {
                'success': True,
                'data': {
                    'host': self.host,
                    'port': 8006,
                    'path': f'/api2/json/nodes/{node_id}/qemu/{vmid}/vncwebsocket',
                    'ticket': ticket_data['ticket'],
                    'vncticket': ticket_data['ticket']
                }
            }
        except Exception as e:
            self.logger.error(f"Erro ao obter console VNC: {str(e)}")
            return {'success': False, 'error': str(e)}
        
    # ---------------------------
    # --- Métodos de CTs (LXC) ---
    # ---------------------------

    def get_containers(self, node_id=None):
        try:
            node_id = self._resolve_node_id(node_id)
            containers = self.connection.nodes(node_id).lxc.get()
            return {'success': True, 'data': containers, 'count': len(containers)}
        except ResourceException as e:
            self.logger.error(f"Erro ao listar CTs: {str(e)}")
            return {'success': False, 'error': str(e)}

    def get_container_status(self, ctid):
        try:
            node_id = self._resolve_node_id()
            status = self.connection.nodes(node_id).lxc(ctid).status.current.get()
            return {'success': True, 'data': status}
        except ResourceException as e:
            self.logger.error(f"Erro ao obter status do CT {ctid}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def get_container_config(self, ctid):
        try:
            node_id = self._resolve_node_id()
            config = self.connection.nodes(node_id).lxc(ctid).config.get()
            return {'success': True, 'data': config}
        except ResourceException as e:
            self.logger.error(f"Erro ao obter config do CT {ctid}: {str(e)}")
            return {'success': False, 'error': str(e)}
    # --- Método Auxiliar para Obter Próximo VMID ---
    
    def _get_next_vmid(self):
        """Consulta o cluster para obter o próximo VMID livre."""
        try:
            # Endpoint: /cluster/nextid
            return self.connection.cluster.nextid.get()
        except Exception as e:
            self.logger.error(f"Erro ao obter nextid: {str(e)}")
            raise ResourceException(f"Não foi possível obter um ID livre para o recurso: {str(e)}")
    

    def start_container(self, ctid):
        try:
            node_id = self._resolve_node_id()
            upid = self.connection.nodes(node_id).lxc(ctid).status.start.post()
            self._wait_for_task_completion(upid, node_id)
            return {'success': True, 'message': f'CT {ctid} iniciado'}
        except Exception as e:
            self.logger.error(f"Erro ao iniciar CT {ctid}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def stop_container(self, ctid):
        try:
            node_id = self._resolve_node_id()
            upid = self.connection.nodes(node_id).lxc(ctid).status.stop.post()
            self._wait_for_task_completion(upid, node_id)
            return {'success': True, 'message': f'CT {ctid} parado'}
        except Exception as e:
            self.logger.error(f"Erro ao parar CT {ctid}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def delete_container(self, ctid):
        try:
            node_id = self._resolve_node_id()
            upid = self.connection.nodes(node_id).lxc(ctid).delete()
            self._wait_for_task_completion(upid, node_id)
            return {'success': True, 'message': f'CT {ctid} excluído'}
        except Exception as e:
            self.logger.error(f"Erro ao excluir CT {ctid}: {str(e)}")
            return {'success': False, 'error': str(e)}
        
    def update_container_resources(self, ctid, updates: dict):
        try:
            node_id = self._resolve_node_id()
            VALID_LXC_CONFIG_KEYS = ['memory', 'cores', 'rootfs', 'swap', 'net0', 'hostname']
            pve_params = {k: v for k, v in updates.items() if k in VALID_LXC_CONFIG_KEYS}

            if not pve_params:
                return {'success': False, 'error': 'Nenhum parâmetro válido fornecido.'}

            # Config update é assíncrono para alguns parâmetros (ex: resize disk)
            # Para segurança, tratamos o retorno como possível UPID
            result = self.connection.nodes(node_id).lxc(ctid).config.put(**pve_params)
            
            # Se retornar UPID (string), faz polling. Se for null (dict vazio), é síncrono.
            if isinstance(result, str) and result.startswith("UPID:"):
                self._wait_for_task_completion(result, node_id)
            
            return {'success': True, 'message': f'Recursos do CT {ctid} atualizados.'}
        except Exception as e:
            self.logger.error(f"Erro ao atualizar CT {ctid}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def assign_ct_to_pool(self, ctid, poolid):
        try:
            node_id = self._resolve_node_id()
            params = {'pool': poolid if poolid else ''}
            self.connection.nodes(node_id).lxc(ctid).config.put(**params)
            msg = f"CT {ctid} atribuído ao Pool '{poolid}'." if poolid else f"CT {ctid} removido do Pool."
            return {'success': True, 'message': msg}
        except ResourceException as e:
            self.logger.error(f"Erro ao atribuir CT {ctid} ao Pool: {str(e)}")
            return {'success': False, 'error': str(e)}

    # --- Métodos de Storage ---
    def get_storages(self, node_id=None):
        try:
            storages = self.connection.storage.get()
            return {'success': True, 'data': storages, 'count': len(storages)}
        except ResourceException as e:
            self.logger.error(f"Erro ao listar storages: {str(e)}")
            return {'success': False, 'error': str(e)}

    def get_storage_status(self, storage_id, node_id=None):
        try:
            node_id = self._resolve_node_id(node_id)
            status = self.connection.nodes(node_id).storage(storage_id).status.get()
            return {'success': True, 'data': status}
        except ResourceException as e:
            self.logger.error(f"Erro ao obter status do storage: {str(e)}")
            return {'success': False, 'error': str(e)}
        
    def get_storage_content(self, storage_id, node_id=None):
        try:
            node_id = self._resolve_node_id(node_id)
            content = self.connection.nodes(node_id).storage(storage_id).content.get()
            return {'success': True, 'data': content, 'count': len(content)}
        except ResourceException as e:
            self.logger.error(f"Erro ao listar conteúdo do storage: {str(e)}")
            return {'success': False, 'error': str(e)}
    def assign_resource_to_pool(self, vmid, poolid, resource_type='vm'):
        """
        Atribui uma VM ou CT a um Resource Pool.
        Se poolid for None/Vazio, tenta remover do pool atual (lógica complexa, requer busca).
        """
        try:
            # Se poolid for vazio, precisamos descobrir qual é o pool atual para remover
            if not poolid:
                return self._remove_from_any_pool(vmid)

            # Para atribuir, usamos PUT /pools/{poolid} com o parâmetro 'vms'
            # O parâmetro 'vms' espera uma lista de IDs. Para adicionar, precisamos tomar cuidado
            # para não sobrescrever os membros existentes. 
            # Mas o endpoint PUT /pools/{poolid} do Proxmoxer tem um comportamento de 'update'
            # se passarmos apenas o vmid que queremos adicionar? NÃO. Ele substitui a lista.
            
            # A estratégia correta e segura para ADICIONAR é:
            # 1. Obter membros atuais
            pool_info = self.connection.pools(poolid).get()
            current_members = [str(member['vmid']) for member in pool_info.get('members', [])]
            
            # 2. Adicionar o novo ID se não estiver lá
            if str(vmid) not in current_members:
                current_members.append(str(vmid))
                
                # 3. Enviar a lista atualizada
                # allow_move=1 permite mover de outro pool se já estiver em um
                self.connection.pools(poolid).put(vms=','.join(current_members), allow_move=1)
                
            return {
                'success': True,
                'message': f"Recurso {vmid} atribuído ao Pool '{poolid}' com sucesso."
            }

        except ResourceException as e:
            self.logger.error(f"Erro ao atribuir recurso {vmid} ao Pool {poolid}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def _remove_from_any_pool(self, vmid):
        """Helper para encontrar o pool de um recurso e removê-lo."""
        try:
            # 1. Listar todos os pools para encontrar onde o vmid está
            pools = self.connection.pools.get()
            target_pool = None
            
            for pool in pools:
                poolid = pool['poolid']
                members = self.connection.pools(poolid).get().get('members', [])
                for member in members:
                    if str(member['vmid']) == str(vmid):
                        target_pool = poolid
                        break
                if target_pool:
                    break
            
            if not target_pool:
                return {'success': True, 'message': f"Recurso {vmid} não estava em nenhum pool."}

            # 2. Remover do pool encontrado (Atualizar lista sem o vmid)
            pool_info = self.connection.pools(target_pool).get()
            current_members = [str(m['vmid']) for m in pool_info.get('members', []) if str(m['vmid']) != str(vmid)]
            
            self.connection.pools(target_pool).put(vms=','.join(current_members))
            
            return {'success': True, 'message': f"Recurso {vmid} removido do Pool '{target_pool}'."}

        except ResourceException as e:
            return {'success': False, 'error': f"Erro ao remover do pool: {str(e)}"}

    # Wrappers para manter compatibilidade com as rotas
    def assign_vm_to_pool(self, vmid, poolid):
        return self.assign_resource_to_pool(vmid, poolid, 'vm')

    def assign_ct_to_pool(self, ctid, poolid):
        return self.assign_resource_to_pool(ctid, poolid, 'ct')
    
    # ---------------------------
    # --- Métodos de Firewall ---
    # ---------------------------

    def enable_container_firewall(self, ctid):
        """
        Habilita o firewall para um Contêiner LXC.
        Ativa o firewall global do CT (via options) e na interface net0 (via config).
        """
        try:
            node_id = self._resolve_node_id()
            
            # 1. Habilita o firewall nas opções de Firewall do CT (Endpoint correto)
            # Endpoint: /nodes/{node}/lxc/{vmid}/firewall/options
            self.connection.nodes(node_id).lxc(ctid).firewall.options.put(enable=1)
            
            # 2. Habilita o firewall na interface de rede net0
            # Endpoint: /nodes/{node}/lxc/{vmid}/config
            config = self.connection.nodes(node_id).lxc(ctid).config.get()
            net0_conf = config.get('net0', '')
            
            # Verifica se já está habilitado na interface para evitar restart de rede desnecessário
            if 'firewall=1' not in net0_conf:
                # Adiciona a flag firewall=1 à string existente (ex: name=eth0,bridge=vmbr0,ip=dhcp,firewall=1)
                new_net0 = f"{net0_conf},firewall=1"
                self.connection.nodes(node_id).lxc(ctid).config.put(net0=new_net0)
                
            return {'success': True, 'message': f'Firewall habilitado com sucesso para o CT {ctid}.'}
            
        except ResourceException as e:
            self.logger.error(f"Erro ao habilitar firewall do CT {ctid}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def add_firewall_rule(self, ctid, rule: dict):
        """
        Adiciona uma regra de firewall ao Contêiner.
        rule dict deve conter: 
          - type: 'in' | 'out' (direção)
          - action: 'ACCEPT' | 'DROP' | 'REJECT'
          - proto: 'tcp' | 'udp' (opcional)
          - dport: porta destino (opcional, ex: '22', '80')
          - source: IP origem (opcional)
          - comment: descrição
        """
        try:
            node_id = self._resolve_node_id()
            
            # Parâmetros obrigatórios e defaults
            params = {
                'type': rule.get('type', 'in'),
                'action': rule.get('action', 'ACCEPT'),
                'enable': 1
            }
            
            # Parâmetros opcionais
            if rule.get('proto'): params['proto'] = rule['proto']
            if rule.get('dport'): params['dport'] = rule['dport']
            if rule.get('source'): params['source'] = rule['source']
            if rule.get('comment'): params['comment'] = rule['comment']
            
            # Endpoint: /nodes/{node}/lxc/{vmid}/firewall/rules
            self.connection.nodes(node_id).lxc(ctid).firewall.rules.post(**params)
            
            return {
                'success': True, 
                'message': f"Regra de firewall ({params['action']} {params.get('dport', 'ALL')}) adicionada ao CT {ctid}."
            }
            
        except ResourceException as e:
            self.logger.error(f"Erro ao adicionar regra de firewall no CT {ctid}: {str(e)}")
            return {'success': False, 'error': str(e)}