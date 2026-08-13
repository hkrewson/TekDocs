from __future__ import annotations

import hashlib
import ipaddress
import socket
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from cryptography import x509
from cryptography.x509.oid import NameOID

from .approved_egress import ApprovedEgressError, is_public_address

PROTOCOL_PORTS = {"https": 443, "smtps": 465, "imaps": 993, "pop3s": 995}
CONNECT_TIMEOUT_SECONDS = 5.0
MAX_CERTIFICATE_BYTES = 64 * 1024
MAX_CHAIN_BYTES = 1024 * 1024
MAX_SAN_NAMES = 500


class CertificateCollectionError(ApprovedEgressError):
    pass


@dataclass(frozen=True, slots=True)
class CollectedCertificateEvidence:
    leaf_sha256: str
    chain_sha256: str
    chain_length: int
    subject_common_name: str
    issuer_common_name: str
    serial_sha256: str
    san_sha256: str
    san_count: int
    not_before: datetime
    not_after: datetime
    hostname_valid: bool
    trust_valid: bool
    tls_version: str
    cipher_name: str


Resolver = Callable[..., list[Any]]
ConnectionFactory = Callable[..., socket.socket]


def _ascii_dns_name(value: str, *, allow_wildcard: bool = False) -> str:
    candidate = value.strip().rstrip(".").lower()
    wildcard = allow_wildcard and candidate.startswith("*.")
    if wildcard:
        candidate = candidate[2:]
    try:
        normalized = candidate.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise CertificateCollectionError("certificate_hostname_invalid") from exc
    labels = normalized.split(".")
    if (
        not normalized
        or len(normalized) > 253
        or len(labels) < 2
        or any(
            not label
            or len(label) > 63
            or label.startswith("-")
            or label.endswith("-")
            or not label.replace("-", "").isalnum()
            for label in labels
        )
    ):
        raise CertificateCollectionError("certificate_hostname_invalid")
    return f"*.{normalized}" if wildcard else normalized


def protocol_port(protocol: str) -> int:
    try:
        return PROTOCOL_PORTS[protocol]
    except KeyError as exc:
        raise CertificateCollectionError("certificate_protocol_invalid") from exc


