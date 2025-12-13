from flask import Blueprint
from .client import ProxmoxClient

# Importando os Mixins (Poderes)
# Certifique-se que você criou a pasta resources e os arquivos lxc.py, qemu.py, etc.
from .resources.lxc import LXCManager
from .resources.qemu import QEMUManager
from .resources.network import NetworkManager
from .resources.storage import StorageManager
from .resources.pool import PoolManager
from .resources.snapshot import SnapshotManager
from .resources.access import AccessManager
from .resources.inspector import TemplateInspector

# 1. Definir o Blueprint PRIMEIRO para evitar erro de importação
bp = Blueprint('proxmox', __name__)

# 2. Definir a Classe de Serviço Unificada
class ProxmoxService(ProxmoxClient, LXCManager, QEMUManager, NetworkManager, StorageManager, PoolManager, SnapshotManager, AccessManager, TemplateInspector):
    """
    Serviço Unificado (Facade).
    Herda capacidades de conexão (Client) e de gerenciamento (Managers).
    """
    pass

# 3. Importar as rotas POR ÚLTIMO
# Isso evita o erro "cannot import name 'bp'", pois o 'bp' já foi criado nas linhas acima
from . import routes