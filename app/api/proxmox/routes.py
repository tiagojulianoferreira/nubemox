from flask import jsonify, request, abort
from app.api.proxmox import bp
from app.services.proxmox_service import ProxmoxService
import re

# Helpers de Disco (Idealmente mover para app/utils/helpers.py no futuro)
def parse_rootfs_size_gb(rootfs_string: str) -> int:
    match = re.search(r'size=(\d+)(G|g)', rootfs_string)
    if match:
        return int(match.group(1))
    # Deixa o erro subir para o handler global ou aborta aqui
    abort(400, description="Formato de rootfs size inválido na configuração atual.")

def reconstruct_rootfs_string(rootfs_string: str, new_size_gb: int) -> str:
    return re.sub(r'size=\d+[Gg]', f'size={new_size_gb}G', rootfs_string)

# Instância leve do serviço ou factory
def get_service():
    return ProxmoxService()

# --- Rotas Básicas e de Cluster ---

@bp.route('/test', methods=['GET'])
def test_connection():
    """
    Testa a conexão com o Cluster Proxmox.
    ---
    tags:
      - System
    responses:
      200:
        description: Conexão bem-sucedida
        schema:
          properties:
            success:
              type: boolean
            message:
              type: string
      500:
        description: Falha na conexão
    """
    result = get_service().test_connection()
    return jsonify(result)

@bp.route('/nodes', methods=['GET'])
def list_nodes():
    """
    Lista todos os nós (Nodes) do cluster.
    ---
    tags:
      - Cluster
    responses:
      200:
        description: Lista de nós retornada com sucesso
    """
    result = get_service().get_nodes()
    return jsonify(result)

@bp.route('/cluster/summary', methods=['GET'])
def cluster_summary():
    """
    Obtém um resumo simplificado do cluster.
    ---
    tags:
      - Cluster
    responses:
      200:
        description: Resumo do cluster
        schema:
          properties:
            total_nodes:
              type: integer
            nodes:
              type: array
              items:
                type: string
    """
    nodes_result = get_service().get_nodes()
    summary = {
        'total_nodes': len(nodes_result['data']),
        'nodes': [n.get('node') for n in nodes_result['data']],
        'total_vms': 'N/A', 
        'total_containers': 'N/A'
    }
    return jsonify(summary)

# --- Rotas de Pools e Provisionamento ---

@bp.route('/pools', methods=['GET'])
def list_pools():
    """
    Lista todos os Resource Pools.
    ---
    tags:
      - Pools
    responses:
      200:
        description: Lista de pools
    """
    return jsonify(get_service().get_pools())

@bp.route('/pools', methods=['POST'])
def create_pool():
    """
    Cria um novo Resource Pool manualmente.
    ---
    tags:
      - Pools
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - poolid
          properties:
            poolid:
              type: string
              example: "pool-teste"
            comment:
              type: string
    responses:
      201:
        description: Pool criado
      400:
        description: Falta poolid
    """
    data = request.get_json() or {}
    poolid = data.get('poolid')
    
    if not poolid:
        abort(400, description="O campo 'poolid' é obrigatório.")
        
    result = get_service().create_pool(poolid, data.get('comment'))
    return jsonify(result), 201

@bp.route('/user-provisioning/pool', methods=['POST'])
def provision_user_pool_route():
    """
    Provisiona um Pool dedicado para um usuário (vps-username).
    ---
    tags:
      - Provisionamento
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - username
          properties:
            username:
              type: string
              example: "paulo.silva"
    responses:
      201:
        description: Pool criado com sucesso
      409:
        description: Pool já existe
    """
    data = request.get_json() or {}
    username = data.get('username')
    
    if not username:
        abort(400, description="O campo 'username' é obrigatório.")
        
    result = get_service().provision_user_pool(username.strip().lower())
    
    status_code = 201
    if result.get('existing'):
        status_code = 409
        
    return jsonify(result), status_code

@bp.route('/user-provisioning/pool', methods=['DELETE'])
def deprovision_user_pool_route():
    """
    Remove o Pool dedicado de um usuário.
    ---
    tags:
      - Provisionamento
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - username
          properties:
            username:
              type: string
              example: "paulo.silva"
    responses:
      200:
        description: Pool removido
      404:
        description: Pool não encontrado
    """
    data = request.get_json() or {}
    username = data.get('username')
    
    if not username:
        abort(400, description="O campo 'username' é obrigatório.")
        
    result = get_service().deprovision_user_pool(username.strip().lower())
    
    status_code = 200
    if result.get('skipped'):
        status_code = 404
        
    return jsonify(result), status_code

