from flask import Blueprint, jsonify, request, abort
from app.models import ServiceTemplate
from app.extensions import db

bp = Blueprint('catalog', __name__)

@bp.route('/templates', methods=['GET'])
def list_templates():
    """
    Lista templates disponíveis para o usuário.
    Retorna apenas templates marcados como ativos.
    ---
    tags:
      - Catálogo
    responses:
      200:
        description: Lista de templates
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
              name:
                type: string
              mode:
                type: string
                description: "file ou clone"
    """
    templates = ServiceTemplate.query.filter_by(is_active=True).all()
    return jsonify([t.to_dict() for t in templates])

@bp.route('/templates', methods=['POST'])
def register_template():
    """
    (Admin) Cadastra um novo template no catálogo.
    Define se será criado via arquivo (ISO/ZST) ou clonagem.
    ---
    tags:
      - Catálogo
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - name
            - type
            - volid
          properties:
            name:
              type: string
              example: "Ubuntu 22.04"
            type:
              type: string
              enum: [lxc, qemu]
            volid:
              type: string
              description: "ID (9000) ou Caminho (local:vztmpl/xxx)"
            mode:
              type: string
              enum: [file, clone]
              description: "Opcional. Se volid for número, assume clone."
            description:
              type: string
            logo_url:
              type: string
    responses:
      201:
        description: Template cadastrado
    """
    data = request.get_json() or {}
    
    if not all(k in data for k in ['name', 'type', 'volid']):
        abort(400, description="Campos obrigatórios: name, type, volid")

    # Detecção automática de modo
    mode = data.get('mode', 'file')
    if str(data['volid']).isdigit():
        mode = 'clone'

    template = ServiceTemplate(
        name=data['name'],
        type=data['type'],
        proxmox_template_volid=data['volid'],
        deploy_mode=mode,
        description=data.get('description'),
        logo_url=data.get('logo_url')
    )
    
    db.session.add(template)
    db.session.commit()
    
    return jsonify(template.to_dict()), 201