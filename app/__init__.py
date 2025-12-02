from flask import Flask, jsonify
from app.config import DevelopmentConfig
from app.extensions import db, migrate, cors, login_manager
import logging

def create_app(config_class=DevelopmentConfig):
    """Factory do aplicativo Flask"""
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Inicializar extensões
    db.init_app(app)
    migrate.init_app(app, db)
    cors.init_app(app, resources={
        r"/api/*": {
            "origins": app.config['CORS_ORIGINS'],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"]
        }
    })
    login_manager.init_app(app)
    
    # Configurar logging
    if not app.debug:
        logging.basicConfig(level=logging.INFO)
    
    # Health check endpoint
    @app.route('/health')
    def health():
        return jsonify({
            'status': 'healthy',
            'service': 'nubemox',
            'version': '0.1.0'
        })
    
    # Registrar blueprints
    from app.api.proxmox import bp as proxmox_bp
    app.register_blueprint(proxmox_bp, url_prefix=f"{app.config['API_PREFIX']}/proxmox")
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Not found'}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f'Server Error: {error}')
        return jsonify({'error': 'Internal server error'}), 500
    
    return app