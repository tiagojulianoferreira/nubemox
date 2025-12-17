from flask import Blueprint, jsonify, request, abort
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_cors import cross_origin
from app.models import ServiceTemplate, User
from app.extensions import db, proxmox_client

bp = Blueprint('catalog', __name__)

# --- HELPER DE PERMISSÃO ---
def check_admin_access():
    """
    Verifica se o usuário é Admin (flag) ou do grupo 'Admins'.
    Lança exceção 403 se não for.
    """
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    if not user:
        abort(403, description="Usuário não encontrado.")

    # 1. Flag direta
    if user.is_admin:
        return user
    
    # 2. Verificação de Grupo (Case insensitive)
    if user.group and user.group.name.lower() in ['admins', 'administradores', 'root', 'ti']:
        return user

    abort(403, description="Acesso restrito a administradores.")

# ----------------------------------------------------------------
# ROTA PÚBLICA (Para usuários finais - Apenas Ativos)
# ----------------------------------------------------------------
@bp.route('/templates', methods=['GET', 'OPTIONS'])
@cross_origin()
@jwt_required()
def list_templates():
    """Lista apenas templates ATIVOS para uso no Deploy."""
    templates = ServiceTemplate.query.filter_by(is_active=True).all()
    return jsonify([t.to_dict() for t in templates]), 200

# ----------------------------------------------------------------
# ROTAS ADMINISTRATIVAS (CRUD COMPLETO)
# ----------------------------------------------------------------

@bp.route('/admin/templates', methods=['GET', 'OPTIONS'])
@cross_origin()
@jwt_required()
def list_all_templates_admin():
    """Lista TODOS os templates (ativos e inativos) para gestão."""
    check_admin_access()
    templates = ServiceTemplate.query.order_by(ServiceTemplate.id).all()
    return jsonify([t.to_dict() for t in templates]), 200


@bp.route('/templates', methods=['POST', 'OPTIONS'])
@cross_origin()
@jwt_required()
def create_template():
    """Cria um novo template no catálogo com validação de modo (Clone vs File)."""
    check_admin_access()
    data = request.get_json()

    # 1. Validação de Campos Obrigatórios
    if not data.get('name') or not data.get('proxmox_template_volid'):
        return jsonify({'error': 'Nome e ID/Volid do Proxmox são obrigatórios.'}), 400

    # 2. Validação Lógica de Tipo (Clone vs File)
    deploy_mode = data.get('deploy_mode', 'clone')
    volid = str(data.get('proxmox_template_volid'))

    if deploy_mode == 'clone':
        # Modo CLONE (VM): Exige ID numérico (ex: 100, 101)
        if not volid.isdigit():
            return jsonify({'error': 'No modo Clone (VM), o ID deve ser numérico (ex: 100).'}), 400
    
    elif deploy_mode == 'file':
        # Modo FILE (Container Template): Exige string com storage (ex: local:vztmpl/image.tar.zst)
        if ':' not in volid:
            return jsonify({'error': 'No modo File (LXC), use o formato Storage:Path (ex: local:vztmpl/ubuntu-22.04.tar.zst).'}), 400

    try:
        new_tmpl = ServiceTemplate(
            name=data['name'],
            type=data.get('type', 'lxc'), # lxc ou qemu
            proxmox_template_volid=data['proxmox_template_volid'],
            deploy_mode=deploy_mode,
            description=data.get('description', ''),
            category=data.get('category', 'os'),
            logo_url=data.get('logo_url', ''), # Frontend deve tratar imagem quebrada se vazio
            is_active=data.get('is_active', True),
            default_cpu=int(data.get('default_cpu', 1)),
            default_memory=int(data.get('default_memory', 512)),
            default_storage=int(data.get('default_storage', 8))
        )

        db.session.add(new_tmpl)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Template criado com sucesso.', 'id': new_tmpl.id}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/templates/<int:template_id>', methods=['PUT', 'OPTIONS'])
@cross_origin()
@jwt_required()
def update_template(template_id):
    """
    Atualiza um template. 
    Lógica inteligente: Só tenta sincronizar com Proxmox se for VM/Clone.
    Se for arquivo (LXC template), apenas salva a string (corrigindo o erro).
    """
    check_admin_access()
    template = ServiceTemplate.query.get_or_404(template_id)
    data = request.get_json()

    try:
        # 1. Atualiza campos básicos
        if 'name' in data: template.name = data['name']
        if 'description' in data: template.description = data['description']
        if 'proxmox_template_volid' in data: template.proxmox_template_volid = data['proxmox_template_volid']
        if 'type' in data: template.type = data['type']
        if 'deploy_mode' in data: template.deploy_mode = data['deploy_mode']
        if 'logo_url' in data: template.logo_url = data['logo_url']
        if 'category' in data: template.category = data['category']
        if 'is_active' in data: template.is_active = bool(data['is_active'])
        
        # Atualiza specs manuais (se fornecidas)
        if 'default_cpu' in data: template.default_cpu = int(data['default_cpu'])
        if 'default_memory' in data: template.default_memory = int(data['default_memory'])
        if 'default_storage' in data: template.default_storage = int(data['default_storage'])

        # 2. Sincronização Opcional com Proxmox (Apenas para CLONE de VM)
        # Se estamos corrigindo um erro de arquivo inexistente, NÃO queremos que isso rode e falhe.
        should_sync = data.get('sync_pve', False) 
        pve_warning = None

        if should_sync and template.deploy_mode == 'clone' and str(template.proxmox_template_volid).isdigit():
            try:
                # Tenta ler a config lá no Proxmox para preencher CPU/RAM automaticamente
                vmid = int(template.proxmox_template_volid)
                config = proxmox_client.get_vm_config(vmid) # Você precisará garantir que esse método existe no client.py
                
                if config:
                    template.default_memory = int(config.get('memory', template.default_memory))
                    # Lógica para cores vs sockets
                    sockets = int(config.get('sockets', 1))
                    cores = int(config.get('cores', 1))
                    template.default_cpu = sockets * cores
            except Exception as e:
                pve_warning = f"Dados salvos, mas falha ao sincronizar specs do PVE: {str(e)}"

        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Template atualizado.', 
            'warning': pve_warning,
            'data': template.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/templates/<int:template_id>', methods=['DELETE', 'OPTIONS'])
@cross_origin()
@jwt_required()
def delete_template(template_id):
    """Remove o template do catálogo (não deleta do Proxmox)."""
    check_admin_access()
    template = ServiceTemplate.query.get_or_404(template_id)
    
    try:
        db.session.delete(template)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Template removido do catálogo.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500