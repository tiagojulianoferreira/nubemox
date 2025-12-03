from flask import jsonify, request, current_app
from app.api.proxmox import bp
from app.services.proxmox_service import ProxmoxService
from proxmoxer import ResourceException
import re
# ATENÇÃO: Assumindo que você criou o arquivo app/utils/config_helpers.py
# Estas funções são necessárias para a rota PUT /cts/<ctid>
#from app.utils.config_helpers import parse_rootfs_size_gb, reconstruct_rootfs_string

# Para simplificar, definiremos as funções helper aqui, mas o ideal é movê-las
def parse_rootfs_size_gb(rootfs_string: str) -> int:
    """Extrai o tamanho do disco em GB de uma string rootfs do PVE."""
    match = re.search(r'size=(\d+)(G|g)', rootfs_string)
    if match:
        return int(match.group(1))
    raise ValueError("Formato de rootfs size inválido ou não encontrado.")

def reconstruct_rootfs_string(rootfs_string: str, new_size_gb: int) -> str:
    """Substitui o tamanho do disco na string rootfs do PVE."""
    return re.sub(r'size=\d+[Gg]', f'size={new_size_gb}G', rootfs_string)


# --- Rotas de Cluster (Não requerem node na URL) ---

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
        'nodes': [node_data.get('node') for node_data in nodes_result['data']],
        'total_vms': 'N/A', 
        'total_containers': 'N/A'
    }
    
    return jsonify(summary), 200

# --- Rotas de Status e Gerenciamento por Node ---

@bp.route('/nodes/<node>/status', methods=['GET'])
def node_status(node):
    """Obtém status de um node específico"""
    service = ProxmoxService()
    result = service.get_node_status(node)
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/nodes/<node>/vms', methods=['GET'])
def list_vms_by_node(node):
    """Lista todas as VMs de um node"""
    service = ProxmoxService()
    result = service.get_vms(node)
    return jsonify(result), 200 if result['success'] else 500

# --- Rotas de Gerenciamento de Resource Pools (NOVAS) ---

@bp.route('/pools', methods=['GET'])
def list_pools():
    """Lista todos os Resource Pools"""
    service = ProxmoxService()
    result = service.get_pools()
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/pools', methods=['POST'])
def create_pool():
    """Cria um novo Resource Pool (Requer poolid)"""
    data = request.get_json()
    
    if not data or 'poolid' not in data:
        return jsonify({
            'success': False,
            'error': 'O campo poolid é obrigatório para criar um Pool.'
        }), 400
        
    service = ProxmoxService()
    result = service.create_pool(data.get('poolid'), data.get('comment'))
    
    return jsonify(result), 201 if result['success'] else 500

# --- Rotas de Listagem e Criação (Node Padrão) ---

@bp.route('/vms', methods=['GET'])
def list_vms():
    """Lista todas as VMs do node padrão"""
    service = ProxmoxService()
    result = service.get_vms()
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/cts', methods=['GET'])
def list_containers():
    """Lista todos os contêineres (CTs) do node padrão"""
    service = ProxmoxService()
    result = service.get_containers()
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/vms', methods=['POST'])
def create_vm():
    """Cria uma nova VM no node padrão (poolid obrigatório)"""
    data = request.get_json()
    
    # Validação do poolid
    if not data or 'name' not in data or 'poolid' not in data:
        return jsonify({
            'success': False,
            'error': 'Nome (name) e Pool ID (poolid) são obrigatórios para a criação da VM.'
        }), 400
    
    service = ProxmoxService()
    result = service.create_vm(data)
    
    return jsonify(result), 201 if result['success'] else 500

@bp.route('/cts', methods=['POST'])
def create_container():
    """Cria um novo Contêiner LXC no node padrão (poolid obrigatório)"""
    data = request.get_json()
    
    # Validação do poolid
    if not data or 'name' not in data or 'template' not in data or 'poolid' not in data:
        return jsonify({
            'success': False,
            'error': 'Nome (name), Template (template) e Pool ID (poolid) são obrigatórios para a criação do Contêiner.'
        }), 400
    
    service = ProxmoxService()
    result = service.create_container(data)
    
    return jsonify(result), 201 if result['success'] else 500

# --- Rotas de Ação e Status por ID (VM) ---

