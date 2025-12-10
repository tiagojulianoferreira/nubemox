# app/services/ldap_service.py
from ldap3 import Server, Connection, ALL, BASE
from flask import current_app

class LDAPService:
    def authenticate(self, username, password):
        """
        Valida credenciais no LDAP e retorna os dados do utilizador.
        Retorna None se falhar.
        """
        # 1. Configurações
        ldap_server = current_app.config.get('LDAP_SERVER')
        
        # Monta o DN do utilizador (Ex: cn=tiago,ou=users,dc=nubemox...)
        # Assume que o template no config é: 'cn={},ou=users,dc=nubemox,dc=local'
        user_dn = current_app.config.get('LDAP_USER_DN_TEMPLATE').format(username)
        
        try:
            # 2. Tenta Conectar e Autenticar (Bind)
            server = Server(ldap_server, get_info=ALL)
            conn = Connection(server, user=user_dn, password=password, auto_bind=True)
            
            # Se não lançou exceção, a senha está correta.
            
            # 3. Buscar detalhes do utilizador (Email, Nome)
            # Usamos search_base=user_dn para buscar o próprio objeto
            conn.search(
                search_base=user_dn,
                search_filter='(objectClass=*)',
                search_scope=BASE,
                attributes=['mail', 'cn', 'uid']
            )
            
            user_data = {
                'username': username,
                'email': f"{username}@local", # Fallback
                'fullname': username
            }
            
            if conn.entries:
                entry = conn.entries[0]
                # Extrai dados se existirem, senão usa fallback
                if 'mail' in entry: user_data['email'] = str(entry.mail)
                if 'cn' in entry: user_data['fullname'] = str(entry.cn)
                
            conn.unbind()
            return user_data

        except Exception as e:
            # Log de erro (print por enquanto)
            print(f"Falha de Autenticação LDAP para {username}: {str(e)}")
            return None