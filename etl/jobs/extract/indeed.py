"""Indeed-specific parser for browser-saved job postings."""

from html import unescape
from urllib.parse import parse_qs, quote, urlparse

import re

from bs4 import BeautifulSoup

from etl.jobs.config import MIN_BODY_LENGTH
from .exceptions import JobDescriptionNotFound


def _text(node) -> str | None:
    """Return compact readable text from one selected DOM node."""
    if node is None:
        return None

    text = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
    return text or None


def _description_text(node) -> str | None:
    """Keep paragraph and list boundaries in the job description."""
    if node is None:
        return None

    for tag in node.find_all(["script", "style", "noscript"]):
        tag.decompose()

    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in node.get_text("\n", strip=True).splitlines()
    ]
    body = "\n".join(line for line in lines if line)
    return unescape(body) or None


def _description_node(soup: BeautifulSoup):
    """Find the description in desktop and mobile Indeed snapshots."""
    # Desktop Indeed pages use the long-standing id.  Mobile snapshots use a
    # React Native HTML wrapper instead and do not render that id at all.
    for selector in (
        "#jobDescriptionText",
        '[data-testid="vj-job-description"]',
        "div.simple-job-description-html",
    ):
        node = soup.select_one(selector)
        if node is not None:
            return node
    return None


def _source_from_url(source_url: str | None, soup: BeautifulSoup) -> dict:
    """Resolve Indeed's ``jk`` id and keep a canonical job URL."""
    canonical = soup.select_one('meta[property="og:url"]')
    candidate = canonical.get("content") if canonical else source_url
    candidate = candidate or source_url

    parsed = urlparse(candidate or "")
    job_id = parse_qs(parsed.query).get("jk", [None])[0]
    if job_id is None:
        raise ValueError("Indeed source URL has no jk job id")

    base_url = f"{parsed.scheme or 'https'}://{parsed.netloc or 'ar.indeed.com'}"
    return {
        "source": "indeed",
        "source_url": f"{base_url}/viewjob?jk={quote(job_id)}",
        "source_job_id": job_id,
    }


def _extract_title(soup: BeautifulSoup) -> str | None:
    return _text(
        soup.select_one('[data-testid="jobsearch-JobInfoHeader-title"]')
        or soup.select_one('[data-testid="vj-job-title"]')
        or soup.select_one("h1")
    )


def _extract_company(soup: BeautifulSoup) -> str | None:
    return _text(
        soup.select_one('[data-testid="inlineHeader-companyName"]')
        or soup.select_one('[data-company-name="true"]')
        or soup.select_one('[data-testid="company-info-metadata"] a')
    )


def _extract_location(soup: BeautifulSoup) -> str | None:
    return _text(
        soup.select_one('[data-testid="inlineHeader-companyLocation"]')
        or soup.select_one('[data-testid="jobsearch-JobInfoHeader-companyLocation"]')
        or soup.select_one("#jobLocationText")
        or soup.select_one(
            '[data-testid="company-info-metadata"] > div > div:nth-child(2)'
        )
        or soup.select_one('[data-testid="company-info-metadata"] > div:nth-child(2)')
    )


def _extract_contract_type(soup: BeautifulSoup) -> str | None:
    return _text(soup.select_one("#salaryInfoAndJobType"))


def extract(html_content: str, source_info: dict) -> dict:
    """Extract one Indeed posting into the normalized job extract shape."""
    soup = BeautifulSoup(html_content, "html.parser")
    body = _description_text(_description_node(soup))

    if body is None or len(body) < MIN_BODY_LENGTH:
        raise JobDescriptionNotFound(
            f"description missing or too short "
            f"({0 if body is None else len(body)} chars); "
            "the Indeed page was likely saved before it rendered"
        )

    source = _source_from_url(source_info.get("source_url"), soup)
    return {
        "header": {
            **source,
            "position_name": _extract_title(soup),
            "company_name": _extract_company(soup),
            "location": _extract_location(soup),
            "modality": None,
            "contract_type": _extract_contract_type(soup),
            "posted_raw": None,
            "posted_days_ago": None,
        },
        "body": body,
    }
