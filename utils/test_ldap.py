# utils/test_ldap.py
from ldap3 import Server, Connection, ALL, BASE

# Configurações
LDAP_SERVER = 'ldap://localhost:389'
USER_DN = 'cn=tiago,ou=users,dc=nubemox,dc=local' # DN Completo
LDAP_PASS = '123456'

print(f"Tentando conectar e autenticar: {USER_DN}...")

server = Server(LDAP_SERVER, get_info=ALL)
conn = Connection(server, user=USER_DN, password=LDAP_PASS)

if not conn.bind():
    print("FALHA no Bind! Credenciais inválidas.")
else:
    print("SUCESSO! Senha correta.")
    print(f"   WhoAmI: {conn.extend.standard.who_am_i()}")
    
    # --- BUSCA CORRIGIDA ---
    # Estratégia: Buscar o PRÓPRIO objeto (SCOPE_BASE) em vez de varrer a pasta.
    # Isso evita problemas de permissão e performance.
    
    print(f"🔍 Buscando atributos de: {USER_DN}")
    
    conn.search(
        search_base=USER_DN,        # Busca exatamente este objeto
        search_filter='(objectClass=*)', # Pega qualquer classe de objeto
        search_scope=BASE,          # Escopo: Apenas o objeto base
        attributes=['mail', 'uid', 'cn', 'sn'] # O que queremos trazer
    )
    
    if conn.entries:
        entry = conn.entries[0]
        print(f"   Dados recuperados com sucesso:")
        print(f"      - Nome: {entry.cn}")
        print(f"      - Email: {entry.mail}")
        print(f"      - UID: {entry.uid}")
        print(f"      - Raw Entry: {entry}")
    else:
        print("A busca não retornou resultados.")
        print(f"   Detalhes do erro LDAP: {conn.result}")

conn.unbind()