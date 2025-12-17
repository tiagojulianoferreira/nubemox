from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_cors import cross_origin
import re

# Modelos e Banco de Dados
from app.models import ServiceTemplate, VirtualResource, User
from app.extensions import db

# Importamos a instância do Serviço Unificado (Facade)
from app.proxmox import proxmox_client

# Tenta importar utils de forma robusta
try:
    from app.utils import check_user_quota
except ImportError:
    from utils.utils import check_user_quota 

bp = Blueprint('provisioning', __name__)

@bp.route('/deploy', methods=['POST', 'OPTIONS'])
@cross_origin()
@jwt_required()
def deploy_resource():
    """
    Provisiona um novo recurso (Container ou VM).
    ---
    tags:
      - Provisionamento
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
              description: ID do template de serviço
            name:
              type: string
              description: Nome do recurso (hostname)
            cpu:
              type: integer
              description: Opcional - Quantidade de vCPUs
            memory:
              type: integer
              description: Opcional - Memória em MB
            storage:
              type: integer
              description: Opcional - Disco em GB
    responses:
      201:
        description: Recurso criado e iniciado com sucesso
      400:
        description: Dados inválidos ou validação falhou
      403:
        description: Cota excedida
    """
    new_id = None 
    resource_type = 'lxc' 

    try:
        # --- 1. VALIDAÇÕES E DADOS ---
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({"error": "Usuário não encontrado."}), 401

        data = request.get_json() or {}
        template_id = data.get('template_id')
        name = data.get('name') 
        
        if not template_id or not name:
            return jsonify({"error": "Campos obrigatórios ausentes."}), 400

        if not re.match(r'^[a-zA-Z0-9-]+$', name):
             return jsonify({"error": "Nome inválido."}), 400

        template = ServiceTemplate.query.get(template_id)
        if not template: return jsonify({"error": "Template não encontrado."}), 404
        
        req_cpu = int(data.get('cpu', template.default_cpu or 1))
        req_ram = int(data.get('memory', template.default_memory or 512))
        req_storage = int(data.get('storage', template.default_storage or 10))
        
        can_create, reason = check_user_quota(user, req_cpu, req_ram, req_storage)
        if not can_create: return jsonify({"error": reason}), 403

        # --- 2. INFRAESTRUTURA ---
        target_storage = user.group.default_storage_pool if user.group else 'local-lvm'
        target_bridge = user.group.default_network_bridge if user.group else 'vmbr0'
        vlan_tag = user.group.default_vlan_tag if user.group else None
        
        net_config_lxc = f"name=eth0,bridge={target_bridge},ip=dhcp"
        net_config_qemu = f"virtio,bridge={target_bridge}"
        
        if vlan_tag:
            net_config_lxc += f",tag={vlan_tag}"
            net_config_qemu += f",tag={vlan_tag}"

        # --- 3. PREPARAÇÃO ---
        resource_type = template.type
        new_id = proxmox_client.get_next_vmid()
        target_pool = proxmox_client.ensure_user_pool(user.username)
        proxmox_client.ensure_pve_user(user.username)

        template_volid = template.proxmox_template_volid
        is_file_template = not str(template_volid).isdigit()

        # --- 4. DEPLOY TÉCNICO ---
        node = proxmox_client._resolve_node_id()

        if resource_type == 'lxc':
            if template.deploy_mode == 'clone' and not is_file_template:
                # A. CLONE
                proxmox_client.clone_container(
                    source_vmid=template_volid,
                    new_vmid=new_id,
                    name=name,
                    poolid=target_pool,
                    full_clone=True
                )
            elif (template.deploy_mode == 'file') or (is_file_template):
                # B. CREATE FILE
                config = {
                    'vmid': new_id,
                    'template': template_volid,
                    'name': name,
                    'memory': req_ram,
                    'cores': req_cpu,
                    'storage': target_storage,  
                    'net0': net_config_lxc,     
                    'poolid': target_pool,
                    'password': 'ChangeMe123!',
                    'onboot': 1  # Define Start on Boot
                }
                proxmox_client.create_container(config)
            else:
                 return jsonify({"error": "Modo inválido."}), 400

            # --- PÓS-DEPLOY LXC ---
            try:
                # 1. Garante persistência da config de boot
                proxmox_client.connection.nodes(node).lxc(new_id).config.put(onboot=1)
                # 2. Inicia imediatamente
                proxmox_client.start_container(new_id)
            except Exception as e:
                current_app.logger.warning(f"Container criado, mas falha ao iniciar: {e}")

        elif resource_type == 'qemu':
            proxmox_client.create_vm({
                'vmid': new_id,
                'name': name,
                'cores': req_cpu,
                'memory': req_ram,
                'storage': target_storage,  
                'net0': net_config_qemu,    
                'poolid': target_pool
            })
            # Pós-deploy VM
            try:
                proxmox_client.connection.nodes(node).qemu(new_id).config.put(onboot=1)
                if hasattr(proxmox_client, 'start_vm'):
                    proxmox_client.start_vm(new_id)
            except Exception:
                pass

        # --- 5. PERSISTÊNCIA ---
        final_status = 'stopped'
        try:
            if resource_type == 'lxc':
                status_data = proxmox_client.get_container_status(new_id)
                final_status = status_data['data'].get('status', 'stopped')
        except:
            pass

        resource = VirtualResource(
            proxmox_vmid=new_id,
            name=name,
            type=resource_type,
            template_id=template.id,
            owner_id=user.id,
            cpu_cores=req_cpu,
            memory_mb=req_ram,
            storage_gb=req_storage,
            status=final_status 
        )
        db.session.add(resource)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f"Recurso criado e iniciado.",
            'vmid': new_id,
            'status': final_status
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erro Deploy: {e}")
        if new_id:
            try:
                if resource_type == 'lxc': proxmox_client.delete_container(new_id)
            except: pass
        return jsonify({'error': str(e)}), 500
    
