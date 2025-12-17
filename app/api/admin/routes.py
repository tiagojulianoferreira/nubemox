from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_cors import cross_origin
from app.models import User, VirtualResource, ServiceTemplate
from app.extensions import db
from app.proxmox import proxmox_client
import math

# Define o prefixo da URL como /api/admin
bp = Blueprint('admin', __name__, url_prefix='/api/admin')

def check_admin_permission():
    """Helper para verificar permissão de admin."""
    current_user_id = int(get_jwt_identity())
    admin = User.query.get(current_user_id)
    if not admin or not getattr(admin, 'is_admin', False):
        return False
    return True

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
    Lista todos os usuários e seus consumos de recursos.
    ---
    tags:
      - Admin Users
    security:
      - Bearer: []
    responses:
      200:
        description: Lista de usuários recuperada com sucesso.
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
              username:
                type: string
              email:
                type: string
              is_admin:
                type: boolean
              usage:
                type: object
                properties:
                  cpu:
                    type: integer
                  memory:
                    type: integer
                  storage:
                    type: integer
                  count:
                    type: integer
              limits:
                type: object
      403:
        description: Acesso negado.
    """
    if not check_admin_permission(): return jsonify({"error": "Acesso negado."}), 403

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
    Atualiza as cotas (limites) de um usuário específico.
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
              description: "Limite de Cores (ex: 4)"
            memory:
              type: integer
              description: "Limite de RAM em MB (ex: 4096)"
            storage:
              type: integer
              description: "Limite de Disco em GB (ex: 50)"
    responses:
      200:
        description: Cota atualizada com sucesso.
      404:
        description: Usuário não encontrado.
    """
    if not check_admin_permission(): return jsonify({"error": "Acesso negado."}), 403

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
    Lista todos os templates cadastrados no sistema.
    ---
    tags:
      - Admin Templates
    security:
      - Bearer: []
    responses:
      200:
        description: Lista de templates.
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
              name:
                type: string
              deploy_mode:
                type: string
                enum: ['clone', 'file', 'create']
              proxmox_template_volid:
                type: string
              is_active:
                type: boolean
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
    Varre o Proxmox em busca de candidatos a template.
    ---
    tags:
      - Admin Templates
    security:
      - Bearer: []
    description: >
      Busca em 3 locais:
      1. Storage 'local' por arquivos ISO e Vztmpl (Modo File).
      2. Lista de VMs QEMU com flag 'template=1' (Modo Clone).
      3. Lista de Containers LXC com flag 'template=1' (Modo Clone).
    responses:
      200:
        description: Lista de candidatos encontrados no Proxmox.
        schema:
          type: array
          items:
            type: object
            properties:
              volid:
                type: string
                description: ID ou Caminho do recurso
              name:
                type: string
              type:
                type: string
                enum: ['lxc', 'qemu']
              origin:
                type: string
                enum: ['file', 'vm']
              detected_size_gb:
                type: integer
    """
    if not check_admin_permission(): return jsonify({"error": "Acesso negado."}), 403

    try:
        node = proxmox_client._resolve_node_id()
        target_storage = 'local' 
        
        # Lista IDs/Volids já cadastrados para evitar duplicatas
        existing_volids = [str(t.proxmox_template_volid) for t in ServiceTemplate.query.all()]
        candidates = []

        # --- 1. SCAN DE ARQUIVOS (Storage) ---
        try:
            contents = proxmox_client.connection.nodes(node).storage(target_storage).content.get()
            for item in contents:
                volid = str(item.get('volid'))
                content_type = item.get('content') 
                size_bytes = int(item.get('size', 0))
                size_gb = math.ceil(size_bytes / (1024**3))
                if size_gb < 1: size_gb = 1

                if content_type in ['vztmpl', 'iso'] and volid not in existing_volids:
                    candidates.append({
                        'volid': volid,
                        'name': volid.split('/')[-1].replace('.iso', '').replace('.tar.zst', ''),
                        'type': 'lxc' if content_type == 'vztmpl' else 'qemu', # Se ISO, sugere QEMU
                        'detected_size_gb': size_gb,
                        'origin': 'file' # Flag para definir deploy_mode depois
                    })
        except Exception as e:
            print(f"Aviso Scan Storage: {e}")

        # --- 2. SCAN DE VMS QEMU (Template=1) ---
        try:
            qemu_list = proxmox_client.connection.nodes(node).qemu.get()
            for vm in qemu_list:
                is_template = vm.get('template') == 1
                vmid = str(vm.get('vmid'))
                
                if is_template and vmid not in existing_volids:
                    size_bytes = int(vm.get('maxdisk', 0))
                    size_gb = math.ceil(size_bytes / (1024**3))
                    
                    candidates.append({
                        'volid': vmid,
                        'name': vm.get('name', f'VM-Template-{vmid}'),
                        'type': 'qemu',
                        'detected_size_gb': size_gb,
                        'origin': 'vm' # Indica Clone
                    })
        except Exception as e:
            print(f"Aviso Scan QEMU: {e}")

        # --- 3. SCAN DE LXC CONTAINERS (Template=1) [NOVO] ---
        try:
            lxc_list = proxmox_client.connection.nodes(node).lxc.get()
            for ct in lxc_list:
                is_template = ct.get('template') == 1
                vmid = str(ct.get('vmid'))

                if is_template and vmid not in existing_volids:
                    size_bytes = int(ct.get('maxdisk', 0))
                    size_gb = math.ceil(size_bytes / (1024**3))

                    candidates.append({
                        'volid': vmid,
                        'name': ct.get('name', f'LXC-Template-{vmid}'),
                        'type': 'lxc', # Tipo correto
                        'detected_size_gb': size_gb,
                        'origin': 'vm' # Indica Clone (tratamos CT como VM para lógica de ID)
                    })
        except Exception as e:
             print(f"Aviso Scan LXC: {e}")
        
        return jsonify(candidates)

    except Exception as e:
        print(f"Erro Crítico Scan: {e}")
        return jsonify({'error': str(e)}), 500

@bp.route('/templates/import', methods=['POST', 'OPTIONS'])
@cross_origin()
@jwt_required()
def import_selected_templates():
    """
    Importa templates selecionados para o catálogo.
    ---
    tags:
      - Admin Templates
    security:
      - Bearer: []
    parameters:
      - name: body
        in: body
        required: true
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
                  origin:
                    type: string
                  detected_size_gb:
                    type: integer
    responses:
      200:
        description: Templates importados com sucesso.
    """
    if not check_admin_permission(): return jsonify({"error": "Acesso negado."}), 403

    data = request.get_json()
    selected_items = data.get('templates', []) 
    
    added_count = 0
    for item in selected_items:
        exists = ServiceTemplate.query.filter_by(proxmox_template_volid=item['volid']).first()
        if not exists:
            # Lógica inteligente para definir o modo
            # Se origin for 'vm' (IDs numéricos de VM ou CT), usamos CLONE.
            # Se origin for 'file' (caminho de storage), usamos FILE.
            origin = item.get('origin', 'file')
            deploy_mode = 'clone' if origin == 'vm' else 'file'

            new_tmpl = ServiceTemplate(
                name=item['name'],
                proxmox_template_volid=item['volid'],
                type=item['type'],
                deploy_mode=deploy_mode,
                category='os',
                is_active=False,
                default_cpu=1,
                default_memory=512,
                default_storage=item.get('detected_size_gb', 5)
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
    Alterna o status Ativo/Inativo de um template.
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
    responses:
      200:
        description: Status alterado com sucesso.
    """
    if not check_admin_permission(): return jsonify({"error": "Acesso negado."}), 403

    tmpl = ServiceTemplate.query.get_or_404(id)
    tmpl.is_active = not tmpl.is_active
    db.session.commit()
    
    return jsonify({
        'success': True, 
        'is_active': tmpl.is_active,
        'message': f'Template {"ativado" if tmpl.is_active else "desativado"}.'
    })

