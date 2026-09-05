#!/usr/bin/env python3
"""Write and assemble value-safe, commit-bound diagram release evidence."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from check_automated_security_review import (
    COMMIT_PATTERN,
    object_value,
    reject_secret_shaped_content,
    require,
    text_value,
    timestamp,
)


REQUIRED_CHECKS = {
    "dependency_contract": {
        "chromium_build_assertion",
        "contract_file_checksums",
        "exact_dependency_pins",
        "preview_renderer_version_alignment",
    },
    "authoring_and_failures": {
        "accessible_title_and_description_required",
        "guided_markdown_round_trip",
        "oversized_output_failure",
        "oversized_source_failure",
        "parse_error_failure",
        "raster_failure",
        "renderer_timeout_failure",
        "renderer_unavailable_failure",
        "unsafe_svg_failure",
        "unsupported_directive_failure",
        "unsupported_mermaid_preserved",
    },
    "renderer_and_exports": {
        "accessible_source_fallback",
        "bounded_concurrency_and_capacity",
        "deterministic_svg_and_png",
        "html_pdf_docx_zip_carry_through",
        "network_disabled_sandbox",
        "renderer_job_cleanup",
        "retained_artifact_integrity",
        "static_fail_before_promotion",
        "supported_mermaid_families",
    },
    "browser_accessibility": {
        "axe_wcag_2_2_scan",
        "diagram_download",
        "forced_colors",
        "keyboard_source_fallback",
        "print_rendering",
        "saved_document_graphic",
        "screen_reader_semantics",
        "source_edit_round_trip",
        "wrapped_labels_and_accessible_description",
        "zoom_and_reflow",
    },
    "production_image": {
        "actual_diagram_export",
        "browser_version_matches_image_record",
        "nonroot_readonly_runtime",
        "production_renderer_health",
        "renderer_version_attribution",
    },
    "upgrade_and_restore": {
        "restored_diagram_artifact_checksums",
        "restored_signed_publication",
        "separate_database_and_media_restore",
        "versioned_diagram_source_upgrade",
    },
    "supply_chain": {
        "dependency_and_license_audit",
        "renderer_image_digest",
        "renderer_image_vulnerability_scan",
        "renderer_provenance_attestation",
        "renderer_sbom_attestation",
    },
}
REQUIRED_CATEGORIES = set(REQUIRED_CHECKS)
ALL_REQUIRED_CHECKS = set().union(*REQUIRED_CHECKS.values())
EVIDENCE_FIELDS = {
    "schema_version",
    "category",
    "status",
    "scope_commit",
    "completed_at",
    "tool",
    "tool_version",
    "reference",
    "immutable_identifier",
    "checks",
}
SHA256_IDENTIFIER = re.compile(r"^sha256:[0-9a-f]{64}$")


def build_evidence(
    *,
    category: str,
    scope_commit: str,
    tool: str,
    tool_version: str,
    reference: str,
    immutable_identifier: str,
    completed_at: str,
) -> dict[str, Any]:
    require(category in REQUIRED_CATEGORIES, f"unknown diagram evidence category: {category}")
    require(COMMIT_PATTERN.fullmatch(scope_commit) is not None, "scope commit must be an exact lowercase SHA")
    record = {
        "schema_version": 1,
        "category": category,
        "status": "passed",
        "scope_commit": scope_commit,
        "completed_at": timestamp(completed_at, "completed_at").isoformat().replace("+00:00", "Z"),
        "tool": text_value(tool, "tool", maximum=160),
        "tool_version": text_value(tool_version, "tool_version", maximum=160),
        "reference": text_value(reference, "reference", maximum=500),
        "immutable_identifier": text_value(immutable_identifier, "immutable_identifier", maximum=500),
        "checks": sorted(REQUIRED_CHECKS[category]),
    }
    if category == "dependency_contract":
        require(
            SHA256_IDENTIFIER.fullmatch(record["immutable_identifier"]) is not None,
            "dependency contract identifier must be its sha256 digest",
        )
    if category == "supply_chain":
        require(
            SHA256_IDENTIFIER.fullmatch(record["immutable_identifier"]) is not None,
            "supply-chain identifier must be the renderer image sha256 digest",
        )
    reject_secret_shaped_content(record)
    return record


def validate_evidence_entry(
    record: dict[str, Any],
    candidate_commit: str,
    *,
    name: str,
    now: datetime,
) -> tuple[str, set[str]]:
    require(record.get("schema_version") == 1, f"{name} has an unsupported or missing schema_version")
    unexpected = sorted(record.keys() - EVIDENCE_FIELDS)
    require(not unexpected, f"{name} contains unsupported fields: {', '.join(unexpected)}")
    category = text_value(record.get("category"), f"{name}.category", maximum=80)
    require(category in REQUIRED_CATEGORIES, f"unknown diagram evidence category: {category}")
    require(record.get("status") == "passed", f"diagram evidence {category} has not passed")
    require(record.get("scope_commit") == candidate_commit, f"diagram evidence {category} does not match candidate commit")
    completed_at = timestamp(record.get("completed_at"), f"diagram evidence {category}.completed_at")
    require(completed_at <= now, f"diagram evidence {category} completion is in the future")
    text_value(record.get("tool"), f"diagram evidence {category}.tool", maximum=160)
    text_value(record.get("tool_version"), f"diagram evidence {category}.tool_version", maximum=160)
    text_value(record.get("reference"), f"diagram evidence {category}.reference", maximum=500)
    identifier = text_value(
        record.get("immutable_identifier"),
        f"diagram evidence {category}.immutable_identifier",
        maximum=500,
    )
    if category in {"dependency_contract", "supply_chain"}:
        require(
            SHA256_IDENTIFIER.fullmatch(identifier) is not None,
            f"diagram evidence {category} requires a sha256 identifier",
        )
    raw_checks = record.get("checks")
    require(isinstance(raw_checks, list), f"diagram evidence {category}.checks must be a list")
    checks: list[str] = []
    for index, raw_check in enumerate(raw_checks):
        checks.append(text_value(raw_check, f"diagram evidence {category}.checks[{index}]", maximum=100))
    require(len(checks) == len(set(checks)), f"diagram evidence {category} contains duplicate checks")
    actual = set(checks)
    expected = REQUIRED_CHECKS[category]
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    require(not missing, f"diagram evidence {category} is missing checks: {', '.join(missing)}")
    require(not extra, f"diagram evidence {category} contains unknown checks: {', '.join(extra)}")
    reject_secret_shaped_content(record)
    return category, actual


def assemble_evidence(input_directory: Path, candidate_commit: str, *, now: datetime) -> dict[str, Any]:
    require(COMMIT_PATTERN.fullmatch(candidate_commit) is not None, "candidate commit must be an exact lowercase SHA")
    paths = sorted(input_directory.rglob("*.json"))
    require(bool(paths), f"no diagram evidence fragments found in {input_directory}")

    evidence: dict[str, dict[str, Any]] = {}
    covered_checks: set[str] = set()
    for path in paths:
        try:
            raw_record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"could not read diagram evidence fragment {path}: {exc}") from exc
        record = object_value(raw_record, str(path))
        category, checks = validate_evidence_entry(record, candidate_commit, name=str(path), now=now)
        require(category not in evidence, f"duplicate diagram evidence category: {category}")
        evidence[category] = record
        covered_checks.update(checks)

    missing_categories = sorted(REQUIRED_CATEGORIES - evidence.keys())
    require(not missing_categories, f"missing diagram evidence categories: {', '.join(missing_categories)}")
    missing_checks = sorted(ALL_REQUIRED_CHECKS - covered_checks)
    require(not missing_checks, f"diagram release evidence is missing checks: {', '.join(missing_checks)}")
    return {
        "schema_version": 1,
        "candidate_commit": candidate_commit,
        "status": "complete",
        "covered_checks": sorted(covered_checks),
        "evidence": [evidence[category] for category in sorted(evidence)],
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    write = commands.add_parser("write", help="write one evidence fragment after a gate passes")
    write.add_argument("--category", required=True, choices=sorted(REQUIRED_CATEGORIES))
    write.add_argument("--scope-commit", required=True)
    write.add_argument("--tool", required=True)
    write.add_argument("--tool-version", required=True)
    write.add_argument("--reference", required=True)
    write.add_argument("--immutable-identifier", required=True)
    write.add_argument("--completed-at")
    write.add_argument("--output", required=True, type=Path)
    assemble = commands.add_parser("assemble", help="assemble and validate all required fragments")
    assemble.add_argument("--input-directory", required=True, type=Path)
    assemble.add_argument("--candidate-commit", required=True)
    assemble.add_argument("--output", required=True, type=Path)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "write":
            result = build_evidence(
                category=args.category,
                scope_commit=args.scope_commit,
                tool=args.tool,
                tool_version=args.tool_version,
                reference=args.reference,
                immutable_identifier=args.immutable_identifier,
                completed_at=args.completed_at or datetime.now(UTC).isoformat(),
            )
        else:
            result = assemble_evidence(
                args.input_directory,
                args.candidate_commit,
                now=datetime.now(UTC),
            )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(f"Diagram release evidence failed: {exc}", file=sys.stderr)
        return 1
    if args.command == "write":
        print(f"Wrote {result['category']} diagram evidence for {result['scope_commit']}.")
    else:
        print(
            f"Assembled {len(result['evidence'])} diagram evidence records "
            f"covering {len(result['covered_checks'])} required checks for {result['candidate_commit']}."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
