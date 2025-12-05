from proxmoxer import ProxmoxAPI, ResourceException
from flask import current_app
import logging
import time

# --- Nova Exceção de Tratamento de Erros Assíncronos ---
class ProxmoxTaskFailedError(Exception):
    """Exceção levantada quando uma tarefa do Proxmox retorna um status de falha."""
    pass

class ProxmoxService:
    """
    Serviço para integração com API do Proxmox VE.
    Prioriza autenticação via API Token. Lança exceções para serem tratadas pelo Global Handler.
    """
    
    def __init__(self, host=None, user=None, password=None, verify_ssl=None, default_node=None, token_name=None, token_value=None):
        self.config = current_app.config
        self.host = host or self.config['PROXMOX_HOST']
        
        self.user = user or self.config['PROXMOX_USER']
        self.password = password or self.config['PROXMOX_PASSWORD']
        
        self.token_name = token_name or self.config.get('PROXMOX_API_TOKEN_NAME')
        self.token_value = token_value or self.config.get('PROXMOX_API_TOKEN_VALUE')
        
        default_node_config = self.config.get('PROXMOX_DEFAULT_NODE') or self.config.get('PROXMOX_NODE')
        self._default_node = default_node or default_node_config
        
        # Converte string 'false'/'true' para booleano com segurança
        config_ssl = self.config.get('PROXMOX_VERIFY_SSL', False)
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
            connect_kwargs = {
                'host': self.host,
                'user': self.user, 
                'verify_ssl': self.verify_ssl,
                'timeout': 30
            }
            
            if self.token_name and self.token_value:
                connect_kwargs['token_name'] = self.token_name
                connect_kwargs['token_value'] = self.token_value
                log_message = f"API Token: {self.token_name} for user {self.user}"
            else:
                connect_kwargs['password'] = self.password
                log_message = f"User/Pass: {self.user}"
            
            # Se falhar, lança exceção que será pega pelo Global Handler
            self._connection = ProxmoxAPI(**connect_kwargs)
            self.logger.info(f"Conectado ao Proxmox: {self.host} via {log_message}")
            
        return self._connection

    # -------------------------------------------------------------
    # --- Métodos Auxiliares (Privados) ---
    # -------------------------------------------------------------

    def _wait_for_task_completion(self, task_upid, node_id: str):
        """Monitora o status de uma tarefa assíncrona do Proxmox usando polling."""
        if not task_upid or not isinstance(task_upid, str) or not task_upid.startswith('UPID:'):
            return # Tarefa síncrona

        start_time = time.time()
        timeout = self.config.get('PROXMOX_TASK_TIMEOUT', 300)
        poll_interval = self.config.get('PROXMOX_TASK_POLL_INTERVAL', 5)

        self.logger.info(f"Iniciando polling da tarefa UPID: {task_upid}")

        while (time.time() - start_time) < timeout:
            # Pode lançar ResourceException, capturada pelo Global Handler
            task_status = self.connection.nodes(node_id).tasks(task_upid).status.get()
            
            if task_status.get('status') == 'stopped':
                if task_status.get('exitstatus') == 'OK':
                    self.logger.info(f"Tarefa UPID: {task_upid} concluída com sucesso.")
                    return 
                else:
                    error_message = task_status.get('exitstatus', 'Falha desconhecida na tarefa PVE.')
                    raise ProxmoxTaskFailedError(f"A operação do Proxmox falhou: {error_message}")

            time.sleep(poll_interval)

        raise TimeoutError(f"A tarefa do Proxmox excedeu o tempo limite de {timeout} segundos.")

    def _resolve_node_id(self, node_id=None):
        if node_id: return node_id
        if self._default_node: return self._default_node
        if self._cached_first_node_id: return self._cached_first_node_id
        
        # Pode falhar se não houver nodes ou conexão, lança exceção
        nodes = self.connection.nodes.get()
        if nodes:
            self._cached_first_node_id = nodes[0]['node']
            return self._cached_first_node_id
            
        raise ResourceException("Não foi possível resolver o Node Padrão (Nenhum node encontrado).")

    def _get_resource_endpoint(self, node_id, vmid, resource_type):
        """Helper para selecionar o endpoint correto (qemu/lxc)."""
        if resource_type == 'lxc':
            return self.connection.nodes(node_id).lxc(vmid)
        elif resource_type == 'qemu':
            return self.connection.nodes(node_id).qemu(vmid)
        else:
            raise ValueError(f"Tipo de recurso inválido: {resource_type}")

    def _get_next_vmid(self):
        """Obtém o próximo VMID livre."""
        return self.connection.cluster.nextid.get()

    # ---------------------------------
    # --- Métodos de Listagem (Node) ---
    # ---------------------------------

    def test_connection(self):
        self.connection.nodes.get()
        return {'success': True, 'message': 'Conexão com Proxmox OK.'}

    def get_nodes(self):
        nodes = self.connection.nodes.get()
        return {'data': nodes, 'count': len(nodes)}

    def get_node_status(self, node_id=None):
        node_id = self._resolve_node_id(node_id)
        return {'data': self.connection.nodes(node_id).status.get()}

    # ------------------------------------
    # --- Métodos de Resource Pool ---
    # ------------------------------------

    def get_pools(self):
        pools = self.connection.pools.get()
        return {'data': pools, 'count': len(pools)}

    def create_pool(self, poolid, comment=None):
        params = {'poolid': poolid}
        if comment: params['comment'] = comment
        self.connection.pools.post(**params)
        return {'message': f'Pool {poolid} criado com sucesso.'}

    def delete_pool(self, poolid):
        self.connection.pools(poolid).delete()
        return {'message': f'Pool {poolid} excluído com sucesso.'}

    def provision_user_pool(self, username: str):
        poolid = f"vps-{username.lower()}"
        params = {'poolid': poolid, 'comment': f"Pool dedicado ao usuário: {username}"}
        
        try:
            self.connection.pools.post(**params)
            return {'poolid': poolid, 'message': f'Pool "{poolid}" criado.'}
        except ResourceException as e:
            # Caso especial onde queremos tratar o erro e não abortar com 500
            if 'poolid already exists' in str(e):
                 return {'poolid': poolid, 'message': f'Pool "{poolid}" já existe (Reutilizado).', 'existing': True}
            raise # Relança outros erros

    def deprovision_user_pool(self, username: str):
        poolid = f"vps-{username.lower()}"
        try:
            self.connection.pools(poolid).delete()
            return {'message': f'Pool "{poolid}" excluído.'}
        except ResourceException as e:
            if 'not found' in str(e):
                 return {'message': f'Pool "{poolid}" não encontrado (Já removido).', 'skipped': True}
            if 'still has members' in str(e):
                 # Poderíamos levantar erro customizado ou deixar o handler pegar
                 raise ResourceException(f"Não é possível excluir: O Pool {poolid} ainda possui recursos.")
            raise

    def assign_resource_to_pool(self, vmid, poolid, resource_type='vm'):
        """Move ou atribui recurso ao pool. (Lógica de remover -> adicionar)."""
        vmid_str = str(vmid)
        
        # 1. Descobre pool atual (otimizado via cluster resources)
        resources = self.connection.cluster.resources.get(type=resource_type)
        current_pool = next((res.get('pool') for res in resources if str(res.get('vmid')) == vmid_str), None)

        if current_pool == poolid:
            return {'message': f"Recurso {vmid} já está no Pool '{poolid}'."}

        # 2. Remove do antigo se necessário
        if current_pool:
            old_pool_info = self.connection.pools(current_pool).get()
            old_members = [str(m['vmid']) for m in old_pool_info.get('members', []) if str(m['vmid']) != vmid_str]
            self.connection.pools(current_pool).put(vms=','.join(old_members))

        if not poolid:
            return {'message': f"Recurso {vmid} removido do Pool '{current_pool}'."}

        # 3. Adiciona ao novo
        new_pool_info = self.connection.pools(poolid).get()
        current_members = [str(m['vmid']) for m in new_pool_info.get('members', [])]
        if vmid_str not in current_members:
            current_members.append(vmid_str)
            self.connection.pools(poolid).put(vms=','.join(current_members))
            
        return {'message': f"Recurso {vmid} movido para Pool '{poolid}'."}

    def assign_vm_to_pool(self, vmid, poolid):
        return self.assign_resource_to_pool(vmid, poolid, 'vm')

    def assign_ct_to_pool(self, ctid, poolid):
        return self.assign_resource_to_pool(ctid, poolid, 'ct')

    # ---------------------------
    # --- Métodos de VM (QEMU) ---
    # ---------------------------

    def get_vms(self, node_id=None):
        node_id = self._resolve_node_id(node_id)
        vms = self.connection.nodes(node_id).qemu.get()
        return {'data': vms, 'count': len(vms)}

    def get_vm_status(self, vmid):
        node_id = self._resolve_node_id()
        status = self.connection.nodes(node_id).qemu(vmid).status.current.get()
        return {'data': status}

    def create_vm(self, config: dict):
        node_id = self._resolve_node_id()
        
        vmid = config.get('vmid') or self._get_next_vmid()
        
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
        # Remove chaves nulas
        create_config = {k: v for k, v in create_config.items() if v is not None}
        
        # Criação (Assíncrona)
        upid = self.connection.nodes(node_id).qemu.create(**create_config)
        self._wait_for_task_completion(upid, node_id)
        
        return {'vmid': vmid, 'message': f'VM {vmid} criada com sucesso.'}

    def start_vm(self, vmid):
        node_id = self._resolve_node_id()
        upid = self.connection.nodes(node_id).qemu(vmid).status.start.post()
        self._wait_for_task_completion(upid, node_id)
        return {'message': f'VM {vmid} iniciada.'}

    def stop_vm(self, vmid):
        node_id = self._resolve_node_id()
        upid = self.connection.nodes(node_id).qemu(vmid).status.stop.post()
        self._wait_for_task_completion(upid, node_id)
        return {'message': f'VM {vmid} parada.'}

    def delete_vm(self, vmid):
        node_id = self._resolve_node_id()
        upid = self.connection.nodes(node_id).qemu(vmid).delete()
        self._wait_for_task_completion(upid, node_id)
        return {'message': f'VM {vmid} excluída.'}

    def get_vnc_console(self, vmid):
        node_id = self._resolve_node_id()
        # VNC exige user/pass explicitamente
        ticket_data = self.connection.access.ticket.post(
            username=self.user, password=self.password
        )
        return {
            'data': {
                'host': self.host,
                'port': 8006,
                'path': f'/api2/json/nodes/{node_id}/qemu/{vmid}/vncwebsocket',
                'ticket': ticket_data['ticket'],
                'vncticket': ticket_data['ticket']
            }
        }
        
    # ---------------------------
    # --- Métodos de CTs (LXC) ---
    # ---------------------------

    def get_containers(self, node_id=None):
        node_id = self._resolve_node_id(node_id)
        cts = self.connection.nodes(node_id).lxc.get()
        return {'data': cts, 'count': len(cts)}

    def get_container_status(self, ctid):
        node_id = self._resolve_node_id()
        status = self.connection.nodes(node_id).lxc(ctid).status.current.get()
        return {'data': status}

    def get_container_config(self, ctid):
        node_id = self._resolve_node_id()
        return {'data': self.connection.nodes(node_id).lxc(ctid).config.get()}

    def create_container(self, config: dict):
        node_id = self._resolve_node_id()
        
        vmid = config.get('vmid') or self._get_next_vmid()
        
        create_config = {
            'vmid': vmid,
            'ostemplate': config['template'],
            'hostname': config['name'],
            'memory': config.get('memory', 512),
            'cores': config.get('cores', 1),
            'storage': config.get('storage', 'local-lvm'),
            'rootfs': config.get('rootfs') or f"{config.get('storage', 'local-lvm')}:{config.get('disk_size', 8)}",
            'net0': config.get('net0', 'name=eth0,bridge=vmbr0,ip=dhcp'),
            'pool': config.get('poolid')
        }
        create_config = {k: v for k, v in create_config.items() if v is not None}

        upid = self.connection.nodes(node_id).lxc.post(**create_config)
        self._wait_for_task_completion(upid, node_id)
        
        return {'ctid': vmid, 'message': f'Contêiner {vmid} criado com sucesso.'}

    def start_container(self, ctid):
        node_id = self._resolve_node_id()
        upid = self.connection.nodes(node_id).lxc(ctid).status.start.post()
        self._wait_for_task_completion(upid, node_id)
        return {'message': f'CT {ctid} iniciado.'}

    def stop_container(self, ctid):
        node_id = self._resolve_node_id()
        upid = self.connection.nodes(node_id).lxc(ctid).status.stop.post()
        self._wait_for_task_completion(upid, node_id)
        return {'message': f'CT {ctid} parado.'}

    def delete_container(self, ctid):
        node_id = self._resolve_node_id()
        upid = self.connection.nodes(node_id).lxc(ctid).delete()
        self._wait_for_task_completion(upid, node_id)
        return {'message': f'CT {ctid} excluído.'}
        
    def update_container_resources(self, ctid, updates: dict):
        node_id = self._resolve_node_id()
        VALID_LXC_CONFIG_KEYS = ['memory', 'cores', 'rootfs', 'swap', 'net0', 'hostname']
        pve_params = {k: v for k, v in updates.items() if k in VALID_LXC_CONFIG_KEYS}

        if not pve_params:
            raise ValueError("Nenhum parâmetro de atualização válido fornecido.")

        result = self.connection.nodes(node_id).lxc(ctid).config.put(**pve_params)
        
        # Se for assíncrono (UPID), espera. Se for síncrono (null/dict), retorna.
        if isinstance(result, str) and result.startswith("UPID:"):
            self._wait_for_task_completion(result, node_id)
        
        return {'message': f'Recursos do CT {ctid} atualizados.'}

    # ---------------------------
    # --- Métodos de Firewall e Rede ---
    # ---------------------------

    def enable_container_firewall(self, ctid):
        node_id = self._resolve_node_id()
        # Habilita Globalmente no CT
        self.connection.nodes(node_id).lxc(ctid).firewall.options.put(enable=1)
        
        # Habilita na Interface (net0)
        config = self.connection.nodes(node_id).lxc(ctid).config.get()
        net0_conf = config.get('net0', '')
        if 'firewall=1' not in net0_conf:
            new_net0 = f"{net0_conf},firewall=1"
            self.connection.nodes(node_id).lxc(ctid).config.put(net0=new_net0)
            
        return {'message': f'Firewall habilitado para CT {ctid}.'}

    def get_firewall_rules(self, ctid):
        node_id = self._resolve_node_id()
        rules = self.connection.nodes(node_id).lxc(ctid).firewall.rules.get()
        return {'data': rules}

    def add_firewall_rule(self, ctid, rule: dict):
        node_id = self._resolve_node_id()
        params = {
            'type': rule.get('type', 'in'),
            'action': rule.get('action', 'ACCEPT'),
            'enable': 1
        }
        for field in ['proto', 'dport', 'source', 'comment']:
            if rule.get(field): params[field] = rule[field]
            
        self.connection.nodes(node_id).lxc(ctid).firewall.rules.post(**params)
        return {'message': 'Regra de firewall adicionada.'}

    def delete_firewall_rule(self, ctid, pos):
        node_id = self._resolve_node_id()
        self.connection.nodes(node_id).lxc(ctid).firewall.rules(pos).delete()
        return {'message': f'Regra {pos} excluída.'}

    def update_firewall_rule(self, ctid, pos, updates: dict):
        node_id = self._resolve_node_id()
        # Filtra chaves, se vazio deixa a API reclamar ou valida aqui
        self.connection.nodes(node_id).lxc(ctid).firewall.rules(pos).put(**updates)
        return {'message': f'Regra {pos} atualizada.'}

    def set_container_network_rate_limit(self, ctid, rate_mbps):
        node_id = self._resolve_node_id()
        config = self.connection.nodes(node_id).lxc(ctid).config.get()
        net0_conf = config.get('net0', '')
        if not net0_conf:
            raise ResourceException(f"Interface net0 não encontrada no CT {ctid}.")

        net0_parts = net0_conf.split(',')
        net0_dict = {}
        for part in net0_parts:
            if '=' in part:
                k, v = part.split('=', 1)
                net0_dict[k] = v
        
        if rate_mbps and int(rate_mbps) > 0:
            net0_dict['rate'] = str(rate_mbps)
        else:
            net0_dict.pop('rate', None)
            
        new_net0_conf = ','.join([f"{k}={v}" for k, v in net0_dict.items()])
        self.connection.nodes(node_id).lxc(ctid).config.put(net0=new_net0_conf)
        
        return {'message': f'Rate limit atualizado para {rate_mbps} MB/s.'}

    # ---------------------------
    # --- Métodos de Snapshot ---
    # ---------------------------

    def get_snapshots(self, vmid, resource_type='qemu'):
        node_id = self._resolve_node_id()
        resource = self._get_resource_endpoint(node_id, vmid, resource_type)
        return {'data': resource.snapshot.get()}

    def create_snapshot(self, vmid, snapname, description=None, vmstate=False, resource_type='qemu'):
        node_id = self._resolve_node_id()
        resource = self._get_resource_endpoint(node_id, vmid, resource_type)
        
        params = {'snapname': snapname}
        if description: params['description'] = description
        if vmstate and resource_type == 'qemu': params['vmstate'] = 1
        
        upid = resource.snapshot.post(**params)
        self._wait_for_task_completion(upid, node_id)
        return {'message': f"Snapshot '{snapname}' criado."}

    def rollback_snapshot(self, vmid, snapname, resource_type='qemu'):
        node_id = self._resolve_node_id()
        resource = self._get_resource_endpoint(node_id, vmid, resource_type)
        
        upid = resource.snapshot(snapname).rollback.post()
        self._wait_for_task_completion(upid, node_id)
        return {'message': f"Rollback para '{snapname}' concluído."}

    def delete_snapshot(self, vmid, snapname, resource_type='qemu'):
        node_id = self._resolve_node_id()
        resource = self._get_resource_endpoint(node_id, vmid, resource_type)
        
        upid = resource.snapshot(snapname).delete()
        self._wait_for_task_completion(upid, node_id)
        return {'message': f"Snapshot '{snapname}' excluído."}

    # ---------------------------
    # --- Métodos de Storage ---
    # ---------------------------

    def get_storages(self, node_id=None):
        storages = self.connection.storage.get()
        return {'data': storages, 'count': len(storages)}

    def get_storage_status(self, storage_id, node_id=None):
        node_id = self._resolve_node_id(node_id)
        status = self.connection.nodes(node_id).storage(storage_id).status.get()
        return {'data': status}
        
    def get_storage_content(self, storage_id, node_id=None):
        node_id = self._resolve_node_id(node_id)
        content = self.connection.nodes(node_id).storage(storage_id).content.get()
        return {'data': content, 'count': len(content)}