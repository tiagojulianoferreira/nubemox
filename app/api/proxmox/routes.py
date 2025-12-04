from flask import jsonify, request, current_app
from app.api.proxmox import bp
from app.services.proxmox_service import ProxmoxService
from proxmoxer import ResourceException
import re

# Helpers de Disco
def parse_rootfs_size_gb(rootfs_string: str) -> int:
    match = re.search(r'size=(\d+)(G|g)', rootfs_string)
    if match:
        return int(match.group(1))
    raise ValueError("Formato de rootfs size inválido.")

def reconstruct_rootfs_string(rootfs_string: str, new_size_gb: int) -> str:
    return re.sub(r'size=\d+[Gg]', f'size={new_size_gb}G', rootfs_string)

# --- Rotas Básicas ---

@bp.route('/test', methods=['GET'])
def test_connection():
    service = ProxmoxService()
    result = service.test_connection()
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/nodes', methods=['GET'])
def list_nodes():
    service = ProxmoxService()
    result = service.get_nodes()
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/cluster/summary', methods=['GET'])
def cluster_summary():
    service = ProxmoxService()
    nodes_result = service.get_nodes()
    if not nodes_result['success']:
        return jsonify(nodes_result), 500
    summary = {
        'total_nodes': len(nodes_result['data']),
        'nodes': [n.get('node') for n in nodes_result['data']],
        'total_vms': 'N/A', 'total_containers': 'N/A'
    }
    return jsonify(summary), 200

# --- Rotas de Pools e Provisionamento ---

@bp.route('/pools', methods=['GET'])
def list_pools():
    service = ProxmoxService()
    result = service.get_pools()
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/pools', methods=['POST'])
def create_pool():
    data = request.get_json()
    if not data or 'poolid' not in data:
        return jsonify({'success': False, 'error': 'poolid é obrigatório.'}), 400
    service = ProxmoxService()
    result = service.create_pool(data.get('poolid'), data.get('comment'))
    return jsonify(result), 201 if result['success'] else 500

@bp.route('/user-provisioning/pool', methods=['POST'])
def provision_user_pool_route():
    data = request.get_json()
    username = data.get('username')
    if not username:
        return jsonify({'success': False, 'error': 'username é obrigatório.'}), 400
    service = ProxmoxService()
    result = service.provision_user_pool(username.strip().lower())
    status_code = 201 if result['success'] else (409 if 'já existe' in str(result.get('error')) else 500)
    return jsonify(result), status_code

@bp.route('/user-provisioning/pool', methods=['DELETE'])
def deprovision_user_pool_route():
    data = request.get_json()
    username = data.get('username')
    if not username:
        return jsonify({'success': False, 'error': 'username é obrigatório.'}), 400
    service = ProxmoxService()
    result = service.deprovision_user_pool(username.strip().lower())
    if result['success']: return jsonify(result), 200
    if 'não encontrado' in str(result.get('error')): return jsonify(result), 404
    if 'não pode ser excluído' in str(result.get('error')): return jsonify(result), 409
    return jsonify(result), 500

# --- Rotas de VMs ---

@bp.route('/vms', methods=['GET'])
def list_vms():
    service = ProxmoxService()
    result = service.get_vms()
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/vms', methods=['POST'])
def create_vm():
    data = request.get_json()
    if not data or 'name' not in data or 'poolid' not in data:
        return jsonify({'success': False, 'error': 'Name e poolid são obrigatórios.'}), 400
    service = ProxmoxService()
    result = service.create_vm(data)
    return jsonify(result), 201 if result['success'] else 500

@bp.route('/vms/<int:vmid>/status', methods=['GET'])
def vm_status(vmid):
    service = ProxmoxService()
    result = service.get_vm_status(vmid)
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/vms/<int:vmid>/start', methods=['POST'])
def start_vm(vmid):
    service = ProxmoxService()
    result = service.start_vm(vmid)
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/vms/<int:vmid>/stop', methods=['POST'])
def stop_vm(vmid):
    service = ProxmoxService()
    result = service.stop_vm(vmid)
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/vms/<int:vmid>', methods=['DELETE'])
def delete_vm(vmid):
    service = ProxmoxService()
    result = service.delete_vm(vmid)
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/vms/<int:vmid>/pool', methods=['PUT'])
def assign_vm_to_pool_route(vmid):
    data = request.get_json()
    poolid = data.get('poolid')
    if poolid is None and 'poolid' not in data:
        return jsonify({'success': False, 'error': 'poolid é obrigatório.'}), 400
    service = ProxmoxService()
    result = service.assign_vm_to_pool(vmid, poolid)
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/vms/<int:vmid>/vnc', methods=['GET'])
def vm_vnc_console(vmid):
    service = ProxmoxService()
    result = service.get_vnc_console(vmid)
    return jsonify(result), 200 if result['success'] else 500

# --- Rotas de CTs (LXC) ---

