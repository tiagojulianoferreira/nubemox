from flask import Blueprint, jsonify, request, abort, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import ServiceTemplate, VirtualResource, User
from app.proxmox import ProxmoxService 
from app.extensions import db
from utils.utils import check_user_quota
import re

bp = Blueprint('provisioning', __name__)

def get_service():
    return ProxmoxService()

@bp.route('/deploy', methods=['POST'])
@jwt_required()
def deploy_resource():
    """
    Provisiona um novo recurso para o usuário autenticado.
    Identifica o usuário pelo Token, garante seu Pool e Permissões no Proxmox e cria o recurso.

    O Nubemox implementa uma estratégia de espelhamento de usuários no Proxmox ("Shadow Users") para garantir robustez e segurança. Esta abordagem justifica-se por três pilares fundamentais:

    Segurança do Console (VNC): Permite a geração de tickets de autenticação VNC vinculados estritamente ao usuário e à VM. Isso elimina a necessidade de gerar tickets com privilégios de root, mitigando o risco crítico de escalada de privilégios via navegador.

    Continuidade de Negócio (Disaster Recovery): Garante redundância de acesso. Na eventualidade de indisponibilidade da API/Frontend do Nubemox, os usuários podem autenticar-se diretamente na interface nativa do Proxmox (via Realm LDAP) e gerir os seus recursos, uma vez que as permissões (ACLs) estão nativamente sincronizadas.

    Auditoria e Rastreabilidade: Assegura que a propriedade dos recursos seja visível diretamente no cluster. Administradores podem identificar o "dono" de cada carga de trabalho e auditar ações nos logs do Proxmox sem necessitar de consultas cruzadas ao banco de dados da aplicação.
    ---
    tags:
      - Provisionamento (Autenticado)
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - template_id
            - name
          properties:
            template_id:
              type: integer
              description: ID do template no catálogo Nubemox
            name:
              type: string
              description: Nome da máquina a ser criada
    responses:
      201:
        description: Recurso criado com sucesso
      400:
        description: Erro de validação
      401:
        description: Token inválido
      500:
        description: Erro no Proxmox
    """
    # 1. RECUPERAR USUÁRIO AUTENTICADO
    # O ID vem como string do token, convertemos para int para o DB
    current_user_id = int(get_jwt_identity())
    user = User.query.get(current_user_id)
    
    if not user:
        abort(401, description="Usuário do token não encontrado no banco de dados.")

    # --- REFINAMENTO 1: Validação de Nome (Sanitização) ---
    # Só permite letras, números e hífens. Evita injeção de comandos no shell do Proxmox.
    if not re.match(r'^[a-zA-Z0-9-]+$', name):
        abort(400, description="Nome inválido. Use apenas letras, números e hífens.")

    # --- REFINAMENTO 2: Verificação de Cota ---
    # Estimativa de custo (Para MVP, assumimos valores fixos ou baseados no Template)
    # Futuro: Ler estes valores do ServiceTemplate no banco
    cost_cpu = 1 
    cost_ram = 512
    cost_disk = 8
    
    can_create, reason = check_user_quota(user, cost_cpu, cost_ram, cost_disk)
    if not can_create:
        abort(403, description=f"Deploy bloqueado: {reason}")

    # 2. VALIDAR ENTRADA
    data = request.get_json() or {}
    template_id = data.get('template_id')
    name = data.get('name')
    
    if not template_id or not name:
        abort(400, description="template_id e name são obrigatórios.")
        
    template = ServiceTemplate.query.get_or_404(template_id)
    service = get_service()
    
    try:
        # --- ORQUESTRAÇÃO DE AMBIENTE DO USUÁRIO ---
        
        # A. Garante Pool (ex: vps-tiago)
        target_pool = service.ensure_user_pool(user.username)
        
        # B. Garante Usuário no Proxmox (ex: tiago@pve-ldap)
        # Pega o Realm do config (pve-ldap-mock ou pam)
        realm = current_app.config.get('PROXMOX_AUTH_REALM', 'pam')
        pve_userid = service.ensure_pve_user(user.username, realm)
        
        # C. Garante Permissão (ACL)
        # O usuário ganha permissão 'PVEVMUser' apenas sobre o seu pool
        service.set_pool_permission(target_pool, pve_userid, role='PVEVMUser')
        
        # -------------------------------------------
        
        new_id = None
        resource_type = template.type # 'lxc' ou 'qemu'
        
        # 3. ESTRATÉGIA: CLONE
        if template.deploy_mode == 'clone':
            new_id = service.get_next_vmid()
            
            # Executa clonagem (assume Container para o MVP)
            if resource_type == 'lxc':
                service.clone_container(
                    source_vmid=template.proxmox_template_volid,
                    new_vmid=new_id,
                    name=name,
                    poolid=target_pool,
                    full_clone=True
                )
            # Futuro: Implementar clone_vm para qemu

        # 4. ESTRATÉGIA: FILE (ISO/Template)
        elif template.deploy_mode == 'file':
            # Configuração mínima padrão
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

        # 5. PERSISTÊNCIA NO BANCO LOCAL
        resource = VirtualResource(
            proxmox_vmid=new_id,
            name=name,
            type=resource_type,
            template_id=template.id,
            owner_id=user.id,
            cpu_cores=1,
            memory_mb=512,
            storage_gb=8
        )
        db.session.add(resource)
        db.session.commit()


        return jsonify({
            'success': True,
            'message': f"Recurso {name} ({new_id}) criado no pool {target_pool}.",
            'vmid': new_id,
            'pool': target_pool,
            'owner': user.username,
            'pve_user': pve_userid
        }), 201

    except Exception as e:
        # 1. Desfaz qualquer mudança pendente no banco local
        db.session.rollback()
        
        # 2. LOGICA ANTI-ZUMBI (A Melhoria)
        # Se new_id existe, significa que o Proxmox criou a máquina, 
        # mas o Nubemox falhou em registrá-la. Devemos apagar no Proxmox.
        if new_id:
            print(f"Erro de persistência. Iniciando limpeza da VM órfã {new_id}...")
            try:
                # Tenta parar e deletar para não deixar lixo no cluster
                if resource_type == 'lxc':
                    # O try/except interno garante que o erro original (e) 
                    # não seja mascarado se a limpeza falhar
                    try: 
                        service.stop_container(new_id)
                    except: 
                        pass # Ignora se já estiver parado
                    
                    service.delete_container(new_id)
                    
                # elif resource_type == 'qemu': ... (mesma lógica para VM)
                
                print(f"VM órfã {new_id} removida com sucesso.")
                
            except Exception as cleanup_error:
                # Se falhar aqui, é grave: temos um recurso consumindo RAM/Disk 
                # que o Nubemox desconhece. Idealmente, alertaria um admin (Slack/Email).
                print(f"FALHA CRÍTICA: Não foi possível limpar VM {new_id}. Erro: {cleanup_error}")
        
        # 3. Relança o erro original para o usuário saber que o deploy falhou
        raise e

