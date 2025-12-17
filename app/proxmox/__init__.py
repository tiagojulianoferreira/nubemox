from flask import Blueprint

# 1. Importar a Classe Base (Conexão e Helpers)
from .client import ProxmoxClient

# 2. Importar os Gerenciadores de Recursos (Mixins)
# Estes ficheiros devem estar na pasta app/proxmox/resources/
from .resources.lxc import LXCManager
from .resources.qemu import QEMUManager
from .resources.network import NetworkManager
from .resources.storage import StorageManager
from .resources.pool import PoolManager
from .resources.snapshot import SnapshotManager
from .resources.access import AccessManager
from .resources.inspector import TemplateInspector

# 3. Definir o Blueprint
# Necessário para registrar rotas específicas do módulo Proxmox (se houverem)
bp = Blueprint('proxmox', __name__)

# 4. Definir a Classe de Serviço Unificada (Facade)
# A ordem de herança importa: ProxmoxClient fornece a base (self.connection),
# e os outros fornecem os métodos específicos (.create_container, .create_vm, etc.)
class ProxmoxService(ProxmoxClient, 
                     LXCManager, 
                     QEMUManager, 
                     NetworkManager, 
                     StorageManager, 
                     PoolManager, 
                     SnapshotManager, 
                     AccessManager, 
                     TemplateInspector):
    """
    Serviço Unificado (Facade) do Proxmox.
    
    Ao instanciar esta classe, você obtém um objeto que sabe:
    1. Conectar-se ao cluster (via ProxmoxClient)
    2. Gerir Containers (via LXCManager)
    3. Gerir VMs (via QEMUManager)
    4. Gerir Redes, Storage, Pools, etc.
    """
    pass

# 5. Criar a Instância Global (Singleton)
# Esta é a variável que será importada pelo resto da aplicação (app/extensions.py ou rotas)
proxmox_client = ProxmoxService()

# 6. Importar Rotas (no final para evitar Ciclo de Importação)
from . import routes