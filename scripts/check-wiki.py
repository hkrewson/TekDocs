#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / ".github" / "wiki-pages.json"
TOPICS = ROOT / "frontend" / "src" / "help" / "topics.ts"
SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")
LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def validate(wiki: Path | None) -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    pages = data.get("pages")
    if not isinstance(pages, list) or len(pages) != 37:
        raise ValueError("Wiki manifest must define exactly 37 public pages")

    slugs: set[str] = set()
    contextual: set[str] = set()
    audiences: set[str] = set()
    for page in pages:
        slug = page.get("slug")
        audience = page.get("audience")
        if not isinstance(slug, str) or not SLUG.fullmatch(slug) or slug in slugs:
            raise ValueError(f"unsafe or duplicate Wiki slug: {slug!r}")
        if audience not in {"end_user", "operator", "security", "api"}:
            raise ValueError(f"invalid audience for {slug}: {audience!r}")
        slugs.add(slug)
        audiences.add(audience)
        if page.get("contextual") is True:
            contextual.add(slug)

    if audiences != {"end_user", "operator", "security", "api"}:
        raise ValueError(f"Wiki audience coverage drifted: {sorted(audiences)}")
    topic_slugs = set(re.findall(r"slug: '([^']+)'", TOPICS.read_text(encoding="utf-8")))
    if topic_slugs != contextual:
        raise ValueError(
            f"contextual help drift: manifest-only={sorted(contextual - topic_slugs)}, "
            f"application-only={sorted(topic_slugs - contextual)}"
        )

    if wiki is None:
        print(f"Wiki contract passed: {len(slugs)} pages and {len(contextual)} contextual topics")
        return

    checkout = wiki.resolve()
    if not (checkout / ".git").exists():
        raise ValueError(f"not a Git Wiki checkout: {checkout}")
    missing = sorted(slug for slug in slugs if not (checkout / f"{slug}.md").is_file())
    if missing:
        raise ValueError(f"Wiki checkout is missing pages: {missing}")
    # The manifest owns required product/help pages, not the entire operator
    # manual. Retain supplemental setup guides and check their links as well.
    page_paths = {
        path.stem: path
        for path in checkout.glob("*.md")
        if path.is_file() and SLUG.fullmatch(path.stem)
    }
    for source in list(page_paths.values()) + [checkout / "_Sidebar.md"]:
        if not source.is_file():
            raise ValueError(f"Wiki checkout is missing {source.name}")
        for raw_target in LINK.findall(source.read_text(encoding="utf-8")):
            target = raw_target.strip().strip("<>").split(maxsplit=1)[0]
            if not target or target.startswith(("#", "https://", "mailto:")):
                continue
            linked_slug = unquote(target.split("#", 1)[0]).removesuffix(".md")
            if linked_slug not in page_paths:
                raise ValueError(f"{source.name} has an unknown local page link: {raw_target}")
    print(
        f"Wiki checkout passed: {len(slugs)} required pages, "
        f"{len(page_paths)} total pages and local links are complete"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the TekDocs GitHub Wiki contract")
    parser.add_argument("--checkout", type=Path)
    args = parser.parse_args()
    try:
        validate(args.checkout)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Wiki contract failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
