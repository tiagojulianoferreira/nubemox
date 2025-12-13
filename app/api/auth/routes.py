from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from app.services.ldap_service import LDAPService
from app.models import User, UserQuota  # <--- CORRIGIDO: Nome atualizado
from app.extensions import db, bcrypt

bp = Blueprint('auth', __name__)

@bp.route('/login', methods=['POST'])
def login():
    """
    Autentica o utilizador e retorna um Token JWT.
    
    Tenta autenticação via LDAP primeiro. Se bem-sucedido, sincroniza o utilizador 
    no banco de dados local (Shadow User) e cria cotas padrão se necessário.
    Caso o LDAP falhe ou o usuário seja local (ex: admin), tenta autenticação local.
    
    ---
    tags:
      - Autenticação
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - username
            - password
          properties:
            username:
              type: string
              example: "tiago"
            password:
              type: string
              example: "senha123"
    responses:
      200:
        description: Login realizado com sucesso.
        schema:
          type: object
          properties:
            access_token:
              type: string
              description: "Token JWT para cabeçalho Authorization: Bearer <token>"
            user:
              type: object
              properties:
                id:
                  type: integer
                username:
                  type: string
                is_admin:
                  type: boolean
      401:
        description: Credenciais inválidas (LDAP ou Local).
    """
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"msg": "Username e password obrigatórios"}), 400

    ldap_user_data = None
    
    # 1. TENTATIVA VIA LDAP (Prioritária)
    try:
        ldap_service = LDAPService()
        # Se conectar, retorna dict com email/dn. Se falhar, retorna None.
        ldap_user_data = ldap_service.authenticate(username, password)
    except Exception as e:
        print(f"⚠️ Erro ao contactar LDAP: {e}. Tentando login local...")

    user = User.query.filter_by(username=username).first()

    # 2. SINCRONIZAÇÃO OU FALLBACK
    if ldap_user_data:
        # --- CASO A: Sucesso no LDAP (Shadow User Logic) ---
        if not user:
            # Cria novo utilizador localmente (Shadow User)
            user = User(
                username=username, 
                email=ldap_user_data.get('email', f'{username}@nubemox.local'),
                is_admin=False # Por segurança, novos do LDAP não são admin
            )
            # Senha dummy local (a real está no LDAP)
            user.set_password('ldap-managed-account')
            
            db.session.add(user)
            db.session.flush() # Gera o ID para usar na cota
            
            # Cria Cota Padrão (CORRIGIDO PARA UserQuota)
            default_quota = UserQuota(
                user_id=user.id,
                max_vms=2,
                max_cpu_cores=4,
                max_memory_mb=4096,
                max_storage_gb=20
            )
            db.session.add(default_quota)
            db.session.commit()
            print(f"🆕 Shadow User '{username}' criado no banco local via LDAP.")
            
        else:
            # Atualiza dados existentes se necessário
            email_ldap = ldap_user_data.get('email')
            if email_ldap and user.email != email_ldap:
                user.email = email_ldap
                db.session.commit()
    
    else:
        # --- CASO B: Falha no LDAP -> Tenta Login Local (Ex: Admin CLI) ---
        if not user or not user.check_password(password):
            return jsonify({"msg": "Credenciais inválidas"}), 401

    # 3. GERAÇÃO DO TOKEN
    access_token = create_access_token(identity=str(user.id))
    
    return jsonify({
        "access_token": access_token,
        "user": {
            "id": user.id,
            "username": user.username,
            "is_admin": user.is_admin
        }
    }), 200

@bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user_profile():
    """
    Retorna o perfil do usuário logado e o consumo de sua cota.
    
    Esta rota é usada pelo Dashboard para mostrar gráficos de consumo.
    Calcula dinamicamente quantos recursos (CPU/RAM) o usuário está usando.
    
    ---
    tags:
      - Autenticação
    security:
      - Bearer: []
    responses:
      200:
        description: Perfil do usuário e status da cota.
        schema:
          type: object
          properties:
            username:
              type: string
            quota:
              type: object
              properties:
                limit:
                  type: object
                  description: Limites definidos no banco
                used:
                  type: object
                  description: Consumo atual calculado
      404:
        description: Usuário não encontrado.
    """
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    
    if not user:
        return jsonify({"msg": "Usuário não encontrado"}), 404

    # Garante que cota existe (correção para usuários legados)
    if not user.quota:
        default_quota = UserQuota(user_id=user.id)
        db.session.add(default_quota)
        db.session.commit()

    # Cálculo de uso em tempo real
    # Como definimos lazy='dynamic' no model User, podemos filtrar
    # Mas aqui vamos usar a lista carregada
    resources = user.resources.all()
    
    used_vms = len(resources)
    used_cpu = sum(r.cpu_cores for r in resources)
    used_ram = sum(r.memory_mb for r in resources)
    used_storage = sum(r.storage_gb for r in resources)

    return jsonify({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_admin": user.is_admin,
        "quota": {
            "used": {
                "vms": used_vms,
                "cpu": used_cpu,
                "memory": used_ram,
                "storage": used_storage
            },
            "limit": {
                "vms": user.quota.max_vms,
                "cpu": user.quota.max_cpu_cores,
                "memory": user.quota.max_memory_mb,
                "storage": user.quota.max_storage_gb
            }
        }
    })