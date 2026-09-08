"""Orchestration for saved job-posting extracts."""

from datetime import datetime, timezone
from email import policy
from pathlib import Path

import email
import re

from bs4 import BeautifulSoup


_SAVED_URL_RE = re.compile(r"saved from url=\(\d+\)([^\s\->]+)")


class JobDescriptionNotFound(Exception):
    """Raised when a saved page carries no usable job description."""


class UnsupportedJobSource(ValueError):
    """Raised when no source-specific extractor is registered for a page."""


def _clean_html(html_content: str) -> str:
    """Remove non-readable tags and collapse the remaining page text."""
    soup = BeautifulSoup(html_content, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()


def _read_mhtml(path: Path) -> tuple[str, str | None]:
    """Read the HTML document and origin URL from a browser MHTML archive."""
    with path.open("rb") as handle:
        message = email.message_from_binary_file(handle, policy=policy.default)

    part = next(
        (part for part in message.walk() if part.get_content_type() == "text/html"),
        None,
    )
    if part is None:
        raise JobDescriptionNotFound("archive carries no HTML part")

    # Saved pages declare no charset even though their HTML is UTF-8.  Decode
    # the payload explicitly so localized anchors remain intact.
    html_content = part.get_payload(decode=True).decode("utf-8")

    return html_content, message["Snapshot-Content-Location"]


def read_saved_page(path: Path) -> tuple[str, dict]:
    """Read a saved page and return its HTML plus source metadata."""
    if path.suffix.lower() == ".mhtml":
        html_content, source_url = _read_mhtml(path)
    else:
        with path.open(encoding="utf-8") as handle:
            html_content = handle.read()

        match = _SAVED_URL_RE.search(html_content[:4000])
        source_url = match.group(1) if match else None

    return html_content, {"source_url": source_url}


def extractor_for(source_url: str | None):
    """Return the parser module registered for a saved page's source."""
    if source_url and "linkedin.com" in source_url.casefold():
        # Lazy import avoids a package-initialization cycle: the LinkedIn
        # adapter imports shared helpers from this module.
        from . import linkedin

        return linkedin

    raise UnsupportedJobSource(f"no extractor registered for {source_url!r}")


def scrape_date_from(path: Path) -> str:
    """Return the UTC calendar date on which the browser saved the file."""
    mtime = path.stat().st_mtime
    return datetime.fromtimestamp(mtime, tz=timezone.utc).date().isoformat()


def extract_from_file(path: Path) -> dict:
    """Extract a saved posting through the source-specific parser."""
    html, source_info = read_saved_page(path)
    extractor = extractor_for(source_info["source_url"])
    result = extractor.extract(html, source_info)
    result["scrape_date"] = scrape_date_from(path)

    return result
