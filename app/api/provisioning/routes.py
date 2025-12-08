from flask import Blueprint, jsonify, request, abort
from app.models import ServiceTemplate
# Importando o Serviço Unificado da nova arquitetura
from app.proxmox import ProxmoxService 
from app.extensions import db

bp = Blueprint('provisioning', __name__)

def get_service():
    return ProxmoxService()

@bp.route('/deploy', methods=['POST'])
def deploy_resource():
    """
    Provisiona um novo recurso (Deploy Inteligente).
    Identifica a estratégia (File vs Clone) e garante que o Pool do usuário exista.
    ---
    tags:
      - Provisionamento (Usuário)
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - template_id
            - name
            - username
          properties:
            template_id:
              type: integer
              description: ID do template no catálogo Nubemox
            name:
              type: string
              description: Nome da máquina a ser criada
            username:
              type: string
              description: Nome do usuário dono (usado para criar o Pool vps-nome)
              example: "tiago"
    responses:
      201:
        description: Recurso criado com sucesso
        schema:
          type: object
          properties:
            success:
              type: boolean
            vmid:
              type: integer
            pool:
              type: string
            message:
              type: string
      400:
        description: Erro de validação
      500:
        description: Erro no Proxmox
    """
    data = request.get_json() or {}
    
    template_id = data.get('template_id')
    name = data.get('name')
    username = data.get('username') # <--- Recebe o usuário dono
    
    # Validação de entrada
    if not template_id or not name or not username:
        abort(400, description="template_id, name e username são obrigatórios.")
        
    template = ServiceTemplate.query.get_or_404(template_id)
    service = get_service()
    
    try:
        # 1. AUTOMAÇÃO DE POOL DINÂMICA
        # Chama o método que criamos no PoolManager para garantir 'vps-username'
        target_pool = service.ensure_user_pool(username)
        
        new_id = None
        
        # 2. ESTRATÉGIA: CLONE (CT/VM Existente)
        if template.deploy_mode == 'clone':
            # Gera o ID antes para passar ao comando de clone
            new_id = service.get_next_vmid()
            
            # Executa a clonagem (Hardware é herdado da origem)
            service.clone_container(
                source_vmid=template.proxmox_template_volid,
                new_vmid=new_id,
                name=name,
                poolid=target_pool,
                full_clone=True
            )

        # 3. ESTRATÉGIA: FILE (ISO/Template ZST)
        elif template.deploy_mode == 'file':
            # Usa hardware padrão mínimo do sistema para 'bootstrapping'
            config = {
                'name': name,
                'template': template.proxmox_template_volid,
                'poolid': target_pool,
                'cores': 1,
                'memory': 512,
                'disk_size': 8,
                'storage': 'local-lvm'
            }
            result = service.create_container(config)
            new_id = result.get('ctid')

        else:
            abort(400, description="Modo de deploy inválido configurado no template.")

        # 4. Retorno de Sucesso
        return jsonify({
            'success': True,
            'message': f"Recurso {name} ({new_id}) criado via {template.deploy_mode}.",
            'vmid': new_id,
            'pool': target_pool
        }), 201

    except Exception as e:
        # Repassa o erro para o handler global (que devolve JSON 500)
        raise e

@bp.route('/resources/<int:vmid>/scale', methods=['PUT'])
def scale_resource(vmid):
    """
    Escala verticalmente um recurso (Elasticidade).
    Permite aumentar ou diminuir CPU e RAM.
    ---
    tags:
      - Provisionamento (Usuário)
    parameters:
      - name: vmid
        in: path
        type: integer
        required: true
        description: ID do recurso (VMID)
      - in: body
        name: body
        schema:
          type: object
          properties:
            memory:
              type: integer
              description: Nova quantidade de RAM em MB
              example: 2048
            cores:
              type: integer
              description: Novo número de vCPUs
              example: 2
    responses:
      200:
        description: Recursos atualizados com sucesso
    """
    data = request.get_json() or {}
    service = get_service()
    
    updates = {}
    if 'memory' in data:
        updates['memory'] = int(data['memory'])

    if 'cores' in data:
        updates['cores'] = int(data['cores'])
        
    if not updates:
        abort(400, description="Nenhum parâmetro de escala enviado (memory ou cores).")

    try:
        # Nota: Por enquanto assume CT. 
        # Num sistema completo, verificaríamos o tipo no DB antes de chamar.
        result = service.update_container_resources(vmid, updates)
        
        return jsonify(result)
        
    except Exception as e:
        abort(500, description=f"Falha ao escalar recurso {vmid}: {str(e)}")