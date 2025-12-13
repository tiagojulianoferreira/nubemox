import re

class TemplateInspector:
    def inspect_resource(self, vmid, resource_type):
        """Lê specs do Proxmox."""
        node_id = self._resolve_node_id()
        specs = {'cpu': 1, 'memory': 512, 'storage': 8}
        try:
            if resource_type == 'lxc':
                raw = self.connection.nodes(node_id).lxc(vmid).config.get()
                if 'cores' in raw: specs['cpu'] = int(raw['cores'])
                if 'memory' in raw: specs['memory'] = int(raw['memory'])
                if 'rootfs' in raw:
                    match = re.search(r'size=(\d+)([GM])', raw['rootfs'])
                    if match:
                        size = int(match.group(1))
                        specs['storage'] = size if match.group(2) == 'G' else size // 1024
            return specs
        except Exception:
            return specs