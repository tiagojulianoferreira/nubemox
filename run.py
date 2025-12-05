#!/usr/bin/env python3
import os
import urllib.parse
from flask import url_for
from app import create_app
from app.config import DevelopmentConfig

app = create_app(DevelopmentConfig)

def list_routes():
    output = []
    for rule in app.url_map.iter_rules():
        methods = ','.join(rule.methods)
        line = urllib.parse.unquote(f"{rule.endpoint:35s} {methods:20s} {rule}")
        output.append(line)
    
    print("\n🚀 Nubemox Backend Rodando!")
    print("===========================")
    print("Rotas Ativas:")
    for line in sorted(output):
        print(line)
    print("===========================\n")

if __name__ == '__main__':
    # Em modo debug, o reloader pode duplicar o print, mas é útil
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        list_routes()
    app.run(host='0.0.0.0', port=5000)