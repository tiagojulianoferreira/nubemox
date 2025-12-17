from app.extensions import db
from datetime import datetime

class SystemSetting(db.Model):
    __tablename__ = 'system_settings'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False) # ex: 'default_quota_cpu'
    value = db.Column(db.String(255), nullable=False) # ex: '2'
    description = db.Column(db.String(255))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get_value(key, default=None):
        """Retorna o valor cru (string)."""
        setting = SystemSetting.query.filter_by(key=key).first()
        if setting:
            return setting.value
        return default

    @staticmethod
    def get_int(key, default=0):
        """
        NOVO MÉTODO: Retorna o valor convertido para Inteiro.
        Necessário para o cálculo de cotas no user.py.
        """
        val = SystemSetting.get_value(key)
        if val is None:
            return default
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def set_value(key, value, description=None):
        """Define ou atualiza um valor."""
        setting = SystemSetting.query.filter_by(key=key).first()
        if not setting:
            setting = SystemSetting(key=key, value=str(value), description=description)
            db.session.add(setting)
        else:
            setting.value = str(value)
            if description:
                setting.description = description
        db.session.commit()