@bp.route('/resources/<int:vmid>/scale', methods=['PUT', 'OPTIONS'])
@cross_origin()
@jwt_required()
def scale_resource(vmid):
    """
    Escala verticalmente o recurso (CPU e RAM).
    ---
    tags:
      - Gerenciamento de Recursos
    security:
      - Bearer: []
    parameters:
      - in: path
        name: vmid
        type: integer
        required: true
        description: ID da VM/Container no Proxmox
      - in: body
        name: body
        schema:
          type: object
          properties:
            memory:
              type: integer
            cores:
              type: integer
    responses:
      200:
        description: Recursos atualizados com sucesso
      403:
        description: Cota excedida
    """
    current_user_id = int(get_jwt_identity())
    user = User.query.get(current_user_id)
    resource = VirtualResource.query.filter_by(proxmox_vmid=vmid).first_or_404()
    
    if resource.owner_id != current_user_id and not getattr(user, 'is_admin', False):
        return jsonify({"error": "Acesso negado."}), 403

    data = request.get_json() or {}
    new_ram = int(data.get('memory', resource.memory_mb))
    new_cpu = int(data.get('cores', resource.cpu_cores))
    
    # Check Quota
    quota_data = getattr(user, 'quota', None)
    if quota_data and 'limit' in quota_data:
        limits = quota_data['limit']
        max_ram = limits.get('memory', 0)
        max_cpu = limits.get('cpu', 0)
        
        all_resources = VirtualResource.query.filter_by(owner_id=user.id).all()
        other_ram = sum(r.memory_mb for r in all_resources if r.id != resource.id)
        other_cpu = sum(r.cpu_cores for r in all_resources if r.id != resource.id)
        
        if (other_ram + new_ram) > max_ram:
             available = max_ram - other_ram
             return jsonify({"error": f"Cota de RAM excedida. Disponível: {available}MB"}), 403
        
        if (other_cpu + new_cpu) > max_cpu:
             available = max_cpu - other_cpu
             return jsonify({"error": f"Cota de vCPUs excedida. Disponível: {available}"}), 403

    try:
        if resource.type == 'lxc':
            if hasattr(proxmox_client, 'update_container_resources'):
                proxmox_client.update_container_resources(vmid, {'memory': new_ram, 'cores': new_cpu})
            else:
                node = proxmox_client._resolve_node_id()
                proxmox_client.connection.nodes(node).lxc(vmid).config.put(
                    memory=new_ram, 
                    cores=new_cpu
                )
        
        resource.memory_mb = new_ram
        resource.cpu_cores = new_cpu
        db.session.commit()
        
        return jsonify({'success': True, 'new_specs': {'ram': new_ram, 'cpu': new_cpu}})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/resources/<int:vmid>', methods=['DELETE', 'OPTIONS'])
