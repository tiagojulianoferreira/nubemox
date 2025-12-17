# init_groups.py
import os
from dotenv import load_dotenv

# Força o carregamento do .env antes de qualquer importação do app
load_dotenv() 

from app import create_app
from app.extensions import db
from app.models.user import UserGroup

app = create_app()

with app.app_context():
    print(f"--- Conectando com usuário: {os.getenv('POSTGRES_USER') or os.getenv('DATABASE_URL')} ---")
    print("--- Inicializando Grupos de Usuários ---")
    
    # Cria as tabelas novas se não existirem
    db.create_all()

    # Definição dos Grupos Iniciais
    groups = [
        {
            'name': 'Alunos', 
            'desc': 'Recursos limitados, disco local HDD',
            'storage': 'local-lvm',
            'bridge': 'vmbr0',
            'vlan': None,
            'cpu': 2, 'ram': 2048, 'disk': 20, 'vms': 2
        },
        {
            'name': 'Docentes', 
            'desc': 'Alta performance, disco SSD/NVMe',
            'storage': 'local-lvm',
            'bridge': 'vmbr0',
            'vlan': None,
            'cpu': 8, 'ram': 16384, 'disk': 100, 'vms': 10
        },
        {
            'name': 'Admins', 
            'desc': 'Acesso irrestrito',
            'storage': 'local-lvm', 
            'bridge': 'vmbr0',
            'vlan': None,
            'cpu': 32, 'ram': 64000, 'disk': 500, 'vms': 50
        }
    ]

    for g_data in groups:
        # Verifica se já existe para não duplicar
        existing = UserGroup.query.filter_by(name=g_data['name']).first()
        if not existing:
            new_group = UserGroup(
                name=g_data['name'],
                description=g_data['desc'],
                default_storage_pool=g_data['storage'],
                default_network_bridge=g_data['bridge'],
                default_vlan_tag=g_data['vlan'],
                max_cpu=g_data['cpu'],
                max_memory=g_data['ram'],
                max_storage=g_data['disk'],
                max_vms=g_data['vms']
            )
            db.session.add(new_group)
            print(f"Grupo criado: {g_data['name']}")
        else:
            print(f"Grupo já existe: {g_data['name']}")

    db.session.commit()
    print("--- Concluído ---")