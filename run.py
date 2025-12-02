#!/usr/bin/env python3
"""
Entry point para desenvolvimento
"""
import os
from app import create_app
from app.config import DevelopmentConfig

app = create_app(DevelopmentConfig)

if __name__ == '__main__':
    print("""
    🚀 Nubemox Backend - Proxmox API Interface
    ==========================================
    
    Endpoints disponíveis (Node Padrão):
    - GET  /health                    → Health check
    - GET  /api/proxmox/test          → Testar conexão Proxmox
    - GET  /api/proxmox/nodes         → Listar todos os nodes
    - GET  /api/proxmox/node/status   → Status do Node Padrão
    - GET  /api/proxmox/vms           → Listar VMs no Node Padrão
    - POST /api/proxmox/vms            → Criar nova VM
    - GET  /api/proxmox/vms/<vmid>/status → Status da VM
    - POST /api/proxmox/vms/<vmid>/start → Iniciar VM
    - POST /api/proxmox/vms/<vmid>/stop  → Parar VM
    - GET  /api/proxmox/cts           → Listar Contêineres LXC no Node Padrão
    - POST /api/proxmox/cts           → Criar novo Contêiner LXC
    - GET  /api/proxmox/cts/<ctid>/status → Status do Contêiner LXC
    - POST /api/proxmox/cts/<ctid>/start → Iniciar Contêiner LXC
    - POST /api/proxmox/cts/<ctid>/stop  → Parar Contêiner LXC
    - GET  /api/proxmox/pools         → Listar Pools de Recursos
    - POST /api/proxmox/pools         → Criar Pool de Recursos
    
    Servidor rodando em: http://localhost:5000
    """)
    app.run(host='0.0.0.0', port=5000, debug=True)