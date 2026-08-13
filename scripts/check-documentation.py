from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / ".github" / "wiki-pages.json"
HELP_TOPICS = ROOT / "frontend" / "src" / "help" / "topics.ts"
LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
SLUG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")


def fail(message: str) -> None:
    raise ValueError(message)


def check_local_link(source: Path, raw_target: str, boundary: Path) -> None:
    target = raw_target.strip().strip("<>").split(maxsplit=1)[0]
    if not target or target.startswith(("#", "http://", "https://", "mailto:", "tekdocs://")):
        return
    file_target = unquote(target.split("#", 1)[0])
    resolved = (source.parent / file_target).resolve()
    if boundary not in resolved.parents and resolved != boundary:
        fail(f"{source.relative_to(boundary)} links outside its documentation boundary: {raw_target}")
    if not resolved.exists():
        fail(f"{source.relative_to(boundary)} has a missing link target: {raw_target}")


def check_markdown_links(paths: set[Path], boundary: Path) -> None:
    for source in sorted(path for path in paths if path.suffix.lower() == ".md"):
        for target in LINK_PATTERN.findall(source.read_text(encoding="utf-8")):
            check_local_link(source, target, boundary)


def check_manifest(wiki_checkout: Path | None) -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    pages = data.get("pages")
    if not isinstance(pages, list) or not pages:
        fail("Wiki manifest has no pages")

    slugs: set[str] = set()
    sources: set[Path] = set()
    audiences: set[str] = set()
    contextual: set[str] = set()
    for page in pages:
        slug = page.get("slug")
        if not isinstance(slug, str) or not SLUG_PATTERN.fullmatch(slug):
            fail(f"Invalid Wiki slug: {slug!r}")
        if slug in slugs:
            fail(f"Duplicate Wiki slug: {slug}")
        slugs.add(slug)
        audience = page.get("audience")
        if audience not in {"end_user", "operator", "security", "api"}:
            fail(f"Invalid audience for {slug}: {audience!r}")
        audiences.add(audience)
        if page.get("contextual") is True:
            contextual.add(slug)
        page_sources = page.get("sources")
        if not isinstance(page_sources, list) or not page_sources:
            fail(f"Wiki page {slug} has no reviewed source coverage")
        for relative in page_sources:
            source = (ROOT / relative).resolve()
            if ROOT not in source.parents or not source.is_file():
                fail(f"Wiki page {slug} has a missing or unsafe source: {relative}")
            sources.add(source)

    required_audiences = {"end_user", "operator", "security", "api"}
    if audiences != required_audiences:
        fail(f"Wiki audience coverage drifted: {sorted(audiences)}")

    topic_slugs = set(re.findall(r"slug: '([^']+)'", HELP_TOPICS.read_text(encoding="utf-8")))
    if topic_slugs != contextual:
        fail(
            "Contextual help/Wiki drift: "
            f"missing in manifest={sorted(topic_slugs - contextual)}, "
            f"missing in app={sorted(contextual - topic_slugs)}"
        )

    check_markdown_links(sources, ROOT)

    if wiki_checkout is not None:
        resolved_wiki = wiki_checkout.resolve()
        if not (resolved_wiki / ".git").exists():
            fail(f"Wiki checkout is not a Git worktree: {resolved_wiki}")
        missing_pages = sorted(slug for slug in slugs if not (resolved_wiki / f"{slug}.md").is_file())
        if missing_pages:
            fail(f"Published Wiki checkout is missing pages: {missing_pages}")
        check_markdown_links({resolved_wiki / f"{slug}.md" for slug in slugs}, resolved_wiki)

    print(
        f"Documentation contract passed: {len(slugs)} Wiki pages, "
        f"{len(contextual)} contextual topics, {len(sources)} reviewed sources."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate TekDocs documentation and Wiki drift")
    parser.add_argument("--wiki-checkout", type=Path)
    args = parser.parse_args()
    try:
        check_manifest(args.wiki_checkout)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Documentation contract failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