@cross_origin()
@jwt_required()
def destroy_resource(vmid):
    """
    Destrói permanentemente o recurso.
    ---
    tags:
      - Gerenciamento de Recursos
    security:
      - Bearer: []
    parameters:
      - in: path
        name: vmid
        type: integer
        required: true
        description: ID da VM/Container
    responses:
      200:
        description: Recurso destruído com sucesso
    """
    current_user_id = int(get_jwt_identity())
    resource = VirtualResource.query.filter_by(proxmox_vmid=vmid).first_or_404()
    user = User.query.get(current_user_id)
    
    if resource.owner_id != current_user_id and not getattr(user, 'is_admin', False):
         return jsonify({"error": "Sem permissão."}), 403

    try:
        try:
            if resource.type == 'lxc':
                proxmox_client.stop_container(vmid)
            elif resource.type == 'qemu' and hasattr(proxmox_client, 'stop_vm'):
                proxmox_client.stop_vm(vmid)
        except Exception:
            pass 

        if resource.type == 'lxc':
            proxmox_client.delete_container(vmid)
        elif resource.type == 'qemu' and hasattr(proxmox_client, 'delete_vm'):
             proxmox_client.delete_vm(vmid)

        db.session.delete(resource)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Recurso destruído.'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/resources', methods=['GET', 'OPTIONS'])
@cross_origin()
@jwt_required()
def list_user_resources():
    """
    Lista recursos do usuário com sincronização de status em tempo real.
    ---
    tags:
      - Leitura de Recursos
    security:
      - Bearer: []
    responses:
      200:
        description: Lista de recursos
        schema:
          type: array
          items:
            type: object
            properties:
              vmid:
                type: integer
              name:
                type: string
              status:
                type: string
              cpu:
                type: integer
              ram:
                type: integer
    """
    current_user_id = int(get_jwt_identity())
    resources = VirtualResource.query.filter_by(owner_id=current_user_id).all()
    
    try:
        node = proxmox_client._resolve_node_id()
        pve_online = True
    except Exception:
        pve_online = False

    output = []
    changes_detected = False

    for r in resources:
        real_status = r.status 
        
        if pve_online:
            try:
                if r.type == 'lxc':
                    st = proxmox_client.connection.nodes(node).lxc(r.proxmox_vmid).status.current.get()
                    real_status = st.get('status', 'unknown')
                elif r.type == 'qemu':
                    st = proxmox_client.connection.nodes(node).qemu(r.proxmox_vmid).status.current.get()
                    real_status = st.get('status', 'unknown')

                if real_status != r.status and real_status != 'unknown':
                    r.status = real_status
                    changes_detected = True

            except Exception as e:
                pass

        output.append({
            'id': r.id,
            'vmid': r.proxmox_vmid,
            'name': r.name,
            'type': r.type,
            'status': real_status,
            'cpu': r.cpu_cores,
            'ram': r.memory_mb,
            'storage': r.storage_gb,
            'created_at': r.created_at.isoformat() if r.created_at else None
        })
    
    if changes_detected:
        db.session.commit()

    return jsonify(output)


