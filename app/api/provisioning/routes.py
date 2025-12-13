from flask import Blueprint, jsonify, request, abort, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import ServiceTemplate, VirtualResource, User
from app.proxmox import ProxmoxService 
from app.extensions import db
import re

# Tenta importar utils de forma robusta
try:
    from app.utils import check_user_quota
except ImportError:
    from utils.utils import check_user_quota 

bp = Blueprint('provisioning', __name__)

def get_service():
    return ProxmoxService()

@bp.route('/deploy', methods=['POST'])
@jwt_required()
def deploy_resource():
    """
    Provisiona um novo recurso.
    """
    # 1. RECUPERAR USUÁRIO
    current_user_id = int(get_jwt_identity())
    user = User.query.get(current_user_id)
    
    if not user:
        abort(401, description="Usuário não encontrado.")

    # 2. RECUPERAR DADOS (MOVIDO PARA O TOPO - CRÍTICO!)
    data = request.get_json() or {}
    template_id = data.get('template_id')
    name = data.get('name') # <--- A variável 'name' nasce aqui
    
    if not template_id or not name:
        abort(400, description="template_id e name são obrigatórios.")

    # 3. VALIDAÇÃO DE NOME (Agora 'name' já existe, então funciona)
    if not re.match(r'^[a-zA-Z0-9-]+$', name):
        abort(400, description="Nome inválido. Use apenas letras, números e hífens.")

    # 4. OBTER TEMPLATE
    template = ServiceTemplate.query.get_or_404(template_id)
    
    # 5. RECURSOS DO TEMPLATE (Fixo)
    req_cpu = template.default_cpu
    req_ram = template.default_memory
    req_storage = template.default_storage
    
    # 6. VERIFICAR COTA
    can_create, reason = check_user_quota(user, req_cpu, req_ram, req_storage)
    if not can_create:
        abort(403, description=f"Cota excedida: {reason}")

    service = get_service()
    
    # Inicializa new_id para o tratamento de erro
    new_id = None
    resource_type = template.type 

    try:
        # --- ORQUESTRAÇÃO PROXMOX ---
        
        # A. Garante infraestrutura do usuário
        target_pool = service.ensure_user_pool(user.username)
        
        # Configuração de Realm segura
        realm = current_app.config.get('PROXMOX_AUTH_REALM', 'pve-ldap-mock')
        
        pve_userid = service.ensure_pve_user(user.username, realm)
        service.set_pool_permission(target_pool, pve_userid, role='PVEVMUser')
        
        # B. Deploy Técnico
        if template.deploy_mode == 'clone':
            new_id = service.get_next_vmid()
            
            # Clone sem override (usa o hardware do template)
            if resource_type == 'lxc':
                service.clone_container(
                    source_vmid=template.proxmox_template_volid,
                    new_vmid=new_id,
                    name=name,
                    poolid=target_pool,
                    full_clone=True
                )
            # elif resource_type == 'qemu': ...

        elif template.deploy_mode == 'file':
            pass

        # --- PERSISTÊNCIA ---
        resource = VirtualResource(
            proxmox_vmid=new_id,
            name=name,
            type=resource_type,
            template_id=template.id,
            owner_id=user.id,
            cpu_cores=req_cpu,
            memory_mb=req_ram,
            storage_gb=req_storage
        )
        db.session.add(resource)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f"Recurso {name} ({new_id}) criado.",
            'vmid': new_id,
            'pool': target_pool
        }), 201

    except Exception as e:
        db.session.rollback()
        
        # Anti-Zumbi: Limpa no Proxmox se falhar no banco
        if new_id:
            print(f"⚠️ Limpando VM zumbi {new_id}...")
            try:
                if resource_type == 'lxc':
                    service.stop_container(new_id)
                    service.delete_container(new_id)
            except Exception:
                pass
        
        # Retorna erro JSON em vez de estourar HTML
        return jsonify({'error': str(e)}), 500

@bp.route('/resources/<int:vmid>/scale', methods=['PUT'])
@jwt_required()
def scale_resource(vmid):
    """Altera recursos de uma VM existente."""
    current_user_id = int(get_jwt_identity())
    user = User.query.get(current_user_id)
    resource = VirtualResource.query.filter_by(proxmox_vmid=vmid).first_or_404()
    
    if resource.owner_id != current_user_id and not getattr(user, 'is_admin', False):
        abort(403, description="Acesso negado.")

    data = request.get_json() or {}
    new_ram = int(data.get('memory', resource.memory_mb))
    new_cpu = int(data.get('cores', resource.cpu_cores))
    
    # Verificar Cota (Apenas se user.quota existir)
    if user.quota:
        all_resources = VirtualResource.query.filter_by(owner_id=user.id).all()
        total_ram = sum(r.memory_mb for r in all_resources)
        total_cpu = sum(r.cpu_cores for r in all_resources)
        
        projected_ram = (total_ram - resource.memory_mb) + new_ram
        projected_cpu = (total_cpu - resource.cpu_cores) + new_cpu
        
        if projected_ram > user.quota.max_memory_mb:
            abort(403, description=f"Cota de RAM excedida. Limite: {user.quota.max_memory_mb}MB.")

    service = get_service()
    updates = {}
    if 'memory' in data: updates['memory'] = new_ram
    if 'cores' in data: updates['cores'] = new_cpu
    
    try:
        if resource.type == 'lxc':
            service.update_container_resources(vmid, updates)
        
        resource.memory_mb = new_ram
        resource.cpu_cores = new_cpu
        db.session.commit()
        
        return jsonify({'success': True, 'new_specs': {'ram': new_ram, 'cpu': new_cpu}})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/resources/<int:vmid>', methods=['DELETE'])
@jwt_required()
def destroy_resource(vmid):
    """Destrói o recurso."""
    current_user_id = int(get_jwt_identity())
    resource = VirtualResource.query.filter_by(proxmox_vmid=vmid).first_or_404()
    user = User.query.get(current_user_id)
    
    if resource.owner_id != current_user_id and not getattr(user, 'is_admin', False):
         abort(403, description="Sem permissão.")

    service = get_service()
    
    try:
        try:
            if resource.type == 'lxc': service.stop_container(vmid)
        except Exception: pass
        
        if resource.type == 'lxc':
            service.delete_container(vmid)
        
        db.session.delete(resource)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Recurso destruído.'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/resources', methods=['GET'])
@jwt_required()
def list_user_resources():
    """Lista recursos do usuário."""
    current_user_id = int(get_jwt_identity())
    resources = VirtualResource.query.filter_by(owner_id=current_user_id).all()
    
    output = []
    for r in resources:
        output.append({
            'id': r.id,
            'vmid': r.proxmox_vmid,
            'name': r.name,
            'type': r.type,
            'status': r.status,
            'cpu': r.cpu_cores,
            'ram': r.memory_mb,
            'storage': r.storage_gb,
            'created_at': r.created_at.isoformat() if r.created_at else None
        })
    return jsonify(output)