@bp.route('/vms/<int:vmid>/status', methods=['GET'])
def vm_status(vmid):
    """Obtém status de uma VM específica no node padrão"""
    service = ProxmoxService()
    result = service.get_vm_status(vmid)
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/vms/<int:vmid>/vnc', methods=['GET'])
def vm_vnc_console(vmid):
    """Obtém informações para console VNC da VM no node padrão"""
    service = ProxmoxService()
    result = service.get_vnc_console(vmid)
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

@bp.route('/vms/<int:vmid>', methods=['DELETE'])
def delete_vm(vmid):
    """Exclui permanentemente uma VM no node padrão"""
    service = ProxmoxService()
    result = service.delete_vm(vmid)
    return jsonify(result), 200 if result['success'] else 500

# --- Rotas de Ação e Status por ID (CT) ---

@bp.route('/cts/<int:ctid>/status', methods=['GET'])
def container_status(ctid):
    """Obtém status de um Contêiner específico no node padrão"""
    service = ProxmoxService()
    result = service.get_container_status(ctid)
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/cts/<int:ctid>', methods=['PUT'])
def update_container_resources_route(ctid):
    """
    Atualiza recursos (memória, cores, etc.) de um Contêiner LXC.
    Permite atualização de disco via 'disk_increment_gb'.
    """
    data = request.get_json()
    service = ProxmoxService()
    
    disk_increment_gb = data.pop('disk_increment_gb', None)
    
    if disk_increment_gb:
        try:
            # Requer um novo método no service para buscar a config
            current_config_result = service.get_container_config(ctid)
            if not current_config_result['success']:
                return jsonify(current_config_result), 500
                
            current_rootfs_string = current_config_result['data'].get('rootfs')
            
            if not current_rootfs_string:
                return jsonify({'success': False, 'error': 'Configuração de disco (rootfs) não encontrada para o Contêiner.'}), 400
            
            increment_value = int(disk_increment_gb)
            current_size_gb = parse_rootfs_size_gb(current_rootfs_string)
            
            new_size_gb = current_size_gb + increment_value
            
            if new_size_gb <= current_size_gb:
                return jsonify({'success': False, 'error': f'O incremento deve resultar em um tamanho maior que o atual ({current_size_gb}G).'}), 400
            
            # Formata o novo tamanho no padrão PVE e adiciona ao 'data'
            data['rootfs'] = reconstruct_rootfs_string(current_rootfs_string, new_size_gb)
            
        except ResourceException as e:
            return jsonify({'success': False, 'error': f"Erro ao buscar configuração do CT para calcular disco: {str(e)}"}), 500
        except ValueError:
             return jsonify({'success': False, 'error': 'O valor do incremento de disco deve ser um número inteiro válido.'}), 400
        
    # Continua com a atualização de recursos
    result = service.update_container_resources(ctid, data)
    
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/cts/<int:ctid>/start', methods=['POST'])
def start_container(ctid):
    """Inicia um Contêiner no node padrão"""
    service = ProxmoxService()
    result = service.start_container(ctid)
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/cts/<int:ctid>/stop', methods=['POST'])
def stop_container(ctid):
    """Para um Contêiner no node padrão"""
    service = ProxmoxService()
    result = service.stop_container(ctid)
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/cts/<int:ctid>', methods=['DELETE'])
def delete_container(ctid):
    """Exclui permanentemente um Contêiner no node padrão"""
    service = ProxmoxService()
    result = service.delete_container(ctid)
    return jsonify(result), 200 if result['success'] else 500

# --- Rotas de Storage (Mantidas) ---

@bp.route('/storages', methods=['GET'])
def list_storages():
    """Lista todos os storages do cluster"""
    service = ProxmoxService()
    result = service.get_storages()
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/storages/<storage_id>', methods=['GET'])
def storage_status(storage_id):
    """Obtém status de um storage específico"""
    service = ProxmoxService()
    result = service.get_storage_status(storage_id)
    return jsonify(result), 200 if result['success'] else 500

@bp.route('/storages/<storage_id>/content', methods=['GET'])
def storage_content(storage_id):
    """Lista o conteúdo de um storage (templates, discos, etc.)"""
    service = ProxmoxService()
    result = service.get_storage_content(storage_id)
    return jsonify(result), 200 if result['success'] else 500