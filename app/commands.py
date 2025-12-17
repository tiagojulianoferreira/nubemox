import click
from flask.cli import with_appcontext
from app.extensions import db
# CORREÇÃO: Removemos UserQuota e adicionamos SystemSetting
from app.models import User, ServiceTemplate, VirtualResource, SystemSetting 

@click.command('init-db')
@with_appcontext
def init_db_command():
    """Limpa as tabelas existentes e cria novas com dados iniciais."""
    
    # 1. Limpar Banco (Cuidado em produção!)
    db.drop_all()
    db.create_all()
    click.echo('Banco de dados recriado.')

    # 2. Criar Configurações Padrão do Sistema (System Settings)
    defaults = {
        'default_quota_vms': ('2', 'Máximo de VMs por usuário padrão'),
        'default_quota_cpu': ('2', 'Máximo de Cores de CPU padrão'),
        'default_quota_memory': ('2048', 'Máximo de RAM (MB) padrão'),
        'default_quota_storage': ('20', 'Máximo de Disco (GB) padrão')
    }
    
    for key, (val, desc) in defaults.items():
        SystemSetting.set_value(key, val, desc)
    click.echo('Parâmetros do sistema configurados.')

    # 3. Criar Usuário Admin
    admin = User(username='admin', email='admin@nubemox.local', is_admin=True)
    admin.set_password('admin123')
    # Admin ganha override (cota ilimitada ou maior)
    admin.quota_vms_override = 100 
    admin.quota_cpu_override = 32
    admin.quota_memory_override = 65536
    admin.quota_storage_override = 1000
    
    # 4. Criar Usuário Comum
    user = User(username='tiago', email='tiago@nubemox.local', is_admin=False)
    user.set_password('123456')
    # Usuário comum não precisa de override, usará os defaults do SystemSetting
    
    db.session.add(admin)
    db.session.add(user)
    
    # 5. Criar Templates Básicos
    # Exemplo: Debian 12 (LXC)
    tmpl_lxc = ServiceTemplate(
        name='Debian 12 (LXC)',
        type='lxc',
        proxmox_template_volid='local:vztmpl/debian-12-standard_12.0-1_amd64.tar.zst',
        description='Container leve Debian 12',
        default_cpu=1,
        default_memory=512,
        default_storage=8
    )
    
    # Exemplo: Ubuntu 22.04 (VM)
    # Nota: Para VMs, o 'proxmox_template_volid' geralmente é o ID da VM Template (ex: 9000)
    tmpl_vm = ServiceTemplate(
        name='Ubuntu 22.04 LTS',
        type='qemu',
        proxmox_template_volid='9000', 
        description='VM Completa Ubuntu Server',
        default_cpu=2,
        default_memory=2048,
        default_storage=20
    )

    db.session.add(tmpl_lxc)
    db.session.add(tmpl_vm)

    db.session.commit()
    click.echo('Usuários e Templates criados com sucesso.')