def _public_address(hostname: str, port: int, resolver: Resolver) -> str:
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise CertificateCollectionError("certificate_hostname_invalid")
    try:
        answers = resolver(hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise CertificateCollectionError("certificate_dns_unavailable") from exc
    addresses = sorted({str(answer[4][0]) for answer in answers})
    if not addresses or any(not is_public_address(address) for address in addresses):
        raise CertificateCollectionError("certificate_destination_not_public")
    return addresses[0]


def _context(*, verify: bool, hostname_check: bool, protocol: str) -> ssl.SSLContext:
    context = ssl.create_default_context() if verify else ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    if not verify:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    else:
        context.check_hostname = hostname_check
    if protocol == "https":
        context.set_alpn_protocols(["h2", "http/1.1"])
    return context


def _handshake(
    *,
    address: str,
    hostname: str,
    port: int,
    protocol: str,
    verify: bool,
    hostname_check: bool,
    connection_factory: ConnectionFactory,
) -> tuple[bytes, ssl.SSLSocket]:
    raw = connection_factory((address, port), timeout=CONNECT_TIMEOUT_SECONDS)
    try:
        tls = _context(verify=verify, hostname_check=hostname_check, protocol=protocol).wrap_socket(
            raw, server_hostname=hostname
        )
        leaf = tls.getpeercert(binary_form=True)
        if not leaf:
            tls.close()
            raise CertificateCollectionError("certificate_missing")
        if len(leaf) > MAX_CERTIFICATE_BYTES:
            tls.close()
            raise CertificateCollectionError("certificate_too_large")
        return leaf, tls
    except Exception:
        raw.close()
        raise


def _common_name(name: x509.Name) -> str:
    values = name.get_attributes_for_oid(NameOID.COMMON_NAME)
    return str(values[0].value)[:253] if values else ""


def _presented_chain(tls: ssl.SSLSocket, leaf_der: bytes) -> tuple[str, int]:
    try:
        chain = tls.get_unverified_chain()
    except (AttributeError, ssl.SSLError):
        chain = []
    encoded: list[bytes] = []
    encoded_size = 0
    for certificate in chain[:20]:
        if isinstance(certificate, bytes):
            raw_value = certificate
        else:
            value = certificate.public_bytes()
            raw_value = value.encode() if isinstance(value, str) else value
        encoded_size += len(raw_value)
        if len(raw_value) > MAX_CERTIFICATE_BYTES or encoded_size > MAX_CHAIN_BYTES:
            raise CertificateCollectionError("certificate_chain_too_large")
        encoded.append(raw_value)
    if not encoded:
        encoded = [leaf_der]
    digests = b"".join(hashlib.sha256(item).digest() for item in encoded)
    return hashlib.sha256(digests).hexdigest(), len(encoded)


def _dnsname_matches(pattern: str, hostname: str) -> bool:
    try:
        expected = _ascii_dns_name(pattern, allow_wildcard=True)
        actual = _ascii_dns_name(hostname)
    except CertificateCollectionError:
        return False
    if "*" not in expected:
        return expected == actual
    if not expected.startswith("*.") or expected.count("*") != 1:
        return False
    return actual.count(".") == expected.count(".") and actual.endswith(expected[1:])


def collect_certificate_evidence(
    hostname: str,
    protocol: str,
    *,
    resolver: Resolver = socket.getaddrinfo,
    connection_factory: ConnectionFactory = socket.create_connection,
) -> CollectedCertificateEvidence:
    hostname = _ascii_dns_name(hostname)
    port = protocol_port(protocol)
    address = _public_address(hostname, port, resolver)
    try:
        leaf_der, unverified = _handshake(
            address=address,
            hostname=hostname,
            port=port,
            protocol=protocol,
            verify=False,
            hostname_check=False,
            connection_factory=connection_factory,
        )
        try:
            chain_sha256, chain_length = _presented_chain(unverified, leaf_der)
            tls_version = unverified.version() or ""
            cipher = unverified.cipher()
            cipher_name = cipher[0] if cipher else ""
        finally:
            unverified.close()
        certificate = x509.load_der_x509_certificate(leaf_der)
        try:
            raw_sans: list[str] = list(
                certificate.extensions.get_extension_for_class(
                    x509.SubjectAlternativeName
                ).value.get_values_for_type(x509.DNSName)
            )
            if len(raw_sans) > MAX_SAN_NAMES or any(len(value) > 253 for value in raw_sans):
                raise CertificateCollectionError("certificate_san_invalid")
            sans = sorted(_ascii_dns_name(san_value, allow_wildcard=True) for san_value in raw_sans)
        except x509.ExtensionNotFound:
            sans = []
        subject_common_name = _common_name(certificate.subject)
        names = sans or ([subject_common_name] if subject_common_name else [])
        hostname_valid = any(_dnsname_matches(pattern, hostname) for pattern in names)
        trust_valid = False
        trusted_leaf: bytes | None = None
        try:
            trusted_leaf, trusted = _handshake(
                address=address,
                hostname=hostname,
                port=port,
                protocol=protocol,
                verify=True,
                hostname_check=False,
                connection_factory=connection_factory,
            )
            trusted.close()
            trust_valid = True
        except ssl.SSLCertVerificationError:
            pass
        if trust_valid:
            if trusted_leaf != leaf_der:
                raise CertificateCollectionError("certificate_changed_during_scan")
        return CollectedCertificateEvidence(
            leaf_sha256=hashlib.sha256(leaf_der).hexdigest(),
            chain_sha256=chain_sha256,
            chain_length=chain_length,
            subject_common_name=subject_common_name,
            issuer_common_name=_common_name(certificate.issuer),
            serial_sha256=hashlib.sha256(str(certificate.serial_number).encode()).hexdigest(),
            san_sha256=hashlib.sha256("\0".join(sans).encode()).hexdigest(),
            san_count=len(sans),
            not_before=certificate.not_valid_before_utc.astimezone(UTC),
            not_after=certificate.not_valid_after_utc.astimezone(UTC),
            hostname_valid=hostname_valid,
            trust_valid=trust_valid,
            tls_version=tls_version[:32],
            cipher_name=cipher_name[:64],
        )
    except CertificateCollectionError:
        raise
    except (OSError, ssl.SSLError, ValueError) as exc:
        raise CertificateCollectionError("certificate_connection_failed") from exc
