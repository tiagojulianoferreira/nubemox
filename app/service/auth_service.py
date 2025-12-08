# app/services/auth_service.py
from ldap3 import Server, Connection, ALL
from flask import current_app

class LDAPAuthService:
    def authenticate(self, username, password):
        """
        Tenta bindar no LDAP. Se sucesso, retorna dados do user.
        Se falha, retorna None.
        """
        server_uri = current_app.config['LDAP_SERVER']
        # Monta o DN (Distinguished Name)
        # Ex: uid=tiago,ou=users,dc=empresa...
        user_dn = current_app.config['LDAP_USER_DN_TEMPLATE'].format(username)
        
        server = Server(server_uri, get_info=ALL)
        try:
            conn = Connection(server, user=user_dn, password=password, auto_bind=True)
            
            # Se passou daqui, a senha está correta.
            # Vamos buscar dados extras (email, fullname)
            conn.search(user_dn, '(objectclass=*)', attributes=['mail', 'cn', 'uid'])
            
            if not conn.entries:
                return None
                
            entry = conn.entries[0]
            return {
                'username': str(entry.uid), # ou username passado
                'email': str(entry.mail) if 'mail' in entry else f"{username}@local",
                'fullname': str(entry.cn) if 'cn' in entry else username
            }
        except Exception as e:
            print(f"Erro LDAP: {e}")
            return None