# ----------------------------------------------------------------
# ROTAS DE GERENCIAMENTO DE ENERGIA (Start, Stop, Reboot)
# ----------------------------------------------------------------

@bp.route('/resources/<int:vmid>/start', methods=['POST', 'OPTIONS'])
@cross_origin()
@jwt_required()
def start_resource(vmid):
    """
    Inicia a VM ou Container.
    ---
    tags:
      - Energia (Power)
    security:
      - Bearer: []
    parameters:
      - in: path
        name: vmid
        type: integer
        required: true
        description: ID do recurso
    responses:
      200:
        description: Recurso iniciado (ou já estava rodando)
    """
    current_user_id = int(get_jwt_identity())
    user = User.query.get(current_user_id)
    resource = VirtualResource.query.filter_by(proxmox_vmid=vmid).first_or_404()
    
    if resource.owner_id != current_user_id and not getattr(user, 'is_admin', False):
         return jsonify({"error": "Acesso negado."}), 403

    try:
        # Idempotência: Checa status real
        actual_status = 'unknown'
        try:
            if resource.type == 'lxc':
                status_data = proxmox_client.get_container_status(vmid)
                actual_status = status_data['data'].get('status', 'unknown')
        except Exception:
            pass

        if actual_status == 'running':
            resource.status = 'running'
            db.session.commit()
            return jsonify({'success': True, 'message': 'O recurso já está rodando.', 'status': 'running'})

        # Execução
        if resource.type == 'lxc':
            proxmox_client.start_container(vmid)
        elif resource.type == 'qemu':
            if hasattr(proxmox_client, 'start_vm'):
                proxmox_client.start_vm(vmid)
            else:
                node = proxmox_client._resolve_node_id()
                proxmox_client.connection.nodes(node).qemu(vmid).status.start.post()

        resource.status = 'running'
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Recurso iniciado.', 'status': 'running'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/resources/<int:vmid>/stop', methods=['POST', 'OPTIONS'])
@cross_origin()
@jwt_required()
def stop_resource(vmid):
    """
    Para (Stop) a VM ou Container.
    ---
    tags:
      - Energia (Power)
    security:
      - Bearer: []
    parameters:
      - in: path
        name: vmid
        type: integer
        required: true
        description: ID do recurso
    responses:
      200:
        description: Recurso parado (ou já estava parado)
    """
    current_user_id = int(get_jwt_identity())
    user = User.query.get(current_user_id)
    resource = VirtualResource.query.filter_by(proxmox_vmid=vmid).first_or_404()
    
    if resource.owner_id != current_user_id and not getattr(user, 'is_admin', False):
         return jsonify({"error": "Acesso negado."}), 403

    try:
        # Idempotência: Checa status real
        actual_status = 'unknown'
        try:
            if resource.type == 'lxc':
                status_data = proxmox_client.get_container_status(vmid)
                actual_status = status_data['data'].get('status', 'unknown')
        except Exception:
            pass

        if actual_status == 'stopped':
            resource.status = 'stopped'
            db.session.commit()
            return jsonify({'success': True, 'message': 'O recurso já está parado.', 'status': 'stopped'})

        # Execução
        if resource.type == 'lxc':
            proxmox_client.stop_container(vmid)
        elif resource.type == 'qemu':
            if hasattr(proxmox_client, 'stop_vm'):
                proxmox_client.stop_vm(vmid)
            else:
                node = proxmox_client._resolve_node_id()
                proxmox_client.connection.nodes(node).qemu(vmid).status.stop.post()

        resource.status = 'stopped'
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Recurso parado.', 'status': 'stopped'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/resources/<int:vmid>/reboot', methods=['POST', 'OPTIONS'])
@cross_origin()
@jwt_required()
def reboot_resource(vmid):
    """
    Reinicia o recurso (se estiver rodando).
    ---
    tags:
      - Energia (Power)
    security:
      - Bearer: []
    parameters:
      - in: path
        name: vmid
        type: integer
        required: true
        description: ID do recurso
    responses:
      200:
        description: Comando de reboot enviado
    """
    current_user_id = int(get_jwt_identity())
    user = User.query.get(current_user_id)
    resource = VirtualResource.query.filter_by(proxmox_vmid=vmid).first_or_404()
    
    if resource.owner_id != current_user_id and not getattr(user, 'is_admin', False):
         return jsonify({"error": "Acesso negado."}), 403

    try:
        # Verifica se está rodando
        actual_status = 'unknown'
        try:
            if resource.type == 'lxc':
                status_data = proxmox_client.get_container_status(vmid)
                actual_status = status_data['data'].get('status', 'unknown')
        except Exception:
            pass
        
        if actual_status == 'stopped':
            return jsonify({'error': 'Não é possível reiniciar um recurso parado. Inicie-o primeiro.'}), 400

        node = proxmox_client._resolve_node_id()
        
        if resource.type == 'lxc':
            proxmox_client.connection.nodes(node).lxc(vmid).status.reboot.post()
        elif resource.type == 'qemu':
            proxmox_client.connection.nodes(node).qemu(vmid).status.reset.post()

        resource.status = 'running'
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Comando de reboot enviado.', 'status': 'running'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ----------------------------------------------------------------
# ROTAS DE SNAPSHOTS
# ----------------------------------------------------------------

