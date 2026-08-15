from datetime import datetime, timezone
from pathlib import Path

import re

from bs4 import BeautifulSoup

from etl.jobs.config import (
    BODY_END_ANCHORS,
    BODY_START_ANCHOR,
    CONTRACT_TYPES,
    MIN_BODY_LENGTH,
    MODALITIES,
)


_SOURCE_URL_RE = re.compile(r"saved from url=\(\d+\)([^\s\->]+)")
_JOB_ID_RE = re.compile(r"/jobs/view/(\d+)")
_TITLE_SUFFIX = " | LinkedIn"
_POSTED_RE = re.compile(
    r"hace\s+(?:más de\s+)?(\d+)\s+"
    r"(minutos?|horas?|días?|semanas?|meses|mes|años?)"
)
_POSTED_ANCHOR_RE = re.compile(r"·\s*(?:Compartido\s+)?hace")

# Coarse by design: LinkedIn only ever reports elapsed time, so a posting
# listed as "hace 3 meses" cannot be resolved more precisely than this.
_UNIT_DAYS = {
    "minuto": 0,
    "minutos": 0,
    "hora": 0,
    "horas": 0,
    "día": 1,
    "días": 1,
    "semana": 7,
    "semanas": 7,
    "mes": 30,
    "meses": 30,
    "año": 365,
    "años": 365,
}


class JobDescriptionNotFound(Exception):
    """Raised when a saved page carries no usable job description."""


def _clean_html(html_content: str) -> str:
    """
    Cleans the HTML content by removing unnecessary tags and whitespace.

    Args:
        html_content (str): The raw HTML content.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()


def _extract_source(html_content: str) -> dict:
    """
    Extracts the origin URL and job id from the browser's save comment.

    The job id must come from this comment and not from the document body,
    where the recommended-jobs rail contributes ids of unrelated postings.

    Args:
        html_content (str): The raw HTML content.
    """
    match = _SOURCE_URL_RE.search(html_content[:4000])
    if match is None:
        return {"source_url": None, "linkedin_job_id": None}

    source_url = match.group(1)
    job_id = _JOB_ID_RE.search(source_url)

    return {
        "source_url": source_url,
        "linkedin_job_id": int(job_id.group(1)) if job_id else None,
    }


def _extract_posted(header: str) -> dict:
    """
    Extracts how long ago the posting was published.

    Args:
        header (str): The text preceding the job description.
    """
    match = _POSTED_RE.search(header)
    if match is None:
        return {"posted_raw": None, "posted_days_ago": None}

    amount = int(match.group(1))

    return {
        "posted_raw": match.group(0),
        "posted_days_ago": amount * _UNIT_DAYS[match.group(2)],
    }


def _extract_location(header: str, position_name: str | None) -> str | None:
    """
    Extracts the job location, which sits between the title and the
    publication date.

    Args:
        header (str): The text preceding the job description.
        position_name (str | None): The title used to find where the
            location starts.
    """
    match = _POSTED_ANCHOR_RE.search(header)
    if match is None:
        return None

    segment = header[: match.start()]
    if position_name:
        title_at = segment.rfind(position_name)
        if title_at >= 0:
            segment = segment[title_at + len(position_name) :]

    return segment.strip(" ·") or None


def _longest_common_suffix(left: str, right: str) -> str:
    """
    Returns the longest string that ends both arguments.

    Args:
        left (str): First string.
        right (str): Second string.
    """
    length = 0
    limit = min(len(left), len(right))
    while length < limit and left[-1 - length] == right[-1 - length]:
        length += 1

    return left[len(left) - length :] if length else ""


def _extract_company(header: str, full_title: str) -> str | None:
    """
    Extracts the company name from the page title.

    The title reads "{position} | {company}", but both halves may contain a
    pipe of their own, so the split point is confirmed against the subheader
    line "{company} • {location}" whenever LinkedIn renders one.

    Args:
        header (str): The text preceding the job description.
        full_title (str): The page title, without its " | LinkedIn" suffix.
    """
    bullet = header.find("•")
    if bullet >= 0:
        subheader = header[:bullet].rstrip()
        company = _longest_common_suffix(full_title, subheader).strip()
        if company:
            return company

    return full_title.rpartition("|")[2].strip() or None


def _extract_header(cleaned_html: str) -> dict:
    """
    Extracts the header information from the cleaned HTML content.

    Args:
        cleaned_html (str): The cleaned HTML content.
    """
    header = cleaned_html.split(BODY_START_ANCHOR, 1)[0]

    position_name = None
    company_name = None
    title_end = cleaned_html.find(_TITLE_SUFFIX)
    if title_end >= 0:
        full_title = cleaned_html[:title_end].strip()
        company_name = _extract_company(header, full_title)
        if company_name and full_title.endswith(company_name):
            position_name = full_title[: -len(company_name)].strip(" |") or None
        else:
            position_name = full_title.rpartition("|")[0].strip() or None

    modality = next((m for m in MODALITIES if m in header), None)
    contract_type = next((c for c in CONTRACT_TYPES if c in header), None)

    return {
        "position_name": position_name,
        "company_name": company_name,
        "location": _extract_location(header, position_name),
        # Left as the interface label: mapping to days_at_the_office is the
        # loader's call, since "Híbrido" carries no day count.
        "modality": modality,
        "contract_type": contract_type,
        **_extract_posted(header),
    }


def _extract_body(cleaned_html: str) -> str | None:
    """
    Extracts the body content from the cleaned HTML content.

    Args:
        cleaned_html (str): The cleaned HTML content.
    """
    start = cleaned_html.find(BODY_START_ANCHOR)
    if start < 0:
        return None
    start += len(BODY_START_ANCHOR)

    end = len(cleaned_html)
    for anchor in BODY_END_ANCHORS:
        at = cleaned_html.find(anchor, start)
        if at >= 0:
            end = min(end, at)

    return cleaned_html[start:end].strip()


def extract_from_html(html_content: str):
    cleaned_html = _clean_html(html_content)
    header = _extract_header(cleaned_html)
    body = _extract_body(cleaned_html)

    if body is None or len(body) < MIN_BODY_LENGTH:
        raise JobDescriptionNotFound(
            f"description missing or too short "
            f"({0 if body is None else len(body)} chars); "
            f"the page was likely saved before it rendered"
        )

    return {
        "header": {**header, **_extract_source(html_content)},
        "body": body
    }


def extract_from_file(path) -> dict:
    """
    Extracts a saved job posting from disk.

    Args:
        path: Path to the saved LinkedIn HTML file.
    """
    path = Path(path)
    # Explicit encoding: the saved pages are UTF-8, and falling back to a
    # locale default silently mangles the accented anchors above.
    with path.open(encoding="utf-8") as handle:
        extracted = extract_from_html(handle.read())

    # The file's mtime is when the browser wrote the page, which is the moment
    # it was scraped. Captured here at the one point that still holds the file,
    # so transform can carry it and load never has to guess. Date precision to
    # match FactJob.scrape_date and the post_date it is walked back from.
    mtime = path.stat().st_mtime
    extracted["scrape_date"] = datetime.fromtimestamp(mtime, tz=timezone.utc).date().isoformat()

    return extracted
