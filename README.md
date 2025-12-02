# 🚀 Nubemox - Interface API para Proxmox VE

Este projeto é uma API em Python (Flask) que serve como uma camada de gerenciamento simplificada para um cluster **Proxmox Virtual Environment (PVE)**. Ele permite a automatização de tarefas como listagem, criação e controle de energia de VMs e Contêineres, além do gerenciamento de Resource Pools para multi-tenancy.

## 📋 Requisitos Básicos para Execução

Para rodar o Nubemox Backend, você precisa de:

### 1\. Sistema Operacional e Ambiente

  * **Python:** Versão 3.8+
  * **Sistema Operacional:** Linux, macOS ou Windows.
  * **Dependências:** Instale as bibliotecas Python (Flask, `proxmoxer`, etc.) usando o arquivo `requirements.txt`:
    ```bash
    pip install -r requirements.txt
    ```

### 2\. Instância do Proxmox VE (PVE)

Você deve ter acesso a um cluster PVE funcional. As seguintes credenciais devem ser configuradas no seu arquivo de ambiente (`.env`):

| Variável | Exemplo | Descrição |
| :--- | :--- | :--- |
| `PROXMOX_HOST` | `pve.local` | Endereço IP ou FQDN do seu PVE. |
| `PROXMOX_USER` | `root@pam` | Usuário **completo** (com realm) para autenticação. |
| `PROXMOX_API_TOKEN_NAME` | `nubemox_api` | Nome do API Token criado no PVE. |
| `PROXMOX_API_TOKEN_VALUE` | `00000000-0000-0000...` | Valor do segredo do API Token. |
| `PROXMOX_DEFAULT_NODE` | `pve01` | O ID do Node que será usado por padrão nas rotas sem especificação. |
| `PROXMOX_VERIFY_SSL` | `false` | Defina como `true` se você estiver usando um certificado SSL válido. |

> ⚠️ **IMPORTANTE:** O **API Token** deve ser criado no PVE e ter as permissões necessárias (`PVEAdmin` ou uma Role customizada) para criar VMs/CTs, manipular *Resource Pools* e gerenciar o ciclo de vida dos recursos (`VM.PowerMgmt`, `Pool.Allocate`, etc.).

### 3\. Execução

Inicie o aplicativo Flask usando o arquivo `run.py`:

```bash
python run.py
```

A API estará acessível em `http://localhost:5000/api/proxmox`.

## 🛠️ Próximas Etapas (TO DO LIST)

O plano atual visa completar o gerenciamento essencial e, em seguida, construir a base para o isolamento de recursos por usuário (Pools).

| Status | Funcionalidade | ID | Descrição |
| :--- | :--- | :--- | :--- |
| ✅ | **Fase 1: Gerenciamento Essencial e Pools (Core)** | |
| | **Exclusão de VMs (`DELETE`)** | **1.1** | Implementar a rota e o método de serviço para **excluir permanentemente** uma VM (Qemu). |
| | **Exclusão de CTs (`DELETE`)** | **1.2** | Implementar a rota e o método de serviço para **excluir permanentemente** um Contêiner LXC. |
| | **Criação de Recurso c/ Pool ID** | **2.2** | Modificar `create_vm()` e `create_container()` para **exigir o `poolid`** e adicionar o recurso ao pool no momento da criação. |
| | **Listagem Otimizada por Pool** | **1.4** | Refatorar rotas de listagem para aceitar `poolid` e listar apenas os recursos daquele pool (base para isolamento). |
| | **Fase 2: Isolamento (Multi-Tenancy) e ACLs** | |
| | **Criação de Usuário PVE** | **3.1** | Implementar método para **criar um novo usuário PVE** (sem senha, para uso com LDAP) usando a conta Admin do `.env`. |
| | **Criação de ACLs de Isolamento** | **3.2** | Implementar método para **associar o novo usuário** ao seu Resource Pool exclusivo (`/pool/<poolid>`) com uma **Role restritiva** (`PVEVMUser` ou customizada), garantindo que ele não possa ver outros pools ou recursos. |
| | **Rotas por Node Específico** | **2.1** | Adaptar rotas de status/criação/ação para permitir a especificação explícita do Node ID na URL. |