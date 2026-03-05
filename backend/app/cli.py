from __future__ import annotations

import click
from flask import Flask

from .extensions import db
from .models import User
from .services.auth_service import hash_password


def register_cli(app: Flask) -> None:
    @app.cli.command("create-admin")
    @click.option("--username", required=True, help="Username del admin")
    @click.option("--password", required=True, help="Password del admin (min 8 chars)")
    @click.option("--nombre", required=True, help="Nombre completo del admin")
    def create_admin(username: str, password: str, nombre: str):
        """Crea el usuario administrador inicial."""
        if len(password) < 8:
            click.echo("Error: El password debe tener al menos 8 caracteres", err=True)
            raise SystemExit(1)

        existing_admin = User.query.filter_by(rol="admin").first()
        if existing_admin:
            click.echo(f"Error: Ya existe un admin: {existing_admin.username}", err=True)
            raise SystemExit(1)

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            click.echo(f"Error: Ya existe un usuario con username: {username}", err=True)
            raise SystemExit(1)

        user = User()
        user.username = username
        user.password_hash = hash_password(password)
        user.nombre = nombre
        user.rol = "admin"
        user.activo = True

        db.session.add(user)
        db.session.commit()

        click.echo(f"Admin creado exitosamente: {username}")
