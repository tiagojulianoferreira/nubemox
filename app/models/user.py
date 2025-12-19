from app.extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from app.models.settings import SystemSetting 

# --- NOVO MODELO: GRUPO DE USUÁRIOS ---
class UserGroup(db.Model):
    __tablename__ = 'user_group'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False) # Ex: 'Alunos', 'Docentes'
    description = db.Column(db.String(255))
    
    # [NOVO] Campo para armazenar o filtro LDAP (Raw Filter)
    # Permite que o admin cole filtros como: (memberOf=cn=Professores,ou=Grupos...)
    ldap_filter = db.Column(db.String(1000), nullable=True)

    # --- Configurações de Infraestrutura (Infrastructure Policy) ---
    # Define ONDE os recursos deste grupo serão criados fisicamente
    default_storage_pool = db.Column(db.String(50), default='local-lvm') 
    default_network_bridge = db.Column(db.String(50), default='vmbr0')
    default_vlan_tag = db.Column(db.Integer, nullable=True) # Ex: 10 para Alunos, 20 para Profs
    
    # --- Cotas Padrão do Grupo ---
    max_vms = db.Column(db.Integer, default=2)
    max_cpu = db.Column(db.Integer, default=2)
    max_memory = db.Column(db.Integer, default=2048)
    max_storage = db.Column(db.Integer, default=20)

    # Relacionamento
    users = db.relationship('User', backref='group', lazy='dynamic')


class User(db.Model):
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    is_admin = db.Column(db.Boolean, default=False)
    
    # Novo campo: Link para o Grupo
    group_id = db.Column(db.Integer, db.ForeignKey('user_group.id'), nullable=True)
    
    # Relacionamento com recursos
    resources = db.relationship('VirtualResource', backref='owner', lazy='dynamic')

    # --- HIERARQUIA DE COTAS ---
    # 1. Override do Usuário (Prioridade Máxima)
    # 2. Config do Grupo
    # 3. Default do Sistema (SystemSettings)
    quota_cpu_override = db.Column(db.Integer, nullable=True)     
    quota_memory_override = db.Column(db.Integer, nullable=True)  
    quota_storage_override = db.Column(db.Integer, nullable=True) 
    quota_vms_override = db.Column(db.Integer, nullable=True)     

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def quota(self):
        """
        Calcula a cota efetiva baseada na hierarquia:
        User Override > User Group > System Settings
        """
        # 1. Determina os valores base (Do Grupo ou do Sistema)
        if self.group:
            base_vms = self.group.max_vms
            base_cpu = self.group.max_cpu
            base_mem = self.group.max_memory
            base_store = self.group.max_storage
        else:
            base_vms = SystemSetting.get_int('default_quota_vms', 2)
            base_cpu = SystemSetting.get_int('default_quota_cpu', 2)
            base_mem = SystemSetting.get_int('default_quota_memory', 2048)
            base_store = SystemSetting.get_int('default_quota_storage', 20)

        # 2. Aplica Overrides (se existirem)
        limit_vms = self.quota_vms_override if self.quota_vms_override is not None else base_vms
        limit_cpu = self.quota_cpu_override if self.quota_cpu_override is not None else base_cpu
        limit_mem = self.quota_memory_override if self.quota_memory_override is not None else base_mem
        limit_store = self.quota_storage_override if self.quota_storage_override is not None else base_store

        # 3. Calcular uso atual (soma do banco de dados)
        # Nota: Idealmente usamos COALESCE no SQL, mas aqui fazemos em Python para simplificar
        used_vms = 0
        used_cpu = 0
        used_mem = 0
        used_store = 0
        
        # Iteramos sobre recursos ativos (não destruídos)
        # O ideal é filtrar por status != 'terminated' se você tiver soft-delete
        for res in self.resources:
            used_vms += 1
            used_cpu += (res.cpu_cores or 0)
            used_mem += (res.memory_mb or 0)
            used_store += (res.storage_gb or 0)

        return {
            "limit": {
                "vms": limit_vms,
                "cpu": limit_cpu,
                "memory": limit_mem,
                "storage": limit_store
            },
            "used": {
                "vms": used_vms,
                "cpu": used_cpu,
                "memory": used_mem,
                "storage": used_store
            }
        }