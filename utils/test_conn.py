# test_conn.py
import psycopg2
import os

# Defina aqui exatamente o que está no seu .env
# DATABASE_URL=postgresql://nubemox_user:nubemox_password@localhost:5432/nubemox_dev

DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "nubemox_dev"
DB_USER = "nubemox_user"
DB_PASS = "nubemox_password" # <--- A senha que você quer testar

try:
    print(f"🔌 Tentando conectar a {DB_HOST}...")
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )
    print("✅ SUCESSO! A senha está correta e a conexão foi estabelecida.")
    conn.close()
except Exception as e:
    print("\n❌ ERRO DE CONEXÃO:")
    print(e)