# ==============================================================================
# ROTA UNIFICADA: UPDATE (PUT) E DELETE (DELETE)
# ==============================================================================
@bp.route('/templates/<int:id>', methods=['PUT', 'DELETE', 'OPTIONS'])
@cross_origin()
@jwt_required()
def manage_single_template(id):
    """
    Gerencia um template específico (Atualização ou Remoção).
    ---
    tags:
        - Admin Templates
    put:
      summary: Atualiza configurações do template
      description: Atualiza nome, categoria, specs. Se for Clone, tenta sincronizar com Proxmox.
      
      security:
        - Bearer: []
      parameters:
        - name: id
          in: path
          type: integer
          required: true
          description: ID do Template no Banco de Dados
        - name: body
          in: body
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
      responses:
        200:
          description: Template atualizado.
    
    delete:
      summary: Remove o template do catálogo
      description: Apaga o registo local. O recurso no Proxmox NÃO é afetado.
      tags:
        - Admin Templates
      security:
        - Bearer: []
      parameters:
        - name: id
          in: path
          type: integer
          required: true
          description: ID do Template
      responses:
        200:
          description: Template removido.
        409:
          description: "Impossível remover (está em uso)."
    """
    if not check_admin_permission(): return jsonify({"error": "Acesso negado."}), 403

    tmpl = ServiceTemplate.query.get_or_404(id)

    # --- DELETE: REMOVER TEMPLATE ---
    if request.method == 'DELETE':
        try:
            db.session.delete(tmpl)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Template removido do catálogo.'})
        except Exception as e:
            db.session.rollback()
            if "foreign key" in str(e).lower():
                return jsonify({'error': 'Não é possível remover: Existem instâncias usando este template.'}), 409
            return jsonify({'error': str(e)}), 500

    # --- PUT: ATUALIZAR TEMPLATE ---
    if request.method == 'PUT':
        data = request.get_json()

        if 'name' in data: tmpl.name = data['name']
        if 'category' in data: tmpl.category = data['category']
        
        # Atualização de metadados simples
        if 'is_active' in data: tmpl.is_active = data['is_active']
        if 'description' in data: tmpl.description = data['description']

        # Atualização de Hardware
        # Se for Clone, o Backend tenta re-inspecionar a verdade no PVE
        if getattr(tmpl, 'deploy_mode', 'file') == 'clone':
             try:
                # Re-inspeciona se o volid for numérico
                if str(tmpl.proxmox_template_volid).isdigit():
                    real = proxmox_client.inspect_resource(int(tmpl.proxmox_template_volid), tmpl.type)
                    tmpl.default_cpu = real['cpu']
                    tmpl.default_memory = real['memory']
                    tmpl.default_storage = real['storage']
             except:
                 pass # Se falhar a inspeção, mantém valores antigos
        else:
            # Modo File: Aceita input manual
            if 'default_cpu' in data: tmpl.default_cpu = int(data['default_cpu'])
            if 'default_memory' in data: tmpl.default_memory = int(data['default_memory'])
            if 'default_storage' in data: 
                new_storage = int(data['default_storage'])
                if new_storage >= tmpl.default_storage:
                    tmpl.default_storage = new_storage

        db.session.commit()
        return jsonify({'success': True, 'message': 'Template atualizado.', 'data': tmpl.to_dict()})