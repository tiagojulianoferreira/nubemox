from app.extensions import db
from datetime import datetime

class ServiceTemplate(db.Model):
    __tablename__ = 'service_template'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), nullable=False) # 'lxc' ou 'qemu'
    proxmox_template_volid = db.Column(db.String(100), nullable=False) # ex: 100 ou local:vztmpl/...
    deploy_mode = db.Column(db.String(20), default='clone')
    
    description = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    logo_url = db.Column(db.String(255))
    category = db.Column(db.String(50), default='os')
    
    # Specs fixas deste template
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