from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_cors import cross_origin
from app.models import User, VirtualResource, ServiceTemplate
from app.extensions import db
from app.proxmox import proxmox_client
import math

bp = Blueprint('admin', __name__, url_prefix='/api/admin')

def get_current_usage(user_id):
    """Calcula o consumo atual de recursos do usuário (Interno)."""
    resources = VirtualResource.query.filter_by(owner_id=user_id).all()
    return {
        'cpu': sum(r.cpu_cores for r in resources),
        'memory': sum(r.memory_mb for r in resources),
        'storage': sum(r.storage_gb for r in resources),
        'count': len(resources)
    }

# ==========================================
#  GESTÃO DE USUÁRIOS
# ==========================================

@bp.route('/users', methods=['GET', 'OPTIONS'])
@cross_origin()
@jwt_required()
def list_users():
    """
    Lista todos os usuários e suas cotas.
    ---
    tags:
      - Admin Users
    security:
      - Bearer: []
    responses:
      200:
        description: Lista de usuários recuperada com sucesso
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
              username:
                type: string
              usage:
                type: object
              limits:
                type: object
      403:
        description: Acesso negado (Requer Admin)
    """
    current_user_id = int(get_jwt_identity())
    admin = User.query.get(current_user_id)
    
    if not admin or not getattr(admin, 'is_admin', False):
        return jsonify({"error": "Acesso negado. Requer privilégios de Admin."}), 403

    users = User.query.all()
    output = []

    for u in users:
        usage = get_current_usage(u.id)
        limits = u.quota.get('limit', {}) if u.quota else {}
        
        output.append({
            'id': u.id,
            'username': u.username,
            'email': u.email,
            'is_admin': u.is_admin,
            'usage': usage,
            'limits': {
                'cpu': limits.get('cpu', 0),
                'memory': limits.get('memory', 0),
                'storage': limits.get('storage', 0)
            }
        })

    return jsonify(output)

@bp.route('/users/<int:user_id>/quota', methods=['PUT', 'OPTIONS'])
@cross_origin()
@jwt_required()
def update_user_quota(user_id):
    """
    Atualiza as cotas de um usuário.
    ---
    tags:
      - Admin Users
    security:
      - Bearer: []
    parameters:
      - name: user_id
        in: path
        type: integer
        required: true
        description: ID do usuário alvo
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            cpu:
              type: integer
            memory:
              type: integer
            storage:
              type: integer
    responses:
      200:
        description: Cota atualizada
      404:
        description: Usuário não encontrado
    """
    current_user_id = int(get_jwt_identity())
    admin = User.query.get(current_user_id)
    
    if not admin or not getattr(admin, 'is_admin', False):
        return jsonify({"error": "Acesso negado."}), 403

    target_user = User.query.get(user_id)
    if not target_user:
        return jsonify({"error": "Usuário alvo não encontrado"}), 404

    data = request.get_json()
    
    current_quota = target_user.quota if target_user.quota else {}
    if 'limit' not in current_quota:
        current_quota['limit'] = {}

    if 'cpu' in data: current_quota['limit']['cpu'] = int(data['cpu'])
    if 'memory' in data: current_quota['limit']['memory'] = int(data['memory'])
    if 'storage' in data: current_quota['limit']['storage'] = int(data['storage'])

    target_user.quota = dict(current_quota)
    db.session.commit()
    
    return jsonify({"message": "Cota atualizada com sucesso", "quota": current_quota})


# ==========================================
#  GESTÃO DE TEMPLATES (CURADORIA)
# ==========================================

@bp.route('/templates', methods=['GET', 'OPTIONS'])
@cross_origin()
@jwt_required()
def list_templates():
    """
    Lista todos os templates cadastrados (Ativos e Inativos).
    ---
    tags:
      - Admin Templates
    security:
      - Bearer: []
    responses:
      200:
        description: Lista de templates do banco de dados
    """
    templates = ServiceTemplate.query.all()
    return jsonify([{
        'id': t.id,
        'name': t.name,
        'type': t.type, 
        'proxmox_template_volid': t.proxmox_template_volid,
        'category': t.category,
        'deploy_mode': getattr(t, 'deploy_mode', 'file'),
        'is_active': getattr(t, 'is_active', False),
        'default_cpu': t.default_cpu,
        'default_memory': t.default_memory,
        'default_storage': t.default_storage
    } for t in templates])

