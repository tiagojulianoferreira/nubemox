from app.extensions import db
from datetime import datetime

class VirtualResource(db.Model):
    __tablename__ = 'virtual_resource'
    
    id = db.Column(db.Integer, primary_key=True)
    proxmox_vmid = db.Column(db.Integer, unique=True, nullable=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), nullable=False) # 'qemu' (VM) ou 'lxc' (Container)
    
    # Relacionamentos
    # Note o uso de strings ('ServiceTemplate') para evitar imports circulares se necessário
    template_id = db.Column(db.Integer, db.ForeignKey('service_template.id'), nullable=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Snapshot das specs no momento da criação (para calcular consumo)
    cpu_cores = db.Column(db.Integer, default=1)
    memory_mb = db.Column(db.Integer, default=512)
    storage_gb = db.Column(db.Integer, default=8)
    
    status = db.Column(db.String(20), default='provisioning')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)