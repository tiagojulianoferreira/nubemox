class LXCManager:
    """Mixin responsável por operações de Contêineres (LXC)."""

    def get_containers(self, node_id=None):
        node_id = self._resolve_node_id(node_id)
        cts = self.connection.nodes(node_id).lxc.get()
        return {'data': cts, 'count': len(cts)}

    def get_container_config(self, ctid):
        node_id = self._resolve_node_id()
        return {'data': self.connection.nodes(node_id).lxc(ctid).config.get()}
    
    def get_container_status(self, ctid):
        node_id = self._resolve_node_id()
        return {'data': self.connection.nodes(node_id).lxc(ctid).status.current.get()}

    def create_container(self, config: dict):
        node_id = self._resolve_node_id()
        vmid = config.get('vmid') or self.get_next_vmid()
        
        create_config = {
            'vmid': vmid,
            'ostemplate': config['template'],
            'hostname': config['name'],
            'memory': config.get('memory', 512),
            'cores': config.get('cores', 1),
            'storage': config.get('storage', 'local-lvm'),
            'rootfs': config.get('rootfs') or f"{config.get('storage', 'local-lvm')}:{config.get('disk_size', 8)}",
            'net0': config.get('net0', 'name=eth0,bridge=vmbr0,ip=dhcp'),
            'pool': config.get('poolid')
        }
        # Remove chaves nulas
        create_config = {k: v for k, v in create_config.items() if v is not None}

        upid = self.connection.nodes(node_id).lxc.post(**create_config)
        self._wait_for_task_completion(upid, node_id)
        return {'ctid': vmid, 'message': f'CT {vmid} criado com sucesso.'}

    def clone_container(self, source_vmid, new_vmid, name, poolid=None, full_clone=True):
        node_id = self._resolve_node_id()
        params = {
            'newid': new_vmid,
            'hostname': name,
            'full': 1 if full_clone else 0,
        }
        if poolid: params['pool'] = poolid

        upid = self.connection.nodes(node_id).lxc(source_vmid).clone.post(**params)
        self._wait_for_task_completion(upid, node_id)
        return {'ctid': new_vmid, 'message': f"CT {new_vmid} clonado."}

    def update_container_resources(self, ctid, updates: dict):
        node_id = self._resolve_node_id()
        valid_keys = ['memory', 'cores', 'rootfs', 'swap', 'net0', 'hostname']
        params = {k: v for k, v in updates.items() if k in valid_keys}
        
        if params:
            res = self.connection.nodes(node_id).lxc(ctid).config.put(**params)
            if isinstance(res, str) and res.startswith("UPID:"):
                self._wait_for_task_completion(res, node_id)
        return {'message': f'CT {ctid} atualizado.'}

    def start_container(self, ctid):
        node_id = self._resolve_node_id()
        upid = self.connection.nodes(node_id).lxc(ctid).status.start.post()
        self._wait_for_task_completion(upid, node_id)
        return {'message': f'CT {ctid} iniciado.'}
    
    def stop_container(self, ctid):
        node_id = self._resolve_node_id()
        upid = self.connection.nodes(node_id).lxc(ctid).status.stop.post()
        self._wait_for_task_completion(upid, node_id)
        return {'message': f'CT {ctid} parado.'}
        
    def delete_container(self, ctid):
        """
        Remove o container. Usado na rota DELETE normal 
        e agora também na limpeza de Zumbis.
        """
        node_id = self._resolve_node_id()
        # Chama a API DELETE do Proxmox
        upid = self.connection.nodes(node_id).lxc(ctid).delete()
        self._wait_for_task_completion(upid, node_id)
        return {'message': f'CT {ctid} excluído.'}
    
    def resize_disk(self, vmid, new_size_gb, disk='rootfs'):
        node_id = self._resolve_node_id()
        size_str = f"{new_size_gb}G"
        upid = self.connection.nodes(node_id).lxc(vmid).resize.put(disk=disk, size=size_str)
        self._wait_for_task_completion(upid, node_id)
        return {'message': f'Disco redimensionado para {size_str}'}
    
   