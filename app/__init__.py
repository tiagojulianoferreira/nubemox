from flask import Flask, jsonify
from flasgger import Swagger
from app.config import DevelopmentConfig
from app.extensions import db, migrate, cors, login_manager
from proxmoxer import ResourceException, AuthenticationError
# Importamos a exceção customizada para capturá-la globalmente
from app.services.proxmox_service import ProxmoxTaskFailedError
import logging


def create_app(config_class=DevelopmentConfig):
    """Factory do aplicativo Flask"""
    app = Flask(__name__)
    app.config.from_object(config_class)

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
        "specs_route": "/docs"  # <--- A documentação ficará em /docs
    }
    
    swagger = Swagger(app, config=swagger_config) # <--- Inicializar
    
    # 1. Inicializar extensões
    init_extensions(app)
    
    # 2. Configurar logging
    configure_logging(app)
    
    # 3. Registrar Rotas e Blueprints
    register_blueprints(app)
    
    # 4. Registrar Tratamento de Erros Global (NOVO)
    register_error_handlers(app)
    
    @login_manager.user_loader
    def load_user(user_id):
        # Por enquanto, retornamos None pois não temos DB de usuários ainda.
        # Quando tivermos o modelo User, faremos: return User.query.get(int(user_id))
        return None

    # Health check endpoint
    @app.route('/health')
    def health():
        return jsonify({
            'status': 'healthy',
            'service': 'nubemox',
            'version': '0.1.0'
        })
        
    return app

def init_extensions(app):
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

def configure_logging(app):
    if not app.debug:
        logging.basicConfig(level=logging.INFO)

def register_blueprints(app):
    from app.api.proxmox import bp as proxmox_bp
    # Usa o prefixo definido na config ou default
    prefix = app.config.get('API_PREFIX', '/api')
    app.register_blueprint(proxmox_bp, url_prefix=f"{prefix}/proxmox")

def register_error_handlers(app):
    """Centraliza o tratamento de exceções da aplicação."""
    
    # Erros do Proxmoxer (API do Proxmox rejeitou ou falhou)
    @app.errorhandler(ResourceException)
    def handle_proxmox_resource_error(e):
        app.logger.error(f"Proxmox Resource Error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

    # Erros de Autenticação com o Proxmox
    @app.errorhandler(AuthenticationError)
    def handle_auth_error(e):
        app.logger.error(f"Proxmox Auth Error: {str(e)}")
        return jsonify({'success': False, 'error': 'Falha de autenticação com o Proxmox backend.'}), 401

    # Erros de Tarefas Assíncronas (Polling falhou)
    @app.errorhandler(ProxmoxTaskFailedError)
    def handle_task_error(e):
        app.logger.error(f"Proxmox Task Error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
        
    # Erro de Validação (abort(400))
    @app.errorhandler(400)
    def handle_bad_request(e):
        return jsonify({'success': False, 'error': e.description}), 400

    # Rota não encontrada
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Endpoint not found'}), 404

    # Erro Genérico (Crash do servidor)
    @app.errorhandler(500)
    def handle_generic_error(e):
        app.logger.error(f"Internal Server Error: {str(e)}")
        return jsonify({'success': False, 'error': 'Erro interno do servidor. Consulte os logs.'}), 500