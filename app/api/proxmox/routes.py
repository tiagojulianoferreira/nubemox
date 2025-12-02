from flask import jsonify, request, current_app
from app.api.proxmox import bp
from app.services.proxmox_service import ProxmoxService

# Rotas de Cluster (Não requerem node na URL)

@bp.route('/test', methods=['GET'])
def test_connection():
    """Testa conexão com o Proxmox"""
    service = ProxmoxService()
    result = service.test_connection()
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/nodes', methods=['GET'])
def list_nodes():
    """Lista todos os nodes do cluster"""
    service = ProxmoxService()
    result = service.get_nodes()
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/cluster/summary', methods=['GET'])
def cluster_summary():
    """Resumo simplificado do cluster (apenas lista os nodes)"""
    service = ProxmoxService()
    
    nodes_result = service.get_nodes()
    if not nodes_result['success']:
        return jsonify(nodes_result), 500
    
    summary = {
        'total_nodes': len(nodes_result['data']),
        'nodes': [],
        'total_vms': 'N/A', 
        'total_containers': 'N/A'
    }
    
    # Coletar dados de cada node (Apenas nomes, sem status detalhado)
    for node_data in nodes_result['data']:
        node_summary = {
            'name': node_data['node'],
            'status': 'Detalhes via /node/status (serviço otimizado para node padrão)'
        }
        summary['nodes'].append(node_summary)
    
    return jsonify({
        'success': True,
        'data': summary
    })

# Rotas de Node Padrão (Sem Node na URL)

@bp.route('/node/status', methods=['GET'])
def node_status():
    """Obtém status do node padrão"""
    service = ProxmoxService()
    result = service.get_node_status()
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/vms', methods=['GET'])
def list_vms():
    """Lista todas as VMs do node padrão"""
    service = ProxmoxService()
    result = service.get_vms()
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/cts', methods=['GET'])
def list_containers():
    """Lista todos os containers LXC do node padrão"""
    service = ProxmoxService()
    result = service.get_containers()
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/storage', methods=['GET'])
def list_storage():
    """Lista storage disponível no node padrão"""
    service = ProxmoxService()
    result = service.get_storage()
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/templates', methods=['GET'])
def list_templates():
    """Lista templates disponíveis no node padrão"""
    service = ProxmoxService()
    result = service.get_templates()
    return jsonify(result), 200 if result['success'] else 500

# Rotas de Criação (Node Padrão)

@bp.route('/vms', methods=['POST'])
def create_vm():
    """Cria uma nova VM no node padrão"""
    data = request.get_json()
    
    if not data or 'name' not in data:
        return jsonify({
            'success': False,
            'error': 'Nome da VM é obrigatório'
        }), 400
    
    service = ProxmoxService()
    result = service.create_vm(data)
    
    return jsonify(result), 201 if result['success'] else 500

@bp.route('/cts', methods=['POST'])
def create_container():
    """Cria um novo Contêiner LXC no node padrão"""
    data = request.get_json()
    
    # Validamos 'template' (que mapeia para 'ostemplate' no service) e 'name'
    if not data or 'name' not in data or 'template' not in data:
        return jsonify({
            'success': False,
            'error': 'Nome (name) e Template (template) são obrigatórios para a criação do Contêiner'
        }), 400
    
    service = ProxmoxService()
    result = service.create_container(data)
    
    return jsonify(result), 201 if result['success'] else 500

# Rotas de Status e Ação da VM (Node Padrão)

@bp.route('/vms/<int:vmid>/status', methods=['GET'])
def vm_status(vmid):
    """Obtém status de uma VM específica no node padrão"""
    service = ProxmoxService()
    result = service.get_vm_status(vmid)
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/vms/<int:vmid>/start', methods=['POST'])
def start_vm(vmid):
    """Inicia uma VM no node padrão"""
    service = ProxmoxService()
    result = service.start_vm(vmid)
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/vms/<int:vmid>/stop', methods=['POST'])
def stop_vm(vmid):
    """Para uma VM no node padrão"""
    service = ProxmoxService()
    result = service.stop_vm(vmid)
    return jsonify(result), 200 if result['success'] else 500

# Rotas de Ação do Contêiner (Node Padrão)

@bp.route('/cts/<int:ctid>/status', methods=['GET'])
def container_status(ctid):
    """Obtém status de um Contêiner LXC específico no node padrão"""
    service = ProxmoxService()
    result = service.get_container_status(ctid)
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/cts/<int:ctid>/start', methods=['POST'])
def start_container(ctid):
    """Inicia um Contêiner LXC no node padrão"""
    service = ProxmoxService()
    result = service.start_container(ctid)
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/cts/<int:ctid>/stop', methods=['POST'])
def stop_container(ctid):
    """Para um Contêiner LXC no node padrão"""
    service = ProxmoxService()
    result = service.stop_container(ctid)
    return jsonify(result), 200 if result['success'] else 500


@bp.route('/vms/<int:vmid>/console', methods=['GET'])
def get_vm_console(vmid):
    """Obtém informações para console VNC da VM no node padrão"""
    service = ProxmoxService()
    result = service.get_vnc_console(vmid)
    return jsonify(result), 200 if result['success'] else 500

# --- Rotas de Resource Pools ---

@bp.route('/pools', methods=['GET'])
def list_pools():
    """Lista todos os Resource Pools do cluster."""
    service = ProxmoxService()
    result = service.get_pools()
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/pools', methods=['POST'])
def create_pool():
    """Cria um novo Resource Pool."""
    data = request.get_json()
    poolid = data.get('poolid')
    comment = data.get('comment', "")
    
    if not poolid:
        return jsonify({'success': False, 'error': 'O ID do Pool é obrigatório.'}), 400
        
    service = ProxmoxService()
    result = service.create_pool(poolid, comment)
    return jsonify(result), 201 if result['success'] else 500

@bp.route('/pools/<poolid>/members', methods=['GET'])
def list_pool_members(poolid):
    """Lista todos os membros (VMs/CTs) de um Pool."""
    service = ProxmoxService()
    result = service.list_pool_vms(poolid)
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/pools/<poolid>/add_member', methods=['POST'])
def add_pool_member_route(poolid):
    """Adiciona uma VM ou CT a um Pool."""
    data = request.get_json()
    vmid = data.get('vmid')
    
    if not vmid:
        return jsonify({'success': False, 'error': 'O VMID/CTID (vmid) é obrigatório.'}), 400
        
    service = ProxmoxService()
    result = service.add_pool_member(poolid, vmid)
    return jsonify(result), 200 if result['success'] else 500