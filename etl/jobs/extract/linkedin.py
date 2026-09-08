import re

from etl.jobs.config import (
    BODY_END_ANCHORS,
    BODY_START_ANCHOR,
    CONTRACT_TYPES,
    MIN_BODY_LENGTH,
    MODALITIES,
)
from .extract import (
    JobDescriptionNotFound,
    _clean_html,
)


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


def _source_from_url(source_url: str | None) -> dict:
    """
    Pairs the origin URL with the job id read out of it.

    Args:
        source_url (str | None): The URL the page was saved from.
    """
    if source_url is None:
        return {"source_url": None, "linkedin_job_id": None}

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


def extract(html_content: str, source_info: dict):
    """
    Extracts a saved job posting from its markup.

    Args:
        html_content (str): The raw HTML content.
        source_info (dict): Origin metadata from the common reader.
    """
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
        "header": {
            **header,
            **_source_from_url(source_info["source_url"]),
        },
        "body": body
    }