# --- Rotas de VMs ---

@bp.route('/vms', methods=['GET'])
def list_vms():
    """
    Lista todas as VMs (QEMU).
    ---
    tags:
      - VMs
    responses:
      200:
        description: Lista de VMs
    """
    return jsonify(get_service().get_vms())

@bp.route('/vms', methods=['POST'])
def create_vm():
    """
    Cria uma nova Máquina Virtual.
    ---
    tags:
      - VMs
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - name
            - poolid
          properties:
            name:
              type: string
              example: "vm-app-01"
            poolid:
              type: string
              description: "ID do Pool (ex: vps-usuario)"
              example: "vps-paulo.silva"
            cores:
              type: integer
              default: 2
            memory:
              type: integer
              description: RAM em MB
              default: 2048
            vmid:
              type: integer
              description: Opcional. Se não enviado, gera automático.
    responses:
      201:
        description: VM criada com sucesso
    """
    data = request.get_json() or {}
    
    if not data.get('name') or not data.get('poolid'):
        abort(400, description="Campos 'name' e 'poolid' são obrigatórios.")
        
    result = get_service().create_vm(data)
    return jsonify(result), 201

@bp.route('/vms/<int:vmid>/status', methods=['GET'])
def vm_status(vmid):
    """
    Obtém status da VM.
    ---
    tags:
      - VMs
    parameters:
      - name: vmid
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Status retornado
    """
    return jsonify(get_service().get_vm_status(vmid))

@bp.route('/vms/<int:vmid>/start', methods=['POST'])
def start_vm(vmid):
    """
    Liga (Start) uma VM.
    ---
    tags:
      - VMs
    parameters:
      - name: vmid
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Comando enviado
    """
    return jsonify(get_service().start_vm(vmid))

@bp.route('/vms/<int:vmid>/stop', methods=['POST'])
def stop_vm(vmid):
    """
    Desliga (Stop) uma VM.
    ---
    tags:
      - VMs
    parameters:
      - name: vmid
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Comando enviado
    """
    return jsonify(get_service().stop_vm(vmid))

@bp.route('/vms/<int:vmid>', methods=['DELETE'])
def delete_vm(vmid):
    """
    Exclui uma VM.
    ---
    tags:
      - VMs
    parameters:
      - name: vmid
        in: path
        type: integer
        required: true
    responses:
      200:
        description: VM excluída
    """
    return jsonify(get_service().delete_vm(vmid))

@bp.route('/vms/<int:vmid>/pool', methods=['PUT'])
def assign_vm_to_pool_route(vmid):
    """
    Move uma VM para um Pool.
    ---
    tags:
      - VMs
    parameters:
      - name: vmid
        in: path
        type: integer
        required: true
      - in: body
        name: body
        schema:
          type: object
          properties:
            poolid:
              type: string
              description: Novo Pool ID. Vazio para remover do atual.
    responses:
      200:
        description: VM movida
    """
    data = request.get_json() or {}
    if 'poolid' not in data:
        abort(400, description="O campo 'poolid' é obrigatório (envie vazio para remover).")
        
    result = get_service().assign_vm_to_pool(vmid, data.get('poolid'))
    return jsonify(result)

@bp.route('/vms/<int:vmid>/vnc', methods=['GET'])
def vm_vnc_console(vmid):
    """
    Obtém ticket VNC para console.
    ---
    tags:
      - VMs
    parameters:
      - name: vmid
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Dados de conexão VNC
    """
    return jsonify(get_service().get_vnc_console(vmid))

# --- Rotas de Snapshots (VM) ---

@bp.route('/vms/<int:vmid>/snapshots', methods=['GET'])
def list_vm_snapshots(vmid):
    """
    Lista snapshots da VM.
    ---
    tags:
      - Snapshots (VM)
    parameters:
      - name: vmid
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Lista de snapshots
    """
    return jsonify(get_service().get_snapshots(vmid, 'qemu'))

