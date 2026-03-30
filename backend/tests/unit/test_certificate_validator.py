from __future__ import annotations

import pytest

from app.services.certificate_validator import (
    CertificateValidationError,
    validate_certificate_and_key,
)


def test_certificate_and_key_match(cert_pair_bytes):
    cert_bytes, key_bytes = cert_pair_bytes
    validate_certificate_and_key(cert_bytes, key_bytes)


def test_certificate_and_key_mismatch(cert_pair_bytes, mismatched_private_key_bytes):
    cert_bytes, _ = cert_pair_bytes

    with pytest.raises(CertificateValidationError):
        validate_certificate_and_key(cert_bytes, mismatched_private_key_bytes)
