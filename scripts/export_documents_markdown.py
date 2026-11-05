#!/usr/bin/env python3
"""Copy current, accessible TekDocs documents to a new local directory."""

import argparse
import getpass
import hashlib
import ipaddress
import json
import os
import re
import sys
from datetime import UTC, datetime
from http.client import HTTPException
from pathlib import Path
from urllib import error, parse, request
from uuid import UUID

MAX_RESPONSE_BYTES = 32 * 1024 * 1024


class ExportError(Exception):
    """A safe message suitable for the terminal and export index."""


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ExportError("Redirect refused; use the installation's final URL.")


class Client:
    def __init__(self, url, token):
        parts = parse.urlsplit(url)
        try:
            loopback = parts.hostname == "localhost" or ipaddress.ip_address(parts.hostname).is_loopback
        except ValueError:
            loopback = False
        if (
            not parts.hostname or parts.username or parts.password or parts.query or parts.fragment
            or parts.path not in ("", "/")
            or (parts.scheme != "https" and not (parts.scheme == "http" and loopback))
        ):
            raise ExportError("Use an HTTPS installation origin (HTTP is allowed only on loopback).")
        if not token or any(ord(char) < 33 or ord(char) > 126 for char in token):
            raise ExportError("A nonempty API token without spaces is required.")
        self.url = url.rstrip("/")
        self.token = token
        self.opener = request.build_opener(NoRedirect())

    def get(self, path, *, markdown=False, missing_ok=False):
        # The constructor permits only HTTPS or loopback HTTP; paths are generated here.
        req = request.Request(self.url + path, headers={  # noqa: S310
            "Authorization": f"Bearer {self.token}",
            "Accept": "text/markdown" if markdown else "application/json",
        })
        try:
            with self.opener.open(req, timeout=60) as response:
                content_type = response.headers.get_content_type()
                expected = "text/markdown" if markdown else "application/json"
                if content_type != expected:
                    raise ExportError("Unexpected response type; no document was saved.")
                data = response.read(MAX_RESPONSE_BYTES + 1)
        except error.HTTPError as exc:
            if exc.code == 404 and missing_ok:
                return None
            raise ExportError(f"HTTP {exc.code}; check token permissions and document availability.") from None
        except (error.URLError, OSError, ValueError, HTTPException):
            raise ExportError("Request failed; check the installation URL and connection.") from None
        if len(data) > MAX_RESPONSE_BYTES:
            raise ExportError("Response exceeds the 32 MiB export limit.")
        try:
            return data.decode("utf-8") if markdown else json.loads(data)
        except (UnicodeError, ValueError):
            raise ExportError("Invalid UTF-8 or JSON response.") from None

    def pages(self, path, page_size, *, repository=False):
        expected_count = None
        received = 0
        head = None
        for page in range(1, 100001):
            separator = "&" if "?" in path else "?"
            result = self.get(f"{path}{separator}page={page}&page_size={page_size}")
            if not isinstance(result, dict) or not isinstance(result.get("results"), list):
                raise ExportError("Invalid document or Workspace listing.")
            count = result.get("count")
            if count is not None:
                if not isinstance(count, int) or count < 0 or (expected_count is not None and count != expected_count):
                    raise ExportError("Inventory changed or has an invalid count; retry the export.")
                expected_count = count
            if repository:
                current = result.get("accepted_commit")
                if current != result.get("indexed_commit") or (page > 1 and current != head):
                    raise ExportError("Repository inventory is stale or changed during export; retry.")
                head = current
            received += len(result["results"])
            yield from result["results"]
            if result.get("has_more") is False:
                if expected_count is not None and received != expected_count:
                    raise ExportError("Inventory count does not match received records; export is incomplete.")
                return
            if result.get("has_more") is not True or not result["results"]:
                raise ExportError("Invalid pagination; export may be incomplete.")
        raise ExportError("Pagination limit reached; export may be incomplete.")


def identifier(value):
    return str(UUID(str(value)))


