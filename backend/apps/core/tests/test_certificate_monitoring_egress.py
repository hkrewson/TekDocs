from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from apps.core import certificate_monitoring_egress as collector


class FakeTLS:
    def __init__(self, certificate: bytes, chain: list[bytes] | None = None):
        self.certificate = certificate
        self.chain = chain or [certificate]

    def get_unverified_chain(self):  # type: ignore[no-untyped-def]
        return self.chain

    def version(self):
        return "TLSv1.3"

    def cipher(self):
        return ("TLS_AES_256_GCM_SHA384", "TLSv1.3", 256)

    def close(self):
        return None


def _certificate(hostname: str, *, sans: list[str] | None = None) -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(value) for value in (sans or [hostname])]), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    return certificate.public_bytes(serialization.Encoding.DER)


def test_certificate_collection_pins_public_address_and_reduces_evidence(monkeypatch):
    certificate = _certificate("www.example.com")
    calls: list[tuple[str, bool]] = []

    def handshake(**kwargs):  # type: ignore[no-untyped-def]
        calls.append((kwargs["address"], kwargs["verify"]))
        return certificate, FakeTLS(certificate)

    monkeypatch.setattr(collector, "_handshake", handshake)
    evidence = collector.collect_certificate_evidence(
        "www.example.com",
        "https",
        resolver=lambda *_args, **_kwargs: [(None, None, None, None, ("93.184.216.34", 443))],
    )
    assert calls == [("93.184.216.34", False), ("93.184.216.34", True)]
    assert evidence.hostname_valid is True
    assert evidence.trust_valid is True
    assert evidence.chain_length == 1
    assert evidence.san_count == 1
    assert len(evidence.leaf_sha256) == 64


def test_certificate_collection_rejects_private_answers_before_connecting():
    with pytest.raises(collector.CertificateCollectionError, match="certificate_destination_not_public"):
        collector.collect_certificate_evidence(
            "internal.example.com",
            "https",
            resolver=lambda *_args, **_kwargs: [(None, None, None, None, ("127.0.0.1", 443))],
        )


def test_certificate_protocols_are_fixed_and_wildcards_match_one_label():
    assert collector.protocol_port("https") == 443
    assert collector.protocol_port("smtps") == 465
    assert collector._dnsname_matches("*.example.com", "mail.example.com")
    assert not collector._dnsname_matches("*.example.com", "nested.mail.example.com")
    assert collector._dnsname_matches("*.bücher.example", "shop.xn--bcher-kva.example")
    assert not collector._dnsname_matches("*.*.example.com", "mail.dev.example.com")
    with pytest.raises(collector.CertificateCollectionError, match="certificate_protocol_invalid"):
        collector.protocol_port("starttls")


def test_certificate_collection_rejects_unbounded_chain_and_san_metadata(monkeypatch):
    certificate = _certificate("www.example.com")
    with pytest.raises(collector.CertificateCollectionError, match="certificate_chain_too_large"):
        collector._presented_chain(FakeTLS(certificate, [b"x" * (collector.MAX_CERTIFICATE_BYTES + 1)]), certificate)

    oversized_sans = [f"host-{index}.example.com" for index in range(collector.MAX_SAN_NAMES + 1)]
    oversized_certificate = _certificate("www.example.com", sans=oversized_sans)
    monkeypatch.setattr(
        collector,
        "_handshake",
        lambda **_kwargs: (oversized_certificate, FakeTLS(oversized_certificate)),
    )
    with pytest.raises(collector.CertificateCollectionError, match="certificate_san_invalid"):
        collector.collect_certificate_evidence(
            "www.example.com",
            "https",
            resolver=lambda *_args, **_kwargs: [(None, None, None, None, ("93.184.216.34", 443))],
        )
