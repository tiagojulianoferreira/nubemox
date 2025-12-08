from proxmoxer import ResourceException

class NetworkManager:
    """Mixin para Firewall e Rate Limit."""

    def enable_container_firewall(self, ctid):
        node_id = self._resolve_node_id()
        # Habilita Globalmente no CT
        self.connection.nodes(node_id).lxc(ctid).firewall.options.put(enable=1)
        
        # Habilita na Interface (net0)
        config = self.connection.nodes(node_id).lxc(ctid).config.get()
        net0 = config.get('net0', '')
        if 'firewall=1' not in net0:
            self.connection.nodes(node_id).lxc(ctid).config.put(net0=f"{net0},firewall=1")
        return {'message': f'Firewall habilitado para CT {ctid}.'}

    def add_firewall_rule(self, ctid, rule: dict):
        node_id = self._resolve_node_id()
        params = {
            'type': rule.get('type', 'in'),
            'action': rule.get('action', 'ACCEPT'),
            'enable': 1,
            'proto': rule.get('proto'),
            'dport': rule.get('dport'),
            'comment': rule.get('comment')
        }
        # Remove nulos
        params = {k: v for k, v in params.items() if v is not None}
        self.connection.nodes(node_id).lxc(ctid).firewall.rules.post(**params)
        return {'message': 'Regra adicionada.'}

    def set_container_network_rate_limit(self, ctid, rate_mbps):
        node_id = self._resolve_node_id()
        config = self.connection.nodes(node_id).lxc(ctid).config.get()
        net0_conf = config.get('net0', '')
        
        # Lógica de parsing de string (simplificada para brevidade)
        props = dict(item.split('=') for item in net0_conf.split(',') if '=' in item)
        
        if rate_mbps and int(rate_mbps) > 0:
            props['rate'] = str(rate_mbps)
        else:
            props.pop('rate', None)
            
        new_conf = ','.join([f"{k}={v}" for k, v in props.items()])
        self.connection.nodes(node_id).lxc(ctid).config.put(net0=new_conf)
        return {'message': f'Rate limit definido para {rate_mbps}MB/s.'}