def save_private(path, content):
    stream = open(path, "x", encoding="utf-8", opener=lambda p, flags: os.open(p, flags, 0o600))
    try:
        with stream:
            stream.write(content)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def export(client, output):
    # A fresh private directory avoids overwriting any earlier copy.
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    index = {
        "started_at": datetime.now(UTC).isoformat(),
        "complete": False,
        "description": "Current readable Markdown only; not a backup of history, files or publications.",
        "documents": [], "failures": [],
    }
    scopes = [("msp", "/api/v1/documents", "/api/v1/workspaces/msp")]
    try:
        for organization in client.pages("/api/v1/workspaces/organizations", 25):
            org_id = identifier(organization["id"])
            root = f"/api/v1/workspaces/organizations/{org_id}"
            scopes.append((org_id, root + "/documents", root))
    except (ExportError, ValueError, KeyError, TypeError) as exc:
        index["failures"].append({"scope": "organization discovery", "error": safe_error(exc)})

    for scope, collection, root in scopes:
        documents = {}
        try:
            for document in client.pages(collection + "/search", 100):
                content_id = identifier(document.get("content_id", document["id"]))
                if content_id in documents:
                    raise ExportError("Duplicate document in listing; retry when edits have stopped.")
                documents[content_id] = document
        except (ExportError, ValueError, KeyError, TypeError) as exc:
            index["failures"].append({"scope": scope, "error": safe_error(exc)})
        try:
            graph_seen = set()
            for document in client.pages(root + "/content-graph/documents?kind=document", 100, repository=True):
                content_id = identifier(document["id"])
                if content_id in graph_seen or document["kind"] != "document":
                    raise ExportError("Invalid or duplicate repository document inventory.")
                graph_seen.add(content_id)
                if content_id not in documents:
                    if document.get("repository_native") is False:
                        continue  # An archived/shadow legacy document is not a new native document.
                    if document.get("repository_native") is not True:
                        raise ExportError(
                            "Cannot classify an unlisted Git document; update the server before exporting."
                        )
                    documents[content_id] = {
                        "id": content_id, "content_id": content_id, "title": document["title"],
                        "content_authority": "repository", "repository_native": True,
                    }
        except (ExportError, ValueError, KeyError, TypeError) as exc:
            index["failures"].append({"scope": scope, "error": safe_error(exc)})
        try:
            for document in documents.values():
                entry = {"scope": scope}
                try:
                    doc_id = identifier(document["id"])
                    entry["id"] = doc_id
                    title = document["title"]
                    if not isinstance(title, str):
                        raise ExportError("Invalid document title.")
                    entry["title"] = title
                    authority = document["content_authority"]
                    if authority not in ("repository", "legacy"):
                        raise ExportError("Unknown document authority; no document was saved.")
                    markdown = None if document.get("repository_native") else client.get(
                        collection + f"/{doc_id}/export?export_format=md",
                        markdown=True, missing_ok=authority == "repository",
                    )
                    if markdown is None:
                        content_id = identifier(document["content_id"])
                        detail = client.get(root + f"/content-graph/documents/{content_id}")
                        markdown = detail["markdown"]
                        entry["findings"] = detail.get("findings", [])
                        entry["representation"] = "repository composition; review TekDocs key/entity/file references"
                    else:
                        entry["representation"] = "editable Markdown export"
                    if not isinstance(markdown, str):
                        raise ExportError("Invalid Markdown response.")
                    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:70] or "document"
                    filename = f"{scope}-{slug}-{doc_id}.md"
                    save_private(output / filename, markdown)
                    entry.update(file=filename, empty=not markdown.strip(),
                                 sha256=hashlib.sha256(markdown.encode("utf-8")).hexdigest())
                    index["documents"].append(entry)
                except (ExportError, ValueError, KeyError, TypeError, OSError) as exc:
                    index["failures"].append({**entry, "error": safe_error(exc)})
        except (ExportError, ValueError, KeyError, TypeError) as exc:
            index["failures"].append({"scope": scope, "error": safe_error(exc)})
    index["finished_at"] = datetime.now(UTC).isoformat()
    index["complete"] = not index["failures"]
    save_private(output / "index.json", json.dumps(index, ensure_ascii=False, indent=2) + "\n")
    return index


def safe_error(exc):
    return str(exc) if isinstance(exc, ExportError) else "Invalid API record or local file write failure."


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Installation origin, e.g. https://docs.example.com")
    parser.add_argument("--output", type=Path, required=True, help="New local directory; parent must exist")
    args = parser.parse_args(argv)
    try:
        token = os.environ.get("TEKDOCS_API_TOKEN") or getpass.getpass("TekDocs API token: ")
        index = export(Client(args.url, token), args.output.expanduser())
    except (ExportError, OSError, ValueError, EOFError):
        print("Export could not finish. Check the URL, token, and a new output path; retain any saved files.",
              file=sys.stderr)
        return 1
    documents = index["documents"]
    empty = sum(entry["empty"] for entry in documents)
    warnings = sum(bool(entry.get("findings")) for entry in documents)
    failures = len(index["failures"])
    print(f"Saved {len(documents)} document(s); {empty} empty; {warnings} with findings; {failures} failure(s).")
    print("Review index.json and open the Markdown files before changing or removing the originals.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
