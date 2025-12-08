# app/proxmox/resources/snapshot.py

class SnapshotManager:
    """Mixin para gerenciamento de Snapshots (Backups de estado)."""

    def _get_resource_endpoint(self, node_id, vmid, resource_type):
        """Helper interno para selecionar entre LXC ou QEMU."""
        if resource_type == 'lxc':
            return self.connection.nodes(node_id).lxc(vmid)
        elif resource_type == 'qemu':
            return self.connection.nodes(node_id).qemu(vmid)
        else:
            raise ValueError(f"Tipo de recurso desconhecido: {resource_type}")

    def get_snapshots(self, vmid, resource_type='qemu'):
        node_id = self._resolve_node_id()
        resource = self._get_resource_endpoint(node_id, vmid, resource_type)
        # O endpoint retorna uma lista flat ou árvore dependendo da versão, 
        # mas .get() é o padrão.
        return {'data': resource.snapshot.get()}

    def create_snapshot(self, vmid, snapname, description=None, vmstate=False, resource_type='qemu'):
        node_id = self._resolve_node_id()
        resource = self._get_resource_endpoint(node_id, vmid, resource_type)
        
        params = {'snapname': snapname}
        if description: params['description'] = description
        
        # 'vmstate' salva a RAM (apenas para VMs QEMU)
        if vmstate and resource_type == 'qemu': 
            params['vmstate'] = 1
        
        upid = resource.snapshot.post(**params)
        self._wait_for_task_completion(upid, node_id)
        return {'message': f"Snapshot '{snapname}' criado."}

    def rollback_snapshot(self, vmid, snapname, resource_type='qemu'):
        node_id = self._resolve_node_id()
        resource = self._get_resource_endpoint(node_id, vmid, resource_type)
        
        upid = resource.snapshot(snapname).rollback.post()
        self._wait_for_task_completion(upid, node_id)
        return {'message': f"Rollback para '{snapname}' concluído."}

    def delete_snapshot(self, vmid, snapname, resource_type='qemu'):
        node_id = self._resolve_node_id()
        resource = self._get_resource_endpoint(node_id, vmid, resource_type)
        
        upid = resource.snapshot(snapname).delete()
        self._wait_for_task_completion(upid, node_id)
        return {'message': f"Snapshot '{snapname}' excluído."}