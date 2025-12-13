from flask import Flask, jsonify
import flask
import markupsafe
# Patch para compatibilidade do Flasgger com Flask 3.0+
flask.Markup = markupsafe.Markup 

from flasgger import Swagger
from app.config import DevelopmentConfig
from app.extensions import db, migrate, cors, login_manager, jwt, bcrypt
from proxmoxer import ResourceException, AuthenticationError

# --- CORREÇÃO 1: Importar a exceção do novo local (client.py) ---
from app.proxmox.client import ProxmoxTaskFailedError
import logging

def create_app(config_class=DevelopmentConfig):
    """Factory do aplicativo Flask"""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # REGISTRO DE COMANDOS (Novo)
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
    
    # 1. Inicializar extensões
    init_extensions(app)
    
    # 2. Configurar logging
    configure_logging(app)
    
    # 3. Registrar Rotas e Blueprints
    register_blueprints(app)
    
    # 4. Registrar Tratamento de Erros Global
    register_error_handlers(app)
    
    @login_manager.user_loader
    def load_user(user_id):
        return None
    
    return app

def init_extensions(app):
    """Inicializa todas as extensões do Flask."""
    db.init_app(app)
    migrate.init_app(app, db)
    
    cors.init_app(app, resources={
        r"/api/*": {
            "origins": app.config.get('CORS_ORIGINS', '*'),
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"]
        }
    })
    
    login_manager.init_app(app)
    jwt.init_app(app)
    bcrypt.init_app(app)

def configure_logging(app):
    if not app.debug:
        logging.basicConfig(level=logging.INFO)

def register_blueprints(app):
    """Registra os módulos de rotas (Blueprints)."""
    prefix = app.config.get('API_PREFIX', '/api')

    # --- CORREÇÃO 2: Importar do novo módulo modular 'app.proxmox' ---
    # O __init__.py de app/proxmox expõe o 'bp'
    from app.proxmox import bp as proxmox_bp
    app.register_blueprint(proxmox_bp, url_prefix=f"{prefix}/proxmox")

    # Módulo Catálogo
    from app.api.catalog.routes import bp as catalog_bp
    app.register_blueprint(catalog_bp, url_prefix=f"{prefix}/catalog")

    # Módulo Provisionamento
    from app.api.provisioning.routes import bp as provisioning_bp
    app.register_blueprint(provisioning_bp, url_prefix=f"{prefix}/provisioning")

    # Módulo Auth
    from app.api.auth.routes import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix=f"{prefix}/auth")

def register_error_handlers(app):
    """Centraliza o tratamento de exceções da aplicação."""
    
    @app.errorhandler(ResourceException)
    def handle_proxmox_resource_error(e):
        app.logger.error(f"Proxmox Resource Error: {str(e)}")
        # Retorna o erro real para facilitar o debug (em prod, oculte isso)
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