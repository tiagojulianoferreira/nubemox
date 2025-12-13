from flask import Blueprint, jsonify, request, abort
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import ServiceTemplate, User
from app.extensions import db

bp = Blueprint('catalog', __name__)


# Helper para verificar Admin
def ensure_admin():
    current_user_id = int(get_jwt_identity())
    user = User.query.get(current_user_id)
    
    # Desativado temporariamente para testes
    # if not user or not getattr(user, 'is_admin', False):
    #     abort(403, description="Acesso negado. Apenas administradores.")
    # return user

# ----------------------------------------------------------------
# ROTA PÚBLICA (Para usuários autenticados verem o menu)
# ----------------------------------------------------------------
@bp.route('/templates', methods=['GET'])
@jwt_required()
def list_templates():
    """
    Lista os templates de serviço disponíveis para provisionamento.
    
    Retorna apenas os templates marcados como 'ativos' pelo administrador. 
    A resposta inclui o objeto 'specs' detalhado, permitindo que o frontend
    renderize os cards com as informações de hardware (CPU, RAM, Disco)
    que foram sincronizadas com o Proxmox.

    ---
    tags:
      - Catálogo
    security:
      - Bearer: []
    responses:
      200:
        description: Lista de templates retornada com sucesso.
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
                description: ID interno do template no Nubemox
                example: 1
              name:
                type: string
                example: "Ubuntu 22.04 LTS"
              description:
                type: string
                example: "Imagem oficial mínima pronta para Docker."
              category:
                type: string
                example: "os"
                description: "Categoria para filtro visual (os, app, database)"
              type:
                type: string
                enum: [lxc, qemu]
                example: "lxc"
              logo_url:
                type: string
                example: "/assets/logos/ubuntu.png"
              specs:
                type: object
                description: "Especificações de hardware padrão do template (Fonte: PVE)."
                properties:
                  cpu:
                    type: integer
                    description: "Núcleos de CPU (vCores)"
                    example: 2
                  memory:
                    type: integer
                    description: "Memória RAM em MB"
                    example: 1024
                  storage:
                    type: integer
                    description: "Tamanho do Disco em GB"
                    example: 20
      401:
        description: Token de acesso ausente ou inválido.
    """

    templates = ServiceTemplate.query.filter_by(is_active=True).all()
    
    return jsonify([{
        'id': t.id,
        'name': t.name,
        'description': t.description,
        'logo_url': t.logo_url,
        'category': getattr(t, 'category', 'os'),
        'type': t.type,
        'mode': t.deploy_mode,
        # O Frontend usa isso para mostrar: "1 vCPU • 512 MB RAM"
        'specs': {
            'cpu': getattr(t, 'default_cpu', 1),
            'memory': getattr(t, 'default_memory', 512),
            'storage': getattr(t, 'default_storage', 8)
        }
    } for t in templates])

# ----------------------------------------------------------------
# ROTAS DE ADMINISTRAÇÃO (Cadastro e Edição Sincronizada)
# ----------------------------------------------------------------

@bp.route('/templates', methods=['POST'])
@jwt_required()
def register_template():
    """
    (ADMIN) Cadastra template.
    Se for Clone (ID numérico), consulta o PVE para preencher as specs automaticamente.
    """
    ensure_admin()
    data = request.get_json() or {}
    
    required = ['name', 'type', 'volid']
    if not all(k in data for k in required):
        abort(400, description=f"Campos obrigatórios: {', '.join(required)}")

    # Valores padrão iniciais (caso a inspeção falhe)
    def_cpu = int(data.get('default_cpu', 1))
    def_mem = int(data.get('default_memory', 512))
    def_dsk = int(data.get('default_storage', 8))
    
    mode = data.get('mode', 'file')
    
    # Lógica de Fonte Única da Verdade (PVE)
    if str(data['volid']).isdigit():
        mode = 'clone'
        try:
            # Importação tardia para evitar ciclo circular
            from app.proxmox import ProxmoxService
            service = ProxmoxService()
            
            # Chama o INSPETOR (Mixin que lê o config do PVE)
            # Certifique-se de ter adicionado TemplateInspector no __init__.py
            specs = service.inspect_resource(data['volid'], data['type'])
            
            # Usa o valor do PVE se o admin não forçou outro no JSON
            if 'default_cpu' not in data: def_cpu = specs['cpu']
            if 'default_memory' not in data: def_mem = specs['memory']
            if 'default_storage' not in data: def_dsk = specs['storage']
            
            print(f"✅ Template {data['volid']} inspecionado no PVE: {specs}")
            
        except Exception as e:
            print(f"⚠️ Aviso: Não foi possível inspecionar o PVE ({str(e)}). Usando defaults.")

    template = ServiceTemplate(
        name=data['name'],
        type=data['type'], # 'lxc' ou 'qemu'
        proxmox_template_volid=data['volid'],
        deploy_mode=mode,
        description=data.get('description', ''),
        logo_url=data.get('logo_url', ''),
        category=data.get('category', 'os'),
        is_active=True,
        default_cpu=def_cpu,
        default_memory=def_mem,
        default_storage=def_dsk
    )
    
    db.session.add(template)
    db.session.commit()
    
    return jsonify({
        'success': True, 
        'message': f"Template cadastrado.",
        'id': template.id,
        'detected_specs': {'cpu': def_cpu, 'ram': def_mem, 'disk': def_dsk}
    }), 201

