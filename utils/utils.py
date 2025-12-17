# app/utils/utils.py
from app.models import VirtualResource
import logging

logger = logging.getLogger(__name__)

def check_user_quota(user, requested_cpu=0, requested_ram=0, requested_storage=0):
    """
    Verifica se o utilizador tem saldo para criar um novo recurso.
    Retorna (True, None) ou (False, "Motivo do erro").
    """
    
    # 0. Bypass para Admin: Administradores não devem ser barrados por cota
    if getattr(user, 'is_admin', False):
        return True, "Admin bypass"

    # 1. Obter a Cota (que vem como Dicionário do user.py)
    # Estrutura esperada: {'limit': {'vms': 2, 'cpu': 4...}, 'used': {...}}
    quota_data = getattr(user, 'quota', None)
    
    if not quota_data or 'limit' not in quota_data:
        logger.warning(f"Utilizador {user.username} (ID: {user.id}) sem estrutura de cota válida.")
        return False, "Erro ao calcular cotas do usuário."

    limits = quota_data['limit']
    
    # Extrair limites (com fallback seguro para 0)
    max_vms = limits.get('vms', 0)
    max_cpu = limits.get('cpu', 0)
    max_ram = limits.get('memory', 0)
    max_storage = limits.get('storage', 0)

    # 2. Contagem de VMs Atuais
    current_vms = VirtualResource.query.filter_by(owner_id=user.id).count()
    
    # Validação de Quantidade de VMs
    if current_vms >= max_vms:
        return False, f"Limite de VMs atingido ({current_vms}/{max_vms})."

    # 3. Cálculo de Recursos Usados (CPU/RAM/Disk)
    resources = VirtualResource.query.filter_by(owner_id=user.id).all()
    
    # Soma segura (trata valores None como 0)
    used_ram = sum((r.memory_mb or 0) for r in resources)
    used_cpu = sum((r.cpu_cores or 0) for r in resources)
    used_storage = sum((r.storage_gb or 0) for r in resources)

    # Validações dos Inputs (garante int)
    req_ram = int(requested_ram or 0)
    req_cpu = int(requested_cpu or 0)
    req_storage = int(requested_storage or 0)

    # 4. Comparação (Uso Atual + Novo Pedido > Limite)
    if (used_ram + req_ram) > max_ram:
        available = max_ram - used_ram
        return False, f"Memória insuficiente. Disponível: {available}MB, Requisitado: {req_ram}MB."

    if (used_cpu + req_cpu) > max_cpu:
        available = max_cpu - used_cpu
        return False, f"vCPUs insuficientes. Disponível: {available}, Requisitado: {req_cpu}."

    if (used_storage + req_storage) > max_storage:
        available = max_storage - used_storage
        return False, f"Armazenamento insuficiente. Disponível: {available}GB, Requisitado: {req_storage}GB."

    return True, None