@bp.route('/templates/scan', methods=['GET', 'OPTIONS'])
@cross_origin()
@jwt_required()
def scan_templates_pve():
    """
    Scaneia o Proxmox por novos templates (Sem gravar no DB).
    ---
    tags:
      - Admin Templates
    security:
      - Bearer: []
    description: Lê o storage 'local' do Proxmox, calcula tamanho real (GB) e retorna candidatos.
    responses:
      200:
        description: Lista de candidatos encontrados
        schema:
          type: array
          items:
            type: object
            properties:
              volid:
                type: string
              name:
                type: string
              type:
                type: string
              detected_size_gb:
                type: integer
      500:
        description: Erro de conexão com Proxmox
    """
    try:
        current_user_id = int(get_jwt_identity())
        admin = User.query.get(current_user_id)
        if not getattr(admin, 'is_admin', False): return jsonify({"error": "Acesso negado."}), 403

        node = proxmox_client._resolve_node_id()
        target_storage = 'local' 
        
        try:
            contents = proxmox_client.connection.nodes(node).storage(target_storage).content.get()
        except Exception:
            return jsonify({'error': f"Não foi possível ler o storage '{target_storage}'."}), 500
        
        existing_volids = [t.proxmox_template_volid for t in ServiceTemplate.query.all()]
        candidates = []
        
        for item in contents:
            volid = item.get('volid')
            content_type = item.get('content') 
            size_bytes = int(item.get('size', 0))
            
            # Converte Bytes para GB (Arredonda para cima)
            size_gb = math.ceil(size_bytes / (1024**3))
            if size_gb < 1: size_gb = 1

            if content_type in ['vztmpl', 'iso'] and volid not in existing_volids:
                candidates.append({
                    'volid': volid,
                    'name': volid.split('/')[-1].replace('.iso', '').replace('.tar.zst', ''),
                    'type': 'lxc' if content_type == 'vztmpl' else 'qemu',
                    'detected_size_gb': size_gb 
                })
        
        return jsonify(candidates)

    except Exception as e:
        print(f"Erro Scan: {e}")
        return jsonify({'error': str(e)}), 500

@bp.route('/templates/import', methods=['POST', 'OPTIONS'])
@cross_origin()
@jwt_required()
def import_selected_templates():
    """
    Importa templates selecionados para o banco de dados.
    ---
    tags:
      - Admin Templates
    security:
      - Bearer: []
    parameters:
      - name: body
        in: body
        required: true
        description: Lista de objetos de template selecionados no scan
        schema:
          type: object
          properties:
            templates:
              type: array
              items:
                type: object
                properties:
                  volid:
                    type: string
                  name:
                    type: string
                  type:
                    type: string
                  detected_size_gb:
                    type: integer
    responses:
      200:
        description: Sucesso na importação
    """
    current_user_id = int(get_jwt_identity())
    admin = User.query.get(current_user_id)
    if not getattr(admin, 'is_admin', False): return jsonify({"error": "Acesso negado."}), 403

    data = request.get_json()
    selected_items = data.get('templates', []) 
    
    added_count = 0
    for item in selected_items:
        exists = ServiceTemplate.query.filter_by(proxmox_template_volid=item['volid']).first()
        if not exists:
            new_tmpl = ServiceTemplate(
                name=item['name'],
                proxmox_template_volid=item['volid'],
                type=item['type'],
                deploy_mode='file',
                category='os',
                is_active=False, # Nasce oculto/inativo
                default_cpu=1,
                default_memory=512,
                default_storage=item.get('detected_size_gb', 5) # Usa o tamanho real detectado
            )
            db.session.add(new_tmpl)
            added_count += 1
    
    db.session.commit()
    return jsonify({'success': True, 'message': f'{added_count} templates importados com sucesso.'})

@bp.route('/templates/<int:id>/toggle', methods=['PUT', 'OPTIONS'])
@cross_origin()
@jwt_required()
def toggle_template(id):
    """
    Ativa ou Desativa um template no catálogo.
    ---
    tags:
      - Admin Templates
    security:
      - Bearer: []
    parameters:
      - name: id
        in: path
        type: integer
        required: true
        description: ID do template
    responses:
      200:
        description: Status alterado
    """
    current_user_id = int(get_jwt_identity())
    admin = User.query.get(current_user_id)
    if not getattr(admin, 'is_admin', False): return jsonify({"error": "Acesso negado."}), 403

    tmpl = ServiceTemplate.query.get_or_404(id)
    tmpl.is_active = not tmpl.is_active
    db.session.commit()
    
    return jsonify({
        'success': True, 
        'is_active': tmpl.is_active,
        'message': f'Template {"ativado" if tmpl.is_active else "desativado"}.'
    })

@bp.route('/templates/<int:id>', methods=['PUT', 'OPTIONS'])
@cross_origin()
@jwt_required()
def update_template(id):
    """
    Atualiza as configurações padrão de um template (Com trava de disco).
    ---
    tags:
      - Admin Templates
    security:
      - Bearer: []
    parameters:
      - name: id
        in: path
        type: integer
        required: true
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            name:
              type: string
            category:
              type: string
            default_cpu:
              type: integer
            default_memory:
              type: integer
            default_storage:
              type: integer
              description: O valor não pode ser menor que o atual (proteção lógica)
    responses:
      200:
        description: Template atualizado
    """
    current_user_id = int(get_jwt_identity())
    admin = User.query.get(current_user_id)
    if not getattr(admin, 'is_admin', False): return jsonify({"error": "Acesso negado."}), 403

    tmpl = ServiceTemplate.query.get_or_404(id)
    data = request.get_json()

    if 'name' in data: tmpl.name = data['name']
    if 'category' in data: tmpl.category = data['category']
    if 'default_cpu' in data: tmpl.default_cpu = int(data['default_cpu'])
    if 'default_memory' in data: tmpl.default_memory = int(data['default_memory'])
    
    # Proteção de Backend para o Disco
    if 'default_storage' in data: 
        new_storage = int(data['default_storage'])
        if new_storage >= tmpl.default_storage:
            tmpl.default_storage = new_storage
        # Se for menor, ignora silenciosamente

    db.session.commit()
    return jsonify({'success': True, 'message': 'Template atualizado.'})