@bp.route('/resources/<int:vmid>/scale', methods=['PUT'])
@jwt_required()
def scale_resource(vmid):
    """
    Escala verticalmente um recurso.
    ---
    tags:
      - Provisionamento (Autenticado)
    security:
      - Bearer: []
    parameters:
      - name: vmid
        in: path
        type: integer
        required: true
      - in: body
        name: body
        schema:
          type: object
          properties:
            memory:
              type: integer
            cores:
              type: integer
    """
    # 1. Verificação de Propriedade
    current_user_id = int(get_jwt_identity())
    resource = VirtualResource.query.filter_by(proxmox_vmid=vmid).first()
    
    if not resource:
        # Se não achou no banco, pode ser um recurso legado ou erro de sync.
        # Por segurança, apenas admin deveria mexer em recursos sem dono conhecido.
        pass 
    
    if resource and resource.owner_id != current_user_id:
        user = User.query.get(current_user_id)
        if not user.is_admin:
            abort(403, description="Você não tem permissão para alterar este recurso.")

    # 2. Execução
    data = request.get_json() or {}
    service = get_service()
    
    updates = {}
    if 'memory' in data: updates['memory'] = int(data['memory'])
    if 'cores' in data: updates['cores'] = int(data['cores'])
        
    if not updates:
        abort(400, description="Nenhum parâmetro enviado.")

    try:
        result = service.update_container_resources(vmid, updates)
        
        # Atualiza cache local
        if resource:
            if 'memory' in updates: resource.memory_mb = updates['memory']
            if 'cores' in updates: resource.cpu_cores = updates['cores']
            db.session.commit()
            
        return jsonify(result)
        
    except Exception as e:
        abort(500, description=f"Falha ao escalar: {str(e)}")
