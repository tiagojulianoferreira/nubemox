class QEMUManager:
    """Mixin responsável por Máquinas Virtuais (KVM/QEMU)."""

    def get_vms(self, node_id=None):
        node_id = self._resolve_node_id(node_id)
        vms = self.connection.nodes(node_id).qemu.get()
        return {'data': vms, 'count': len(vms)}

    def create_vm(self, config: dict):
        node_id = self._resolve_node_id()
        vmid = config.get('vmid') or self.get_next_vmid()
        
        create_config = {
            'vmid': vmid,
            'name': config['name'],
            'cores': config.get('cores', 2),
            'memory': config.get('memory', 2048),
            'net0': config.get('net0', 'virtio,bridge=vmbr0'),
            'scsi0': config.get('scsi0', f"{config.get('storage', 'local-lvm')}:{config.get('disk_size', 20)}"),
            'pool': config.get('poolid')
        }
        # Limpeza
        create_config = {k: v for k, v in create_config.items() if v is not None}
        
        upid = self.connection.nodes(node_id).qemu.create(**create_config)
        self._wait_for_task_completion(upid, node_id)
        return {'vmid': vmid, 'message': f'VM {vmid} criada.'}

    def start_vm(self, vmid):
        node_id = self._resolve_node_id()
        upid = self.connection.nodes(node_id).qemu(vmid).status.start.post()
        self._wait_for_task_completion(upid, node_id)
        return {'message': f'VM {vmid} iniciada.'}

    def stop_vm(self, vmid):
        node_id = self._resolve_node_id()
        upid = self.connection.nodes(node_id).qemu(vmid).status.stop.post()
        self._wait_for_task_completion(upid, node_id)
        return {'message': f'VM {vmid} parada.'}
        
    def delete_vm(self, vmid):
        node_id = self._resolve_node_id()
        upid = self.connection.nodes(node_id).qemu(vmid).delete()
        self._wait_for_task_completion(upid, node_id)
        return {'message': f'VM {vmid} excluída.'}