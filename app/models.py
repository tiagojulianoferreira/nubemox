from app.extensions import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

class User(db.Model):
    __tablename__ = 'user'  # <--- Garanta que esta linha existe
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    is_admin = db.Column(db.Boolean, default=False)
    
    resources = db.relationship('VirtualResource', backref='owner', lazy='dynamic')
    quota = db.relationship('UserQuota', backref='user', uselist=False, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class UserQuota(db.Model):
    __tablename__ = 'user_quota'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    
    max_vms = db.Column(db.Integer, default=2)
    max_cpu_cores = db.Column(db.Integer, default=4)
    max_memory_mb = db.Column(db.Integer, default=4096)
    max_storage_gb = db.Column(db.Integer, default=40)

class ServiceTemplate(db.Model):
    __tablename__ = 'service_template'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    proxmox_template_volid = db.Column(db.String(100), nullable=False)
    deploy_mode = db.Column(db.String(20), default='clone')
    description = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    logo_url = db.Column(db.String(255))
    category = db.Column(db.String(50), default='os')
    default_cpu = db.Column(db.Integer, default=1)
    default_memory = db.Column(db.Integer, default=512)
    default_storage = db.Column(db.Integer, default=8)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'description': self.description,
            'category': self.category,
            'logo_url': self.logo_url,
            'specs': {
                'cpu': self.default_cpu,
                'memory': self.default_memory,
                'storage': self.default_storage
            }
        }

class VirtualResource(db.Model):
    __tablename__ = 'virtual_resource'
    
    id = db.Column(db.Integer, primary_key=True)
    proxmox_vmid = db.Column(db.Integer, unique=True, nullable=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    
    template_id = db.Column(db.Integer, db.ForeignKey('service_template.id'), nullable=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    cpu_cores = db.Column(db.Integer, default=1)
    memory_mb = db.Column(db.Integer, default=512)
    storage_gb = db.Column(db.Integer, default=8)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='provisioning')