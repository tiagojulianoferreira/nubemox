from app.extensions import db, bcrypt
from datetime import datetime

# ==========================================
# 1. GESTÃO DE USUÁRIOS E COTAS
# ==========================================

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    
    # Perfil e Status
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    
    # Vínculo com Proxmox: Nome do Pool deste usuário (ex: vps-admin)
    proxmox_pool = db.Column(db.String(64), unique=True, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relacionamentos
    # cascade="all, delete-orphan" remove a cota se o usuário for deletado
    quota = db.relationship('ResourceQuota', backref='user', uselist=False, cascade="all, delete-orphan")
    resources = db.relationship('VirtualResource', backref='owner', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'is_admin': self.is_admin,
            'pool': self.proxmox_pool,
            'quota': self.quota.to_dict() if self.quota else None
        }

class ResourceQuota(db.Model):
    """
    Define o TETO global de consumo do usuário.
    Serve para impedir que um usuário consuma recursos infinitos do cluster.
    """
    __tablename__ = 'resource_quotas'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    
    max_vms = db.Column(db.Integer, default=2)        # Máximo de instâncias
    max_cpu_cores = db.Column(db.Integer, default=4)  # Soma total de Cores
    max_memory_mb = db.Column(db.Integer, default=4096) # Soma total de RAM (4GB)
    max_storage_gb = db.Column(db.Integer, default=50)  # Soma total de Disco (50GB)

    def to_dict(self):
        return {
            'max_vms': self.max_vms,
            'max_cpu_cores': self.max_cpu_cores,
            'max_memory_mb': self.max_memory_mb,
            'max_storage_gb': self.max_storage_gb
        }

# ==========================================
# 2. CATÁLOGO DE SERVIÇOS (SIMPLIFICADO)
# ==========================================

class ServiceTemplate(db.Model):
    """
    Catálogo de Serviços.
    Define apenas a ORIGEM e o MODO de deploy. 
    Não guarda mais specs de hardware (confia no PVE ou Defaults).
    """
    __tablename__ = 'service_templates'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False) # Ex: "PostgreSQL 15"
    type = db.Column(db.String(10), nullable=False)  # 'lxc' ou 'qemu'
    
    # Identificador no Proxmox (VolID ou VMID)
    # Ex file: "local:vztmpl/debian...tar.zst"
    # Ex clone: "9000"
    proxmox_template_volid = db.Column(db.String(255), nullable=False)
    
    # Estratégia de Deploy: 'file' (ISO/ZST) ou 'clone' (VM/CT existente)
    deploy_mode = db.Column(db.String(20), default='file', nullable=False)
    
    description = db.Column(db.String(255))
    logo_url = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'mode': self.deploy_mode,
            'source': self.proxmox_template_volid,
            'description': self.description,
            'logo': self.logo_url
        }

# ==========================================
# 3. INVENTÁRIO (O QUE FOI CRIADO)
# ==========================================

class VirtualResource(db.Model):
    """
    Registra os recursos criados e seu consumo ATUAL.
    Embora o Template não defina hardware mínimo, precisamos rastrear
    quanto cada recurso está consumindo para abater da Cota do Usuário.
    """
    __tablename__ = 'virtual_resources'

    id = db.Column(db.Integer, primary_key=True)
    
    # Identificação no Proxmox
    proxmox_vmid = db.Column(db.Integer, nullable=False, index=True)
    name = db.Column(db.String(64), nullable=False)
    type = db.Column(db.String(10), nullable=False) # 'lxc' ou 'qemu'
    
    # Origem
    template_id = db.Column(db.Integer, db.ForeignKey('service_templates.id'), nullable=True)
    
    # Dono
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Configuração Atual (Sincronizada ou Cacheada)
    # Fundamental para validação de cota (ex: Usuário tem 2 VMs de 2GB = 4GB usados)
    cpu_cores = db.Column(db.Integer, default=1)
    memory_mb = db.Column(db.Integer, default=512)
    storage_gb = db.Column(db.Integer, default=8)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'vmid': self.proxmox_vmid,
            'name': self.name,
            'type': self.type,
            'specs': {
                'cores': self.cpu_cores,
                'memory': self.memory_mb,
                'storage': self.storage_gb
            },
            'template_id': self.template_id,
            'created_at': self.created_at.isoformat()
        }