@bp.route('/vms/<int:vmid>/snapshots', methods=['POST'])
def create_vm_snapshot(vmid):
    """
    Cria snapshot da VM.
    ---
    tags:
      - Snapshots (VM)
    parameters:
      - name: vmid
        in: path
        type: integer
        required: true
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - snapname
          properties:
            snapname:
              type: string
            description:
              type: string
            vmstate:
              type: boolean
              description: Salvar estado da RAM
    responses:
      201:
        description: Snapshot criado
    """
    data = request.get_json() or {}
    if not data.get('snapname'):
        abort(400, description="O campo 'snapname' é obrigatório.")
        
    result = get_service().create_snapshot(
        vmid, data['snapname'], data.get('description'), 
        vmstate=data.get('vmstate', False), resource_type='qemu'
    )
    return jsonify(result), 201

@bp.route('/vms/<int:vmid>/snapshots/<snapname>/rollback', methods=['POST'])
def rollback_vm_snapshot(vmid, snapname):
    """
    Restaura VM para um snapshot.
    ---
    tags:
      - Snapshots (VM)
    parameters:
      - name: vmid
        in: path
        type: integer
        required: true
      - name: snapname
        in: path
        type: string
        required: true
    responses:
      200:
        description: Rollback concluído
    """
    return jsonify(get_service().rollback_snapshot(vmid, snapname, 'qemu'))

@bp.route('/vms/<int:vmid>/snapshots/<snapname>', methods=['DELETE'])
def delete_vm_snapshot(vmid, snapname):
    """
    Exclui um snapshot da VM.
    ---
    tags:
      - Snapshots (VM)
    parameters:
      - name: vmid
        in: path
        type: integer
        required: true
      - name: snapname
        in: path
        type: string
        required: true
    responses:
      200:
        description: Snapshot excluído
    """
    return jsonify(get_service().delete_snapshot(vmid, snapname, 'qemu'))

# --- Rotas de Contêineres (LXC) ---

@bp.route('/cts', methods=['GET'])
def list_containers():
    """
    Lista todos os Contêineres LXC.
    ---
    tags:
      - Containers
    responses:
      200:
        description: Lista de CTs
    """
    return jsonify(get_service().get_containers())

@bp.route('/cts', methods=['POST'])
def create_container():
    """
    Cria um novo Contêiner LXC.
    ---
    tags:
      - Containers
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - name
            - template
            - poolid
          properties:
            name:
              type: string
              example: "ct-web-01"
            template:
              type: string
              description: Nome exato do template no storage
              example: "local:vztmpl/debian-12-standard_12.2-1_amd64.tar.zst"
            poolid:
              type: string
              example: "vps-paulo.silva"
            cores:
              type: integer
              default: 1
            memory:
              type: integer
              default: 512
            storage:
              type: string
              default: "local-lvm"
    responses:
      201:
        description: Contêiner criado com sucesso
    """
    data = request.get_json() or {}
    
    required = ['name', 'template', 'poolid']
    if not all(k in data for k in required):
        abort(400, description=f"Campos obrigatórios: {', '.join(required)}")
        
    result = get_service().create_container(data)
    return jsonify(result), 201

@bp.route('/cts/<int:ctid>/status', methods=['GET'])
def container_status(ctid):
    """
    Obtém status do Contêiner.
    ---
    tags:
      - Containers
    parameters:
      - name: ctid
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Status retornado
    """
    return jsonify(get_service().get_container_status(ctid))

@bp.route('/cts/<int:ctid>', methods=['PUT'])
def update_container_resources_route(ctid):
    """
    Atualiza recursos do CT (ex: aumentar disco).
    ---
    tags:
      - Containers
    parameters:
      - name: ctid
        in: path
        type: integer
        required: true
      - in: body
        name: body
        schema:
          type: object
          properties:
            memory:
              type: integer
            cores:
              type: integer
            disk_increment_gb:
              type: integer
              description: Quantidade de GB para adicionar ao disco
    responses:
      200:
        description: Recursos atualizados
    """
    data = request.get_json() or {}
    service = get_service()
    
    disk_increment_gb = data.pop('disk_increment_gb', None)
    
    if disk_increment_gb:
        current_config = service.get_container_config(ctid)['data']
        current_rootfs = current_config.get('rootfs')
        
        if not current_rootfs:
            abort(400, description="Configuração de rootfs não encontrada no CT.")
            
        try:
            current_size = parse_rootfs_size_gb(current_rootfs)
            new_size = current_size + int(disk_increment_gb)
            
            if new_size <= current_size:
                abort(400, description="O incremento deve resultar em um tamanho maior que o atual.")
                
            data['rootfs'] = reconstruct_rootfs_string(current_rootfs, new_size)
        except ValueError:
            abort(400, description="Valor de incremento inválido.")

    result = service.update_container_resources(ctid, data)
    return jsonify(result)

