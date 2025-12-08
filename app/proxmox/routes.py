from flask import jsonify, request, abort
from . import bp, ProxmoxService

def get_service():
    return ProxmoxService()

# --- Rotas Cluster ---

@bp.route('/nodes', methods=['GET'])
def list_nodes():
    """
    Lista os nós (Nodes) do Cluster.
    Retorna o status de saúde e consumo de recursos de cada nó.
    ---
    tags:
      - Proxmox Admin (Raw)
    responses:
      200:
        description: Lista de nós recuperada com sucesso
    """
    return jsonify(get_service().get_nodes())

# --- Rotas Containers (LXC) ---

@bp.route('/cts', methods=['GET'])
def list_containers():
    """
    Lista todos os Containers LXC.
    ---
    tags:
      - Proxmox Admin (Raw)
    responses:
      200:
        description: Lista de CTs
    """
    return jsonify(get_service().get_containers())

@bp.route('/cts', methods=['POST'])
def create_container():
    """
    Cria um Container LXC (Modo Admin/Raw).
    Permite passar qualquer parâmetro aceito pela API do Proxmox.
    ---
    tags:
      - Proxmox Admin (Raw)
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            name:
              type: string
              example: "my-container"
            template:
              type: string
              example: "local:vztmpl/debian-12.tar.zst"
            vmid:
              type: integer
              example: 105
            cores:
              type: integer
            memory:
              type: integer
    responses:
      201:
        description: Tarefa de criação iniciada
    """
    data = request.get_json() or {}
    return jsonify(get_service().create_container(data)), 201

@bp.route('/cts/<int:ctid>/start', methods=['POST'])
def start_container(ctid):
    """
    Inicia (Boot) um Container LXC.
    ---
    tags:
      - Proxmox Admin (Raw)
    parameters:
      - name: ctid
        in: path
        type: integer
        required: true
        description: VMID do Container
    responses:
      200:
        description: Comando enviado
    """
    return jsonify(get_service().start_container(ctid))

@bp.route('/cts/<int:ctid>/stop', methods=['POST'])
def stop_container(ctid):
    """
    Para (Shutdown) um Container LXC.
    ---
    tags:
      - Proxmox Admin (Raw)
    parameters:
      - name: ctid
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Comando enviado
    """
    return jsonify(get_service().stop_container(ctid))

# --- Rotas VMs (QEMU) ---

@bp.route('/vms', methods=['GET'])
def list_vms():
    """
    Lista todas as Máquinas Virtuais (KVM).
    ---
    tags:
      - Proxmox Admin (Raw)
    responses:
      200:
        description: Lista de VMs
    """
    return jsonify(get_service().get_vms())

@bp.route('/vms', methods=['POST'])
def create_vm():
    """
    Cria uma VM (Modo Admin/Raw).
    ---
    tags:
      - Proxmox Admin (Raw)
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            name:
              type: string
              example: "my-vm"
            cores:
              type: integer
            memory:
              type: integer
    responses:
      201:
        description: Tarefa iniciada
    """
    data = request.get_json() or {}
    return jsonify(get_service().create_vm(data)), 201

# --- Rotas Storage ---

@bp.route('/storages', methods=['GET'])
def list_storages():
    """
    Lista os storages disponíveis no Cluster.
    ---
    tags:
      - Proxmox Admin (Raw)
    responses:
      200:
        description: Lista de storages
    """
    return jsonify(get_service().get_storages())

# --- Rotas Pools (Atualizado com Swagger) ---

@bp.route('/pools', methods=['GET'])
def list_pools():
    """
    Lista todos os Resource Pools do Cluster.
    ---
    tags:
      - Proxmox Admin (Raw)
    responses:
      200:
        description: Lista de pools recuperada com sucesso
    """
    return jsonify(get_service().get_pools())

@bp.route('/pools', methods=['POST'])
def create_pool():
    """
    Cria um novo Resource Pool.
    Útil para organizar recursos por utilizador ou projeto.
    ---
    tags:
      - Proxmox Admin (Raw)
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
              description: "ID único do Pool (ex: vps-cliente-a)"
            comment:
              type: string
              description: Descrição opcional
    responses:
      201:
        description: Pool criado com sucesso
      400:
        description: Falta o poolid
    """
    data = request.get_json() or {}
    poolid = data.get('poolid')
    comment = data.get('comment')
    
    if not poolid:
        abort(400, description="O campo 'poolid' é obrigatório.")
        
    return jsonify(get_service().create_pool(poolid, comment)), 201

@bp.route('/pools/<string:poolid>', methods=['DELETE'])
def delete_pool(poolid):
    """
    Exclui um Resource Pool.
    Nota: O pool deve estar vazio (sem VMs/CTs) para ser excluído.
    ---
    tags:
      - Proxmox Admin (Raw)
    parameters:
      - name: poolid
        in: path
        type: string
        required: true
        description: ID do Pool a ser removido
    responses:
      200:
        description: Pool removido
    """
    return jsonify(get_service().delete_pool(poolid))