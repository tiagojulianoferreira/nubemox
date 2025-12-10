# app/utils/utils.py
from app.models import VirtualResource

def check_user_quota(user, requested_cpu=0, requested_ram=0, requested_storage=0):
    """
    Verifica se o utilizador tem saldo para criar um novo recurso.
    Retorna (True, None) ou (False, "Motivo do erro").
    """
    quota = user.quota
    if not quota:
        # Se não tem cota definida, assumimos que não pode criar nada (ou policy default)
        return False, "Utilizador sem cota definida."

    # 1. Contagem de VMs
    current_vms = VirtualResource.query.filter_by(owner_id=user.id).count()
    if current_vms >= quota.max_vms:
        return False, f"Limite de VMs atingido ({current_vms}/{quota.max_vms})."

    # 2. Cálculo de Recursos Usados (Soma do que está no banco)
    resources = VirtualResource.query.filter_by(owner_id=user.id).all()
    used_ram = sum(r.memory_mb for r in resources)
    used_cpu = sum(r.cpu_cores for r in resources)
    used_storage = sum(r.storage_gb for r in resources)

    if (used_ram + requested_ram) > quota.max_memory_mb:
        return False, f"Cota de RAM excedida. Livre: {quota.max_memory_mb - used_ram}MB."

    if (used_cpu + requested_cpu) > quota.max_cpu_cores:
        return False, "Cota de vCPUs excedida."

    if (used_storage + requested_storage) > quota.max_storage_gb:
        return False, "Cota de Disco excedida."

    return True, None