@bp.route('/resources/<int:vmid>/snapshots', methods=['GET', 'OPTIONS'])
@cross_origin()
@jwt_required()
def list_snapshots(vmid):
    """
    Lista snapshots de um recurso.
    ---
    tags:
      - Snapshots
    security:
      - Bearer: []
    parameters:
      - in: path
        name: vmid
        type: integer
        required: true
    responses:
      200:
        description: Lista de snapshots disponíveis
    """
    current_user_id = int(get_jwt_identity())
    user = User.query.get(current_user_id)
    resource = VirtualResource.query.filter_by(proxmox_vmid=vmid).first_or_404()
    
    if resource.owner_id != current_user_id and not getattr(user, 'is_admin', False):
         return jsonify({"error": "Acesso negado."}), 403

    try:
        node = proxmox_client._resolve_node_id()
        endpoint = 'lxc' if resource.type == 'lxc' else 'qemu'
        
        snaps = getattr(proxmox_client.connection.nodes(node), endpoint)(vmid).snapshot.get()
        valid_snaps = [s for s in snaps if s.get('name') != 'current']
        
        return jsonify(valid_snaps)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/resources/<int:vmid>/snapshots', methods=['POST', 'OPTIONS'])
@cross_origin()
@jwt_required()
def create_snapshot(vmid):
    """
    Cria um novo snapshot.
    ---
    tags:
      - Snapshots
    security:
      - Bearer: []
    parameters:
      - in: path
        name: vmid
        type: integer
        required: true
      - in: body
        name: body
        schema:
          type: object
          properties:
            name:
              type: string
              description: Nome do snapshot (opcional)
    responses:
      200:
        description: Snapshot criado com sucesso
    """
    current_user_id = int(get_jwt_identity())
    user = User.query.get(current_user_id)
    resource = VirtualResource.query.filter_by(proxmox_vmid=vmid).first_or_404()
    
    if resource.owner_id != current_user_id and not getattr(user, 'is_admin', False):
         return jsonify({"error": "Acesso negado."}), 403

    data = request.get_json()
    snap_name = data.get('name', f"snap_{vmid}_manual")

    try:
        node = proxmox_client._resolve_node_id()
        endpoint = 'lxc' if resource.type == 'lxc' else 'qemu'
        
        getattr(proxmox_client.connection.nodes(node), endpoint)(vmid).snapshot.post(
            snapname=snap_name,
            description="Criado via Nubemox"
        )
        
        return jsonify({'success': True, 'message': 'Snapshot criado com sucesso.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/resources/<int:vmid>/snapshots/<string:snapname>/rollback', methods=['POST', 'OPTIONS'])
@cross_origin()
@jwt_required()
def rollback_snapshot(vmid, snapname):
    """
    Restaura (Rollback) o recurso para um snapshot específico.
    ---
    tags:
      - Snapshots
    security:
      - Bearer: []
    parameters:
      - in: path
        name: vmid
        type: integer
        required: true
      - in: path
        name: snapname
        type: string
        required: true
    responses:
      200:
        description: Rollback iniciado
    """
    current_user_id = int(get_jwt_identity())
    user = User.query.get(current_user_id)
    resource = VirtualResource.query.filter_by(proxmox_vmid=vmid).first_or_404()
    
    if resource.owner_id != current_user_id and not getattr(user, 'is_admin', False):
         return jsonify({"error": "Acesso negado."}), 403

    try:
        node = proxmox_client._resolve_node_id()
        endpoint = 'lxc' if resource.type == 'lxc' else 'qemu'
        
        getattr(proxmox_client.connection.nodes(node), endpoint)(vmid).snapshot(snapname).rollback.post()
        
        return jsonify({'success': True, 'message': f'Rollback para {snapname} iniciado.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
# ----------------------------------------------------------------
# ROTA DE ACESSO REMOTO (VNC)
# ----------------------------------------------------------------

@bp.route('/resources/<int:vmid>/vnc', methods=['POST', 'OPTIONS'])
@cross_origin()
@jwt_required()
def get_vnc_console(vmid):
    """
    Gera um ticket VNC para acesso remoto via Browser (NoVNC).
    ---
    tags:
      - Acesso Remoto
    security:
      - Bearer: []
    parameters:
      - in: path
        name: vmid
        type: integer
        required: true
    responses:
      200:
        description: Credenciais do ticket VNC retornadas
    """
    current_user_id = int(get_jwt_identity())
    user = User.query.get(current_user_id)
    resource = VirtualResource.query.filter_by(proxmox_vmid=vmid).first_or_404()

    if resource.owner_id != current_user_id and not getattr(user, 'is_admin', False):
         return jsonify({"error": "Acesso negado."}), 403

    try:
        node = proxmox_client._resolve_node_id()
        # Detecta se é container (lxc) ou VM (qemu)
        type_path = 'lxc' if resource.type == 'lxc' else 'qemu'
        
        # 1. Cria o Ticket VNC no Proxmox (websocket=1 é crucial para NoVNC)
        # Equivalente a: pvesh create /nodes/{node}/{type}/{vmid}/vncproxy -websocket 1
        vnc_rpc = getattr(proxmox_client.connection.nodes(node), type_path)(vmid).vncproxy.post(websocket=1)
        
        # O Proxmox retorna um dicionário com o ticket e a porta
        ticket = vnc_rpc.get('ticket')
        port = vnc_rpc.get('port')
        
        # Em versões mais recentes do Proxmox API, o retorno pode variar,
        # mas geralmente contém 'ticket', 'port', 'user', 'cert'.
        
        if not ticket:
            raise Exception("Falha ao obter ticket VNC do Proxmox (Ticket vazio)")

        # 2. Retorna os dados para o Frontend montar a URL
        return jsonify({
            'success': True,
            'ticket': ticket,
            'port': port,
            'node': node,
            'vmid': vmid,
            'type': resource.type,
            # 'cert': vnc_rpc.get('cert'), # Opcional, dependendo da config do frontend
            # 'user': vnc_rpc.get('user')  # Opcional
        })

    except Exception as e:
        current_app.logger.error(f"Erro VNC: {e}")
        return jsonify({'error': str(e)}), 500