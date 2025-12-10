# app/proxmox/resources/access.py
from flask import current_app

class AccessManager:
    """Mixin para gerenciamento de Usuários e Permissões (ACLs) no PVE."""

    def get_users(self):
        return {'data': self.connection.access.users.get()}

    def ensure_pve_user(self, username, realm=None):
        """
        Garante que o usuário exista no PVE mapeado para o Realm correto.
        Ex: cria 'tiago@pve-ldap' se não existir.
        """
        # Se não passar realm, tenta pegar do config ou usa 'pam'
        if not realm:
            realm = current_app.config.get('PROXMOX_AUTH_REALM', 'pam')
            
        pve_userid = f"{username}@{realm}"
        
        # Verifica se já existe (para evitar erro 400 ou 500 desnecessário)
        users = self.connection.access.users.get()
        exists = any(u.get('userid') == pve_userid for u in users)
        
        if not exists:
            # Cria o usuário. Não definimos senha pois a autenticação é delegada ao Realm.
            self.connection.access.users.post(userid=pve_userid, enable=1, comment="Gerenciado pelo Nubemox")
            print(f"Usuário PVE {pve_userid} criado.")
        
        return pve_userid

    def set_pool_permission(self, poolid, pve_userid, role='PVEVMUser'):
        """
        Define permissão (ACL) sobre um Pool.
        - path: /pool/{poolid}
        - roles: PVEVMUser (Pode ver, ligar, desligar, console)
        - users: tiago@realm
        """
        try:
            # O endpoint acl aceita PUT para adicionar/atualizar regras
            self.connection.access.acl.put(
                path=f"/pool/{poolid}",
                roles=role,
                users=pve_userid
            )
            return {'message': f"Permissão {role} concedida a {pve_userid} em {poolid}"}
        except Exception as e:
            # Logar erro mas não quebrar o fluxo se for algo menor
            print(f"Erro ao definir ACL: {e}")
            raise e