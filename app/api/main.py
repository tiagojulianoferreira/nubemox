from flask import Blueprint, jsonify
from flask_cors import cross_origin
from datetime import datetime
# Importamos o Singleton que já configuramos e sabemos que funciona (ou deveria)
from app.extensions import db, proxmox_client 
from sqlalchemy import text

main_bp = Blueprint('main', __name__)

@main_bp.route('/', methods=['GET'])
def index():
    return jsonify({
        "project": "Nubemox API",
        "status": "online",
        "documentation": "/docs"
    }), 200

@main_bp.route('/health', methods=['GET'])
@main_bp.route('/api/health', methods=['GET', 'OPTIONS'])
@cross_origin()
def health_check():
    """
    Verifica a saúde usando a MESMA conexão que o resto do sistema usa.
    """
    status_report = {
        "status": "online",     # Estado geral da API (Python)
        "database": "unknown",  # Estado do PostgreSQL
        "proxmox": "unknown",   # Estado do Hypervisor
        "details": {},
        "server_time": datetime.utcnow().isoformat()
    }

    # 1. TESTE DE BANCO DE DADOS
    try:
        db.session.execute(text('SELECT 1'))
        status_report['database'] = "connected"
    except Exception as e:
        status_report['status'] = "unstable"
        status_report['database'] = "disconnected"
        status_report['details']['db_error'] = str(e)

    # 2. TESTE DE PROXMOX (Usando Singleton)
    try:
        # Acessa a propriedade .connection. Se falhar autenticação/rede, estoura erro aqui.
        conn = proxmox_client.connection
        
        # Tenta uma operação leve de leitura (listar nós)
        nodes = conn.nodes.get()
        
        status_report['proxmox'] = "connected"
        status_report['details']['nodes_online'] = len(nodes)
        
        # Pega versão para garantir leitura profunda
        version = conn.version.get()
        status_report['details']['pve_version'] = version.get('version', 'unknown')

    except Exception as e:
        # Se cair aqui, o Frontend recebe "proxmox": "disconnected" e pinta de vermelho
        status_report['status'] = "unstable"
        status_report['proxmox'] = "disconnected"
        status_report['details']['proxmox_error'] = str(e)
        
        # Log no terminal para você debugar
        print(f"\n ERRO NO HEALTH CHECK (PROXMOX): {str(e)}\n")

    return jsonify(status_report), 200