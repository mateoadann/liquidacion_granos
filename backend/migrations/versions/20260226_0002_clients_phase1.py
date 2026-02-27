"""Evolve taxpayer table for client phase 1

Revision ID: 20260226_0002
Revises: 20260225_0001
Create Date: 2026-02-26 10:00:00.000000

"""

import base64
import hashlib
import os

from alembic import op
from cryptography.fernet import Fernet
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260226_0002"
down_revision = "20260225_0001"
branch_labels = None
depends_on = None


def _build_fernet_from_env() -> Fernet:
    raw_key = os.getenv("CLIENT_SECRET_KEY") or os.getenv("SECRET_KEY") or "dev-secret"
    raw_bytes = raw_key.encode("utf-8")

    try:
        return Fernet(raw_bytes)
    except Exception:
        derived_key = base64.urlsafe_b64encode(hashlib.sha256(raw_bytes).digest())
        return Fernet(derived_key)


def upgrade():
    op.add_column("taxpayer", sa.Column("empresa", sa.String(length=255), nullable=True))
    op.add_column(
        "taxpayer", sa.Column("cuit_representado", sa.String(length=11), nullable=True)
    )
    op.add_column(
        "taxpayer", sa.Column("clave_fiscal_encrypted", sa.Text(), nullable=True)
    )
    op.add_column("taxpayer", sa.Column("cert_crt_path", sa.Text(), nullable=True))
    op.add_column("taxpayer", sa.Column("cert_key_path", sa.Text(), nullable=True))
    op.add_column(
        "taxpayer", sa.Column("cert_crt_filename", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "taxpayer", sa.Column("cert_key_filename", sa.String(length=255), nullable=True)
    )
    op.add_column("taxpayer", sa.Column("cert_uploaded_at", sa.DateTime(), nullable=True))
    op.add_column(
        "taxpayer",
        sa.Column(
            "playwright_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )

    encrypted_placeholder = _build_fernet_from_env().encrypt(
        b"PENDIENTE_ACTUALIZACION_UI"
    ).decode("utf-8")

    op.execute(
        sa.text(
            """
            UPDATE taxpayer
               SET empresa = COALESCE(NULLIF(razon_social, ''), 'Sin empresa')
             WHERE empresa IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE taxpayer
               SET cuit_representado = cuit
             WHERE cuit_representado IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE taxpayer
               SET clave_fiscal_encrypted = :placeholder
             WHERE clave_fiscal_encrypted IS NULL
            """
        ).bindparams(placeholder=encrypted_placeholder)
    )

    op.alter_column("taxpayer", "empresa", existing_type=sa.String(255), nullable=False)
    op.alter_column(
        "taxpayer",
        "cuit_representado",
        existing_type=sa.String(11),
        nullable=False,
    )
    op.alter_column(
        "taxpayer",
        "clave_fiscal_encrypted",
        existing_type=sa.Text(),
        nullable=False,
    )


def downgrade():
    op.drop_column("taxpayer", "playwright_enabled")
    op.drop_column("taxpayer", "cert_uploaded_at")
    op.drop_column("taxpayer", "cert_key_filename")
    op.drop_column("taxpayer", "cert_crt_filename")
    op.drop_column("taxpayer", "cert_key_path")
    op.drop_column("taxpayer", "cert_crt_path")
    op.drop_column("taxpayer", "clave_fiscal_encrypted")
    op.drop_column("taxpayer", "cuit_representado")
    op.drop_column("taxpayer", "empresa")
