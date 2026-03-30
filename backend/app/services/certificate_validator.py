from __future__ import annotations

from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization


class CertificateValidationError(ValueError):
    """Error funcional para validacion de certificados."""


def _load_certificate(cert_bytes: bytes) -> x509.Certificate:
    try:
        return x509.load_pem_x509_certificate(cert_bytes)
    except ValueError:
        try:
            return x509.load_der_x509_certificate(cert_bytes)
        except ValueError as exc:
            raise CertificateValidationError("No se pudo parsear el certificado .crt.") from exc


def _load_private_key(key_bytes: bytes):
    try:
        return serialization.load_pem_private_key(key_bytes, password=None)
    except TypeError as exc:
        raise CertificateValidationError(
            "La private key esta cifrada y requiere passphrase."
        ) from exc
    except ValueError:
        try:
            return serialization.load_der_private_key(key_bytes, password=None)
        except TypeError as exc:
            raise CertificateValidationError(
                "La private key esta cifrada y requiere passphrase."
            ) from exc
        except ValueError as exc:
            raise CertificateValidationError("No se pudo parsear la private key.") from exc


def validate_certificate_and_key(cert_bytes: bytes, key_bytes: bytes) -> None:
    if not cert_bytes:
        raise CertificateValidationError("El archivo cert_file esta vacio.")
    if not key_bytes:
        raise CertificateValidationError("El archivo key_file esta vacio.")

    certificate = _load_certificate(cert_bytes)
    private_key = _load_private_key(key_bytes)

    cert_public_der = certificate.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    key_public_der = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    if cert_public_der != key_public_der:
        raise CertificateValidationError(
            "El certificado y la private key no corresponden al mismo par criptografico."
        )


def validate_certificate_and_key_paths(cert_path: str, key_path: str) -> None:
    cert_file = Path(cert_path)
    key_file = Path(key_path)

    if not cert_file.is_file() or not key_file.is_file():
        raise CertificateValidationError("No se encontraron los certificados en filesystem.")

    validate_certificate_and_key(cert_file.read_bytes(), key_file.read_bytes())
