import os

class Config:
    # --- SEGURANÇA ---
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-change-in-production'
    # Adicionado: Chave para assinar os tokens (login falha sem isso)
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'super-secret-jwt-key-change-me'
    
    # --- CONFIGS GERAIS ---
    DEBUG = False
    TESTING = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # --- PROXMOX ---
    PROXMOX_HOST = os.environ.get('PROXMOX_HOST', 'pve.local')
    PROXMOX_USER = os.environ.get('PROXMOX_USER', 'root@pam')
    PROXMOX_PASSWORD = os.environ.get('PROXMOX_PASSWORD', '')
    PROXMOX_API_TOKEN_NAME = os.environ.get('PROXMOX_API_TOKEN_NAME')
    PROXMOX_API_TOKEN_VALUE = os.environ.get('PROXMOX_API_TOKEN_VALUE')
    PROXMOX_DEFAULT_NODE = os.environ.get('PROXMOX_DEFAULT_NODE', 'pve-lab')
    
    # Realm onde criar usuários no Proxmox (Essencial para Shadow Users)
    PROXMOX_AUTH_REALM = os.environ.get('PROXMOX_AUTH_REALM', 'pve-ldap-mock')
    
    PROXMOX_VERIFY_SSL = os.environ.get('PROXMOX_VERIFY_SSL', 'false').lower() == 'true'

    # --- LDAP (INTEGRAÇÃO MANTIDA) ---
    LDAP_SERVER = os.environ.get('LDAP_SERVER', 'ldap://localhost:389')
    # O {} será substituído pelo username no login
    LDAP_USER_DN_TEMPLATE = os.environ.get('LDAP_USER_DN_TEMPLATE', 'cn={},ou=users,dc=nubemox,dc=local')
    LDAP_BASE_DN = os.environ.get('LDAP_BASE_DN', 'dc=nubemox,dc=local')

    # --- API & CORS ---
    API_PREFIX = '/api'
    CORS_ORIGINS = ['http://localhost:5000', 'http://localhost:5173']

    # --- TAREFAS ASSÍNCRONAS ---
    PROXMOX_TASK_TIMEOUT = int(os.environ.get('PROXMOX_TASK_TIMEOUT', 300)) 
    PROXMOX_TASK_POLL_INTERVAL = int(os.environ.get('PROXMOX_TASK_POLL_INTERVAL', 2))

class DevelopmentConfig(Config):
    """
    Configuração para Dev Local com Docker.
    Conecta no localhost:5432 onde o container Postgres está a rodar.
    """
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'postgresql://nubemox:password@localhost:5432/nubemox'

class ProductionConfig(Config):
    """
    Configuração para Produção.
    """
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')