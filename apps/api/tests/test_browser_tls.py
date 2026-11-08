"""Fixture TLS verification never changes application trust or database state."""

import hashlib
from pathlib import Path

import pytest
from browser_tls import generate
from cryptography import x509
from cryptography.hazmat.primitives.serialization import load_pem_private_key


def test_fixture_certificate_is_ca_signed_and_bound_to_loopback(tmp_path: Path) -> None:
    generate(tmp_path)
    ca = x509.load_pem_x509_certificate((tmp_path / "ca.pem").read_bytes())
    certificate = x509.load_pem_x509_certificate((tmp_path / "server.pem").read_bytes())
    certificate.verify_directly_issued_by(ca)
    assert ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    assert not certificate.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    names = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert [str(item) for item in names.get_values_for_type(x509.IPAddress)] == ["127.0.0.1"]
    assert names.get_values_for_type(x509.DNSName) == []
    key = load_pem_private_key((tmp_path / "server.key").read_bytes(), password=None)
    assert key is not None
    assert {path.name for path in tmp_path.iterdir()} == {"ca.pem", "server.pem", "server.key"}
    fingerprints = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in tmp_path.iterdir()
    }
    with pytest.raises(FileExistsError):
        generate(tmp_path)
    assert fingerprints == {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in tmp_path.iterdir()
    }