@bp.route('/resources/<int:vmid>', methods=['DELETE'])
@jwt_required()
def destroy_resource(vmid):
    """
    Exclui um recurso (Decommissioning).
    Para a máquina, remove do Proxmox e limpa do banco de dados.

    
    Stop: O Nubemox enviou comando de shutdown para o CT no Proxmox.

    Purge: O Nubemox enviou comando de destroy para o CT.

    Clean: O Nubemox apagou a linha correspondente na tabela virtual_resources do banco local.

    Audit: Se tentar listar os recursos desse usuário agora, essa VM já não aparecerá.

    ---
    tags:
      - Provisionamento (Autenticado)
    security:
      - Bearer: []
    parameters:
      - name: vmid
        in: path
        type: integer
        required: true
        description: ID do recurso a ser destruído
    responses:
      200:
        description: Recurso destruído
      403:
        description: Tentativa de apagar recurso de outro usuário
    """
    # 1. Busca no Banco Local
    current_user_id = int(get_jwt_identity())
    resource = VirtualResource.query.filter_by(proxmox_vmid=vmid).first_or_404()
    
    # 2. Segurança: Verifica se o usuário é o dono ou é Admin
    # (Assumindo que User tem campo is_admin, senão remova a parte do 'or')
    user = User.query.get(current_user_id)
    if resource.owner_id != current_user_id and not getattr(user, 'is_admin', False):
         abort(403, description="Você não tem permissão para excluir este recurso.")

    service = get_service()
    
    try:
        # 3. Execução Técnica (Usa o seu lxc.py)
        
        # A. Stop Forçado (Safety First)
        # O Proxmox não deixa deletar se estiver rodando ("locked").
        # Tentamos parar, ignorando erro se já estiver parado.
        try:
            if resource.type == 'lxc':
                service.stop_container(vmid)
            # elif resource.type == 'qemu': service.stop_vm(vmid)
        except Exception:
            pass # Segue o baile se já estiver parado ou der timeout
        
        # B. Purge no Proxmox (Chama o método que adicionamos acima)
        if resource.type == 'lxc':
            service.delete_container(vmid)
        # elif resource.type == 'qemu': service.delete_vm(vmid)
        
        # 4. Limpeza no Banco de Dados
        db.session.delete(resource)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Recurso {resource.name} ({vmid}) foi destruído completamente.'
        })
        
    except Exception as e:
        db.session.rollback()
        # Se deu erro no Proxmox (ex: VM não existe), 
        # talvez devêssemos forçar a limpeza do banco? 
        # Por enquanto, retornamos erro 500.
        return jsonify({'success': False, 'error': str(e)}), 500
    # ----------------------------------------------------------------
# --- ROTAS DE SNAPSHOTS ---
# ----------------------------------------------------------------

def get_resource_or_404(vmid, user_id):
    """Helper para buscar recurso e validar dono."""
    resource = VirtualResource.query.filter_by(proxmox_vmid=vmid).first_or_404()
    user = User.query.get(user_id)
    # Admin pode tudo, Dono pode seus recursos
    if resource.owner_id != user_id and not getattr(user, 'is_admin', False):
        abort(403, description="Acesso negado ao recurso.")
    return resource

@bp.route('/resources/<int:vmid>/snapshots', methods=['GET'])
@jwt_required()
def list_snapshots(vmid):
    """Lista snapshots de uma VM."""
    current_user_id = int(get_jwt_identity())
    resource = get_resource_or_404(vmid, current_user_id)
    
    service = get_service()
    try:
        # Passamos o tipo (lxc ou qemu) armazenado no banco
        return jsonify(service.get_snapshots(vmid, resource_type=resource.type))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/resources/<int:vmid>/snapshots', methods=['POST'])
@jwt_required()
def create_snapshot(vmid):
    """Cria um novo snapshot."""
    current_user_id = int(get_jwt_identity())
    resource = get_resource_or_404(vmid, current_user_id)
    
    data = request.get_json() or {}
    snapname = data.get('name')
    if not snapname: abort(400, "Nome do snapshot obrigatório")
    
    service = get_service()
    try:
        result = service.create_snapshot(
            vmid=vmid, 
            snapname=snapname, 
            description=data.get('description'),
            vmstate=True, # Salva RAM se possível
            resource_type=resource.type
        )
        return jsonify(result), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/resources/<int:vmid>/snapshots/<string:snapname>/rollback', methods=['POST'])
@jwt_required()
def rollback_snapshot(vmid, snapname):
    """Restaura a VM para um ponto anterior."""
    current_user_id = int(get_jwt_identity())
    resource = get_resource_or_404(vmid, current_user_id)
    
    service = get_service()
    try:
        # Rollback exige que a VM esteja parada ou reinicia ela.
        # O serviço cuida do comando.
        result = service.rollback_snapshot(vmid, snapname, resource_type=resource.type)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/resources/<int:vmid>/snapshots/<string:snapname>', methods=['DELETE'])
@jwt_required()
def delete_snapshot(vmid, snapname):
    """Apaga um snapshot."""
    current_user_id = int(get_jwt_identity())
    resource = get_resource_or_404(vmid, current_user_id)
    
    service = get_service()
    try:
        result = service.delete_snapshot(vmid, snapname, resource_type=resource.type)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
@bp.route('/resources', methods=['GET'])
@jwt_required()
def list_user_resources():
    """
    Lista todos os recursos (VMs/CTs) do usuário autenticado.
    ---
    tags:
      - Provisionamento (Autenticado)
    responses:
      200:
        description: Lista de recursos
    """
    current_user_id = int(get_jwt_identity())
    
    # Filtra apenas recursos onde owner_id == usuário logado
    resources = VirtualResource.query.filter_by(owner_id=current_user_id).all()
    
    output = []
    for r in resources:
        output.append({
            'id': r.id,
            'vmid': r.proxmox_vmid,
            'name': r.name,
            'type': r.type,
            'status': 'unknown', # Futuro: consultar status real no Proxmox
            'cpu': r.cpu_cores,
            'ram': r.memory_mb,
            'created_at': r.created_at.isoformat() if r.created_at else None
        })
    
    return jsonify(output)