# Comandos úteis para validação


### Iniciar/Parar contêiner LXC por ID (POST)
```
# inicia
curl -X POST http://127.0.0.1:5000/api/proxmox/cts/101/start

# para
curl -X POST http://127.0.0.1:5000/api/proxmox/cts/101/stop

```
### Deleta VM por ID (DELETE)
```
curl -X DELETE http://127.0.0.1:5000/api/proxmox/vms/102
```

### Ajustar recursos de CPU e RAM do LXC (PUT)
```
curl -X PUT http://localhost:5000/api/proxmox/cts/101   -H "Content-Type: application/json"   -d '{
        "memory": 1024, 
        "cores": 3
      }'
```

### Incrementar Disco e CPU do LXC (PUT)
```
curl -X PUT http://localhost:5000/api/proxmox/cts/101 \
  -H "Content-Type: application/json" \
  -d '{
        "disk_increment_gb": 10,
        "cores": 4
      }'
```
Calcula o novo tamanho: TAMANHO ATUAL + 10G = 20G.

### Criar novo Resource Pool
```
curl -X POST \
  http://localhost:5000/api/proxmox/pools \
  -H "Content-Type: application/json" \
  -d '{
        "poolid": "pool-dev", 
        "comment": "Recursos reservados para ambiente de desenvolvimento."
      }'

```