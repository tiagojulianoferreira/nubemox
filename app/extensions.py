from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from flask_login import LoginManager
from flask_jwt_extended import JWTManager
from flask_bcrypt import Bcrypt

# Inicialização das extensões
# Nota: A vinculação com o app (init_app) é feita no __init__.py
db = SQLAlchemy()
migrate = Migrate()
cors = CORS()
login_manager = LoginManager()
jwt = JWTManager()     # Necessário para autenticação via Token (API)
bcrypt = Bcrypt()      # Necessário para hash de senhas