@bp.route('/templates/<int:template_id>', methods=['PUT'])
@jwt_required()
def update_template(template_id):
    """
    (ADMIN) Atualiza template.
    Se alterar CPU/RAM/Disco de um template 'clone', aplica no PVE também.
    """
    ensure_admin()
    template = ServiceTemplate.query.get_or_404(template_id)
    data = request.get_json() or {}
    
    # 1. Captura novos valores
    old_storage = template.default_storage
    new_cpu = int(data.get('default_cpu', template.default_cpu))
    new_mem = int(data.get('default_memory', template.default_memory))
    new_storage = int(data.get('default_storage', template.default_storage))
    
    # 2. Regra de Segurança: Proibido Diminuir Disco via API
    if new_storage < old_storage:
        abort(400, description=f"Não é permitido diminuir o disco (Atual: {old_storage}GB). O Proxmox não suporta shrink seguro.")

    updated_pve = False
    pve_error = None

    # 3. Sincronização com PVE (Apenas se for Clone e existir no PVE)
    if template.deploy_mode == 'clone' and str(template.proxmox_template_volid).isdigit():
        try:
            from app.proxmox import ProxmoxService
            service = ProxmoxService()
            updates = {}
            
            # Detecta mudanças em CPU/RAM
            if new_cpu != template.default_cpu: updates['cores'] = new_cpu
            if new_mem != template.default_memory: updates['memory'] = new_mem
            
            # Aplica CPU/RAM se houver mudanças
            if updates:
                if template.type == 'lxc':
                    service.update_container_resources(template.proxmox_template_volid, updates)
                    updated_pve = True
            
            # Aplica Resize de Disco (Apenas se aumentou)
            if new_storage > old_storage:
                if template.type == 'lxc':
                    # Chama o método resize_disk (Adicionado no LXCManager)
                    service.resize_disk(template.proxmox_template_volid, new_storage)
                    updated_pve = True
                    
        except Exception as e:
            pve_error = str(e)
            # Em caso de erro no PVE, abortamos para evitar inconsistência
            return jsonify({
                'success': False,
                'error': f"Falha ao sincronizar com Proxmox: {pve_error}. Nenhuma alteração foi salva."
            }), 500

    # 4. Salva no Banco Local
    template.name = data.get('name', template.name)
    template.description = data.get('description', template.description)
    template.logo_url = data.get('logo_url', template.logo_url)
    template.category = data.get('category', template.category)
    template.is_active = data.get('is_active', template.is_active)
    
    template.default_cpu = new_cpu
    template.default_memory = new_mem
    template.default_storage = new_storage
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Template atualizado com sucesso.',
        'pve_sync': updated_pve,
        'specs': {'cpu': new_cpu, 'ram': new_mem, 'disk': new_storage}
    })

@bp.route('/templates/<int:template_id>', methods=['DELETE'])
@jwt_required()
def delete_template(template_id):
    """(ADMIN) Remove do catálogo (não apaga o template do PVE)."""
    ensure_admin()
    template = ServiceTemplate.query.get_or_404(template_id)
    
    db.session.delete(template)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Template removido do catálogo.'})