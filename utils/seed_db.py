# seed_db.py
import os
from dotenv import load_dotenv

# 1. Carrega as variáveis do arquivo .env antes de qualquer outra coisa
load_dotenv()

from app import create_app
from app.extensions import db, bcrypt
from app.models import ServiceTemplate, User, ResourceQuota

app = create_app()

def seed():
    """
    Popula o banco de dados com dados iniciais para teste.
    ATENÇÃO: Isso apagará todos os dados existentes no banco configurado!
    """
    with app.app_context():
        print("🌱 Iniciando o Seed do Banco de Dados...")
        
        # Verifica se a URL do banco foi carregada corretamente
        db_url = app.config.get('SQLALCHEMY_DATABASE_URI')
        if 'nubemox_user' not in db_url:
            print(f"⚠️ AVISO: Parece que a string de conexão está usando o padrão incorreto.")
            print(f"   URL atual: {db_url}")
            print("   Verifique se o arquivo .env está correto e sendo carregado.")
        
        # 1. Limpar e Recriar Schema do Banco
        db.drop_all()
        db.create_all()
        print("   ✅ Tabelas recriadas (Schema limpo).")

        # 2. Criar Usuário Admin Demo
        print("   👤 Criando usuário admin...")
        admin = User(
            username='admin', 
            email='admin@nubemox.local', 
            is_admin=True, 
            proxmox_pool='vps-admin',
            is_active=True
        )
        admin.set_password('admin123')
        
        # Definir Cota generosa para o admin
        quota = ResourceQuota(
            user=admin, 
            max_vms=20, 
            max_cpu_cores=40, 
            max_memory_mb=32768, 
            max_storage_gb=500
        )
        
        db.session.add(admin)
        db.session.add(quota)

        # 3. Criar Templates de Serviço
        
        # --- Template A: ARQUIVO (File/ISO) ---
        print("   📦 Cadastrando Template: Debian 12 (Modo: FILE)...")
        tmpl_debian = ServiceTemplate(
            name="Debian 12 Standard",
            type="lxc",
            deploy_mode="file",
            proxmox_template_volid="local:vztmpl/debian-12-standard_12.2-1_amd64.tar.zst",
            description="Container limpo, instalação mínima (Padrão do Sistema).",
            logo_url="https://www.debian.org/logos/openlogo-nd-50.png"
        )

        # --- Template B: CLONE (CT Pré-configurado) ---
        print("   📦 Cadastrando Template: LAMP Stack (Modo: CLONE ID 9000)...")
        tmpl_lamp = ServiceTemplate(
            name="Servidor Web LAMP",
            type="lxc",
            deploy_mode="clone",
            proxmox_template_volid="9000", 
            description="Apache, MySQL e PHP. Hardware definido pelo template original.",
            logo_url="https://upload.wikimedia.org/wikipedia/commons/thumb/2/27/PHP-logo.svg/711px-PHP-logo.svg.png"
        )
        
        # --- Template C: CLONE (VM QEMU) ---
        print("   📦 Cadastrando Template: Ubuntu Server VM (Modo: CLONE ID 9001)...")
        tmpl_ubuntu_vm = ServiceTemplate(
            name="Ubuntu 22.04 VM",
            type="qemu",
            deploy_mode="clone",
            proxmox_template_volid="9001",
            description="Máquina Virtual completa (KVM).",
            logo_url="https://assets.ubuntu.com/v1/29985a98-ubuntu-logo32.png"
        )

        db.session.add(tmpl_debian)
        db.session.add(tmpl_lamp)
        db.session.add(tmpl_ubuntu_vm)
        
        db.session.commit()
        print("✨ Banco de dados populado com sucesso!")
        print("=========================================")
        print("   -> Usuário: admin / admin123")
        print(f"   -> Template 1: {tmpl_debian.name} (ID: {tmpl_debian.id})")
        print(f"   -> Template 2: {tmpl_lamp.name} (ID: {tmpl_lamp.id})")
        print("=========================================")

if __name__ == '__main__':
    seed()