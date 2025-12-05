# Nubemox - Interface API para Proxmox VE

Este projeto é uma API em Python (Flask) que serve como uma camada de gerenciamento simplificada para um cluster **Proxmox Virtual Environment (PVE)**. Ele permite a automatização de tarefas como listagem, criação e controle de VMs e Contêineres, além do gerenciamento de Resource Pools para multi-tenancy.

Ativando serviços em 3 passos? Esse é desafio que nos propomos. Será que é possível?

## 📋 Funcionalidades

* **Gerenciamento de Ciclo de Vida:** Criar, Iniciar, Parar e Excluir VMs e CTs.
* **Provisionamento de Usuários:** Criação automática de Pools isolados (`vps-username`).
* **Segurança:** Gerenciamento de Firewall e Rate Limiting de Rede por container.
* **Snapshots:** Criação e rollback de pontos de restauração.
* **Polling Inteligente:** Suporte a operações assíncronas do Proxmox.

## 🚀 Como Rodar

### Pré-requisitos
* Python 3.10+
* Acesso a um cluster Proxmox VE (Host, User, Token/Password).

### Instalação

1.  **Clone o repositório:**
    ```bash
    git clone [https://github.com/tiagojulianoferreira/nubemox](https://github.com/tiagojulianoferreira/nubemox)
    cd nubemox
    ```

2.  **Crie o ambiente virtual:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # Linux/Mac
    # .venv\Scripts\activate   # Windows
    ```

3.  **Instale as dependências:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure as Variáveis de Ambiente:**
    Crie um arquivo `.env` na raiz ou exporte as variáveis:
    ```bash
    export PROXMOX_HOST="192.168.1.10"
    export PROXMOX_USER="root@pam"
    export PROXMOX_API_TOKEN_NAME="nubemox"
    export PROXMOX_API_TOKEN_VALUE="seu-token-secreto-aqui"
    export PROXMOX_DEFAULT_NODE="pve-01"
    # Timeout para tarefas longas (segundos)
    export PROXMOX_TASK_TIMEOUT=300
    ```

5.  **Execute:**
    ```bash
    python run.py
    ```

## Documentação da API

Com o servidor rodando, acesse a documentação interativa (Swagger UI):
**http://localhost:5000/docs**

## Arquitetura

O sistema utiliza uma arquitetura de camadas:
1.  **Routes:** Validação de entrada e resposta HTTP.
2.  **Service:** Lógica de negócio, polling e tratamento de regras.
3.  **Proxmoxer:** Comunicação direta com a API do PVE.

---
Desenvolvido para um contexto experimental de campus da Instituto Federal.