@bp.route('/cts/<int:ctid>/start', methods=['POST'])
def start_container(ctid):
    """
    Inicia (Start) o Contêiner.
    ---
    tags:
      - Containers
    parameters:
      - name: ctid
        in: path
        type: integer
        required: true
    responses:
      200:
        description: CT iniciado
    """
    return jsonify(get_service().start_container(ctid))

@bp.route('/cts/<int:ctid>/stop', methods=['POST'])
def stop_container(ctid):
    """
    Para (Stop) o Contêiner.
    ---
    tags:
      - Containers
    parameters:
      - name: ctid
        in: path
        type: integer
        required: true
    responses:
      200:
        description: CT parado
    """
    return jsonify(get_service().stop_container(ctid))

@bp.route('/cts/<int:ctid>', methods=['DELETE'])
def delete_container(ctid):
    """
    Exclui o Contêiner.
    ---
    tags:
      - Containers
    parameters:
      - name: ctid
        in: path
        type: integer
        required: true
    responses:
      200:
        description: CT excluído
    """
    return jsonify(get_service().delete_container(ctid))

@bp.route('/cts/<int:ctid>/pool', methods=['PUT'])
def assign_ct_to_pool_route(ctid):
    """
    Move um CT para um Pool.
    ---
    tags:
      - Containers
    parameters:
      - name: ctid
        in: path
        type: integer
        required: true
      - in: body
        name: body
        schema:
          type: object
          properties:
            poolid:
              type: string
              description: Novo Pool ID. Vazio para remover.
    responses:
      200:
        description: Movimentação concluída
    """
    data = request.get_json() or {}
    if 'poolid' not in data:
        abort(400, description="O campo 'poolid' é obrigatório.")
    return jsonify(get_service().assign_ct_to_pool(ctid, data.get('poolid')))

# --- Rotas de Firewall (CT) ---

@bp.route('/cts/<int:ctid>/firewall/enable', methods=['POST'])
def enable_ct_firewall_route(ctid):
    """
    Habilita Firewall no CT.
    ---
    tags:
      - Firewall (CT)
    parameters:
      - name: ctid
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Firewall habilitado
    """
    return jsonify(get_service().enable_container_firewall(ctid))

@bp.route('/cts/<int:ctid>/firewall/rules', methods=['GET'])
def list_ct_firewall_rules_route(ctid):
    """
    Lista regras de firewall do CT.
    ---
    tags:
      - Firewall (CT)
    parameters:
      - name: ctid
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Lista de regras
    """
    return jsonify(get_service().get_firewall_rules(ctid))

@bp.route('/cts/<int:ctid>/firewall/rules', methods=['POST'])
def add_ct_firewall_rule_route(ctid):
    """
    Adiciona regra de firewall.
    ---
    tags:
      - Firewall (CT)
    parameters:
      - name: ctid
        in: path
        type: integer
        required: true
      - in: body
        name: body
        schema:
          type: object
          required:
            - action
          properties:
            type:
              type: string
              default: "in"
            action:
              type: string
              enum: ["ACCEPT", "DROP", "REJECT"]
            proto:
              type: string
              example: "tcp"
            dport:
              type: string
              example: "80"
            comment:
              type: string
    responses:
      201:
        description: Regra adicionada
    """
    data = request.get_json() or {}
    if not data.get('action'):
        abort(400, description="O campo 'action' é obrigatório.")
    return jsonify(get_service().add_firewall_rule(ctid, data)), 201

@bp.route('/cts/<int:ctid>/firewall/rules/<int:pos>', methods=['DELETE'])
def delete_ct_firewall_rule_route(ctid, pos):
    """
    Remove uma regra de firewall pela posição.
    ---
    tags:
      - Firewall (CT)
    parameters:
      - name: ctid
        in: path
        type: integer
        required: true
      - name: pos
        in: path
        type: integer
        description: Posição da regra
        required: true
    responses:
      200:
        description: Regra excluída
    """
    return jsonify(get_service().delete_firewall_rule(ctid, pos))

