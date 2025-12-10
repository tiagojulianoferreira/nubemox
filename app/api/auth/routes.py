# app/api/auth/routes.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from app.services.ldap_service import LDAPService
from app.models import User, ResourceQuota
from app.extensions import db

bp = Blueprint('auth', __name__)

@bp.route('/login', methods=['POST'])
def login():
    """
    Autentica o utilizador via LDAP e retorna um JWT.
    Sincroniza o utilizador LDAP com o banco local (Postgres).
    ---
    tags:
      - Autenticação
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [username, password]
          properties:
            username:
              type: string
              example: "tiago"
            password:
              type: string
              example: "123456"
    responses:
      200:
        description: Login realizado com sucesso
      401:
        description: Credenciais inválidas
    """
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"msg": "Username e password obrigatórios"}), 400

    # 1. Autenticar no LDAP
    ldap_service = LDAPService()
    ldap_user_data = ldap_service.authenticate(username, password)

    if not ldap_user_data:
        return jsonify({"msg": "Credenciais inválidas (LDAP)"}), 401

    # 2. Lógica "Shadow User" (Sincronizar com DB Local)
    user = User.query.filter_by(username=username).first()

    if not user:
        # Cria novo utilizador localmente
        user = User(
            username=username, 
            email=ldap_user_data['email'],
            is_active=True,
            is_admin=False # Por segurança, novos não são admin
        )
        # Define uma senha dummy no banco local (já que a real está no LDAP)
        user.set_password('ldap-managed-account')
        
        # Cria Cota Padrão para novos utilizadores
        default_quota = ResourceQuota(user=user) # Usa defaults do model (2 VMs, 4GB RAM)
        
        db.session.add(user)
        db.session.add(default_quota)
        db.session.commit()
        print(f"🆕 Utilizador '{username}' criado no banco local.")
    else:
        # Atualiza dados existentes (ex: email mudou no LDAP)
        if user.email != ldap_user_data['email']:
            user.email = ldap_user_data['email']
            db.session.commit()

    # 3. Gerar Token JWT
    # O 'identity' geralmente é o ID do utilizador no banco local
    access_token = create_access_token(identity=str(user.id))

    return jsonify({
        "access_token": access_token,
        "user": user.to_dict()
    }), 200