from flask import Blueprint, jsonify, request, abort
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_cors import cross_origin
from app.models import ServiceTemplate, User
from app.extensions import db, proxmox_client

bp = Blueprint('catalog', __name__)

# --- HELPER DE PERMISSÃO ---
def check_admin_access():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user: abort(403)
    if user.is_admin: return user
    if user.group and user.group.name.lower() in ['admins', 'administradores', 'root', 'ti']: return user
    abort(403)

# ==============================================================================
# 1. ROTAS PÚBLICAS (Leitura para Alunos)
# ==============================================================================

@bp.route('/templates', methods=['GET', 'OPTIONS'])
@cross_origin()
@jwt_required()
def list_active_templates():
    """Retorna lista de templates ativos para o usuário final."""
    templates = ServiceTemplate.query.filter_by(is_active=True).all()
    return jsonify([t.to_dict() for t in templates]), 200


# ==============================================================================
# 2. ROTAS ADMINISTRATIVAS (Gestão Total)
# ==============================================================================

# ------------------------------------------------------------------------------
# COLEÇÃO: Listar Todos (GET) ou Criar Novo (POST)
# URL: /admin/templates
# ------------------------------------------------------------------------------
@bp.route('/admin/templates', methods=['GET', 'POST', 'OPTIONS'])
@cross_origin()
@jwt_required()
def manage_collection():
    check_admin_access()

    # [GET] Listar Todos (Incluindo inativos)
    if request.method == 'GET':
        templates = ServiceTemplate.query.all()
        return jsonify([t.to_dict() for t in templates]), 200

    # [POST] Criar Novo Template
    if request.method == 'POST':
        data = request.get_json()
        
        # Validação Básica
        if not data.get('name') or not data.get('proxmox_template_volid'):
            return jsonify({'error': 'Nome e ID Proxmox são obrigatórios.'}), 400

        # Leitura dos dados
        deploy_mode = data.get('deploy_mode', 'clone')
        res_type = data.get('type', 'lxc')
        volid = str(data.get('proxmox_template_volid'))
        
        # Defaults
        t_cpu = int(data.get('default_cpu', 1))
        t_mem = int(data.get('default_memory', 512))
        t_disk = int(data.get('default_storage', 8))

        # Lógica de Inspeção (Se for Clone)
        if deploy_mode == 'clone':
            if not volid.isdigit():
                return jsonify({'error': 'Modo Clone exige ID numérico (VMID).'}), 400
            try:
                # Tenta buscar a verdade no Proxmox
                real = proxmox_client.inspect_resource(int(volid), res_type)
                t_cpu, t_mem, t_disk = real['cpu'], real['memory'], real['storage']
            except Exception as e:
                return jsonify({'error': f'Erro ao ler Proxmox: {str(e)}'}), 500

        # Persistência
        try:
            new_tmpl = ServiceTemplate(
                name=data['name'],
                type=res_type,
                proxmox_template_volid=volid,
                deploy_mode=deploy_mode,
                description=data.get('description', ''),
                category=data.get('category', 'os'),
                logo_url=data.get('logo_url', ''),
                is_active=data.get('is_active', True),
                default_cpu=t_cpu,
                default_memory=t_mem,
                default_storage=t_disk
            )
            db.session.add(new_tmpl)
            db.session.commit()
            return jsonify({'success': True, 'id': new_tmpl.id}), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500


# ------------------------------------------------------------------------------
# ITEM ÚNICO: Editar (PUT) ou Deletar (DELETE)
# URL: /admin/templates/<id>
# ------------------------------------------------------------------------------
@bp.route('/admin/templates/<int:template_id>', methods=['PUT', 'DELETE', 'OPTIONS'])
@cross_origin()
@jwt_required()
def manage_single_item(template_id):
    check_admin_access()
    template = ServiceTemplate.query.get_or_404(template_id)

    # [PUT] Atualizar Template
    if request.method == 'PUT':
        data = request.get_json()
        try:
            # Atualiza campos simples
            if 'name' in data: template.name = data['name']
            if 'description' in data: template.description = data['description']
            if 'category' in data: template.category = data['category']
            if 'is_active' in data: template.is_active = data['is_active']
            if 'type' in data: template.type = data['type']
            if 'deploy_mode' in data: template.deploy_mode = data['deploy_mode']
            if 'proxmox_template_volid' in data: template.proxmox_template_volid = data['proxmox_template_volid']

            # Se for Clone, tenta atualizar specs via Proxmox
            if template.deploy_mode == 'clone':
                try:
                    if str(template.proxmox_template_volid).isdigit():
                        real = proxmox_client.inspect_resource(int(template.proxmox_template_volid), template.type)
                        template.default_cpu = real['cpu']
                        template.default_memory = real['memory']
                        template.default_storage = real['storage']
                except: pass # Se falhar, mantém os antigos
            else:
                # Se for File, aceita edição manual
                if 'default_cpu' in data: template.default_cpu = int(data['default_cpu'])
                if 'default_memory' in data: template.default_memory = int(data['default_memory'])
                if 'default_storage' in data: template.default_storage = int(data['default_storage'])

            db.session.commit()
            return jsonify({'success': True, 'data': template.to_dict()})
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    # [DELETE] Remover Template
    if request.method == 'DELETE':
        try:
            nome_bkp = template.name
            db.session.delete(template)
            db.session.commit()
            return jsonify({'success': True, 'message': f"Template '{nome_bkp}' removido."})
        except Exception as e:
            db.session.rollback()
            # Tratamento de chave estrangeira (se já houver instâncias criadas)
            if "foreign key" in str(e).lower():
                return jsonify({'error': 'Não é possível remover: Existem instâncias usando este template.'}), 409
            return jsonify({'error': str(e)}), 500