@bp.route('/cts/<int:ctid>/firewall/rules/<int:pos>', methods=['PUT'])
def update_ct_firewall_rule_route(ctid, pos):
    """
    Atualiza uma regra de firewall.
    ---
    tags:
      - Firewall (CT)
    parameters:
      - name: ctid
        in: path
        type: integer
        required: true
      - name: pos
        in: path
        type: integer
        required: true
      - in: body
        name: body
        schema:
          type: object
          properties:
            action:
              type: string
            enable:
              type: integer
              description: 0 ou 1
    responses:
      200:
        description: Regra atualizada
    """
    data = request.get_json() or {}
    if not data:
        abort(400, description="Corpo da requisição vazio.")
    return jsonify(get_service().update_firewall_rule(ctid, pos, data))

@bp.route('/cts/<int:ctid>/network/rate-limit', methods=['PUT'])
def set_ct_rate_limit_route(ctid):
    """
    Define Rate Limit de Rede (MB/s).
    ---
    tags:
      - Networking (CT)
    parameters:
      - name: ctid
        in: path
        type: integer
        required: true
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - rate_mbps
          properties:
            rate_mbps:
              type: integer
              description: Limite em MB/s (0 para remover)
              example: 5
    responses:
      200:
        description: Limite definido
    """
    data = request.get_json() or {}
    if 'rate_mbps' not in data:
        abort(400, description="O campo 'rate_mbps' é obrigatório.")
    return jsonify(get_service().set_container_network_rate_limit(ctid, data['rate_mbps']))

# --- Rotas de Snapshots (CT) ---

@bp.route('/cts/<int:ctid>/snapshots', methods=['GET'])
def list_ct_snapshots(ctid):
    """
    Lista snapshots do CT.
    ---
    tags:
      - Snapshots (CT)
    parameters:
      - name: ctid
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Lista de snapshots
    """
    return jsonify(get_service().get_snapshots(ctid, 'lxc'))

@bp.route('/cts/<int:ctid>/snapshots', methods=['POST'])
def create_ct_snapshot(ctid):
    """
    Cria snapshot do CT.
    ---
    tags:
      - Snapshots (CT)
    parameters:
      - name: ctid
        in: path
        type: integer
        required: true
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - snapname
          properties:
            snapname:
              type: string
            description:
              type: string
    responses:
      201:
        description: Snapshot criado
    """
    data = request.get_json() or {}
    if not data.get('snapname'):
        abort(400, description="O campo 'snapname' é obrigatório.")
        
    result = get_service().create_snapshot(
        ctid, data['snapname'], data.get('description'), resource_type='lxc'
    )
    return jsonify(result), 201

@bp.route('/cts/<int:ctid>/snapshots/<snapname>/rollback', methods=['POST'])
def rollback_ct_snapshot(ctid, snapname):
    """
    Restaura CT para um snapshot.
    ---
    tags:
      - Snapshots (CT)
    parameters:
      - name: ctid
        in: path
        type: integer
        required: true
      - name: snapname
        in: path
        type: string
        required: true
    responses:
      200:
        description: Rollback concluído
    """
    return jsonify(get_service().rollback_snapshot(ctid, snapname, 'lxc'))

@bp.route('/cts/<int:ctid>/snapshots/<snapname>', methods=['DELETE'])
def delete_ct_snapshot(ctid, snapname):
    """
    Exclui snapshot do CT.
    ---
    tags:
      - Snapshots (CT)
    parameters:
      - name: ctid
        in: path
        type: integer
        required: true
      - name: snapname
        in: path
        type: string
        required: true
    responses:
      200:
        description: Snapshot excluído
    """
    return jsonify(get_service().delete_snapshot(ctid, snapname, 'lxc'))

# --- Rotas de Storage ---

@bp.route('/storages', methods=['GET'])
def list_storages():
    """
    Lista todos os Storages.
    ---
    tags:
      - Storage
    responses:
      200:
        description: Lista de storages
    """
    return jsonify(get_service().get_storages())

@bp.route('/storages/<storage_id>', methods=['GET'])
def storage_status(storage_id):
    """
    Obtém status do Storage.
    ---
    tags:
      - Storage
    parameters:
      - name: storage_id
        in: path
        type: string
        required: true
    responses:
      200:
        description: Status do storage
    """
    return jsonify(get_service().get_storage_status(storage_id))

@bp.route('/storages/<storage_id>/content', methods=['GET'])
def storage_content(storage_id):
    """
    Lista conteúdo do Storage (Templates, Backups).
    ---
    tags:
      - Storage
    parameters:
      - name: storage_id
        in: path
        type: string
        required: true
    responses:
      200:
        description: Conteúdo do storage
    """
    return jsonify(get_service().get_storage_content(storage_id))