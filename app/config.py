import os


class Config:
    # App
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-change-in-production'
    DEBUG = False
    TESTING = False
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'postgresql://nubemox:password@localhost/nubemox'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Proxmox
    PROXMOX_HOST = os.environ.get('PROXMOX_HOST', 'pve.local')
    
    # 1. Usuário/Realm (Usado como 'user' na API, obrigatório com ou sem token)
    PROXMOX_USER = os.environ.get('PROXMOX_USER', 'root@pam')
    PROXMOX_PASSWORD = os.environ.get('PROXMOX_PASSWORD', '') # Fallback para User/Pass
    
    # 2. Credenciais API Token (Preferencial)
    PROXMOX_API_TOKEN_NAME = os.environ.get('PROXMOX_API_TOKEN_NAME')
    PROXMOX_API_TOKEN_VALUE = os.environ.get('PROXMOX_API_TOKEN_VALUE')
    
    # Node Padrão (Renomeado)
    PROXMOX_DEFAULT_NODE = os.environ.get('PROXMOX_DEFAULT_NODE', 'pve-lab')
    PROXMOX_VERIFY_SSL = os.environ.get('PROXMOX_VERIFY_SSL', 'false').lower() == 'true'
    
    # API
    API_PREFIX = '/api'
    
    # CORS
    CORS_ORIGINS = ['http://localhost:3000', 'http://localhost:5173']

    # --- Configurações de Polling para Tarefas Assíncronas ---
    # Tempo limite em segundos para o Nubemox esperar pela conclusão de tarefas no PVE (5 minutos padrão)
    PROXMOX_TASK_TIMEOUT = int(os.environ.get('PROXMOX_TASK_TIMEOUT', 300)) 
    # Intervalo de polling em segundos (5 segundos padrão)
    PROXMOX_TASK_POLL_INTERVAL = int(os.environ.get('PROXMOX_TASK_POLL_INTERVAL', 5))
    
    # Endereço do servidor (ex: ldap://localhost:389)
    LDAP_SERVER = os.environ.get('LDAP_SERVER', 'ldap://localhost:389')
    
    # Template para login (DN). 
    # O {} será substituído pelo username (ex: cn=tiago,ou=users...)
    # Se não houver no .env, usa o padrão do nosso mock.
    LDAP_USER_DN_TEMPLATE = os.environ.get('LDAP_USER_DN_TEMPLATE', 'cn={},ou=users,dc=nubemox,dc=local')
    
    # Base DN (Opcional, usado se quisermos fazer buscas genéricas)
    LDAP_BASE_DN = os.environ.get('LDAP_BASE_DN', 'dc=nubemox,dc=local')

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

class TestingConfig(Config):
    TESTING = True
    # Se DATABASE_URL existir, usa ela (Postgres). Se não, cai pro SQLite local.
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///app.db'
