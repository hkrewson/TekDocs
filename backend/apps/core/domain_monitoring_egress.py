from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

import urllib3
from django.conf import settings
from urllib3.exceptions import HTTPError

from .approved_egress import ApprovedEgressError, pinned_https_pool, resolve_public_https_target

MAX_MONITOR_RESPONSE_BYTES = 512 * 1024
DNS_TYPES = ("A", "AAAA", "MX", "NS", "CAA")


class DomainCollectionError(ApprovedEgressError):
    pass


@dataclass(frozen=True, slots=True)
class DNSAnswer:
    record_type: str
    value: str
    ttl: int | None


@dataclass(frozen=True, slots=True)
class CollectedDomainEvidence:
    rdap_source: str
    rdap_digest: str
    expiration_date: date | None
    registrar: str
    dns_source: str
    dns_digest: str
    dnssec_validated: bool | None
    dns_answers: tuple[DNSAnswer, ...]


def _get_json(url: str, *, accept: str) -> dict[str, Any]:
    target = resolve_public_https_target(url, label="Domain monitoring", allow_query=True)
    pool = pinned_https_pool(
        target,
        connect_timeout=3.0,
        read_timeout=10.0,
        pool_factory=urllib3.HTTPSConnectionPool,
    )
    try:
        response = pool.urlopen(
            "GET",
            target.path,
            headers={"Host": target.hostname, "Accept": accept, "User-Agent": "TekDocs-domain-monitor/1"},
            redirect=False,
            assert_same_host=False,
            preload_content=False,
        )
        if response.status != 200:
            response.close()
            raise DomainCollectionError("monitor_http_error")
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type not in {"application/json", "application/rdap+json", "application/dns-json"}:
            response.close()
            raise DomainCollectionError("monitor_content_type_invalid")
        body = response.read(MAX_MONITOR_RESPONSE_BYTES + 1)
        response.close()
        if len(body) > MAX_MONITOR_RESPONSE_BYTES:
            raise DomainCollectionError("monitor_response_too_large")
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise DomainCollectionError("monitor_response_invalid")
        return payload
    except (HTTPError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DomainCollectionError("monitor_connection_failed") from exc
    finally:
        pool.close()


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def _rdap_date(payload: dict[str, Any]) -> date | None:
    for event in payload.get("events", []):
        if not isinstance(event, dict) or str(event.get("eventAction", "")).lower() not in {
            "expiration",
            "expiry",
            "registration expiration",
        }:
            continue
        value = event.get("eventDate")
        if not isinstance(value, str):
            continue
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            continue
    return None


def _rdap_registrar(payload: dict[str, Any]) -> str:
    for entity in payload.get("entities", []):
        if not isinstance(entity, dict) or "registrar" not in entity.get("roles", []):
            continue
        vcard = entity.get("vcardArray")
        if not isinstance(vcard, list) or len(vcard) != 2 or not isinstance(vcard[1], list):
            continue
        for item in vcard[1]:
            if isinstance(item, list) and len(item) >= 4 and item[0] == "fn" and isinstance(item[3], str):
                return item[3].strip()[:240]
    return ""


def _doh_answers(payload: dict[str, Any], expected_type: str) -> tuple[list[DNSAnswer], bool | None]:
    answers: list[DNSAnswer] = []
    for answer in payload.get("Answer", []):
        if not isinstance(answer, dict) or len(answers) >= 100:
            continue
        value = answer.get("data")
        ttl = answer.get("TTL")
        if not isinstance(value, str) or not value.strip() or len(value) > 1_024:
            continue
        answers.append(DNSAnswer(expected_type, value.strip(), ttl if isinstance(ttl, int) and ttl >= 0 else None))
    validated = payload.get("AD")
    return answers, validated if isinstance(validated, bool) else None


def collect_domain_evidence(ascii_name: str) -> CollectedDomainEvidence:
    bootstrap = _get_json(settings.TEKDOCS_RDAP_BOOTSTRAP_URL, accept="application/json")
    tld = ascii_name.rsplit(".", 1)[-1]
    rdap_base = ""
    for service in bootstrap.get("services", []):
        if (
            isinstance(service, list)
            and len(service) == 2
            and isinstance(service[0], list)
            and tld in service[0]
            and isinstance(service[1], list)
            and service[1]
            and isinstance(service[1][0], str)
        ):
            rdap_base = service[1][0].rstrip("/")
            break
    if not rdap_base:
        raise DomainCollectionError("rdap_service_unavailable")
    rdap_url = f"{rdap_base}/domain/{quote(ascii_name, safe='')}"
    rdap = _get_json(rdap_url, accept="application/rdap+json, application/json")

    doh_base = settings.TEKDOCS_DOH_URL
    parsed_doh = urlsplit(doh_base)
    separator = "&" if parsed_doh.query else "?"
    answers: list[DNSAnswer] = []
    validations: list[bool] = []
    for record_type in DNS_TYPES:
        query_url = f"{doh_base}{separator}{urlencode({'name': ascii_name, 'type': record_type, 'do': '1'})}"
        records, validated = _doh_answers(_get_json(query_url, accept="application/dns-json"), record_type)
        answers.extend(records)
        if validated is not None:
            validations.append(validated)
    canonical_dns = sorted((item.record_type, item.value, item.ttl) for item in answers)
    return CollectedDomainEvidence(
        rdap_source=urlsplit(rdap_base).hostname or "rdap",
        rdap_digest=_digest(rdap),
        expiration_date=_rdap_date(rdap),
        registrar=_rdap_registrar(rdap),
        dns_source=urlsplit(doh_base).hostname or "doh",
        dns_digest=_digest(canonical_dns),
        dnssec_validated=all(validations) if validations else None,
        dns_answers=tuple(answers),
    )
