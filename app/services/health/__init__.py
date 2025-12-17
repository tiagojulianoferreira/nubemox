from .providers.proxmox import ProxmoxHealthCheck

def get_system_health():
    """
    Executa verificação de saúde em todos os subsistemas registrados.
    """
    # Lista de providers ativos no sistema
    providers = [
        ProxmoxHealthCheck(),
        # Futuramente: DatabaseHealthCheck(), RedisHealthCheck()...
    ]

    results = []
    global_status = "healthy"

    for provider in providers:
        # Executa o check (o método .run() trata erros e cronometra)
        data = provider.run()
        
        # Adiciona metadados
        data['name'] = provider.name
        data['category'] = provider.category
        
        # Se algum falhar, o status global do sistema muda
        if data['status'] != 'healthy':
            global_status = "unhealthy"
        
        results.append(data)

    return {
        "status": global_status,
        "checks": results
    }