import click
from flask.cli import with_appcontext
from app.extensions import db
from sqlalchemy import text
from app.models import User, ServiceTemplate, VirtualResource, UserQuota # <--- Importar UserQuota

@click.command('init-db')
@with_appcontext
def init_db_command():
    """Limpa as tabelas existentes e cria novas (Modo Forçado)."""
    
    click.echo('🗑️  Apagando banco de dados antigo (Reset Completo)...')
    
    try:
        db.session.execute(text('DROP SCHEMA public CASCADE;'))
        db.session.execute(text('CREATE SCHEMA public;'))
        db.session.commit()
        click.echo('✅ Esquema limpo com sucesso.')
    except Exception as e:
        db.session.rollback()
        click.echo(f'⚠️ Erro ao limpar esquema: {e}')
    
    click.echo('🏗️  Criando novas tabelas...')
    db.create_all()
    
    click.echo('🌱 Semeando dados iniciais...')
    
    # --- ADMIN (Com cota ilimitada/alta) ---
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', email='admin@nubemox.local', is_admin=True)
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.flush() # Gera o ID para usar na cota
        
        # Cota de Admin (Bem generosa)
        db.session.add(UserQuota(
            user_id=admin.id,
            max_vms=100,
            max_cpu_cores=200,
            max_memory_mb=102400, # 100GB
            max_storage_gb=1000   # 1TB
        ))
    
    # --- USER COMUM (Cota padrão) ---
    if not User.query.filter_by(username='tiago').first():
        user = User(username='tiago', email='tiago@nubemox.local', is_admin=False)
        user.set_password('123456')
        db.session.add(user)
        db.session.flush()
        
        # Cota Default (2 VMs, 4GB RAM...)
        db.session.add(UserQuota(user_id=user.id))
    
    db.session.commit()
    click.echo('✅ Banco de dados reiniciado e cotas definidas! 🚀')