from flask import Blueprint

bp = Blueprint('proxmox', __name__)

from app.api.proxmox import routes