@bp.route('/cts', methods=['GET'])
def list_containers():
    service = ProxmoxService()
    result = service.get_containers()
    return jsonify(result), 200 if result['success'] else 500

# @bp.route('/cts', methods=['POST'])
# def create_container():
#     data = request.get_json()
#     if not data or 'name' not in data or 'template' not in data or 'poolid' not in data:
#         return jsonify({'success': False, 'error': 'Name, template e poolid são obrigatórios.'}), 400
#     service = ProxmoxService()
#     result = service.create_container(data)
#     return jsonify(result), 201 if result['success'] else 500

@bp.route('/cts', methods=['POST'])
def create_container():
    data = request.get_json()
    # Supondo que você tenha o username do usuário autenticado (ex: via token)
    # Por enquanto, vamos assumir que o frontend envia o 'username' ou confiamos no 'poolid'
    
    # AJUSTE DE SEGURANÇA (Exemplo):
    # Se você quiser garantir o padrão vps-*, force aqui:
    if 'username' in data:
        data['poolid'] = f"vps-{data['username'].lower()}"
    
    # Validação do poolid (Mantida)
    if not data or 'name' not in data or 'template' not in data or 'poolid' not in data:
        return jsonify({
            'success': False,
            'error': 'Nome, Template e Pool ID (ou username) são obrigatórios.'
        }), 400
    
    service = ProxmoxService()
    result = service.create_container(data)
    
    return jsonify(result), 201 if result['success'] else 500

@bp.route('/cts/<int:ctid>/status', methods=['GET'])
def container_status(ctid):
    service = ProxmoxService()
    result = service.get_container_status(ctid)
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/cts/<int:ctid>', methods=['PUT'])
def update_container_resources_route(ctid):
    data = request.get_json()
    service = ProxmoxService()
    
    # Lógica de incremento de disco
    disk_increment_gb = data.pop('disk_increment_gb', None)
    if disk_increment_gb:
        try:
            current_config_result = service.get_container_config(ctid)
            if not current_config_result['success']: return jsonify(current_config_result), 500
            current_rootfs = current_config_result['data'].get('rootfs')
            if not current_rootfs: return jsonify({'success': False, 'error': 'Rootfs não encontrado.'}), 400
            
            new_size = parse_rootfs_size_gb(current_rootfs) + int(disk_increment_gb)
            data['rootfs'] = reconstruct_rootfs_string(current_rootfs, new_size)
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 400

    result = service.update_container_resources(ctid, data)
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/cts/<int:ctid>/start', methods=['POST'])
def start_container(ctid):
    service = ProxmoxService()
    result = service.start_container(ctid)
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/cts/<int:ctid>/stop', methods=['POST'])
def stop_container(ctid):
    service = ProxmoxService()
    result = service.stop_container(ctid)
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/cts/<int:ctid>', methods=['DELETE'])
def delete_container(ctid):
    service = ProxmoxService()
    result = service.delete_container(ctid)
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/cts/<int:ctid>/pool', methods=['PUT'])
def assign_ct_to_pool_route(ctid):
    data = request.get_json()
    poolid = data.get('poolid')
    if poolid is None and 'poolid' not in data:
        return jsonify({'success': False, 'error': 'poolid é obrigatório.'}), 400
    service = ProxmoxService()
    result = service.assign_ct_to_pool(ctid, poolid)
    return jsonify(result), 200 if result['success'] else 500

# --- Rotas de Storage ---

@bp.route('/storages', methods=['GET'])
def list_storages():
    service = ProxmoxService()
    result = service.get_storages()
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/storages/<storage_id>', methods=['GET'])
def storage_status(storage_id):
    service = ProxmoxService()
    result = service.get_storage_status(storage_id)
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/storages/<storage_id>/content', methods=['GET'])
def storage_content(storage_id):
    service = ProxmoxService()
    result = service.get_storage_content(storage_id)
    return jsonify(result), 200 if result['success'] else 500
# --- Rotas de Firewall (CTs) ---

@bp.route('/cts/<int:ctid>/firewall/enable', methods=['POST'])
def enable_ct_firewall_route(ctid):
    """Habilita o firewall no Contêiner."""
    service = ProxmoxService()
    result = service.enable_container_firewall(ctid)
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/cts/<int:ctid>/firewall/rules', methods=['POST'])
def add_ct_firewall_rule_route(ctid):
    """
    Adiciona uma regra de firewall.
    Body: { "type": "in", "action": "ACCEPT", "proto": "tcp", "dport": "22", "comment": "SSH Access" }
    """
    data = request.get_json()
    if not data or 'action' not in data:
        return jsonify({'success': False, 'error': 'Parâmetros inválidos. "action" é obrigatório.'}), 400
        
    service = ProxmoxService()
    result = service.add_firewall_rule(ctid, data)
    return jsonify(result), 201 if result['success'] else 500