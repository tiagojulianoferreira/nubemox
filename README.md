# Nubemox - Interface API para Proxmox VE

Este projeto é uma API em Python (Flask) que serve como uma camada de gerenciamento simplificada para um cluster **Proxmox Virtual Environment (PVE)**. Ele permite a automatização de tarefas como listagem, criação e controle de VMs e Contêineres, além do gerenciamento de Resource Pools para multi-tenancy.

Ativando serviços em 3 passos? Esse é desafio que nos propomos. Será que é possível?

## Requisitos Básicos para Execução

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

>  **IMPORTANTE:** O **API Token** deve ser criado no PVE e ter as permissões necessárias (`PVEAdmin` ou uma Role customizada) para criar VMs/CTs, manipular *Resource Pools* e gerenciar o ciclo de vida dos recursos (`VM.PowerMgmt`, `Pool.Allocate`, etc.).

### 3\. Execução

Inicie o aplicativo Flask usando o arquivo `run.py`:

```bash
python run.py
```

A API estará acessível em `http://localhost:5000/api/proxmox`.

Com prazer!

Aqui está a tabela **API Reference: Gerenciamento de Recursos (Node Padrão)** em formato Markdown. Ela será a base da documentação para o desenvolvedor *frontend* e pode ser incluída diretamente no seu `README.md`.

---

## API Reference: Gerenciamento de Recursos (Nubemox)

Todas as requisições utilizam o prefixo base configurado: **`/api/proxmox`**.

---

### Rotas de Status e Listagem

| Funcionalidade | Endpoint (Prefixo: `/api/proxmox`) | Método | Descrição |
| :--- | :--- | :--- | :--- |
| **Teste de Conexão** | `/test` | `GET` | Testa a conectividade e as credenciais com o PVE. |
| **Listar Nodes** | `/nodes` | `GET` | Lista todos os nodes do cluster. |
| **Resumo do Cluster** | `/cluster/summary` | `GET` | Resumo simplificado do cluster (Contagem de Nodes). |
| **Listar VMs** | `/vms` | `GET` | Lista todas as VMs do Node Padrão. |
| **Listar CTs** | `/cts` | `GET` | Lista todos os Contêineres (CTs) do Node Padrão. |
| **Listar Pools** | `/pools` | `GET` | Lista todos os Resource Pools criados. |
| **Status VM** | `/vms/<vmid>/status` | `GET` | Obtém o status em tempo real da VM. |
| **Status CT** | `/cts/<ctid>/status` | `GET` | Obtém o status em tempo real do CT. |
| **Console VNC** | `/vms/<vmid>/vnc` | `GET` | Obtém dados para conexão VNC/WebSocket. |

---

### Rotas de Criação e Modificação

| Funcionalidade | Endpoint (Prefixo: `/api/proxmox`) | Método | Descrição |
| :--- | :--- | :--- | :--- |
| **Criar Pool** | `/pools` | `POST` | Cria um novo Resource Pool. (Body: `poolid`, `comment`). |
| **Criar VM** | `/vms` | `POST` | **Cria** uma nova VM. **Requer** `poolid` (Body: `vmid`, `name`, `memory`, `cores`, `storage`, `poolid`). |
| **Criar CT** | `/cts` | `POST` | **Cria** um novo Contêiner. **Requer** `poolid` (Body: `vmid`, `name`, `template`, `storage`, `poolid`). |
| **Atualizar CT** | `/cts/<ctid>` | **`PUT`** | **Atualiza recursos** (memória, cores, swap, etc.). Suporta incremento de disco via chave simplificada **`"disk_increment_gb"`**. |

---

### Rotas de Ação e Exclusão

| Funcionalidade | Endpoint (Prefixo: `/api/proxmox`) | Método | Descrição |
| :--- | :--- | :--- | :--- |
| **Iniciar VM** | `/vms/<vmid>/start` | `POST` | Inicia a VM. |
| **Parar VM** | `/vms/<vmid>/stop` | `POST` | Desliga a VM (shutdown gracioso). |
| **Reiniciar VM** | `/vms/<vmid>/reboot` | `POST` | Reinicia a VM. |
| **Iniciar CT** | `/cts/<ctid>/start` | `POST` | Inicia o Contêiner. |
| **Parar CT** | `/cts/<ctid>/stop` | `POST` | Desliga o Contêiner. |
| **Excluir VM** | `/vms/<vmid>` | `DELETE` | **Exclui permanentemente a VM.** |
| **Excluir CT** | `/cts/<ctid>` | `DELETE` | **Exclui permanentemente o Contêiner.** |

---

Com as rotas de criação (`POST /vms` e `POST /cts`) atualizadas para exigir o `poolid` (conforme nosso plano de desenvolvimento), podemos agora focar na **implementação dessa validação** e no método de criação de **Resource Pools**.
## Próximas Etapas (TO DO LIST)

O plano atual visa completar o gerenciamento essencial e, em seguida, construir a base para o isolamento de recursos por usuário (Pools).

| Status | Funcionalidade | ID | Descrição |
| :--- | :--- | :--- | :--- |
| | **Fase 1: Gerenciamento Essencial e Pools (Core)** | |
| | **Criação de Recurso c/ Pool ID** | **2.2** | Modificar `create_vm()` e `create_container()` para **exigir o `poolid`** e adicionar o recurso ao pool no momento da criação. |
| | **Listagem Otimizada por Pool** | **1.4** | Refatorar rotas de listagem para aceitar `poolid` e listar apenas os recursos daquele pool (base para isolamento). |
| | **Fase 2: Isolamento (Multi-Tenancy) e ACLs** | |
| | **Criação de Usuário PVE** | **3.1** | Implementar método para **criar um novo usuário PVE** (sem senha, para uso com LDAP) usando a conta Admin do `.env`. |
| | **Criação de ACLs de Isolamento** | **3.2** | Implementar método para **associar o novo usuário** ao seu Resource Pool exclusivo (`/pool/<poolid>`) com uma **Role restritiva** (`PVEVMUser` ou customizada), garantindo que ele não possa ver outros pools ou recursos. |
| | **Isolamento LXC** | **2.1** | Garantir que somente sejam criados LXC Unprivileged. |