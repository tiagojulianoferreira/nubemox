from abc import ABC, abstractmethod
import time

class HealthCheckProvider(ABC):
    """
    Interface base para todos os verificadores de saúde (Proxmox, DB, Redis, etc).
    """

    @property
    @abstractmethod
    def name(self):
        """Nome legível do serviço (ex: 'Proxmox Hypervisor')"""
        pass

    @property
    @abstractmethod
    def category(self):
        """Categoria: 'compute', 'storage', 'network', 'database'"""
        pass

    @abstractmethod
    def check(self):
        """
        Lógica específica de verificação.
        Deve retornar um dicionário com 'status': 'healthy' e metadados opcionais,
        ou lançar uma exceção em caso de erro.
        """
        pass

    def run(self):
        """
        Método wrapper que mede o tempo de resposta e trata exceções.
        """
        start = time.time()
        try:
            result = self.check()
            # Garante que o status existe
            if 'status' not in result:
                result['status'] = 'healthy'
        except Exception as e:
            result = {
                'status': 'unhealthy',
                'error': str(e)
            }
        
        # Calcula latência em milissegundos
        latency = (time.time() - start) * 1000
        result['latency_ms'] = round(latency, 2)
        
        return result