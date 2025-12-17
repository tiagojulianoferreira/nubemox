from flask import Flask, jsonify
import flask
import markupsafe
# Patch para compatibilidade do Flasgger com Flask 3.0+
flask.Markup = markupsafe.Markup 

from flasgger import Swagger
from app.config import DevelopmentConfig

# 1. IMPORTAÇÃO CENTRALIZADA (SINGLETON)
# Agora importamos o proxmox_client daqui, junto com as outras extensões
from app.extensions import db, migrate, cors, login_manager, jwt, bcrypt, proxmox_client

from proxmoxer import ResourceException, AuthenticationError
# Ajuste o import abaixo conforme onde definiu sua classe de exceção
# Se estiver no client.py, mantenha. Se moveu, ajuste.
from app.proxmox.client import ProxmoxTaskFailedError 
import logging

from app.api.main import main_bp

def create_app(config_class=DevelopmentConfig):
    """Factory do aplicativo Flask"""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # REGISTRO DE COMANDOS
    from app.commands import init_db_command
    app.cli.add_command(init_db_command)

    # Configuração do Swagger
    swagger_config = {
        "headers": [],
        "specs": [
            {
                "endpoint": 'apispec',
                "route": '/apispec.json',
                "rule_filter": lambda rule: True,
                "model_filter": lambda tag: True,
            }
        ],
        "static_url_path": "/flasgger_static",
        "swagger_ui": True,
        "specs_route": "/docs"
    }
    
    swagger = Swagger(app, config=swagger_config)
    
    # 2. INICIALIZAR EXTENSÕES
    # Movemos a lógica para a função auxiliar, incluindo o Proxmox
    init_extensions(app)
    
    # 3. CONFIGURAR LOGGING
    configure_logging(app)
    
    # 4. REGISTRAR ROTAS
    register_blueprints(app)
    
    # Registra a rota raiz (Health Check / Main)
    app.register_blueprint(main_bp)

    # 5. TRATAMENTO DE ERROS
    register_error_handlers(app)
    
    @login_manager.user_loader
    def load_user(user_id):
        return None
    
    return app

def init_extensions(app):
    """Inicializa todas as extensões do Flask."""
    db.init_app(app)
    migrate.init_app(app, db)
    
    # Configuração de CORS (Mantida a sua correção anterior)
    cors.init_app(app, resources={r"/*": {
        "origins": ["http://localhost:5173", "http://127.0.0.1:5173"],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "expose_headers": ["Content-Range", "X-Total-Count"]
    }}, supports_credentials=True)
    
    login_manager.init_app(app)
    jwt.init_app(app)
    bcrypt.init_app(app)

    # --- INICIALIZAÇÃO DO SINGLETON PROXMOX ---
    # O objeto já existe (criado em extensions.py), aqui apenas injetamos a config do app.
    proxmox_client.init_app(app)

def configure_logging(app):
    if not app.debug:
        logging.basicConfig(level=logging.INFO)

def register_blueprints(app):
    """Registra os módulos de rotas (Blueprints)."""
    prefix = app.config.get('API_PREFIX', '/api')

    # Removemos imports cíclicos ao importar dentro da função
    from app.proxmox import bp as proxmox_bp
    app.register_blueprint(proxmox_bp, url_prefix=f"{prefix}/proxmox")

    from app.api.catalog.routes import bp as catalog_bp
    app.register_blueprint(catalog_bp, url_prefix=f"{prefix}/catalog")

    from app.api.provisioning.routes import bp as provisioning_bp
    app.register_blueprint(provisioning_bp, url_prefix=f"{prefix}/provisioning")

    from app.api.auth.routes import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix=f"{prefix}/auth")

    from app.api.admin.routes import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix='/api/admin')

def register_error_handlers(app):
    """Centraliza o tratamento de exceções da aplicação."""
    
    @app.errorhandler(ResourceException)
    def handle_proxmox_resource_error(e):
        app.logger.error(f"Proxmox Resource Error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

    @app.errorhandler(AuthenticationError)
    def handle_auth_error(e):
        app.logger.error(f"Proxmox Auth Error: {str(e)}")
        return jsonify({'success': False, 'error': 'Falha de autenticação com o Proxmox backend.'}), 401

    @app.errorhandler(ProxmoxTaskFailedError)
    def handle_task_error(e):
        app.logger.error(f"Proxmox Task Error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
        
    @app.errorhandler(400)
    def handle_bad_request(e):
        return jsonify({'success': False, 'error': e.description}), 400

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Endpoint not found'}), 404

    @app.errorhandler(500)
    def handle_generic_error(e):
        app.logger.error(f"Internal Server Error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500